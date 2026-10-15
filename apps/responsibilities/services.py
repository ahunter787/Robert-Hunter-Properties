"""Staging a property's bills and dividing them between its units.

E2. The office stages each cycle before its months arrive, RHP proposes each unit's
monthly share from the property's recorded sizes, and **the office's figures are
what the ledger charges** — no percentage is re-applied at charge time (ADR-014).

Once a month has been charged, its cycle and shares are history: a correction
belongs on the ledger, as an adjustment, so the record shows both what was billed
and what corrected it (ADR-008).
"""

import datetime as dt
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.ledger.models import Charge, ChargeKind
from apps.properties.models import Property, Unit
from apps.responsibilities.models import (
    PropertyResponsibility,
    ResponsibilityCategory,
    ResponsibilityCycle,
    ResponsibilityShare,
)

ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def _actor(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


# --- reading a property's bills for a screen ------------------------------


@dataclass
class ShareRow:
    """One unit's place in a cycle, as the property screen shows it."""

    unit: Unit
    share_of_property: Decimal | None
    monthly_amount: Decimal
    has_lease: bool
    note: str = ""


@dataclass
class ResponsibilityRow:
    """One responsibility, its cycles, and who is carrying it today."""

    responsibility: PropertyResponsibility
    current_cycle: ResponsibilityCycle | None
    next_cycle: ResponsibilityCycle | None
    shares: list[ShareRow] = field(default_factory=list)

    @property
    def monthly_total(self) -> Decimal:
        if self.current_cycle is None:
            return ZERO
        return self.current_cycle.monthly_total

    @property
    def allocated_monthly(self) -> Decimal:
        return sum((row.monthly_amount for row in self.shares), ZERO)

    @property
    def landlord_monthly(self) -> Decimal:
        """The part of the bill nobody's unit is carrying, so it stays visible."""
        return max(self.monthly_total - self.allocated_monthly, ZERO)


def property_overview(property_obj: Property) -> list[ResponsibilityRow]:
    """Every responsibility on a property, with its current cycle and shares.

    Read-only and shaped for the property screen; the shares shown are the current
    cycle's, which is what a tenant is being charged this month.
    """
    units = list(property_obj.units.order_by("identifier"))
    rows: list[ResponsibilityRow] = []
    for responsibility in property_obj.responsibilities.order_by("label"):
        current = responsibility.current_cycle()
        staged = responsibility.next_cycle()
        cycle = current or staged
        shares: list[ShareRow] = []
        if cycle is not None:
            by_unit = {share.unit_id: share for share in cycle.shares.all()}
            shares = [
                ShareRow(
                    unit=unit,
                    share_of_property=unit.share_of_property,
                    monthly_amount=(
                        by_unit[unit.pk].monthly_amount if unit.pk in by_unit else ZERO
                    ),
                    has_lease=unit.current_lease is not None,
                    note=by_unit[unit.pk].note if unit.pk in by_unit else "",
                )
                for unit in units
            ]
        rows.append(
            ResponsibilityRow(
                responsibility=responsibility,
                current_cycle=current,
                next_cycle=staged,
                shares=shares,
            )
        )
    return rows


# --- staging ---------------------------------------------------------------


def next_cycle_start(responsibility: PropertyResponsibility) -> dt.date:
    """The date a property's next cycle would start: the day after the last one ends.

    A quarterly bill that ran to the end of July is followed by one starting on
    1 August, which is what the office would type anyway.
    """
    cycles = responsibility.cycles_ordered()
    if not cycles:
        return timezone.localdate().replace(day=1)
    last = cycles[-1]
    following = last.ends_on + dt.timedelta(days=1)
    return following


def cycle_is_locked(cycle: ResponsibilityCycle) -> bool:
    """Whether anything has been charged for the months this cycle covers."""
    if cycle.pk is None:
        return False
    return Charge.objects.filter(
        kind=ChargeKind.RESPONSIBILITY,
        responsibility=cycle.responsibility_id,
        due_date__range=(cycle.starts_on, cycle.ends_on),
    ).exists()


def _refuse_locked(cycle: ResponsibilityCycle) -> None:
    if cycle_is_locked(cycle):
        raise ValidationError(
            "That cycle's months have already been charged. Correct the charges with "
            "adjustments instead of changing what the property was billed."
        )


def propose_shares(cycle: ResponsibilityCycle) -> dict[int, Decimal]:
    """Each active unit's monthly share of a cycle, before the office edits it.

    A unit's recorded size gives its share; when no unit in the property records a
    size, the bill is split evenly and the screen says so. The proposals add up to the
    bill exactly, so the office never has to find a penny by hand.
    """
    units = list(cycle.responsibility.property.units.filter(is_active=True))
    if not units:
        return {}

    monthly = cycle.monthly_total
    sized = [unit for unit in units if unit.share_of_property is not None]
    if len(sized) == len(units):
        amounts = {
            unit.pk: (monthly * unit.share_of_property / HUNDRED).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            for unit in units
        }
    else:
        even = (monthly / len(units)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        amounts = {unit.pk: even for unit in units}
    return _absorb_rounding(amounts, monthly)


def _absorb_rounding(amounts: dict[int, Decimal], cap: Decimal) -> dict[int, Decimal]:
    """Make the proposals add up to ``cap`` exactly, the rounding riding the largest share.

    Two units at 42.03% and 57.97% of 233.33 round to 98.07 and 135.26, which happens to be
    exact; three units rarely are. A remainder left floating would make the office hunt for a
    penny and make the ceiling check arbitrary, so the largest share carries it.
    """
    if not amounts:
        return amounts
    difference = cap - sum(amounts.values(), ZERO)
    if difference == ZERO:
        return amounts
    largest = max(amounts, key=lambda unit_id: amounts[unit_id])
    if amounts[largest] + difference < ZERO:
        # Nothing sensible to absorb it: leave the proposals as they are and let the screen
        # show the remainder.
        return amounts
    amounts[largest] += difference
    return amounts


#: What the office reads when the unit amounts add up to more than the bill.
OVER_THE_BILL = (
    "The unit amounts add up to {total} a month, and this bill is {cap} a month to divide. "
    "Take {over} off the amounts."
)


def check_share_total(cycle: ResponsibilityCycle, amounts_by_unit) -> Decimal:
    """Refuse unit amounts that add up to more than one month of the bill.

    The bill is the ceiling: units divide what RHP was billed, so a division that adds up to
    more would charge the tenants more than the property cost (E2, ADR-014). The remainder
    may be *less* than the bill — a vacant unit's share, or a share nobody carries, stays
    with the owner — which is why only the ceiling is enforced and the screen shows what is
    left.
    """
    total = sum(
        (Decimal(amount) for amount in amounts_by_unit.values() if amount is not None), ZERO
    )
    cap = cycle.monthly_total
    if total > cap:
        raise ValidationError(OVER_THE_BILL.format(total=total, cap=cap, over=total - cap))
    return total


@transaction.atomic
def stage_cycle(
    responsibility: PropertyResponsibility,
    *,
    starts_on,
    total_amount: Decimal,
    months: int | None = None,
    note: str = "",
    amounts_by_unit: dict[int, Decimal] | None = None,
    actor=None,
) -> ResponsibilityCycle:
    """Stage a cycle's bill and the units' monthly amounts.

    Staging a start date that already has a cycle updates it, unless its months have
    been charged. The proposed shares are saved, so the figures the ledger will
    charge are visible and editable rather than re-derived later.
    """
    months = months or responsibility.cycle_months
    cycle = responsibility.cycles.filter(starts_on=starts_on).first()
    if cycle is not None:
        _refuse_locked(cycle)
        cycle.months = months
        cycle.total_amount = total_amount
        cycle.note = note or cycle.note
    else:
        cycle = ResponsibilityCycle(
            responsibility=responsibility,
            starts_on=starts_on,
            months=months,
            total_amount=total_amount,
            note=note,
        )
    cycle.set_by = _actor(actor) or cycle.set_by
    cycle.save()

    # Units the office typed win; units it left alone get the proposed share, so
    # the normal quarterly case is one number to enter and the unusual one is
    # overridden where it differs (ADR-014).
    amounts = {**propose_shares(cycle), **(amounts_by_unit or {})}
    _apply_shares(cycle, amounts, actor=actor)

    record(
        _actor(actor),
        AuditAction.RESPONSIBILITY_CYCLE_STAGED,
        obj=cycle,
        lease=None,
        summary=(
            f"{responsibility.label} billing period from {cycle.starts_on} scheduled at "
            f"{cycle.total_amount} ({cycle.months} month"
            f"{'' if cycle.months == 1 else 's'})"
        ),
        property=str(responsibility.property_id),
        total=cycle.total_amount,
        months=cycle.months,
        starts_on=cycle.starts_on,
    )
    return cycle


@transaction.atomic
def set_shares(
    cycle: ResponsibilityCycle, amounts_by_unit: dict[int, Decimal], *, note: str = "", actor=None
) -> list[ResponsibilityShare]:
    """Set the units' monthly amounts for one cycle, and record who did it."""
    _refuse_locked(cycle)
    shares = _apply_shares(cycle, amounts_by_unit, note=note, actor=actor)
    record(
        _actor(actor),
        AuditAction.RESPONSIBILITY_SHARES_SET,
        obj=cycle,
        lease=None,
        summary=(
            f"{cycle.responsibility.label} from {cycle.starts_on}: "
            f"{len(shares)} unit share{'' if len(shares) == 1 else 's'} set"
        ),
        property=str(cycle.responsibility.property_id),
        total=sum(amounts_by_unit.values(), ZERO),
        units=len(shares),
    )
    return shares


def _apply_shares(
    cycle: ResponsibilityCycle,
    amounts_by_unit: dict[int, Decimal],
    *,
    note: str = "",
    actor=None,
) -> list[ResponsibilityShare]:
    """Create, update or remove a cycle's shares so they match ``amounts_by_unit``.

    A zero takes a unit out of the cycle: the row is removed, so a screen does not
    have to explain a zero-dollar charge that will never be raised.
    """
    # Before anything is written: the units may not divide more than the property was billed.
    check_share_total(cycle, amounts_by_unit)
    property_id = cycle.responsibility.property_id
    valid_units = {unit.pk: unit for unit in Unit.objects.filter(property_id=property_id)}
    existing = {share.unit_id: share for share in cycle.shares.all()}
    saved: list[ResponsibilityShare] = []

    for unit_id, amount in amounts_by_unit.items():
        unit_pk = int(unit_id)
        if unit_pk not in valid_units:
            raise ValidationError("That unit is not part of this expense recovery's property.")
        if amount is None:
            continue
        amount = Decimal(amount)
        if amount < ZERO:
            raise ValidationError("A unit's share cannot be negative.")
        share = existing.pop(unit_pk, None)
        if amount == ZERO:
            if share is not None:
                share.delete()
            continue
        if share is None:
            share = ResponsibilityShare(cycle=cycle, unit_id=unit_pk)
        share.monthly_amount = amount
        if note:
            share.note = note
        share.set_by = _actor(actor) or share.set_by
        share.save()
        saved.append(share)

    for share in existing.values():
        # A unit left out of the form is no longer carrying this cycle.
        share.delete()

    return saved


@transaction.atomic
def save_responsibility(
    responsibility: PropertyResponsibility,
    *,
    label: str,
    category: str,
    cycle_months: int,
    is_active: bool,
    note: str = "",
    actor=None,
) -> PropertyResponsibility:
    """Add or change a property's responsibility, and record who did it."""
    if category not in ResponsibilityCategory.values:
        raise ValidationError({"category": "Choose a category."})
    responsibility.label = label.strip()
    responsibility.category = category
    responsibility.cycle_months = cycle_months
    responsibility.is_active = is_active
    responsibility.note = note
    responsibility.created_by = _actor(actor) or responsibility.created_by
    responsibility.save()

    record(
        _actor(actor),
        AuditAction.RESPONSIBILITY_CHANGED,
        obj=responsibility,
        lease=None,
        summary=(
            f"{responsibility.label} ({responsibility.get_category_display().lower()}) on "
            f"{responsibility.property.name}: every {responsibility.cycle_months} month"
            f"{'' if responsibility.cycle_months == 1 else 's'}"
            f"{'' if responsibility.is_active else ', stopped'}"
        ),
        property=str(responsibility.property_id),
        category=responsibility.category,
        cycle_months=responsibility.cycle_months,
        is_active=responsibility.is_active,
    )
    return responsibility

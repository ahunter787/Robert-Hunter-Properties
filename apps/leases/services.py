"""The lease terms that decide money: the rent schedule and the NNN amount.

E1. The ledger still owns every balance (ADR-008); this module owns what a lease
charges and when. Two rules hold everything together (ADR-013):

* **A value applies from a rent due date**, never from the middle of a month, so a
  step up or a new NNN starts on a date rent actually falls due.
* **A period that has already been charged is never rewritten.** A charge is
  corrected with an adjustment, not by changing what the lease used to say.
"""

import datetime as dt
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.dates import due_date_in, due_date_on_or_after
from apps.leases.models import (
    ZERO,
    FinancialCutover,
    Lease,
    LeaseAccountStatus,
    LeaseOnboarding,
    LeaseStatus,
    NnnRate,
    OnboardingMethod,
    RentPeriod,
    RentPeriodOrigin,
)
from apps.ledger.models import ChargeKind, PaymentMethod

#: The smallest amount a rent period or an NNN rate may carry.
MINIMUM_AMOUNT = Decimal("0.01")


def _date_label(value: dt.date) -> str:
    """Portal date style for human-readable audit summaries."""
    return f"{value:%b} {value.day}, {value.year}"


@dataclass
class ScheduleResult:
    """What regenerating a lease's rent schedule did, in the desk's words."""

    created: list[RentPeriod] = field(default_factory=list)
    updated: list[RentPeriod] = field(default_factory=list)
    kept: list[RentPeriod] = field(default_factory=list)
    removed: list[dt.date] = field(default_factory=list)
    #: Periods left alone because rent has already been charged against them.
    locked: list[dt.date] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated or self.removed)

    def summary(self) -> str:
        if not self.changed:
            if self.locked:
                return (
                    f"The rent schedule was already in step with the lease; "
                    f"{len(self.locked)} period{'' if len(self.locked) == 1 else 's'} "
                    f"{'is' if len(self.locked) == 1 else 'are'} already charged."
                )
            return "The rent schedule was already in step with the lease."
        parts = []
        if self.created:
            parts.append(f"{len(self.created)} period{'' if len(self.created) == 1 else 's'} added")
        if self.updated:
            parts.append(f"{len(self.updated)} updated")
        if self.removed:
            parts.append(f"{len(self.removed)} removed")
        if self.locked:
            parts.append(f"{len(self.locked)} left alone as already charged")
        return "Rent schedule: " + ", ".join(parts) + "."


def _actor(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


def _forget_cached(lease: Lease) -> None:
    """Drop the per-instance rent-period and NNN caches after writing rows.

    ``Lease.rent_for``/``nnn_for`` read the related sets once per instance, so a
    write through the same object has to say the answer has changed. Otherwise a
    freshly staged rate is invisible to the very code that just created it.
    """
    for attribute in ("_rent_period_cache", "_nnn_rate_cache"):
        if hasattr(lease, attribute):
            delattr(lease, attribute)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def first_due_on_or_after(lease: Lease, day: dt.date) -> dt.date:
    """The first date this lease's rent falls due on or after ``day``.

    The rule itself lives in ``apps.common.dates``, because a property
    responsibility works out which months its bill covers with the same question
    (E2).
    """
    return due_date_on_or_after(day, lease.rent_due_day)


def _stepped_amount(amount: Decimal, lease: Lease) -> Decimal:
    """One year's increase, rounded to a cent and then never re-derived."""
    if lease.step_up_percent is not None:
        grown = amount * (Decimal("1") + (lease.step_up_percent / Decimal("100")))
    else:
        grown = amount + lease.step_up_amount
    return grown.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def planned_periods(lease: Lease) -> list[tuple[dt.date, Decimal, str]]:
    """The periods this lease's template asks for: ``(date, amount, origin)``.

    A fixed lease plans nothing — it answers its stored rent for the whole term —
    so this is only ever called for a step-up or triple-net lease.
    """
    base = first_due_on_or_after(lease, lease.start_date)
    planned = [(base, lease.monthly_rent, RentPeriodOrigin.BASE)]
    if lease.step_up_month is None:
        return planned

    year = base.year
    while True:
        candidate = due_date_in(year, lease.step_up_month, lease.rent_due_day)
        if candidate > lease.end_date:
            return planned
        if candidate > base:
            planned.append(
                (candidate, _stepped_amount(planned[-1][1], lease), RentPeriodOrigin.STEP_UP)
            )
        year += 1


def _charged_dates(lease: Lease, *, kinds=(ChargeKind.RENT, ChargeKind.NNN)) -> set[dt.date]:
    """The due dates a given kind of charge has already been raised for.

    A rent period is locked by rent *or* NNN having been charged for it; an NNN
    rate is locked only by NNN, because staging next year's NNN after the rent has
    been billed is the ordinary case, not a rewrite of anything.
    """
    return set(lease.charges.filter(kind__in=list(kinds)).values_list("due_date", flat=True))


def _window_end(date: dt.date, every_date: list[dt.date], lease: Lease) -> dt.date:
    """The last day a value starting on ``date`` covers."""
    later = [candidate for candidate in every_date if candidate > date]
    return later[0] if later else lease.end_date


def _is_locked(
    date: dt.date, every_date: list[dt.date], charged: set[dt.date], lease: Lease
) -> bool:
    stop = _window_end(date, every_date, lease)
    return any(date <= charged_date < stop for charged_date in charged)


def _period_is_locked(lease: Lease, period: RentPeriod) -> bool:
    dates = sorted(p.effective_from for p in lease.rent_periods_ordered)
    if period.effective_from not in dates:
        dates.append(period.effective_from)
        dates.sort()
    return _is_locked(period.effective_from, dates, _charged_dates(lease), lease)


def _nnn_window_is_charged(lease: Lease, date: dt.date) -> bool:
    dates = sorted(rate.effective_from for rate in lease.nnn_rates_ordered)
    if date not in dates:
        dates.append(date)
        dates.sort()
    nnn_only = _charged_dates(lease, kinds=(ChargeKind.NNN,))
    return _is_locked(date, dates, nnn_only, lease)


# --- generating the schedule ----------------------------------------------


def schedule_rows(lease: Lease) -> list[dict]:
    """The schedule as the lease screen shows it: each period, and whether it is charged."""
    periods = lease.rent_periods_ordered
    if not periods:
        return []
    charged = _charged_dates(lease)
    every_date = [period.effective_from for period in periods]
    return [
        {"period": period, "locked": _is_locked(period.effective_from, every_date, charged, lease)}
        for period in periods
    ]


@transaction.atomic
def generate_rent_schedule(
    lease: Lease, *, actor=None, today: dt.date | None = None
) -> ScheduleResult:
    """Work out every period a stepped lease asks for, and store it.

    Idempotent: running it twice changes nothing, and a period that has already
    been charged is never rewritten. Periods the template no longer calls for are
    removed only when nothing has been charged against them — which is how a lease
    that goes back to a fixed rent loses the periods it no longer has.
    """
    if lease.is_stated:
        # A stated lease's amounts are the office's, entered from the paper: there
        # is no rule to work out and nothing here may remove what they wrote (E4).
        return ScheduleResult()

    planned = planned_periods(lease) if lease.uses_schedule else []
    existing = {period.effective_from: period for period in lease.rent_periods.all()}
    if not planned and not existing:
        return ScheduleResult()

    charged = _charged_dates(lease)
    every_date = sorted(set(existing) | {date for date, _, _ in planned})

    result = ScheduleResult()
    planned_dates = set()
    for date, amount, origin in planned:
        planned_dates.add(date)
        period = existing.pop(date, None)
        if period is not None and period.origin == RentPeriodOrigin.MANUAL:
            # A hand-set amount is the desk's decision, not the template's.
            result.kept.append(period)
            continue
        if _is_locked(date, every_date, charged, lease):
            result.locked.append(date)
            if period is not None:
                result.kept.append(period)
            continue
        if period is None:
            result.created.append(
                RentPeriod.objects.create(
                    lease=lease,
                    effective_from=date,
                    amount=amount,
                    origin=origin,
                    created_by=_actor(actor),
                )
            )
        elif period.amount != amount or period.origin != origin:
            period.amount = amount
            period.origin = origin
            period.save(update_fields=["amount", "origin"])
            result.updated.append(period)
        else:
            result.kept.append(period)

    for date, period in existing.items():
        if date in planned_dates:  # pragma: no cover - planned dates are popped above
            continue
        if period.origin == RentPeriodOrigin.MANUAL:
            # The office's own dated amount — a mid-term step, a renegotiation, an
            # "extra space" change. A rule cannot plan it, so the rule must not
            # delete it either (E4; this was a real defect).
            result.kept.append(period)
            continue
        if _is_locked(date, every_date, charged, lease):
            result.locked.append(date)
            result.kept.append(period)
            continue
        result.removed.append(date)
        period.delete()

    if result.changed:
        record(
            _actor(actor),
            AuditAction.RENT_SCHEDULE_GENERATED,
            obj=lease,
            lease=lease,
            summary=result.summary(),
            template=lease.template,
            created=len(result.created),
            updated=len(result.updated),
            removed=len(result.removed),
            locked=len(result.locked),
        )
    _forget_cached(lease)
    return result


@transaction.atomic
def set_rent_period_amount(
    period: RentPeriod, *, amount: Decimal, note: str = "", actor=None
) -> RentPeriod:
    """Set one period's rent by hand — an agreed figure, not a formula."""
    if amount is None or amount < MINIMUM_AMOUNT:
        raise ValidationError({"amount": "A rent amount must be at least one cent."})
    if _period_is_locked(period.lease, period):
        raise ValidationError(
            {
                "amount": (
                    "This period has already been charged. Correct the charge with an "
                    "adjustment instead of changing what the lease said."
                )
            }
        )

    previous = period.amount
    period.amount = amount
    period.origin = RentPeriodOrigin.MANUAL
    if note:
        period.note = note
    period.created_by = _actor(actor) or period.created_by
    period.save()
    _forget_cached(period.lease)

    record(
        _actor(actor),
        AuditAction.RENT_PERIOD_CHANGED,
        obj=period,
        lease=period.lease,
        summary=f"Rent from {_date_label(period.effective_from)} set to {amount} (was {previous})",
        amount=amount,
        previous=previous,
        effective_from=period.effective_from,
    )
    return period


# --- the NNN amount -------------------------------------------------------


def next_nnn_effective_date(lease: Lease, *, today: dt.date | None = None) -> dt.date | None:
    """The date the next NNN year would start: a year on from the staged one.

    Robert works the year out each November; the value that follows the last one
    starts on the same due date a year later, or — for a lease that has none yet —
    on the next date rent falls due.
    """
    rates = lease.nnn_rates_ordered
    if not rates:
        return first_due_on_or_after(lease, today or timezone.localdate())
    last = rates[-1].effective_from
    candidate = due_date_in(last.year + 1, last.month, lease.rent_due_day)
    return candidate if candidate <= lease.end_date else None


@transaction.atomic
def stage_nnn_rate(
    lease: Lease,
    *,
    effective_from: dt.date,
    monthly_amount: Decimal,
    note: str = "",
    actor=None,
) -> NnnRate:
    """Stage the NNN amount that applies from a date.

    The rate already in force keeps applying until that date arrives, so staging
    next year's figure never disturbs this year's (ADR-013).
    """
    if not lease.uses_nnn:
        raise ValidationError("Only a lease that carries NNN takes an NNN amount.")
    if monthly_amount is None or monthly_amount < ZERO:
        raise ValidationError({"monthly_amount": "An NNN amount cannot be negative."})
    if _nnn_window_is_charged(lease, effective_from):
        raise ValidationError(
            {
                "effective_from": (
                    "NNN has already been charged for that period. Correct the charge with an "
                    "adjustment instead of changing what the lease said."
                )
            }
        )

    rate = lease.nnn_rates.filter(effective_from=effective_from).first()
    if rate is None:
        rate = NnnRate(lease=lease, effective_from=effective_from)
    rate.monthly_amount = monthly_amount
    if note:
        rate.note = note
    rate.set_by = _actor(actor) or rate.set_by
    rate.save()
    _forget_cached(lease)

    record(
        _actor(actor),
        AuditAction.NNN_RATE_SET,
        obj=rate,
        lease=lease,
        summary=f"NNN set to {monthly_amount} a month from {_date_label(effective_from)}",
        amount=monthly_amount,
        effective_from=effective_from,
    )
    return rate


# --- the office's own dated amounts (E4) ----------------------------------


@transaction.atomic
def add_rent_period(
    lease: Lease, *, effective_from: dt.date, amount: Decimal, note: str = "", actor=None
) -> RentPeriod:
    """Add a dated rent amount the lease states — a mid-term step, a renegotiation.

    This is what a *stated* lease is for, and it also lets a stepped lease record a
    change its rule cannot plan. The period is marked as the office's own, so
    regenerating the schedule never removes it (E4, ADR-016).
    """
    if not lease.uses_schedule:
        raise ValidationError(
            "This lease has one rent for its term. Make it a stated-amounts lease to record "
            "dated amounts."
        )
    if amount is None or amount < MINIMUM_AMOUNT:
        raise ValidationError({"amount": "A rent amount must be at least one cent."})

    period = RentPeriod(
        lease=lease,
        effective_from=effective_from,
        amount=amount,
        origin=RentPeriodOrigin.MANUAL,
        note=note,
        created_by=_actor(actor),
    )
    period.save()
    _forget_cached(lease)
    record(
        _actor(actor),
        AuditAction.RENT_PERIOD_CHANGED,
        obj=period,
        lease=lease,
        summary=f"Rent from {_date_label(period.effective_from)} set to {amount}",
        amount=amount,
        effective_from=period.effective_from,
    )
    return period


@transaction.atomic
def remove_rent_period(period: RentPeriod, *, actor=None) -> None:
    """Remove a dated amount the office added, while nothing has been charged for it."""
    if _period_is_locked(period.lease, period):
        raise ValidationError(
            "That period has already been charged. Correct the charge with an adjustment "
            "instead of removing the amount the lease states."
        )
    lease = period.lease
    effective_from = period.effective_from
    period.delete()
    _forget_cached(lease)
    record(
        _actor(actor),
        AuditAction.RENT_PERIOD_CHANGED,
        obj=lease,
        lease=lease,
        summary=f"Rent from {_date_label(effective_from)} removed",
        effective_from=effective_from,
    )


# --- bringing a live tenancy in (E4) --------------------------------------


@transaction.atomic
def onboard_lease(
    lease: Lease,
    *,
    method: str,
    as_of: dt.date,
    received_total: Decimal | None = None,
    opening_amount: Decimal | None = None,
    billing_start_date: dt.date | None = None,
    note: str = "",
    through: dt.date | None = None,
    actor=None,
) -> LeaseOnboarding:
    """Place a tenancy that began before RHP, without inventing a debt (E4).

    Two ways in, both recorded on the lease:

    * **history** — the term's charges are raised and everything the tenant had
      already paid is brought in as one settling payment. The ledger's oldest-first
      allocation then leaves the true position, and the tenant has a full statement.
    * **position** — charging starts at the cutover and the past is one line: a
      brought-forward balance, or a credit on account.

    Either way the lease may not be charged before this runs, which is what makes
    the phantom back-bill impossible rather than merely discouraged (ADR-016).
    """
    from apps.ledger import services as ledger_services
    from apps.ledger.models import ChargeKind

    if FinancialCutover.objects.exists():
        raise ValidationError(
            "Use the reviewed starting account workflow; historical reconstruction is retired."
        )
    if method not in OnboardingMethod.values:
        raise ValidationError({"method": "Choose how this tenancy is being brought in."})
    if lease.status == LeaseStatus.DRAFT:
        raise ValidationError("Activate the lease first: a draft's terms can still change.")
    if lease.charges.exists():
        raise ValidationError(
            "This lease already has charges. Correct them with adjustments rather than "
            "bringing it in again."
        )
    if not lease.is_retroactive:
        raise ValidationError(
            "This tenancy begins in the current month or later. Use Post due rent charges."
        )

    if method == OnboardingMethod.HISTORY:
        if received_total is None or received_total < ZERO:
            raise ValidationError(
                {"received_total": "Say what the tenant had paid before RHP (0 if nothing)."}
            )
        # The whole term is billed from its start, up to today: nothing is charged ahead
        # of the day it falls due (P4-Q7). The payment settles it oldest-first.
        lease.billing_start_date = billing_start_date or lease.start_date
        lease.save(update_fields=["billing_start_date", "updated_at"])
        through = through or ledger_services.charges_due()
        ledger_services.generate_charges(lease, through=through, actor=actor)
        if received_total > ZERO:
            ledger_services.record_payment(
                lease,
                amount=received_total,
                payment_date=as_of,
                method=PaymentMethod.OTHER,
                external_reference="Opening balance",
                notes="Payments received before RHP began tracking this lease.",
                actor=actor,
            )
    else:
        cutover = billing_start_date or ledger_services.upcoming_rent_date(lease) or as_of
        if cutover < lease.start_date or cutover > lease.end_date:
            raise ValidationError(
                {"billing_start_date": "The first month billed has to fall inside the term."}
            )
        if opening_amount is None:
            raise ValidationError({"opening_amount": "Enter 0 if the account was paid in full."})
        lease.billing_start_date = cutover
        lease.save(update_fields=["billing_start_date", "updated_at"])
        if opening_amount > ZERO:
            ledger_services.create_charge(
                lease,
                description="Balance brought forward",
                amount=opening_amount,
                due_date=as_of,
                actor=actor,
                kind=ChargeKind.OPENING,
            )
        elif opening_amount < ZERO:
            # Paid ahead: money on account, which is what a credit is.
            ledger_services.record_payment(
                lease,
                amount=-opening_amount,
                payment_date=as_of,
                method=PaymentMethod.OTHER,
                external_reference="Opening balance",
                notes="Credit brought forward from before RHP (E4).",
                actor=actor,
            )

    onboarding = LeaseOnboarding(
        lease=lease,
        method=method,
        as_of=as_of,
        received_total=received_total if method == OnboardingMethod.HISTORY else None,
        opening_amount=opening_amount if method == OnboardingMethod.POSITION else None,
        note=note,
        set_by=_actor(actor),
    )
    onboarding.save()
    _forget_cached(lease)

    record(
        _actor(actor),
        AuditAction.LEASE_ONBOARDED,
        obj=lease,
        lease=lease,
        summary=(
            f"Prior activity for {lease.unit.label} set up using "
            f"{onboarding.get_method_display().lower()} as of {_date_label(as_of)}"
        ),
        method=method,
        as_of=as_of,
        received_total=received_total,
        opening_amount=opening_amount,
        billing_start_date=lease.billing_start_date,
    )
    return onboarding


# --- ending a tenancy, and closing its money (P4-Q1, P4-Q2, P4-Q3) ---------


def _set_status(lease: Lease, status: str, *, fields: list[str] | None = None) -> None:
    lease.status = status
    lease.save(update_fields=["status", *(fields or []), "updated_at"])


@transaction.atomic
def end_lease(
    lease: Lease,
    *,
    ended_on: dt.date,
    reason: str,
    note: str,
    keep=(),
    actor=None,
) -> list:
    """End a running tenancy: the paperwork, then the money (P4-Q1, P4-Q2).

    The reason and its detail are required, because ending a tenancy is a decision somebody
    has to be able to cite later — in a dispute, in a report, or in a conversation with the
    tenant. The close-out then cancels the months the tenancy will not use, by adjustment,
    and leaves the ones the office ticked to keep. Nothing is deleted.
    """
    if lease.status != LeaseStatus.ACTIVE:
        raise ValidationError(
            "Only a running tenancy can be ended. A settled tenancy is closed, and a draft "
            "has not started."
        )
    if ended_on is None:
        raise ValidationError({"ended_on": "Say which day the tenancy stops."})
    if ended_on < lease.start_date:
        raise ValidationError({"ended_on": "A tenancy cannot end before it starts."})
    if not reason:
        raise ValidationError({"reason": "Say why the tenancy is ending."})
    if not note.strip():
        raise ValidationError({"note": "Add the detail behind the reason."})

    # Imported here: the ledger imports this module for the E4 onboarding seam, so a
    # module-level import would close the circle.
    from apps.ledger import services as ledger_services

    lease.ended_on = ended_on
    lease.end_reason = reason
    lease.end_reason_note = note.strip()
    _set_status(
        lease,
        LeaseStatus.ENDED,
        fields=["ended_on", "end_reason", "end_reason_note"],
    )
    adjustments = ledger_services.close_out_lease(
        lease,
        on=ended_on,
        keep=keep,
        reason=f"Tenancy ended {_date_label(ended_on)}",
        actor=actor,
    )
    _forget_cached(lease)

    record(
        _actor(actor),
        AuditAction.LEASE_ENDED,
        obj=lease,
        lease=lease,
        summary=(
            f"{lease.unit.label} ended {_date_label(ended_on)}: "
            f"{lease.get_end_reason_display().lower()} — {lease.end_reason_note}"
        ),
        ended_on=ended_on,
        end_reason=reason,
        end_reason_note=lease.end_reason_note,
        closed_out=len(adjustments),
        kept=len(list(keep)),
    )
    return adjustments


@transaction.atomic
def settle_account(lease: Lease, *, note: str = "", actor=None) -> Lease:
    """Settle an ended tenancy's financial account when nothing remains unresolved.

    An act, not a state that happens: a person decides the financial relationship is over,
    so the record says who and when. Refused while anything is owed or held — a write-off is
    an adjustment the office makes first, and a credit is money RHP is holding.
    """
    # Imported here for the same reason as above.
    from apps.ledger import services as ledger_services
    from apps.ledger.models import PaymentStatus

    Lease.objects.select_for_update().get(pk=lease.pk)
    lease.refresh_from_db()

    if lease.status != LeaseStatus.ENDED:
        raise ValidationError(
            "Only a tenancy that has ended can be settled. End it first, so the record says "
            "when the tenancy stopped."
        )
    if lease.account_status == LeaseAccountStatus.SETTLED:
        raise ValidationError("This financial account is already settled.")
    ledger = ledger_services.build_ledger(lease)
    if ledger.balance_due > ZERO:
        raise ValidationError(
            f"{ledger.balance_due} is still owed on this tenancy. Correct or write it off on "
            "the ledger first, then settle it."
        )
    if ledger.credit > ZERO:
        raise ValidationError(
            f"{ledger.credit} is still held for this tenant. Return it or apply it first, then "
            "settle the account."
        )
    if lease.payments.filter(status=PaymentStatus.PENDING).exists():
        raise ValidationError(
            "A payment is still pending. Clear or void it before settling the account."
        )
    if lease.deposit > ZERO:
        raise ValidationError(
            "The recorded security deposit must be fully disposed of before this account can "
            "be settled. Deposit disposition will be recorded by the move-out workflow."
        )

    lease.account_status = LeaseAccountStatus.SETTLED
    lease.settled_at = timezone.now()
    lease.settled_by = _actor(actor)
    lease.settlement_note = note.strip()
    lease.save(
        update_fields=[
            "account_status",
            "settled_at",
            "settled_by",
            "settlement_note",
            "updated_at",
        ]
    )
    _forget_cached(lease)
    record(
        _actor(actor),
        AuditAction.LEASE_SETTLED,
        obj=lease,
        lease=lease,
        summary=f"{lease.unit.label} account settled: nothing owed and nothing held"
        + (f" — {note.strip()}" if note.strip() else ""),
        note=note.strip(),
    )
    return lease


@transaction.atomic
def reopen_account(lease: Lease, *, reason: str, actor=None) -> Lease:
    """Reopen only the financial account; occupancy always remains ended."""
    Lease.objects.select_for_update().get(pk=lease.pk)
    lease.refresh_from_db()
    if lease.status != LeaseStatus.ENDED:
        raise ValidationError("Only an ended tenancy's financial account can be reopened.")
    if lease.account_status != LeaseAccountStatus.SETTLED:
        raise ValidationError("Only a settled financial account can be reopened.")
    if not reason.strip():
        raise ValidationError({"reason": "Say why the tenancy is being reopened."})

    settled_at_before = lease.settled_at
    lease.account_status = LeaseAccountStatus.OPEN
    lease.settled_at = None
    lease.settled_by = None
    lease.settlement_note = ""
    lease.save(
        update_fields=[
            "account_status",
            "settled_at",
            "settled_by",
            "settlement_note",
            "updated_at",
        ]
    )
    _forget_cached(lease)
    record(
        _actor(actor),
        AuditAction.LEASE_REOPENED,
        obj=lease,
        lease=lease,
        summary=f"{lease.unit.label} financial account reopened: {reason.strip()}",
        reason=reason.strip(),
        settled_at_before=settled_at_before,
    )
    return lease

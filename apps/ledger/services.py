"""The ledger arithmetic and the actions that change it.

Everything that defines money lives here, once: what a balance is, which charge a
payment settles, when a charge is overdue, and what a month's rent charge looks
like. Views stay thin, the management command is a wrapper, and the tenant page
reads the same numbers as the staff ledger (ADR-008).
"""

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.dates import due_date_in
from apps.leases.models import Lease, LeaseStatus
from apps.ledger.models import (
    Charge,
    ChargeKind,
    ChargeState,
    Direction,
    Payment,
    PaymentKind,
    PaymentStatus,
)

ZERO = Decimal("0.00")


# --- value objects --------------------------------------------------------


@dataclass
class ChargeLine:
    """One charge, with the allocation the ledger has decided for it."""

    charge: Charge
    settled: Decimal = ZERO
    pending: Decimal = ZERO

    @property
    def is_reduction(self) -> bool:
        """A credit: it reduces what is owed rather than being settled itself."""
        return self.charge.balance_effect <= ZERO

    @property
    def outstanding(self) -> Decimal:
        """What is still owed on this charge. A credit owes nothing."""
        if self.is_reduction:
            return ZERO
        return max(self.charge.amount - self.settled, ZERO)

    @property
    def is_overdue(self) -> bool:
        """Money still owed on a charge whose date has passed."""
        return (
            not self.is_reduction
            and self.outstanding > ZERO
            and self.charge.due_date < timezone.localdate()
        )

    @property
    def state(self) -> str:
        """The derived status: paid, pending, overdue, partly paid, or unpaid."""
        if self.is_reduction:
            return ChargeState.ADJUSTMENT
        if self.settled >= self.charge.amount:
            return ChargeState.PAID
        if self.settled + self.pending >= self.charge.amount:
            # Money is on its way and would settle this charge; the desk should
            # see that rather than start chasing it.
            return ChargeState.PENDING
        if self.charge.due_date < timezone.localdate():
            return ChargeState.OVERDUE
        if self.settled > ZERO:
            return ChargeState.PARTIAL
        return ChargeState.UNPAID


@dataclass
class ActivityRow:
    """One line of the merged charge/payment history."""

    date: dt.date
    label: str
    detail: str
    amount: Decimal
    is_charge: bool


@dataclass
class LeaseLedger:
    """Everything one lease's money adds up to."""

    lease: Lease
    charges: list[ChargeLine] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)
    reversed_payment_ids: set = field(default_factory=set)

    @property
    def effective_payments(self) -> list[Payment]:
        """Money that counts: cleared, received, and not since reversed."""
        return [
            payment
            for payment in self.payments
            if payment.kind == PaymentKind.RECEIVED
            and payment.status == PaymentStatus.CLEARED
            and payment.pk not in self.reversed_payment_ids
        ]

    @property
    def pending_payments(self) -> list[Payment]:
        """Money expected: it marks a charge as pending, and moves no balance."""
        return [
            payment
            for payment in self.payments
            if payment.kind == PaymentKind.RECEIVED and payment.status == PaymentStatus.PENDING
        ]

    @property
    def balance_due(self) -> Decimal:
        """Positive: owed. Negative: a credit on the account."""
        charged = sum((line.charge.balance_effect for line in self.charges), ZERO)
        paid = sum((payment.amount for payment in self.effective_payments), ZERO)
        return (charged - paid).quantize(ZERO)

    @property
    def credit(self) -> Decimal:
        """The credit balance as a positive number (or zero)."""
        balance = self.balance_due
        return -balance if balance < ZERO else ZERO

    @property
    def overdue_amount(self) -> Decimal:
        return sum((line.outstanding for line in self.charges if line.is_overdue), ZERO)

    @property
    def is_overdue(self) -> bool:
        return self.overdue_amount > ZERO

    @property
    def next_due(self) -> ChargeLine | None:
        """The soonest charge that is not settled yet, if there is one."""
        unsettled = [
            line
            for line in self.charges
            if line.charge.balance_effect > ZERO and line.settled < line.charge.amount
        ]
        return min(unsettled, key=lambda line: (line.charge.due_date, line.charge.pk), default=None)

    @property
    def activity(self) -> list[ActivityRow]:
        """Charges and payments merged, newest first — the tenant's activity list."""
        rows = [
            ActivityRow(
                date=line.charge.due_date,
                label=line.charge.description,
                detail=line.charge.get_kind_display(),
                amount=line.charge.balance_effect,
                is_charge=True,
            )
            for line in self.charges
        ]
        rows += [
            ActivityRow(
                date=payment.payment_date,
                label=(
                    "Payment reversed"
                    if payment.kind == PaymentKind.REVERSAL
                    else "Payment received"
                ),
                detail=payment.get_method_display(),
                amount=payment.balance_effect,
                is_charge=False,
            )
            for payment in self.payments
            if payment.status != PaymentStatus.VOID
        ]
        return sorted(rows, key=lambda row: (row.date, row.is_charge), reverse=True)


# --- building a ledger ----------------------------------------------------


def _allocate(lines: list[ChargeLine], amounts: list[Decimal], *, pending: bool) -> None:
    """Apply a pool of money to charges oldest-first.

    First in, first out is what a rent ledger does: an August payment settles
    August before it settles September, and the partly paid charge is therefore
    the one at the front of the line.
    """
    pool = sum(amounts, ZERO)
    if pool <= ZERO:
        return

    for line in sorted(lines, key=lambda item: (item.charge.due_date, item.charge.pk)):
        if line.charge.balance_effect <= ZERO:
            # A reduction is not something a payment settles.
            continue
        settled = (line.settled + line.pending) if pending else line.settled
        remaining = line.charge.amount - settled
        if remaining <= ZERO:
            continue
        applied = min(remaining, pool)
        if pending:
            line.pending += applied
        else:
            line.settled += applied
        pool -= applied
        if pool <= ZERO:
            return


def build_ledger(lease: Lease) -> LeaseLedger:
    """The one place a tenancy's money is worked out."""
    charges = list(lease.charges.all())
    payments = list(lease.payments.all())

    ledger = LeaseLedger(
        lease=lease,
        charges=[ChargeLine(charge=charge) for charge in charges],
        payments=payments,
        reversed_payment_ids={payment.reverses_id for payment in payments if payment.reverses_id},
    )
    # A credit corrects one charge, so it settles that charge — not the oldest one.
    by_charge = {line.charge.pk: line for line in ledger.charges}
    for line in ledger.charges:
        if line.is_reduction and line.charge.adjusts_id:
            target = by_charge.get(line.charge.adjusts_id)
            if target is not None:
                target.settled += line.charge.amount

    _allocate(ledger.charges, [p.amount for p in ledger.effective_payments], pending=False)
    _allocate(ledger.charges, [p.amount for p in ledger.pending_payments], pending=True)
    return ledger


def build_ledgers(leases) -> dict[int, LeaseLedger]:
    """Ledgers for a page of leases, in two queries rather than two per lease."""
    if hasattr(leases, "prefetch_related"):
        leases = leases.prefetch_related("charges", "payments")
    return {lease.pk: build_ledger(lease) for lease in leases}


def totals(ledgers) -> dict:
    """The portfolio totals behind the accounting overview."""
    ledgers = list(ledgers)
    return {
        "outstanding": sum((led.balance_due for led in ledgers if led.balance_due > ZERO), ZERO),
        "credits": sum((led.credit for led in ledgers), ZERO),
        "overdue": sum((led.overdue_amount for led in ledgers), ZERO),
        "overdue_leases": sum(1 for led in ledgers if led.is_overdue),
    }


def by_urgency(ledgers) -> list[LeaseLedger]:
    """Overdue first, then the largest balance: the order the desk works in."""
    return sorted(ledgers, key=lambda led: (-led.overdue_amount, -led.balance_due))


# --- rent generation ------------------------------------------------------


def rent_due_dates(lease: Lease, *, through: dt.date) -> list[dt.date]:
    """The monthly due dates a lease should have been charged for.

    Bounded by the lease's own term — RHP never charges beyond the agreement —
    and by ``through``, so generating a year ahead is a deliberate act rather
    than an accident. A due date before the lease starts is skipped: a tenancy
    beginning mid-month is a partial month, and proration is deliberately not in
    Phase 4 (the desk adds a manual charge for it).
    """
    horizon = min(through, lease.end_date)
    dates: list[dt.date] = []
    year, month = lease.start_date.year, lease.start_date.month
    while (year, month) <= (horizon.year, horizon.month):
        due = due_date_in(year, month, lease.rent_due_day)
        if lease.start_date <= due <= horizon:
            dates.append(due)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return dates


def generation_horizon(months: int, *, today: dt.date | None = None) -> dt.date:
    """The last day of the month ``months`` months from today."""
    day = today or timezone.localdate()
    year, month = day.year, day.month
    for _ in range(max(months, 0)):
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return due_date_in(year, month, 31)


def generate_rent_charges(lease: Lease, *, through: dt.date, actor=None) -> list[Charge]:
    """Create the missing monthly rent charges for a lease; never duplicates."""
    if lease.status == LeaseStatus.DRAFT:
        raise ValidationError(
            "A draft lease has no ledger yet: its terms can still change. Activate the lease first."
        )

    created: list[Charge] = []
    for due in rent_due_dates(lease, through=through):
        # get_or_create also absorbs a concurrent double submit: the unique
        # constraint is one rent charge per lease per due date.
        charge, was_created = Charge.objects.get_or_create(
            lease=lease,
            kind=ChargeKind.RENT,
            due_date=due,
            defaults={
                "amount": lease.monthly_rent,
                "description": f"Rent for {due:%B %Y}",
                "created_by": actor if getattr(actor, "is_authenticated", False) else None,
            },
        )
        if was_created:
            record(
                actor,
                AuditAction.CHARGE_CREATED,
                obj=charge,
                lease=lease,
                summary=f"Rent charge for {due:%B %Y} created ({charge.amount})",
                amount=charge.amount,
                due_date=due,
                source="rent generation",
            )
            created.append(charge)
    return created


# --- the actions that change the ledger -----------------------------------


@transaction.atomic
def create_charge(
    lease: Lease,
    *,
    description: str,
    amount: Decimal,
    due_date: dt.date,
    actor=None,
    kind: str = ChargeKind.MANUAL,
) -> Charge:
    """A one-off charge — a repair recharge, a key replacement, a partial month."""
    charge = Charge(
        lease=lease,
        kind=kind,
        description=description,
        amount=amount,
        due_date=due_date,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    charge.save()
    record(
        actor,
        AuditAction.CHARGE_CREATED,
        obj=charge,
        lease=lease,
        summary=f"{charge.get_kind_display()} added: {description} ({amount})",
        amount=amount,
        due_date=due_date,
    )
    return charge


@transaction.atomic
def create_adjustment(
    charge: Charge,
    *,
    direction: str,
    amount: Decimal,
    reason: str,
    actor=None,
) -> Charge:
    """A correction to a charge, as its own entry. The original stays visible."""
    adjustment = Charge(
        lease=charge.lease,
        kind=ChargeKind.ADJUSTMENT,
        direction=direction,
        description=f"Adjustment to {charge.description}",
        amount=amount,
        due_date=charge.due_date,
        adjusts=charge,
        reason=reason,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    adjustment.save()
    record(
        actor,
        AuditAction.CHARGE_ADJUSTED,
        obj=adjustment,
        lease=charge.lease,
        summary=(
            f"{charge.description} adjusted "
            f"{'down' if direction == Direction.DECREASE else 'up'} by {amount}: {reason}"
        ),
        adjusts=str(charge.pk),
        amount=amount,
        direction=direction,
        reason=reason,
    )
    return adjustment


@transaction.atomic
def record_payment(
    lease: Lease,
    *,
    amount: Decimal,
    payment_date: dt.date,
    method: str,
    status: str = PaymentStatus.CLEARED,
    external_reference: str = "",
    notes: str = "",
    actor=None,
) -> Payment:
    """Record money received, or money expected."""
    payment = Payment(
        lease=lease,
        amount=amount,
        payment_date=payment_date,
        method=method,
        status=status,
        external_reference=external_reference,
        notes=notes,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    payment.save()
    record(
        actor,
        AuditAction.PAYMENT_RECORDED,
        obj=payment,
        lease=lease,
        summary=(
            f"{payment.get_status_display()} payment of {amount} recorded "
            f"({payment.get_method_display()})"
        ),
        amount=amount,
        payment_date=payment_date,
        method=method,
        status=status,
        external_reference=external_reference,
    )
    return payment


@transaction.atomic
def clear_payment(payment: Payment, *, actor=None) -> Payment:
    """The expected money arrived."""
    if payment.status != PaymentStatus.PENDING:
        raise ValidationError("Only a pending payment can be marked as cleared.")
    payment.status = PaymentStatus.CLEARED
    payment.save(update_fields=["status"])
    record(
        actor,
        AuditAction.PAYMENT_CLEARED,
        obj=payment,
        lease=payment.lease,
        summary=f"Payment of {payment.amount} cleared",
        amount=payment.amount,
        payment_date=payment.payment_date,
    )
    return payment


@transaction.atomic
def void_payment(payment: Payment, *, actor=None, reason: str = "") -> Payment:
    """The expected money never existed — canceled before it was money."""
    if payment.status != PaymentStatus.PENDING:
        raise ValidationError(
            "Only a pending payment can be voided. A cleared payment is corrected with a reversal."
        )
    payment.status = PaymentStatus.VOID
    payment.save(update_fields=["status"])
    record(
        actor,
        AuditAction.PAYMENT_VOIDED,
        obj=payment,
        lease=payment.lease,
        summary=f"Pending payment of {payment.amount} voided",
        amount=payment.amount,
        payment_date=payment.payment_date,
        reason=reason,
    )
    return payment


@transaction.atomic
def reverse_payment(payment: Payment, *, reason: str, actor=None) -> Payment:
    """Undo money that was recorded, by adding the offsetting entry."""
    if payment.kind != PaymentKind.RECEIVED:
        raise ValidationError("A reversal is not itself reversed.")
    if payment.status != PaymentStatus.CLEARED:
        raise ValidationError("Only a cleared payment can be reversed.")
    if payment.is_reversed():
        raise ValidationError("That payment has already been reversed.")

    reversal = Payment(
        lease=payment.lease,
        kind=PaymentKind.REVERSAL,
        amount=payment.amount,
        payment_date=timezone.localdate(),
        method=payment.method,
        status=PaymentStatus.CLEARED,
        external_reference=payment.external_reference,
        notes=f"Reversal of payment {payment.pk}: {reason}",
        reverses=payment,
        reason=reason,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    reversal.save()
    record(
        actor,
        AuditAction.PAYMENT_REVERSED,
        obj=reversal,
        lease=payment.lease,
        summary=f"Payment of {payment.amount} on {payment.payment_date} reversed: {reason}",
        amount=payment.amount,
        reversed_payment=str(payment.pk),
        reason=reason,
    )
    return reversal


# --- the accounting overview ----------------------------------------------


def lease_search(term: str) -> Q:
    """The text a desk types to find a tenancy: unit, property, or tenant name."""
    return (
        Q(unit__identifier__icontains=term)
        | Q(unit__property__name__icontains=term)
        | Q(lease_tenants__tenant__first_name__icontains=term)
        | Q(lease_tenants__tenant__last_name__icontains=term)
        | Q(lease_tenants__tenant__username__icontains=term)
    )


def ledger_rows(*, search: str = "", property_id=None) -> list[LeaseLedger]:
    """Every lease that can owe money, with its ledger, in desk order."""
    leases = (
        Lease.objects.exclude(status=LeaseStatus.DRAFT)
        .select_related("unit__property")
        .prefetch_related("lease_tenants__tenant")
    )
    if property_id:
        leases = leases.filter(unit__property_id=property_id)
    if search:
        leases = leases.filter(lease_search(search)).distinct()
    return by_urgency(build_ledgers(leases).values())

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
from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.dates import due_date_in
from apps.leases.models import FinancialCutover, Lease, LeaseAccountStatus, LeaseStatus
from apps.ledger.models import (
    SCHEDULED_KINDS,
    Charge,
    ChargeKind,
    ChargeState,
    Direction,
    Payment,
    PaymentKind,
    PaymentStatus,
)
from apps.responsibilities.models import PropertyResponsibility

ZERO = Decimal("0.00")


def _actor(actor):
    """The signed-in person behind an act, or None for a system write."""
    return actor if getattr(actor, "is_authenticated", False) else None


# --- value objects --------------------------------------------------------


@dataclass
class ChargeLine:
    """One charge, with its corrections and the allocation the ledger has decided.

    ``adjusted_by`` is what the corrections naming this charge do to it, net: negative for a
    reduction, positive for an increase. Reading a charge through it is what keeps a charge
    that has been corrected from reporting the figure it was raised at — a charge of 1,000
    paid in full and then increased by 200 is 200 in arrears, not paid.
    """

    charge: Charge
    adjusted_by: Decimal = ZERO
    settled: Decimal = ZERO
    pending: Decimal = ZERO
    credit_applied: Decimal = ZERO

    @property
    def is_reduction(self) -> bool:
        """A credit: it reduces what is owed rather than being settled itself."""
        return self.charge.balance_effect <= ZERO

    @property
    def net_amount(self) -> Decimal:
        """What this charge asks for once its corrections are read."""
        return self.charge.balance_effect + self.adjusted_by

    @property
    def outstanding(self) -> Decimal:
        """What is still owed on this charge. A credit owes nothing."""
        if self.is_reduction:
            return ZERO
        return max(self.net_amount - self.settled, ZERO)

    @property
    def is_overdue(self) -> bool:
        """Money still owed on a charge whose date has passed."""
        return (
            not self.is_reduction
            and not self.charge.aging_unknown
            and self.outstanding > ZERO
            and self.charge.due_date < timezone.localdate()
        )

    @property
    def state(self) -> str:
        """The derived status: adjusted, paid, pending, overdue, partly paid, or unpaid."""
        if self.is_reduction or self.net_amount <= ZERO:
            return ChargeState.ADJUSTMENT
        if self.settled >= self.net_amount:
            return ChargeState.PAID
        if self.settled + self.pending >= self.net_amount:
            # Money is on its way and would settle this charge; the desk should
            # see that rather than start chasing it.
            return ChargeState.PENDING
        if self.is_overdue:
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
class TransactionRow:
    """A charge read net with its corrections, or a payment, and the running balance."""

    date: dt.date
    entry_type: str
    description: str
    charge: Decimal
    payment_or_credit: Decimal
    running_balance: Decimal
    status: str
    charge_entry: Charge | None = None
    payment_entry: Payment | None = None
    adjustments: list[Charge] = field(default_factory=list)


# --- reading the ledger as a tenant ---------------------------------------
# The office reads entries (a charge, then the adjustment that corrects it); a
# tenant reads a statement (what a thing costs now, and what is paid). Same
# records, same balance, two readings — ADR-011.


#: How each derived charge state reads to a person. One definition, used by a
#: single charge row and by a month's card (E2).
STATE_LABELS = {
    ChargeState.ADJUSTMENT: "Adjusted",
    ChargeState.PAID: "Paid",
    ChargeState.PENDING: "Payment pending",
    ChargeState.OVERDUE: "Past due",
    ChargeState.PARTIAL: "Partly paid",
    ChargeState.UNPAID: "Unpaid",
}


@dataclass
class StatementCharge:
    """One charge as the person paying it should read it.

    An adjustment is not a separate line: it is absorbed here, so a charge raised
    at $2,084 and corrected to nothing reads as "$0.00, adjusted" rather than as
    money arriving and leaving again.
    """

    date: dt.date
    title: str
    detail: str
    gross: Decimal
    net: Decimal
    adjusted_by: Decimal
    adjustment_count: int
    paid: Decimal
    left: Decimal
    pending: Decimal
    #: The row type, so a template can branch on "charge" or "payment".
    kind: str = "charge"
    #: What the charge is: rent, NNN, a manual charge or an adjustment, so a
    #: screen can talk about rent without reading the description (E1).
    charge_kind: str = ""
    #: Where a responsibility charge came from, so a month can be grouped by
    #: category and the tenant reads "Utility" rather than a kind name (E2).
    category: str = ""
    responsibility_label: str = ""
    charge_id: int | None = None
    aging_unknown: bool = False
    credit_applied: Decimal = ZERO

    @property
    def was_adjusted(self) -> bool:
        return self.adjustment_count > 0

    @property
    def amount(self) -> Decimal:
        """What to show as this charge's cost: never a negative headline."""
        return max(self.net, ZERO)

    @property
    def credit(self) -> Decimal:
        """An adjustment that overshot leaves money in the tenant's favor."""
        return -self.net if self.net < ZERO else ZERO

    @property
    def is_overdue(self) -> bool:
        return not self.aging_unknown and self.left > ZERO and self.date < timezone.localdate()

    @property
    def state(self) -> str:
        """The tenant's reading: adjusted, paid, pending, overdue, part paid, unpaid."""
        if self.net <= ZERO:
            return ChargeState.ADJUSTMENT
        if self.left <= ZERO:
            return ChargeState.PAID
        if self.pending >= self.left:
            return ChargeState.PENDING
        if self.is_overdue:
            return ChargeState.OVERDUE
        if self.paid > ZERO:
            return ChargeState.PARTIAL
        return ChargeState.UNPAID

    @property
    def state_label(self) -> str:
        return STATE_LABELS[self.state]


@dataclass
class StatementPayment:
    """Money in, as the tenant reads it."""

    date: dt.date
    amount: Decimal
    method: str
    reference: str
    status: str
    is_reversal: bool
    is_reversed: bool = False
    kind: str = "payment"

    @property
    def label(self) -> str:
        if self.is_reversal:
            return "Payment reversed"
        if self.status == PaymentStatus.PENDING:
            return "Payment expected"
        return "Payment received"

    @property
    def status_label(self) -> str:
        return "Expected" if self.status == PaymentStatus.PENDING else "Cleared"


@dataclass
class ComponentRow:
    """One part of a month, with the thing worth saying about it.

    The note is the lease's own news — "steps up in 1 month", "updates in 2 months"
    — read against the month the card is for, exactly as the owner's sketch shows it.
    """

    component: StatementCharge
    note: str = ""


@dataclass
class ResponsibilityGroup:
    """A month's responsibility charges under one category, with their subtotal."""

    label: str
    rows: list[ComponentRow] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        return sum((row.component.amount for row in self.rows), ZERO)


@dataclass
class StatementMonth:
    """One exact due-date bill, shared by staff and tenant presentation (E2/E9).

    A reading, not a record: the month's rent, NNN and responsibilities are separate
    ledger entries that share a due date, and this sums them so a tenant sees one
    figure and can open it up. ``LeaseLedger.statement`` still holds the plain rows
    (ADR-011).
    """

    date: dt.date
    rows: list[ComponentRow] = field(default_factory=list)
    kind: str = "month"
    #: Whether this month is where the tenant first meets NNN, so it can be spelled out once
    #: (ADR-021) instead of in every month of every statement.
    spells_out_nnn: bool = False
    # Staff-only source rows are never rendered by tenant components.
    transactions: list[TransactionRow] = field(default_factory=list)
    running_balance: Decimal = ZERO

    @property
    def is_opening(self):
        return bool(self.components) and all(
            row.charge_kind == ChargeKind.OPENING for row in self.components
        )

    @property
    def components(self) -> list[StatementCharge]:
        return [row.component for row in self.rows]

    @property
    def total(self) -> Decimal:
        """What the month costs, at the figures the charges now stand at."""
        return sum((component.net for component in self.components), ZERO)

    @property
    def paid(self) -> Decimal:
        return sum((component.paid for component in self.components), ZERO)

    @property
    def credit_applied(self) -> Decimal:
        return sum((component.credit_applied for component in self.components), ZERO)

    @property
    def pending(self) -> Decimal:
        return sum((component.pending for component in self.components), ZERO)

    @property
    def left(self) -> Decimal:
        return sum((component.left for component in self.components), ZERO)

    @property
    def state(self) -> str:
        """One bill's progress, never a component's individual settlement state."""
        if self.total <= ZERO and self.left <= ZERO:
            return ChargeState.ADJUSTMENT
        if self.left <= ZERO:
            return ChargeState.PAID
        if self.paid > ZERO:
            return ChargeState.PARTIAL
        if self.pending >= self.left:
            return ChargeState.PENDING
        if self.date < timezone.localdate():
            return ChargeState.OVERDUE
        return ChargeState.UNPAID

    @property
    def state_label(self) -> str:
        if self.is_opening:
            if self.total < ZERO:
                return "Manager-entered starting credit"
            return "Manager-entered starting balance · See repayment details"
        if self.credit_applied > ZERO:
            label = (
                "Credit applied"
                if self.paid == self.credit_applied
                else "Payment and credit applied"
            )
            return label + (" · Nothing remaining" if self.left == ZERO else " · Remaining to pay")
        if self.state == ChargeState.ADJUSTMENT:
            return "Credit" if self.total < ZERO else "Nothing to pay"
        if self.state == ChargeState.PAID:
            return "Paid in full"
        if self.state == ChargeState.PARTIAL and self.date < timezone.localdate():
            return "Partly paid · Past due"
        return STATE_LABELS[self.state]

    @property
    def is_one_line(self) -> bool:
        """Compatibility metadata; a single component still uses an expandable bill card."""
        return len(self.rows) == 1

    def _of_kind(self, kind: str) -> list[ComponentRow]:
        return [row for row in self.rows if row.component.charge_kind == kind]

    @property
    def rent_rows(self) -> list[ComponentRow]:
        return self._of_kind(ChargeKind.RENT)

    @property
    def nnn_rows(self) -> list[ComponentRow]:
        return self._of_kind(ChargeKind.NNN)

    @property
    def responsibility_rows(self) -> list[ComponentRow]:
        return self._of_kind(ChargeKind.RESPONSIBILITY)

    @property
    def other_rows(self) -> list[ComponentRow]:
        """Manual charges, and anything the ledger grows later."""
        return [
            row
            for row in self.rows
            if row.component.charge_kind
            not in (ChargeKind.RENT, ChargeKind.NNN, ChargeKind.RESPONSIBILITY)
        ]

    @property
    def responsibility_groups(self) -> list[ResponsibilityGroup]:
        """Property charges under one plain heading, retaining their actual names."""
        rows = self.responsibility_rows
        return [ResponsibilityGroup(label="Property charges", rows=rows)] if rows else []


@dataclass
class LeaseLedger:
    """Everything one lease's money adds up to."""

    lease: Lease
    charges: list[ChargeLine] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)
    deposit_applied: Decimal = ZERO
    reversed_payment_ids: set = field(default_factory=set)
    obligations: list = field(default_factory=list)
    credit_sources: list = field(default_factory=list)
    repayment_plans: list = field(default_factory=list)
    application_history: list = field(default_factory=list)
    plan_history: list = field(default_factory=list)

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
        # A retained deposit applied to a bill moves held money, not new cash.
        return (charged - paid - self.deposit_applied).quantize(ZERO)

    @property
    def credit(self) -> Decimal:
        """Unapplied credit held for this tenant: money available, not yet applied.

        A retained security deposit is available to apply to final charges but is not the
        tenant's spendable credit; it is shown separately on the move-out statement.
        """
        return sum(
            (source["available"] for source in self.credit_sources if not source.get("is_deposit")),
            ZERO,
        )

    @property
    def future_repayments(self):
        today = timezone.localdate()
        return sum((row.left for row in self.obligations if row.key and row.date > today), ZERO)

    @property
    def unpaid_charges(self):
        return sum((row.left for row in self.obligations), ZERO)

    @property
    def undated_starting_debt(self):
        return sum((row.left for row in self.obligations if row.unknown), ZERO)

    @property
    def transactions(self) -> list[TransactionRow]:
        """Chronological account activity, with adjustments nested under their charge.

        Running balances use each charge's corrected amount as of today. The original
        entries and correction dates remain available inline and in audit history.
        """
        charge_lines = {line.charge.pk: line for line in self.charges}
        adjustments = {}
        for line in self.charges:
            if line.charge.adjusts_id is not None:
                adjustments.setdefault(line.charge.adjusts_id, []).append(line.charge)
        entries = []
        for line in self.charges:
            charge = line.charge
            if charge.adjusts_id is not None:
                continue
            entries.append((charge.due_date, charge.created_at, 0, charge.pk, "charge", charge))
        for payment in self.payments:
            entries.append(
                (
                    payment.payment_date,
                    payment.created_at,
                    1,
                    payment.pk,
                    "payment",
                    payment,
                )
            )

        balance = ZERO
        rows = []
        for date, _created_at, _order, _pk, kind, entry in sorted(entries):
            if kind == "charge":
                corrections = adjustments.get(entry.pk, [])
                effect = entry.balance_effect + sum(
                    (correction.balance_effect for correction in corrections), ZERO
                )
                balance += effect
                rows.append(
                    TransactionRow(
                        date=date,
                        entry_type=entry.get_kind_display(),
                        description=entry.description,
                        charge=max(effect, ZERO),
                        payment_or_credit=max(-effect, ZERO),
                        running_balance=balance,
                        status=(
                            "Adjusted"
                            if corrections and effect <= ZERO
                            else STATE_LABELS[charge_lines[entry.pk].state]
                        ),
                        charge_entry=entry,
                        adjustments=corrections,
                    )
                )
                continue

            if entry.status in (PaymentStatus.PENDING, PaymentStatus.VOID):
                effect = ZERO
            elif entry.kind == PaymentKind.REVERSAL:
                effect = entry.amount
            else:
                effect = -entry.amount
            balance += effect
            rows.append(
                TransactionRow(
                    date=date,
                    entry_type=entry.get_kind_display(),
                    description=(
                        f"{entry.get_method_display()}"
                        + (f" · {entry.external_reference}" if entry.external_reference else "")
                    ),
                    charge=max(effect, ZERO),
                    payment_or_credit=max(-effect, ZERO),
                    running_balance=balance,
                    status=(
                        "Reversed"
                        if entry.pk in self.reversed_payment_ids
                        else entry.get_status_display()
                    ),
                    payment_entry=entry,
                )
            )
        return rows

    # --- What is owed, when -------------------------------------------------
    # Three different questions, three different answers. Calling the oldest unpaid
    # charge "the next rent due" reads as "the next obligation", which is a
    # different thing entirely (ADR-012).

    @property
    def statement_charges(self) -> list[StatementCharge]:
        """The charges, read net, without the payments mixed in."""
        return [row for row in self.statement if isinstance(row, StatementCharge)]

    @property
    def due_now(self) -> Decimal:
        """What the tenant should pay now: everything due today or earlier."""
        today = timezone.localdate()
        return sum((row.left for row in self.obligations if row.date <= today), ZERO)

    @property
    def arrears(self) -> Decimal:
        """The part of what is owed whose due date has already passed."""
        today = timezone.localdate()
        return sum(
            (row.left for row in self.obligations if row.date < today and not row.unknown), ZERO
        )

    @property
    def has_arrears(self) -> bool:
        return self.arrears > ZERO

    @property
    def arrears_oldest(self) -> StatementCharge | None:
        """The oldest unpaid charge, so a screen can say how far behind this is.

        The desk works the oldest bucket first, and the age is what says so.
        """
        return min(
            (
                row
                for row in self.obligations
                if row.date < timezone.localdate() and not row.unknown and row.left > ZERO
            ),
            key=lambda row: (row.date, row.charge.pk),
            default=None,
        )

    @property
    def arrears_age_days(self) -> int | None:
        oldest = self.arrears_oldest
        if oldest is None:
            return None
        return (timezone.localdate() - oldest.date).days

    @property
    def next_charge(self) -> StatementCharge | None:
        """The next obligation of any kind: the desk's "coming due" line."""
        return self._soonest_after_today()

    @property
    def next_rent_charge(self) -> StatementCharge | None:
        """The next *rent* due after today, so NNN never stands in for the rent.

        A triple-net month carries rent and NNN on the same date (E1); the rent
        figure on a tenant's card has to stay the rent.
        """
        return self._soonest_after_today(kinds=(ChargeKind.RENT,))

    def _soonest_after_today(self, *, kinds=None) -> StatementCharge | None:
        today = timezone.localdate()
        upcoming = [
            row
            for row in self.statement_charges
            if row.date > today and row.left > ZERO and (kinds is None or row.charge_kind in kinds)
        ]
        return min(upcoming, key=lambda row: (row.date, row.title), default=None)

    @property
    def not_yet_due(self) -> Decimal:
        """Billed, but not due yet — stated, never headlined."""
        today = timezone.localdate()
        return sum((row.left for row in self.obligations if not row.key and row.date > today), ZERO)

    # --- the next date a tenant has to pay, and what that month costs -------
    # A month is rent plus NNN today, and responsibilities once E2 lands. The
    # card states the whole figure, because a tenant who is told only the rent
    # is being told a number smaller than the bill (E1, ADR-013).

    @property
    def can_post_due_charges(self) -> bool:
        """Whether posting today would bill this tenancy for something it has not been billed.

        The overview needs this to offer the button where the office sees "not posted", and it
        reads the charges the ledger already holds rather than asking again.
        """
        return has_due_charges_to_post(
            self.lease, through=charges_due(), charges=[line.charge for line in self.charges]
        )

    @property
    def next_due_date(self) -> dt.date | None:
        """The next date anything falls due, billed or forecast from the lease.

        Nothing is coming on a tenancy that has ended or been settled: what is left is what was
        charged, not what the lease would have charged next (P4-Q1).
        """
        if not self.lease.can_be_charged:
            return None
        today = timezone.localdate()
        upcoming = [
            row.date for row in self.statement_charges if row.date > today and row.left > ZERO
        ]
        if upcoming:
            return min(upcoming)
        return upcoming_rent_date(self.lease)

    def next_due_charges(self, on_date: dt.date) -> list[StatementCharge]:
        """Every charge dated ``on_date`` that still owes something."""
        return [row for row in self.statement_charges if row.date == on_date and row.left > ZERO]

    @property
    def next_due_rent(self) -> Decimal:
        """The rent part of the next date due."""
        date = self.next_due_date
        if date is None:
            return ZERO
        raised = self.next_due_charges(date)
        if raised:
            return sum((row.left for row in raised if row.charge_kind == ChargeKind.RENT), ZERO)
        return self.lease.rent_for(date)

    @property
    def next_due_nnn(self) -> Decimal:
        """The NNN part of the next date due: billed, or the lease's staged rate."""
        date = self.next_due_date
        if date is None:
            return ZERO
        raised = self.next_due_charges(date)
        if raised:
            return sum((row.left for row in raised if row.charge_kind == ChargeKind.NNN), ZERO)
        return self.lease.nnn_for(date)

    @property
    def next_due_total(self) -> Decimal:
        """What the next date costs in total."""
        date = self.next_due_date
        if date is None:
            return ZERO
        raised = self.next_due_charges(date)
        if raised:
            return sum((row.left for row in raised), ZERO)
        return self.lease.rent_for(date) + self.lease.nnn_for(date)

    @property
    def next_due_billed(self) -> bool:
        """Whether a charge has actually been raised for the next date."""
        date = self.next_due_date
        return bool(date) and bool(self.next_due_charges(date))

    @property
    def next_due_pending(self) -> bool:
        """Whether money is on its way for the next date."""
        date = self.next_due_date
        return bool(date) and any(row.pending > ZERO for row in self.next_due_charges(date))

    @property
    def next_rent_date(self) -> dt.date | None:
        """When the next rent falls due, whether or not it has been billed yet.

        The office raises charges a month at a time, so the coming period may not
        exist as an entry; the lease still says when it is. A tenant should never
        see an empty card because nobody pressed a button — and never see rent
        coming on a tenancy that has already ended (P4-Q1).
        """
        if not self.lease.can_be_charged:
            return None
        charge = self.next_rent_charge
        if charge is not None:
            return charge.date
        return upcoming_rent_date(self.lease)

    @property
    def next_rent_amount(self) -> Decimal:
        """What the next rent is: what is left on it, or what the lease says."""
        charge = self.next_rent_charge
        if charge is not None:
            return charge.left
        date = upcoming_rent_date(self.lease)
        if date is None:
            return ZERO
        return self.lease.rent_for(date)

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
                    else "Payment expected"
                    if payment.status == PaymentStatus.PENDING
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

    @property
    def statement(self) -> list[StatementCharge | StatementPayment]:
        """This money as the tenant reads it: one list, adjustments absorbed.

        Every figure is derived from data already loaded — the adjustments are
        charges with an ``adjusts`` link — so this costs no further queries. The
        office keeps reading ``charges`` and ``activity``; this is the other
        reading of the same records (ADR-011).
        """
        absorbed: dict[int, list[Charge]] = {}
        for line in self.charges:
            charge = line.charge
            if charge.kind == ChargeKind.ADJUSTMENT and charge.adjusts_id is not None:
                absorbed.setdefault(charge.adjusts_id, []).append(charge)

        rows: list[StatementCharge | StatementPayment] = []
        for line in self.charges:
            charge = line.charge
            # An adjustment that names a charge is shown inside that charge; one
            # that names nothing is a charge in its own right.
            if charge.kind == ChargeKind.ADJUSTMENT and charge.adjusts_id is not None:
                continue

            adjustments = absorbed.get(charge.pk, [])
            adjusted_by = sum((entry.balance_effect for entry in adjustments), ZERO)
            # One definition of a corrected charge, read from the line.
            net = line.net_amount
            # `settled` is money applied to this charge and nothing else: a correction never
            # counts as paid, which is why the line reads it into the amount instead.
            paid = max(line.settled, ZERO)
            responsibility = charge.responsibility
            rows.append(
                StatementCharge(
                    date=charge.due_date,
                    title=charge.description,
                    detail=(
                        "Property charge"
                        if charge.kind == ChargeKind.RESPONSIBILITY
                        else charge.get_kind_display()
                    ),
                    gross=charge.amount,
                    net=net,
                    adjusted_by=adjusted_by,
                    adjustment_count=len(adjustments),
                    paid=paid,
                    left=max(net - paid, ZERO),
                    pending=line.pending,
                    charge_kind=charge.kind,
                    charge_id=charge.pk,
                    aging_unknown=charge.aging_unknown,
                    credit_applied=line.credit_applied,
                    category=(
                        responsibility.get_category_display() if responsibility is not None else ""
                    ),
                    responsibility_label=(
                        responsibility.label if responsibility is not None else ""
                    ),
                )
            )

        rows += [
            StatementPayment(
                date=payment.payment_date,
                amount=payment.amount,
                method=payment.get_method_display(),
                reference=payment.external_reference,
                status=payment.status,
                is_reversal=payment.kind == PaymentKind.REVERSAL,
            )
            for payment in self.payments
            if payment.status != PaymentStatus.VOID
        ]
        # Newest first; on a shared date the charge is shown before the payment
        # that settled it, which is the order it happened in.
        return sorted(rows, key=lambda row: (row.date, row.kind == "charge"), reverse=True)

    # --- the same rows, read as months (E2) --------------------------------
    # A month's rent, NNN and responsibilities are separate entries that share a
    # date. The card groups them so a tenant sees one figure and can open it up;
    # the plain rows above are untouched (ADR-011, ADR-014).

    def _note_for(self, component: StatementCharge, on_date: dt.date) -> str:
        """The lease's own news about one component, read against the month."""
        if component.charge_kind == ChargeKind.RENT:
            change = self.lease.next_rent_change(today=on_date)
            if change is not None:
                return _in_months("steps up", on_date, change.effective_from)
        if component.charge_kind == ChargeKind.NNN:
            change = self.lease.next_nnn_change(today=on_date)
            if change is not None:
                return _in_months("updates", on_date, change.effective_from)
        return ""

    def statement_months(self) -> list[StatementMonth | StatementPayment]:
        """The statement grouped by due date, newest first."""
        from apps.ledger.presentation import bill_history

        # Shared grouping and chronology; only the public payment fields reach tenant templates.
        grouped = []
        for row in bill_history(self, newest=True):
            if isinstance(row, StatementMonth):
                grouped.append(row)
            else:
                payment = row.payment_entry
                grouped.append(
                    StatementPayment(
                        date=row.date,
                        amount=payment.amount,
                        method=payment.get_method_display(),
                        reference=payment.external_reference,
                        status=payment.status,
                        is_reversal=payment.kind == PaymentKind.REVERSAL,
                        is_reversed=payment.pk in self.reversed_payment_ids,
                    )
                )
        return grouped


def _in_months(verb: str, from_date: dt.date, to_date: dt.date) -> str:
    """``steps up in 1 month`` — the news a component carries on a month's card."""
    months = (to_date.year - from_date.year) * 12 + (to_date.month - from_date.month)
    if months <= 0:
        return f"{verb} this month"
    return f"{verb} in {months} month{'' if months == 1 else 's'}"


# --- building a ledger ----------------------------------------------------


def upcoming_rent_date(lease: Lease, *, today: dt.date | None = None) -> dt.date | None:
    """The lease's next rent due date, whether or not a charge has been raised.

    The office raises charges a month at a time, so the coming period often has no
    entry yet; the lease itself still says when the rent falls due, and a tenant
    should not see an empty card because nobody pressed a button.

    The due day is clamped to a day the month actually has (a 31st is the 28th in
    February), a tenancy is never billed before it starts, and no rent falls due
    after the term ends.
    """
    day = today or timezone.localdate()
    if lease.status != LeaseStatus.ACTIVE or lease.end_date < day:
        return None

    # Start from the current month, or from the month the term begins when that is
    # still ahead: an unstarted tenancy's first rent is its next rent.
    anchor = max(day, lease.start_date - dt.timedelta(days=1))
    year, month = anchor.year, anchor.month
    while True:
        due = due_date_in(year, month, lease.rent_due_day)
        if due > lease.end_date:
            return None
        if due > day and due >= lease.start_date:
            return due
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def _load_charges(lease: Lease) -> list[Charge]:
    """A lease's charges, with the responsibility attached, in one query.

    A prefetched list is reused when the caller already fetched one (the list
    screens do), so nothing pays two queries for the same rows.
    """
    prefetched = getattr(lease, "_prefetched_objects_cache", {}).get("charges")
    if prefetched is not None:
        return list(prefetched)
    return list(lease.charges.select_related("responsibility"))


def build_ledger(lease: Lease) -> LeaseLedger:
    """The one place a tenancy's money is worked out."""
    charges = _load_charges(lease)
    payments = list(lease.payments.all())

    # A correction belongs to the charge it names, so the charge reads it. This replaced a
    # patch that added a reduction's amount to its target's `settled`, which left an
    # *increase* with nowhere to go: it moved the balance and no charge ever showed it.
    corrected: dict[int, Decimal] = {}
    for charge in charges:
        if charge.adjusts_id is not None:
            corrected[charge.adjusts_id] = (
                corrected.get(charge.adjusts_id, ZERO) + charge.balance_effect
            )

    ledger = LeaseLedger(
        lease=lease,
        charges=[
            ChargeLine(charge=charge, adjusted_by=corrected.get(charge.pk, ZERO))
            for charge in charges
        ],
        payments=payments,
        reversed_payment_ids={payment.reverses_id for payment in payments if payment.reverses_id},
    )

    # Allocation is recorded, never recomputed: the applications are the coverage,
    # and a read that found none is a read of nothing (ADR-028 D3). The pending
    # projection inside `read` is display only.
    from apps.ledger.applications import read

    read(ledger)
    return ledger


def build_ledgers(leases) -> dict[int, LeaseLedger]:
    """Batch charges, receipts, applications and plans; query count does not grow per lease."""
    if hasattr(leases, "prefetch_related"):
        leases = leases.prefetch_related(
            Prefetch("charges", queryset=Charge.objects.select_related("responsibility")),
            "payments",
            "funds_applications",
            "repayment_plans__installments",
            "deposit_entries",
        )
    result = {}
    for lease in leases:
        result[lease.pk] = build_ledger(lease)
    return result


def totals(ledgers) -> dict:
    """The portfolio totals behind the accounting overview."""
    ledgers = list(ledgers)
    return {
        "due_now": sum((led.due_now for led in ledgers), ZERO),
        "outstanding": sum((led.balance_due for led in ledgers if led.balance_due > ZERO), ZERO),
        "credits": sum((led.credit for led in ledgers), ZERO),
        "arrears": sum((led.arrears for led in ledgers), ZERO),
        "arrears_leases": sum(1 for led in ledgers if led.has_arrears),
    }


def by_urgency(ledgers) -> list[LeaseLedger]:
    """Past due first, then the largest balance: the order the desk works in."""
    return sorted(ledgers, key=lambda led: (-led.arrears, -led.balance_due))


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
    # Charging starts at the lease's cutover: a tenancy RHP took on part-way through
    # its term is billed from the month the office named, never from before it (E4).
    start = max(lease.start_date, lease.bill_from)
    cutover = FinancialCutover.objects.first()
    if cutover is not None:
        horizon = min(horizon, charges_due())
        start = max(start, cutover.first_native_date)
    dates: list[dt.date] = []
    year, month = start.year, start.month
    while (year, month) <= (horizon.year, horizon.month):
        due = due_date_in(year, month, lease.rent_due_day)
        if start <= due <= horizon:
            dates.append(due)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return dates


def charges_due(*, today: dt.date | None = None) -> dt.date:
    """The last day a charge may be raised for: today.

    A month's rent is raised **on its due date**, never ahead of it (P4-Q7). The tenant still
    sees what is coming, because the statement derives the next rent from the lease rather
    than from a charge row (ADR-012) — so a charge dated in the future would only ever be
    something to cancel when a tenancy ends. This is the one place that rule is expressed.
    """
    return today or timezone.localdate()


#: What is said when a new obligation is refused because the tenancy is not running (P4-Q1,
#: P4-Q3). One message per state, so the services, the screens and the management command
#: all say the same thing — and so a test can assert the words rather than a code.
#: Said when a settled account refuses a write, from one place.
NOT_SETTLED = (
    "This financial account is settled. Reopen the financial account before making any "
    "payment, charge, or correction."
)

#: Said when a tenancy that began before RHP takes a charge it has not been placed for.
NEEDS_STARTING_ACCOUNT = (
    "This tenancy began before RHP's records. Record its starting account balance before "
    "posting charges, so a paid-up past is not recreated."
)

NOT_CHARGEABLE = {
    LeaseStatus.DRAFT: (
        "A draft lease has no ledger yet: its terms can still change. Activate the lease first."
    ),
    LeaseStatus.FUTURE: (
        "This tenancy has not started. Charges begin with its term; a deposit may be recorded "
        "in the meantime."
    ),
    LeaseStatus.ENDED: (
        "This tenancy has ended. Its terms are history and do not change; its money can still "
        "be recorded and corrected, but nothing new can be charged on it."
    ),
}


def refuse_if_account_settled(lease: Lease) -> None:
    """Require an explicit, audited financial reopening before any ledger write."""
    current = (
        Lease.objects.select_for_update()
        .only("status", "account_status", "financial_ready", "billing_start_date")
        .get(pk=lease.pk)
    )
    lease.status = current.status
    lease.account_status = current.account_status
    lease.financial_ready = current.financial_ready
    lease.billing_start_date = current.billing_start_date
    if lease.account_status == LeaseAccountStatus.SETTLED:
        raise ValidationError(NOT_SETTLED)


def refuse_if_not_chargeable(lease: Lease) -> None:
    """Raise unless this tenancy may take a new obligation (P4-Q1, P4-Q3).

    The rule lives here rather than in a screen, because the ledger screen is not the only
    caller: `manage.py generate_rent_charges` is another, and Phase 12 may put it on a
    schedule. A screen-only guard is how the ended-lease hole appeared.

    The post-tenancy extension (P4-E6) will relax exactly this: a remedial charge carrying a
    reason code, its lease clause and its evidence, on a tenancy that has ended.
    """
    refuse_if_account_settled(lease)
    reason = charge_refusal(lease)
    if reason is not None:
        raise ValidationError(reason)


def charge_refusal(lease: Lease) -> str | None:
    """Why this tenancy may not take a new charge, or ``None`` when it may.

    One definition of the rule, so the guard that raises and the screen that decides whether
    to offer the button cannot drift apart — they did once, and a duplicate of this logic in
    `has_due_charges_to_post` is how. The rules, in the order they are asked: a settled
    account takes nothing; only a running tenancy takes new obligations; and a tenancy that
    began before RHP must be placed before anything is billed (E4).

    The rule lives here rather than in a screen, because the ledger screen is not the only
    caller: `manage.py generate_rent_charges` is another, and Phase 12 may put it on a
    schedule. A screen-only guard is how the ended-lease hole appeared.
    """
    if lease.account_status == LeaseAccountStatus.SETTLED:
        return NOT_SETTLED
    if not lease.can_be_charged:
        return NOT_CHARGEABLE[lease.status]
    if lease.needs_starting_account:
        return NEEDS_STARTING_ACCOUNT
    return None


@transaction.atomic
def generate_charges(lease: Lease, *, through: dt.date, actor=None) -> list[Charge]:
    """Create the missing rent — and NNN — charges for a lease; never duplicates.

    The amount for each month comes from the lease, not from a field read here:
    a stepped lease answers per period and a triple-net month carries both its
    rent and its NNN (E1, ADR-013).
    """
    refuse_if_not_chargeable(lease)

    created: list[Charge] = []
    for due in rent_due_dates(lease, through=through):
        created.extend(_create_rent_charge(lease, due, actor=actor))
        if lease.uses_nnn:
            created.extend(_create_nnn_charge(lease, due, actor=actor))
        created.extend(_create_responsibility_charges(lease, due, actor=actor))
    return created


def has_due_charges_to_post(lease: Lease, *, through: dt.date, charges=None) -> bool:
    """Whether charge generation would add at least one entry through ``through``.

    The eligibility half of `generate_charges` — the same predicate, so a screen cannot offer
    a button the service would refuse. ``charges`` lets a caller that already holds them (a
    ledger being read on a screen) answer without another query.
    """
    if charge_refusal(lease) is not None:
        return False
    if charges is None:
        charges = lease.charges.all()
    existing = {(row.kind, row.responsibility_id, row.due_date) for row in charges}
    for due in rent_due_dates(lease, through=through):
        if (ChargeKind.RENT, None, due) not in existing:
            return True
        if lease.uses_nnn and lease.nnn_for(due) > ZERO:
            if (ChargeKind.NNN, None, due) not in existing:
                return True
        for responsibility, _amount in responsibilities_due(lease, due):
            if (ChargeKind.RESPONSIBILITY, responsibility.pk, due) not in existing:
                return True
    return False


def _create_rent_charge(lease: Lease, due: dt.date, *, actor) -> list[Charge]:
    # get_or_create also absorbs a concurrent double submit: the unique
    # constraint is one rent charge per lease per due date.
    charge, was_created = Charge.objects.get_or_create(
        lease=lease,
        kind=ChargeKind.RENT,
        due_date=due,
        defaults={
            "amount": lease.rent_for(due),
            "description": f"Rent for {due:%B %Y}",
            "created_by": _actor(actor),
        },
    )
    if not was_created:
        return []
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
    from apps.accounting.services import post_charge

    post_charge(charge, actor=_actor(actor))
    return [charge]


def _create_nnn_charge(lease: Lease, due: dt.date, *, actor) -> list[Charge]:
    """A triple-net month's NNN, at the rate the lease stages for that date."""
    amount = lease.nnn_for(due)
    if amount <= ZERO:
        # No rate has been staged for this month yet. Nothing is charged, and the
        # lease's own screen says so rather than raising a silent zero.
        return []

    charge, was_created = Charge.objects.get_or_create(
        lease=lease,
        kind=ChargeKind.NNN,
        due_date=due,
        defaults={
            "amount": amount,
            "description": f"NNN for {due:%B %Y}",
            "created_by": _actor(actor),
        },
    )
    if not was_created:
        return []
    record(
        actor,
        AuditAction.CHARGE_CREATED,
        obj=charge,
        lease=lease,
        summary=f"NNN charge for {due:%B %Y} created ({charge.amount})",
        amount=charge.amount,
        due_date=due,
        source="NNN generation",
    )
    from apps.accounting.services import post_charge

    post_charge(charge, actor=_actor(actor))
    return [charge]


def responsibilities_due(
    lease: Lease, due: dt.date, *, lock=False
) -> list[tuple[PropertyResponsibility, Decimal]]:
    """The property bills this tenancy carries on one due date (E2).

    A responsibility counts when it is active, its staged cycle covers the month,
    and the unit has a share for that cycle. No share means the unit is not carrying
    it — which is how a unit opts out, and how a vacant unit's share stays with the
    landlord instead of being invented for a tenant.
    """
    unit = lease.unit
    due_rows: list[tuple[PropertyResponsibility, Decimal]] = []
    responsibilities = PropertyResponsibility.objects.filter(
        property_id=unit.property_id, is_active=True
    ).order_by("pk")
    if lock:
        responsibilities = responsibilities.select_for_update()
    for responsibility in responsibilities:
        cycle = responsibility.cycle_covering(due)
        if cycle is None or not cycle.covers(due, lease):
            continue
        share = next((entry for entry in cycle.shares.all() if entry.unit_id == unit.pk), None)
        if share is None or share.monthly_amount <= ZERO:
            continue
        due_rows.append((responsibility, share.monthly_amount))
    return due_rows


def _create_responsibility_charges(lease: Lease, due: dt.date, *, actor) -> list[Charge]:
    """One charge per property responsibility the unit carries this month."""
    created: list[Charge] = []
    for responsibility, amount in responsibilities_due(lease, due, lock=True):
        charge, was_created = Charge.objects.get_or_create(
            lease=lease,
            kind=ChargeKind.RESPONSIBILITY,
            responsibility=responsibility,
            due_date=due,
            defaults={
                "amount": amount,
                "description": f"{responsibility.label} for {due:%B %Y}",
                "created_by": _actor(actor),
            },
        )
        if not was_created:
            continue
        record(
            actor,
            AuditAction.CHARGE_CREATED,
            obj=charge,
            lease=lease,
            summary=(f"{responsibility.label} charge for {due:%B %Y} created ({charge.amount})"),
            amount=charge.amount,
            due_date=due,
            source="responsibility generation",
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
    opening: bool = False,
    direction: str = Direction.INCREASE,
) -> Charge:
    """A one-off charge — a repair recharge, a key replacement, a partial month.

    Refused on a tenancy that is not running (P4-Q3). Until a charge can carry its evidence
    (Phase 6, P4-E6), a debt discovered after a tenancy ends is billed by reopening the
    tenancy, so the record says why.

    ``opening=True`` is the one deliberate exception (ADR-028 D4): the reviewed starting
    account creates the brought-forward line while the tenancy still *needs its starting
    account*, which is the act that places it. It is still refused on a draft, an ended
    tenancy or a settled account — the P4-Q3/E6 hole stays closed — and it records the
    ``CHARGE_CREATED`` event like every other charge.
    """
    if opening:
        refuse_if_account_settled(lease)
        if lease.status != LeaseStatus.ACTIVE:
            raise ValidationError(NOT_CHARGEABLE[lease.status])
        if kind != ChargeKind.OPENING:
            raise ValidationError("Only a brought-forward charge can be recorded as an opening.")
        if amount <= ZERO:
            raise ValidationError("An opening charge must be greater than zero.")
        if direction not in (Direction.INCREASE, Direction.DECREASE):
            raise ValidationError("An opening charge moves the balance up or down.")
    else:
        refuse_if_not_chargeable(lease)
        direction = Direction.INCREASE
    charge = Charge(
        lease=lease,
        kind=kind,
        direction=direction,
        description=description,
        amount=amount,
        due_date=due_date,
        aging_unknown=opening,
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
        source="starting account" if opening else "manual charge",
    )
    from apps.accounting.services import post_charge

    post_charge(charge, actor=_actor(actor))
    return charge


@transaction.atomic
def create_adjustment(
    charge: Charge,
    *,
    direction: str,
    amount: Decimal,
    reason: str,
    actor=None,
    reviewed_repayment=False,
) -> Charge:
    """A correction to a charge, as its own entry. The original stays visible.

    The target must be a charge, never another correction: a correction of a correction is
    invisible to the ledger's rows while still moving the balance, so a manager corrects the
    original charge again instead — which is what they mean by "put it back".
    """
    refuse_if_account_settled(charge.lease)
    from apps.ledger.applications import current_plans, reconcile_correction

    refuse_if_account_settled(charge.lease)
    if not reviewed_repayment and any(
        plan.charge_id == charge.pk for plan in current_plans(charge.lease)
    ):
        raise ValidationError(
            "Review the starting debt correction and repayment schedule together."
        )
    if charge.kind == ChargeKind.ADJUSTMENT or charge.adjusts_id is not None:
        raise ValidationError(
            "An adjustment corrects a charge; it cannot itself be adjusted. Correct the "
            "original charge again instead — another adjustment on it says what changed."
        )
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
    reconcile_correction(charge, actor=_actor(actor), release_target=not reviewed_repayment)
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
    from apps.accounting.services import post_charge

    post_charge(adjustment, actor=_actor(actor))
    return adjustment


def close_out_candidates(lease: Lease, *, on: dt.date):
    """The charges a close-out would cancel: what the schedule raised after ``on``.

    One definition, used by the end screen (to show the office what it is about to cancel)
    and by the close-out itself (to cancel it), so the two can never disagree.
    """
    return (
        lease.charges.filter(kind__in=SCHEDULED_KINDS, due_date__gt=on)
        # A charge that already carries a correction is left for a person: canceling its full
        # amount a second time would overshoot, and the first adjustment is somebody's decision.
        .filter(adjustments__isnull=True)
        .select_related("responsibility")
        .order_by("due_date")
    )


@transaction.atomic
def close_out_lease(
    lease: Lease, *, on: dt.date, keep=(), reason: str = "", actor=None
) -> list[Charge]:
    """Cancel the months a tenancy will not use, by adjustment — never by deletion (P4-Q2).

    Each canceled charge keeps its row and gains an adjustment naming the reason, so the
    tenant's statement shows the charge and what corrected it. Idempotent: a second call
    finds nothing left to cancel. ``keep`` holds the ids of charges the office decided the
    tenant still owes, which are left exactly as they are.
    """
    kept = {int(pk) for pk in keep}
    settled_reason = reason or f"Tenancy ended {on:%d %B %Y}"
    adjustments: list[Charge] = []
    for charge in close_out_candidates(lease, on=on):
        if charge.pk in kept:
            continue
        adjustments.append(
            create_adjustment(
                charge,
                direction=Direction.DECREASE,
                amount=charge.amount,
                reason=settled_reason,
                actor=actor,
            )
        )
    return adjustments


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
    refuse_if_account_settled(lease)
    from apps.ledger.applications import allocate_receipt

    refuse_if_account_settled(lease)
    cutover = FinancialCutover.objects.first()
    if cutover is not None:
        if lease.needs_starting_account:
            raise ValidationError("Set the starting account balance before recording payments.")
        if payment_date < cutover.first_native_date:
            raise ValidationError(
                "Earlier payments belong in the starting account, not as new receipts."
            )
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
    if status == PaymentStatus.CLEARED:
        allocate_receipt(payment, actor=_actor(actor))
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
    if status == PaymentStatus.CLEARED:
        from apps.accounting.services import post_payment

        post_payment(payment, transition="recorded", actor=_actor(actor))
    return payment


@transaction.atomic
def clear_payment(payment: Payment, *, actor=None) -> Payment:
    """The expected money arrived."""
    refuse_if_account_settled(payment.lease)
    from apps.ledger.applications import allocate_receipt

    payment.refresh_from_db()
    refuse_if_account_settled(payment.lease)
    if payment.status != PaymentStatus.PENDING:
        raise ValidationError("Only a pending payment can be marked as cleared.")
    payment.status = PaymentStatus.CLEARED
    payment.save(update_fields=["status"])
    allocate_receipt(payment, actor=_actor(actor))
    record(
        actor,
        AuditAction.PAYMENT_CLEARED,
        obj=payment,
        lease=payment.lease,
        summary=f"Payment of {payment.amount} cleared",
        amount=payment.amount,
        payment_date=payment.payment_date,
    )
    from apps.accounting.services import post_payment

    post_payment(payment, transition="cleared", actor=_actor(actor))
    return payment


@transaction.atomic
def void_payment(payment: Payment, *, actor=None, reason: str = "") -> Payment:
    """The expected money never existed — canceled before it was money."""
    refuse_if_account_settled(payment.lease)
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
    refuse_if_account_settled(payment.lease)
    from apps.ledger.applications import release_source

    payment.refresh_from_db()
    refuse_if_account_settled(payment.lease)
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
    release_source(payment, actor=_actor(actor))
    record(
        actor,
        AuditAction.PAYMENT_REVERSED,
        obj=reversal,
        lease=payment.lease,
        summary=(
            f"Payment of {payment.amount} on {payment.payment_date:%b} "
            f"{payment.payment_date.day}, {payment.payment_date.year} reversed: {reason}"
        ),
        amount=payment.amount,
        reversed_payment=str(payment.pk),
        reason=reason,
    )
    from apps.accounting.services import post_payment

    post_payment(payment, transition="reversed", actor=_actor(actor))
    return reversal


# --- the accounting overview ----------------------------------------------


def lease_search(term: str) -> Q:
    """The text a desk types to find a tenancy: unit, property, or tenant name."""
    return (
        Q(unit__identifier__icontains=term)
        | Q(unit__property__name__icontains=term)
        | Q(lease_tenants__person__first_name__icontains=term)
        | Q(lease_tenants__person__last_name__icontains=term)
        | Q(lease_tenants__tenant__username__icontains=term)
    )


def ledger_rows(*, search: str = "", property_id=None) -> list[LeaseLedger]:
    """Every lease that can owe money, with its ledger, in desk order."""
    leases = (
        Lease.objects.exclude(status=LeaseStatus.DRAFT)
        .select_related("unit__property")
        .prefetch_related("lease_tenants__person")
    )
    if property_id:
        leases = leases.filter(unit__property_id=property_id)
    if search:
        leases = leases.filter(lease_search(search)).distinct()
    return by_urgency(build_ledgers(leases).values())

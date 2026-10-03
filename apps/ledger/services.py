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
from apps.leases.models import Lease, LeaseStatus, LeaseTemplate
from apps.ledger.models import (
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
        return self.left > ZERO and self.date < timezone.localdate()

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
    """One month of a tenancy's charges, as the tenant's card reads it (E2).

    A reading, not a record: the month's rent, NNN and responsibilities are separate
    ledger entries that share a due date, and this sums them so a tenant sees one
    figure and can open it up. ``LeaseLedger.statement`` still holds the plain rows
    (ADR-011).
    """

    date: dt.date
    rows: list[ComponentRow] = field(default_factory=list)
    kind: str = "month"

    @property
    def components(self) -> list[StatementCharge]:
        return [row.component for row in self.rows]

    @property
    def total(self) -> Decimal:
        """What the month costs, at the figures the charges now stand at."""
        return sum((component.amount for component in self.components), ZERO)

    @property
    def left(self) -> Decimal:
        return sum((component.left for component in self.components), ZERO)

    @property
    def state(self) -> str:
        """The month's own state: the most pressing thing in it wins."""
        states = [component.state for component in self.components]
        if not states:
            return ChargeState.UNPAID
        if ChargeState.OVERDUE in states:
            return ChargeState.OVERDUE
        if ChargeState.PENDING in states:
            return ChargeState.PENDING
        if ChargeState.PARTIAL in states:
            return ChargeState.PARTIAL
        if all(state == ChargeState.PAID for state in states):
            return ChargeState.PAID
        if all(state == ChargeState.ADJUSTMENT for state in states):
            return ChargeState.ADJUSTMENT
        return ChargeState.UNPAID

    @property
    def state_label(self) -> str:
        if self.state == ChargeState.ADJUSTMENT:
            return "Nothing to pay"
        return STATE_LABELS[self.state]

    @property
    def is_one_line(self) -> bool:
        """A month of a single charge needs no card: it reads as a row."""
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
        """The month's responsibilities under their categories, in a stable order."""
        groups: dict[str, ResponsibilityGroup] = {}
        for row in self.responsibility_rows:
            label = row.component.category or "Other"
            groups.setdefault(label, ResponsibilityGroup(label=label)).rows.append(row)
        return [groups[label] for label in sorted(groups)]


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
        return sum((row.left for row in self.statement_charges if row.date <= today), ZERO)

    @property
    def arrears(self) -> Decimal:
        """The part of what is owed whose due date has already passed."""
        today = timezone.localdate()
        return sum((row.left for row in self.statement_charges if row.date < today), ZERO)

    @property
    def has_arrears(self) -> bool:
        return self.arrears > ZERO

    @property
    def arrears_oldest(self) -> StatementCharge | None:
        """The oldest unpaid charge, so a screen can say how far behind this is.

        The desk works the oldest bucket first, and the age is what says so.
        """
        overdue = [row for row in self.statement_charges if row.date < timezone.localdate()]
        unpaid = [row for row in overdue if row.left > ZERO]
        return min(unpaid, key=lambda row: (row.date, row.title), default=None)

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
        return sum((row.left for row in self.statement_charges if row.date > today), ZERO)

    # --- the next date a tenant has to pay, and what that month costs -------
    # A month is rent plus NNN today, and responsibilities once E2 lands. The
    # card states the whole figure, because a tenant who is told only the rent
    # is being told a number smaller than the bill (E1, ADR-013).

    @property
    def next_due_date(self) -> dt.date | None:
        """The next date anything falls due, billed or forecast from the lease."""
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
        see an empty card because nobody pressed a button.
        """
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
            reductions = sum(
                (-entry.balance_effect for entry in adjustments if entry.balance_effect < ZERO),
                ZERO,
            )
            net = charge.amount + adjusted_by
            # `settled` holds corrections first and money after them, so what is
            # left once the corrections are taken out is what was actually paid.
            paid = max(line.settled - reductions, ZERO)
            responsibility = charge.responsibility
            rows.append(
                StatementCharge(
                    date=charge.due_date,
                    title=charge.description,
                    detail=charge.get_kind_display(),
                    gross=charge.amount,
                    net=net,
                    adjusted_by=adjusted_by,
                    adjustment_count=len(adjustments),
                    paid=paid,
                    left=max(net - paid, ZERO),
                    pending=line.pending,
                    charge_kind=charge.kind,
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
        grouped: list[StatementMonth | StatementPayment] = []
        for row in self.statement:
            if isinstance(row, StatementPayment):
                grouped.append(row)
                continue
            component = ComponentRow(component=row, note=self._note_for(row, row.date))
            last = grouped[-1] if grouped else None
            if isinstance(last, StatementMonth) and last.date == row.date:
                last.rows.append(component)
            else:
                grouped.append(StatementMonth(date=row.date, rows=[component]))
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
        leases = leases.prefetch_related(
            Prefetch("charges", queryset=Charge.objects.select_related("responsibility")),
            "payments",
        )
    return {lease.pk: build_ledger(lease) for lease in leases}


def totals(ledgers) -> dict:
    """The portfolio totals behind the accounting overview."""
    ledgers = list(ledgers)
    return {
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


def generate_charges(lease: Lease, *, through: dt.date, actor=None) -> list[Charge]:
    """Create the missing rent — and NNN — charges for a lease; never duplicates.

    The amount for each month comes from the lease, not from a field read here:
    a stepped lease answers per period and a triple-net month carries both its
    rent and its NNN (E1, ADR-013).
    """
    if lease.status == LeaseStatus.DRAFT:
        raise ValidationError(
            "A draft lease has no ledger yet: its terms can still change. Activate the lease first."
        )

    created: list[Charge] = []
    for due in rent_due_dates(lease, through=through):
        created.extend(_create_rent_charge(lease, due, actor=actor))
        if lease.template == LeaseTemplate.NNN:
            created.extend(_create_nnn_charge(lease, due, actor=actor))
        created.extend(_create_responsibility_charges(lease, due, actor=actor))
    return created


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
    return [charge]


def responsibilities_due(
    lease: Lease, due: dt.date
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
    )
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
    for responsibility, amount in responsibilities_due(lease, due):
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

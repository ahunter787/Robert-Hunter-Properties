"""Read-only financial meanings, applied only to an already-authorized ledger."""

import calendar
from dataclasses import replace
from decimal import Decimal

from django.utils import timezone

from apps.ledger.models import ChargeKind
from apps.ledger.services import ComponentRow, StatementMonth, upcoming_rent_date

CHARGE_ICONS = {
    ChargeKind.RENT: "rent",
    ChargeKind.NNN: "charge",
    ChargeKind.RESPONSIBILITY: "recovery",
    ChargeKind.MANUAL: "charge",
    ChargeKind.ADJUSTMENT: "correction",
    ChargeKind.OPENING: "starting",
}


def charge_icon(kind):
    """A charge's financial meaning, not a document upload/download action."""
    return CHARGE_ICONS.get(kind, "charge")


def charge_label(charge):
    """Keep historical model identifiers while presenting the approved product term."""
    if charge.kind == ChargeKind.RESPONSIBILITY:
        return "Expense Recovery"
    return charge.get_kind_display()


def bill_history(ledger, *, newest=False):
    """Group corrected charges before ordering/filtering; never change financial allocation.

    The historic StatementMonth name remains for existing statement consumers. It represents
    an exact due-date bill, including a bill with just one component, not a calendar month.
    """
    bills = {}
    transactions = ledger.transactions
    charges = {row.charge_entry.pk: row for row in transactions if row.charge_entry is not None}
    for component in ledger.statement_charges:
        source = charges[component.charge_id]
        # Standalone reductions are credits, not positive bills. Read the immutable entry's
        # signed effect; do not alter the existing allocation engine or classify it as cash.
        net = source.charge - source.payment_or_credit
        component = replace(component, net=net, left=max(net - component.paid, Decimal("0.00")))
        bill = bills.setdefault(component.date, StatementMonth(date=component.date))
        bill.rows.append(
            ComponentRow(component=component, note=ledger._note_for(component, component.date))
        )
    payments = []
    for row in transactions:
        if row.charge_entry is not None:
            bills[row.date].transactions.append(row)
        else:
            payments.append(row)
    # Bills precede payments on the same date in BOTH display directions. Running balances
    # are calculated in chronological order before changing the direction of date groups.
    days = {}
    for date, bill in bills.items():
        days.setdefault(date, []).append(bill)
    for row in payments:
        days.setdefault(row.date, []).append(row)
    balance = Decimal("0.00")
    for date in sorted(days):
        for index, row in enumerate(days[date]):
            effect = (
                row.total if isinstance(row, StatementMonth) else row.charge - row.payment_or_credit
            )
            balance += effect
            if isinstance(row, StatementMonth):
                row.running_balance = balance
            else:
                days[date][index] = replace(row, running_balance=balance)
    rows = [row for date in sorted(days, reverse=newest) for row in days[date]]
    for row in rows:
        if isinstance(row, StatementMonth) and row.nnn_rows:
            row.spells_out_nnn = True
            break
    return rows


def transaction_history(ledger, *, sort="newest", history="year"):
    """Derive full-history balances first, then select/order the visible transactions."""
    sort = sort if sort in ("newest", "oldest") else "newest"
    history = history if history in ("year", "all") else "year"
    today = timezone.localdate()
    previous_year = today.year - 1
    cutoff = today.replace(
        year=previous_year,
        day=min(today.day, calendar.monthrange(previous_year, today.month)[1]),
    )
    complete = bill_history(ledger, newest=sort == "newest")
    rows = complete if history == "all" else [row for row in complete if row.date >= cutoff]
    return {
        "transaction_rows": rows,
        "transaction_sort": sort,
        "transaction_history": history,
        "transaction_cutoff": cutoff,
        "transaction_total": len(complete),
        "transaction_hidden_count": len(complete) - len(rows),
    }


def financial_summary(ledger):
    """Keep forecasts separate from posted debt; never infer cash from a balance."""
    scheduled_date = upcoming_rent_date(ledger.lease) if ledger.lease.can_be_charged else None
    if scheduled_date and any(
        line.charge.kind == ChargeKind.RENT and line.charge.due_date == scheduled_date
        for line in ledger.charges
    ):
        scheduled_date = None
    empty = not ledger.charges and not ledger.payments
    paid_in_full = (
        ledger.balance_due == 0
        and any(row.net > 0 for row in ledger.statement_charges)
        and not ledger.pending_payments
    )
    return {
        "ledger": ledger,
        "empty": empty,
        "paid_in_full": paid_in_full,
        "scheduled_date": scheduled_date,
        "scheduled_amount": ledger.lease.rent_for(scheduled_date) if scheduled_date else None,
        "upcoming_date": ledger.next_charge.date if ledger.next_charge else None,
    }

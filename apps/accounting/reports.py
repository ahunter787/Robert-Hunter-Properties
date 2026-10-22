"""B4 reports: every number is a reading of journal lines (or the source it already has)."""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.accounting.models import AccountKind, JournalLine

ZERO = Decimal("0.00")
CASH_CODES = ("1110", "1120", "1450")
SCHEDULE_E = {
    "4000": ("3", "Rents received"),
    "4100": ("3", "Rents received"),
    "4200": ("3", "Rents received"),
    "4300": ("3", "Rents received"),
    "4350": ("3", "Rents received"),
    "4900": ("3", "Rents received"),
    "5000": ("14", "Repairs"),
    "5100": ("17", "Utilities"),
    "5200": ("16", "Taxes"),
    "5300": ("9", "Insurance"),
    "5400": ("12", "Mortgage interest"),
    "5500": ("10", "Legal and professional"),
    "5600": ("18", "Other"),
    "5700": ("18", "Other"),
    "5900": ("18", "Other"),
}


def _q(start=None, end=None, property=None):
    lines = JournalLine.objects.select_related("entry", "account")
    if start is not None:
        lines = lines.filter(entry__posted_on__gte=start)
    if end is not None:
        lines = lines.filter(entry__posted_on__lte=end)
    if property is not None:
        lines = lines.filter(property=property)
    return lines


def income_statement(start, end, property=None):
    rows = {}
    for line in _q(start, end, property).filter(
        account__kind__in=(AccountKind.INCOME, AccountKind.EXPENSE)
    ):
        account = line.account
        amount = (
            line.credit - line.debit
            if account.kind == AccountKind.INCOME
            else line.debit - line.credit
        )
        row = rows.setdefault(account.pk, {"account": account, "amount": ZERO})
        row["amount"] += amount
    ordered = sorted(rows.values(), key=lambda row: (row["account"].kind, row["account"].code))
    income = [row for row in ordered if row["account"].kind == AccountKind.INCOME]
    expenses = [row for row in ordered if row["account"].kind == AccountKind.EXPENSE]
    total_income = sum((row["amount"] for row in income), ZERO)
    total_expenses = sum((row["amount"] for row in expenses), ZERO)
    return {
        "income": income,
        "expenses": expenses,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net": total_income - total_expenses,
    }


def _account_balance(account, as_of):
    total = JournalLine.objects.filter(account=account, entry__posted_on__lte=as_of).aggregate(
        debit=Sum("debit"), credit=Sum("credit")
    )
    debit = total["debit"] or ZERO
    credit = total["credit"] or ZERO
    return debit - credit if account.normal_side == "DEBIT" else credit - debit


def balance_sheet(as_of, property=None):
    lines = JournalLine.objects.select_related("account").filter(entry__posted_on__lte=as_of)
    if property is not None:
        lines = lines.filter(property=property)
    totals = (
        lines.values(
            "account__pk",
            "account__code",
            "account__name",
            "account__kind",
            "account__normal_side",
        )
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
        .order_by("account__code")
    )
    assets, liabilities, equity = [], [], []
    for row in totals:
        debit = row["debit"] or ZERO
        credit = row["credit"] or ZERO
        amount = debit - credit if row["account__normal_side"] == "DEBIT" else credit - debit
        if amount == ZERO:
            continue
        item = {
            "code": row["account__code"],
            "name": row["account__name"],
            "amount": amount,
        }
        if row["account__kind"] == AccountKind.ASSET:
            assets.append(item)
        elif row["account__kind"] == AccountKind.LIABILITY:
            liabilities.append(item)
        elif row["account__kind"] == AccountKind.EQUITY:
            equity.append(item)
    earnings = income_statement(date.min, as_of, property)["net"]
    if earnings:
        equity.append({"code": "", "name": "Current earnings", "amount": earnings})
    total_assets = sum((row["amount"] for row in assets), ZERO)
    total_liabilities = sum((row["amount"] for row in liabilities), ZERO)
    total_equity = sum((row["amount"] for row in equity), ZERO)
    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "balanced": total_assets == total_liabilities + total_equity,
    }


def cash_flow(start, end, property=None):
    """A direct cash summary from bank and undeposited-funds lines."""
    cash_lines = _q(start, end, property).filter(account__code__in=CASH_CODES)
    inflow = {}
    outflow = {}
    for line in cash_lines:
        cash_effect = line.debit - line.credit
        counterpart = (
            line.entry.lines.select_related("account").exclude(account__code__in=CASH_CODES).first()
        )
        label = counterpart.account.name if counterpart else "Cash movement"
        category = "operating"
        if counterpart:
            if counterpart.account.kind == AccountKind.EQUITY:
                category = "financing"
            elif counterpart.account.kind == AccountKind.ASSET and counterpart.account.code not in (
                "1200",
                "1300",
                "1400",
                "1450",
            ):
                # AR is an operating item; only non-current/prepaid assets are investing.
                category = "investing"
        bucket = inflow if cash_effect > ZERO else outflow
        key = (category, label)
        bucket[key] = bucket.get(key, ZERO) + abs(cash_effect)
    rows = []
    for category in ("operating", "investing", "financing"):
        for label, amount in sorted(inflow.items()):
            if label[0] == category:
                rows.append({"category": category, "label": label[1], "amount": amount})
        for label, amount in sorted(outflow.items()):
            if label[0] == category:
                rows.append({"category": category, "label": label[1], "amount": -amount})
    # The opening/closing cash figures come from account balances, not the flows.
    from apps.accounting.models import ChartAccount

    accounts = ChartAccount.objects.filter(code__in=CASH_CODES)
    opening = sum(
        (_account_balance(account, start - timedelta(days=1)) for account in accounts),
        ZERO,
    )
    closing = sum((_account_balance(account, end) for account in accounts), ZERO)
    return {
        "rows": rows,
        "inflow": sum((row["amount"] for row in rows if row["amount"] > ZERO), ZERO),
        "outflow": sum((-row["amount"] for row in rows if row["amount"] < ZERO), ZERO),
        "net": sum((row["amount"] for row in rows), ZERO),
        "opening": opening,
        "closing": closing,
    }


def schedule_e(start, end, property=None):
    rows = income_statement(start, end, property)
    grouped = {}
    for row in rows["income"] + rows["expenses"]:
        default = (
            "18" if row["account"].kind == AccountKind.EXPENSE else "3",
            "Other" if row["account"].kind == AccountKind.EXPENSE else "Rents received",
        )
        line, label = SCHEDULE_E.get(row["account"].code, default)
        bucket = grouped.setdefault(line, {"line": line, "label": label, "amount": ZERO})
        bucket["amount"] += row["amount"]
    ordered = sorted(grouped.values(), key=lambda row: int(row["line"]))
    return {"lines": ordered, "net": rows["net"]}


def ar_aging(as_of=None):
    from apps.leases.models import Lease
    from apps.ledger.services import build_ledgers

    as_of = as_of or timezone.localdate()
    buckets = {"current": ZERO, "1–30": ZERO, "31–60": ZERO, "61–90": ZERO, "90+": ZERO}
    rows = []
    for lease in Lease.objects.exclude(status="DRAFT").select_related("unit__property"):
        ledger = build_ledgers([lease])[lease.pk]
        for obligation in ledger.obligations:
            if obligation.date > as_of or obligation.left <= ZERO or obligation.unknown:
                continue
            age = (as_of - obligation.date).days
            if age <= 0:
                bucket = "current"
            elif age <= 30:
                bucket = "1–30"
            elif age <= 60:
                bucket = "31–60"
            elif age <= 90:
                bucket = "61–90"
            else:
                bucket = "90+"
            buckets[bucket] += obligation.left
            rows.append(
                {
                    "lease": lease,
                    "date": obligation.date,
                    "description": obligation.charge.description,
                    "amount": obligation.left,
                    "bucket": bucket,
                }
            )
    return {"rows": rows, "buckets": buckets, "total": sum(buckets.values(), ZERO)}


def ap_aging(as_of=None):
    from apps.accounting.models import VendorBill

    as_of = as_of or timezone.localdate()
    buckets = {"current": ZERO, "1–30": ZERO, "31–60": ZERO, "61–90": ZERO, "90+": ZERO}
    rows = []
    for bill in VendorBill.objects.prefetch_related("payments"):
        if bill.balance <= ZERO:
            continue
        age = (as_of - bill.due_date).days
        if age <= 0:
            bucket = "current"
        elif age <= 30:
            bucket = "1–30"
        elif age <= 60:
            bucket = "31–60"
        elif age <= 90:
            bucket = "61–90"
        else:
            bucket = "90+"
        buckets[bucket] += bill.balance
        rows.append({"bill": bill, "bucket": bucket, "amount": bill.balance})
    return {"rows": rows, "buckets": buckets, "total": sum(buckets.values(), ZERO)}


def deposit_register(as_of=None):
    from apps.leases.models import Lease
    from apps.ledger.deposits import entries, held

    as_of = as_of or timezone.localdate()
    rows = []
    for lease in Lease.objects.exclude(status="DRAFT").select_related("unit__property"):
        rows.append({"lease": lease, "held": held(lease), "entries": entries(lease)})
    return {"rows": rows, "total": sum((row["held"] for row in rows), ZERO)}

"""Posting service: the only writer of journals (B1, ADR-032).

Every journal is a double-entry reading of one explicit kernel source transition. It is
balanced, immutable, and keyed by ``<model>:<pk>:<transition>``; replaying the transition
returns the existing journal instead of posting a second time. No caller may hand-write a
journal line against a control account.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounting.models import (
    AccountKind,
    AccountMapping,
    ChartAccount,
    JournalEntry,
    JournalLine,
)

ZERO = Decimal("0.00")
MONEY = Decimal("0.01")
CONTROL_CODES = {"1110", "1120", "1200", "1450", "2100", "2300", "2400"}


def _signed_money(value) -> Decimal:
    try:
        return Decimal(value or ZERO).quantize(MONEY)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError("A balance must be a decimal number.") from exc


def _money(value) -> Decimal:
    try:
        amount = Decimal(value)
    except Exception as exc:  # noqa: BLE001 - a bad amount is a validation failure
        raise ValidationError("A journal amount must be a decimal number.") from exc
    if amount <= ZERO:
        raise ValidationError("A journal line must be greater than zero.")
    return amount.quantize(MONEY)


def ensure_seeded():
    """Restore the seeded chart if a flushed test database has lost it."""
    from django.db import OperationalError, ProgrammingError

    try:
        if ChartAccount.objects.exists():
            return
        from apps.accounting.seed import seed_defaults

        seed_defaults()
    except OperationalError, ProgrammingError:
        # A historical-migration test may not have the accounting tables yet.
        return


def account(code: str) -> ChartAccount:
    ensure_seeded()
    try:
        return ChartAccount.objects.get(code=code, is_active=True)
    except ChartAccount.DoesNotExist as exc:
        raise ValidationError(f"The chart has no active account {code}.") from exc


def mapping(event_key: str) -> ChartAccount:
    ensure_seeded()
    row = AccountMapping.objects.select_related("account").filter(event_key=event_key).first()
    if row is None or not row.account.is_active:
        raise ValidationError(f"The chart has no active mapping for {event_key}.")
    return row.account


def post_journal(
    *,
    source_key: str,
    event_type: str,
    posted_on,
    lines,
    lease=None,
    property=None,
    memo: str = "",
    actor=None,
) -> JournalEntry:
    """Post one balanced journal, or return the one already posted for ``source_key``."""
    if not source_key or not event_type or posted_on is None:
        raise ValidationError("A journal needs a source key, an event type and a date.")
    ensure_seeded()
    existing = JournalEntry.objects.filter(source_key=source_key).first()
    if existing is not None:
        return existing

    prepared = []
    total_debit = ZERO
    total_credit = ZERO
    for row in lines:
        if isinstance(row["account"], str):
            chart_account = account(row["account"])
        else:
            chart_account = row["account"]
        if not chart_account.is_active:
            raise ValidationError(f"Account {chart_account.code} is inactive.")
        debit = ZERO if not row.get("debit") else _money(row["debit"])
        credit = ZERO if not row.get("credit") else _money(row["credit"])
        if (debit > ZERO) == (credit > ZERO):
            raise ValidationError("A journal line is either a debit or a credit, never both.")
        total_debit += debit
        total_credit += credit
        prepared.append(
            {
                "account": chart_account,
                "debit": debit,
                "credit": credit,
                "property": row.get("property") or property,
                "memo": row.get("memo", ""),
            }
        )
    if not prepared:
        raise ValidationError("A journal needs at least one line.")
    if total_debit != total_credit:
        raise ValidationError(
            f"The journal does not balance: debits {total_debit}, credits {total_credit}."
        )
    if property is None and lease is not None:
        property = lease.unit.property

    try:
        with transaction.atomic():
            entry = JournalEntry.objects.create(
                source_key=source_key,
                event_type=event_type,
                posted_on=posted_on,
                property=property,
                lease=lease,
                memo=memo[:500],
                created_by=actor if getattr(actor, "is_authenticated", False) else None,
            )
            JournalLine.objects.bulk_create([JournalLine(entry=entry, **line) for line in prepared])
    except IntegrityError:
        # A concurrent poster won the unique source key; its journal is the truth.
        return JournalEntry.objects.get(source_key=source_key)
    return entry


def post_manual_journal(*, source_key, posted_on, lines, memo, actor, property=None):
    """A reviewed manual journal, refused on any control account (ADR-032 D4)."""
    for row in lines:
        chart_account = (
            account(row["account"]) if isinstance(row["account"], str) else row["account"]
        )
        if chart_account.is_control or chart_account.code in CONTROL_CODES:
            raise ValidationError(
                "Control accounts move only from kernel source events; a manual journal "
                "cannot touch them."
            )
    return post_journal(
        source_key=source_key,
        event_type="manual",
        posted_on=posted_on,
        lines=lines,
        property=property,
        memo=memo,
        actor=actor,
    )


def _income_account(charge) -> ChartAccount:
    if charge.kind == "NNN":
        return mapping("charge.NNN")
    if charge.kind == "RESPONSIBILITY":
        category = getattr(getattr(charge, "responsibility", None), "category", None)
        if category == "UTILITY":
            return mapping("charge.UTILITY")
        if category == "MAINTENANCE":
            return mapping("charge.MAINTENANCE")
        return mapping("charge.OTHER")
    if charge.kind == "MANUAL":
        return mapping("charge.MANUAL")
    if charge.kind == "RENT":
        return mapping("charge.RENT")
    return mapping("charge.DEFAULT")


def _original_account(charge) -> ChartAccount:
    original = getattr(charge, "adjusts", None)
    if original is None:
        return mapping("charge.DEFAULT")
    entry = JournalEntry.objects.filter(source_key=f"charge:{original.pk}:created").first()
    if entry is not None:
        for line in entry.lines.select_related("account"):
            if line.account.code != "1200":
                return line.account
    return _income_account(original)


def post_charge(charge, *, actor=None) -> JournalEntry:
    """Post a charge or its correction exactly once."""
    amount = _money(charge.amount)
    if charge.kind == "ADJUSTMENT":
        original = charge.adjusts
        if original is not None and original.kind == "OPENING" and original.direction == "DECREASE":
            # An opening credit lives in 2400, not AR; correcting it moves 2400/3070.
            if charge.direction == "INCREASE":
                lines = [
                    {"account": "2400", "debit": amount, "memo": charge.description},
                    {"account": "3070", "credit": amount, "memo": charge.description},
                ]
            else:
                lines = [
                    {"account": "3070", "debit": amount, "memo": charge.description},
                    {"account": "2400", "credit": amount, "memo": charge.description},
                ]
        else:
            income = _original_account(charge)
            if charge.direction == "DECREASE":
                lines = [
                    {"account": income, "debit": amount, "memo": charge.description},
                    {"account": "1200", "credit": amount, "memo": charge.description},
                ]
            else:
                lines = [
                    {"account": "1200", "debit": amount, "memo": charge.description},
                    {"account": income, "credit": amount, "memo": charge.description},
                ]
        event_type = "charge.adjustment"
    elif charge.kind == "OPENING" and charge.direction == "DECREASE":
        # A brought-forward credit is money owed to the tenant, not a receivable reduction.
        lines = [
            {"account": "3070", "debit": amount, "memo": charge.description},
            {"account": "2400", "credit": amount, "memo": charge.description},
        ]
        event_type = "charge.opening_credit"
    elif charge.kind == "OPENING":
        lines = [
            {"account": "1200", "debit": amount, "memo": charge.description},
            {"account": "3070", "credit": amount, "memo": charge.description},
        ]
        event_type = "charge.opening_debt"
    else:
        income = _income_account(charge)
        lines = [
            {"account": "1200", "debit": amount, "memo": charge.description},
            {"account": income, "credit": amount, "memo": charge.description},
        ]
        event_type = f"charge.{charge.kind.lower()}"
    return post_journal(
        source_key=f"charge:{charge.pk}:created",
        event_type=event_type,
        posted_on=charge.due_date,
        lines=lines,
        lease=charge.lease,
        memo=f"{charge.get_kind_display()}: {charge.description}",
        actor=actor,
    )


def post_payment(payment, *, transition: str, actor=None) -> JournalEntry:
    """Post a receipt, a late clearing, or a reversal; pending money posts nothing."""
    amount = _money(payment.amount)
    if transition == "reversed":
        lines = [
            {"account": "1200", "debit": amount, "memo": f"Reverse payment {payment.pk}"},
            {"account": "1450", "credit": amount, "memo": "Reversed receipt"},
        ]
        event_type = "payment.reversed"
    else:
        lines = [
            {"account": "1450", "debit": amount, "memo": payment.get_method_display()},
            {"account": "1200", "credit": amount, "memo": "Tenant payment received"},
        ]
        event_type = "payment.received"
    return post_journal(
        source_key=f"payment:{payment.pk}:{transition}",
        event_type=event_type,
        posted_on=payment.payment_date,
        lines=lines,
        lease=payment.lease,
        memo=f"Payment {payment.pk} {payment.get_status_display().lower()}",
        actor=actor,
    )


def post_application(application, *, actor=None) -> JournalEntry | None:
    """A credit application moves held tenant credit to AR; receipts are already in AR."""
    if application.source_deposit_id:
        deposit = application.source_deposit
        if deposit.kind != "WITHHELD":
            return None
        amount = _money(application.amount)
        released = application.reverses_id is not None
        if released:
            lines = [
                {"account": "1200", "debit": amount, "memo": "Released retained deposit"},
                {"account": "2300", "credit": amount, "memo": "Released retained deposit"},
            ]
            event_type = "deposit.application_released"
            key = f"application:{application.pk}:released"
        else:
            lines = [
                {"account": "2300", "debit": amount, "memo": "Retained deposit applied"},
                {"account": "1200", "credit": amount, "memo": "Retained deposit applied"},
            ]
            event_type = "deposit.applied"
            key = f"application:{application.pk}:applied"
        return post_journal(
            source_key=key,
            event_type=event_type,
            posted_on=(
                application.created_at.date() if application.created_at else timezone.localdate()
            ),
            lines=lines,
            lease=application.lease,
            memo=f"Deposit application {application.pk}",
            actor=actor,
        )
    if application.source_payment_id:
        return None
    source_charge = application.source_charge
    if source_charge is None or source_charge.kind != "OPENING":
        return None
    if source_charge.direction != "DECREASE":
        return None
    amount = _money(application.amount)
    released = application.reverses_id is not None
    if released:
        lines = [
            {"account": "1200", "debit": amount, "memo": "Released tenant credit"},
            {"account": "2400", "credit": amount, "memo": "Released tenant credit"},
        ]
        event_type = "credit.released"
        key = f"application:{application.pk}:released"
    else:
        lines = [
            {"account": "2400", "debit": amount, "memo": "Tenant credit applied"},
            {"account": "1200", "credit": amount, "memo": "Tenant credit applied"},
        ]
        event_type = "credit.applied"
        key = f"application:{application.pk}:applied"
    return post_journal(
        source_key=key,
        event_type=event_type,
        posted_on=application.created_at.date() if application.created_at else timezone.localdate(),
        lines=lines,
        lease=application.lease,
        memo=f"Credit application {application.pk}",
        actor=actor,
    )


def unposted_count() -> int:
    """How many existing source events have no journal yet."""
    from apps.ledger.models import Charge, FundsApplication, Payment, PaymentKind, PaymentStatus

    missing = 0
    missing += sum(
        1
        for charge in Charge.objects.all()
        if not JournalEntry.objects.filter(source_key=f"charge:{charge.pk}:created").exists()
    )
    for payment in Payment.objects.all():
        if payment.kind == PaymentKind.REVERSAL:
            key = f"payment:{payment.reverses_id}:reversed"
        elif payment.status == PaymentStatus.CLEARED:
            key = f"payment:{payment.pk}:recorded"
        else:
            continue
        if not JournalEntry.objects.filter(source_key=key).exists():
            missing += 1
    for application in FundsApplication.objects.all():
        transition = "released" if application.reverses_id else "applied"
        if not JournalEntry.objects.filter(
            source_key=f"application:{application.pk}:{transition}"
        ).exists():
            missing += 1
    return missing


def trial_balance(*, as_of=None, property=None):
    """Every account's debit/credit activity up to ``as_of``, in code order."""
    lines = JournalLine.objects.select_related("account", "entry")
    if as_of is not None:
        lines = lines.filter(entry__posted_on__lte=as_of)
    if property is not None:
        lines = lines.filter(property=property)
    totals = {}
    for line in lines:
        row = totals.setdefault(
            line.account.code,
            {"account": line.account, "debit": ZERO, "credit": ZERO},
        )
        row["debit"] += line.debit
        row["credit"] += line.credit
    return [totals[code] for code in sorted(totals)]


def account_balance(code: str, *, as_of=None, property=None) -> Decimal:
    lines = JournalLine.objects.filter(account__code=code)
    if as_of is not None:
        lines = lines.filter(entry__posted_on__lte=as_of)
    if property is not None:
        lines = lines.filter(property=property)
    debit = sum((line.debit for line in lines), ZERO)
    credit = sum((line.credit for line in lines), ZERO)
    chart_account = account(code)
    return (debit - credit) if chart_account.normal_side == "DEBIT" else (credit - debit)


def net_tenant_receivable(*, as_of=None, property=None) -> Decimal:
    """AR less tenant credits held: the number the tenant sub-ledger must equal."""
    return account_balance("1200", as_of=as_of, property=property) - account_balance(
        "2400", as_of=as_of, property=property
    )


def ar_control_tie(*, as_of=None, property=None):
    """Compare the GL control to the tenant sub-ledger; any difference is a defect."""
    from apps.leases.models import Lease
    from apps.ledger.services import build_ledger

    leases = Lease.objects.exclude(status="DRAFT").select_related("unit__property")
    if property is not None:
        leases = leases.filter(unit__property=property)
    subledger = ZERO
    for lease in leases:
        subledger += build_ledger(lease).balance_due
    control = net_tenant_receivable(as_of=as_of, property=property)
    return {
        "control": control.quantize(MONEY),
        "subledger": subledger.quantize(MONEY),
        "difference": (control - subledger).quantize(MONEY),
    }


@transaction.atomic
def post_opening_batch(*, as_of, note, lines, actor=None):
    """Post a reviewed opening balance sheet. The batch and its journal are one unit.

    Opening balances are the one place a control account may be debited/credited by a
    manager, because they establish the starting position rather than adjust history. The
    batch is immutable; a correction is another reviewed batch or a reversing entry.
    """
    from uuid import uuid4

    from apps.accounting.models import OpeningBalanceBatch, OpeningBalanceLine
    from apps.audit.models import AuditAction
    from apps.audit.services import record

    if not note or not note.strip():
        raise ValidationError("Say where these opening balances came from.")
    prepared = []
    total_debit = ZERO
    total_credit = ZERO
    for row in lines:
        chart_account = (
            account(row["account"]) if isinstance(row["account"], str) else row["account"]
        )
        if chart_account.kind not in (
            AccountKind.ASSET,
            AccountKind.LIABILITY,
            AccountKind.EQUITY,
        ):
            raise ValidationError(
                "Opening balances may only use asset, liability and equity accounts."
            )
        debit = ZERO if not row.get("debit") else _money(row["debit"])
        credit = ZERO if not row.get("credit") else _money(row["credit"])
        if (debit > ZERO) == (credit > ZERO):
            raise ValidationError("Each opening line is either a debit or a credit.")
        total_debit += debit
        total_credit += credit
        prepared.append(
            {
                "account": chart_account,
                "debit": debit,
                "credit": credit,
                "property": row.get("property"),
                "memo": row.get("memo", ""),
            }
        )
    if len(prepared) < 2:
        raise ValidationError("At least two opening lines are needed.")
    if total_debit != total_credit:
        raise ValidationError(
            f"Opening balances do not balance: debits {total_debit}, credits {total_credit}."
        )
    key = uuid4()
    batch = OpeningBalanceBatch.objects.create(
        key=key,
        as_of=as_of,
        note=note.strip(),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    OpeningBalanceLine.objects.bulk_create(
        [OpeningBalanceLine(batch=batch, **row) for row in prepared]
    )
    journal = post_journal(
        source_key=f"opening:{key}:posted",
        event_type="opening.balance",
        posted_on=as_of,
        lines=prepared,
        memo=note.strip(),
        actor=actor,
    )
    batch.journal = journal
    batch.save(update_fields=["journal"])
    record(
        actor,
        AuditAction.ACCOUNTING_OPENING_POSTED,
        obj=batch,
        summary=f"Opening balances posted for {as_of}",
        total_debit=str(total_debit),
        total_credit=str(total_credit),
        lines=len(prepared),
    )
    return batch


def post_deposit(entry) -> JournalEntry | None:
    """Post deposit money received or returned; retention waits for its E6 charge."""
    if entry.kind not in ("RECEIVED", "RETURNED"):
        return None
    amount = _money(entry.amount)
    if entry.kind == "RECEIVED":
        lines = [
            {"account": "1450", "debit": amount, "memo": "Security deposit received"},
            {"account": "2300", "credit": amount, "memo": "Security deposit held"},
        ]
        event_type = "deposit.received"
    elif entry.kind == "RETURNED":
        lines = [
            {"account": "2300", "debit": amount, "memo": "Security deposit returned"},
            {"account": "1450", "credit": amount, "memo": "Security deposit refund paid"},
        ]
        event_type = "deposit.returned"
    else:
        # WITHHELD: the documented method raises the E6 charge first; NOT_COLLECTED is zero.
        return None
    return post_journal(
        source_key=f"deposit:{entry.pk}:{entry.kind.lower()}",
        event_type=event_type,
        posted_on=entry.date,
        lines=lines,
        lease=entry.lease,
        memo=f"Security deposit {entry.get_kind_display().lower()}",
        actor=entry.created_by,
    )


def deposit_control_tie():
    """GL security-deposit liability against the held-deposit register.

    A retention posts nothing until its E6 charge exists, so a nonzero difference is the
    expected pending disposition until then; it is never adjusted away.
    """
    from apps.leases.models import Lease
    from apps.ledger.deposits import held

    register = ZERO
    for lease in Lease.objects.exclude(status="DRAFT"):
        register += held(lease)
    gl = account_balance("2300")
    return {
        "control": gl.quantize(MONEY),
        "register": register.quantize(MONEY),
        "difference": (gl - register).quantize(MONEY),
    }


@transaction.atomic
def record_vendor_bill(
    *,
    property,
    vendor,
    expense_account,
    description,
    amount,
    received_on,
    due_date,
    note="",
    actor=None,
):
    """Record a vendor bill: Dr expense / Cr accounts payable."""
    from apps.accounting.models import VendorBill
    from apps.audit.models import AuditAction
    from apps.audit.services import record

    account_obj = account(expense_account) if isinstance(expense_account, str) else expense_account
    if account_obj.kind != AccountKind.EXPENSE:
        raise ValidationError("A vendor bill must use an expense account.")
    amount = _money(amount)
    bill = VendorBill.objects.create(
        property=property,
        vendor=vendor,
        expense_account=account_obj,
        description=description.strip(),
        amount=amount,
        received_on=received_on,
        due_date=due_date,
        note=note.strip(),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    journal = post_journal(
        source_key=f"bill:{bill.pk}:recorded",
        event_type="vendor_bill.recorded",
        posted_on=received_on,
        lines=[
            {"account": account_obj, "debit": amount, "memo": description},
            {"account": "2100", "credit": amount, "memo": "Accounts payable"},
        ],
        property=property,
        memo=f"Vendor bill {bill.pk}: {description}",
        actor=actor,
    )
    bill.journal = journal
    bill.save(update_fields=["journal"])
    record(
        actor,
        AuditAction.VENDOR_BILL_RECORDED,
        obj=bill,
        summary=f"Vendor bill {description} recorded ({amount})",
        amount=str(amount),
        property=str(property.pk),
    )
    return bill


@transaction.atomic
def pay_vendor_bill(
    bill,
    *,
    amount,
    paid_on,
    method="ACH",
    reference="",
    note="",
    actor=None,
):
    """Pay a vendor bill: Dr accounts payable / Cr undeposited funds until B3."""
    from apps.accounting.models import VendorPayment
    from apps.audit.models import AuditAction
    from apps.audit.services import record
    from apps.ledger.models import MINIMUM_AMOUNT

    amount = _money(amount)
    if amount < MINIMUM_AMOUNT:
        raise ValidationError("A payment must be at least one cent.")
    if amount > bill.balance:
        raise ValidationError("A bill cannot be paid more than its remaining balance.")
    payment = VendorPayment.objects.create(
        bill=bill,
        amount=amount,
        paid_on=paid_on,
        method=method,
        reference=reference.strip(),
        note=note.strip(),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    journal = post_journal(
        source_key=f"billpayment:{payment.pk}:recorded",
        event_type="vendor_payment.recorded",
        posted_on=paid_on,
        lines=[
            {"account": "2100", "debit": amount, "memo": f"Pay bill {bill.pk}"},
            {"account": "1450", "credit": amount, "memo": "Vendor payment pending bank"},
        ],
        property=bill.property,
        memo=f"Vendor payment {payment.pk} for bill {bill.pk}",
        actor=actor,
    )
    payment.journal = journal
    payment.save(update_fields=["journal"])
    record(
        actor,
        AuditAction.VENDOR_BILL_PAID,
        obj=payment,
        summary=f"Vendor bill {bill.pk} paid ({amount})",
        amount=str(amount),
        bill=str(bill.pk),
    )
    return payment


def ap_control_tie():
    """GL accounts payable against the sum of unpaid vendor bills."""
    from apps.accounting.models import VendorBill

    subledger = ZERO
    for bill in VendorBill.objects.prefetch_related("payments"):
        subledger += bill.balance
    control = account_balance("2100")
    return {
        "control": control.quantize(MONEY),
        "subledger": subledger.quantize(MONEY),
        "difference": (control - subledger).quantize(MONEY),
    }


@transaction.atomic
def record_bank_movement(
    bank_account,
    *,
    date,
    kind,
    amount,
    reference="",
    memo="",
    actor=None,
):
    """Move money between undeposited funds and the bank, posting the clearing entry."""
    from apps.accounting.models import BankMovement
    from apps.audit.models import AuditAction
    from apps.audit.services import record

    amount = _money(amount)
    if kind not in ("DEPOSIT", "WITHDRAWAL"):
        raise ValidationError("Choose whether money was deposited or withdrawn.")
    bank_gl = account(bank_account.chart_account.code)
    if kind == "DEPOSIT":
        lines = [
            {"account": bank_gl, "debit": amount, "memo": "Bank deposit"},
            {"account": "1450", "credit": amount, "memo": "Undeposited funds cleared"},
        ]
    else:
        lines = [
            {"account": "1450", "debit": amount, "memo": "Bank withdrawal"},
            {"account": bank_gl, "credit": amount, "memo": "Money left the bank"},
        ]
    movement = BankMovement.objects.create(
        bank_account=bank_account,
        date=date,
        kind=kind,
        amount=amount,
        reference=reference.strip(),
        memo=memo.strip(),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    journal = post_journal(
        source_key=f"bankmovement:{movement.pk}:recorded",
        event_type=f"bank_movement.{kind.lower()}",
        posted_on=date,
        lines=lines,
        property=None,
        memo=f"Bank {kind.lower()} {amount} · {bank_account.name}",
        actor=actor,
    )
    movement.journal = journal
    movement.save(update_fields=["journal"])
    record(
        actor,
        AuditAction.BANK_MOVEMENT_RECORDED,
        obj=movement,
        summary=f"Bank {kind.lower()} of {amount} on {bank_account.name}",
        amount=str(amount),
        bank=str(bank_account.pk),
    )
    return movement


@transaction.atomic
def import_bank_statement(
    bank_account,
    *,
    period_start,
    period_end,
    opening_balance,
    closing_balance,
    rows,
    source_name="",
    actor=None,
):
    """Create a statement and its lines, then auto-match exact bank GL movements."""
    from apps.accounting.models import BankStatement, StatementLine
    from apps.audit.models import AuditAction
    from apps.audit.services import record

    if period_end < period_start:
        raise ValidationError("The statement period ends before it starts.")
    if BankStatement.objects.filter(
        bank_account=bank_account, period_start=period_start, period_end=period_end
    ).exists():
        raise ValidationError("That bank/period has already been imported.")
    statement = BankStatement.objects.create(
        bank_account=bank_account,
        period_start=period_start,
        period_end=period_end,
        opening_balance=_signed_money(opening_balance),
        closing_balance=_signed_money(closing_balance),
        imported_by=actor if getattr(actor, "is_authenticated", False) else None,
        source_name=source_name[:200],
    )
    StatementLine.objects.bulk_create(
        [
            StatementLine(
                statement=statement,
                date=row["date"],
                description=row["description"][:300],
                amount=row["amount"],
                reference=row.get("reference", "")[:200],
            )
            for row in rows
        ]
    )
    matched = auto_match_statement(statement)
    record(
        actor,
        AuditAction.BANK_STATEMENT_IMPORTED,
        obj=statement,
        summary=f"Statement {period_start}–{period_end} imported for {bank_account.name}",
        lines=len(rows),
        matched=matched,
        closing=str(closing_balance),
    )
    return statement


def auto_match_statement(statement) -> int:
    """Match statement lines to bank GL movements by exact amount and nearby date."""
    from apps.accounting.models import StatementLine

    bank_account = statement.bank_account
    gl_lines = JournalLine.objects.select_related("entry").filter(
        account=bank_account.chart_account
    )
    taken = set(
        StatementLine.objects.exclude(matched_journal_line__isnull=True).values_list(
            "matched_journal_line_id", flat=True
        )
    )
    candidates = []
    for line in gl_lines:
        if line.pk in taken:
            continue
        signed = line.debit - line.credit
        candidates.append((line, signed))
    matched = 0
    for statement_line in statement.lines.filter(matched_journal_line__isnull=True).order_by(
        "date", "pk"
    ):
        best = None
        best_distance = None
        for line, signed in candidates:
            if signed != statement_line.amount:
                continue
            distance = abs((line.entry.posted_on - statement_line.date).days)
            if distance > 5:
                continue
            if best is None or distance < best_distance:
                best, best_distance = line, distance
        if best is not None:
            statement_line.matched_journal_line = best
            statement_line.save(update_fields=["matched_journal_line"])
            candidates = [row for row in candidates if row[0].pk != best.pk]
            matched += 1
    return matched


@transaction.atomic
def reconcile_bank_statement(statement, *, actor=None):
    """Reconcile only when every statement line is matched and the balances agree."""
    from apps.accounting.models import BankReconciliation
    from apps.audit.models import AuditAction
    from apps.audit.services import record

    if hasattr(statement, "reconciliation"):
        raise ValidationError("This statement is already reconciled.")
    if statement.lines.filter(matched_journal_line__isnull=True).exists():
        raise ValidationError(
            "Every statement line must be matched before the statement can be reconciled."
        )
    cleared = sum((line.amount for line in statement.lines.all()), ZERO)
    adjusted = (statement.opening_balance + cleared).quantize(MONEY)
    difference = (statement.closing_balance - adjusted).quantize(MONEY)
    if difference != ZERO:
        raise ValidationError(
            f"The statement does not balance: closing {statement.closing_balance}, "
            f"adjusted {adjusted}, difference {difference}."
        )
    gl = account_balance(statement.bank_account.chart_account.code, as_of=statement.period_end)
    if gl != statement.closing_balance:
        raise ValidationError(
            f"The bank GL balance at {statement.period_end} is {gl}, not the statement's "
            f"closing {statement.closing_balance}. Post or match the missing movement first."
        )
    reconciliation = BankReconciliation.objects.create(
        statement=statement,
        cleared_total=cleared.quantize(MONEY),
        adjusted_balance=adjusted,
        difference=difference,
        reconciled_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    record(
        actor,
        AuditAction.BANK_RECONCILED,
        obj=statement,
        summary=f"Statement {statement.period_start}–{statement.period_end} reconciled",
        cleared=str(cleared),
        adjusted=str(adjusted),
        closing=str(statement.closing_balance),
    )
    return reconciliation


def bank_control_tie(bank_account):
    """GL bank balance against the latest reconciled statement, if any."""
    gl = account_balance(bank_account.chart_account.code)
    latest = bank_account.statements.exclude(reconciliation__isnull=True).first()
    if latest is None:
        return {"control": gl.quantize(MONEY), "statement": None, "difference": None}
    closing = latest.closing_balance
    return {
        "control": gl.quantize(MONEY),
        "statement": closing,
        "difference": (gl - closing).quantize(MONEY),
    }

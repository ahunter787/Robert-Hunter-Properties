"""The held-deposit register: money held, returned, retained, or not collected.

A security deposit is the tenant's money RHP holds until move-out. It is not AR and not a
credit (ADR-008, amended by ADR-028 D5), so it never moves a tenant balance; the register's
derived balance is what is held. The lease keeps the *agreed* deposit as a term, and the two
are deliberately different facts: a lease can say "1,850" while nothing was collected, and
the register is where the office says which is true.

Entries are append-only. A refund or a retention is a new entry with a reason, never an
edit; a move-out outcome is the set of entries recorded before the account settles.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.models import AuditAction
from apps.audit.services import record as audit_record
from apps.ledger.models import MINIMUM_AMOUNT, DepositEntry, DepositKind

ZERO = Decimal("0.00")


def entries(lease):
    """Every deposit fact for one tenancy, oldest first."""
    return list(lease.deposit_entries.all())


def held(lease) -> Decimal:
    """What RHP is holding for this tenant right now.

    Received money counts; a return or a retention releases it. ``NOT_COLLECTED`` is a
    statement, not money, so it moves nothing.
    """
    received = sum(
        (entry.amount for entry in entries(lease) if entry.kind == DepositKind.RECEIVED), ZERO
    )
    released = sum(
        (
            entry.amount
            for entry in entries(lease)
            if entry.kind in (DepositKind.RETURNED, DepositKind.WITHHELD)
        ),
        ZERO,
    )
    return (received - released).quantize(ZERO)


def has_received(lease) -> bool:
    return any(entry.kind == DepositKind.RECEIVED for entry in entries(lease))


def has_not_collected(lease) -> bool:
    return any(entry.kind == DepositKind.NOT_COLLECTED for entry in entries(lease))


def addressed(lease) -> bool:
    """Whether the agreed deposit has a recorded outcome.

    An explicit "not collected" is an outcome. Otherwise money was received and all of it
    has been returned or retained. A zero agreed deposit needs nothing.
    """
    if lease.deposit <= ZERO:
        return True
    if has_not_collected(lease):
        return True
    return has_received(lease) and held(lease) <= ZERO


def blocker(lease) -> str | None:
    """Why settlement cannot proceed on the deposit, or ``None`` when it can."""
    balance = held(lease)
    if balance > ZERO:
        return (
            f"{balance} of the security deposit is still held. Record what happened to it — "
            "returned, retained with a reason, or explicitly not collected — on the security "
            "deposit screen, then settle the account."
        )
    if not addressed(lease):
        return (
            "The agreed security deposit has no recorded outcome. Record whether it was held "
            "and returned or retained, or that it was never collected, on the security deposit "
            "screen, then settle the account."
        )
    return None


@transaction.atomic
def record(
    lease,
    *,
    kind: str,
    amount: Decimal,
    date,
    method: str = "",
    reference: str = "",
    reason: str = "",
    evidence=None,
    actor=None,
):
    """Append one deposit fact. Server-side validation; the view is not the only caller."""
    from apps.ledger.services import refuse_if_account_settled

    refuse_if_account_settled(lease)
    if kind not in DepositKind.values:
        raise ValidationError("Choose what happened to the deposit.")
    reason = (reason or "").strip()

    if kind == DepositKind.NOT_COLLECTED:
        amount = ZERO
        if not reason:
            raise ValidationError(
                {"reason": "Say why no deposit was collected, so the record is honest."}
            )
        if has_received(lease) or held(lease) > ZERO:
            raise ValidationError(
                "This account already records deposit money. Record a return or a retention "
                "instead of saying none was collected."
            )
    else:
        amount = Decimal(amount or ZERO)
        if amount < MINIMUM_AMOUNT:
            raise ValidationError({"amount": "Enter an amount of at least one cent."})
        if kind in (DepositKind.RETURNED, DepositKind.WITHHELD):
            if lease.status != "ENDED":
                raise ValidationError(
                    "A deposit is returned or retained when the tenancy ends, not before."
                )
            balance = held(lease)
            if amount > balance:
                raise ValidationError(
                    {"amount": f"Only {balance} is held; you cannot release more than that."}
                )
            if kind == DepositKind.WITHHELD and not reason:
                raise ValidationError(
                    {"reason": "Say what was retained and why — the tenant is entitled to know."}
                )
        if kind == DepositKind.RECEIVED and lease.status != "ACTIVE":
            raise ValidationError("Record deposit money while the tenancy is running.")

    if evidence is not None and (evidence.lease_id != lease.pk or evidence.tenant_visible):
        raise ValidationError("Choose a staff-only document filed against this tenancy.")

    entry = DepositEntry(
        lease=lease,
        kind=kind,
        amount=amount,
        date=date,
        method=method,
        reference=(reference or "").strip(),
        reason=reason,
        evidence=evidence,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    entry.full_clean()
    entry.save()
    audit_record(
        actor,
        AuditAction.DEPOSIT_CHANGED,
        obj=entry,
        lease=lease,
        summary=f"Security deposit {entry.get_kind_display().lower()}: {amount}",
        kind=kind,
        amount=str(amount),
        date=str(date),
        held_after=str(held(lease)),
        reason=reason,
    )
    return entry

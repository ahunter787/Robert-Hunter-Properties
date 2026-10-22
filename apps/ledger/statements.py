"""The move-out statement: one page that closes a tenancy's money (E5, ADR-031).

Industry practice is a final accounting: final charges, payments and credits, then the
security deposit applied to what is owed, then the remainder refunded or carried as owed,
with every deduction named (APM Help on Buildium; ERG's ledger guide). RHP derives the
statement from the same ledger and deposit register every other screen reads, and records
its issuance as an append-only audit event so the copy sent to the tenant has a date and an
author. The statement is not a second balance: it explains the one balance.
"""

import datetime as dt
import json
from dataclasses import dataclass, field
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.ledger import deposits
from apps.ledger.services import build_ledger

ZERO = Decimal("0.00")
OUTCOME_TENANT_OWES = "TENANT_OWES"
OUTCOME_PROPERTY_OWES = "PROPERTY_OWES"
OUTCOME_ZERO = "ZERO"


@dataclass
class MoveOutStatement:
    lease: object
    charged: Decimal
    paid: Decimal
    deposit_entries: list
    deposit_received: Decimal
    deposit_returned: Decimal
    deposit_withheld: Decimal
    deposit_not_collected: Decimal
    deposit_applied: Decimal
    deposit_held: Decimal
    balance_due: Decimal
    credit_held: Decimal
    tenant_owes: Decimal
    property_owes: Decimal
    outcome: str
    outcome_amount: Decimal
    charges: list = field(default_factory=list)
    payments: list = field(default_factory=list)
    issued_at: dt.datetime | None = None
    issued_by: object = None
    issue_note: str = ""

    @property
    def forwarding_address(self) -> str:
        return self.lease.forwarding_address

    @property
    def outcome_label(self) -> str:
        return {
            OUTCOME_TENANT_OWES: "The tenant owes RHP",
            OUTCOME_PROPERTY_OWES: "RHP owes the tenant",
            OUTCOME_ZERO: "Nothing further is owed either way",
        }[self.outcome]

    @property
    def deposit_withheld_entries(self):
        return [entry for entry in self.deposit_entries if entry.kind == "WITHHELD"]

    def snapshot(self) -> dict:
        """The durable facts recorded when the statement is issued."""
        return {
            "forwarding_address": self.forwarding_address,
            "charged": str(self.charged),
            "paid": str(self.paid),
            "deposit_received": str(self.deposit_received),
            "deposit_returned": str(self.deposit_returned),
            "deposit_withheld": str(self.deposit_withheld),
            "deposit_not_collected": str(self.deposit_not_collected),
            "deposit_applied": str(self.deposit_applied),
            "deposit_held": str(self.deposit_held),
            "balance_due": str(self.balance_due),
            "credit_held": str(self.credit_held),
            "outcome": self.outcome,
            "outcome_amount": str(self.outcome_amount),
            "deposit_entries": [
                {
                    "kind": entry.kind,
                    "amount": str(entry.amount),
                    "date": entry.date.isoformat(),
                    "reason": entry.reason,
                }
                for entry in self.deposit_entries
            ],
            "issued_on": dt.date.today().isoformat(),
        }


def build(lease) -> MoveOutStatement:
    """Derive the final accounting from the ledger and the held-deposit register."""
    ledger = build_ledger(lease)
    entries = deposits.entries(lease)
    totals = dict.fromkeys(("RECEIVED", "RETURNED", "WITHHELD", "NOT_COLLECTED"), ZERO)
    for entry in entries:
        totals[entry.kind] += entry.amount
    charged = sum((line.charge.balance_effect for line in ledger.charges), ZERO)
    paid = sum((payment.amount for payment in ledger.effective_payments), ZERO)
    tenant_owes = max(ledger.balance_due, ZERO)
    property_owes = (
        max(-ledger.balance_due, ZERO) + deposits.held(lease) + ledger.credit
    ).quantize(ZERO)
    if tenant_owes > ZERO:
        outcome, amount = OUTCOME_TENANT_OWES, tenant_owes
    elif property_owes > ZERO:
        outcome, amount = OUTCOME_PROPERTY_OWES, property_owes
    else:
        outcome, amount = OUTCOME_ZERO, ZERO
    return MoveOutStatement(
        lease=lease,
        charged=charged,
        paid=paid,
        deposit_entries=entries,
        deposit_received=totals["RECEIVED"],
        deposit_returned=totals["RETURNED"],
        deposit_withheld=totals["WITHHELD"],
        deposit_not_collected=totals["NOT_COLLECTED"],
        deposit_applied=ledger.deposit_applied,
        deposit_held=deposits.held(lease),
        balance_due=ledger.balance_due,
        credit_held=ledger.credit,
        tenant_owes=tenant_owes,
        property_owes=property_owes,
        outcome=outcome,
        outcome_amount=amount,
        charges=list(ledger.charges),
        payments=list(ledger.effective_payments),
    )


def latest(lease):
    """The most recently issued statement event, if any (append-only history keeps all)."""
    return (
        lease.audit_events.filter(action=AuditAction.MOVE_OUT_STATEMENT_ISSUED)
        .select_related("actor")
        .order_by("-created_at", "-pk")
        .first()
    )


def attach_issued(statement: MoveOutStatement):
    event = latest(statement.lease)
    if event is not None:
        statement.issued_at = event.created_at
        statement.issued_by = event.actor
        statement.issue_note = event.metadata.get("note", "")
    return statement


def issue(lease, *, actor, note: str = ""):
    """Record that the final accounting was issued to the tenant.

    A correction after issue is a new statement (another event), never an edit: the tenant
    may hold the earlier copy. The statement can be issued without a forwarding address
    (the portal may be how it reaches them), but the screen says when none is recorded.
    """
    if lease.status != "ENDED":
        raise ValidationError("The final statement is issued after the tenancy ends.")
    statement = build(lease)
    snapshot = statement.snapshot()
    event = record(
        actor,
        AuditAction.MOVE_OUT_STATEMENT_ISSUED,
        obj=lease,
        lease=lease,
        summary=(
            f"Move-out statement issued for {lease.unit.label}: {statement.outcome_label.lower()} "
            f"({statement.outcome_amount})"
        ),
        note=note.strip(),
        statement=json.dumps(snapshot, default=str),
    )
    return event

"""Durable bill applications and repayment projections. Reading never writes."""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.leases.cutover import authorize
from apps.leases.models import Lease
from apps.ledger.models import AllocationAccount, ChargeKind, FundsApplication

ZERO = Decimal("0.00")


def active(rows):
    released = {row.reverses_id for row in rows if row.reverses_id}
    return [row for row in rows if not row.reverses_id and row.pk not in released]


def current_plans(lease):
    plans = list(lease.repayment_plans.all())
    superseded = {plan.previous_id for plan in plans if plan.previous_id}
    return [plan for plan in plans if plan.pk not in superseded]


@dataclass
class Obligation:
    charge: object
    date: dt.date
    amount: Decimal
    paid: Decimal = ZERO
    key: object = None
    unknown: bool = False

    @property
    def left(self):
        return max(self.amount - self.paid, ZERO)


def read(ledger):
    rows = sorted(ledger.lease.funds_applications.all(), key=lambda row: row.pk)
    ledger.application_history = rows
    rows = active(rows)
    active_ids = {row.pk for row in rows}
    for row in ledger.application_history:
        row.can_undo = row.pk in active_ids and row.is_credit
    ledger.plan_history = list(ledger.lease.repayment_plans.all())
    superseded = {plan.previous_id for plan in ledger.plan_history if plan.previous_id}
    plans = [plan for plan in ledger.plan_history if plan.pk not in superseded]
    ledger.repayment_plans = plans
    plan_by_charge = {plan.charge_id: plan for plan in plans}
    for line in ledger.charges:
        allocations = [row for row in rows if row.target_id == line.charge.pk]
        line.settled = sum((row.amount for row in allocations), ZERO)
        line.credit_applied = sum((row.amount for row in allocations if row.is_credit), ZERO)
        if line.charge.kind == ChargeKind.ADJUSTMENT or line.net_amount <= 0:
            continue
        plan = plan_by_charge.get(line.charge.pk)
        if plan:
            for installment in plan.installments.all():
                covered = sum(
                    (row.amount for row in allocations if row.installment_key == installment.key),
                    ZERO,
                )
                ledger.obligations.append(
                    Obligation(
                        line.charge,
                        installment.due_date,
                        installment.amount,
                        covered,
                        installment.key,
                    )
                )
        else:
            ledger.obligations.append(
                Obligation(
                    line.charge,
                    line.charge.due_date,
                    line.net_amount,
                    line.settled,
                    unknown=line.charge.aging_unknown,
                )
            )
    sources = []
    for payment in ledger.effective_payments:
        used = sum((row.amount for row in rows if row.source_payment_id == payment.pk), ZERO)
        sources.append(
            {
                "value": f"payment:{payment.pk}",
                "label": f"Payment received {payment.payment_date} · #{payment.pk}",
                "available": payment.amount - used,
            }
        )
    for line in ledger.charges:
        if line.charge.kind != ChargeKind.ADJUSTMENT and line.net_amount < ZERO:
            used = sum((row.amount for row in rows if row.source_charge_id == line.charge.pk), ZERO)
            sources.append(
                {
                    "value": f"charge:{line.charge.pk}",
                    "label": line.charge.description,
                    "available": -line.net_amount - used,
                }
            )
    ledger.credit_sources = [source for source in sources if source["available"] > ZERO]


@transaction.atomic
def initialize(lease):
    """Called by mutations/migration, never a read. Snapshot the old implied coverage."""
    lease = Lease.objects.select_for_update().get(pk=lease.pk)
    if AllocationAccount.objects.filter(lease=lease).exists():
        return lease
    from apps.ledger.services import build_ledger

    ledger = build_ledger(lease)
    sources = [("source_payment_id", p.pk, p.amount, False) for p in ledger.effective_payments]
    sources += [
        ("source_charge_id", line.charge.pk, -line.net_amount, True)
        for line in ledger.charges
        if line.charge.kind == ChargeKind.OPENING and line.net_amount < ZERO
    ]
    remaining = {line.charge.pk: line.settled for line in ledger.charges if line.settled > ZERO}
    for field, pk, amount, credit in sources:
        for line in sorted(ledger.charges, key=lambda row: (row.charge.due_date, row.charge.pk)):
            portion = min(amount, remaining.get(line.charge.pk, ZERO))
            if portion <= ZERO:
                continue
            FundsApplication.objects.create(
                lease=lease,
                target=line.charge,
                amount=portion,
                is_credit=credit,
                legacy_derived=True,
                reason="Legacy-derived allocation; not a manager-confirmed application",
                **{field: pk},
            )
            amount -= portion
            remaining[line.charge.pk] -= portion
    if any(value != ZERO for value in remaining.values()):
        raise ValidationError("Legacy allocations did not reconcile; initialization stopped.")
    AllocationAccount.objects.create(lease=lease)
    return lease


def release(row, *, actor=None, reason="", review_key=""):
    return FundsApplication.objects.create(
        lease_id=row.lease_id,
        source_payment_id=row.source_payment_id,
        source_charge_id=row.source_charge_id,
        target_id=row.target_id,
        installment_key=row.installment_key,
        amount=row.amount,
        reverses=row,
        is_credit=row.is_credit,
        created_by=actor,
        reason=reason,
        review_key=review_key,
    )


def allocate_receipt(payment, *, actor=None):
    from apps.ledger.services import build_ledger

    ledger = build_ledger(payment.lease)
    remaining = next(
        (s["available"] for s in ledger.credit_sources if s["value"] == f"payment:{payment.pk}"),
        ZERO,
    )
    for obligation in sorted(
        ledger.obligations, key=lambda row: (row.date, row.charge.pk, str(row.key or ""))
    ):
        if obligation.date > timezone.localdate():
            continue
        portion = min(remaining, obligation.left)
        if portion > ZERO:
            FundsApplication.objects.create(
                lease=payment.lease,
                source_payment=payment,
                target=obligation.charge,
                installment_key=obligation.key,
                amount=portion,
                created_by=actor,
            )
            remaining -= portion


def release_source(payment, *, actor=None):
    for row in active(list(payment.lease.funds_applications.all())):
        if row.source_payment_id == payment.pk:
            release(row, actor=actor, reason="Recorded payment undone")


def reconcile_correction(charge, *, actor=None, release_target=True):
    """Release only invalidated coverage; never silently move it to another bill."""
    from apps.ledger.services import build_ledger

    ledger = build_ledger(charge.lease)
    line = next(row for row in ledger.charges if row.charge.pk == charge.pk)
    rows = active(list(charge.lease.funds_applications.all()))
    target_excess = max(
        sum((r.amount for r in rows if r.target_id == charge.pk), ZERO)
        - max(line.net_amount, ZERO),
        ZERO,
    )
    if not release_target:
        target_excess = ZERO
    source_excess = max(
        sum((r.amount for r in rows if r.source_charge_id == charge.pk), ZERO)
        - max(-line.net_amount, ZERO),
        ZERO,
    )
    for source, excess in ((False, target_excess), (True, source_excess)):
        for row in reversed(rows):
            if (row.source_charge_id if source else row.target_id) != charge.pk or excess <= ZERO:
                continue
            release(row, actor=actor, reason="Coverage released by charge correction")
            kept = row.amount - min(excess, row.amount)
            if kept > ZERO:
                FundsApplication.objects.create(
                    lease=row.lease,
                    source_payment_id=row.source_payment_id,
                    source_charge_id=row.source_charge_id,
                    target_id=row.target_id,
                    installment_key=row.installment_key,
                    amount=kept,
                    is_credit=row.is_credit,
                    created_by=actor,
                    reason="Coverage retained after correction",
                )
            excess -= min(excess, row.amount)


def writable(lease, actor):
    authorize(actor)
    if lease.status == "DRAFT" or lease.is_settled:
        raise ValidationError(
            "Activate the lease and reopen its financial account before making changes."
        )


def audit(lease, actor, summary, **metadata):
    record(
        actor,
        AuditAction.CHARGE_ADJUSTED,
        lease=lease,
        summary=summary,
        workflow="funds_application",
        **metadata,
    )

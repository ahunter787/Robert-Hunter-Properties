"""Snapshot implied coverage, without asserting a manager approved it."""

from decimal import Decimal

from django.db import migrations


def preserve(apps, schema_editor):
    Lease = apps.get_model("leases", "Lease")
    Charge = apps.get_model("ledger", "Charge")
    Payment = apps.get_model("ledger", "Payment")
    Application = apps.get_model("ledger", "FundsApplication")
    Account = apps.get_model("ledger", "AllocationAccount")
    database = schema_editor.connection.alias
    zero = Decimal("0.00")
    for lease in Lease.objects.using(database).all().iterator():
        charges = list(
            Charge.objects.using(database).filter(lease=lease).order_by("due_date", "pk")
        )
        payments = list(
            Payment.objects.using(database).filter(lease=lease).order_by("payment_date", "pk")
        )
        reversed_ids = {p.reverses_id for p in payments if p.reverses_id}
        corrections = {}
        for row in charges:
            if row.adjusts_id:
                corrections[row.adjusts_id] = corrections.get(row.adjusts_id, zero) + (
                    row.amount if row.direction == "INCREASE" else -row.amount
                )
        net = {
            c.pk: (c.amount if c.direction == "INCREASE" else -c.amount)
            + corrections.get(c.pk, zero)
            for c in charges
            if not c.adjusts_id
        }
        sources = [
            ("source_payment_id", p.pk, p.amount, False)
            for p in payments
            if p.kind == "RECEIVED" and p.status == "CLEARED" and p.pk not in reversed_ids
        ]
        sources += [
            ("source_charge_id", c.pk, -net[c.pk], True)
            for c in charges
            if c.kind == "OPENING" and net.get(c.pk, zero) < zero
        ]
        remaining = {
            c.pk: max(net.get(c.pk, zero), zero) for c in charges if c.kind != "ADJUSTMENT"
        }
        expected = min(sum((s[2] for s in sources), zero), sum(remaining.values(), zero))
        allocated = zero
        for field, source_id, capacity, credit in sources:
            for charge in charges:
                amount = min(capacity, remaining.get(charge.pk, zero))
                if amount <= zero:
                    continue
                Application.objects.using(database).create(
                    lease_id=lease.pk,
                    target_id=charge.pk,
                    amount=amount,
                    is_credit=credit,
                    legacy_derived=True,
                    reason="Legacy-derived allocation; not a manager-confirmed application",
                    **{field: source_id},
                )
                capacity -= amount
                remaining[charge.pk] -= amount
                allocated += amount
        if allocated != expected:
            raise RuntimeError(f"Legacy allocation reconciliation failed for lease {lease.pk}")
        Account.objects.using(database).create(lease_id=lease.pk)


def reverse_snapshot(apps, schema_editor):
    """Only a disposable/untouched derived snapshot may be rebuilt by migration tests.

    Operational applications or agreements make reversal unsafe; refuse instead of losing history.
    Original charges and payments are never changed in either direction.
    """
    Application = apps.get_model("ledger", "FundsApplication")
    Plan = apps.get_model("ledger", "RepaymentPlan")
    Account = apps.get_model("ledger", "AllocationAccount")
    database = schema_editor.connection.alias
    if (
        Application.objects.using(database).filter(legacy_derived=False).exists()
        or Plan.objects.using(database).exists()
    ):
        from django.db.migrations.exceptions import IrreversibleError

        raise IrreversibleError(
            "Operational credit/repayment history exists; restore a backup instead."
        )
    Application.objects.using(database).all().delete()
    Account.objects.using(database).all().delete()


class Migration(migrations.Migration):
    dependencies = [("ledger", "0007_allocationaccount_repaymentplan_fundsapplication_and_more")]
    operations = [migrations.RunPython(preserve, reverse_snapshot)]

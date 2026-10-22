"""One allocation engine: snapshot any remaining implied coverage, then drop the marker.

ADR-028 D3. Before this migration, a tenancy without an ``AllocationAccount`` was read
through a read-time FIFO projection. The code no longer has that branch, so any lease that
still relied on it must have its coverage written down once, exactly as ledger 0008 did for
the tenancies that existed then. Leases that already have recorded applications are left
alone — the application rows are the record, and re-snapshotting would duplicate them.

The reverse discards only the derived snapshot rows and recreates the marker table; a
manager-confirmed application is never deleted here (ledger 0008's reverse refuses then).
"""

from decimal import Decimal

from django.db import migrations


def snapshot(apps, schema_editor):
    Lease = apps.get_model("leases", "Lease")
    Charge = apps.get_model("ledger", "Charge")
    Payment = apps.get_model("ledger", "Payment")
    Application = apps.get_model("ledger", "FundsApplication")
    database = schema_editor.connection.alias
    zero = Decimal("0.00")

    for lease in Lease.objects.using(database).all().iterator():
        if Application.objects.using(database).filter(lease_id=lease.pk).exists():
            continue

        charges = list(
            Charge.objects.using(database).filter(lease=lease).order_by("due_date", "pk")
        )
        payments = list(
            Payment.objects.using(database).filter(lease=lease).order_by("payment_date", "pk")
        )
        if not charges and not payments:
            continue

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


def drop_derived_snapshot(apps, schema_editor):
    """Reverse by discarding only the migration-derived rows.

    Manager-confirmed applications are never touched: if any exist, ledger 0008's own
    reverse refuses the rollback rather than destroying a decision. The derived rows are
    a snapshot of charges and payments, so a later forward migration rebuilds them.
    """
    Application = apps.get_model("ledger", "FundsApplication")
    database = schema_editor.connection.alias
    Application.objects.using(database).filter(legacy_derived=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("leases", "0011_lease_financial_ready_financialcutover_and_more"),
        ("ledger", "0008_preserve_legacy_applications"),
    ]

    operations = [
        migrations.RunPython(snapshot, drop_derived_snapshot),
        migrations.DeleteModel(name="AllocationAccount"),
    ]

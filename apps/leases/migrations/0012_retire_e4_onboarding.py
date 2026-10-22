"""Retire the E4 onboarding mechanism: keep the decision, drop the table.

ADR-028 D2. A tenancy's starting account is recorded by the reviewed E10 workflow
(ADR-027); the E4 HISTORY/POSITION record is no longer written or read, and its screen is
already unreachable (the onboarding URL serves the starting-account flow). The rows that
exist are *decisions someone made*, so they are preserved as append-only audit events before
the table is removed — the mechanism goes, the history does not.

The active development database has no E4 rows (it was reset under ADR-027), so this is a
no-op there; a restored archive keeps its placement decisions as audit events.

The reverse recreates an empty table and keeps the audit events: the rows are not
reconstructed, because inventing a placement decision is worse than losing the old shape.
"""

from django.db import migrations


def preserve_as_audit(apps, schema_editor):
    Onboarding = apps.get_model("leases", "LeaseOnboarding")
    AuditEvent = apps.get_model("audit", "AuditEvent")
    database = schema_editor.connection.alias
    for row in Onboarding.objects.using(database).all().iterator():
        method = (
            row.get_method_display()
            if hasattr(row, "get_method_display")
            else row.method
        )
        parts = [f"Retired E4 onboarding: {method}"]
        if row.received_total is not None:
            parts.append(f"received before RHP {row.received_total}")
        if row.opening_amount is not None:
            parts.append(f"opening amount {row.opening_amount}")
        if row.as_of is not None:
            parts.append(f"as of {row.as_of}")
        if row.note:
            parts.append(row.note)
        AuditEvent.objects.using(database).create(
            actor_id=row.set_by_id,
            lease_id=row.lease_id,
            action="LEASE_ONBOARDED",
            object_type="leases.LeaseOnboarding",
            object_id=row.pk,
            summary=" — ".join(parts)[:255],
            metadata={
                "workflow": "retired_e4_onboarding",
                "method": row.method,
                "as_of": str(row.as_of) if row.as_of else None,
                "received_total": (
                    str(row.received_total) if row.received_total is not None else None
                ),
                "opening_amount": (
                    str(row.opening_amount) if row.opening_amount is not None else None
                ),
                "note": row.note,
            },
        )


def restore_nothing(apps, schema_editor):
    """The E4 rows cannot be reconstructed from the audit events, and must not be invented.

    A reverse recreates the empty table (from DeleteModel) and leaves the preserved audit
    events in place — the mechanism comes back, the decisions stay where they were recorded.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
        ("leases", "0011_lease_financial_ready_financialcutover_and_more"),
    ]

    operations = [
        migrations.RunPython(preserve_as_audit, restore_nothing),
        migrations.DeleteModel(name="LeaseOnboarding"),
    ]

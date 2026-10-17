"""Every lease's single file becomes a categorised document row (ADR-022).

The file is **not moved**: the row points at the same storage path, so nothing is
re-uploaded and no link breaks. The row is **tenant-visible**, because tenants could
already open their lease — a migration must not take something away — and it is filed
against both the tenancy and the tenancy's property.

This runs before `leases/0010`, which drops the fields it reads: the dependency is
declared both ways so the order cannot be got wrong.
"""

from django.db import migrations

#: Written on every row this migration creates, so the reverse can find exactly them.
MIGRATION_NOTE = "Brought in from the lease's single file when documents arrived (Phase 6)."


def lease_files_become_documents(apps, schema_editor):
    Lease = apps.get_model("leases", "Lease")
    Document = apps.get_model("documents", "Document")

    leases = (
        Lease.objects.exclude(lease_file="")
        .exclude(lease_file__isnull=True)
        .select_related("unit")
        .iterator()
    )
    for lease in leases:
        stored_path = lease.lease_file.name
        display_name = (lease.lease_document_name or "").strip()
        if Document.objects.filter(
            lease_id=lease.pk, original_name=display_name, category="LEASE"
        ).exists():
            continue
        Document.objects.create(
            title=(display_name or "Signed lease")[:200],
            category="LEASE",
            file=stored_path,
            original_name=display_name,
            lease_id=lease.pk,
            property_id=lease.unit.property_id,
            tenant_visible=True,
            note=MIGRATION_NOTE,
        )


def documents_become_lease_files(apps, schema_editor):
    """Reverse: drop the rows this migration made, and nothing else.

    The lease's own field is still there at this point, so the file is not lost by
    going back — which is the only reason this is a safe thing to do.
    """
    Document = apps.get_model("documents", "Document")
    Document.objects.filter(note=MIGRATION_NOTE, category="LEASE").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0001_initial"),
        ("leases", "0009_lease_lease_document_name_alter_lease_lease_file"),
    ]

    operations = [
        migrations.RunPython(lease_files_become_documents, documents_become_lease_files),
    ]

"""Every lease's single file becomes a document row, and comes back on a rollback.

The only honest way to test a data migration: put the schema back where it was, write
rows in the old shape with raw model access, migrate forward, and check what the data
became. The file is not moved — the row points at the same storage path — and the row
is tenant-visible, because tenants could already open their lease and a migration must
not take something away (ADR-022).
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("restore_schema")]

#: The state just before the documents app reads Lease.lease_file: the column exists
#: on leases/0009 and the Document model exists at documents/0001.
BEFORE = [
    ("leases", "0009_lease_lease_document_name_alter_lease_lease_file"),
    ("documents", "0001_initial"),
]
AFTER = ("documents", "0002_lease_files_become_documents")
#: The end of the chain, so a test never leaves the schema in a half-migrated state.
LATEST = ("leases", "0010_remove_lease_lease_document_name_and_more")

NOTE = "Brought in from the lease's single file when documents arrived (Phase 6)."


def migrate(target):
    """Move the schema to ``target`` and return the historical app registry."""
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    targets = target if isinstance(target, list) else [target]
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


def a_lease_with_a_file(apps, *, name: str, document_name: str = "", stored: str):
    """A lease in the old shape: one file on the model, and a display name for it."""
    Property = apps.get_model("properties", "Property")
    Unit = apps.get_model("properties", "Unit")
    Lease = apps.get_model("leases", "Lease")

    property_ = Property.objects.create(
        name=f"Migration property {stored}",
        property_type="RESIDENTIAL",
        street="1 Migration Way",
        city="Portland",
        state="OR",
        postal_code="97201",
    )
    unit = Unit.objects.create(property=property_, identifier="1")
    lease = Lease.objects.create(
        unit=unit,
        start_date=dt.date(2025, 1, 1),
        end_date=dt.date(2025, 12, 31),
        monthly_rent=Decimal("1000.00"),
        deposit=Decimal("1000.00"),
        status="ACTIVE",
        lease_file=stored,
        lease_document_name=document_name,
    )
    return property_, lease


def test_a_lease_file_becomes_a_tenant_visible_document_row(settings):
    old = migrate(BEFORE)
    property_, lease = a_lease_with_a_file(
        old,
        name="signed-lease.pdf",
        document_name="Michael Ortolano Lease (Nov 2024).pdf",
        stored="lease_documents/abc123.pdf",
    )
    # The bytes are where the stored path says; the migration must not move them.
    settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    (settings.MEDIA_ROOT / "lease_documents").mkdir(exist_ok=True)
    (settings.MEDIA_ROOT / "lease_documents" / "abc123.pdf").write_bytes(b"%PDF-1.4 lease")

    try:
        new = migrate(AFTER)
        Document = new.get_model("documents", "Document")

        document = Document.objects.get(lease_id=lease.pk)
        assert document.file.name == "lease_documents/abc123.pdf"
        assert document.title == "Michael Ortolano Lease (Nov 2024).pdf"
        assert document.original_name == "Michael Ortolano Lease (Nov 2024).pdf"
        assert document.category == "LEASE"
        assert document.tenant_visible is True
        assert document.lease_id == lease.pk
        assert document.property_id == property_.pk
        assert document.note == NOTE
        assert (settings.MEDIA_ROOT / document.file.name).exists()
    finally:
        migrate(LATEST)


def test_a_lease_file_without_a_name_reads_as_the_signed_lease():
    old = migrate(BEFORE)
    _, lease = a_lease_with_a_file(old, name="scan.pdf", stored="lease_documents/def456.pdf")

    try:
        new = migrate(AFTER)
        Document = new.get_model("documents", "Document")

        document = Document.objects.get(lease_id=lease.pk)
        assert document.title == "Signed lease"
        assert document.original_name == ""
        assert document.file.name == "lease_documents/def456.pdf"
    finally:
        migrate(LATEST)


def test_reversing_removes_the_migrated_rows_and_gives_the_field_back():
    """The lease's own field is still there going back, so nothing is lost."""
    old = migrate(BEFORE)
    _, lease = a_lease_with_a_file(
        old, name="scan.pdf", document_name="Scan.pdf", stored="lease_documents/ghi789.pdf"
    )

    try:
        new = migrate(AFTER)
        Document = new.get_model("documents", "Document")
        assert Document.objects.filter(lease_id=lease.pk).count() == 1

        restore = migrate(BEFORE)
        ReversedLease = restore.get_model("leases", "Lease")

        reversed_lease = ReversedLease.objects.get(pk=lease.pk)
        assert reversed_lease.lease_file.name == "lease_documents/ghi789.pdf"
        assert reversed_lease.lease_document_name == "Scan.pdf"
        assert not Document.objects.exists(), "only the rows the migration made are removed"
    finally:
        migrate(LATEST)


def test_only_the_rows_this_migration_made_are_removed_on_the_way_back():
    """A document filed by hand is not collateral of a rollback."""
    old = migrate(BEFORE)
    _, lease = a_lease_with_a_file(old, name="scan.pdf", stored="lease_documents/jkl012.pdf")
    new = migrate(AFTER)
    Document = new.get_model("documents", "Document")
    Document.objects.create(
        title="Boiler certificate",
        category="OTHER",
        file="documents/boiler.pdf",
        original_name="boiler.pdf",
        lease_id=lease.pk,
        property_id=Document.objects.get(lease_id=lease.pk).property_id,
        note="Filed by hand.",
    )

    try:
        restore = migrate(BEFORE)
        # The hand-filed document's row survives the reverse; the migrated one does not.
        assert Document.objects.filter(title="Boiler certificate").exists()
        assert not Document.objects.filter(note=NOTE).exists()
        assert restore.get_model("leases", "Lease").objects.get(pk=lease.pk).lease_file
    finally:
        migrate(LATEST)


def test_the_migration_runs_twice_without_filing_the_same_file_twice():
    """Re-running it (a replayed deploy) must not duplicate the lease's document."""
    old = migrate(BEFORE)
    _, lease = a_lease_with_a_file(
        old, name="scan.pdf", document_name="Scan.pdf", stored="lease_documents/mno345.pdf"
    )

    try:
        migrate(AFTER)
        migrate(BEFORE)
        # The lease is back in its old shape; migrate forward again over the same row.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([("documents", "0002_lease_files_become_documents")])
        Document = executor.loader.project_state(
            [("documents", "0002_lease_files_become_documents")]
        ).apps.get_model("documents", "Document")

        assert Document.objects.filter(lease_id=lease.pk, category="LEASE").count() == 1
    finally:
        migrate(LATEST)


def test_a_document_the_migration_made_is_the_one_the_tenant_can_open():
    """Forward is not only a row: it is a row the tenant scope actually returns."""
    from apps.accounts.models import User
    from apps.documents.models import Document as LiveDocument

    old = migrate(BEFORE)
    _, lease = a_lease_with_a_file(old, name="scan.pdf", stored="lease_documents/pqr678.pdf")
    ada = User.objects.create_user(username="ada", password="pw", role="TENANT")
    old.get_model("leases", "LeaseTenant").objects.create(
        lease_id=lease.pk, tenant_id=ada.pk, is_primary=True
    )

    try:
        migrate(AFTER)
        document = LiveDocument.objects.get(lease_id=lease.pk)
        assert document.is_visible_to(ada)
        assert LiveDocument.objects.visible_to(ada).filter(pk=document.pk).exists()
    finally:
        migrate(LATEST)

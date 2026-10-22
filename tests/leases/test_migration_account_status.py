"""Legacy settled tenancies reopen for review under the split lifecycle."""

import datetime as dt
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.audit.models import AuditEvent

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("restore_schema")]

BEFORE = ("leases", "0005_lease_end_reason_lease_end_reason_note_and_more")
AFTER = ("leases", "0006_lease_account_status_lease_settled_at_and_more")


#: The head of the chain; computed from the graph so a test's restore step follows it.
def latest():
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    return executor.loader.graph.leaf_nodes()


DOCUMENTS = ("documents", "0002_lease_files_become_documents")
PROPERTIES = ("properties", "0004_property_cam_rate_per_sqft")


def migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    targets = target if isinstance(target, list) else [target, PROPERTIES]
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


def test_legacy_settlement_becomes_ended_open_with_a_system_audit_event():
    old = migrate(BEFORE)
    Property = old.get_model("properties", "Property")
    Unit = old.get_model("properties", "Unit")
    Lease = old.get_model("leases", "Lease")
    property_ = Property.objects.create(
        name="Lifecycle migration property",
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
        status="SETTLED",
    )

    try:
        new = migrate(AFTER)
        NewLease = new.get_model("leases", "Lease")
        AuditEvent = new.get_model("audit", "AuditEvent")
        migrated = NewLease.objects.get(pk=lease.pk)

        assert migrated.status == "ENDED"
        assert migrated.account_status == "OPEN"
        event = AuditEvent.objects.get(lease_id=lease.pk, action="LEASE_REOPENED")
        assert event.actor_id is None
        assert "security-deposit disposition" in event.metadata["reason"]
    finally:
        migrate(latest())


def test_the_migration_can_be_reversed_without_losing_the_audit_events():
    """The note claims a rollback preserves the append-only audit trail. Prove it."""
    old = migrate(BEFORE)
    Property = old.get_model("properties", "Property")
    Unit = old.get_model("properties", "Unit")
    Lease = old.get_model("leases", "Lease")
    property_ = Property.objects.create(
        name="Reversal migration property",
        property_type="RESIDENTIAL",
        street="2 Migration Way",
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
        status="SETTLED",
    )

    try:
        migrate(AFTER)
        migrate(BEFORE)

        reversed_lease = old.get_model("leases", "Lease").objects.get(pk=lease.pk)
        assert reversed_lease.status == "SETTLED", "the old status is restored"
        assert AuditEvent.objects.filter(lease_id=lease.pk, action="LEASE_REOPENED").exists(), (
            "the record of the migration survives the rollback: audit rows are append-only"
        )
    finally:
        migrate(latest())

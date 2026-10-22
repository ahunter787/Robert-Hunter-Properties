"""A tenancy that has not started is upcoming: scheduled, not billed (ADR-029 D1).

The case these tests exist for: a renewal is signed months before it begins, while the current
tenancy is still running. RHP had one `ACTIVE` bucket, so the renewal either could not be stored
(one active lease per unit) or was stored as active before its term — and every screen then had
to guess which kind of "active" it was. `FUTURE` is that missing state.
"""

import datetime as dt
import importlib
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.audit.models import AuditAction, AuditEvent
from apps.leases import services as lease_services
from apps.leases.models import Lease, LeaseStatus
from apps.ledger import deposits
from apps.ledger import services as ledger_services
from tests.factories import make_admin, make_lease, make_manager, make_payment, make_tenant

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
START = TODAY + dt.timedelta(days=45)
END = START + dt.timedelta(days=365)


def future_lease(**fields):
    tenant = fields.pop("tenant", None)
    fields.setdefault("start_date", START)
    fields.setdefault("end_date", END)
    fields.setdefault("status", LeaseStatus.FUTURE)
    fields.setdefault("billing_start_date", None)
    return make_lease(tenants=[tenant] if tenant else (), **fields)


def signed_in(user):
    from django.test import Client

    client = Client()
    client.force_login(user)
    return client


# --- scheduling -----------------------------------------------------------


def test_activating_a_future_draft_schedules_it_and_posts_nothing():
    tenant = make_tenant(username="upcoming-tenant")
    lease = make_lease(
        tenants=[tenant],
        status=LeaseStatus.DRAFT,
        start_date=START,
        end_date=END,
        template="STEP_UP",
        step_up_month=START.month,
        step_up_percent=Decimal("4.00"),
        monthly_rent=Decimal("1000.00"),
    )

    response = signed_in(make_manager()).post(
        reverse("leases:lease-activate", args=[lease.pk]), follow=True
    )

    lease.refresh_from_db()
    assert response.status_code == 200
    assert lease.status == LeaseStatus.FUTURE
    assert "scheduled to start" in response.content.decode()
    assert lease.rent_periods.exists(), "the future amounts are worked out now"
    assert not lease.charges.exists(), "an upcoming tenancy takes no obligation"
    assert AuditEvent.objects.filter(action=AuditAction.LEASE_SCHEDULED, lease=lease).exists()
    assert not AuditEvent.objects.filter(action=AuditAction.LEASE_ACTIVATED, lease=lease).exists()


def test_a_future_tenancy_is_neither_occupancy_nor_a_charge():
    lease = future_lease()

    assert lease.is_future and not lease.is_current
    assert not Lease.objects.current().filter(pk=lease.pk).exists()
    assert lease.unit.current_lease is None
    with pytest.raises(Exception, match="has not started"):
        ledger_services.create_charge(
            lease, description="Key", amount=Decimal("25.00"), due_date=TODAY
        )


def test_a_renewal_can_be_signed_while_the_current_tenancy_runs():
    """The unique active-lease rule is untouched; the missing state is what allows this."""
    unit = make_lease().unit
    renewal = make_lease(
        unit,
        tenants=[make_tenant(username="renewal-tenant")],
        status=LeaseStatus.DRAFT,
        start_date=unit.leases.first().end_date + dt.timedelta(days=1),
        end_date=unit.leases.first().end_date + dt.timedelta(days=366),
    )

    response = signed_in(make_manager()).post(reverse("leases:lease-activate", args=[renewal.pk]))

    renewal.refresh_from_db()
    assert response.status_code == 302
    assert renewal.status == LeaseStatus.FUTURE
    assert unit.leases.filter(status=LeaseStatus.ACTIVE).count() == 1, "the current one"


def test_a_scheduled_tenancy_starts_on_its_day():
    start = TODAY.replace(day=1)
    lease = future_lease(start_date=start, end_date=start + dt.timedelta(days=365))

    started = lease_services.activate_due_leases()

    lease.refresh_from_db()
    assert lease.status == LeaseStatus.ACTIVE
    assert len(started) == 1
    assert lease.charges.exists(), "rent due on the start day is posted"
    event = AuditEvent.objects.get(action=AuditAction.LEASE_ACTIVATED, lease=lease)
    assert event.metadata["automatic"] is True
    assert lease_services.activate_due_leases() == [], "idempotent"


def test_the_screens_start_a_due_tenancy():
    lease = future_lease(tenant=make_tenant(username="starts-today"), start_date=TODAY)

    signed_in(make_manager()).get(reverse("leases:lease-list"))

    lease.refresh_from_db()
    assert lease.status == LeaseStatus.ACTIVE


def test_the_management_command_starts_due_tenancies(capsys):
    lease = future_lease(start_date=TODAY)

    from django.core.management import call_command

    call_command("activate_leases")

    lease.refresh_from_db()
    assert lease.status == LeaseStatus.ACTIVE
    assert "Started tenancy" in capsys.readouterr().out


# --- the tenant sees an upcoming lease, not a bill ------------------------


def test_the_tenant_sees_the_upcoming_lease_without_money():
    tenant = make_tenant(username="upcoming-viewer")
    future_lease(tenant=tenant)
    client = signed_in(tenant)

    lease_body = strip_tags(client.get(reverse("tenancy:lease")).content.decode())
    payments_body = strip_tags(client.get(reverse("payments:home")).content.decode())

    assert "This tenancy begins" in lease_body
    assert "Nothing is due yet" in payments_body
    assert "Due now$0.00" in payments_body, "the summary is present and shows nothing owed"
    assert "0 statement entries" in payments_body


def test_the_tenant_dashboard_says_nothing_is_due_before_the_start():
    tenant = make_tenant(username="upcoming-dashboard")
    future_lease(tenant=tenant)

    body = strip_tags(signed_in(tenant).get(reverse("accounts:home")).content.decode())

    assert "Your tenancy begins" in body
    assert "Nothing is due before then" in body


# --- pre-move-in money and the reserved unit -------------------------------


def test_a_deposit_can_be_received_before_the_term_starts():
    lease = future_lease()

    entry = deposits.record(
        lease,
        kind="RECEIVED",
        amount=Decimal("500.00"),
        date=TODAY,
        method="CHECK",
        actor=make_manager(),
    )

    assert entry.pk
    assert deposits.held(lease) == Decimal("500.00")


def test_an_upcoming_lease_with_money_attached_is_kept():
    lease = future_lease()
    deposits.record(lease, kind="RECEIVED", amount=Decimal("500.00"), date=TODAY)
    client = signed_in(make_admin())

    response = client.post(reverse("leases:lease-delete", args=[lease.pk]), follow=True)

    assert response.status_code == 200
    assert Lease.objects.filter(pk=lease.pk).exists()
    assert b"kept as history" in response.content
    assert deposits.held(lease) == Decimal("500.00")


def test_an_upcoming_lease_with_nothing_attached_can_be_deleted():
    lease = future_lease()
    client = signed_in(make_admin())

    response = client.post(reverse("leases:lease-delete", args=[lease.pk]))

    assert response.status_code == 302
    assert not Lease.objects.filter(pk=lease.pk).exists()


# --- the stored state follows the date ------------------------------------


def test_the_migration_flips_a_future_dated_active_lease():
    """The data step of leases/0013: an active label on a term that has not begun is corrected."""
    migration = importlib.import_module("apps.leases.migrations.0013_future_lease_state")
    future = make_lease(start_date=START, end_date=END, status=LeaseStatus.ACTIVE)
    running = make_lease()

    migration.schedule_future_leases(
        django_apps, SimpleNamespace(connection=SimpleNamespace(alias="default"))
    )

    future.refresh_from_db()
    running.refresh_from_db()
    assert future.status == LeaseStatus.FUTURE
    assert running.status == LeaseStatus.ACTIVE
    # Clean up so the rest of the module (shared database) is not surprised.
    future.status = LeaseStatus.ACTIVE
    future.save(update_fields=["status"])


def test_an_upcoming_lease_is_editable_and_hides_the_money_actions():
    lease = future_lease()
    body = strip_tags(
        signed_in(make_manager())
        .get(reverse("ledger:lease-ledger", args=[lease.pk]))
        .content.decode()
    )

    assert "This tenancy has not started" in body
    assert "Post due charges" not in body
    assert "Record payment" not in body
    assert "Edit" in body and "End this tenancy" not in body


def test_the_unit_and_property_screens_point_at_the_upcoming_tenancy():
    lease = future_lease(tenant=make_tenant(username="scheduled-on-page"))
    manager = signed_in(make_manager())

    unit_body = strip_tags(
        manager.get(reverse("portfolio:unit-detail", args=[lease.unit_id])).content.decode()
    )
    property_body = strip_tags(
        manager.get(
            reverse("portfolio:property-detail", args=[lease.unit.property_id])
        ).content.decode()
    )

    assert "scheduled to start" in unit_body
    assert "Open the upcoming lease" in unit_body
    assert "Upcoming" in property_body


def test_a_scheduled_tenancy_never_consumes_a_payment():
    """Money cannot settle a charge that does not exist yet; the kernel rule holds in the UI."""
    lease = future_lease(tenant=make_tenant(username="payer"))
    assert not lease.charges.exists()
    assert make_payment(lease, amount=Decimal("100.00")).pk
    assert lease.payments.count() == 1, "held credit is a payment fact, not a settled charge"

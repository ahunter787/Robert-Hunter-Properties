"""E16: authorized tenant timeline and manual activity."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.ledger.models import ChargeKind
from apps.ledger.services import create_charge
from apps.timeline.models import TimelineEntry
from tests.factories import make_lease, make_manager, make_tenant
from tests.test_communications import start

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def safe_settings(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def world():
    manager = make_manager(username="timeline-manager")
    tenant = make_tenant(username="timeline-tenant")
    lease = make_lease(tenants=[tenant])
    create_charge(
        lease,
        description="Rent",
        amount=Decimal("100.00"),
        due_date=timezone.localdate(),
        kind=ChargeKind.RENT,
    )
    from apps.maintenance.models import MaintenanceRequest

    MaintenanceRequest.objects.create(
        property=lease.unit.property,
        unit=lease.unit,
        reporting_lease=lease,
        reporter=manager,
        title="Leaky tap",
        description="Synthetic",
        category="plumbing",
    )
    start(manager, lease, tenant=tenant, body="Welcome")
    return manager, tenant, lease


def test_a_tenant_sees_their_authorized_timeline(client, world):
    manager, tenant, lease = world
    TimelineEntry.objects.create(
        lease=lease,
        kind="NOTE",
        body="Shared note",
        occurred_at=timezone.now(),
        author=manager,
        visible_to_tenant=True,
    )
    TimelineEntry.objects.create(
        lease=lease,
        kind="NOTE",
        body="Internal note",
        occurred_at=timezone.now(),
        author=manager,
        visible_to_tenant=False,
    )
    client.force_login(tenant)
    response = client.get(reverse("tenant_timeline:timeline"))
    assert response.status_code == 200
    assert b"Rent charged" in response.content
    assert b"Leaky tap" in response.content
    assert b"Shared note" in response.content
    assert b"Internal note" not in response.content


def test_another_tenant_does_not_see_the_timeline(client):
    tenant = make_tenant(username="timeline-tenant-2")
    other = make_tenant(username="timeline-other")
    lease = make_lease(tenants=[tenant])
    create_charge(
        lease,
        description="Rent",
        amount=Decimal("100.00"),
        due_date=timezone.localdate(),
        kind=ChargeKind.RENT,
    )
    client.force_login(other)
    response = client.get(reverse("tenant_timeline:timeline"))
    assert response.status_code == 200
    assert b"Rent charged" not in response.content


def test_staff_can_read_and_add_manual_activity(client, world):
    manager, _, lease = world
    client.force_login(manager)
    assert client.get(reverse("timeline:list")).status_code == 200
    detail = client.get(reverse("timeline:lease", args=[lease.pk]))
    assert detail.status_code == 200
    assert b"Internal note" not in detail.content  # no entry yet

    response = client.post(
        reverse("timeline:lease", args=[lease.pk]),
        {
            "kind": "NOTE",
            "body": "Called the tenant about the leak.",
            "occurred_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "visible_to_tenant": "on",
        },
    )
    assert response.status_code == 302
    entry = TimelineEntry.objects.get()
    assert entry.visible_to_tenant is True
    assert entry.author == manager


def test_manual_activity_can_be_internal(client, world):
    manager, tenant, lease = world
    client.force_login(manager)
    client.post(
        reverse("timeline:lease", args=[lease.pk]),
        {
            "kind": "NOTE",
            "body": "Internal only",
            "occurred_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
        },
    )
    client.force_login(tenant)
    response = client.get(reverse("tenant_timeline:timeline"))
    assert b"Internal only" not in response.content


def test_tenant_cannot_reach_staff_timeline(client, world):
    _, tenant, lease = world
    client.force_login(tenant)
    assert client.get(reverse("timeline:list")).status_code == 403
    assert client.get(reverse("timeline:lease", args=[lease.pk])).status_code == 403

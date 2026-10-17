"""The tenant's own lease area — the first page a tenant sees with real data."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.leases.models import LeaseStatus
from tests.documents.helpers import make_document
from tests.factories import make_lease, make_tenant, make_unit

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def test_a_tenant_sees_their_current_lease(client):
    tenant = make_tenant(username="ada", first_name="Ada", last_name="One")
    make_lease(make_unit(identifier="Storefront"), tenants=[tenant])
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "Storefront" in body
    assert "Lease term" in body
    assert "$1,850.00" in body
    assert "1st of every month" in body
    assert "Ada One" in body


def test_the_tenant_page_shows_the_other_people_on_the_lease(client):
    ada = make_tenant(username="ada", first_name="Ada")
    ben = make_tenant(username="ben", first_name="Ben")
    make_lease(make_unit(), tenants=[ada, ben])
    client.force_login(ada)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "Ada" in body
    assert "Ben" in body
    assert "Primary contact" in body


def test_a_tenant_without_a_lease_sees_an_empty_state(client):
    client.force_login(make_tenant(username="new-tenant"))

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "No lease yet" in body
    assert "contact Robert Hunter Properties" in body


def test_an_ended_lease_is_still_shown_to_the_tenant(client):
    tenant = make_tenant(username="former")
    make_lease(
        make_unit(),
        tenants=[tenant],
        status=LeaseStatus.ENDED,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY - dt.timedelta(days=40),
    )
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "This tenancy ended on" in body


def test_a_tenant_only_ever_sees_their_own_lease(client):
    mine = make_tenant(username="mine", first_name="Mine")
    theirs = make_tenant(username="theirs", first_name="Theirs")
    make_lease(make_unit(identifier="MyUnit"), tenants=[mine])
    make_lease(make_unit(identifier="TheirUnit"), tenants=[theirs])
    client.force_login(mine)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "MyUnit" in body
    assert "TheirUnit" not in body
    assert "Theirs" not in body


def test_the_lease_page_offers_the_tenants_documents(client):
    """The lease itself is a document now, and the door to them is on this page."""
    tenant = make_tenant(username="ada")
    lease = make_lease(make_unit(), tenants=[tenant])
    make_document(title="Signed lease", lease=lease, tenant_visible=True)
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert reverse("tenant_documents:list") in body
    assert "Your documents" in body


def test_the_tenant_navigation_offers_the_lease_page(client):
    client.force_login(make_tenant(username="ada"))

    body = client.get(reverse("accounts:profile")).content.decode()

    assert reverse("tenancy:lease") in body


def test_staff_navigation_offers_the_lease_desk(client):
    from tests.factories import make_manager

    client.force_login(make_manager(username="lease-manager"))

    body = client.get(reverse("manage:home")).content.decode()

    assert reverse("leases:lease-list") in body

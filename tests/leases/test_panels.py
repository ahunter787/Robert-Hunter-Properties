"""What Phase 3 fills in: the panels and counters Phase 2 left labelled."""

import pytest
from django.urls import reverse

from apps.leases.models import LeaseStatus
from tests.factories import make_lease, make_manager, make_property, make_tenant, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client):
    client.force_login(make_manager(username="panels-manager"))
    return client


def test_an_occupied_unit_shows_its_tenancy(signed_in):
    unit = make_unit(identifier="Storefront")
    tenant = make_tenant(username="ada", first_name="Ada", last_name="One")
    make_lease(unit, tenants=[tenant])

    body = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()

    assert "Occupied" in body
    assert "Ada One" in body
    assert "$1,850.00" in body
    assert "1st of every month" in body
    assert "Open the lease" in body


def test_a_vacant_unit_offers_to_start_a_lease(signed_in):
    unit = make_unit()

    body = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()

    assert "Vacant" in body
    assert "Nobody is on a lease here right now" in body
    assert f"{reverse('leases:lease-create')}?unit={unit.pk}" in body


def test_a_unit_whose_lease_was_a_draft_is_still_vacant(signed_in):
    unit = make_unit()
    make_lease(unit, status=LeaseStatus.DRAFT)

    body = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()

    assert "Vacant" in body


def test_a_property_lists_its_occupants(signed_in):
    property_ = make_property(name="Maple Street Duplex")
    make_unit(property_, identifier="Storefront")
    tenant = make_tenant(username="ada", first_name="Ada", last_name="One")
    make_lease(property_.units.first(), tenants=[tenant])

    body = signed_in.get(reverse("portfolio:property-detail", args=[property_.pk])).content.decode()

    assert "Occupants and active leases" in body
    assert "Ada One" in body
    assert "Open lease" in body


def test_a_property_with_no_leases_says_so(signed_in):
    property_ = make_property()
    make_unit(property_, identifier="A")

    body = signed_in.get(reverse("portfolio:property-detail", args=[property_.pk])).content.decode()

    assert "No active leases at this property" in body


def test_the_landing_page_counts_leases_and_occupancy(signed_in):
    occupied = make_unit(identifier="Occupied")
    make_unit(identifier="Vacant")
    make_lease(occupied, tenants=[make_tenant(username="ada")])

    response = signed_in.get(reverse("manage:home"))
    context = response.context

    assert context["unit_active_count"] == 2
    assert context["unit_occupied_count"] == 1
    assert context["unit_vacant_count"] == 1
    assert context["lease_active_count"] == 1
    assert context["lease_draft_count"] == 0
    assert "occupied" in response.content.decode()


def test_the_landing_page_counts_drafts_and_expiring_leases(signed_in):
    import datetime as dt

    from django.utils import timezone

    today = timezone.localdate()
    make_lease(make_unit(identifier="Draft"), status=LeaseStatus.DRAFT)
    make_lease(make_unit(identifier="Soon"), end_date=today + dt.timedelta(days=5))
    make_lease(make_unit(identifier="Later"), end_date=today + dt.timedelta(days=300))

    context = signed_in.get(reverse("manage:home")).context

    assert context["lease_active_count"] == 2
    assert context["lease_draft_count"] == 1
    assert context["lease_expiring_count"] == 1


def test_a_property_panel_does_not_leak_another_propertys_tenants(signed_in):
    mine = make_property(name="Mine")
    theirs = make_property(name="Theirs")
    make_lease(
        make_unit(mine, identifier="A"), tenants=[make_tenant(username="mine", first_name="Mine")]
    )
    make_lease(
        make_unit(theirs, identifier="B"),
        tenants=[make_tenant(username="theirs", first_name="Theirs")],
    )

    body = signed_in.get(reverse("portfolio:property-detail", args=[mine.pk])).content.decode()

    assert "Mine" in body
    assert "Theirs" not in body

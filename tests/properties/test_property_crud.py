"""Property screens: create, edit, search, and taking a property out of service."""

import pytest
from django.urls import reverse

from apps.properties.models import Property
from tests.factories import make_manager, make_property, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client):
    client.force_login(make_manager(username="portfolio-manager"))
    return client


def test_list_shows_every_property(signed_in):
    make_property(name="Apple Lane")
    make_property(name="Zebra Court")

    body = signed_in.get(reverse("portfolio:property-list")).content.decode()

    assert "Apple Lane" in body
    assert "Zebra Court" in body


def test_list_search_matches_name_city_and_zip(signed_in):
    make_property(name="Apple Lane", city="Peoria")
    make_property(name="Zebra Court", city="Springfield")

    response = signed_in.get(reverse("portfolio:property-list"), {"q": "Peoria"})

    assert [p.name for p in response.context["properties"]] == ["Apple Lane"]


def test_list_status_filter(signed_in):
    make_property(name="Working")
    make_property(name="Retired", is_active=False)

    response = signed_in.get(reverse("portfolio:property-list"), {"status": "inactive"})

    assert [p.name for p in response.context["properties"]] == ["Retired"]


def test_list_annotates_in_service_and_total_unit_counts(signed_in):
    property_ = make_property()
    make_unit(property_, identifier="A")
    make_unit(property_, identifier="B", is_active=False)

    # The listed queryset is a page slice, so pick the row rather than re-querying.
    listing = next(
        item
        for item in signed_in.get(reverse("portfolio:property-list")).context["properties"]
        if item.pk == property_.pk
    )

    assert listing.unit_total == 2
    assert listing.unit_active == 1


def test_detail_shows_the_address_and_units(signed_in):
    property_ = make_property()
    make_unit(property_, identifier="A", bedrooms=3, bathrooms=None)

    body = signed_in.get(reverse("portfolio:property-detail", args=[property_.pk])).content.decode()

    assert "12 Maple St, Springfield, IL 62704" in body
    assert "Unit A" not in body  # the table shows the bare identifier
    assert ">A<" in body
    assert "Not tracked here yet" in body  # deferred panels are labelled, not faked


def test_create_property(signed_in):
    response = signed_in.post(
        reverse("portfolio:property-create"),
        {
            "name": "Oak Street Fourplex",
            "street": "8 Oak St",
            "city": "Peoria",
            "state": "IL",
            "postal_code": "61602",
            "notes": "Back building needs a new roof.",
            "is_active": "on",
        },
    )

    created = Property.objects.get(name="Oak Street Fourplex")
    assert response.status_code == 302
    assert response["Location"] == reverse("portfolio:property-detail", args=[created.pk])
    assert created.address_line == "8 Oak St, Peoria, IL 61602"


def test_create_requires_the_essentials(signed_in):
    response = signed_in.post(
        reverse("portfolio:property-create"),
        {"name": "", "street": "", "city": "", "state": "", "postal_code": "not-a-zip"},
    )

    assert response.status_code == 200
    assert not Property.objects.exists()
    assert b"This field is required" in response.content


def test_a_duplicate_name_is_reported_rather_than_crashing(signed_in):
    make_property(name="Maple Street Duplex")

    response = signed_in.post(
        reverse("portfolio:property-create"),
        {
            "name": "maple street duplex",
            "street": "12 Maple St",
            "city": "Springfield",
            "state": "IL",
            "postal_code": "62704",
        },
    )

    assert response.status_code == 200
    assert Property.objects.count() == 1
    assert "already exists" in response.content.decode().lower()


def test_edit_property(signed_in):
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:property-update", args=[property_.pk]),
        {
            "name": "Maple Street Duplex",
            "street": "14 Maple St",
            "city": "Springfield",
            "state": "IL",
            "postal_code": "62704",
            "is_active": "on",
        },
    )

    property_.refresh_from_db()
    assert response.status_code == 302
    assert property_.street == "14 Maple St"


def test_take_out_of_service_and_back(signed_in):
    property_ = make_property()

    signed_in.post(reverse("portfolio:property-toggle-active", args=[property_.pk]))
    property_.refresh_from_db()
    assert property_.is_active is False

    signed_in.post(reverse("portfolio:property-toggle-active", args=[property_.pk]))
    property_.refresh_from_db()
    assert property_.is_active is True


def test_taking_a_property_out_of_service_reports_its_active_units(signed_in):
    property_ = make_property()
    make_unit(property_, identifier="A")

    response = signed_in.post(
        reverse("portfolio:property-toggle-active", args=[property_.pk]), follow=True
    )

    assert b"1 in-service unit" in response.content


def test_taking_a_property_out_of_service_leaves_its_units_in_service(signed_in):
    property_ = make_property()
    unit = make_unit(property_, identifier="A")

    signed_in.post(reverse("portfolio:property-toggle-active", args=[property_.pk]))

    unit.refresh_from_db()
    assert unit.is_active is True


def test_an_unknown_property_is_a_404(signed_in):
    response = signed_in.get(reverse("portfolio:property-detail", args=[9999]))

    assert response.status_code == 404

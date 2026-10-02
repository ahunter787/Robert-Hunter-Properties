"""Unit size, amenities, and the unit list grouped by property."""

import pytest
from django.urls import reverse

from apps.properties.models import Unit
from tests.factories import make_amenity, make_manager, make_property, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client):
    client.force_login(make_manager(username="unit-manager"))
    return client


def unit_payload(property_, **overrides):
    payload = {
        "property": property_.pk,
        "identifier": "1",
        "is_active": "on",
    }
    payload.update(overrides)
    return payload


# --- square feet ----------------------------------------------------------


def test_square_feet_is_saved(signed_in):
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:unit-create"), unit_payload(property_, square_feet=850)
    )

    assert response.status_code == 302
    assert Unit.objects.get(identifier="1").square_feet == 850


def test_square_feet_is_optional(signed_in):
    property_ = make_property()

    response = signed_in.post(reverse("portfolio:unit-create"), unit_payload(property_))

    assert response.status_code == 302
    assert Unit.objects.get(identifier="1").square_feet is None


def test_zero_square_feet_is_refused(signed_in):
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:unit-create"), unit_payload(property_, square_feet=0)
    )

    assert response.status_code == 200
    assert not Unit.objects.exists()


def test_square_feet_appears_on_the_unit_and_property_pages(signed_in):
    property_ = make_property()
    unit = make_unit(property_, identifier="Loft", square_feet=1200, bedrooms=None, bathrooms=None)

    unit_page = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()
    property_page = signed_in.get(
        reverse("portfolio:property-detail", args=[property_.pk])
    ).content.decode()

    assert "1,200" not in unit_page, "numbers render as stored, no thousands separator needed"
    assert "1200 sq ft" in unit_page
    assert "1200" in property_page
    assert "Total square feet" in property_page


def test_a_unit_without_a_size_says_so_rather_than_zero(signed_in):
    unit = make_unit(make_property(), identifier="Unknown", square_feet=None)

    body = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()

    assert "Not recorded" in body


# --- amenities ------------------------------------------------------------


def test_amenities_are_saved_on_a_unit(signed_in):
    property_ = make_property()
    parking = make_amenity("Parking")
    laundry = make_amenity("Laundry in unit")

    response = signed_in.post(
        reverse("portfolio:unit-create"),
        unit_payload(property_, amenities=[parking.pk, laundry.pk]),
    )

    assert response.status_code == 302
    unit = Unit.objects.get(identifier="1")
    assert set(unit.amenities.values_list("name", flat=True)) == {
        "Parking",
        "Laundry in unit",
    }


def test_a_unit_can_have_no_amenities(signed_in):
    property_ = make_property()

    response = signed_in.post(reverse("portfolio:unit-create"), unit_payload(property_))

    assert response.status_code == 302
    assert not Unit.objects.get(identifier="1").amenities.exists()


def test_the_unit_page_lists_the_amenities(signed_in):
    property_ = make_property()
    unit = make_unit(property_, identifier="Loft")
    unit.amenities.set([make_amenity("Parking"), make_amenity("Dishwasher")])

    body = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()

    assert "Amenities" in body
    assert "Parking" in body
    assert "Dishwasher" in body


def test_the_unit_page_says_when_there_are_none(signed_in):
    unit = make_unit(make_property(), identifier="Bare")

    body = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()

    assert "No amenities recorded" in body


def test_a_retired_amenity_leaves_the_picker_but_stays_on_the_unit(signed_in):
    property_ = make_property()
    retired = make_amenity("Coal chute", is_active=False)
    unit = make_unit(property_, identifier="Old")
    unit.amenities.set([retired])

    form_page = signed_in.get(reverse("portfolio:unit-update", args=[unit.pk])).content.decode()
    detail = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()

    assert form_page.count("Coal chute") >= 1, "the unit keeps it selectable while editing"
    assert "Coal chute" in detail

    # A *new* unit is not offered it.
    create_page = signed_in.get(
        reverse("portfolio:unit-create"), {"property": property_.pk}
    ).content.decode()
    assert "Coal chute" not in create_page


# --- the unit list, grouped by property -----------------------------------


def test_units_are_grouped_under_their_property(signed_in):
    first = make_property(name="Apple Lane")
    second = make_property(name="Zebra Court")
    make_unit(first, identifier="A1")
    make_unit(first, identifier="A2")
    make_unit(second, identifier="Z1")

    response = signed_in.get(reverse("portfolio:unit-list"))
    groups = response.context["properties"]

    assert [property_.name for property_ in groups] == ["Apple Lane", "Zebra Court"]
    assert [unit.identifier for unit in groups[0].listed_units] == ["A1", "A2"]
    assert [unit.identifier for unit in groups[1].listed_units] == ["Z1"]
    assert len(response.context["units"]) == 3, "the flat list still holds the page's units"


def test_the_group_header_carries_the_property_and_its_type(signed_in):
    property_ = make_property(name="Stark Street Shops", property_type="COMMERCIAL")
    make_unit(property_, identifier="Storefront")

    body = signed_in.get(reverse("portfolio:unit-list")).content.decode()

    assert "Stark Street Shops" in body
    assert "Commercial" in body, "the designation is stated once, by the building"


def test_the_type_column_is_replaced_by_square_footage(signed_in):
    property_ = make_property()
    make_unit(property_, identifier="Loft", square_feet=950, bedrooms=None, bathrooms=None)

    body = signed_in.get(reverse("portfolio:unit-list")).content.decode()

    assert "Square footage" in body
    assert "950 sq ft" in body
    assert "get_unit_type_display" not in body
    assert "Bedrooms" in body, "the rest of the row is unchanged"


def test_a_filter_drops_the_property_row_when_none_of_its_units_match(signed_in):
    first = make_property(name="Apple Lane")
    second = make_property(name="Zebra Court")
    make_unit(first, identifier="A1", bedrooms=None, bathrooms=None)
    make_unit(second, identifier="Z1", bedrooms=2, bathrooms="1.0")

    response = signed_in.get(reverse("portfolio:unit-list"), {"q": "Z1"})

    groups = response.context["properties"]
    assert [property_.name for property_ in groups] == ["Zebra Court"]
    assert [unit.identifier for unit in groups[0].listed_units] == ["Z1"]


def test_the_status_filter_scopes_the_units_inside_a_group(signed_in):
    property_ = make_property()
    make_unit(property_, identifier="Live")
    make_unit(property_, identifier="Retired", is_active=False)

    response = signed_in.get(reverse("portfolio:unit-list"), {"status": "inactive"})

    groups = response.context["properties"]
    assert [unit.identifier for unit in groups[0].listed_units] == ["Retired"]


def test_the_out_of_service_filter_hides_a_property_with_no_matching_units(signed_in):
    property_ = make_property()
    make_unit(property_, identifier="Live")

    response = signed_in.get(reverse("portfolio:unit-list"), {"status": "inactive"})

    assert list(response.context["properties"]) == []


def test_the_list_says_when_nothing_matches(signed_in):
    make_property()
    body = signed_in.get(reverse("portfolio:unit-list"), {"q": "nothing here"}).content.decode()

    assert "No units match that filter." in body


def test_pagination_pages_by_property_and_keeps_filters(signed_in):
    """A page holds properties, not units: 27 properties are two pages."""
    make_unit(make_property(name="Aardvark House"), identifier="Kept")
    for index in range(26):
        make_unit(make_property(name=f"Filler {index:02d}"), identifier="F")

    first_page = signed_in.get(reverse("portfolio:unit-list"))
    assert first_page.context["is_paginated"] is True
    assert len(first_page.context["properties"]) == 25
    assert first_page.context["properties"][0].name == "Aardvark House"
    assert len(first_page.context["units"]) == 25, "each group holds its own unit"

    second_page = signed_in.get(reverse("portfolio:unit-list"), {"page": 2})
    assert [property_.name for property_ in second_page.context["properties"]] == [
        "Filler 24",
        "Filler 25",
    ]

    # A filter travels with the page link rather than being dropped: 26 Fillers
    # match, so there are two pages and page 2's "Previous" link keeps the term.
    filtered = signed_in.get(reverse("portfolio:unit-list"), {"q": "Filler", "page": 2})
    body = filtered.content.decode()
    assert [property_.name for property_ in filtered.context["properties"]] == ["Filler 25"]
    assert "q=Filler" in body

    # And a filter that leaves one property needs no pagination at all.
    single = signed_in.get(reverse("portfolio:unit-list"), {"q": "Aardvark"})
    assert [property_.name for property_ in single.context["properties"]] == ["Aardvark House"]

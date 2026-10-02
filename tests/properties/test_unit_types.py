"""The Commercial/Residential designation, and the fields only one of them has.

The designation belongs to the **property** and its units inherit it, so what
used to be a unit rule is now a property rule (ADR-006, revision).
"""

import pytest
from django.urls import reverse

from apps.properties.constants import PropertyType
from apps.properties.models import Property, Unit
from tests.factories import make_manager, make_property, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client):
    client.force_login(make_manager(username="type-manager"))
    return client


# --- the designation lives on the property --------------------------------


def test_the_property_form_offers_both_types(signed_in):
    body = signed_in.get(reverse("portfolio:property-create")).content.decode()

    assert 'name="property_type"' in body
    assert "Commercial" in body
    assert "Residential" in body


def test_a_property_defaults_to_residential(signed_in):
    response = signed_in.get(reverse("portfolio:property-create"))

    assert response.context["form"]["property_type"].value() == PropertyType.RESIDENTIAL


def test_the_property_type_is_saved(signed_in):
    response = signed_in.post(
        reverse("portfolio:property-create"),
        {
            "name": "Stark Street Shops",
            "property_type": "COMMERCIAL",
            "street": "910 SE Stark St",
            "city": "Portland",
            "state": "OR",
            "postal_code": "97214",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    assert Property.objects.get(name="Stark Street Shops").property_type == "COMMERCIAL"


def test_the_property_type_is_required(signed_in):
    response = signed_in.post(
        reverse("portfolio:property-create"),
        {
            "name": "Nameless Type",
            "property_type": "",
            "street": "1 Main St",
            "city": "Portland",
            "state": "OR",
            "postal_code": "97214",
        },
    )

    assert response.status_code == 200
    assert not Property.objects.filter(name="Nameless Type").exists()


def test_the_unit_form_no_longer_offers_a_type(signed_in):
    property_ = make_property()

    body = signed_in.get(
        reverse("portfolio:unit-create"), {"property": property_.pk}
    ).content.decode()

    assert 'name="unit_type"' not in body
    assert 'name="square_feet"' in body
    assert 'name="amenities"' in body


def test_the_property_list_and_page_show_the_type(signed_in):
    property_ = make_property(name="Stark Street Shops", property_type=PropertyType.COMMERCIAL)

    listing = signed_in.get(reverse("portfolio:property-list")).content.decode()
    detail = signed_in.get(
        reverse("portfolio:property-detail", args=[property_.pk])
    ).content.decode()

    assert "Commercial" in listing
    assert "Commercial" in detail


# --- what a commercial property refuses -----------------------------------


def test_a_commercial_property_refuses_bedrooms_on_a_new_unit(signed_in):
    property_ = make_property(name="Shops", property_type=PropertyType.COMMERCIAL)

    response = signed_in.post(
        reverse("portfolio:unit-create"),
        {
            "property": property_.pk,
            "identifier": "Storefront",
            "bedrooms": 2,
            "bathrooms": "1.0",
            "is_active": "on",
        },
    )

    assert response.status_code == 200
    assert b"commercial property" in response.content
    assert not Unit.objects.filter(identifier="Storefront").exists()


def test_a_commercial_property_accepts_a_unit_without_residential_details(signed_in):
    property_ = make_property(name="Shops", property_type=PropertyType.COMMERCIAL)

    response = signed_in.post(
        reverse("portfolio:unit-create"),
        {
            "property": property_.pk,
            "identifier": "Storefront",
            "square_feet": 900,
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    unit = Unit.objects.get(identifier="Storefront")
    assert unit.is_commercial is True
    assert unit.square_feet == 900


def test_moving_a_unit_into_a_commercial_property_is_refused(signed_in):
    """The rule follows the *destination*, not the property the unit came from."""
    residential = make_property(name="Flats")
    commercial = make_property(name="Shops", property_type=PropertyType.COMMERCIAL)
    unit = make_unit(residential, identifier="Flat", bedrooms=2, bathrooms="1.0")

    response = signed_in.post(
        reverse("portfolio:unit-update", args=[unit.pk]),
        {
            "property": commercial.pk,
            "identifier": "Flat",
            "bedrooms": 2,
            "bathrooms": "1.0",
            "is_active": "on",
        },
    )

    unit.refresh_from_db()
    assert response.status_code == 200
    assert unit.property_id == residential.pk


def test_a_commercial_units_page_says_not_applicable(signed_in):
    property_ = make_property(name="Shops", property_type=PropertyType.COMMERCIAL)
    unit = make_unit(property_, identifier="Storefront")

    body = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()

    assert "Not applicable" in body
    assert "commercial property" in body


# --- switching a property that already has residential detail -------------


def test_a_property_with_bedrooms_cannot_become_commercial(signed_in):
    property_ = make_property(name="Flats")
    make_unit(property_, identifier="Flat", bedrooms=2, bathrooms="1.0")

    response = signed_in.post(
        reverse("portfolio:property-update", args=[property_.pk]),
        {
            "name": "Flats",
            "property_type": "COMMERCIAL",
            "street": "12 Maple St",
            "city": "Springfield",
            "state": "IL",
            "postal_code": "62704",
            "is_active": "on",
        },
    )

    property_.refresh_from_db()
    assert response.status_code == 200
    assert b"Flat" in response.content, "the refusal names the offending unit"
    assert property_.property_type == PropertyType.RESIDENTIAL


def test_a_property_without_residential_detail_can_become_commercial(signed_in):
    property_ = make_property(name="Empty Flats")
    make_unit(property_, identifier="Flat", bedrooms=None, bathrooms=None)

    response = signed_in.post(
        reverse("portfolio:property-update", args=[property_.pk]),
        {
            "name": "Empty Flats",
            "property_type": "COMMERCIAL",
            "street": "12 Maple St",
            "city": "Springfield",
            "state": "IL",
            "postal_code": "62704",
            "is_active": "on",
        },
    )

    property_.refresh_from_db()
    assert response.status_code == 302
    assert property_.property_type == PropertyType.COMMERCIAL


def test_a_commercial_property_can_become_residential_again(signed_in):
    property_ = make_property(name="Shops", property_type=PropertyType.COMMERCIAL)
    make_unit(property_, identifier="Storefront")

    response = signed_in.post(
        reverse("portfolio:property-update", args=[property_.pk]),
        {
            "name": "Shops",
            "property_type": "RESIDENTIAL",
            "street": "12 Maple St",
            "city": "Springfield",
            "state": "IL",
            "postal_code": "62704",
            "is_active": "on",
        },
    )

    property_.refresh_from_db()
    assert response.status_code == 302
    assert property_.property_type == PropertyType.RESIDENTIAL


def test_a_commercial_property_shows_dashes_for_bedrooms_in_its_unit_table(signed_in):
    property_ = make_property(name="Shops", property_type=PropertyType.COMMERCIAL)
    make_unit(property_, identifier="Storefront")

    body = signed_in.get(reverse("portfolio:property-detail", args=[property_.pk])).content.decode()

    assert "Square feet" in body
    assert "Storefront" in body

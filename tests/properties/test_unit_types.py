"""Commercial and residential units, and the fields only one of them has."""

import pytest
from django.urls import reverse

from apps.properties.constants import UnitType
from apps.properties.models import Unit
from tests.factories import make_manager, make_property, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client):
    client.force_login(make_manager(username="type-manager"))
    return client


def test_the_unit_form_offers_both_types(signed_in):
    property_ = make_property()

    body = signed_in.get(
        reverse("portfolio:unit-create"), {"property": property_.pk}
    ).content.decode()

    assert 'name="unit_type"' in body
    assert "Commercial" in body
    assert "Residential" in body


def test_the_unit_form_preselects_residential(signed_in):
    property_ = make_property()

    response = signed_in.get(reverse("portfolio:unit-create"), {"property": property_.pk})

    assert response.context["form"]["unit_type"].value() == UnitType.RESIDENTIAL


def test_an_explicitly_residential_unit_saves(signed_in):
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:unit-create"),
        {
            "property": property_.pk,
            "identifier": "B",
            "unit_type": "RESIDENTIAL",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    assert Unit.objects.get(identifier="B").unit_type == UnitType.RESIDENTIAL


def test_the_unit_type_is_required(signed_in):
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:unit-create"),
        {"property": property_.pk, "identifier": "B", "is_active": "on"},
    )

    assert response.status_code == 200
    assert not Unit.objects.filter(identifier="B").exists()


def test_a_commercial_unit_is_accepted(signed_in):
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:unit-create"),
        {
            "property": property_.pk,
            "identifier": "Storefront",
            "unit_type": "COMMERCIAL",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    assert Unit.objects.get(identifier="Storefront").unit_type == UnitType.COMMERCIAL


@pytest.mark.parametrize(
    "details",
    [{"bedrooms": 2}, {"bathrooms": "1.5"}, {"bedrooms": 1, "bathrooms": "1.0"}],
    ids=["bedrooms", "bathrooms", "both"],
)
def test_a_commercial_unit_cannot_carry_residential_details(signed_in, details):
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:unit-create"),
        {
            "property": property_.pk,
            "identifier": "Shop",
            "unit_type": "COMMERCIAL",
            "is_active": "on",
            **details,
        },
    )

    assert response.status_code == 200
    assert not Unit.objects.filter(identifier="Shop").exists()
    assert b"leave them blank for a commercial unit" in response.content


def test_a_residential_unit_keeps_its_bedrooms_and_bathrooms(signed_in):
    property_ = make_property()

    signed_in.post(
        reverse("portfolio:unit-create"),
        {
            "property": property_.pk,
            "identifier": "Flat 2",
            "unit_type": "RESIDENTIAL",
            "bedrooms": 3,
            "bathrooms": "2.5",
            "is_active": "on",
        },
    )

    unit = Unit.objects.get(identifier="Flat 2")
    assert unit.bedrooms == 3
    assert unit.bathrooms == pytest.approx(2.5)


def test_switching_a_unit_to_commercial_needs_the_details_cleared_first(signed_in):
    unit = make_unit(make_property(), identifier="A")

    response = signed_in.post(
        reverse("portfolio:unit-update", args=[unit.pk]),
        {
            "property": unit.property_id,
            "identifier": "A",
            "unit_type": "COMMERCIAL",
            "bedrooms": 2,
            "bathrooms": "1.0",
            "is_active": "on",
        },
    )

    assert response.status_code == 200
    unit.refresh_from_db()
    assert unit.unit_type == UnitType.RESIDENTIAL
    assert b"leave them blank for a commercial unit" in response.content


def test_the_detail_page_says_not_applicable_for_a_commercial_unit(signed_in):
    unit = make_unit(make_property(), identifier="Storefront", unit_type=UnitType.COMMERCIAL)

    body = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()

    assert body.count("Not applicable") == 2
    assert "residential details" in body


def test_the_detail_page_says_not_recorded_for_a_blank_residential_unit(signed_in):
    unit = make_unit(make_property(), identifier="1", bedrooms=None, bathrooms=None)

    body = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()

    assert body.count("Not recorded") == 2
    assert "Not applicable" not in body


def test_the_unit_list_shows_the_type(signed_in):
    make_unit(make_property(), identifier="Shop", unit_type=UnitType.COMMERCIAL)

    body = signed_in.get(reverse("portfolio:unit-list")).content.decode()

    assert "Commercial" in body
    assert "Type" in body


def test_the_property_page_shows_each_unit_type(signed_in):
    property_ = make_property()
    make_unit(property_, identifier="Shop", unit_type=UnitType.COMMERCIAL)
    make_unit(property_, identifier="Flat", unit_type=UnitType.RESIDENTIAL)

    body = signed_in.get(reverse("portfolio:property-detail", args=[property_.pk])).content.decode()

    assert "Commercial" in body
    assert "Residential" in body

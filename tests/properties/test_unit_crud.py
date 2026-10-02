"""Unit screens: creation inside a property, editing, and service state."""

import pytest
from django.urls import reverse

from apps.properties.models import Unit
from tests.factories import make_manager, make_property, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client):
    client.force_login(make_manager(username="unit-manager"))
    return client


def test_create_a_unit_from_a_property(signed_in):
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:unit-create"),
        {
            "property": property_.pk,
            "identifier": "B",
            "bedrooms": 2,
            "bathrooms": "1.5",
            "is_active": "on",
        },
    )

    unit = Unit.objects.get(identifier="B")
    assert response.status_code == 302
    assert unit.property == property_
    assert unit.bathrooms == pytest.approx(1.5)
    assert response["Location"] == reverse("portfolio:unit-detail", args=[unit.pk])


def test_the_add_unit_link_preselects_the_property(signed_in):
    property_ = make_property()

    response = signed_in.get(reverse("portfolio:unit-create"), {"property": property_.pk})

    assert response.context["form"].initial["property"] == property_.pk


def test_duplicate_identifier_at_the_same_property_is_reported(signed_in):
    property_ = make_property()
    make_unit(property_, identifier="A")

    response = signed_in.post(
        reverse("portfolio:unit-create"),
        {
            "property": property_.pk,
            "identifier": "A",
            "is_active": "on",
        },
    )

    assert response.status_code == 200
    assert Unit.objects.filter(identifier="A").count() == 1
    assert b"already used at this property" in response.content


def test_identifier_whitespace_is_normalised(signed_in):
    property_ = make_property()

    signed_in.post(
        reverse("portfolio:unit-create"),
        {
            "property": property_.pk,
            "identifier": "  B 1 ",
            "is_active": "on",
        },
    )

    assert Unit.objects.get().identifier == "B 1"


def test_the_same_identifier_is_allowed_at_another_property(signed_in):
    make_unit(make_property(name="One"), identifier="A")
    other = make_property(name="Two")

    signed_in.post(
        reverse("portfolio:unit-create"),
        {"property": other.pk, "identifier": "A", "is_active": "on"},
    )

    assert Unit.objects.filter(identifier="A").count() == 2


def test_edit_a_unit(signed_in):
    unit = make_unit(make_property(), identifier="A")

    response = signed_in.post(
        reverse("portfolio:unit-update", args=[unit.pk]),
        {
            "property": unit.property_id,
            "identifier": "A",
            "bedrooms": 4,
            "bathrooms": "2.0",
            "is_active": "on",
        },
    )

    unit.refresh_from_db()
    assert response.status_code == 302
    assert unit.bedrooms == 4


def test_out_of_service_properties_are_not_offered_for_new_units(signed_in):
    make_property(name="Retired", is_active=False)
    make_property(name="Working")

    response = signed_in.get(reverse("portfolio:unit-create"))
    queryset = response.context["form"].fields["property"].queryset

    assert list(queryset.values_list("name", flat=True)) == ["Working"]


def test_a_unit_on_a_retired_property_keeps_that_property_selectable(signed_in):
    retired = make_property(name="Retired", is_active=False)
    unit = make_unit(retired, identifier="A")

    response = signed_in.get(reverse("portfolio:unit-update", args=[unit.pk]))
    queryset = response.context["form"].fields["property"].queryset

    assert retired in queryset


def test_toggle_a_unit_service_state(signed_in):
    unit = make_unit(make_property(), identifier="A")

    signed_in.post(reverse("portfolio:unit-toggle-active", args=[unit.pk]))
    unit.refresh_from_db()
    assert unit.is_active is False

    signed_in.post(reverse("portfolio:unit-toggle-active", args=[unit.pk]))
    unit.refresh_from_db()
    assert unit.is_active is True


def test_negative_bedroom_counts_are_rejected(signed_in):
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:unit-create"),
        {
            "property": property_.pk,
            "identifier": "A",
            "bedrooms": -2,
            "is_active": "on",
        },
    )

    assert response.status_code == 200
    assert not Unit.objects.exists()


def test_unit_list_filters_by_property(signed_in):
    first = make_property(name="First")
    second = make_property(name="Second")
    make_unit(first, identifier="A")
    make_unit(second, identifier="B")

    response = signed_in.get(reverse("portfolio:unit-list"), {"property": first.pk})

    assert [property_.name for property_ in response.context["properties"]] == ["First"]
    assert [unit.identifier for unit in response.context["units"]] == ["A"]


def test_unit_list_searches_by_property_name(signed_in):
    make_unit(make_property(name="Apple Lane"), identifier="A")
    make_unit(make_property(name="Zebra Court"), identifier="B")

    response = signed_in.get(reverse("portfolio:unit-list"), {"q": "Zebra"})

    assert [property_.name for property_ in response.context["properties"]] == ["Zebra Court"]
    assert [unit.identifier for unit in response.context["units"]] == ["B"]


def test_unit_detail_points_back_at_its_property(signed_in):
    unit = make_unit(make_property(name="Maple Street Duplex"), identifier="4")

    body = signed_in.get(reverse("portfolio:unit-detail", args=[unit.pk])).content.decode()

    assert "Maple Street Duplex" in body
    assert "12 Maple St, Springfield, IL 62704" in body
    # The tenancy panel is real from Phase 3 on: this unit has no lease yet.
    assert "Tenancy" in body
    assert "Nobody is on a lease here right now" in body

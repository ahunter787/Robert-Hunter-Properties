"""Destructive operations: confirmation first, and PROTECT at the database."""

import pytest
from django.urls import reverse

from apps.properties.models import Property, Unit
from tests.factories import make_admin, make_manager, make_property, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="delete-admin"))
    return client


def test_the_delete_page_asks_for_confirmation(as_admin):
    property_ = make_property()

    body = as_admin.get(reverse("portfolio:property-delete", args=[property_.pk])).content.decode()

    assert "Delete Maple Street Duplex?" in body
    assert "cannot be undone" in body
    assert property_.name in body


def test_the_confirmation_warns_when_units_exist(as_admin):
    property_ = make_property()
    make_unit(property_, identifier="A")
    make_unit(property_, identifier="B")

    body = as_admin.get(reverse("portfolio:property-delete", args=[property_.pk])).content.decode()

    assert "still has 2 units" in body


def test_confirming_deletes_the_property(as_admin):
    property_ = make_property()

    response = as_admin.post(reverse("portfolio:property-delete", args=[property_.pk]))

    assert response.status_code == 302
    assert response["Location"] == reverse("portfolio:property-list")
    assert not Property.objects.filter(pk=property_.pk).exists()


def test_a_property_with_units_cannot_be_deleted(as_admin):
    property_ = make_property()
    make_unit(property_, identifier="A")

    response = as_admin.post(reverse("portfolio:property-delete", args=[property_.pk]), follow=True)

    assert Property.objects.filter(pk=property_.pk).exists()
    assert b"still has units" in response.content
    assert b"Take it out of service instead" in response.content


def test_deleting_units_then_the_property_succeeds(as_admin):
    property_ = make_property()
    unit = make_unit(property_, identifier="A")

    as_admin.post(reverse("portfolio:unit-delete", args=[unit.pk]))
    as_admin.post(reverse("portfolio:property-delete", args=[property_.pk]))

    assert not Property.objects.exists()


def test_unit_delete_asks_for_confirmation_and_deletes(as_admin):
    unit = make_unit(make_property(), identifier="A")

    confirmation = as_admin.get(reverse("portfolio:unit-delete", args=[unit.pk])).content.decode()
    assert "Delete unit A?" in confirmation

    response = as_admin.post(reverse("portfolio:unit-delete", args=[unit.pk]))

    assert response.status_code == 302
    assert response["Location"] == reverse("portfolio:unit-list")
    assert not Unit.objects.filter(pk=unit.pk).exists()


def test_deletion_requires_an_admin(client):
    """A manager runs the portfolio but cannot destroy records."""
    manager = make_manager(username="manager-cannot-delete")
    property_ = make_property()
    client.force_login(manager)

    assert client.get(reverse("portfolio:property-delete", args=[property_.pk])).status_code == 403
    assert client.post(reverse("portfolio:property-delete", args=[property_.pk])).status_code == 403
    assert Property.objects.filter(pk=property_.pk).exists()


@pytest.mark.parametrize(
    "url_name",
    [
        "portfolio:property-toggle-active",
        "portfolio:unit-toggle-active",
    ],
)
def test_state_changes_are_post_only(client, url_name):
    client.force_login(make_manager(username="post-only-manager"))
    property_ = make_property()
    unit = make_unit(property_, identifier="A")
    target = property_.pk if "property" in url_name else unit.pk

    assert client.get(reverse(url_name, args=[target])).status_code == 405

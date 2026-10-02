"""The map pin on the property screens."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from tests.factories import make_manager, make_property

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client):
    client.force_login(make_manager(username="map-manager"))
    return client


def property_payload(property_, **overrides):
    payload = {
        "name": property_.name,
        "property_type": property_.property_type,
        "street": property_.street,
        "city": property_.city,
        "state": property_.state,
        "postal_code": property_.postal_code,
        "is_active": "on",
    }
    payload.update(overrides)
    return payload


def test_a_pasted_maps_link_becomes_the_pin(signed_in):
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:property-update", args=[property_.pk]),
        property_payload(
            property_, coordinates="https://www.google.com/maps/place/X/@45.5231,-122.6765,15z"
        ),
    )

    property_.refresh_from_db()
    assert response.status_code == 302
    assert str(property_.latitude) == "45.523100"
    assert str(property_.longitude) == "-122.676500"
    assert property_.has_map_pin is True


def test_the_edit_form_shows_the_existing_pin(signed_in):
    property_ = make_property(latitude="45.523100", longitude="-122.676500")

    body = signed_in.get(reverse("portfolio:property-update", args=[property_.pk])).content.decode()

    assert "45.523100, -122.676500" in body


def test_unreadable_coordinates_are_reported_on_the_field(signed_in):
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:property-update", args=[property_.pk]),
        property_payload(property_, coordinates="somewhere downtown"),
    )

    property_.refresh_from_db()
    assert response.status_code == 200
    assert property_.has_map_pin is False
    assert b"Could not read coordinates" in response.content


def test_clearing_the_field_removes_the_pin(signed_in):
    property_ = make_property(latitude="45.523100", longitude="-122.676500")

    signed_in.post(
        reverse("portfolio:property-update", args=[property_.pk]),
        property_payload(property_, coordinates=""),
    )

    property_.refresh_from_db()
    assert property_.has_map_pin is False


def test_the_property_page_embeds_the_map(signed_in):
    property_ = make_property(latitude="45.523100", longitude="-122.676500")

    body = signed_in.get(reverse("portfolio:property-detail", args=[property_.pk])).content.decode()

    assert "google.com/maps?q=45.523100,-122.676500" in body
    assert "output=embed" in body
    assert "Open in Google Maps" in body
    assert 'loading="lazy"' in body


def test_a_property_without_a_pin_says_so(signed_in):
    property_ = make_property()

    body = signed_in.get(reverse("portfolio:property-detail", args=[property_.pk])).content.decode()

    assert "No map pin yet" in body
    assert "<iframe" not in body
    assert "Open in Google Maps" not in body


def test_the_embed_api_is_used_when_the_key_is_configured(signed_in, settings):
    settings.GOOGLE_MAPS_EMBED_API_KEY = "unit-test-key"
    property_ = make_property(latitude="45.523100", longitude="-122.676500")

    body = signed_in.get(reverse("portfolio:property-detail", args=[property_.pk])).content.decode()

    assert "google.com/maps/embed/v1/place" in body
    assert "key=unit-test-key" in body


EXPANDED_PLACE_URL = (
    "https://www.google.com/maps/place/PDX+Woodworks/@45.5192592,-122.6588731,17z"
    "/data=!3m1!4b1!4m6!3m5!1s0x5495a13a5130ad29!8m2!3d45.5192555!4d-122.6562928"
)


def test_a_shortened_link_is_expanded_and_the_place_is_pinned(signed_in, monkeypatch):
    monkeypatch.setattr(
        "apps.properties.locations.resolve_short_link", lambda url: EXPANDED_PLACE_URL
    )
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:property-update", args=[property_.pk]),
        property_payload(property_, coordinates="https://maps.app.goo.gl/bEFCdqfhvPGhsMa39"),
    )

    property_.refresh_from_db()
    assert response.status_code == 302
    # The place marker, not the camera position the link happened to carry.
    assert str(property_.latitude) == "45.519256"
    assert str(property_.longitude) == "-122.656293"


def test_a_link_that_cannot_be_expanded_reports_why(signed_in, monkeypatch):
    def explode(url):
        raise ValidationError("RHP could not reach Google to expand that shortened link.")

    monkeypatch.setattr("apps.properties.locations.resolve_short_link", explode)
    property_ = make_property()

    response = signed_in.post(
        reverse("portfolio:property-update", args=[property_.pk]),
        property_payload(property_, coordinates="https://maps.app.goo.gl/bEFCdqfhvPGhsMa39"),
    )

    property_.refresh_from_db()
    assert response.status_code == 200
    assert property_.has_map_pin is False
    assert b"could not reach Google" in response.content

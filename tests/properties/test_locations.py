"""Map pins: expanding shared links, reading coordinates, and building map URLs.

No test here touches the network: the resolver is exercised through a stubbed
opener, and ``parse_coordinates`` is given an injected resolver.
"""

from decimal import Decimal
from email.message import Message
from urllib.error import HTTPError, URLError

import pytest
from django.core.exceptions import ValidationError

from apps.properties.locations import (
    embed_url,
    external_url,
    is_short_link,
    parse_coordinates,
    resolve_short_link,
)

PIN = (Decimal("45.5231"), Decimal("-122.6765"))

SHORT_URL = "https://maps.app.goo.gl/bEFCdqfhvPGhsMa39"
# The shape Google returns for a shared place: the camera at "@", the place at "!3d/!4d".
EXPANDED_URL = (
    "https://www.google.com/maps/place/PDX+Woodworks/@45.5192592,-122.6588731,17z"
    "/data=!3m1!4b1!4m6!3m5!1s0x5495a13a5130ad29!8m2!3d45.5192555!4d-122.6562928"
)
PLACE_PIN = (Decimal("45.519256"), Decimal("-122.656293"))

ACCEPTED = [
    "45.5231, -122.6765",
    "45.5231,-122.6765",
    "45.5231 -122.6765",
    "https://www.google.com/maps/place/Portland/@45.5231,-122.6765,15z",
    "https://www.google.com/maps?q=45.5231,-122.6765",
    "https://www.google.com/maps/place/X/data=!3d45.5231!4d-122.6765",
]


# --- reading what staff paste ---------------------------------------------


@pytest.mark.parametrize("text", ACCEPTED)
def test_accepted_formats_parse_to_the_same_pin(text):
    assert parse_coordinates(text) == PIN


def test_the_place_marker_wins_over_the_map_camera():
    """The camera is where the map was looking; the place marker is the place."""
    assert parse_coordinates(EXPANDED_URL) == PLACE_PIN


def test_the_camera_is_used_when_there_is_no_place_marker():
    url = "https://www.google.com/maps/place/Portland/@45.5231,-122.6765,15z"

    assert parse_coordinates(url) == PIN


def test_southern_and_eastern_coordinates_keep_their_signs():
    assert parse_coordinates("-33.8688, 151.2093") == (
        Decimal("-33.8688"),
        Decimal("151.2093"),
    )


@pytest.mark.parametrize("text", ["", "   ", None])
def test_no_input_means_no_pin(text):
    assert parse_coordinates(text) is None


@pytest.mark.parametrize(
    "text",
    ["somewhere near the river", "12 Main Street", "40.7", "coordinates to follow"],
)
def test_unreadable_text_is_rejected(text):
    with pytest.raises(ValidationError):
        parse_coordinates(text)


@pytest.mark.parametrize("text", ["91.0, 0", "0, 181", "-90.5, -200"])
def test_out_of_range_coordinates_are_rejected(text):
    with pytest.raises(ValidationError) as error:
        parse_coordinates(text)

    assert "out of range" in str(error.value)


def test_precision_is_capped_at_six_decimals():
    latitude, longitude = parse_coordinates("45.5231234567, -122.6765123456")

    assert latitude == Decimal("45.523123")
    assert longitude == Decimal("-122.676512")


# --- shortened links ------------------------------------------------------


def test_a_shortened_link_is_expanded_before_parsing(monkeypatch):
    monkeypatch.setattr("apps.properties.locations.resolve_short_link", lambda url: EXPANDED_URL)

    assert parse_coordinates(SHORT_URL) == PLACE_PIN


def test_expansion_can_be_switched_off(settings):
    settings.RHP_RESOLVE_MAP_SHORT_LINKS = False

    with pytest.raises(ValidationError) as error:
        parse_coordinates(SHORT_URL)

    assert "expanding links is switched off" in str(error.value)


def test_a_link_that_expands_without_coordinates_says_so(monkeypatch):
    monkeypatch.setattr(
        "apps.properties.locations.resolve_short_link",
        lambda url: "https://consent.google.com/m?continue=...",
    )

    with pytest.raises(ValidationError) as error:
        parse_coordinates(SHORT_URL)

    assert "could not find coordinates" in str(error.value)


def test_an_unreachable_google_is_reported_with_guidance(monkeypatch):
    def explode(url):
        raise ValidationError("RHP could not reach Google to expand that shortened link.")

    monkeypatch.setattr("apps.properties.locations.resolve_short_link", explode)

    with pytest.raises(ValidationError) as error:
        parse_coordinates(SHORT_URL)

    assert "could not reach Google" in str(error.value)


def test_only_shortener_hosts_count_as_short_links():
    assert is_short_link(SHORT_URL) is True
    assert is_short_link("https://goo.gl/abc123") is True
    assert is_short_link("https://www.google.com/maps/place/X/@45.5,-122.6,15z") is False
    assert is_short_link("45.5231, -122.6765") is False


# --- the resolver itself (no network) -------------------------------------


class _Opener:
    """Stands in for urllib's opener, so no request actually leaves the process."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requested = []

    def open(self, request, timeout=None):
        self.requested.append(request.full_url)
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _redirect(to: str) -> HTTPError:
    headers = Message()
    headers["Location"] = to
    return HTTPError("https://maps.app.goo.gl/x", 302, "Found", headers, None)


def test_the_resolver_follows_a_google_redirect(monkeypatch):
    opener = _Opener([_redirect(EXPANDED_URL), _Response()])
    monkeypatch.setattr("urllib.request.build_opener", lambda *handlers: opener)

    assert resolve_short_link(SHORT_URL) == EXPANDED_URL
    assert opener.requested == [SHORT_URL, EXPANDED_URL]


def test_the_resolver_will_not_leave_googles_hosts(monkeypatch):
    """A short link must not become a way to make the server fetch anything else."""
    opener = _Opener([_redirect("http://169.254.169.254/latest/meta-data/")])
    monkeypatch.setattr("urllib.request.build_opener", lambda *handlers: opener)

    with pytest.raises(ValidationError) as error:
        resolve_short_link(SHORT_URL)

    assert "will not follow" in str(error.value)
    assert len(opener.requested) == 1  # it never asked for the metadata address


def test_the_resolver_stops_after_too_many_redirects(monkeypatch):
    opener = _Opener([_redirect("https://www.google.com/maps/1")] * 6)
    monkeypatch.setattr("urllib.request.build_opener", lambda *handlers: opener)

    with pytest.raises(ValidationError) as error:
        resolve_short_link(SHORT_URL)

    assert "will not follow" in str(error.value)
    assert len(opener.requested) == 5


def test_the_resolver_reports_an_unreachable_google(monkeypatch):
    opener = _Opener([URLError("no route to host")])
    monkeypatch.setattr("urllib.request.build_opener", lambda *handlers: opener)

    with pytest.raises(ValidationError) as error:
        resolve_short_link(SHORT_URL)

    assert "could not reach Google" in str(error.value)


# --- link building --------------------------------------------------------


def test_the_keyless_embed_is_the_default():
    url = embed_url(*PIN)

    assert url.startswith("https://www.google.com/maps?q=45.5231,-122.6765")
    assert "output=embed" in url
    assert "key=" not in url


def test_the_embed_api_is_used_when_a_key_is_configured():
    url = embed_url(*PIN, "test-key")

    assert url.startswith("https://www.google.com/maps/embed/v1/place")
    assert "key=test-key" in url
    assert "45.5231,-122.6765" in url


def test_the_external_link_opens_the_pin_in_maps():
    url = external_url(*PIN)

    assert url.startswith("https://www.google.com/maps/search/?api=1")
    assert "45.5231,-122.6765" in url

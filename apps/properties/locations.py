"""Map coordinates: expanding shared links, parsing them, and building map URLs.

RHP stores a pin; it does not geocode an address. Staff paste a Google Maps link or
a latitude/longitude pair, and that text is parsed here.

Parsing is offline for every link shape that already contains the coordinates. The
one exception is a *shortened* share link (``maps.app.goo.gl/...``), which carries
no coordinates at all: it is expanded with a single outbound request to Google,
following redirects only to Google's own hosts (ADR-006). Nothing else leaves the
process.
"""

import logging
import re
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger("apps.properties")

# "45.5231, -122.6765" - also with a space or a semicolon, inside a URL or not.
_PAIR = re.compile(r"(-?\d{1,3}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)")
# A Google Maps place URL carries the *camera* as "@45.5231,-122.6765,15z" ...
_AT = re.compile(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
# ... and the *place itself* as "!3dlat!4dlng". The place is the pin.
_BANG = re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)")
# Google's own hosts, including country domains (www.google.com, google.co.uk).
_GOOGLE_HOST = re.compile(r"^([a-z0-9-]+\.)*google\.[a-z.]{2,7}$")

MAX_LATITUDE = Decimal("90")
MAX_LONGITUDE = Decimal("180")
PRECISION = Decimal("0.000001")

#: Hosts whose links carry no coordinates and must be expanded first.
SHORT_LINK_HOSTS = frozenset({"maps.app.goo.gl", "goo.gl", "g.co"})

RESOLVE_TIMEOUT_SECONDS = 5.0
RESOLVE_MAX_HOPS = 5
USER_AGENT = "Mozilla/5.0 (compatible; RHP/0.1)"

UNREADABLE = (
    "Could not read coordinates from that. Paste a Google Maps link that contains the "
    "coordinates, or a pair like 45.5231, -122.6765."
)
SHORTENED_DISABLED = (
    "That is a shortened Google Maps link and expanding links is switched off "
    "(RHP_RESOLVE_MAP_SHORT_LINKS). Open it, copy the coordinates or the full "
    "address-bar link, and paste those instead."
)
UNREACHABLE = (
    "RHP could not reach Google to expand that shortened link. Open it, copy the "
    "coordinates or the full address-bar link, and paste those instead."
)
NO_COORDINATES_AFTER_EXPANSION = (
    "RHP expanded that link but could not find coordinates in it. Open it, copy the "
    "coordinates and paste those instead."
)
REFUSED_REDIRECT = (
    "That link redirects somewhere RHP will not follow. Open it, copy the coordinates "
    "and paste those instead."
)


def _to_decimal(value: str) -> Decimal:
    return Decimal(value).quantize(PRECISION)


def is_short_link(text: str) -> bool:
    """True for a shortened Maps share link, which has to be expanded first."""
    host = (urlparse((text or "").strip()).hostname or "").lower()
    return host in SHORT_LINK_HOSTS


def _is_google_host(host: str) -> bool:
    return bool(_GOOGLE_HOST.match(host or ""))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect automatically; the caller inspects every hop."""

    def redirect_request(self, *args, **kwargs):
        return None


def resolve_short_link(url: str, *, timeout: float = RESOLVE_TIMEOUT_SECONDS) -> str:
    """Expand a shortened Google Maps link into the full URL.

    Redirects are followed by hand and only to Google's own hosts, so a shared
    link cannot be used to make the server fetch an arbitrary address
    (docs/security.md). Raises :class:`ValidationError` on any failure, leaving
    the caller to keep what the user pasted rather than guessing a location.
    """
    opener = urllib.request.build_opener(_NoRedirect)
    current = url

    for _ in range(RESOLVE_MAX_HOPS):
        host = (urlparse(current).hostname or "").lower()
        if not (_is_google_host(host) or host in SHORT_LINK_HOSTS):
            raise ValidationError(REFUSED_REDIRECT)

        # noqa: S310 - the host was just checked against Google's own hosts.
        request = urllib.request.Request(current, headers={"User-Agent": USER_AGENT})  # noqa: S310
        try:
            with opener.open(request, timeout=timeout):
                return current
        except urllib.error.HTTPError as error:
            location = error.headers.get("Location") if error.headers else None
            status = error.code
            # HTTPError owns the connection; leaving it open leaks a socket per hop.
            error.close()
            if status in (301, 302, 303, 307, 308) and location:
                current = urljoin(current, location)
                continue
            logger.warning("shortened map link returned %s", status)
            raise ValidationError(NO_COORDINATES_AFTER_EXPANSION) from error
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            logger.warning("could not expand a shortened map link: %s", error)
            raise ValidationError(UNREACHABLE) from error

    raise ValidationError(REFUSED_REDIRECT)


def parse_coordinates(text: str | None, *, resolve=None) -> tuple[Decimal, Decimal] | None:
    """Read a pin out of pasted text.

    Returns ``None`` for empty input (no pin). Shortened links are expanded first
    unless ``RHP_RESOLVE_MAP_SHORT_LINKS`` is off. Raises :class:`ValidationError`
    for text that cannot be read as a coordinate pair, for values out of range,
    and for a link that cannot be expanded.

    ``resolve`` exists so tests can supply the expansion instead of the network.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return None

    expanded = False
    if is_short_link(cleaned):
        if not settings.RHP_RESOLVE_MAP_SHORT_LINKS:
            raise ValidationError(SHORTENED_DISABLED)
        cleaned = (resolve or resolve_short_link)(cleaned)
        expanded = True

    # The place marker is the pin; "@lat,lng" is only where the camera happened to
    # be when the link was copied, and can be streets away from the place.
    match = _BANG.search(cleaned) or _AT.search(cleaned) or _PAIR.search(cleaned)
    if not match:
        raise ValidationError(NO_COORDINATES_AFTER_EXPANSION if expanded else UNREADABLE)

    try:
        latitude, longitude = (_to_decimal(part) for part in match.groups())
    except (InvalidOperation, ValueError) as error:
        raise ValidationError(UNREADABLE) from error

    if abs(latitude) > MAX_LATITUDE or abs(longitude) > MAX_LONGITUDE:
        raise ValidationError(
            "Those coordinates are out of range: latitude within ±90, longitude within ±180."
        )
    return latitude, longitude


def embed_url(latitude, longitude, api_key: str = "") -> str:
    """Google Maps embed URL for a pin.

    Keyless by default (``output=embed``); the official Embed API is used when a
    key is configured, because that is the supported path.
    """
    coordinates = f"{latitude},{longitude}"
    if api_key:
        return f"https://www.google.com/maps/embed/v1/place?key={api_key}&q={coordinates}&zoom=16"
    return f"https://www.google.com/maps?q={coordinates}&z=16&output=embed"


def external_url(latitude, longitude) -> str:
    """A link that opens the pin in Google Maps."""
    return f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"

# ADR-006: Unit types, map pins, and banner photos

- **Status:** Accepted (Phase 2, continued)
- **Date:** 2026-10-01
- **Context:** Phase 2 review — commercial units, property location, and property imagery

## Context

Reviewing Phase 2 raised three things the portfolio model did not cover:

1. A unit is not always a dwelling. RHP manages **storefronts** as well as apartments, and the review
   surfaced that bedrooms and bathrooms — fields taken straight from the specification's `UNIT`
   model — are meaningless for commercial space.
2. A property needs a **location** on a map so staff can find it and recognise it.
3. A property needs a **photo** so a record is identifiable at a glance.

Each one forces a decision that is easy to get wrong: how to model the unit kind without splitting the
table, how to obtain coordinates without making the application depend on Google, and how to accept an
image upload without breaking the rule that uploads are served through permission-checked views.

## Decision

### Unit type, and residential-only attributes

`Unit.unit_type` is a `TextChoices` field (`RESIDENTIAL`, `COMMERCIAL`), defaulting to residential
because that is the common case, indexed for later reporting. Bedrooms and bathrooms stay in the model
(the specification asks for them) but are **rejected on a commercial unit** at the form level, and the
unit screens say "Not applicable" for a commercial unit rather than "Not recorded" — the difference
between "we have not filled this in" and "this does not apply".

The rule is enforced in `UnitForm.clean`, not by hiding the inputs, because a rule that exists only in
the browser is not a rule. The unit type also becomes part of the unit list and the property page, so
the portfolio is legible at a glance.

### Map pin: stored coordinates, pasted by staff, keyless embed

- `Property.latitude` / `Property.longitude` are `DecimalField(max_digits=9, decimal_places=6)` — a
  stored measurement with about 11 cm of precision, `Decimal` rather than a float, consistent with the
  project's treatment of money.
- Staff paste a Google Maps link or a coordinate pair into one field. `apps/properties/locations.py`
  parses `45.5231, -122.6765`, `@45.5231,-122.6765,15z`, `?q=…`, and `!3d…!4d…` forms. Shortened
  (`maps.app.goo.gl`) links are refused with an explanation, because following one would require a
  server-side call to Google.
- **RHP never calls Google from the server.** There is no geocoding at save time and no API key
  required. The map on the property page is a keyless `output=embed` iframe, and the official Embed API
  is used only if `GOOGLE_MAPS_EMBED_API_KEY` is configured. The pin itself is data, and it renders
  even with no network and no key.

### Banner photo: validated upload, served by a view, cleaned up

- `Property.banner_image` is an `ImageField`, which requires **Pillow** — the only dependency this
  change adds.
- Validation: at most `RHP_MAX_UPLOAD_MB` (default 5) megabytes, JPEG/PNG/WebP only, at most
  6000×6000 pixels, and stored under a **randomised** filename in `property_banners/` rather than the
  client's name.
- Serving goes through `PropertyBannerView` (`ManagerRequiredMixin`), so **Caddy still never serves
  `/media`** and the rule in `docs/security.md` holds unchanged. Templates use `{% url %}`, so no media
  path is hard-coded.
- Lifecycle: uploading a replacement deletes the previous file, a "remove" checkbox clears it, and a
  `post_delete` receiver removes the file when a property is deleted — including from the Django admin.

## Consequences

**Positive**

- A storefront is modeled as what it is, and the screens stop implying that missing bedrooms are
  missing data.
- No API key, no outbound network, and no per-save cost for the map: pasting a link is a one-time act
  and the pin is then local data.
- Uploads are bounded, typed, renamed, and permission-served — the security rules are enforced rather
  than documented.
- Property records become visually identifiable, which is what staff actually asked for.

**Negative / accepted trade-offs**

- Asking staff to paste coordinates is more work than geocoding an address. Accepted: geocoding means
  a key, a vendor dependency, and a network call in the save path, and the address is right there on
  the same screen.
- Showing a map means the visitor's browser talks to Google. That is disclosed on the page and will be
  an explicit entry in the Phase 12 content-security policy.
- A keyless embed is an unofficial URL shape; if Google changes it, the key-based Embed API is the
  fallback and already wired.
- Uploads are not resized or thumbnailed, so a large banner is served as uploaded. Thumbnails and
  resizing belong with the general document work in Phase 6.
- Existing commercial units created before this change keep their bedroom values until someone edits
  them: the migration deliberately does not rewrite data.

## Alternatives considered

- **A separate `CommercialUnit` model**: two tables, two sets of screens, and every future relation
  (leases, maintenance, documents) would need to handle both. Rejected.
- **Nullable bedrooms with no rule**: the current state, which is what prompted the review.
- **Hiding bedrooms/bathrooms with JavaScript when Commercial is selected**: brittle, and the rule would
  not hold for a direct POST. Rejected; server-side validation with clear help text instead.
- **Geocoding the address on save**: an API key, a vendor dependency, quota, and a failure mode in the
  save path for a field staff can paste in seconds.
- **Serving banners straight from `/media` (or from Caddy)**: faster, but it breaks the single rule that
  keeps tenant documents private, and "banners are not sensitive" is exactly the kind of exception that
  later swallows the rule.
- **Storing banner images in the database**: keeps backups to one artefact, but bloats the database and
  the backup stream for no benefit at this scale.

## Revision: shortened links are expanded after all

**Date:** 2026-10-01, same day, after owner testing.

The decision above refused `maps.app.goo.gl/...` links with "open it and paste the coordinates".
That was the wrong trade: those links are what Google's own *Share* button produces, so the refusal hit
the normal path rather than an edge case.

**Revised decision.** A shortened link is expanded at save time, once, with one outbound request:

- the request carries no credentials and only a plain user agent;
- redirects are followed **by hand**, at most five hops, and only ever to Google's own hosts
  (`*.google.*`), so a shared link cannot be used to make the server fetch an internal address —
  a redirect anywhere else is refused;
- the timeout is 5 seconds, and any failure (offline, blocked, consent page) leaves the field as the
  user typed it with a message that says what to do instead;
- `RHP_RESOLVE_MAP_SHORT_LINKS=0` turns the whole thing off for a host with no outbound network.

Every other link shape is still parsed completely offline; only shortener hosts trigger a request.

**Also corrected: the place marker is the pin.** A shared place URL carries two coordinate pairs — the
map *camera* as `@lat,lng,zoom` and the *place* as `!3d…!4d…`. The first version preferred the camera,
which in the owner's own link sits about 380 m from the actual place. The parser now prefers
`!3d/!4d` and falls back to `@` only when there is no place marker.

**Consequence.** The application can now make one outbound HTTPS request to Google, which the original
decision explicitly avoided. It is bounded (one host family, five hops, five seconds, no credentials)
and it is the only outbound request in RHP. The containment is asserted by tests that feed the resolver
a redirect to a link-local address and check that it is refused without being requested.

## Revision: the designation moves to the property, and units gain size and amenities

**Date:** 2026-10-02, while Phase 4 was open, after owner review of the portfolio screens.

The decision above put the Residential/Commercial designation on the **unit**. In use that is the wrong
place for it: a designation describes a *building*, it was being asked for once per unit inside a
building that already answers the question, and a mixed set of units in one property was a data-entry
problem rather than a real distinction. Three changes follow from that review.

### The property carries the designation; units inherit it

- `Unit.unit_type` is **removed** and `Property.property_type` takes its place (`PropertyType`, same
  two values, indexed, defaulting to residential).
- `Unit.is_commercial` now reads through its property, so every screen and rule keeps working while the
  field that people fill in exists once per building.
- The residential rule moves with it: bedrooms and bathrooms are refused for a unit **in a commercial
  property** — including when an existing unit is moved into one, because the rule is checked against
  the property being submitted, not the one it came from.
- Switching a property **to** commercial while any of its units still records bedrooms or bathrooms is
  refused, and the refusal names those units. Silently clearing them would destroy a measurement
  somebody entered; refusing lets a person decide.
- The data migration gives each property the designation its units had: commercial only when **every**
  unit was commercial, residential otherwise. A property with no units, and a mixed one, become
  residential.

**The trade-off, stated plainly.** A mixed-use building — a storefront with apartments above it — can no
longer be expressed, because the building now has one answer. The migration resolves the ambiguity
deterministically rather than guessing, the current database is empty so nothing was lost when it ran,
and if mixed-use turns out to matter, a per-unit override can be added later without disturbing the
property-level field. What the review gained is a designation that matches how staff talk about these
buildings ("the Stark Street shops") and one fewer field per unit.

### Units record their size

`Unit.square_feet` is an optional `PositiveIntegerField` (1 … 1 000 000, `0` refused as nonsense).
Blank means "not recorded" and every screen says so rather than showing a zero. The unit list's old Type
column becomes **Square footage**, and the property page adds a total when at least one unit has a
figure — the measurement is per unit because that is what an agreement is about.

### Amenities come from a list staff maintain

`Amenity(name, is_active)` with a many-to-many from `Unit`, seeded with seventeen common amenities by
the same migration. Chosen from a multi-select on the unit form, shown as chips on the unit page.

- A row in the database rather than a fixed choice list, so an amenity can be added or renamed in the
  back office without a code change — the review round's whole point was that these lists change.
- **Retire, don't delete.** An amenity in use is unticked, not removed: deleting a row would quietly
  change every unit that had it. A retired amenity leaves the picker but stays on the units that have
  it, and stays selectable while editing one of those units.

### The unit list is grouped by property

`/manage/units/` pages by **property** (25 per page) rather than by unit, so the grouping survives
pagination and a property's units are never split across pages. Filters scope both levels: a property
appears because it has a matching unit, and shows only those units. Each group is headed by the
property's name, its type and its address, with an **Add unit** link that preselects it.

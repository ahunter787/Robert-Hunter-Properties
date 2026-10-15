# Phase 2 — Property and tenant management

**Status:** Complete
**Milestone:** 2 — The real portfolio is modeled: properties, units, tenants, leases
**Specification:** `docs/harness/master-spec.md`, `PHASE 2 — PROPERTY AND TENANT MANAGEMENT`

## Scope as specified

The portfolio: properties, the units inside them, and the tenant records that will later be attached to a
lease. Staff screens to list, create, edit and retire each; destructive operations confirmed and
restricted. The specification also asks for a property's maintenance summary and documents — both belong
to later phases and are labelled rather than faked.

## What exists today

- **Models** (`apps/properties/models.py`): `Property` (address, residential/commercial designation, map
  pin, banner photo, retirement flag), `Unit` (identifier, square feet, bedrooms, bathrooms, amenities,
  active flag), `Amenity` (maintained in the back office, retired rather than deleted).
- **Screens** (`/manage/properties/`, `/manage/units/`): list, detail, create, edit, retire; units grouped
  by property and paged by property; admin-only deletion behind a confirmation page.
- **Relationships:** `PROTECT` foreign keys make "delete a building that has units" impossible rather than
  merely discouraged. `Unit` is a first-class record with a stable id, which is what let Phase 3 attach
  `Lease.unit` without reshaping anything.
- **Media:** the property banner photo and the tenant photo are both stored under randomised names and
  served through permission-checked views, never by the web server or the proxy.
- **Tenant records:** created and changed by admins; managers have read access (`/manage/accounts/`).

## Decisions that govern it

| Record | What it settled |
| --- | --- |
| [ADR-005](../decisions/ADR-005-portfolio-modeling.md) | Property → unit → lease, retirement instead of deletion, and which panels are deliberately labelled until a later phase fills them |
| [ADR-006](../decisions/ADR-006-unit-types-maps-and-banners.md) | Unit types, the residential/commercial designation (later moved to the property), the map pin parsed from a pasted Google Maps link or coordinates, and the validated banner photo |

## Extensions filed under this phase

None filed here. **P4-E2** (property responsibilities) reaches into this phase: it hangs a
`PropertyResponsibility` and its cycles off a property and splits the cost across that property's units by
square footage, and it added `Property.cam_rate_per_sqft`. See the
[Phase 4 record](phase-04-rent-ledger.md#extensions-filed-under-this-phase).

## Acceptance criteria and evidence

- [x] An admin can create, edit and deactivate properties; managers can too (the specification grants them
      the portfolio)
- [x] An admin can create and edit units, and the screens refuse bedrooms/bathrooms on a commercial unit,
      saying "Not applicable" rather than "Not recorded"
- [x] `Unit` is a first-class record, so Phase 3 attaches `Lease.unit` with no reshaping
- [x] Destructive operations require confirmation and are admin-only
- [x] A property stores a map pin (full or shortened link, or coordinates) and shows it, linking out to
      Google Maps
- [x] The banner photo is validated (size, type, dimensions), served through a permission-checked view,
      and removed when replaced or when the property is deleted
- [x] Unit screens read identifier first, property second (`Storefront` / `- 910 Stark`)
- [x] `/manage/units/` is grouped by property with square footage in place of the old Type column

`tests/properties/` covers the model rules, the screens, the media views and the permission boundaries.

## Deliberately not here

Each panel the specification lists but a later phase owns is labelled in the UI rather than faked:

| Panel or counter | Arrives with |
| --- | --- |
| Property maintenance summary, unit recent maintenance | Phase 7 |
| Property documents | Phase 6 |
| Open maintenance requests counter | Phase 7 |
| Full admin dashboard | Phase 9 |

## Known gaps and defects

- The occupancy and vacancy counters on the staff landing page are derived from leases (Phase 3) and will
  be consolidated into the real dashboard in Phase 9.
- Amenities are a maintained list; there is no per-unit amenity *history*, so a removal loses the fact
  that it was ever there. Reports in Phase 10 should read the retirement flag, not the current list.
- Ownership and purchase information (what the owner pays for a building, land value, depreciation) is not
  modelled at all. That is the owner-facing finance direction recorded in `extensions.md`, not a Phase 2
  deliverable.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P2-Q1 | Should a retired unit or property stay visible in later reports as history? | Yes — retirement means "not rentable", not "never existed"; reports should include retired records with a marker. | *(awaiting)* |
| P2-Q2 | Do you want vendor or owner records attached to a property (who maintains what, who owns it)? | Phase 7 introduces vendors for maintenance; ownership is a separate direction and should not be smuggled into Phase 2. | *(awaiting)* |

## How to verify it

`make test` (with `tests/properties/`), then browse `/manage/properties/` and `/manage/units/`: create a
property with a map pin and a banner, add a unit with square feet and amenities, retire it, and confirm the
counter changes. `/manage/` shows the portfolio totals for the role you are signed in as.

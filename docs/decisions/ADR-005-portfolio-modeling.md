# ADR-005: Portfolio modeling — properties, units, and deletion policy

- **Status:** Accepted (Phase 2)
- **Date:** 2026-10-01
- **Context:** Phase 2 property and unit management

## Context

Phase 2 lets RHP model the portfolio it actually operates: buildings and the rentable units inside
them. The specification names `PROPERTY` (name, street, city, state, ZIP, active status, notes) and
`UNIT` (property, unit identifier, optional bedrooms, optional bathrooms, active status), and requires
that "destructive operations require confirmation". It also lists occupancy, active leases, rent, and
maintenance on the property and unit pages — none of which exist until Phase 3 (leases) or Phase 7
(maintenance).

Decisions needed: how to model the hierarchy, how records stop being used, who may do what, and what
to show where the data does not exist yet.

## Decision

1. **Two models in `apps/properties`**: `Property` and `Unit`, with `Unit.property` a foreign key.
   A unit is a first-class record (it is what a lease and a maintenance request attach to), not a
   string field on the property.
2. **`Unit.property` uses `PROTECT`, not `CASCADE`.** Deleting a property with units raises
   `ProtectedError`; the screen explains it and offers deactivation. Phase 3's `Lease.unit` will do the
   same, so a unit with tenancy history cannot be destroyed either.
3. **Deactivation is the everyday path, deletion is the exception.** Both models carry `is_active`;
   retired records stay in history and drop out of pickers. Hard deletion is available to `ADMIN` and
   above behind a confirmation page that names the record and warns about dependent units.
4. **Property names are unique case-insensitively** (`UniqueConstraint(Lower("name"))`); addresses are
   not constrained at all, because a duplex split into two records or a renamed building is a real
   case. Unit identifiers are unique **within** a property (`UniqueConstraint("property",
   "identifier")`) and may repeat across properties.
5. **Roles split by consequence**: `MANAGER` and above read and edit the portfolio; hard deletion is
   `ADMIN` and above. Reading tenant records is a manager activity (the spec grants managers
   "properties, units, tenants"); creating accounts, inviting, deactivating, and changing roles stay
   with admins.
6. **Nothing lease-shaped is faked.** Occupancy, vacancy, current tenant, rent, and maintenance are
   not shown as zeroes. The property page lists a "Not tracked here yet" panel and the unit page a
   "Tenancy" panel, each naming the phase that fills it.
7. **Menu namespace `portfolio`, URL prefix `/manage/`.** A second `include()` under `/manage/`
   cannot reuse the `manage` namespace: two includes sharing one namespace leave the earlier set of
   routes unreachable through `reverse()`.

## Consequences

**Positive**

- The database enforces the two invariants that matter (unique names, unique unit identifiers), so
  the application cannot create duplicates even through the admin.
- `PROTECT` makes "delete everything below this" impossible by accident, and the failure is a readable
  message rather than a silent cascade of lease history.
- Managers do the everyday work; destroying records requires an admin, which matches the
  specification's "destructive operations require confirmation" without inventing new roles.
- The portfolio screens are honest: a number is only displayed when the data behind it exists.

**Negative / accepted trade-offs**

- Deactivation must be understood by staff; a retired property still appears in lists (behind a status
  filter) and in history.
- Two models with an explicit `is_active` on each means a retired property can still contain
  in-service units. That is allowed on purpose (the message says how many are unaffected), but it is
  a state staff can create.
- `property` as a field name shadows Python's builtin `property` inside the `Unit` class body, so
  computed attributes there use `cached_property`. It is a small readability tax paid for a field name
  that reads correctly everywhere else.

## Alternatives considered

- **One `Unit`-only model with the address repeated**: no way to see a building's units together, and
  every lease would duplicate address data. Rejected.
- **`CASCADE` with a confirmation dialog**: one mis-click destroys units and (later) lease history.
  Rejected.
- **Soft-delete flags with a manager that hides deleted rows everywhere**: two kinds of "gone" and a
  query filter that every future view must remember. Deactivation plus rare hard deletion is simpler
  and auditable.
- **`ManagerRequiredMixin` for deletion too**: makes the spec's confirmation requirement the only
  guard on an irreversible action. Rejected in favor of a role boundary.
- **Showing occupancy as 0 until Phase 3**: a number that looks like data but is not. Rejected.

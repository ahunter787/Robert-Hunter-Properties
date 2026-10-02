# RHP roadmap

Derived from the governing specification in [`harness/master-spec.md`](harness/master-spec.md).
Work proceeds one phase at a time; a phase is complete only when its acceptance criteria and tests
pass.

For the readable version — what each phase is for, what exists, and which later phase will change it —
see [`phase-guide.md`](phase-guide.md). This file is the terse checklist.

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Foundation and architecture | **Complete** |
| 1 | Authentication and authorization | **Complete** |
| 2 | Property and tenant management | **In review** (owner testing) |
| 3 | Lease management | Not started |
| 4 | Rent ledger | Not started |
| 5 | Tenant dashboard | Not started |
| 6 | Document management | Not started |
| 7 | Maintenance system | Not started |
| 8 | Communications (announcements) | Not started |
| 9 | Admin dashboard | Not started |
| 10 | Reporting and search | Not started |
| 11 | Payment integration | Blocked by design — requires explicit approval |
| 12 | Production hardening | Not started |

## Milestones

| Milestone | Phases | Outcome |
| --- | --- | --- |
| 1 | 0 + 1 | A deployed portal where RHP can create tenant accounts and tenants can sign in safely |
| 2 | 2 + 3 | The real portfolio is modeled: properties, units, tenants, leases |
| 3 | 4 + 5 | Tenants see their balance and rent due; the ledger is authoritative |
| 4 | 6 + 7 | Documents and maintenance requests work end to end |
| 5 | 8 + 9 | Communication and an operational dashboard for the RHP team |
| 6 | 10 + 12 | Reporting, search, and production hardening |
| later | 11 | Online payments (separate approval; the ledger must be trustworthy first) |

## Phase 0 — Foundation (complete)

Delivered: Django 6.1 project with split settings, PostgreSQL 17, Docker Compose for development and
production, Caddy TLS/static in production, Makefile workflow, `/healthz` readiness probe, console
logging, ruff + pytest with coverage, GitHub Actions CI, Tailwind-based design system, and the
documentation set (architecture, database, deployment, security, ADRs, this roadmap, master spec).

Acceptance criteria from the specification:

- [x] A clean clone launches from the documented instructions (`make init`) — verified by cloning
      the pushed repository into a fresh directory and running the first-run path end to end
      (stack up, migrations applied, `/healthz` 200, landing page, static CSS, admin login, 26 tests)
- [x] PostgreSQL persists across container restarts (named `pgdata` volume)
- [x] The application starts without manual hacks (entrypoint migrates, then serves)
- [x] Tests run (`make test`, against PostgreSQL)
- [x] Environment secrets are not committed (`.env` gitignored/dockerignored; CI has no secrets)
- [x] Development and production configuration are separated (`config/settings/*`, fail-fast prod)

Deliberately **not** in Phase 0: any tenant/staff feature, and any domain app other than
`apps/accounts` (which exists only to fix `AUTH_USER_MODEL` — see
[`decisions/ADR-002-custom-user.md`](decisions/ADR-002-custom-user.md)).

## Phase 1 — Authentication and authorization (complete)

Delivered: sign-in (throttled), sign-out, password reset, admin-created tenant accounts with a
single-use invitation link, role-based permissions, staff/tenant route separation (`/account/` vs
`/manage/`), the account page, and tenant contact details. Decisions are recorded in
[ADR-003](decisions/ADR-003-role-on-user-model.md) (role on the user model) and
[ADR-004](decisions/ADR-004-invitations-and-throttle.md) (invitations and throttling); the
rate-limiting strategy is documented in [`security.md`](security.md).

Acceptance criteria from the specification, each proven by tests in `tests/accounts/`:

- [x] A tenant cannot access management routes (403)
- [x] Tenant A cannot access tenant B data (scoped queries; 404 for another tenancy's records)
- [x] A maintenance user has restricted access (`/manage/` only, no account administration)
- [x] An admin can administer accounts (list, create, invite, deactivate, re-invite)

Also verified: role changes require a superadmin, invitations and resets are single-use, password
reset never reveals whether an address exists, and a deactivated account cannot sign in.

## Phase 2 — Property and tenant management (complete)

Folded into `main` as a single commit after owner testing, and the `rhp-2` branch was deleted. The
build on the branch remains visible in the repository history.

Delivered: the portfolio — properties and their units — with staff screens for listing, creating,
editing, and taking records out of service; admin-only deletion behind a confirmation page; a
`PROTECT` relationship that makes "delete a building with units" impossible rather than merely
discouraged; manager read access to tenant records (creating and changing accounts stays with admins);
and a staff landing page whose counters are true for the role viewing them.

Acceptance criteria from the specification:

- [x] An admin can create, edit, and deactivate properties
- [x] An admin can create and edit units (managers can too — the spec grants managers the portfolio)
- [x] Tenants can be associated with leases later: `Unit` is a first-class record with a stable id, so
      Phase 3 attaches `Lease.unit` without reshaping anything
- [x] Destructive operations require confirmation, and deletion is admin-only

Review round (ADR-006), added while the phase is open:

- [x] Units carry a **type** (Residential / Commercial); bedrooms and bathrooms are refused on a
      commercial unit and the screens say "Not applicable" rather than "Not recorded"
- [x] A property stores a **map pin** (pasted Google Maps link — full *or shortened* — or coordinates)
      and shows it, with an "Open in Google Maps" link; the *place* is pinned, not the map camera
- [x] A property has a **banner photo**, validated (size, type, dimensions), stored under a randomised
      name, served through a permission-checked view, and removed when replaced or when the property is
      deleted
- [x] Unit screens read **identifier first, property second** (`Storefront` / `- 910 Stark`)

Deferred on purpose, each labeled in the UI rather than faked (ADR-005):

| Panel or counter the spec lists | Arrives with |
| --- | --- |
| Property maintenance summary, unit recent maintenance | Phase 7 (maintenance) |
| Property documents | Phase 6 (documents) |
| Open maintenance requests counter | Phase 7 |
| Full admin dashboard | Phase 9 |

## Phase 3 — Lease management (complete)

Folded into `main` as a single commit after owner testing, and the `rhp-3` branch was deleted.

Delivered: the lease desk — leases created and edited by managers and admins, moving *draft* → *active* →
*ended* under explicit actions; one or more tenants per lease with exactly one primary contact; monthly
rent, deposit and rent due day; the lease term; a signed-lease document; and the tenant-facing `/lease/`
page showing their unit, term, rent, deposit, co-tenants and document. The Phase 2 property and unit
panels and the occupied/vacant counters are now filled from leases rather than labeled as missing.

Acceptance criteria from the specification:

- [x] A unit cannot be rented twice: `one_active_lease_per_unit` is a database constraint, not a form rule
- [x] A lease is ended by a person, never by the calendar; ended leases are read-only history
- [x] Co-tenants are supported with exactly one primary contact (`UniqueConstraint` per lease)
- [x] A tenant sees their own lease and document, and nothing else: the tenant document URL carries no id
- [x] Documents are never served by the proxy; both document views check permissions first

Decisions are recorded in [ADR-007](decisions/ADR-007-lease-modeling.md) (lease modeling: one active
lease per unit, explicit status, frozen unit, co-tenants, one document, one occupancy definition).

Deliberately not built here: balances, charges and payments (Phase 4), the full tenant dashboard
(Phase 5), the documents area (Phase 6), electronic signatures (not in the specification).

## Phase 4 — Rent ledger (in review: owner testing)

**Status note:** implemented and tested on the `rhp-4` branch, not yet signed off. `main` is not updated
until the owner has exercised it; the branch is squashed into one commit on `main` afterward.

Delivered: the ledger — recurring monthly rent charges generated on demand and never twice for the same
month, manual charges, recorded payments (cleared or pending), reversals, adjustments, and a running
balance derived from the entries. The accounting area at `/manage/ledger/` lists every live lease with
its balance, overdue amount and next due date; each lease has a ledger with its charges, payments,
merged activity and a History panel written from the audit trail; the tenant's `/lease/` page shows
their own balance, next rent and recent activity; and the staff landing page counts what is outstanding
and what is late. The audit table the phase plan promised now exists and records lease status changes,
money movements and role changes.

Acceptance criteria from the specification:

- [x] Balance is derived from ledger entries — there is no stored balance or charge status anywhere
- [x] Financial history is immutable **and** auditable: append-only models, `PROTECT` foreign keys,
      read-only in the Django admin, and an audit event in the same transaction as every change
- [x] Edits and corrections leave an audit trail: a reversal or adjustment row, with an actor, a
      timestamp and a reason, shown on the lease's History panel
- [x] A tenant sees an understandable balance: what is owed (or in credit), what is next due, and the
      recent activity, on `/lease/`
- [x] Statuses distinguish unpaid, partly paid, paid, overdue and payment pending
- [x] No card or bank credential is stored, and the model leaves room for a provider: amount, date,
      method, free-text reference and a pending state already exist

Decisions are recorded in [ADR-008](decisions/ADR-008-rent-ledger.md) (two tables with explicit
directions, derived balances and states, first-in-first-out allocation, corrections as new entries,
rent generation that is idempotent and bounded by the term, managers record and admins correct).

Deliberately not built here: proration, late fees, interest, invoicing or receipt PDFs (none are in the
specification), deposit returns and deductions, and any payment-provider integration (Phase 11).

Review round, added while the phase is open:

- [x] The **Residential/Commercial designation moved to the property**; units inherit it, the data
      migration gives each property the designation its units had, and a property cannot be switched to
      commercial while its units still record bedrooms or bathrooms (ADR-006 revision)
- [x] Units gained **square feet** and **amenities**, the latter from a list staff maintain in the back
      office and retired rather than deleted (ADR-006 revision)
- [x] `/manage/units/` is **grouped by property** and pages by property, with square footage replacing
      the old Type column
- [x] The ledger's adjustment screen **prefills the amount with what is still owed**, so zeroing a
      charge is one submit, with a second button for the full charge amount
- [x] Tenants gained a **photo** on the account page, admin-set, served through a permission-checked
      view, with a drawn placeholder when there is none (ADR-009)

## Phase 5 — Tenant dashboard

The tenant's five questions answered on one page: how much do I owe, when is it due, where is my
lease, is my maintenance request being handled, has management sent me anything. Mobile-first.

## Phase 6 — Document management

Uploads categorised (lease, addendum, notice, receipt, inspection, correspondence, other) and
attached to a lease, property, or tenant, with explicit tenant visibility and permission-checked
downloads that are never reachable by guessing a URL.

## Phase 7 — Maintenance system

Tenant submission (category, title, description, photos, permission to enter) and a staff queue with
assignment, priority, status transitions (open → acknowledged → scheduled → in progress → waiting →
completed → closed), and a timeline that separates tenant-visible updates from internal notes.

## Phase 8 — Communications

Property-scoped announcements (water shutoff, inspections, parking, holidays) that appear only to the
intended tenants and expire correctly. Direct messaging is evaluated later, not built prematurely.

## Phase 9 — Admin dashboard

Portfolio, rent, maintenance, and lease metrics where every number links to the records behind it —
no decorative analytics.

## Phase 10 — Reporting and search

Search across tenants, properties, units, and leases; reports for rent roll, balances due, payment
history, lease expirations, maintenance aging, and occupancy; CSV export first, PDF only where it
earns its keep.

## Phase 11 — Payment integration (not approved)

Architecture leaves room for ACH/card providers, but nothing is chosen or integrated until explicitly
approved. Provider-hosted/tokenised flows only; no card numbers or bank credentials in RHP.

## Phase 12 — Production hardening

HTTPS, secret management, database and media backups with a tested restore, audit logging, admin MFA,
brute-force mitigation, email configuration, monitoring, error reporting, file-upload restrictions,
log retention, privacy review, and disaster-recovery documentation — plus the security test battery
(tenant isolation, authorization bypass, document and attachment access, id enumeration, sessions).

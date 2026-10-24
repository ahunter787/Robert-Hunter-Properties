# RHP roadmap

Derived from the governing specification in [`harness/master-spec.md`](harness/master-spec.md).
Work proceeds one phase at a time; a phase is complete only when its acceptance criteria and tests
pass.

Each phase also has **one record** in [`phases/`](phases/README.md) — its scope, what exists in the code
today, the decisions that govern it, its gaps, and the questions waiting on you. This file is the terse
checklist and the status word the tooling mirrors into Plane; the record is where the working knowledge
lives. For the long-horizon view — which later phase will change something that already works — see
[`phase-guide.md`](phase-guide.md).

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Foundation and architecture | **Complete** |
| 1 | Authentication and authorization | **Complete** |
| 2 | Property and tenant management | **Complete** |
| 3 | Lease management | **Complete** |
| 4 | Rent ledger | **Complete** |
| 5 | Tenant dashboard | **Complete** |
| 6 | Document management | **Complete** |
| 7 | Maintenance system | **Complete** |
| 8 | Communications (announcements and tenant–RHP messaging) | **Complete** |
| 9 | Admin dashboard | **Complete** |
| 10 | Reporting and search | Not started |
| 11 | Payment integration | Not started — approved, optional for 2027 |
| 12 | Production hardening | Not started |

## Extensions (owner-approved additions)

The specification models a lease as one monthly rent and a ledger of charges. RHP's real leases do more, so
additions that are **not** phases are proposed, approved and tracked in
[`extensions.md`](extensions.md), each with its own decision record and its own branch.

| # | Extension | Status | Decision | Branch |
| --- | --- | --- | --- | --- |
| E1 | Lease templates — Fixed, Step Up, Triple Net (NNN) | **In `main`** | [ADR-013](decisions/ADR-013-lease-templates.md) | folded |
| E2 | Property responsibilities charged to the unit | **In `main`** | [ADR-014](decisions/ADR-014-property-responsibilities.md) | folded |
| E4 | Retroactive onboarding, and a stated rent schedule | **Retired** — the stated-rent part is in `main`; the onboarding mechanism is retired by ADR-028 (ADR-027 supersedes it) | [ADR-016](decisions/ADR-016-retroactive-onboarding.md) | folded |
| E5 | Move-out settlement — the deposit, deductions, a final statement | **In `main`** — ADR-031 | ADR-031 | folded |
| E6 | Post-tenancy charges with their evidence | Proposed — no longer blocked by Phase 6 | — | — |
| E7 | A unit's ledger history | Proposed | — | — |
| E8 | A tenant's request for early termination (filed under Phase 3) | Proposed | — | — |
| E3 | Concessions — forgiveness, a deferral plan, a term extension | Proposed, re-scoped | — | — |
| E9 | Plain-language interface — product vocabulary and account-first design | **In `main`** | [ADR-021](decisions/ADR-021-plain-language-interface.md) | folded |
| E10 | RHP property accounting — general-ledger style books | Building — **B1–B5 in `main`** (ADR-032); go-live onboarding, opening data load and bank-feed follow-ups remain | ADR-026 / ADR-027 / ADR-028 / ADR-029 / ADR-030 / ADR-031 / ADR-032 | folded |
| E11 | Operations desk — shared shell and application migration | In main — owner accepted October 19, 2026; local merge authorized | [Implementation](design/implementation.md) | `codex/operations-desk` |
| E12 | Tenant–RHP messaging (`P8-E1`) — conversations, unread state, protected attachments and email | In main — owner accepted for local merge | [ADR-024](decisions/ADR-024-communications.md) | folded |
| E15 | Messenger operational enhancements — quick replies, archive/mute, export, shared media, internal notes | **In `main`** — optional maintenance context deferred | ADR-033 | folded |
| E16 | Tenant timeline — authorized, date-grouped read model | **In `main`** — first slice | ADR-034 | folded |
| E17 | Renters-insurance proof — three-state proof intake and manager decision | **In `main`** | ADR-035 | folded |
| E18 | Portal UX hardening — grouped navigation, messenger, action-first dashboards, accessibility | Built — folded into `main` | [ux-hardening](design/ux-hardening.md) | `main` |

## Milestones

| Milestone | Phases | Outcome |
| --- | --- | --- |
| 1 | 0 + 1 | A deployed portal where RHP can create tenant accounts and tenants can sign in safely |
| 2 | 2 + 3 | The real portfolio is modeled: properties, units, tenants, leases |
| 3 | 4 + 5 | Tenants see their balance and rent due; the ledger is authoritative |
| 4 | 6 + 7 | Documents and maintenance requests work end to end |
| 5 | 8 + 9 | Communication and an operational dashboard for the RHP team |
| 6 | 10 + 12 | Reporting, search, and production hardening |
| 2027 optional | 11 | One-time ACH and ACH autopay after ledger approval |

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
| Property documents | Phase 6 — filing works; the property page does not list them yet |
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

## Phase 4 — Rent ledger (complete)

**Status note:** implemented and tested on the `rhp-4` branch, reviewed by the owner, and squashed into
`main` as one commit. Phase 5 refines how a tenant *reads* these figures — what is due now, what is past
due, and what is coming due (ADR-012) — without changing the ledger itself.

Delivered: the ledger — recurring monthly rent charges generated on demand and never twice for the same
month, manual charges, recorded payments (cleared or pending), reversals, adjustments, and a running
balance derived from the entries. The accounting area at `/manage/ledger/` lists every live lease with
its balance, what is past due and what is coming due; each lease has a ledger with its charges, payments,
merged activity and a History panel written from the audit trail; the tenant's `/lease/` page shows
what they owe now, their next rent and recent activity; and the staff landing page counts what is
outstanding and what is late. The audit table the phase plan promised now exists and records lease status
changes, money movements and role changes.

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

## Phase 5 — Tenant dashboard (complete)

**Status note:** implemented and tested on the `rhp-5` branch, reviewed by the owner (including on a
phone), and squashed into `main` as one commit; the branch was deleted.

Delivered: the tenant's landing page at `/account/` — what is due now (or that they are in credit, or that
nothing is owing), when the next rent falls due and how much, when their lease ends, quick actions, and
their recent activity — plus `/payments/`, their own statement, and a tenant navigation that has become
real (Dashboard, Lease, Payments). Expected money is labelled "expected" and does not move the balance;
voided entries are hidden from the tenant; the two panels that belong to later phases are labelled rather
than faked.

Acceptance criteria from the specification:

- [x] Works well at phone width — single column, full-width tap targets, list rows rather than tables,
      nothing hidden at small sizes (the final check is the owner's own phone)
- [x] No unnecessary information density — three figures, three actions, five recent rows
- [x] The tenant's critical information is visible without digging — it is the page they land on
- [x] Decided in [ADR-010](decisions/ADR-010-tenant-dashboard.md), including what is deliberately a
      sentence rather than a screen

Deliberately not built here: maintenance requests (Phase 7), announcements (Phase 8), documents (Phase 6)
and payments taken through the site (Phase 11). Phase 5 adds no data of its own.

Review round, added while the phase was open (ADR-010 revision, ADR-011, ADR-012):

- [x] The greeting, the "Your home" eyebrow and the "thank you" copy are **removed** along with
      `RHP_DISPLAY_TIME_ZONE`; the header is a thin banner naming the unit and the property
- [x] A correction is **absorbed into the charge it corrects** for the tenant, so a cancelled charge reads
      "$0.00, nothing to pay" rather than a charge and an opposing credit
- [x] Paid money and credited money are shown separately, each charge states its own settlement
- [x] Charges and payments are **one statement**, paginated, instead of two disconnected boxes
- [x] The office's ledger, the audit trail and every balance are unchanged
- [x] The tenant's headline is **what is due now** — with how much of it is past due, and since when — not
      the remainder of the whole lease
- [x] **"Next rent due" is the incoming month**, dated from the lease when the office has not raised it yet,
      instead of the oldest unpaid month
- [x] What is billed but not yet due is **stated in a sentence**, never headlined; the office screens keep
      the whole balance, the age of the oldest unpaid charge, and what is coming due (ADR-012)

## Phase 6 — Document management

**Status note:** complete and in `main`. The decision is [ADR-022](decisions/ADR-022-documents.md) and the
working detail is in the [Phase 6 record](phases/phase-06-document-management.md).

Delivered: an app of its own (`apps/documents`) with one row per file — title, category, the file, the
name it arrived with, optional links to a tenancy, a property and a tenant, a document date, an office
note, and staff-only visibility unless the uploader ticks "the tenant can see this". The office gets the
list at `/manage/documents/` (search, category, visibility and property filters, 25 to a page) and the
upload screen, and the tenant gets `/lease/documents/`; every download is a permission-checked view,
never a media path. `documents/0002_lease_files_become_documents` turned each lease's single file into a
document row without moving it, and `leases/0010` dropped the old fields and routes. A document uploaded
in error can be removed by an admin, with a required note; superseded documents are kept alongside.

Uploads categorised (lease, addendum, notice, receipt, inspection, correspondence, other) and
attached to a lease, property, or tenant, with explicit tenant visibility and permission-checked
downloads that are never reachable by guessing a URL.

## Phase 7 — Maintenance system

Built and verified on `rhp-7`, accepted by the owner October 18, 2026 for local merge. The governing decision is
[ADR-023](decisions/ADR-023-maintenance.md); the [phase record](phases/phase-07-maintenance.md) preserves
all owner answers and verification evidence. Local baseline commits and merge are authorized; no push.

Tenant/property/unit requests, explicit tenancy sharing, assigned-worker access, seven work statuses,
entry permission, unresolved follow-up, immutable note revisions, private photos/invoices, reusable
vendors, append-only repair expenses, separately reviewed manual tenant recharges, and durable
after-commit email delivery attempts. Dashboards and property/unit pages link to scoped requests.
No financial liability is inferred, and existing occupancy/account locks remain authoritative.

## Phase 8 — Communications

Property-scoped announcements (water shutoff, inspections, parking, holidays) that appear only to the
intended tenants and expire correctly. E12 / P8-E1 adds bounded tenant–RHP messaging in approved scope;
owner decisions are resolved and implementation is owner-accepted for local merge after the
“Allow messages after move-out” wording correction. Recorded manual verification gaps remain explicit.
See the [Phase 8 record](phases/phase-08-communications.md).

## Phase 9 — Admin dashboard

Portfolio, rent, maintenance, and lease metrics where every number links to the records behind it —
no decorative analytics.

## Phase 10 — Reporting and search

Search across tenants, properties, units, and leases; reports for rent roll, balances due, payment
history, lease expirations, maintenance aging, and occupancy; CSV export first, PDF only where it
earns its keep.

## Phase 11 — Payment integration (approved, optional for 2027)

The owner approved one-time ACH and ACH autopay as desirable but not a launch blocker. Provider-hosted or
tokenized bank linking only; no card numbers, bank credentials, or raw account numbers in RHP. Provider
selection and implementation remain Phase 11 work.

## Phase 12 — Production hardening

HTTPS, secret management, database and media backups with a tested restore, audit logging, admin MFA,
brute-force mitigation, email configuration, monitoring, error reporting, file-upload restrictions,
log retention, privacy review, and disaster-recovery documentation — plus the security test battery
(tenant isolation, authorization bypass, document and attachment access, id enumeration, sessions).

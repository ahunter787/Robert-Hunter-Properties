# RHP roadmap

Derived from the governing specification in [`harness/master-spec.md`](harness/master-spec.md).
Work proceeds one phase at a time; a phase is complete only when its acceptance criteria and tests
pass.

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Foundation and architecture | **Complete** |
| 1 | Authentication and authorization | **Complete** |
| 2 | Property and tenant management | Not started |
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
| 2 | 2 + 3 | The real portfolio is modelled: properties, units, tenants, leases |
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

## Phase 2 — Property and tenant management

Management screens for properties, units, and tenants; admin dashboard counters (active properties,
occupied units, active tenants, open maintenance requests); property and unit detail pages.

## Phase 3 — Lease management

Lease creation and editing with draft/active/ended states, multiple tenants per lease, rent amount,
deposit, rent due day, dates, and lease document attachment. No electronic signatures yet.

## Phase 4 — Rent ledger

Recurring rent charges, manual charges, recorded payments, reversals and adjustments, and an
immutable, auditable ledger from which balances are derived. Statuses distinguish unpaid, partially
paid, paid, overdue, and pending. No card or bank credential storage, ever.

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

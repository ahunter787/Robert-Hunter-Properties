# RHP architecture

RHP is a **monolith**: one Django application, one PostgreSQL database, deployed with Docker
Compose. This is a deliberate choice (see [`decisions/ADR-001-monolith.md`](decisions/ADR-001-monolith.md)):
it is the smallest system that can safely hold tenant, lease, financial, and maintenance data for a
small property-management business, and it can move from a local VM to a cloud VPS unchanged.

**Status: Phase 2.** The foundation (configuration, database, container topology, health endpoint,
tests, design system), the identity layer (sign-in, roles, invitations, password reset, account page),
and the portfolio (properties and units) are in place. Domain apps arrive one phase at a time
([`roadmap.md`](roadmap.md)).

## System shape

```
                     development                              production
   ┌───────────────────────────────────────┐   ┌──────────────────────────────────────────┐
   │ docker compose up                     │   │ caddy :80/:443  (TLS, static files)      │
   │                                       │   │        │                                 │
   │  web :8000  (runserver, source mount) │   │        ▼                                 │
   │        │                              │   │  web  (gunicorn, config.wsgi)            │
   │        ▼                              │   │        │                                 │
   │  db :5432  (PostgreSQL 17, published) │   │        ▼                                 │
   └───────────────────────────────────────┘   │  db  (PostgreSQL 17, private network)    │
                                               └──────────────────────────────────────────┘
      volumes: pgdata, media_data                  volumes: pgdata, media_data, static_data,
                                                            caddy_data, caddy_config
```

- **web** — Django, serving server-rendered templates. Development runs `runserver` with the source
  tree bind-mounted; production runs gunicorn with 3 workers.
- **db** — PostgreSQL 17 on a named volume. Development publishes the port for host-side tooling;
  production keeps it private to the Compose network.
- **caddy** — production only. Terminates TLS, serves `/static/*` from the shared volume, and proxies
  everything else to gunicorn. It deliberately does **not** serve `/media`: tenant documents must pass
  Django permission checks (Phase 6).
- **Entry point** — `docker/entrypoint.sh` applies migrations (and collects static files for `web`)
  before starting the server, so a fresh stack comes up without manual steps.
- **Health** — `docker/healthcheck.py` polls `/healthz`, which returns 200 only when PostgreSQL
  answers `SELECT 1`.

## Request flow

```
browser → caddy (TLS, /static/*) → gunicorn → Django middleware → view → ORM → PostgreSQL
                                     │
                                     └── /healthz (unauthenticated readiness probe)
```

`SECURE_PROXY_SSL_HEADER` is enabled in production so Django knows the original request was HTTPS
while Caddy talks plain HTTP on the internal network. `config/settings/production.py` refuses to boot
if SSL redirection is on without that header (that combination produces an infinite redirect loop).

## Repository structure

```
config/                 project configuration
  settings/base.py        settings shared by every environment
  settings/development.py DEBUG, console email, verbose SQL logging
  settings/production.py  required secrets/hosts, HTTPS and cookie hardening
  urls.py views.py        routing; landing page and /healthz
  wsgi.py asgi.py         server entry points
apps/                   domain apps, one per phase
  accounts/               identity: user + roles, tenant profile, invitations, throttling (Phases 0-1)
  properties/             portfolio: properties and units (Phase 2)
  leases/                 tenancies: the lease desk and the tenant's lease (Phase 3)
  ledger/                 accounting: charges, payments, balances (Phase 4)
  audit/                  the audit trail: who changed what (Phase 4)
  common/                 shared, domain-neutral building blocks (form styling, dates, filters)
templates/              base layout, components/, account/, management/, tenancy/
assets/css/input.css    Tailwind v4 entry point and the RHP design tokens
static/                 build output only (static/css/rhp.css); gitignored
tests/                  pytest suite, runs against PostgreSQL
docker/                 container entrypoint and healthcheck
docs/                   this document and its siblings
```

Apps are created **when their phase begins**, never as empty placeholders. `apps/accounts` exists in
Phase 0 solely because `AUTH_USER_MODEL` cannot be changed after the first migration.

## Configuration

- Settings are split `base` → `development`/`production`; `DJANGO_SETTINGS_MODULE` selects one.
- All environment input goes through `django-environ`, seeded by a gitignored `.env`
  (`.env.example` documents every variable).
- Development has safe fallbacks so tests and a fresh checkout run without a `.env`. Production has
  no secret fallbacks: a missing key, a placeholder key, or an empty `ALLOWED_HOSTS` aborts the boot.
- `POSTGRES_HOST` defaults to `localhost` (host-side commands) and is overridden to `db` inside the
  container.

## Assets

Tailwind CSS v4 is the whole front-end build: `assets/css/input.css` defines the design tokens
(`@theme`) and component classes (`@layer components`), and compiles to `static/css/rhp.css`, which is
generated output and gitignored. The source lives outside `static/` so `collectstatic` only ever
publishes build output.

- Node is required only to build CSS. The Docker image builds it in a `node:22-alpine` stage and the
  runtime image is Python-only; `make assets` does the same on a workstation.
- There is no JavaScript application. Interactivity is added with HTMX and small progressive
  enhancements when a phase needs it.

## Design language

Professional property-management portal, not a SaaS marketing site: warm neutral surfaces, charcoal
text, restrained forest-green primary, muted gray structure, generous whitespace, restrained cards,
accessible contrast, and mobile-first single-column layouts for tenants. Desktop management screens
may use a left navigation; the tenant portal keeps a short navigation
(Dashboard, Lease, Payments, Maintenance, Documents, Announcements, Account).

## Identity, roles, and URL map

`accounts.User` carries one `role` field; Django's `is_staff`/`is_superuser` keep gating `/admin/`
while `role` gates the RHP portal (ADR-003). Staff-only views mix in a permission mixin from
`apps/accounts/permissions.py`; nothing relies on hidden navigation.

| Role | `/manage/` | Portfolio | Leases | Accounting | `/manage/accounts/` | Delete | Role changes | Tenant data |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `SUPERADMIN` | yes | yes | yes | yes | yes | yes | yes | all |
| `ADMIN` | yes | yes | yes | yes | yes | yes | no | all |
| `MANAGER` | yes | yes | yes | yes, but no reversals or adjustments (403) | read only | no (403) | no | all |
| `MAINTENANCE` | yes | no (403) | no (403) | no (403) | no (403) | no | no | assigned work only (Phase 7) |
| `TENANT` | no (403) | no (403) | own tenancy (`/lease/`) | own balance on that page only | no (403) | no | no | own tenancy only |

| URL | Surface |
| --- | --- |
| `/` | public landing page |
| `/healthz` | readiness probe (unauthenticated) |
| `/account/login/`, `/account/logout/` | sign-in (throttled) and sign-out (POST) |
| `/account/password-reset/…` | password reset (four steps, single-use link) |
| `/account/invite/<uidb64>/<token>/` | accept an invitation and set a password |
| `/account/profile/`, `/account/password/` | account page, contact details, password change |
| `/account/` | role-aware landing: staff → `/manage/`, tenant → `/account/profile/` |
| `/manage/` | staff landing page with the counters that role can use |
| `/manage/properties/…` | portfolio: list, create, detail, edit, take out of service, delete (admin) |
| `/manage/properties/<pk>/banner/` | the banner photo, served by a permission-checked view (never a public media path) |
| `/manage/units/…` | units the same way, attached to a property |
| `/manage/leases/…` | lease desk: list, create, detail, edit, activate/end (POST), delete a draft (admin) |
| `/manage/leases/<pk>/document/` | the signed lease, served by a permission-checked view |
| `/manage/ledger/` | accounting: balances across every live lease, with totals and an overdue filter |
| `/manage/ledger/leases/<pk>/` | one tenancy's ledger: charges, payments, activity and its recorded history |
| `/manage/ledger/leases/<pk>/rent-charges/` | generate the missing monthly rent charges (POST, idempotent) |
| `/manage/ledger/leases/<pk>/charges/new/`, `…/payments/new/` | add a charge, record a payment |
| `/manage/ledger/charges/<pk>/adjust/`, `…/payments/<pk>/reverse/` | corrections (admin only) |
| `/manage/ledger/payments/<pk>/clear/`, `…/void/` | move a pending payment to cleared or void (POST) |
| `/manage/accounts/…` | tenant accounts: read for managers, create/invite/deactivate/role/photo for admins |
| `/manage/accounts/<pk>/photo/`, `/account/photo/` | a tenant photo, served by a permission-checked view — the tenant's own URL carries **no id** |
| `/lease/`, `/lease/document/` | the tenant's own lease and its document — tenant-only, scoped, and the document URL carries **no id** |
| `/admin/` | Django back office (`is_staff` gate) |

Three URL modules sit under `/manage/` with **different namespaces** (`manage` for accounts, `portfolio`
for the portfolio, `leases` for the lease desk, `ledger` for accounting), and the tenant area has its own
(`tenancy`). One shared namespace would leave whichever module was included first unreachable through
`reverse()`.

Denials are deliberate: an authenticated user in the wrong *area* gets **403**, while an individual
record outside the caller's tenancy is resolved with `tenant_scope(...)` and returns **404**, so ids
cannot be probed.

## Conventions

- **Server-rendered templates first.** Add HTMX for interaction; no SPA.
- **Authorization in the view or queryset**, never in the template alone.
- **Money is `Decimal`**; financial history is corrected by reversal or adjustment, never edited.
- **Timestamps are timezone-aware UTC**; rent due dates are plain dates.
- **Logging** goes to stdout (console handler), level from `DJANGO_LOG_LEVEL`; no secrets or tenant
  PII in log messages.
- **Derived facts are computed in one place.** Occupancy is defined once, by `LeaseQuerySet.current()`,
  and every screen reads it; there is no stored occupancy column (ADR-007). The same holds for money:
  `apps.ledger.services.build_ledger` is the only definition of a balance or a charge's state, and
  there is no stored balance (ADR-008).
- **Append-only money.** A charge or payment is corrected by a reversal or an adjustment row, never
  edited or deleted, and every mutation appends an `AuditEvent` in the same transaction.
- **Tests** exercise behavior through the public HTTP surface and the ORM, against PostgreSQL.

## Not in Phase 4

The tenant dashboard (5), documents (6), maintenance (7), communications (8), the full admin dashboard
(9), reporting and a global audit browser (10), payment integration (11), production hardening — MFA,
monitoring, proxy-level rate limiting (12). The ledger stores no card or bank credential and never will;
recording a payment is a manual act until Phase 11 integrates a provider.

## The review round on Phase 4

Four changes landed on top of Phase 4 while the branch was open, all in earlier phases' screens:

- **The Residential/Commercial designation moved from the unit to the property** (ADR-006 revision):
  `Unit.unit_type` is gone, `Property.property_type` replaces it, and the residential rule for bedrooms
  and bathrooms follows the building. A property with such detail cannot be switched to commercial until
  it is cleared.
- **Units gained square feet and amenities**, with amenities drawn from a table staff maintain
  (retire, don't delete) rather than a fixed choice list.
- **`/manage/units/` is grouped by property** and pages by property (25 per page), so a building's units
  are never split across pages; the old Type column is now Square footage.
- **Tenant photos** (ADR-009): uploaded by an administrator on the account page, served only through
  permission-checked views, with an inline placeholder when there is none.

## What Phase 4 changed in earlier work

Phase 3 left one labeled panel ("Not here yet" on a lease) and one placeholder on the tenant page
("your balance arrives with Phase 4"), both of which are now real, and the staff landing page gained the
money counters it had deliberately refused to fake. Two small things in Phase 3 were tightened because
Phase 4 forced the question: `visible_lease_for` no longer shows a tenant a **draft** lease (an unsigned
draft is an offer, not an agreement, and it has no ledger), and the ledger panel on the lease page reads
the same service functions as the accounting screens rather than a second set of numbers. Nothing else
was reshaped: occupancy, roles, scoping and the portfolio model are used unchanged, and Phase 4 added no
new dependency.

## What Phase 3 changed in earlier work

Phase 2 left two panels labeled ("occupants and active leases" on a property, "Tenancy" on a unit) and
one counter pair (occupied/vacant) deliberately switched off, rather than showing a zero that would have
been a lie. Phase 3 filled them from the lease definition, and the property and unit screens now read
`Unit.current_lease`, `occupants`, `is_vacant` and `is_occupied` (ADR-007). Nothing in Phase 1 or 2 was
reshaped: roles, permissions, scoping and the portfolio model are used unchanged. Phase 3 added no new
dependency — lease documents reuse the upload validation and permission-checked serving that Phase 2's
banners established.

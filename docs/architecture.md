# RHP architecture

RHP is a **monolith**: one Django application, one PostgreSQL database, deployed with Docker
Compose. This is a deliberate choice (see [`decisions/ADR-001-monolith.md`](decisions/ADR-001-monolith.md)):
it is the smallest system that can safely hold tenant, lease, financial, and maintenance data for a
small property-management business, and it can move from a local VM to a cloud VPS unchanged.

**Status: Phase 0.** Only the foundation exists — configuration, database, container topology,
health endpoint, tests, and the design system. Domain apps arrive one phase at a time
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
  accounts/               Phase 0: custom user model only (ADR-002)
templates/              base layout, components/, pages/
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

## Conventions

- **Server-rendered templates first.** Add HTMX for interaction; no SPA.
- **Authorization in the view or queryset**, never in the template alone.
- **Money is `Decimal`**; financial history is corrected by reversal or adjustment, never edited.
- **Timestamps are timezone-aware UTC**; rent due dates are plain dates.
- **Logging** goes to stdout (console handler), level from `DJANGO_LOG_LEVEL`; no secrets or tenant
  PII in log messages.
- **Tests** exercise behaviour through the public HTTP surface and the ORM, against PostgreSQL.

## Not in Phase 0

Authentication flows and roles (Phase 1), properties/units/tenants (2), leases (3), the rent ledger
(4), tenant dashboard (5), documents (6), maintenance (7), communications (8), admin dashboard (9),
reporting (10), payment integration (11), production hardening (12).

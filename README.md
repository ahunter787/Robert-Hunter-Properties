# RHP — Robert Hunter Properties

Self-hosted property-management and tenant portal for Robert Hunter Properties:
tenants sign in to see their lease, rent due, payments, documents, and maintenance
requests; the RHP team manages properties, units, tenants, leases, balances, and
communication from one place.

The product specification, non-goals, and phased plan live in
[`docs/harness/master-spec.md`](docs/harness/master-spec.md) and
[`docs/roadmap.md`](docs/roadmap.md).

**Current status: Phase 3 (leases) — in review.** RHP models the properties and units it manages and now
the tenancies inside them: staff and tenants sign in, tenants are created by staff and invited, roles gate
every route server-side, the portfolio can be created, edited, and taken out of service, and a lease ties
a unit to its tenants with a term, rent, deposit and due day. Properties carry a map pin and a banner
photo; units are residential or commercial; tenants can read their own lease and its document. The rent
ledger, documents, and maintenance are still to come
([`docs/roadmap.md`](docs/roadmap.md)).

## Accounts and access

| Role | Reaches |
| --- | --- |
| `SUPERADMIN` | everything, including role changes and deletion |
| `ADMIN` | management area, tenant account administration, deletion |
| `MANAGER` | management area, the portfolio (properties and units), the lease desk, and reading tenant records |
| `MAINTENANCE` | management area (assigned work arrives in Phase 7) |
| `TENANT` | their own account, contact details, and their own lease |

| URL | What it is |
| --- | --- |
| `/account/login/` | sign-in for tenants and staff (rate limited) |
| `/account/profile/` | the account page: details, contact information, password change |
| `/account/invite/<uidb64>/<token>/` | where an invited tenant sets their password |
| `/manage/` | staff landing page with portfolio and occupancy counters |
| `/manage/properties/`, `/manage/units/` | the portfolio: create, edit, take out of service; delete is admin-only |
| `/manage/leases/` | the lease desk: create, edit, activate, end, and attach the signed lease; deleting a draft is admin-only |
| `/manage/accounts/` | tenant accounts: read for managers, create/invite/deactivate/role for admins |
| `/lease/` | a tenant's own lease: unit, term, rent, deposit, co-tenants and their document |
| `/admin/` | Django back office for superusers |

Create the first account with `make superuser`, then sign in at `/account/login/`. Invitations and
password resets are emailed; in development the console backend prints them to `make logs`.

Units are **residential** or **commercial**: bedrooms and bathrooms describe residential space, so they
are refused on a commercial unit and the unit page says "Not applicable" rather than "Not recorded". A
unit is named by its identifier with its property on the line below (`Storefront` / `- 910 Stark`).

A property can hold a **map pin** (paste a Google Maps link — full or shortened — or
`45.5231, -122.6765` on the edit form) and a **banner photo** (JPEG/PNG/WebP, up to `RHP_MAX_UPLOAD_MB`).
The map is a keyless Google embed unless `GOOGLE_MAPS_EMBED_API_KEY` is set; only a shortened link is
sent to Google for expansion (`RHP_RESOLVE_MAP_SHORT_LINKS=0` disables that).

A **lease** ties a unit to the people renting it: its term, monthly rent, deposit, rent due day, one
primary contact among its tenants, and the signed lease as a PDF or a scan. A unit can have only **one
active lease** — a database constraint, not a form rule — and a lease moves *draft* → *active* → *ended*
by explicit action, never because a date passed. Ended leases are read-only history; only a draft can be
deleted, and only by an admin. Tenants read their own lease at `/lease/`, whose document URL carries no
id and is served through a permission-checked view.

## Stack

| Layer | Choice |
| --- | --- |
| Application | Django 6.1 (server-rendered templates) |
| Database | PostgreSQL 17 |
| Server | gunicorn behind Caddy |
| Deployment | Docker Compose (local VM or cloud VPS) |
| Styles | Tailwind CSS v4, built at image-build time |
| Tests / lint | pytest + pytest-django, ruff |
| Python / deps | Python 3.14, managed with [uv](https://docs.astral.sh/uv/) |

## Quickstart

Requirements: Docker with the Compose v2 plugin, Python 3.14, `uv`, Node 22+ (CSS build only).

```bash
git clone git@github.com:ahunter787/Robert-Hunter-Properties.git
cd Robert-Hunter-Properties

make init          # .env + CSS assets + image + stack + migrations
make superuser     # create the first admin account
```

Then open <http://localhost:8000>. `make init` is idempotent: it never overwrites an existing `.env`.

### Common commands

```bash
make            # list every target
make up         # start the development stack in the background
make dev        # run the stack in the foreground
make logs       # follow application logs
make down       # stop the stack
make migrate    # apply migrations in the running container
make superuser  # create an admin account
make test       # pytest against the dev stack's PostgreSQL
make lint       # ruff check + format check
make health     # curl http://localhost:8000/healthz
```

### Running without Docker

```bash
make env
uv sync
make assets                      # needs Node
docker compose up -d db          # or any PostgreSQL reachable per .env
uv run python manage.py migrate
uv run python manage.py runserver
```

`POSTGRES_HOST` in `.env` defaults to `localhost` for host-side commands; the Docker stack
overrides it to `db` inside the `web` container.

### Production

```bash
make env                 # then edit .env: real DJANGO_SECRET_KEY, hosts, TLS, SMTP
make up-prod             # Caddy (TLS) + gunicorn + PostgreSQL
```

See [`docs/deployment.md`](docs/deployment.md) for the local-VM and cloud-VPS topologies, TLS,
backups, and the upgrade path.

## Workflow

`main` always holds a working release. Each phase is developed on its own branch — `rhp-1` for Phase 1,
`rhp-2` for Phase 2, and so on — with one commit per unit of work, and **squashed into `main`** once
`make test`, `make lint`, `make check`, and `make check-deploy` pass (`git merge --squash rhp-2`), so
`main` carries one reviewable commit per phase. The branch is deleted after the merge; its granular
history stays on GitHub until then. The full contract for contributors and agents is in
[`AGENTS.md`](AGENTS.md).

## Layout

```
config/          settings (base/development/production), urls, views, wsgi/asgi
apps/accounts/   identity: user + roles, tenant profile, invitations, throttling
apps/properties/ portfolio: properties and units (Phase 2)
apps/leases/     lease desk and the tenant's own lease (Phase 3)
apps/common/     shared building blocks (form styling, date formatting, filters)
templates/       account/, management/, tenancy/, components/, error pages, base layout
assets/css/      Tailwind entry point (built into static/css/rhp.css)
tests/           pytest suite (tests/accounts/, tests/properties/, tests/leases/)
docs/            architecture, database, deployment, security, roadmap, ADRs, harness spec
docker/          entrypoint and container healthcheck
```

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/phase-guide.md`](docs/phase-guide.md) | **Start here**: every phase in plain language, and what later phases will change |
| [`docs/architecture.md`](docs/architecture.md) | System shape, request flow, structure, conventions |
| [`docs/database.md`](docs/database.md) | Database configuration, migration rules, modelling conventions |
| [`docs/deployment.md`](docs/deployment.md) | Local VM and VPS topologies, TLS, backup/restore, upgrades |
| [`docs/security.md`](docs/security.md) | Authorization rules, secrets handling, upload safety |
| [`docs/roadmap.md`](docs/roadmap.md) | Phases 0–12 as a status checklist |
| [`docs/harness/master-spec.md`](docs/harness/master-spec.md) | The governing product specification |

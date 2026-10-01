# RHP — Robert Hunter Properties

Self-hosted property-management and tenant portal for Robert Hunter Properties:
tenants sign in to see their lease, rent due, payments, documents, and maintenance
requests; the RHP team manages properties, units, tenants, leases, balances, and
communication from one place.

The product specification, non-goals, and phased plan live in
[`docs/harness/master-spec.md`](docs/harness/master-spec.md) and
[`docs/roadmap.md`](docs/roadmap.md).

**Current status: Phase 2 (portfolio).** RHP now models the properties and units it manages, alongside
Phase 1's identity layer: staff and tenants sign in, tenants are created by staff and invited, roles
gate every route server-side, and the portfolio can be created, edited, and taken out of service.
Leases, the rent ledger, documents, and maintenance are still to come
([`docs/roadmap.md`](docs/roadmap.md)).

## Accounts and access

| Role | Reaches |
| --- | --- |
| `SUPERADMIN` | everything, including role changes and deletion |
| `ADMIN` | management area, tenant account administration, deletion |
| `MANAGER` | management area, the portfolio (properties and units), and reading tenant records |
| `MAINTENANCE` | management area (assigned work arrives in Phase 7) |
| `TENANT` | their own account and contact details |

| URL | What it is |
| --- | --- |
| `/account/login/` | sign-in for tenants and staff (rate limited) |
| `/account/profile/` | the account page: details, contact information, password change |
| `/account/invite/<uidb64>/<token>/` | where an invited tenant sets their password |
| `/manage/` | staff landing page with portfolio counters |
| `/manage/properties/`, `/manage/units/` | the portfolio: create, edit, take out of service; delete is admin-only |
| `/manage/accounts/` | tenant accounts: read for managers, create/invite/deactivate/role for admins |
| `/admin/` | Django back office for superusers |

Create the first account with `make superuser`, then sign in at `/account/login/`. Invitations and
password resets are emailed; in development the console backend prints them to `make logs`.

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
apps/common/     shared building blocks (form styling)
templates/       account/, management/, components/, error pages, base layout
assets/css/      Tailwind entry point (built into static/css/rhp.css)
tests/           pytest suite (tests/accounts/, tests/properties/)
docs/            architecture, database, deployment, security, roadmap, ADRs, harness spec
docker/          entrypoint and container healthcheck
```

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/architecture.md`](docs/architecture.md) | System shape, request flow, structure, conventions |
| [`docs/database.md`](docs/database.md) | Database configuration, migration rules, modelling conventions |
| [`docs/deployment.md`](docs/deployment.md) | Local VM and VPS topologies, TLS, backup/restore, upgrades |
| [`docs/security.md`](docs/security.md) | Authorization rules, secrets handling, upload safety |
| [`docs/roadmap.md`](docs/roadmap.md) | Phases 0–12, milestones, current status |
| [`docs/harness/master-spec.md`](docs/harness/master-spec.md) | The governing product specification |

# RHP — Robert Hunter Properties

Self-hosted property-management and tenant portal for Robert Hunter Properties:
tenants sign in to see their lease, rent due, payments, documents, and maintenance
requests; the RHP team manages properties, units, tenants, leases, balances, and
communication from one place.

The product specification, non-goals, and phased plan live in
[`docs/harness/master-spec.md`](docs/harness/master-spec.md) and
[`docs/roadmap.md`](docs/roadmap.md).

**Current status: Phase 5 (the tenant dashboard) is complete; Phase 6 (documents) is next.** RHP models the
properties and units it manages, the tenancies inside them, and the money: staff and tenants sign in,
tenants are created by staff and invited, roles gate every route server-side, the portfolio can be
created, edited, and taken out of service, and a lease ties a unit to its tenants with a term, rent,
deposit and due day. On top of that sits the ledger — rent charges, one-off charges, recorded payments,
reversals and adjustments, and a balance derived from the entries rather than stored — and the tenant's
own pages at `/account/`, `/lease/` and `/payments/` say what is due now, what is past due, and what is
coming due. Extension **E1** adds RHP's own lease shapes — fixed, step up, and triple net — with a stepped
term's rent worked out when the lease is activated and an NNN amount staged each year
([`docs/extensions.md`](docs/extensions.md)).
Properties carry a map pin and a banner photo; units are residential or commercial. Documents and
maintenance are still to come ([`docs/roadmap.md`](docs/roadmap.md)).

## Accounts and access

| Role | Reaches |
| --- | --- |
| `SUPERADMIN` | everything, including role changes and deletion |
| `ADMIN` | management area, tenant account administration, deletion, reversals and adjustments |
| `MANAGER` | management area, the portfolio (properties and units), the lease desk, the ledger, and reading tenant records |
| `MAINTENANCE` | management area (assigned work arrives in Phase 7) |
| `TENANT` | their own account, contact details, their own lease, and their own balance |

| URL | What it is |
| --- | --- |
| `/account/login/` | sign-in for tenants and staff (rate limited) |
| `/account/profile/` | the account page: details, contact information, password change |
| `/account/invite/<uidb64>/<token>/` | where an invited tenant sets their password |
| `/manage/` | staff landing page with portfolio, occupancy and money counters |
| `/manage/properties/`, `/manage/units/` | the portfolio: create, edit, take out of service; delete is admin-only |
| `/manage/leases/` | the lease desk: create, edit, activate, end, and attach the signed lease; deleting a draft is admin-only |
| `/manage/ledger/` | accounting: each live lease's balance, what is past due, and what is coming due; each lease has its own ledger |
| `/manage/accounts/` | tenant accounts: read for managers, create/invite/deactivate/role/photo for admins |
| `/account/` | where a tenant lands: what is due now, the next rent, the lease end date, recent activity and quick actions |
| `/lease/` | a tenant's own lease: unit, term, rent, deposit, co-tenants, their document, and what they owe now |
| `/payments/` | a tenant's own statement: what each charge costs now, what is paid, and what is left |
| `/admin/` | Django back office for superusers |

Create the first account with `make superuser`, then sign in at `/account/login/`. Invitations and
password resets are emailed; in development the console backend prints them to `make logs`.

A **property** is residential or commercial, and its units inherit that: bedrooms and bathrooms
describe residential space, so they are refused for a unit in a commercial property and the unit page
says "Not applicable" rather than "Not recorded". A property with such detail cannot be switched to
commercial until it is cleared. A unit is named by its identifier with its property on the line below
(`Storefront` / `- 910 Stark`), may record its **square footage** and any **amenities** (from a list
staff maintain in the back office), and the unit list at `/manage/units/` is grouped by property.

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

A tenant's own portal is three pages — the **dashboard** at `/account/` (a thin banner naming the unit and
building, then the balance, next rent due and lease end date), the **lease**, and the **statement** at
`/payments/` — built mobile-first: one column, full-width buttons, and list rows rather than tables. The
statement shows each charge at what it costs **now**, with any correction absorbed into it rather than as
a separate opposing amount, and states what has been paid against it.

The **ledger** records what happened to the money: rent charges generated one month at a time (never
twice for the same month, never beyond the tenancy's term), one-off charges, payments recorded as
cleared or pending, and corrections as reversals and adjustments. Nothing is edited or deleted — a
mistake is a new entry that names the one it corrects — and the balance is derived from the entries
every time it is shown, so the ledger and the balance cannot disagree. Managers record money;
reversals and adjustments are admin-only. Every change is written to an audit trail in the same
transaction, visible as the History panel on a lease's ledger (ADR-008).

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

**Testing from a phone.** The dev stack binds every interface, so the same server is reachable from
another device on your network — find the address with `hostname -I` and open `http://<address>:8000`.
Development settings accept any host (`DJANGO_ALLOWED_HOSTS=*`), which is what makes a DHCP address work;
production refuses to boot without an explicit list, so nothing about this reaches a real deployment.
Sign-in works over that address too, because Django checks the origin against the host it was reached on.

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
apps/ledger/     accounting: charges, payments, balances (Phase 4)
apps/audit/      the audit trail: who changed what (Phase 4)
apps/common/     shared building blocks (form styling, dates, filters)
templates/       account/, management/, tenancy/, components/, error pages, base layout
assets/css/      Tailwind entry point (built into static/css/rhp.css)
tests/           pytest suite (tests/accounts/, tests/properties/, tests/leases/, tests/ledger/, tests/audit/)
docs/            architecture, database, deployment, security, roadmap, ADRs, harness spec
docker/          entrypoint and container healthcheck
```

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/phase-guide.md`](docs/phase-guide.md) | **Start here**: every phase in plain language, and what later phases will change |
| [`docs/architecture.md`](docs/architecture.md) | System shape, request flow, structure, conventions |
| [`docs/database.md`](docs/database.md) | Database configuration, migration rules, modeling conventions |
| [`docs/deployment.md`](docs/deployment.md) | Local VM and VPS topologies, TLS, backup/restore, upgrades |
| [`docs/security.md`](docs/security.md) | Authorization rules, secrets handling, upload safety |
| [`docs/roadmap.md`](docs/roadmap.md) | Phases 0–12 as a status checklist |
| [`docs/extensions.md`](docs/extensions.md) | Additions to the specification that are not phases: the register of proposals, with the owner's decisions |
| [`docs/harness/master-spec.md`](docs/harness/master-spec.md) | The governing product specification |

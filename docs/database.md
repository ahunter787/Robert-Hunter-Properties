# Database

PostgreSQL 17, accessed through the Django ORM. There is exactly one database and no cross-database
joins, no stored procedures, and no ORM bypass without a comment explaining why.

## Configuration

Connection settings come from the environment (`config/settings/base.py`):

| Variable | Default | Notes |
| --- | --- | --- |
| `POSTGRES_DB` | `rhp` | Database name |
| `POSTGRES_USER` | `rhp` | Application role — not a superuser |
| `POSTGRES_PASSWORD` | *(none)* | Required in every real environment |
| `POSTGRES_HOST` | `localhost` | Compose sets `db` inside the container |
| `POSTGRES_PORT` | `5432` | |
| `DB_CONN_MAX_AGE` | `60` | Persistent connections; raise if the DB allows more |

`connect_timeout` is 5 seconds so a stuck database fails loudly instead of hanging a worker.

## Persistence

PostgreSQL data lives on the named volume `pgdata` in both stacks, so `docker compose restart db`,
`docker compose up -d` and image rebuilds all preserve it.

> `docker compose down -v` **deletes `pgdata`**. That is the intended way to reset a development
> database and a catastrophic mistake in production. Use `make down` (no `-v`) for routine stops.

## Migrations

- A model change is never complete without its migration: `make migrations`, review the generated
  file, then `make migrate`.
- Migrations are part of the phase that introduces them and are reviewed like code.
- CI fails on drift: `python manage.py makemigrations --check --dry-run`.
- Applied migrations are never edited. Corrections are new migrations.
- The container entrypoint runs `migrate --noinput` on start, so a deploy never serves code against
  an older schema.
- `AUTH_USER_MODEL` is fixed in Phase 0 (`accounts.User`). Migrations for `accounts` run before any
  real data exists; see [`decisions/ADR-002-custom-user.md`](decisions/ADR-002-custom-user.md).

## Identity tables (Phase 1)

| Table | Purpose | Notes |
| --- | --- | --- |
| `accounts_user` | accounts, including the `role` column | indexed `role`; the `AUTH_USER_MODEL` |
| `accounts_tenantprofile` | tenant contact details | one-to-one with the user; `notes` is staff-only and never rendered to a tenant |
| `accounts_loginattempt` | login-throttle ledger | composite indexes on `(username, created_at)` and `(ip, created_at)`; rows older than 24 h are pruned as new ones are written |

Role changes, account creation, deactivation, and invitations are written to the application log as
structured events. The audit-event **table** arrives in Phase 2 with the portfolio models, so Phase 1
does not half-build it.

## Portfolio tables (Phase 2)

| Table | Purpose | Notes |
| --- | --- | --- |
| `properties_property` | a building RHP manages | `UniqueConstraint(Lower("name"))` (case-insensitive), indexed `is_active`; the address itself is not unique |
| `properties_unit` | a rentable unit inside a property | `UniqueConstraint(property, identifier)`; `property` is a FK with **`on_delete=PROTECT`**, so a property with units cannot be deleted |

The unit counts on the property list come from `Count()` annotations, not from a stored column, so they
cannot drift away from the rows.

## Modelling conventions

These are binding for the phases that follow (Phases 2–11):

- **Primary keys**: `BigAutoField` internally. Any resource exposed in a URL that a tenant or an
  outsider could enumerate (documents, maintenance requests, lease documents) uses a `UUIDField`
  instead of a sequential id.
- **Money**: `DecimalField(max_digits=12, decimal_places=2)`. Never `FloatField`. Amounts are stored
  positive with an explicit direction (charge vs payment), not as signed floats.
- **Dates**: `DateField` for business dates (rent due day, lease start/end, payment date).
  `DateTimeField` for events, always timezone-aware UTC.
- **Financial immutability**: charges and payments are append-only. A mistake is corrected with a
  reversal or adjustment row, and the original stays visible. Nothing recalculates history in place.
- **Status fields**: `CharField` with `TextChoices` and database-level `choices` — explicit, greppable,
  and safe to migrate.
- **Deactivation over deletion**: properties, units, tenants, and leases use an `is_active` (or
  status) field. Deletes are reserved for mistakes and draft data, and destructive operations in the
  UI require confirmation.
- **Audit trail**: important state transitions (lease status, charges, payments, role changes) write
  an audit event (actor, action, object type and id, timestamp, small metadata payload).
- **Indexes**: every foreign key used for filtering gets an index; add indexes for the columns the
  real screens filter on (status, due date, property, lease).
- **Constraints**: uniqueness as a database constraint where it is a real invariant
  (`unit` per `property`, `lease_tenant` per `lease`), not only in application code.
- **Tenant scoping is a query concern**: models do not carry "who may see me" logic; the view or a
  manager method applies the authorization scope (see [`security.md`](security.md)).

## Testing

`pytest-django` creates the `test_<POSTGRES_DB>` database against the same PostgreSQL server, so
tests run on the same dialect, constraints, and `Decimal` semantics as production. Development
publishes port 5432 for exactly this reason; use `--reuse-db` locally for speed.

## Backups

`pg_dump` plus a media archive, stored off the machine, with a restore that has actually been
practised — see [`deployment.md`](deployment.md). Backup automation and retention are completed in
Phase 12, before real tenant data is loaded.

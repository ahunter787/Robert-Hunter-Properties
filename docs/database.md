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
| `accounts_tenantprofile` | tenant contact details | one-to-one with the user; `notes` is staff-only and never rendered to a tenant; `photo` holds `tenant_photos/<uuid><ext>`, served only by a permission-checked view (ADR-009) |
| `accounts_loginattempt` | login-throttle ledger | composite indexes on `(username, created_at)` and `(ip, created_at)`; rows older than 24 h are pruned as new ones are written |

Role changes, account creation, deactivation, and invitations are written to the application log as
structured events. The audit-event **table** arrives in Phase 2 with the portfolio models, so Phase 1
does not half-build it.

## Portfolio tables (Phase 2)

| Table | Purpose | Notes |
| --- | --- | --- |
| `properties_property` | a building RHP manages | `UniqueConstraint(Lower("name"))` (case-insensitive), indexed `is_active` and `property_type`; the address itself is not unique. Also holds the map pin (`latitude`, `longitude` — `Decimal(9,6)`, nullable) and the banner image path. **`property_type`** (Residential/Commercial) lives here, not on the unit (ADR-006 revision) |
| `properties_unit` | a rentable unit inside a property | `UniqueConstraint(property, identifier)`; `property` is a FK with **`on_delete=PROTECT`**, so a property with units cannot be deleted; `square_feet` is a nullable `PositiveIntegerField` (blank = not recorded); `amenities` is a many-to-many to `properties_amenity` |
| `properties_amenity` | something a unit offers | `name` unique, indexed `is_active`; amenities in use are **retired, not deleted**, because deleting one removes it from every unit that had it. Seeded by the same migration with seventeen common amenities |

The unit counts on the property list come from `Count()` annotations, not from a stored column, so they
cannot drift away from the rows.

**Uploads.** A banner lives in `MEDIA_ROOT` (the `media_data` volume) under a randomised filename in
`property_banners/`, never the client's name. A tenant photo lives in `tenant_photos/` under the same
rules. Both are served by permission-checked views, not by a public media path — `MEDIA_URL` is only
wired up in development — and both use the one validator in `apps/common/images.py`. An image upload
requires Pillow, which is why it is a runtime dependency (ADR-006, ADR-009).

## Lease tables (Phase 3)

| Table | Purpose | Notes |
| --- | --- | --- |
| `leases_lease` | one tenancy of one unit | `UniqueConstraint(unit, condition=status='ACTIVE')` — `one_active_lease_per_unit`; `CheckConstraint(end_date >= start_date)` — `lease_ends_on_or_after_it_starts`; `unit` is a FK with **`on_delete=PROTECT`**, so a unit with history cannot be deleted; indexed `(status, end_date)`. `monthly_rent` and `deposit` are `Decimal(12,2)`; `rent_due_day` is 1–31; `lease_file` holds `lease_documents/<uuid><ext>` |
| `leases_leasetenant` | the people on a lease | `UniqueConstraint(lease, tenant)` and `UniqueConstraint(lease, condition=is_primary=True)` — one primary contact per lease; `lease` is **`CASCADE`**, `tenant` is **`PROTECT`**, so a person with tenancy history cannot be deleted |

**Occupancy is derived, never stored.** There is no `is_occupied` column: a unit is occupied while an
active lease's term covers today, computed by `LeaseQuerySet.current()`. `Unit.current_lease`,
`Unit.occupants`, `Unit.is_vacant` and `Unit.is_occupied` all read that one definition (ADR-007).
A unit that is out of service is a third state — neither occupied nor vacant.

**Uploads.** A lease document lives in `MEDIA_ROOT` (the `media_data` volume) under a randomised
filename in `lease_documents/`, is validated for size and type, and is served only by a
permission-checked view (`LeaseDocumentView` for staff, `TenantLeaseDocumentView` for the tenant on that
lease). Replacing it, or deleting the lease, deletes the stored file.

## Ledger and audit tables (Phase 4)

| Table | Purpose | Notes |
| --- | --- | --- |
| `ledger_charge` | something a tenancy was charged for | `CheckConstraint(amount >= 0.01)`; `CheckConstraint(kind='ADJUSTMENT' OR direction='INCREASE')` — `only_adjustments_reduce_a_charge`; `UniqueConstraint(lease, due_date, condition=kind='RENT')` — `one_rent_charge_per_month`, which makes rent generation idempotent in the database; `unit`-style `PROTECT` to `leases_lease`; indexed `(lease, due_date)` and `(kind, due_date)`. A reduction requires `adjusts` (the charge it corrects) and a `reason` |
| `ledger_payment` | money received, or the reversal of it | `CheckConstraint(amount >= 0.01)`; `CheckConstraint(kind='RECEIVED' AND reverses IS NULL OR kind='REVERSAL' AND reverses IS NOT NULL)`; `reverses` is a `OneToOneField` to itself, so a payment is reversed once; `PROTECT` to `leases_lease`; indexed `(lease, payment_date)` and `(status, payment_date)` |
| `audit_audit_event` | who changed what, and when | `actor` (`SET_NULL`), `lease` (`SET_NULL`), `action`, `object_type`/`object_id`, `summary`, a small JSON `metadata`, `created_at`; indexed on `(object_type, object_id)`, `(lease, created_at)`, `(action, created_at)` and `created_at` |

**The balance is derived, never stored.** There is no `balance` column and no stored charge status:
`apps.ledger.services.build_ledger` computes both from the entries — `Σ charge.balance_effect − Σ
cleared unreversed payments` — and the staff ledger, the tenant page, the lease panel and the landing
counters all read that one definition (ADR-008). Clearing payments settle charges oldest-first; a
reducing adjustment settles the charge it corrects.

**Append-only.** `Charge.save()` and `Payment.save()` refuse to change a financial field once written
(the only permitted change is `PENDING → CLEARED`/`VOID` on a payment), `delete()` raises on both, and
`AuditEvent` refuses updates and deletions. A mistake is a reversal or an adjustment row, so the
original stays visible. `Charge`/`Payment` are registered read-only in the Django admin.

**Money in the audit trail** is stored as a string in `metadata`, for the same reason money is
`DecimalField` everywhere else: a float in an audit row is still a float.

## Modeling conventions

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

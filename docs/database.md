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
rules. Both are served by permission-checked views, not by a public media path, even in development,
and both use the one validator in `apps/common/images.py`. An image upload
requires Pillow, which is why it is a runtime dependency (ADR-006, ADR-009).

## Lease tables (Phase 3)

| Table | Purpose | Notes |
| --- | --- | --- |
| `leases_lease` | one tenancy of one unit and its financial-account state | `UniqueConstraint(unit, condition=status='ACTIVE')` — `one_active_lease_per_unit`; `CheckConstraint(end_date >= start_date)`; `CheckConstraint(account_status='OPEN' OR (account_status='SETTLED' AND status='ENDED' AND settled_at IS NOT NULL))`; `unit` is a FK with **`on_delete=PROTECT`**, so a unit with history cannot be deleted; indexed `(status, end_date)`. Occupancy is `DRAFT`/`ACTIVE`/`ENDED`; `account_status` is `OPEN`/`SETTLED`; current settlement metadata is `settled_at`, `settled_by`, and `settlement_note`. `monthly_rent` and `deposit` are `Decimal(12,2)`. Its document is now a row in `documents_document` (Phase 6, ADR-022) |
| `leases_leasetenant` | the people on a lease | `UniqueConstraint(lease, tenant)` and `UniqueConstraint(lease, condition=is_primary=True)` — one primary contact per lease; `lease` is **`CASCADE`**, `tenant` is **`PROTECT`**, so a person with tenancy history cannot be deleted |

**Occupancy is derived, never stored.** There is no `is_occupied` column: a unit is occupied while an
active lease's term covers today, computed by `LeaseQuerySet.current()`. `Unit.current_lease`,
`Unit.occupants`, `Unit.is_vacant` and `Unit.is_occupied` all read that one definition (ADR-007).
A unit that is out of service is a third state — neither occupied nor vacant.

**Uploads.** A lease's document is a `documents_document` row now: `apps/documents/models.py` stores the
file under a randomised name in `documents/<uuid4hex><ext>` (the `media_data` volume), keeps the name it
arrived with in `original_name`, and carries the readable `title`. It is validated for size and type by
`apps/common/files.py::validate_document_upload` and served only by a permission-checked view
(`DocumentDownloadView` for staff, `TenantDocumentDownloadView` for the tenant, scoped by
`Document.objects.visible_to`). The migration `documents/0002_lease_files_become_documents` turned each
old `Lease.lease_file` into such a row without moving the file, and `leases/0010` dropped `lease_file`
and `lease_document_name` (ADR-022).

## Document table (Phase 6)

| Table | Purpose | Notes |
| --- | --- | --- |
| `documents_document` | one uploaded file, and who may see it | `title`; `category` (`LEASE`/`ADDENDUM`/`NOTICE`/`RECEIPT`/`INSPECTION`/`CORRESPONDENCE`/`OTHER`); `file` under `documents/<uuid4hex><ext>`; `original_name`; optional `lease`, `property`, `tenant` — all **`PROTECT`**, and `clean()` requires at least one; `tenant_visible` default `False`; `document_date`; `note`; `uploaded_by` (**`SET_NULL`**); `created_at`; indexed `(category, created_at)` and `(tenant_visible, created_at)` (ADR-022) |

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

## Maintenance tables (Phase 7, ADR-023)

All ten tables use integer primary keys for audit compatibility. `maintenance_maintenancerequest`
and `maintenance_attachment` also have unique public UUIDs used in their URLs.

| Table | Purpose and constraints |
| --- | --- |
| `maintenance_maintenancerequest` | Physical property/unit location, separate reporting lease/reporter, assignment, priority, seven statuses, schedule and concurrency revision. Scheduled work requires a date/time or time window. No deletion interface. |
| `maintenance_audience` | Unique request/lease audience, entry permission with actor/time, unresolved follow-up flag. Sharing never follows a unit's new occupants. |
| `maintenance_update` | Chronological internal note (null lease) or tenancy-specific conversation. Audience and identity cannot be edited; publication creates a separate row. |
| `maintenance_revision` | Append-only previous text, correcting actor, reason and timestamp. Never projected into tenant views. |
| `maintenance_attachment` | Exactly one update or cost parent; randomized stored name, readable original name, public UUID and retained administrative-removal metadata. |
| `maintenance_vendor` | Reusable contact/trades/active state; protected references retain used vendors. |
| `maintenance_cost` | Positive `Decimal(12,2)` expenses and signed-effect corrections linked to the original cost. No stored totals or balances. |
| `maintenance_recharge` | Immutable cost/lease/charge link; unique cost/batch/lease and one-to-one ledger charge make reviewed confirmation idempotent. Net recoveries include ledger adjustments. |
| `maintenance_notification` | Unique update/recipient delivery state and attempt count; fresh authorization before sending, after commit. |
| `maintenance_notificationattempt` | Append-only outcomes, safe error summaries and timestamps; failed attempts remain after successful retry. |

Phase 7 adds tables and audit-action choices only: existing leases, documents and ledger entries are
not transformed. Request-row and lease-row locks bind a signed recharge review to current data;
tenant charges still go through the existing ledger service and account-state guards.

## Modeling conventions

These are binding for the phases that follow (Phases 2–11):

- **Primary keys**: `BigAutoField` internally. A resource exposed in a URL that a tenant or an
  outsider could enumerate (maintenance requests, attachments) uses a `UUIDField` instead of a
  sequential id where the surface can afford it. **Documents are the deliberate exception** (ADR-022):
  a `Document` keeps its integer id and its tenant-facing download URL carries it, because the control
  is the tenancy scope rather than the id — `Document.objects.visible_to` returns nothing for another
  tenancy's row, so the view answers 404.
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

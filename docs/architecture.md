# RHP architecture

## Financial clarity — October 20, 2026 checkpoint

The two staff lease financial entry routes share the lease workspace template and view context.
A read-only presentation projection consumes an already-authorized `LeaseLedger` for staff and
tenant summaries. It distinguishes posted future charges from scheduled unposted rent, without
storing balances, querying a wider tenancy scope or changing allocation/payment services.
Financial amount styles are separate from maintenance states and unit-identification colors.
Entry/correction form propagation follows owner review of the shared reading surface.
The narrow existing-history recovery uses the existing onboarding URL, a signed 30-minute
manager-bound review and a lease-row lock. It changes only the missing billing start date and
appends an audit event; it never creates a receipt, opening balance or duplicate charges.
The shared `bill_history` projection groups all corrected charges by exact due date into
expandable bills, with separate payment records. `StatementMonth` retains its compatibility name
but represents a due-date bill, including one-time charges and single-component bills. Payment
progress is displayed only for the combined bill. Full-history running balances are calculated
before filtering/pagination; bills precede payments on shared dates. Tenant templates omit private
correction reasons and staff controls. No stored invoice, allocation-rule change or migration exists.

RHP is a **monolith**: one Django application, one PostgreSQL database, deployed with Docker
Compose. This is a deliberate choice (see [`decisions/ADR-001-monolith.md`](decisions/ADR-001-monolith.md)):
it is the smallest system that can safely hold tenant, lease, financial, and maintenance data for a
small property-management business, and it can move from a local VM to a cloud VPS unchanged.

**Status: Phase 7, E11 and Phase 8 owner-accepted for the local baseline.** Identity, portfolio,
leases, the rent ledger, tenant pages and documents are established; maintenance adds private
tenancy conversations, assigned work, repair expenses and reviewed recharges. Domain apps arrive one phase at a time
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
  everything else to gunicorn. It deliberately does **not** serve `/media`: every uploaded document and
  photo passes a Django permission check before its bytes are returned
  ([ADR-022](decisions/ADR-022-documents.md)).
- **Entry point** — `docker/entrypoint.sh` applies migrations (and collects static files for `web`)
  before starting the server, so a fresh stack comes up without manual steps.
- **Health** — `docker/healthcheck.py` polls `/healthz`, which returns 200 only when PostgreSQL
  answers `SELECT 1`.

## Request flow

Phase 9 centralizes read-only dashboard projections and metric detail populations. It reuses ledger
arithmetic, effective payments and lease occupancy, with no stored summaries. Activity reads the
existing audit table through a role-scoped, bulk-resolved projection; raw metadata is not rendered.
See ADR-025. Existing tenant and assigned-worker dashboards remain independent.

Phase 7 adds `apps/maintenance`: physical requests, explicit tenancy audiences, scoped
timeline updates and attachments, vendors, immutable cost entries and ledger recharge links.
An integer identity integrates with audit events while public routes use UUIDs. Request
locks serialize mutations and signed recharge reviews. Notification rows persist delivery
attempts and are dispatched after commit without another service. See ADR-023.

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
  accounting/             property accounting: chart, journals, banks, reconciliation (E10, in design)
  audit/                  the audit trail: who changed what (Phase 4)
  documents/              documents: one row per uploaded file, and its screens (Phase 6)
  communications/         fixed-participant messages, announcement snapshots and email attempts (Phase 8)
  maintenance/            requests, private conversations, work, costs, recharge reviews and email (Phase 7)
  common/                 shared, domain-neutral building blocks (form styling, dates, filters, the file rules)
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
  enhancements when a phase needs it. **HTMX is installed as of the share calculator** (2026-10-15):
  version **2.0.4**, vendored (committed) at `static/js/htmx.min.js` — the project static directory
  `STATICFILES_DIRS` already serves, so `collectstatic` publishes it and no build step is involved — with
  its upstream hash recorded in the file's banner. `static/css/rhp.css` stays generated and
  gitignored. The October 16 calculator correction replaces the cascade with a stateless
  bill-details → allocation → signed review flow (ADR-014). A small first-party script at
  `static/js/expense-allocation.js` tracks the input basis and requests server-calculated previews;
  aborts and revision checks discard stale responses. Every action also works through a plain
  form submission. All money arithmetic remains in Python. Only a final, validated review writes;
  the responsibility row serializes allocation saves and expense-charge generation so posted
  history cannot race an allocation edit. Review signatures include the saved allocation, unit
  roster, bill and tenancy facts, and bind the reviewed cents to the acting manager.

Phase 8 implementation uses `apps/communications`, not maintenance Update/Attachment records.
Fixed conversation participants and announcement recipient snapshots define tenant scope. PostgreSQL
locks protect sends, lifecycle changes, read positions and signed publication reviews. Durable email
intent dispatches after commit with per-attempt outcomes; no queue/realtime dependency. See ADR-024.

## Design language

The owner-approved [E11 application migration](design/implementation.md) replaces the shared shell
and Properties first, with owner review before other record layouts. Sources and printable vector
artifacts live under `docs/design/`, with scoped review copies in Outline's Design collection.
The project diagram skill is development tooling only; no new application dependency is added.

Navigation context is validated URL/session state, never authorization. Properties retains a
property/unit navigator and scoped sections. Optional unit photos use existing validation,
randomized storage and permission-checked views. Tenant images resolve the same visible lease
as the tenant portal, never a submitted unit id. Old unit images are removed after commit;
failed writes clean up newly stored bytes.

The owner accepted Properties and approved continuing E11. Lease records now have a local
section navigator, with the financial workspace as the default and Terms, Rent schedule, Tenants
and Documents as addressable sections. The lease and ledger routes share one transaction-content
template and the existing ledger service; no parallel balance or correction arithmetic exists.
Allocation SVG geometry is derived from the authoritative worksheet using Decimal; stable unit
identity chooses colors shared by ring segments, legend and fields. Invalid/over-allocated and
zero bills do not display a valid-looking percentage ring. Colors supplement numeric labels.

The remaining E11 records use a small shared section-navigation projection. Accounts resolve their
own lease memberships; no cross-lease balance is introduced. Maintenance first authorizes the UUID
request, then validates conversation Audience IDs within that request and the actor's scope. A selected
former tenancy never borrows another membership's write eligibility. Work/status displays project
existing Update kinds; no history is parsed into new records. Repair costs, delivery and raw audit
summaries remain manager-only, and workers receive no general location-photo endpoint. Recovery
navigation validates property/unit context against the cycle; operational calculator services remain
unchanged. Document property filters include lease-linked records, with unit context independently
validated. Query parameters remain navigation state, not authorization.

Professional property-management portal, not a SaaS marketing site: warm neutral surfaces, charcoal
text, restrained forest-green primary, muted gray structure, generous whitespace, restrained cards,
accessible contrast, and mobile-first single-column layouts for tenants. Desktop management screens
may use a left navigation; the tenant portal keeps a short navigation
(Dashboard, Lease, Payments, Maintenance, Documents, Announcements, Account).

## Identity, roles, and URL map

`accounts.User` carries one `role` field; Django's `is_staff`/`is_superuser` keep gating `/admin/`
while `role` gates the RHP portal (ADR-003). Staff-only views mix in a permission mixin from
`apps/accounts/permissions.py`; nothing relies on hidden navigation.

| Role | `/manage/` | Portfolio | Leases | Rent & Payments | `/manage/accounts/` | Delete | Role changes | Tenant data |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `SUPERADMIN` | yes | yes | yes | yes | yes | yes | yes | all |
| `ADMIN` | yes | yes | yes | yes | yes | yes | no | all |
| `MANAGER` | yes | yes | yes | yes, including corrections, settlement, and reopening | operational, including invitations and activation | no (403) | no | all |
| `MAINTENANCE` | yes | no (403) | no (403) | no (403) | no (403) | no | no | assigned work only (Phase 7) |
| `TENANT` | no (403) | no (403) | own tenancy (`/lease/`) | own statement (`/payments/`) | no (403) | no | no | own tenancy only |

| URL | Surface |
| --- | --- |
| `/` | public landing page |
| `/healthz` | readiness probe (unauthenticated) |
| `/account/login/`, `/account/logout/` | sign-in (throttled) and sign-out (POST) |
| `/account/password-reset/…` | password reset (four steps, single-use link) |
| `/account/invite/<uidb64>/<token>/` | accept an invitation and set a password |
| `/account/profile/`, `/account/password/` | account page, contact details, password change |
| `/account/` | role-aware home: the **tenant dashboard**, or a redirect to `/manage/` for staff |
| `/manage/` | rent-first operational dashboard; assigned-work-only landing for maintenance workers |
| `/manage/dashboard/<metric>/` | shared read-only projection explaining each dashboard figure |
| `/manage/activity/` | paginated operational audit history with validated filters and role-scoped events |
| `/manage/properties/…` | portfolio: list, create, detail, edit, take out of service, delete (admin) |
| `/manage/properties/<pk>/banner/` | the banner photo, served by a permission-checked view (never a public media path) |
| `/manage/units/…` | units the same way, attached to a property |
| `/manage/leases/…` | lease desk: list, create, detail, edit, activate/end (POST), delete a draft (admin) |
| `/manage/documents/…` | documents: list (search, category, visibility and property filters), upload, download, remove (admin) — each download permission-checked |
| `/manage/ledger/` | Rent & Payments: due now, account balance, past due and upcoming amounts, with a past-due filter |
| `/manage/ledger/leases/<pk>/` | one lease account: identity and states, financial summary, actions, chronological transactions with running balance, and audit history |
| `/manage/ledger/leases/<pk>/rent-charges/` | generate the missing monthly rent charges (POST, idempotent) |
| `/manage/ledger/leases/<pk>/charges/new/`, `…/payments/new/` | add a charge, record a payment |
| `/manage/ledger/charges/<pk>/adjust/`, `…/payments/<pk>/reverse/` | audited corrections (manager and above) |
| `/manage/ledger/payments/<pk>/clear/`, `…/void/` | move a pending payment to cleared or void (POST) |
| `/manage/accounts/…` | tenant accounts: managers create/invite/activate and maintain profiles; role changes remain superadmin-only |
| `/manage/accounts/<pk>/photo/`, `/account/photo/` | a tenant photo, served by a permission-checked view — the tenant's own URL carries **no id** |
| `/lease/`, `/lease/documents/`, `/lease/documents/<pk>/download/` | the tenant's own lease and the documents shared with them — tenant-only, every document resolved through the tenancy scope ([ADR-022](decisions/ADR-022-documents.md)) |
| `/payments/` | the tenant's own statement — tenant-only, no id in the URL, one paginated list of list rows rather than tables |
| `/admin/` | Django back office (`is_staff` gate) |

Several URL modules sit under `/manage/` with **different namespaces** (`manage` for accounts, `portfolio`
for the portfolio, `leases` for the lease desk, `ledger` for accounting, `documents` for documents), and
the tenant area has its own (`tenancy`, plus `tenant_documents` for `/lease/documents/`). One shared
namespace would leave whichever module was included first unreachable through `reverse()`.

Denials are deliberate: an authenticated user in the wrong *area* gets **403**, while an individual
record outside the caller's tenancy is resolved with `tenant_scope(...)` and returns **404**, so ids
cannot be probed. The one exception is **staff on a tenant page** (`/lease/`, `/payments/`): a staff
account has no tenancy of its own, so it is redirected to `/manage/` with a line saying why, the way
`/account/` already treats staff (`TenantAreaMixin`, ADR-003 amended). The alternative — a superuser
passing every role test and reading the *tenant* empty state, "No lease yet" — looks like a broken
account, which is exactly how the owner found it.

## Conventions

- **Server-rendered templates first.** Add HTMX for interaction; no SPA.
- **Authorization in the view or queryset**, never in the template alone.
- **Money is `Decimal`**; financial history is corrected by reversal or adjustment, never edited.
- Staff transactions show corrections inline beneath the original charge and calculate running balances
  from corrected charge amounts. Every mutation and account settlement locks the lease row, so a stale
  lease object cannot bypass financial-account closure.
- **Timestamps are timezone-aware UTC**; rent due dates are plain dates.
- **Logging** goes to stdout (console handler), level from `DJANGO_LOG_LEVEL`; no secrets or tenant
  PII in log messages.
- **One record, two readings.** The office reads ledger *entries* (each correction its own row, with its
  author and reason); the tenant reads a *statement* (corrections absorbed into the charge). Both come from
  one derivation over one `LeaseLedger`, so they cannot disagree (ADR-011).
- **One derivation, one question per name.** The balance over the term, what is due now, what is past due,
  and what is coming due are four different questions asked of the same allocation. Each has its own
  property on `LeaseLedger` (`balance_due`, `due_now`, `arrears`, `next_charge` / `next_rent_date`), so no
  screen reuses one figure to answer another (ADR-012).
- **A property answers what it was billed.** `apps/responsibilities` holds a property's recurring costs,
  the cycles they are billed in, and **each unit's monthly amount for that cycle** — the figure the ledger
  charges, never a percentage re-applied later (ADR-014). A month on the tenant's statement is a reading of
  the charges that share a due date, not a record of its own.
- **A lease answers what it charges.** `Lease.rent_for(on_date)` and `Lease.nnn_for(on_date)` are the only
  definitions of a month's base rent and NNN: a Fixed lease answers its stored rent for the whole term, a
  step-up or triple-net lease answers from the periods generated when it was activated, and nothing edits a
  period that has already been charged (extensions `docs/extensions.md`, ADR-013). Charges are separate
  entries per component — rent, NNN, and from E2 each responsibility — so a correction touches one line.
- **Derived facts are computed in one place.** Occupancy is defined once, by `LeaseQuerySet.current()`,
  and every screen reads it; there is no stored occupancy column (ADR-007). The same holds for money:
  `apps.ledger.services.build_ledger` is the only definition of a balance or a charge's state, and
  there is no stored balance (ADR-008).
- **Append-only money.** A charge or payment is corrected by a reversal or an adjustment row, never
  edited or deleted, and every mutation appends an `AuditEvent` in the same transaction.
- **Documents are rows, and every download is a view** ([ADR-022](decisions/ADR-022-documents.md)).
  `apps/documents` holds one `Document` per file, filed against a tenancy, a property or a tenant — at
  least one, and a tenancy is the default — with `tenant_visible` false unless staff tick it. The
  accepted types and the size cap live in `apps/common/files.py`; the stored name is random and the
  uploaded name is kept only as metadata. Staff read any document by id, a tenant only their own visible
  ones through `Document.objects.visible_to`; removal is an admin's act with a required note, and it
  deletes the row and the bytes while recording a `DOCUMENT_REMOVED` event.
- **Tests** exercise behavior through the public HTTP surface and the ORM, against PostgreSQL.

## Historical Phase 5 boundary

Documents (6), maintenance (7), communications (8), the full admin dashboard (9), reporting (10), payment
integration (11), production hardening — MFA, monitoring, proxy-level rate limiting (12). The dashboard
originally stopped at lease and financial information. Phase 6 added documents; Phase 7 adds a scoped
maintenance summary and navigation. Development-placeholder panels have been removed.

## What Phase 5 changed in earlier work

Phase 4's tenant page showed a balance; Phase 5 gave the tenant somewhere to land, so `/account/` is now a
rendered dashboard rather than a redirect to the account page, and the tenant navigation grew from one
item to three. One small correction came out of it: an *expected* payment is labelled "expected" rather
than "received" in the activity list, because the dashboard made that list prominent. The tenant-lease
lookup moved from a view function onto `LeaseQuerySet.visible_for`, so the lease page, the dashboard and
the payment history resolve a tenancy one way. No model, migration or dependency was added.

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
- **Tenant photos** (ADR-009): uploaded by staff on the account page, served only through
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

## Property accounting (E10) — the boundary

ADR-027 implements tenant cutover before accounting: one explicit financial start, durable lease
readiness and immutable linked noncash opening entries. Historical bill reconstruction is no longer the
initial setup UI. Existing ledgers/recovery remain compatible. No GL app is created in the cutover slice.

The [October 21 refinement](design/held-credit-repayments.md) adds immutable source-linked applications
and versioned repayment schedules. Installments schedule existing principal, not new charges. Reads
never allocate funds; mutations lock the tenancy, and only explicit confirmation applies held credit.

E10 adds a general ledger beside the ledger (ADR-026). The tenant sub-ledger stays the operational source of
truth for what a tenancy owes; the GL posts journals from those records once per source row, and every
balance and report is derived from journal lines rather than stored — the same rule the ledger already
follows. An AR control account must equal the sum of tenant-ledger balances, asserted by tests, so the two
readings cannot drift. The GL is staff-only: managers read and reconcile, administrators own the chart of
accounts and manual journals, and no tenant route reaches any accounting record. Bank statements are
imported and reconciled against journal lines; they never rewrite an entry. The blueprint is
[`design/property-accounting.md`](design/property-accounting.md) and the build is sliced `E10-B1`…`B5`.

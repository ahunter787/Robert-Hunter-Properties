# RHP — master specification (governing document)

**October 21 E10 refinement:** [Held credit and dated repayments](../design/held-credit-repayments.md)
supersedes automatic credit application. Managers explicitly apply held credit; new receipts cover
oldest due obligations only. Agreed repayment dates schedule existing opening principal without new
charges. Only due installments enter due-now/past-due totals; full unpaid principal stays in balance.

**E10 tenant cutover amendment, October 20, 2026:** ADR-027 replaces initial historical bill
reconstruction with a stated opening debt, credit or explicit zero, note and optional private evidence.
Keep genuine lease dates, immutable history and Decimal calculations. Opening credits are not receipts;
unknown historical aging is not fabricated. An explicit RHP financial start and durable lease readiness
bound native recurring charges. Accounting B1–B5 remains separately reviewed, not part of this release.

This is the project specification that governs every implementation phase. It was produced during the
RHP design conversation (ChatGPT share `6abd970f-ec50-83e8-a43f-167b0485d1e7`, 2026-09-30) and is
reproduced here so the repository carries its own contract. When this document and any other
description of RHP disagree, **this document wins**; when a change is genuinely needed, change it
here first, in its own commit, with a note explaining why.

The phased plan derived from it lives in [`../roadmap.md`](../roadmap.md). The architecture that
implements it is in [`../architecture.md`](../architecture.md).

```text
PROJECT: RHP
FULL NAME: Robert Hunter Properties

ROLE
You are the engineering harness responsible for designing and implementing a
self-hosted property-management and tenant portal for Robert Hunter Properties.

This is a real operational application that will eventually hold tenant,
lease, payment, property, and maintenance information.

Work incrementally. Do not try to build the entire product in one pass.

Before major architectural changes:
1. Inspect the existing repository.
2. Preserve existing working functionality.
3. State what phase you are implementing.
4. Implement only the scope for that phase.
5. Run tests/build/lint after changes.
6. Update project documentation.
7. Commit changes in logically separated commits.

Do not add major product features outside the scope below without being asked.


============================================================
PRODUCT VISION
============================================================

Build a modern self-hosted web application for Robert Hunter Properties.

There are two primary experiences:

1. TENANT PORTAL
   Tenants log in and manage information related to their tenancy.

2. RHP MANAGEMENT PORTAL
   RHP administrators manage properties, units, tenants, leases, balances,
   documents, maintenance, and communications.

Use Innago as a UX/product reference for property-management workflows,
but DO NOT clone its branding, source code, visual design, or unnecessary
feature set.

The application should feel:
- modern
- simple
- professional
- trustworthy
- mobile responsive
- easy for nontechnical tenants to use
- efficient for RHP administrators


============================================================
NON-GOALS
============================================================

DO NOT implement:

- rental listings
- listing syndication
- rental applications
- applicant pipeline
- tenant screening
- background checks
- credit checks
- renters insurance sales
- tenant credit reporting
- lead generation
- marketing CRM
- property marketplace
- public property search
- aggressive upselling
- advertising

These are explicitly outside the scope of RHP.


============================================================
TECHNICAL PHILOSOPHY
============================================================

This application must be easy to self-host.

It may initially run on:
- a local VM
- a local Docker host
- Proxmox
- a small VPS

It should later be portable to:
- DigitalOcean
- Linode/Akamai
- Hetzner
- AWS
- another managed Linux environment

Prefer a boring, reliable architecture over a complicated distributed system.

Recommended architecture:

Backend:
- Django
- Python
- Django ORM

Database:
- PostgreSQL

Frontend:
- Django templates
- HTMX where interactive behavior is useful
- lightweight JavaScript only where necessary
- Tailwind CSS or another well-maintained utility/component approach

Production server:
- Gunicorn

Reverse proxy:
- Caddy or Nginx

Deployment:
- Docker
- Docker Compose

File storage initially:
- local persistent volume

Future file storage:
- S3-compatible object storage abstraction

Do NOT introduce:
- Kubernetes
- microservices
- Kafka
- Redis unless actually needed
- React SPA architecture unless requirements later justify it
- GraphQL
- unnecessary abstraction layers


============================================================
REPOSITORY STRUCTURE
============================================================

Target structure:

RHP/
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── docs/
│   ├── architecture.md
│   ├── database.md
│   ├── deployment.md
│   ├── security.md
│   ├── roadmap.md
│   └── decisions/
│       └── ADR-001-monolith.md
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── accounts/
│   ├── properties/
│   ├── leases/
│   ├── accounting/
│   ├── maintenance/
│   ├── documents/
│   ├── communications/
│   └── dashboard/
├── templates/
│   ├── base.html
│   ├── components/
│   ├── tenant/
│   └── management/
├── static/
├── media/
└── tests/

Do not create empty applications merely for appearance.
Create each domain app as its implementation phase begins.


============================================================
USER ROLES
============================================================

Design permissions from the beginning.

Roles:

SUPERADMIN
- system administration
- unrestricted access

ADMIN
- full RHP operational access

MANAGER
- full portfolio operations across all RHP-owned properties
- properties and units
- tenants, invitations, and account activation
- leases, rent schedules, and expense recoveries
- charges, payments, settlement, reopening, and financial corrections
- maintenance, documents, and announcements
- no role changes, Django administration, site configuration, or destructive deletion

MAINTENANCE
- assigned maintenance requests
- update ticket status
- add notes/photos
- limited tenant/property information

TENANT
- only their own tenancy information
- lease documents they have permission to see
- their charges/payments
- their maintenance requests
- announcements applicable to them
- their account/profile

Never rely only on hiding navigation links.
Authorization must be enforced server-side.


============================================================
CORE DOMAIN MODEL
============================================================

The initial domain should include:

USER
- authentication identity
- first name
- last name
- email
- password
- active state
- role / memberships

TENANT PROFILE
- user
- phone
- optional contact information

PROPERTY
- property name
- street
- city
- state
- ZIP
- active status
- notes

UNIT
- property
- unit identifier
- optional bedrooms
- optional bathrooms
- active status

LEASE
- unit
- start date
- end date
- monthly rent
- deposit
- rent due day
- lease status
- one or more tenants

LEASE TENANT
- lease
- tenant
- primary tenant flag

CHARGE
- lease
- type
- description
- amount
- due date
- status

PAYMENT
- lease
- amount
- payment date
- method
- status
- external reference
- notes

DOCUMENT
- lease/property/tenant relationship where appropriate
- title
- type
- uploaded file
- visibility
- upload date

MAINTENANCE REQUEST
- unit
- tenant
- category
- title
- description
- priority
- status
- permission to enter
- created timestamp
- updated timestamp
- assigned staff member

MAINTENANCE ATTACHMENT
- request
- file/photo
- uploaded by
- timestamp

MAINTENANCE COMMENT / UPDATE
- request
- author
- body
- tenant-visible flag
- timestamp

ANNOUNCEMENT
- title
- content
- optional property scope
- published date
- expiration date
- active status

AUDIT EVENT
- actor
- action
- object type
- object ID
- timestamp
- relevant metadata

Model money with decimal types.
Never use floating point for financial values.


============================================================
DESIGN PHASES
============================================================


PHASE 0 — FOUNDATION AND ARCHITECTURE
-------------------------------------

Goal:
Establish the project correctly before product features are built.

Tasks:
- initialize Django project
- PostgreSQL configuration
- environment variable configuration
- development/production settings split
- Dockerfile
- docker-compose.yml
- Makefile
- health endpoint
- logging
- test framework
- formatting/linting
- initial README
- architecture documentation
- create base page layout
- establish CSS/design system
- add CI if appropriate

Create commands such as:

make dev
make up
make down
make build
make migrate
make migrations
make test
make lint
make shell
make logs
make superuser

Acceptance criteria:
- clean clone can be launched from documented instructions
- PostgreSQL persists across container restart
- application starts without manual hacks
- tests run
- environment secrets are not committed
- production and development configuration are separated


PHASE 1 — AUTHENTICATION AND AUTHORIZATION
------------------------------------------

Goal:
Build the identity and security foundation.

Implement:
- login
- logout
- password reset
- staff-created tenant accounts (a manager may create one, and activate it)
- invitation flow if practical
- role-based permissions
- tenant/staff route separation
- account/profile page

UI:
- polished login screen
- RHP branding placeholder
- responsive
- clear validation messages

Security:
- secure password storage through Django
- CSRF protection
- secure session configuration
- server-side authorization
- rate limiting strategy documented
- no user enumeration in reset workflow

Acceptance criteria:
- tenant cannot access management routes
- tenant A cannot access tenant B data
- maintenance user has restricted access
- staff can administer accounts: managers create, invite, activate and deactivate them, while a
  superadmin keeps role changes


PHASE 2 — PROPERTY AND TENANT MANAGEMENT
----------------------------------------

Goal:
Allow RHP to model its actual portfolio.

Implement management interfaces for:
- properties
- units
- tenants

Admin dashboard should display:
- number of active properties
- number of occupied units
- number of active tenants
- open maintenance requests

Property detail page:
- address
- units
- occupants
- active leases
- maintenance summary
- documents if applicable

Unit detail page:
- current tenant
- current lease
- rent amount
- recent maintenance
- vacancy state

Acceptance criteria:
- staff can create/edit/deactivate properties
- staff can create/edit units
- admin can associate tenants with leases later
- destructive operations require confirmation


PHASE 3 — LEASE MANAGEMENT
--------------------------

Goal:
Make the lease the central connection between tenant and property.

Implement:
- lease creation
- lease editing
- active / draft / ended state
- one or multiple tenants per lease
- rent amount
- deposit
- rent due day
- dates
- lease document attachment

Tenant lease screen should show:

LEASE
123 Example Street
Unit 4

Lease term:
Jan 1, 2027 — Dec 31, 2027

Monthly Rent:
$1,850.00

Due:
1st of every month

Security Deposit:
$1,850.00

Tenants:
...

Documents:
[View Lease]
[Download Addendum]

Do not implement electronic signatures yet unless specifically requested.

Acceptance criteria:
- staff can create lease and attach tenant(s)
- tenant can only view their lease
- expired leases remain historically available
- active lease is easy to distinguish

AMENDMENT, 2026-10-07 (owner-decided as P4-Q1, and recorded in ADR-020). This phase
defined three states but never said what they mean for a tenancy's money, and left the
end of a tenancy without a reason. Both are now specified:

- Occupancy and money have separate lifecycles. `LeaseStatus` is `DRAFT`, `FUTURE`, `ACTIVE`, or
  `ENDED` (a scheduled tenancy is `FUTURE` until its start date; ADR-029); `LeaseAccountStatus` is
  `OPEN` or `SETTLED`. An ended tenancy may still have an
  open financial account while money is collected or corrected.
- Ending a tenancy is an act by a staff member, and requires a citable reason: a code
  (tenant ended early, end of term or not renewed, eviction, sale or transfer, mutual
  agreement, other) and a note saying what happened.
- `ended_on` records the day the tenancy actually stopped. The term the lease was signed
  for (`end_date`) is never rewritten, so ending early is recorded rather than erased.
- Settlement is available only after the tenancy has ended, the balance is zero, no payment
  is pending, and no recorded security deposit remains undisposed. Until the move-out
  workflow records deposit disposition, a nonzero deposit blocks settlement.
- Reopening requires a reason and reopens only the financial account. It never restores
  occupancy, changes the tenancy's end date, or restarts recurring charges.
- Managers have portfolio-wide operational authority, including settlement, reopening, and
  financial corrections. Role changes, site configuration, Django administration, and
  destructive deletion remain administrator duties.

AMENDMENT, 2026-10-21 (owner-directed industry conformance, recorded in ADR-028 D5). The
settlement rule above keeps its meaning but now has the path it promised:

- The **agreed** security deposit remains a lease term. The **money held** is an append-only
  deposit register (received, returned, withheld with a reason, or explicitly not collected);
  the register's derived balance is what RHP holds. A deposit is never tenant AR and never a
  tenant credit.
- A recorded move-out outcome (full refund, itemised partial refund, or full withhold) is
  required before a financial account can settle. Settlement is refused while anything is still
  held, or while an agreed deposit has no recorded outcome — with a message naming the action,
  not a dead end.
- Held-deposit liability, refund and retained-amount postings belong to the accounting slices
  (E10 B2). Applying withheld funds to outstanding arrears is a later refinement; until then the
  desk corrects the arrears through the existing adjustment path.



AMENDMENT, 2026-10-22 (lease lifecycle conformance, recorded in ADR-029 M2a). A lease now
has a scheduled state, so a signed renewal can be represented before its term starts:

- `LeaseStatus` adds `FUTURE`: the terms are agreed but the term has not begun. Status is assigned
  from the dates, not chosen by hand: activating a future-dated lease schedules it, and a scheduled
  lease becomes active when its start date arrives (idempotent; a management command and the screens
  that read leases perform the check).
- A future tenancy is not occupancy and takes no obligations: no rent, NNN or recovery charges, no
  arrears, no statement, and it cannot be ended or settled. Its rent schedule is computed up front so
  the future amounts are known.
- A future lease may coexist with the active lease on the same unit; the one-active-lease rule is
  unchanged and still applies only to `ACTIVE`.
- A security deposit may be received and held before the term starts; it remains held-deposit money,
  never rent.
- A tenant on a future lease sees the upcoming terms read-only and no money; the person/login split
  (a person may exist without a portal login) is M2b and is not part of this amendment.

PHASE 4 — RENT LEDGER
---------------------

Goal:
Provide transparent accounting without initially processing payments.

Build a tenant ledger.

Tenant dashboard card:

Rent Due
$1,850.00

Due October 1

Current Balance
$0.00

Recent activity:
Sep 1   Rent Charge       +$1,850
Sep 1   ACH Payment       -$1,850
Aug 1   Rent Charge       +$1,850
Aug 1   ACH Payment       -$1,850

Desk capabilities (a manager; see the PHASE 1 amendment on manager authority):
- create recurring monthly rent charge
- manually add charge
- manually record payment
- reverse/correct payment
- add adjustment
- view lease ledger

Statuses should distinguish:
- unpaid
- partially paid
- paid
- overdue
- pending payment

Do NOT implement payment card/bank storage.

Architecture should leave room for later payment provider integration.

Acceptance criteria:
- balance is derived from ledger entries
- financial history is immutable or auditable
- edits/corrections leave an audit trail
- tenant sees an understandable balance

AMENDMENT, 2026-10-07 (owner-decided as P4-Q3 and P4-Q7, recorded in ADR-017). This phase
listed the ledger's actions without saying which of them a tenancy's state allows, and it
left the charging horizon to the office's habit. Both are now specified:

- **A charge falls due on its due date, and is raised then — never ahead of it.** The lease
  says what will be owed; the ledger records what is owed. The tenant's statement derives
  what is coming from the lease, so nothing is lost by not billing the future.
- **A running tenancy is the only one that takes new obligations.** Rent, NNN, a
  responsibility share and one-off charges are raised on an ACTIVE tenancy.
- **An ENDED tenancy (post-tenancy) still takes money in and corrections.** Payments are
  recorded, pending ones cleared, and charges adjusted, reversed or voided exactly as before,
  because arrears still get paid and a final figure must be correctable.
- **A settled financial account takes nothing further at all.** Every financial mutation,
  including payments and corrections, is refused until a manager explicitly reopens it.
- **When a tenancy ends, the months it will not use are closed out** by adjustment, dated at
  the end, naming the reason — never by deleting a charge.
- **A charge posted after a tenancy has ended — damage, cleaning, an unpaid balance, an early
  termination fee — carries its just cause**: a reason code, the lease clause it rests on, and
  its supporting evidence. Until documents exist to hold that evidence (Phase 6), the account
  may be reopened for corrections and payments but the ended tenancy still cannot take new
  recurring rent. The evidence-backed post-tenancy charge workflow remains P4-E6.


PHASE 5 — TENANT DASHBOARD
--------------------------

Goal:
Create the primary tenant experience.

The tenant dashboard should immediately answer:

1. How much do I owe?
2. When is it due?
3. Where is my lease?
4. Is my maintenance request being handled?
5. Has management sent me anything?

Suggested desktop layout:

-------------------------------------------------------
RHP                                      User Menu
-------------------------------------------------------

Good afternoon, [Tenant]

[ Current Balance ] [ Next Rent Due ] [ Lease Ends ]

Quick Actions
[ View Lease ]
[ Maintenance Request ]
[ View Payment History ]

-------------------------------------------------------
Recent Activity
-------------------------------------------------------

-------------------------------------------------------
Maintenance
-------------------------------------------------------

-------------------------------------------------------
Announcements
-------------------------------------------------------

Mobile layout:
single-column cards
large touch targets
no desktop-only functionality

Acceptance criteria:
- works well at phone width
- no unnecessary information density
- tenant's critical information visible without digging


PHASE 6 — DOCUMENT MANAGEMENT
-----------------------------

Goal:
Create safe document access.

Implement:
- upload documents
- categorize documents
- associate with lease/property/tenant
- choose tenant visibility
- secure downloads
- document metadata
- admin search/filter

Categories:
- lease
- addendum
- notice
- receipt
- inspection
- correspondence
- other

IMPORTANT:
Never expose uploaded tenant documents by guessing a public media URL.

Downloads must be permission checked.

Acceptance criteria:
- tenant cannot access documents belonging to another tenancy
- administrator can control tenant visibility
- files persist through deployments
- file type and upload size restrictions exist


PHASE 7 — MAINTENANCE SYSTEM
----------------------------

Owner-approved clarification (October 16, 2026): ADR-023 governs implementation. Requests
belong to properties/units with separate reporting tenancies, explicit sharing and private
tenancy conversations. No financial responsibility is inferred. Managers control closure
and reopening; tenants flag unresolved work. Record immutable repair costs and prepare
explicit, reviewed manual recharge splits through the existing ledger. Notifications are
persisted and sent after commit. General-ledger accounting remains outside this phase.

Goal:
Create a complete maintenance workflow.

Use Innago's maintenance flow as conceptual inspiration.

Tenant can:
- create request
- choose category
- enter title
- enter detailed description
- upload photos
- indicate permission to enter
- see status
- see management updates
- comment/respond

Suggested statuses:
OPEN
ACKNOWLEDGED
SCHEDULED
IN_PROGRESS
WAITING
COMPLETED
CLOSED

Suggested categories:
- plumbing
- electrical
- heating/cooling
- appliance
- structural
- exterior
- pest
- lock/security
- general
- other

Admin can:
- see maintenance queue
- filter property
- filter status
- filter age
- assign employee/vendor
- change priority
- update status
- add internal note
- add tenant-visible update

Ticket view should behave like a timeline:

Oct 4 9:14 AM
Tenant submitted request

Oct 4 10:02 AM
RHP acknowledged request

Oct 4 1:20 PM
Assigned to maintenance

Oct 5 8:00 AM
Technician scheduled

Acceptance criteria:
- tenant sees changes clearly
- admin has actionable queue
- internal comments are NEVER exposed to tenants
- images and attachments are permission checked


PHASE 8 — COMMUNICATIONS
------------------------

Goal:
Provide lightweight property communication.

Implement announcements first.

Examples:
- water shutoff
- parking maintenance
- inspection notice
- holiday schedule
- office closure

Announcements may target:
- everyone
- one property
- selected properties

Owner-approved scope extension, October 17, 2026 — E12 / P8-E1:
Include saved tenant/management conversations, explicit authorized participants, private attachments,
per-user unread state and durable email alerts to tenants and managers. Announcements remain one-way;
follow-up opens a private conversation, not public comments. Optional open-page refresh uses the
existing Django/HTMX stack, with complete plain-form operation. No native mobile app, push notifications,
SMS, general group/community chat, presence/typing indicators or new queue/realtime service is required.

The capability specification and recorded access/lifecycle answers are in
`docs/phases/phase-08-communications.md`. The owner resolved the questions October 19, 2026 and
authorized ADR-024 implementation on `rhp-8` after the accepted E11 local merge. Use the Operations
Desk shell, one Communications workspace, private/shared topic threads, manager-enabled move-out
follow-up, frozen household history, fixed announcement recipients, important-only email and no
acknowledgment. Preserve maintenance and financial boundaries.

Acceptance criteria:
- announcement appears only to intended tenants
- expired announcement disappears from normal tenant view
- important announcement can be highlighted
- private messaging, attachments, unread state and delivery retries preserve authorized tenancy boundaries


PHASE 9 — ADMIN DASHBOARD
-------------------------

Owner-approved implementation, October 19, 2026 (ADR-025): replace the existing staff dashboard,
rent first; all posted charge categories; live calculations on page load; cumulative 30/90-day
lease windows; searchable operational history with role changes superadmin-only. Every metric has
a matching read-only drill-down. Month charges use original due dates with corrections; effective
cleared payments use payment dates. No invented monthly outstanding, stored totals or new accounting.

Goal:
Give RHP a useful operating overview.

Dashboard examples:

PORTFOLIO

Properties: 12
Units: 38
Occupied: 35
Vacant: 3

RENT

Due this month:       $48,250
Collected:            $45,300
Outstanding:           $2,950

MAINTENANCE

Open:                 7
In Progress:           3
Over 7 Days:           1

LEASES

Expiring in 30 days:   2
Expiring in 90 days:   5

Recent activity feed.

Do not make analytics decorative.
Every metric should lead to useful underlying data.


PHASE 10 — REPORTING AND SEARCH
-------------------------------

Implement:
- tenant search
- property search
- unit search
- lease search

Reports:
- rent roll
- balances due
- payment history
- lease expirations
- maintenance aging
- property occupancy

Export:
- CSV first
- PDF only where useful


PHASE 11 — PAYMENT INTEGRATION
------------------------------

DO NOT IMPLEMENT UNTIL EXPLICITLY APPROVED.

Prepare the architecture, but do not choose or integrate a payment provider yet.

Future goals:
- ACH
- optional debit/card
- one-time payment
- autopay
- payment status
- webhook reconciliation

Rules:
- RHP application must never store full card numbers
- RHP application must never store bank login credentials
- use provider-hosted/tokenized payment mechanisms
- webhook events must be verified
- payments must reconcile to ledger entries


PHASE 12 — PRODUCTION HARDENING
-------------------------------

Before real tenant deployment:

- HTTPS
- production secret management
- secure cookies
- database backups
- media backups
- off-machine backups
- restore procedure
- audit logging
- admin MFA
- brute-force mitigation
- email configuration
- monitoring
- error reporting
- application health checks
- dependency updates
- file upload restrictions
- log retention
- privacy review
- disaster recovery documentation

Test:
- tenant isolation
- authorization bypass attempts
- document access
- maintenance attachment access
- ID enumeration
- session handling


============================================================
DESIGN LANGUAGE
============================================================

Do not visually imitate Innago.

Create an RHP identity.

Design goal:
professional property-management portal rather than SaaS marketing product.

Base palette:
- warm white / light neutral background
- charcoal text
- restrained dark navy or forest-green primary
- muted gray surfaces
- green success
- amber warning
- red overdue/error

Use:
- generous whitespace
- rounded but restrained cards
- crisp typography
- subtle shadows/borders
- consistent spacing
- accessible contrast
- simple icons

Avoid:
- excessive gradients
- giant animations
- glassmorphism
- neon colors
- dashboard clutter
- unnecessarily tiny text

Desktop management portal:
left navigation is appropriate.

Tenant portal:
simpler navigation with fewer destinations.


============================================================
TENANT NAVIGATION
============================================================

Dashboard
Lease
Payments
Maintenance
Documents
Announcements
Account


============================================================
ADMIN NAVIGATION
============================================================

Dashboard

Portfolio
  Properties
  Units

People
  Tenants

Leasing
  Leases

Rent & Payments
  Charges
  Payments
  Balances

Maintenance

Documents

Communications
  Announcements

Reports

Administration
  Users
  Audit Log
  Settings


============================================================
SECURITY RULES
============================================================

Treat security as a first-class requirement.

All sensitive objects must be queried with authorization scope.

Bad:

Document.objects.get(pk=id)

Better:

Document.objects.get(
    pk=id,
    lease__tenants=request.user
)

where appropriate.

Use UUIDs where useful for externally exposed resources.

Never trust:
- URL IDs
- hidden fields
- submitted role values
- client-side visibility

Validate access server-side.

Uploads:
- restrict size
- validate extensions/content
- randomize stored filename
- do not execute uploaded content
- permission-check every download


============================================================
DATA INTEGRITY
============================================================

Financial records require particular care.

Do not silently overwrite transaction history.

Prefer:
- original transaction
- reversal/correction entry

rather than modifying historical financial activity.

Important state transitions should be auditable.


============================================================
TEST STRATEGY
============================================================

Every implementation phase should include tests.

Highest priority tests:

AUTHORIZATION
- tenant cannot view another tenant
- tenant cannot access admin routes
- tenant cannot download another lease
- tenant cannot view another maintenance ticket

FINANCIAL
- balance calculations
- partial payments
- reversals
- overdue determination

LEASES
- active lease selection
- multiple tenants
- ended lease behavior

MAINTENANCE
- tenant submission
- assignment
- tenant-visible notes
- internal-note isolation


============================================================
HARNESS WORKFLOW
============================================================

When given a new phase:

1. Inspect repository.
2. Read README and docs/roadmap.md.
3. Report current state briefly.
4. Identify files/components that need changes.
5. Implement only that phase.
6. Add database migrations.
7. Add tests.
8. Run tests.
9. Run formatter/linter.
10. Run application/build smoke test.
11. Update documentation.
12. Show concise summary:
    - implemented
    - files changed
    - migrations
    - tests
    - known limitations
13. Commit only if explicitly instructed to commit.

Never fake successful tests.

If something fails, fix it before declaring completion.


============================================================
INITIAL DELIVERY PLAN
============================================================

Do not implement all phases immediately.

Begin with:

MILESTONE 1
Phase 0 + Phase 1

MILESTONE 2
Phase 2 + Phase 3

MILESTONE 3
Phase 4 + Phase 5

MILESTONE 4
Phase 6 + Phase 7

MILESTONE 5
Phase 8 + Phase 9

MILESTONE 6
Phase 10 + production hardening

Payments are a separate later milestone.


============================================================
FIRST TASK
============================================================

Inspect the current repository.

Then implement PHASE 0 ONLY.

Before coding, produce:

1. proposed repository structure
2. package/dependency choices
3. database configuration
4. Docker topology
5. development workflow
6. production deployment topology
7. any architectural concerns

Then proceed with Phase 0.

Do not implement tenant/property/lease functionality yet.
```

## Phase 0 implementation notes

The repository implements this specification with a few documented, deliberate deviations. Each is
recorded so a later reader does not mistake it for drift:

| Spec | Implementation | Why |
| --- | --- | --- |
| `docker-compose.yml` only | `docker-compose.yml` + `docker-compose.override.yml` (dev) + `docker-compose.prod.yml` | Compose cannot remove published ports via an override, so the base file stays production-shaped |
| Repo structure lists every domain app | Only `apps/accounts` exists | `AUTH_USER_MODEL` must be fixed before the first migration — see [ADR-002](../decisions/ADR-002-custom-user.md) |
| `static/`, `media/` at root | `static/` holds build output only; the Tailwind source lives in `assets/css/`; uploads go to `MEDIA_ROOT`. Generated CSS and all uploads are gitignored | Source files must never be published by `collectstatic`, and build output/user data are not source |
| `templates/tenant/`, `templates/management/` | Not created yet | Created with the phases that render them |
| MAILERS not mentioned | `MAILERS` instead of `EMAIL_*` | Django 6.1 deprecated the old settings; Django 7.0 removes them |
| Make targets listed | Same list plus `init`, `assets`, `check`, `check-deploy`, `health`, `psql`, `up-prod`, `down-prod`, `prod-logs` | Phase 0 needs a one-command first run and an explicit production path |

## Owner-approved extensions

The specification above is the contract, reproduced rather than rewritten. Additions that are not phases
are proposed, approved and tracked in [`../extensions.md`](../extensions.md), each with its own decision
record; this appendix lists the ones that have been approved, so a reader of this document can see what
the contract now includes.

| Extension | What changed | Why | Decision |
| --- | --- | --- | --- |
| **E1** — lease templates | A lease has a **template**: Fixed, Step Up or Triple Net. A step-up or triple-net lease's rent is worked out for the whole term when the lease is activated and stored as dated periods; a triple-net lease also carries an **NNN** amount re-staged each year. `monthly_rent` keeps its meaning — the rent at the start of the term, and the whole answer for a lease that has no periods. | RHP's real leases rise once a year, and some carry NNN on top of the rent. The single `monthly_rent` the specification models could express neither, so the office was re-typing rises and the tenant could not see how a month was worked out. | [ADR-013](../decisions/ADR-013-lease-templates.md) |

| **E2** — property responsibilities | A property carries **responsibilities** — utilities and maintenance it is billed for — each with cycles staged in advance and a **stored monthly amount per unit**, raised as their own ledger charges. The tenant's statement groups a month's charges (rent, NNN, responsibilities) into one card, grouped by category. CAM is recorded as a rate per square foot and shown as a metric, because the lease folds it into base rent. | The landlord is billed per property and each unit carries its share, divided the way the lease says — including divisions that are not a formula. The specification has no way to record a property-level cost, so the office divided bills by hand and typed a charge per unit per month. | [ADR-014](../decisions/ADR-014-property-responsibilities.md) |

| **E4** — retroactive onboarding | A lease carries a **cutover** — the first month RHP bills for — and a live tenancy that began before RHP cannot be charged until somebody places it: either the whole term's charges are raised and one settling payment brings in what was already received, or charging starts at the cutover with a single brought-forward balance (or credit on account). A lease may also be **stated**: its amounts are entered from the paper rather than generated from a rule. | Every RHP tenancy is live now and none began in RHP. Charging them the ordinary way billed years of history as if it were new — on one real lease, 108 charges and a $100,536 "balance" for a tenant who was paid up — and the specification has no notion of a tenancy being *placed*. | [ADR-016](../decisions/ADR-016-retroactive-onboarding.md) |

**E2 calculator clarification, approved October 16, 2026:** entering a bill follows bill
details → explicit monthly allocation → review and save. The edited dollar or percentage
input controls its paired value; only the explicitly selected remainder recipient is
recalculated, with RHP the default. Preview/navigation do not write, final saving revalidates
the reviewed state, and posted cycles remain locked. Monthly Decimal storage, vacancy
treatment and rounding are unchanged. See ADR-014's October 16 amendment.

Proposed but **not** approved: E3 (concessions).

**E11 design study, approved October 17, 2026:** evaluate role-aware navigation and information
density through three comparable desktop/phone concepts. Keep editable, predominantly monochrome
diagrams and print exports in `docs/design/` and scoped copies in Outline Design; use semantic
color intentionally and preserve grayscale meaning. This approves the study and project diagram
skill, not a production shell rollout. Owner selection is recorded in the Design decisions.

**E11 application migration approved October 18, 2026:** adopt Operations Desk and its persistent
sidebar across existing portal capabilities without changing business/security rules. Properties
is the first owner-review checkpoint (accepted October 18; continuation authorized). Add one optional unit photo, manager-managed and privately
served to staff/authorized tenancies. Preserve routes, Decimal calculations and immutable history.
No messaging/accounting/payment-processing feature is included. See `docs/design/implementation.md`.
Baseline commits/local merge are authorized; redesign commits, push and deployment are not.

**Financial clarity release approved October 20, 2026 (E9/E11):** share the lease financial
workspace across both existing staff URLs, retain the middle lease navigation, and apply equivalent
tenant language without staff controls. Distinguish posted upcoming debt from unposted scheduled
rent; empty accounts do not assert payment. Amount-only colors: debt/cost red, receipt/credit green,
explicit correction purple, expected payments and ordinary statement information black. No financial
blue/orange meanings. Preserve domain calculations, immutable history and settlement locks. First
review the shared reading surface before changing remaining financial forms. No new accounting,
payment processing, inferred prior receipts, models or dependencies are approved by this release.

**Expandable bill refinement approved October 20:** both portals group a tenancy's charges by
exact due date (rent, NNN, expense recoveries and one-time charges), with one total and aggregate
payment progress. Components retain descriptions, icons and inline corrections, but no paid/remaining
breakdown. Staff may adjust individual charges, not the overall bill. Payments remain separate dated
records, including expectations, cancellations and reversals. Cards open independently through native
disclosure controls; noninteractive card content toggles without intercepting actions or text selection.
Grouping is read-only, precedes filtering/pagination and preserves full-history balances and existing
payment allocation. This does not authorize invoice storage, accounting or financial-rule changes.

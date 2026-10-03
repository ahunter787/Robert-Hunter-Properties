# RHP — master specification (governing document)

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
- properties
- units
- tenants
- leases
- charges/payments
- maintenance
- documents
- announcements

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
- administrator-created tenant accounts
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
- admin can administer accounts


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
- admin can create/edit/deactivate properties
- admin can create/edit units
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

Admin capabilities:
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

Later:
evaluate direct tenant/management messaging.

Do not build a giant chat system prematurely.

Acceptance criteria:
- announcement appears only to intended tenants
- expired announcement disappears from normal tenant view
- important announcement can be highlighted


PHASE 9 — ADMIN DASHBOARD
-------------------------

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

Accounting
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

Proposed but **not** approved: E2 (property responsibilities charged to the unit) and E3 (concessions).

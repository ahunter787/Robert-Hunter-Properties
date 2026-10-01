# RHP phase guide

This is the plain-language guide to how RHP is being built: what each phase is for, what exists today,
what a phase deliberately leaves out, and — the important part — **which later phase will come back and
change something that already works**. Use it to decide where improvements are worth making and to see
the churn coming before it happens.

Two companion documents:

- [`roadmap.md`](roadmap.md) — the same phases as a terse status checklist (what is done, what is next).
- [`harness/master-spec.md`](harness/master-spec.md) — the original specification every phase is measured
  against.

## How to read this

- **A phase is a chunk of work with a finish line.** Nothing from a later phase is built early, and a
  phase is only finished when its acceptance criteria are tested and you have looked at it.
- **Status words:** *Complete* = built, tested, in `main`, and signed off. *In review* = built and tested
  but you have not signed it off; work continues on a branch. *Next* = about to be built. *Not started* =
  planned, not built. *Needs your approval* = we will not build it without an explicit decision from you.
- **Every phase follows the same path:** work happens on a branch (`rhp-1`, `rhp-2`, …), you test it, then
  it is squashed into `main` as a single commit and the branch is deleted. A phase squashed into `main`
  is finished; new work always starts from `main`.
- **Nothing here is archaeology.** If a decision in an earlier phase is making later work awkward, the
  fix happens in the phase that needs it, and this document records that in advance.

## Where everything stands

| Phase | Name | Status | What you can do today |
| --- | --- | --- | --- |
| 0 | Foundation | Complete | Run RHP anywhere, deploy it, check its health |
| 1 | Identity and access | Complete | Staff and tenants sign in; tenants are invited; roles decide what each person sees |
| 2 | Portfolio | Complete | Record properties and units, photograph them, pin them on a map |
| 3 | Lease management | **In review** | Put a tenant on a lease, activate it, and read it as that tenant |
| 4 | Rent ledger | Next | — |
| 5 | Tenant dashboard | Not started | — |
| 6 | Document management | Not started | — |
| 7 | Maintenance | Not started | — |
| 8 | Communications | Not started | — |
| 9 | Admin dashboard | Not started | — |
| 10 | Reporting and search | Not started | — |
| 11 | Payment integration | Needs your approval | — |
| 12 | Production hardening | Not started | — |

---

## Phase 0 — Foundation

**In one sentence:** the solid, boring base — one application, one database, one way to run it anywhere.

**What exists now:** a Django application with PostgreSQL, development and production configuration kept
apart, a container setup that is identical on a laptop and a server, a health check, logging, a test
suite, linting, continuous integration, the RHP visual design system, and this documentation.

**What you can do today:** start it with one command on a fresh machine; see the landing page and the
health check; deploy the same stack to a VM or a rented server.

**What it deliberately does not do:** no sign-in, no data, no features.

**What later phases will change here:** Phase 12 adds the operational hardening (automated backups,
monitoring, error reporting, stricter web security headers). Phase 9 replaces the counters on the staff
landing page. The database, the containers, and the tests will not be re-designed.

**How to check it:** `make init`, open <http://localhost:8000>, `make test`.

---

## Phase 1 — Identity and access

**In one sentence:** who a person is, and what they are allowed to see.

**What exists now:** sign-in and sign-out, password reset by email, an invitation flow where RHP creates
a tenant account and the tenant chooses their own password, five roles, a hard separation between the
staff area (`/manage/`) and the tenant area (`/account/`), and an account page with contact details.
Sign-in is rate limited: five wrong passwords lock that account or address out for fifteen minutes.

| Role | Reaches |
| --- | --- |
| `SUPERADMIN` | everything, including changing roles and deleting records |
| `ADMIN` | management area, tenant account administration, deletion |
| `MANAGER` | management area, the portfolio, and reading tenant records |
| `MAINTENANCE` | management area (assigned work arrives in Phase 7) |
| `TENANT` | their own account and, from Phase 3, their own lease |

**What you can do today:** sign in as staff or as a tenant; invite a tenant by email; let a tenant set
their own password; deactivate an account; change someone's role; edit your own contact details and
password.

**Deliberate decisions worth knowing:** there is no public sign-up — staff create every account. Nobody
at RHP ever sees or chooses a tenant's password. Passwords, sessions, and the lockout are all
server-side, so hiding a button is never the thing protecting data.

**What it deliberately does not do:** two-factor authentication (Phase 12), tenant-to-management
messaging (Phase 8), any tenant-facing page beyond the account page (Phase 3 gives them their lease).

**What later phases will change here:** Phase 3 gives tenants the first page that shows them something
real. Phase 5 turns that into their dashboard. Phase 6 and 7 add tenant-owned files and photos, which
reuse the same "only the owner may download" rule established here. Phase 12 adds two-factor
authentication and session hardening. Phase 4 introduces the audit table, at which point the security
events that Phase 1 only logs begin to be recorded in the database.

**How to check it:** sign in at `/account/login/`; `/manage/accounts/` as an admin; enter a wrong
password five times and watch the lockout.

---

## Phase 2 — Portfolio

**In one sentence:** the list of buildings RHP manages, and the rentable units inside them.

**What exists now:** properties with an address, notes, an "in service" flag, a map pin and a banner
photo; units inside a property with an identifier, a type (Residential or Commercial), bedrooms and
bathrooms for residential units, and an "in service" flag; staff screens to list, search, create, edit
and retire both; and counters on the staff landing page.

**What you can do today:** build the portfolio; upload a photo per property; paste a Google Maps link
(full or shortened) or coordinates to pin a property on a map; retire a unit or building without losing
its history; see how many properties, units and tenants there are.

**Deliberate decisions worth knowing:**

- A unit is named by its own identifier, with the property underneath it ("Storefront" / "- 910 Stark"),
  because that is how staff talk about units.
- Bedrooms and bathrooms describe *residential* space, so a commercial unit cannot carry them and the
  screen says "Not applicable" rather than "Not recorded" (which would imply missing data).
- A building with units **cannot** be deleted — the database refuses. Retiring is the everyday action;
  deleting is for mistakes and is admin-only, behind a confirmation page.
- Occupancy is not guessed. Until leases exist there is no such thing as an occupied unit, so the pages
  label the gap instead of showing a zero.

**What it deliberately does not do:** leases, occupancy, vacancy, rent (Phase 3 and 4); tenant documents
(Phase 6); maintenance history (Phase 7). The property page says so on screen, in a "Not tracked here
yet" panel.

**What later phases will change here:** **Phase 3** has now filled the two panels Phase 2 left labelled —
"occupants and active leases" on a property and the "Tenancy" panel on a unit — and switched the occupancy
counters on. **Phase 6** takes over document handling and will also give banners thumbnails and
resizing, and will move the single lease file into the documents table. **Phase 9** replaces the
counters with the real dashboard. **Phase 10** reports on the portfolio (rent roll, occupancy).
**Phase 12** adds the content-security entry for the embedded Google map and the operational parts of
file handling.

**How to check it:** `/manage/properties/` and `/manage/units/` as a manager or admin; open a property
and look at the map and banner; try to delete a building that has units and read the refusal.

---

## Phase 3 — Lease management (in review: your testing)

**In one sentence:** the lease is the record that connects a unit to the people renting it — and it is
where the tenant portal begins.

**What exists now:** a lease desk at `/manage/leases/` where a manager or admin creates a lease against a
unit, adds one or more tenants and marks one as the primary contact, records the term, monthly rent,
deposit and rent due day, attaches the signed lease as a PDF or a scan, and moves the lease through
*draft* → *active* → *ended*; a property page that shows which units are let and to whom; a unit page
whose "Tenancy" panel is real; occupied/vacant counters on the staff landing page; and a tenant page at
`/lease/` showing that tenant's unit, term, rent, deposit, co-tenants and their copy of the document.

**What you can do today:** write a lease and keep it as a draft while the details are settled; activate
it when the tenant takes the keys; correct the rent or dates while it is a draft, and the rent on an
active lease; end a lease when the tenancy finishes; see at a glance which units are occupied, which are
vacant, and which leases run out within the next 30 days; sign in as a tenant and read your own lease.

**Deliberate decisions worth knowing:**

- **A unit can only have one active lease.** The database enforces it, so a unit cannot be let twice even
  if two people click *Activate* at the same moment. Drafts are unlimited — several half-written leases
  on one unit are normal.
- **A lease is ended by a person, never by a date passing.** A lease whose end date has gone by shows as
  "ending soon" and waits. That is deliberate: Phase 4 has to be able to bill a holdover month, and a
  status that rewrites itself at midnight cannot be audited with a name against it.
- **Ended leases are history.** They stay readable forever and cannot be edited — including by a direct
  POST, not just by hiding the form. A correction is a new lease.
- **Only a draft can be deleted, and only by an admin.** An active or ended lease is *ended* instead, so
  the record of what was agreed survives.
- **Once a lease is active its unit is fixed.** Moving a live tenancy to another unit is not a typo; end
  the lease and start a new one. If someone edits the page to try it anyway, the desk says so.
- **One primary contact per lease** — the person the office rings. It is not a statement about who owes
  the rent; that is a money question and belongs with Phase 4.
- **One document per lease for now.** Phase 6 replaces it with a proper documents area.
- **A unit taken out of service is neither occupied nor vacant.** Its tenancy stays in the records, but
  it is not counted as available to let.

**What it deliberately does not do:** no balances, charges or payments (Phase 4); no tenant dashboard
(Phase 5); no documents area beyond the single lease file (Phase 6); no electronic signatures, and no
automatic renewal, proration or late fees.

**What later phases will change here:** **Phase 4** turns the stored rent and due day into a real ledger
and implements the month-end rule for a due day of the 31st; lease status changes start being written to
the audit table. **Phase 5** grows `/lease/` into the tenant dashboard with balances. **Phase 6** moves
the single lease file into the documents table (categories, visibility, several files) and generalises
the access rule. **Phase 9** and **Phase 10** report on occupancy and the rent roll. **Phase 12** puts
the document access rule through the security test pass.

**How to check it:** as a manager, go to `/manage/leases/` and create a lease for one of your units with
a tenant and a term; save it as a draft, then activate it. Then try to create a second active lease on
the same unit — the unit no longer appears in the picker, and the database would refuse it anyway. End
the lease and notice that the edit page turns into a read-only record. Finally, sign in as that tenant
and open `/lease/`.

---

## Phase 4 — Rent ledger

**In one sentence:** a truthful running account of what each tenancy was charged and what was paid, so a
balance is something derived rather than typed in.

**What it will deliver:** recurring monthly rent charges generated from a lease, manually added charges,
recorded payments, reversals and adjustments, and a per-lease ledger with unpaid / partly paid / paid /
overdue / pending states. Balances are always calculated from entries.

**What it will change from earlier work:** this is where the **audit table** arrives — lease status
changes and money movements start being recorded as events rather than only log lines. The rent due day
stored in Phase 3 gets its rule implemented (a due day of the 31st in February falls on the last day of
the month). The tenant lease page gains a balance summary, which Phase 5 turns into the dashboard.

**Hard rules, decided now:** nothing is ever edited in place — a mistake is corrected by adding a
reversal, and the original stays visible. Money is stored exactly, never as a floating-point number.
RHP will not store card numbers or bank credentials at any point.

**Needs nothing from you yet.** Phase 11 (actual payments) is where a provider decision is required.

---

## Phase 5 — Tenant dashboard

**In one sentence:** one page that answers the five questions a tenant actually has.

**What it will deliver:** how much do I owe, when is it due, where is my lease, is my maintenance
request being handled, has management sent me anything — on a phone, in that order.

**What it will change from earlier work:** grows the Phase 3 tenant lease page into the real landing
page and links it to the Phase 4 balances. The tenant navigation (Dashboard, Lease, Payments, …) becomes
real rather than a single item.

---

## Phase 6 — Document management

**In one sentence:** the place lease documents, notices, receipts and inspections live, with access
rules that hold.

**What it will deliver:** documents uploaded and categorised (lease, addendum, notice, receipt,
inspection, correspondence, other), attached to a lease, property or tenant, with explicit tenant
visibility and downloads that are permission-checked.

**What it will change from earlier work:** replaces the single lease file from Phase 3 (migrating it into
the documents table) and gives the banner photo its optimisation work (thumbnails, resizing). The
"never served by the web server or proxy" rule established in Phase 2 becomes general.

---

## Phase 7 — Maintenance

**In one sentence:** tenants report problems; RHP tracks them to done, with a timeline both sides can
trust.

**What it will deliver:** tenant submissions with a category, description, photos and permission to
enter; a staff queue with assignment, priority and status (open → acknowledged → scheduled → in progress
→ waiting → completed → closed); and a timeline where tenant-visible updates and internal notes are
handled separately.

**What it will change from earlier work:** adds the maintenance counters promised on the staff landing
page, adds a maintenance panel to the property and unit pages, and gives the `MAINTENANCE` role the work
it was created for.

---

## Phase 8 — Communications

**In one sentence:** the short, targeted notices a property manager actually sends — water shutoff,
inspections, holidays — without building a chat system.

**What it will deliver:** announcements scoped to everyone or to one property, shown only to the
intended tenants, with publication and expiry dates and an option to highlight something important.

**What it will change from earlier work:** adds an announcements panel to the tenant dashboard (Phase 5)
and to the property page. Direct messaging is evaluated afterwards rather than assumed.

---

## Phase 9 — Admin dashboard

**In one sentence:** the operating picture for the RHP team, where every number leads to the records
behind it.

**What it will deliver:** portfolio, rent, maintenance and lease-expiry summaries with a recent-activity
feed.

**What it will change from earlier work:** replaces the counters currently on the staff landing page
(built incrementally in Phases 2, 3 and 7) with the real dashboard. No existing screen is thrown away;
the numbers just move.

---

## Phase 10 — Reporting and search

**In one sentence:** finding things quickly and answering the recurring questions — rent roll, who owes
what, which leases expire, how old the open work is.

**What it will deliver:** search across tenants, properties, units and leases; the standard reports; CSV
export first, PDF only where it earns its place.

**What it will change from earlier work:** reads the portfolio and lease data as built; the bedroom and
bathroom fields from Phase 2 finally get used here (sizing and rent-roll reporting).

---

## Phase 11 — Payment integration (needs your approval)

**In one sentence:** tenants paying rent online, reconciled against the ledger that Phase 4 makes
trustworthy.

**What it will deliver (only once you decide to):** one-time payments, optional autopay, payment status,
and webhook reconciliation into the ledger.

**Hard rules, already decided:** RHP never stores card numbers or bank login credentials; payments go
through a provider that handles the sensitive parts; every payment must reconcile to a ledger entry. The
choice of provider is yours and is deliberately not made yet.

---

## Phase 12 — Production hardening

**In one sentence:** everything that has to be true before real tenant data lives in RHP.

**What it will deliver:** HTTPS and strict web security settings, secret management, database **and**
file backups with a rehearsed restore, off-machine copies, audit logging, two-factor authentication for
staff, brute-force protection, email configuration, monitoring and error reporting, file-upload
restrictions, log retention, a privacy review, and a security test pass (tenant isolation, authorization
bypass attempts, document and attachment access, id enumeration, session handling).

**What it will change from earlier work:** this is the phase that touches almost every earlier phase, on
purpose — it is where the "works" becomes "safe to rely on".

---

## Cross-phase change map

Things that will be revisited, and by which phase. This is the quickest way to see where churn is
coming.

| Element | Built in | Revisited by | What changes |
| --- | --- | --- | --- |
| Single lease file | Phase 3 | Phase 6 | Becomes documents in the documents table (categories, visibility, multiple files) |
| Lease document access rule | Phase 3 | Phase 6, 12 | Generalised to all documents; included in the security test pass |
| Tenant `/lease/` page | Phase 3 | Phase 5 | Grows into the tenant dashboard with balances and announcements |
| Occupancy / vacancy definition | Phase 3 | Phase 9, 10 | Reported on in the dashboard and the occupancy report |
| Staff landing counters | Phases 2, 3, 7 | Phase 9 | Replaced by the real admin dashboard |
| Rent due day (stored) | Phase 3 | Phase 4 | The month-end clamping rule is implemented in the ledger |
| Lease status changes | Phase 3 | Phase 4 | Start being written to the audit table instead of only logs |
| Structured security logs | Phases 1, 2 | Phase 4, 12 | Phase 4 adds the audit table; Phase 12 decides retention |
| Banner photo | Phase 2 | Phase 6, 12 | Thumbnails and resizing; content-security policy for the map |
| Map pin | Phase 2 | Phase 12 | The Google embed becomes an explicit security-policy entry |
| Bedrooms / bathrooms | Phase 2 | Phase 10 | Used for sizing and rent-roll reporting |
| Tenant contact notes | Phase 1 | Phase 5+ | Surface on the tenancy screens once tenants have a dashboard |
| Invitations and passwords | Phase 1 | Phase 12 | Two-factor authentication for staff; session hardening |
| Property / unit retirement | Phase 2 | Phase 10 | Retired records stay in reports as history |
| Money fields | Phase 3 | Phase 4, 11 | The ledger reads them; payments reconcile against ledger entries |

## Open questions worth deciding later

Collected on purpose, so nothing is forgotten and nothing is decided by accident:

- **Month-to-month leases** — the lease term currently needs both a start and an end date. If RHP takes
  on month-to-month tenancies, the end date becomes optional and the screens need a "no fixed end" state.
- **Proration, late fees, rent escalation** — none of these are in the specification. They are common in
  practice, and they would be their own small phase rather than bolted onto the ledger.
- **Deposits** — Phase 3 records the deposit amount. Whether deposits are tracked as balances (held,
  returned, deducted from) is a Phase 4 decision about the ledger.
- **Correcting an ended lease** — ended leases are read-only today; a correction is made by an
  administrator. If that becomes frequent, a proper amendment flow belongs in the ledger phase.
- **Renewing a lease** — Phase 3 has no "copy this lease forward" action, so a renewal is typed again
  from scratch. Once real tenancies start rolling over, that will be the most common repetitive job on
  the desk and worth its own small piece of work.
- **Who is liable for the rent** — a lease records a primary *contact*, not a payer. If RHP needs
  joint-and-several liability, split responsibility, or a guarantor, that is a decision for Phase 4 that
  reaches back into the lease's tenant rows.
- **Direct messaging** — announcements cover the real need; a chat system is a much bigger commitment
  and is explicitly deferred.
- **Payment provider** — Phase 11 waits for your decision.
- **How much tenants should see** — for example whether a tenant ever sees an audit trail of changes to
  their own lease. Easy to add later, and better decided with real usage in front of us.

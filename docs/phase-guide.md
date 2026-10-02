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
| 3 | Lease management | Complete | Put a tenant on a lease, activate it, and read it as that tenant |
| 4 | Rent ledger | Complete | See what every tenancy owes, charge rent, record payments, and correct mistakes without erasing them |
| 5 | Tenant dashboard | Complete | What is due now, when the next rent falls due, when your lease ends, and your statement — on a phone |
| 6 | Document management | Next | — |
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

**What exists now:** properties with an address, notes, a type (Residential or Commercial), an "in
service" flag, a map pin and a banner photo; units inside a property with an identifier, an optional
square footage, amenities, bedrooms and bathrooms for units in a residential property, and an "in
service" flag; staff screens to list, search, create, edit and retire both, with the unit list grouped
under the property it belongs to; and counters on the staff landing page.

**What you can do today:** build the portfolio; upload a photo per property; paste a Google Maps link
(full or shortened) or coordinates to pin a property on a map; retire a unit or building without losing
its history; see how many properties, units and tenants there are.

**Deliberate decisions worth knowing:**

- A unit is named by its own identifier, with the property underneath it ("Storefront" / "- 910 Stark"),
  because that is how staff talk about units.
- **The Residential/Commercial designation belongs to the building, not the unit** — that is how staff
  talk about these properties ("the Stark Street shops"), and a mixed-use building cannot be expressed
  now that it does. `docs/decisions/ADR-006-…md` records the trade-off.
- Units carry their own **square footage** and **amenities**; nothing is required, and a blank size says
  "not recorded" rather than showing a zero.
- Bedrooms and bathrooms describe *residential* space, so a unit in a commercial **property** cannot
  carry them and the screen says "Not applicable" rather than "Not recorded" (which would imply missing
  data). A property with such detail cannot be switched to commercial until it is cleared — the refusal
  names the units rather than silently wiping them.
- A building with units **cannot** be deleted — the database refuses. Retiring is the everyday action;
  deleting is for mistakes and is admin-only, behind a confirmation page.
- Occupancy is not guessed. Until leases exist there is no such thing as an occupied unit, so the pages
  label the gap instead of showing a zero.

**What it deliberately does not do:** leases, occupancy, vacancy, rent (Phase 3 and 4); tenant documents
(Phase 6); maintenance history (Phase 7). The property page says so on screen, in a "Not tracked here
yet" panel.

**What later phases will change here:** **Phase 3** has now filled the two panels Phase 2 left labeled —
"occupants and active leases" on a property and the "Tenancy" panel on a unit — and switched the occupancy
counters on. **Phase 6** takes over document handling and will also give banners thumbnails and
resizing, and will move the single lease file into the documents table. **Phase 9** replaces the
counters with the real dashboard. **Phase 10** reports on the portfolio (rent roll, occupancy).
**Phase 12** adds the content-security entry for the embedded Google map and the operational parts of
file handling.

**How to check it:** `/manage/properties/` and `/manage/units/` as a manager or admin; open a property
and look at the map and banner; try to delete a building that has units and read the refusal.

---

## Phase 3 — Lease management (complete)

**In one sentence:** the lease is the record that connects a unit to the people renting it — and it is
where the tenant portal begins.

**What exists now:** a lease desk at `/manage/leases/` where a manager or admin creates a lease against a
unit, adds one or more tenants and marks one as the primary contact, records the term, monthly rent,
deposit and rent due day, attaches the signed lease as a PDF or a scan, and moves the lease through
*draft* → *active* → *ended*; a property page that shows which units are rented and to whom; a unit page
whose "Tenancy" panel is real; occupied/vacant counters on the staff landing page; and a tenant page at
`/lease/` showing that tenant's unit, term, rent, deposit, co-tenants and their copy of the document.

**What you can do today:** write a lease and keep it as a draft while the details are settled; activate
it when the tenant takes the keys; correct the rent or dates while it is a draft, and the rent on an
active lease; end a lease when the tenancy finishes; see at a glance which units are occupied, which are
vacant, and which leases run out within the next 30 days; sign in as a tenant and read your own lease.

**Deliberate decisions worth knowing:**

- **A unit can only have one active lease.** The database enforces it, so a unit cannot be rented twice even
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
  it is not counted as available to rent.

**What it deliberately does not do:** no balances, charges or payments (Phase 4); no tenant dashboard
(Phase 5); no documents area beyond the single lease file (Phase 6); no electronic signatures, and no
automatic renewal, proration or late fees.

**What later phases will change here:** **Phase 4** has now turned the stored rent and due day into a
real ledger, implemented the month-end rule for a due day of the 31st, and started writing lease status
changes to the audit table. **Phase 5** grows `/lease/` into the tenant dashboard with balances.
**Phase 6** moves the single lease file into the documents table (categories, visibility, several files)
and generalises the access rule. **Phase 9** and **Phase 10** report on occupancy and the rent roll.
**Phase 12** puts the document access rule through the security test pass.

**How to check it:** as a manager, go to `/manage/leases/` and create a lease for one of your units with
a tenant and a term; save it as a draft, then activate it. Then try to create a second active lease on
the same unit — the unit no longer appears in the picker, and the database would refuse it anyway. End
the lease and notice that the edit page turns into a read-only record. Finally, sign in as that tenant
and open `/lease/`.

---

## Phase 4 — Rent ledger (complete)

**In one sentence:** a truthful running account of what each tenancy was charged and what was paid, so a
balance is something derived rather than typed in.

**What exists now:** an accounting area at `/manage/ledger/` listing every live tenancy with what it owes
overall, what is past due, and what is coming due (dated whether or not the month has been raised), with
totals across the portfolio and a filter for accounts in arrears; a ledger for each lease showing every
charge (with its state: unpaid, partly paid, payment pending, paid, past due) and every payment, merged
into one activity list, plus a History panel recording who did what; buttons to create the missing monthly
rent charges, add a one-off charge, and record a payment as cleared or pending; and a panel on the
tenant's own pages.

**What you can do today:** see at a glance who owes what, who is behind, and what falls due next; generate
a month's rent for a tenancy (running it twice does nothing the second time); charge a one-off amount, such
as a recharge or a part month; record money received, or money you are expecting, and mark the expected
money as cleared when it arrives; reverse a payment that should never have been recorded; correct a charge
without altering it, by adding an adjustment that says what was wrong and why; and let a tenant see what
they owe now and their own history.

**Deliberate decisions worth knowing:**

- **No balance is stored, and no charge's status is stored.** Both are worked out from the entries every
  time they are shown, so the ledger and the balance cannot disagree, and there is no nightly
  recalculation to go wrong.
- **Nothing is edited and nothing is deleted.** A mistake is corrected by adding a reversal (for a
  payment) or an adjustment (for a charge), which leaves the original visible with both entries on the
  record. The database refuses to delete a lease or unit that has money history.
- **Payments settle the oldest charge first**, and a credit settles the charge it corrects — which is
  what makes "partly paid" mean the charge at the front of the line.
- **Expected money is not money.** A pending payment does not reduce a balance; it marks the charge it
  would settle as "payment pending" so nobody chases it by mistake. Voiding is for money that never
  arrived; reversing is for money that did.
- **Rent is charged on demand, one month at a time, never twice for the same month, and never beyond the
  tenancy's own end date.** A due day of the 31st means the last day of a short month (28 February, 30
  April).
- **A tenancy starting mid-month is not prorated.** The desk adds a one-off charge for the part month.
  Proration is not in the specification, and guessing at it would make every later report argue about
  which months count.
- **Managers record money; administrators correct it.** Reversals and adjustments are admin-only, on the
  same principle that deleted records are: the everyday act is the manager's, the act that changes what
  the history means is not.
- **The deposit stays off the ledger.** It is held money, not rent paid ahead: counting it would show a
  tenant "in credit" for a deposit they will get back.
- **Every change is recorded with a name against it** — in an audit table, in the same database
  transaction as the change itself, so a balance and the story of how it got there can never disagree.
- **Correcting a charge is one submit.** The adjustment screen arrives with the amount filled in at
  what is still owed, so a charge raised in error can be zeroed without arithmetic; a second button
  credits the charge's full amount for the case where part of it was already paid.

**What it deliberately does not do:** no late fees, interest or proration; no invoices or receipts; no
deposit returns or deductions; no automatic payment collection, and no card or bank details are stored
now or later (Phase 11 hands that to a payment provider). The tenant page shows a balance, not the full
dashboard — that is Phase 5.

**What later phases will change here:** **Phase 5** turns `/lease/` into the tenant dashboard, with the
balance as one card among several. **Phase 8** sends the reminders and receipts this ledger implies.
**Phase 9** replaces the staff counters with the real dashboard and adds the audit browser; the audit
table already holds what those screens will read. **Phase 10** reports on money (collected, outstanding,
rent roll). **Phase 11** integrates a payment provider — the pending/cleared states and the provider
reference already exist for it — and will decide whether payments need to be applied to named charges
rather than oldest-first. **Phase 12** puts money through the security test pass and decides whether the
append-only rules need database-level enforcement.

**How to check it:** open `/manage/ledger/` as a manager; activate a lease, open its ledger and press
*Create rent charges*; add a charge and record a payment, then a partial payment on another lease and
watch the state change to "partly paid"; record a payment as pending and see that the balance does not
move; as an admin, open a charge and press *Adjust* — the amount arrives already holding what is still owed,
so adding a reason and submitting zeroes the charge; reverse a payment and confirm the original is still
on the ledger with a reversal beside it; finally, sign in as the tenant and read the balance panel on
`/lease/`.

---

## Phase 5 — Tenant dashboard (complete)

**In one sentence:** one page that answers the five questions a tenant actually has — three of them today,
and two labelled until the phases that build them arrive.

**What exists now:** a tenant who signs in lands on their dashboard at `/account/` — a thin banner naming
their unit and building, then **what is due now** (or that they are in credit, or that nothing is owing),
**when the next rent falls due and how much**, and **when their lease ends**; then quick actions (their
lease, their payment history, their contact details); then their recent activity; and a **statement** at
`/payments/` where every charge shows what it costs now, what has been paid against it, and what is left,
with payments in the same list.

**What you can do today:** as a tenant, see at a glance what you have to pay now, how much of it is already
late and since when, and when the next rent is due and how much it will be; read the whole history of what
you were charged and what you paid; follow the links to your lease and your contact details; and do all of
it on a phone, in one column, without scrolling sideways.

**Deliberate decisions worth knowing:**

- **It is the page tenants land on**, not a page they have to find: `/account/` is already where signing in
  takes them, and staff are still sent to the management area rather than shown a refusal.
- **No greeting, no thanking, no personality.** The banner carries the facts — the unit and the building —
  and the portal does not address the reader. Removed on review, deliberately, so it is not re-added.
- **The headline is what is due now, not the whole term.** "Due now" is what the tenant is being asked for
  today, with "$4,588.00 past due · since July 5, 2026" beneath it when part of it is late. The whole
  lease's remainder is an office figure and stays on office screens: a term's arithmetic in the largest
  type reads as a demand nobody is making (ADR-012).
- **"Next rent due" is the incoming month**, whether or not the office has raised it yet — the lease says
  when rent falls due, so the card is never empty because nobody pressed a button. An ended lease says no
  further rent falls due.
- **Billed but not yet due is stated, never headlined**: one muted sentence, with the months listed in the
  statement below it.
- **The tenant and the office see the same numbers**, read two ways. The office reads entries — a charge,
  and separately the correction that changed it, with who made it and why. The tenant reads a statement,
  where a correction is absorbed into the charge it corrects: a charge raised at $2,084 and cancelled
  reads **$0.00, nothing to pay**, not "+2,084 then −2,084". Neither reading can disagree with the other,
  because both come from one derivation of the same records (ADR-011).
- **Paid money and credited money are shown differently.** A correction never appears as a payment. Each
  charge states its own settlement ("paid $400.00 of $1,000.00"), which is what connects the two.
- **The statement is paginated**, so a long tenancy reads a page at a time instead of growing without end.
- **Expected money is labelled as expected.** A payment that has not arrived is shown as "expected" and
  does not reduce the balance, move what is due now, or stop a charge being late.
- **Maintenance and announcements are sentences, not dead buttons.** They arrive with Phases 7 and 8, and
  the page says so rather than pretending. Nothing is shown as a zero that isn't real.
- **The tenant's payment history hides voided entries.** A void row is office bookkeeping, not the
  tenant's business.
- **A tenant with no lease is told so plainly** — no balance of zero dressed up as a fact.

**What it deliberately does not do:** no maintenance requests (Phase 7), no announcements or messages
(Phase 8), no documents (Phase 6), no payments taken through the site (Phase 11). It adds no new data of
its own — everything on it is derived.

**What later phases will change here:** **Phase 6** gives the dashboard documents and a document list.
**Phase 7** fills the maintenance panel with live requests and a way to raise one; **Phase 8** fills the
announcements panel. **Phase 9** consolidates the dashboards (staff and tenant) once there is more than
one. **Phase 11** may put a "pay now" action on the due-now card, once a provider is chosen.

**How to check it:** sign in as your tenant account and look at `/account/` — the banner, what is due now,
the next rent and the lease end date should all be right, and it should read comfortably on your phone.
Then open `/payments/` and read the statement: each charge should show what it costs now and what is paid
against it, with no charge and its correction sitting as two opposing amounts. Payments are recorded by the
office on the lease's ledger, so to see something move: record a payment at `/manage/ledger/`, then look
again as the tenant.

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
and to the property page. Direct messaging is evaluated afterward rather than assumed.

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
| Tenant dashboard | Phase 5 | Phase 6, 7, 8, 9 | Gains documents, live maintenance and announcements; Phase 9 consolidates the dashboards |
| Reading money as a tenant | Phase 5 review | Phase 10, 11 | The statement nets corrections and pages; reports and a payment provider will each need their own reading of the same records (ADR-011) |
| Tenant payment history | Phase 5 | Phase 11 | May gain a "pay now" action once a provider is chosen |
| Single lease file | Phase 3 | Phase 6 | Becomes documents in the documents table (categories, visibility, multiple files) |
| Lease document access rule | Phase 3 | Phase 6, 12 | Generalised to all documents; included in the security test pass |
| Tenant `/lease/` page | Phase 3 | Phase 4, 5 | Phase 4 added the balance and activity; Phase 5 added the dashboard beside it, so this page stays the lease detail |
| Occupancy / vacancy definition | Phase 3 | Phase 9, 10 | Reported on in the dashboard and the occupancy report |
| Staff landing counters | Phases 2, 3, 4, 7 | Phase 9 | Replaced by the real admin dashboard |
| Rent due day (stored) | Phase 3 | Phase 4 | Done: the month-end clamping rule lives in `apps.common.dates.due_date_in` |
| Lease status changes | Phase 3 | Phase 4 | Done: they are written to the audit table, not only the log |
| Structured security logs | Phases 1, 2 | Phase 4, 12 | Phase 4 added the audit table; Phase 12 decides retention and whether the append-only rules need database enforcement |
| Banner photo | Phase 2 | Phase 6, 12 | Thumbnails and resizing; content-security policy for the map |
| Map pin | Phase 2 | Phase 12 | The Google embed becomes an explicit security-policy entry |
| Bedrooms / bathrooms | Phase 2 | Phase 10 | Used for sizing and rent-roll reporting |
| Tenant contact notes | Phase 1 | Phase 5+ | Surface on the tenancy screens once tenants have a dashboard |
| Invitations and passwords | Phase 1 | Phase 12 | Two-factor authentication for staff; session hardening |
| Property / unit retirement | Phase 2 | Phase 10 | Retired records stay in reports as history |
| Residential/commercial designation | Phase 2 | Phase 4 review | Moved from the unit to the property; the unit list is grouped by building (ADR-006 revision) |
| Unit size and amenities | Phase 2 | Phase 4 review, 10 | Square feet feeds sizing reports; the amenity list is maintained in the back office |
| Tenant photo | Phase 1 | Phase 4 review, 12 | Admin-set for now; Phase 12 puts personal data through the security pass (ADR-009) |
| Money fields | Phase 3 | Phase 4, 11 | Phase 4 reads them in the ledger; Phase 11 reconciles provider payments against entries |
| Balance and charge states | Phase 4 | Phase 9, 10, 11 | Reported on in the dashboard and the money reports; a provider may need payments applied to named charges rather than oldest-first. Phase 5's review split the one balance into what is due now, what is past due and what is coming due (ADR-008, ADR-012) |
| Audit trail | Phase 4 | Phase 9, 12 | Phase 9 adds the audit browser; Phase 12 decides retention |

## Open questions worth deciding later

Collected on purpose, so nothing is forgotten and nothing is decided by accident:

- **Month-to-month leases** — the lease term currently needs both a start and an end date. If RHP takes
  on month-to-month tenancies, the end date becomes optional and the screens need a "no fixed end" state.
- **Proration, late fees, rent escalation** — none of these are in the specification. Phase 4 decided the
  interim: a tenancy starting mid-month is not prorated, and the desk records a one-off charge for the
  part month. If RHP starts charging late fees or raising rent on a schedule, that is its own small phase
  rather than a rule bolted onto the ledger. The one hook that exists is `Lease.rent_for(on_date)`, which
  every caller asks instead of reading `monthly_rent` — a rent schedule answers there, and nothing else
  changes (ADR-012).
- **Deposits** — decided in Phase 4: the deposit stays a field on the lease and is deliberately **not**
  on the ledger, because held money is not rent paid ahead. When deposit returns and deductions are
  needed, they get their own treatment (what was withheld, and why) rather than being folded into the
  rent balance.
- **Correcting an ended lease** — the lease terms are read-only once ended; the *money* on an ended lease
  is still correctable in Phase 4 (adjustments and reversals work on it), which covers most of the need.
  A formal amendment flow for the lease terms themselves remains open.
- **Renewing a lease** — there is still no "copy this lease forward" action, so a renewal is typed again
  from scratch. Once real tenancies start rolling over, that will be the most common repetitive job on
  the desk and worth its own small piece of work.
- **Who is liable for the rent** — a lease records a primary *contact*, not a payer, and Phase 4 put the
  balance on the **lease**, shared by everyone on it. If RHP needs joint-and-several liability, split
  responsibility, or a guarantor, that reaches back into the lease's tenant rows and into how a payment
  is attributed.
- **Applying a payment to a named charge** — Phase 4 applies money oldest-first, which is what a rent
  ledger does. If a payment ever needs to say which charge it settles, that is an allocation table, and
  Phase 11 (a provider sending remittance detail) is where it will earn its keep.
- **Invoices, statements and receipts** — nothing in the ledger produces a document yet. Phase 6 adds
  document handling, so a statement or a receipt becomes possible there; whether RHP wants them is a
  question for you.
- **Direct messaging** — announcements cover the real need; a chat system is a much bigger commitment
  and is explicitly deferred.
- **Payment provider** — Phase 11 waits for your decision.
- **How much tenants should see** — Phase 4 shows a tenant their balance, next amount and activity, but
  not the audit trail behind it. Whether a tenant ever sees the history of changes to their own lease is
  easy to add later, and better decided with real usage in front of us.

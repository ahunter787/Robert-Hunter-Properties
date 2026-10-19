# Phase 7 — Maintenance system

**Status:** Complete
**Milestone:** 4 — Documents and maintenance requests work end to end
**Specification:** `docs/harness/master-spec.md`, `PHASE 7 — MAINTENANCE SYSTEM`

## Scope as specified

A complete maintenance workflow. A tenant can submit a request with a category, title, a detailed
description, photos and an indication of permission to enter, and can follow its status and the management
updates. Staff get a queue filtered by property, status and age, with assignment to an employee or a
vendor, priority, status transitions (`OPEN → ACKNOWLEDGED → SCHEDULED → IN_PROGRESS → WAITING →
COMPLETED → CLOSED`), internal notes, and tenant-visible updates. The request reads as a timeline.
**Internal comments are never exposed to tenants**, and attachments are permission-checked.

## What exists today

Implemented and verified on `rhp-7`, accepted for local merge October 18, 2026:

Local `main` now includes the Phase 7 squash commit `6a492b6`. The prototype/design baseline and
Phase 8 scope-only records are separate commits. No push was performed. Subsequent E11 work is
on `codex/operations-desk` and remains uncommitted.

- `apps/maintenance` owns physical requests, explicit lease audiences, chronological updates,
  immutable note revisions, private attachments, reusable vendors, append-only costs and corrections,
  recharge links, notification delivery state, and individual immutable delivery-attempt records.
- `/maintenance/` scopes tenants to their own audiences, including former-tenancy read-only history.
  `/manage/maintenance/` gives managers portfolio-wide work and employees assigned requests only.
- Managers can share staff-only requests explicitly, assign/schedule work, close/reopen it with reasons,
  review unresolved follow-ups, record expenses, and review manual charge splits before confirmation.
- Signed recharge reviews expire after 30 minutes, bind actor/cost/current state, lock request and lease
  rows at confirmation, and post through the ledger. Duplicate confirmation is idempotent. Totals
  include immutable corrections and prior net charge adjustments; no liability or ceiling is inferred.
- Downloads use UUID URLs and parent authorization. Admin removal retains metadata and audit history;
  direct development media serving is removed. File writes are cleaned up on submission failure.
- Email uses existing Django configuration after commit, contains a neutral portal link, and never
  includes note bodies, financial evidence or another tenancy's identity. Managers see attempts/failures
  and explicitly retry. Saved requests survive mail failure; no queue dependency was added.
- Tenant/staff dashboards and property/unit pages link to meaningful scoped maintenance summaries.

Foundations reused:

- **The tenant area and its navigation**, the permission mixins, and existing tenancy memberships.
  Maintenance uses its own audience/assignment scope, not the generic staff-wide `tenant_scope`.
- **The photo pipeline** (`apps/common/images.py`) for attachment validation, and the permission-checked
  download pattern for anything a tenant uploads.
- **The audit table**, which already records who did what and when — the basis for a timeline that must
  distinguish tenant-visible from internal events.
- **Dashboard and portfolio detail integration:** property/unit maintenance summaries and dashboard
  counters now link to their scoped request queues.
- **The mail sink** (`http://10.60.0.227:8025` in development) for notification email.

## Decisions that govern it

The governing decision is [ADR-023](../decisions/ADR-023-maintenance.md). The owner answered all five
planning questions in Plane (RHPDEV-98), confirmed in chat on October 16, 2026. The full answers
are preserved below. The implementation plan was subsequently approved, including explicit
sharing of staff tickets, manager-controlled closure/reopening, and reviewed manual recharge
splits. They govern this design:

- Tenants and managers/admins can create requests against properties or units. A request's
  physical location is not a determination of who is responsible for the work or its cost.
- Preserve the reporting tenancy for tenant authorization and private history; allowing
  property/unit requests does not grant tenants access to another tenancy's requests.
- Record repair costs and offer an explicit, separately reviewed one-off recharge linked to
  the request. Never infer liability or create a charge merely because work was requested,
  assigned, completed, or performed by RHP. Existing ended/settled-account guards still apply.
- Staff can add internal notes and tenant-visible updates within their authorized request
  scope; edits retain an audit trail. Managers remain portfolio-wide, while maintenance
  workers are limited to assigned work. Internal notes never appear in tenant views or emails.
- Keep minimal reusable vendor records, without a vendor portal. Notify tenants by email on
  submission and tenant-visible updates, linking back to the request in the portal.

## Extensions filed under this phase

None. **P4-E2** (expense recoveries) is adjacent and has a deliberate boundary: a
`ResponsibilityCycle` already models "a recurring property cost, split across the units", which is how RHP
recovers maintenance from tenants. A Phase 7 request is work *to be done*; a P4-E2 cycle is cost *to be
recovered*. A one-time repair recharge instead links the maintenance expense directly to a normal
one-off ledger charge; it never creates a recurring recovery cycle.

## Acceptance criteria and evidence

Implemented, with service/HTTP tests and authenticated disposable browser evidence:

- [x] A tenant sees changes clearly (status and their own tenancy updates only)
- [x] Staff have an actionable queue with property/status/age/priority/assignment/follow-up filters
- [x] Internal comments and other tenancies' conversations/identities are excluded server-side
- [x] Images and cost evidence have parent-scoped permission checks and upload limits
- [x] Decimal expenses and reviewed manual recharges retain immutable history and existing charge locks
- [x] Concurrent duplicate recharge confirmation posts once; preview, Back and Cancel do not post
- [x] Desktop (1280×900) and phone (390×844) browser review; labeled controls, keyboard submission,
      and a verified `script-src 'none'` QA backend for plain-form recharge/follow-up operations
- [x] Full project gates, migration checks and smoke start
- [x] Outline/Plane publication and ecosystem verification

Final verification, completed October 17, 2026:

- `make test`: **941 passed, 1 skipped**; the skip is the opt-in live-browser harness, not a product test.
- **62 maintenance service/HTTP/concurrency cases**, including changed tenancy rosters invalidating
  signed charge reviews, explicit queue follow-up labels, and individual email-attempt history.
- Opt-in authenticated browser harness: **1 passed**, including script-blocked recharge/follow-up
  forms and clean teardown. Desktop/phone screenshots were captured using disposable test records.
- `make lint`, `make check`, `make check-deploy`, `makemigrations --check --dry-run`,
  `make migrate-check`, `make assets`, and `git diff --check`: passed.
- Five migrations applied: `audit/0009` and `maintenance/0001`–`0004`. Existing lease/document/ledger
  history is unchanged. New cost, request, audience, attachment and delivery records have their own tables.
- Fresh smoke process: `/healthz` and `/` returned 200; tenant/staff maintenance endpoints returned
  authentication redirects. Temporary smoke servers were stopped; no test users were created in the
  development portfolio.
- Legacy migration tests now restore every schema head, preventing historical-schema state from
  leaking into later transactional tests. The full rerun passed after that isolation fix.
- Published ADR-023 and updated records to Outline and Plane. `make -C ecosystem verify` passed:
  49 engineering documents and 23 mirrored work items agree with the checkout; ten manually raised
  Plane items remain untouched. Both syncs report no further changes.

The opt-in browser harness is `tests/test_maintenance_browser.py`; it creates disposable users and
leases in PostgreSQL's test database, not the real development portfolio. The first full browser
workflow passed but exposed a test-server DB-connection teardown error. The corrected script-blocked
rerun passed with clean teardown. Page scripts were blocked by an actual response CSP, not merely
left unused. No real tenant charge or operational request was created for browser QA.

## Deliberately not here

Direct messaging with a tenant (Phase 8 evaluates it), a vendor portal, and any scheduling or dispatch
integration. General-ledger/property accounting remains the future RHP-owned-property
extension (E10). Recording repair costs and offering a reviewed one-off recharge are approved
here (P7-Q2); neither creates a second ledger or changes P4-E2's recurring expense allocation.

## Known gaps and defects

Owner review RHPDEV-98 identified two corrections, approved October 17, 2026:
property-scoped unit selection with a non-writing location step, and explicit tenant entry
authorization using a checkbox. Managers recording offline authorization require a private
source note; permission edits initialize from the selected audience's saved state. These
are implemented on `rhp-7`. The broader visual review is E11, a study rather than a
production redesign; see [Design](../design/README.md).

Owner-review verification: **68 maintenance service/form/HTTP cases passed**. Disposable
authenticated browser review passed separately with JavaScript enabled and with scripts blocked
by response CSP. Both exercised property-first selection and documented manager withdrawal;
the tenant phone review confirmed the saved checkbox and absence of the staff source-note field.
The screenshots use synthetic accounts and are retained with the Design study. No new migration
or dependency is introduced by these corrections. An earlier overlapping QA launch contaminated
only the disposable test database; that run was discarded, the test database recreated, and
browser reviews were rerun sequentially with clean teardown. No development-portfolio records
were changed.

Final correction gate, October 17, 2026: `make test` **951 passed, 1 skipped** in 267.14s;
the opt-in browser harness passed separately in both corrections modes. Lint, Django and
deployment checks, migration checks and fresh smoke start passed. No additional migrations
were needed. The Diagram skill validates, and Design uploads match all 45 source hashes.

No known failing test remains. SMTP acceptance is not guaranteed inbox delivery;
an interrupted send can leave an attempt requiring manager review/retry. No background worker or
automatic retry is provided. The owner accepted the baseline and authorized local commits/merge
on October 18, 2026. No push or later-phase feature implementation is authorized.

## Open questions for the owner

The table is the index — those are the ids the plan tooling reads. **The answers are the bullets
below it**, so an answer can run as long as the question deserves without being squeezed into a
cell.

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P7-Q1 | Is a request about a **unit**, a **tenancy**, or a **property** (a shared roof, a parking lot)? | The request names a unit or a property; a common-area request is property-level. Tying it to a tenancy hides it the moment the tenant moves out. | *(below)* |
| P7-Q2 | Should a maintenance **cost** be recorded in RHP, and should it be rechargeable to the tenant? | Record the cost on the request and let it *offer* a recharge — charged as a one-off ledger charge, linked back to the request. That link is what P4-E2's cycles cannot express. | *(below)* |
| P7-Q3 | Who may add an internal note versus a tenant-visible update, and can a manager edit the other's? | Any staff role may add either; internal notes are visible to staff only and never editable by a tenant. An edit leaves the audit trail. | *(below)* |
| P7-Q4 | Do you want vendors as records (name, contact, trades), or just a free-text name? | Records, but minimal: name, contact, trades, active. Reuse them from the request and report on them in Phase 10. | *(below)* |
| P7-Q5 | Do you want notification email to the tenant, or is seeing it in the portal enough? | Email on submission and on each tenant-visible update; the tenant can be told to reply in the portal. The mail sink makes this safe to develop. | *(below)* |

### The answers, in full

- **P7-Q1 — Is a request about a unit, a tenancy, or a property (a shared roof, a parking lot)?**

  **Owner answer, Plane RHPDEV-98; confirmed October 16, 2026:**

  > Given the scope of the project has increased to eventually becoming a full property
  > management utility, this system becomes a core function for the manager to track expenses.
  >
  > This is another area that turns grey in real world scenarios. Often an A/C unit should be
  > replaced, which may be the duty of the tenant, but Robert (or another manager someday),
  > will do it instead to ensure a quality standard is maintained. For now, maintenance tickets
  > are too grey for this RHP management system to enforce hard rules (like whose responsibility
  > it is).
  > That being said, both the Tenant accounts, and the Manager/Admin accounts should be able
  > to post maintenance tickets onto Properties/Units.

  **Design consequence:** support tenant- and staff-created requests at a property or unit.
  Keep physical location, reporter, assigned worker, recorded cost, and a decision to recharge
  distinct. Do not automate a tenant/landlord responsibility classification.

- **P7-Q2 — Should a maintenance cost be recorded in RHP, and should it be rechargeable to the
  tenant?**

  **Owner answer:** "Use recommended."

  Record costs on the request; offer a separately confirmed one-off ledger charge linked back
  to the request. Charging remains an explicit manager act, never an automatic consequence of
  who reported or performed the repair. Respect existing account and occupancy guards.

- **P7-Q3 — Who may add an internal note versus a tenant-visible update, and can a manager edit
  the other's?**

  **Owner answer:** "use recommended"

  Staff may add internal notes or tenant-visible updates within their authorized scope.
  Internal notes remain staff-only, tenants cannot edit them, and edits preserve an audit trail.
  The portfolio-wide manager and assigned-work-only maintenance boundaries remain in force.

- **P7-Q4 — Do you want vendors as records (name, contact, trades), or just a free-text name?**

  **Owner answer:** "recommended"

  Use minimal vendor records: name, contact information, trades, and active status. Reuse these
  when assigning work; do not introduce a vendor login or portal.

- **P7-Q5 — Do you want notification email to the tenant, or is seeing it in the portal enough?**

  **Owner answer:** "recommended"

  Send email on submission and on tenant-visible updates, with a link back to the request.
  Internal notes must never trigger tenant-facing content. Develop notification delivery using
  a safe test backend or the mail sink, not real tenant email.

## How to verify it

Run `uv run pytest tests/test_maintenance.py` against the isolated PostgreSQL test database for
authorization, money, status, files and mail checks. Run the full gates in the approved plan.
Historical migration tests restore all migration heads before later transactional tests run.

For authenticated browser review, use the opt-in disposable harness:

```bash
RHP_BROWSER_QA=1 uv run pytest tests/test_maintenance_browser.py -s --liveserver=localhost:8011
```

It prints test-only accounts and blocks page scripts with a test-only CSP middleware. Complete the
tenant submission → manager assignment → worker completion → manager closure → tenant unresolved
follow-up, then record an expense and review/confirm a manual recharge. Use desktop and phone widths,
keyboard controls, and verify tenant pages omit internal notes and repair costs. Close browser tabs
before pressing Enter to finish and clean up. `RHP_BROWSER_QA=noscript` seeds a closed request and an
expense for a shorter plain-form follow-up/recharge regression. Never run another DB suite alongside
this live-server harness; neither mode touches the development portfolio.

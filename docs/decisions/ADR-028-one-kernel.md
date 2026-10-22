# ADR-028 — One accounting kernel, built to the industry's shape

- **Status:** Accepted for implementation, 2026-10-21. Owner-directed: where RHP's early accounting
  choices differ from established property-management practice, industry practice decides; RHP's
  groundwork is retained rather than rebuilt.
- **Date:** 2026-10-21
- **Related:** [ADR-007](ADR-007-lease-modeling.md) (lease lifecycle), [ADR-008](ADR-008-rent-ledger.md)
  (append-only sub-ledger), [ADR-016](ADR-016-retroactive-onboarding.md) (E4, retired here),
  [ADR-017](ADR-017-charge-lifecycle.md) (what ending does to money), [ADR-020](ADR-020-tenancy-lifecycle.md)
  (occupancy vs account), [ADR-026](ADR-026-property-accounting.md) (the GL is built in),
  [ADR-027](ADR-027-simple-cutover.md) (starting balances), the
  [cutover plan](../design/accounting-cutover-plan.md), [held-credit refinement](../design/held-credit-repayments.md)
  and [accounting blueprint](../design/property-accounting.md); kernel vocabulary in
  [`docs/kernel/events.md`](../kernel/events.md) and [`docs/kernel/scope.md`](../kernel/scope.md).
- **External research (read-only, outside this repository):** the TenantCloud/TurboTenant study at
  `../tenantcloud/findings/` — `00-overview.md`, `02-domain-model.md`, `07-rhp-applicability.md`,
  `10-capability-parity.md`. It is observation and judgement, not a specification; nothing from it is
  copied here.

## Context

RHP is a development-stage portal whose foundation is sound enough to keep: one Django monolith,
server-side role gating, tenancy-scoped queries, append-only money with derived balances,
permission-checked documents, and a test suite of 1,185 passing tests. Its **accounting core** is where
early choices were made quickly, and two of them produced the disease this ADR treats:

1. The E10 cutover replaced the E4 retroactive-onboarding design but did not finish the deletion. The
   tree carries two opening-balance models (`LeaseOpeningRecord` and `LeaseOnboarding`), two allocation
   engines (read-time FIFO and persisted `FundsApplication` rows chosen by an `AllocationAccount`
   marker), and one direct cross-app `Charge` write in the cutover that bypasses the ledger service and
   its `CHARGE_CREATED` audit event.
2. The owner's instruction is explicit: RHP is still in development, early accounting decisions may have
   been naive, and **the core accounting should not keep a method that established property-management
   products do differently**. A full rebuild is unnecessary — but "we already built it this way" is not
   a reason to keep a non-standard method.

The question this ADR answers is therefore not "what would be nice" but: *what do the products that do
this for a living actually do, and which parts of RHP already match?* The evidence below is drawn from
public product documentation; the study supplies the TenantCloud/TurboTenant observations it already
made (lease `FUTURE` status; `Contact` separate from `User`; upcoming/current/past lease states).

## Evidence — how established products model this

| # | Practice | Source | What it shows |
| --- | --- | --- | --- |
| 1 | **Security deposits are held/escrow liabilities**, recorded through the move-in workflow and released at move-out with itemised, documented outcomes | AppFolio trust structure: the Security Deposit account is an **escrow liability**; Buildium: deposit recorded to **escrow** at move-in, a **Security Deposit Liability report**, and three move-out outcomes (full refund, itemised deductions with partial refund, full withhold) with written reasons | The lease's deposit *term* is not the same fact as money *held*; both must exist, and the liability must reconcile |
| 2 | **Advance rent is a liability (prepayment)**, not income and not AR | AppFolio: the Prepayment account holds advance rent | Rent received before it is earned is held, not income; a credit is not a negative charge |
| 3 | **Every transaction names a property**; the GL is property-dimensioned | AppFolio: no transaction can post without a property; three-way reconciliation closes statement, cleared and adjusted balances | The tenant sub-ledger and the GL meet through the property, not through a second set of numbers |
| 4 | **Lease statuses include a future/upcoming state and a past state** | Buildium `lease_status` includes Future and Past ("set the lease status to past when the lease ends"); TenantCloud `LeaseStatus` has `FUTURE`; TurboTenant live shows Upcoming/Current/Past/Draft (study `02-domain-model.md`, `10-capability-parity.md`) | A signed tenancy that has not started is a first-class state, distinct from active and from draft |
| 5 | **A person is a record; portal access is an optional grant** | PropertyBoss: contacts/tenants are records with a separate "Allow Login to Web Portal"; Buildium's tenant entity has optional email and is distinct from its owner/user entities | A tenant record must outlive a login: former tenants, paper-only people, guarantors |
| 6 | **Payment application is recorded**, and can be customised | Buildium "Custom Payment Allocation": how a payment applies to charges is a recorded decision, not a recomputation | Durable allocations are the industry shape; read-time FIFO is a shortcut |
| 7 | **Conversion enters carry-forward tenant balances as a charge or a credit** | DoorLoop: beginning balance owed = a charge with a "Carry-forward balance" description; starting credit = an "Issue Credit" with the Opening Balance category; TurboTenant: opening-balance transactions at a bookkeeping start date | The E10 `LeaseOpeningRecord` + linked `OPENING` entry is right in shape; history is not reconstructed |
| 8 | **Receipt is not bank settlement** | AppFolio: a manual receipt must be added to a **deposit** before funds are available for payments or reconciliation | Two events, two postings: money received vs money in the bank |
| 9 | **GL, AP, banks, reconciliation and reports are built in**; external accounting is a downstream copy | [ADR-026](ADR-026-property-accounting.md) already records Buildium/AppFolio/TenantCloud/Innago and rejects GnuCash as a backend | E10 B1–B5 direction stands |
| 10 | **Immutable entries and corrections as new entries** | Buildium/AppFolio ledger practice; RHP ADR-008 | RHP's append-only, derived-balance sub-ledger already matches; do not change it |

## Decision

### D1 — One kernel home

The kernel lives in **`apps/accounting/`** (created when slice B1 starts, per
[ADR-026](ADR-026-property-accounting.md)); `apps/ledger/` remains the **tenant AR projection and desk**
(charges, payments, applications, statements). Cross-cutting rules and the event vocabulary live in
**`docs/kernel/`** — [`events.md`](../kernel/events.md) and [`scope.md`](../kernel/scope.md). No new
domain app is created before its slice.

### D2 — One opening position

`LeaseOpeningRecord` (E10) is the only opening-balance record. **Retired with the deletion work:**
`LeaseOnboarding`, `onboard_lease()`, the E4 `HISTORY`/`POSITION` workflow, `Lease.onboarding_record` /
`has_onboarding`, and `Lease.needs_onboarding` (renamed to the one gate below). Any recorded E4 decision
is preserved as an append-only audit event before its table is removed — the decision survives even
though the mechanism does not. ADR-016 remains historical; ADR-027 governs.

The surviving gate is **one predicate**, `Lease.needs_starting_account` (a tenancy from before RHP's
financial start with no starting account), consulted by the charging services and the screens. The
cutover's `eligible()` is not a second gate: it answers a different question — *may a starting account be
recorded now?* — and both are documented together in `docs/kernel/scope.md` so they cannot drift.

### D3 — One allocation engine

Only **persisted `FundsApplication` rows** allocate money. Deleted: the read-time FIFO engine
(`_allocate`), the `recorded_allocations` mode, its six `LeaseLedger` branches, the
`_ledger_allocations_ready` cache, `initialize()` and the `AllocationAccount` marker. A one-time data
migration snapshots any remaining legacy coverage into applications (with `legacy_derived=True`, the
flag kept as read-only provenance). Oldest-first remains the *rule for creating* applications; it is not
a second way to read a balance. A parity harness proves the persisted engine and the retired projection
agree on the same history before either is removed.

### D4 — One charge write path

`ledger.services.create_charge` is the only code that creates a `Charge`. It accepts an explicit
`opening=True` path for the reviewed starting account (the one legitimate case where an obligation is
created while `needs_starting_account` is true), and writes the `CHARGE_CREATED` audit event for it. The
cutover routes through the service. No general exception is added for ended tenancies: post-tenancy
charges remain E6's evidence-backed workflow (ADR-017).

### D5 — Deposits are held liabilities

The lease keeps the **agreed deposit** (`Lease.deposit`) as a term. The money is tracked by an
append-only **deposit register** (`DepositEntry`: received, returned, withheld with a reason, or an
explicit "not collected") whose derived balance is what RHP holds. A deposit is never tenant AR and never
a tenant credit; the tenant statement shows what is held, not extra credit. Move-out records the
outcome (full refund, itemised partial refund, full withhold) before the financial account can settle,
so settlement has a path instead of a dead end. GL postings (held liability, refund, retained amount)
belong to B2 and are specified in `docs/kernel/events.md`; a bank-account *kind* keeps a separate
deposit account possible where state law requires one, without a trust module. Applying withheld funds
to outstanding AR is an E5/B2 refinement, recorded as a known limitation, not hidden.

### D6 — A signed tenancy that has not started is `FUTURE` (staged)

`LeaseStatus` gains **`FUTURE`** between `DRAFT` and `ACTIVE`: a signed tenancy whose start date is
ahead. It takes no obligations, is not occupancy, and is shown as upcoming to staff and tenant.
Occupancy **starting** becomes calendar-driven and idempotent (an audited system transition on the start
date); occupancy **ending** stays a person's act with a citable reason (ADR-007/ADR-020), because ending
has a money consequence and needs a record. Migration converts existing active future-start tenancies.
Staged as M2, before E5/E6 — the kernel guard it touches is the charging predicate, not this deletion
work.

### D7 — A person is not a login (staged)

Introduce an `accounts.Person` record (name and contact facts) with an **optional** link to the existing
`accounts.User`; `LeaseTenant` references the person. `AUTH_USER_MODEL` stays `accounts.User` and there is
**no second user model** (AGENTS). Former tenants, paper-only people and (later) vendors/guarantors keep
their history without needing a login; portal access remains a grant. Until this lands, a former tenant
with arrears is a deactivated user, which persists (PROTECT). Staged as M2, before E5/E6, as its own
ADR and branch.

### D8 — Conformance table: keep, change, record

| Area | RHP today | Industry | Decision |
| --- | --- | --- | --- |
| Pending/expected payment | `PENDING` moves nothing | Expected money is not AR | **Keep** |
| Receipt vs bank settlement | `CLEARED` = office-confirmed receipt | Receipt and bank deposit are separate events | **Keep** the sub-ledger fact; **record** the mapping; B3 posts bank settlement |
| Charge and payment model | Two append-only tables, positive amounts, explicit direction | Charges/bills and payments/credits | **Keep** |
| Balance and charge status | Derived, never stored | Derived at read/report | **Keep** |
| Corrections | Adjustment/reversal entries, originals immutable | Corrections as entries | **Keep** |
| Allocation | Persisted applications (after this ADR) | Recorded, customisable application | **Keep** (adopt) |
| Opening balance | One immutable opening record + linked `OPENING` entry | Conversion charge/credit at go-live | **Keep** |
| Rent rule | Raised on its due date, never ahead (P4-Q7) | Recurring charges post on schedule | **Keep** the rule; **record** the operational gap: system-scheduled posting in Phase 12 |
| Deposit | Lease field, no disposition, settlement dead end | Escrow/held liability + disposition | **Change** (D5) |
| Lease lifecycle | DRAFT/ACTIVE/ENDED | DRAFT/FUTURE/ACTIVE/PAST/ENDED | **Change** (D6) — M2a implemented as DRAFT/FUTURE/ACTIVE/ENDED ([ADR-029](ADR-029-lease-future-and-people.md)); `PAST` stays derived/ENDED |
| Party | Person = login | Person record + optional portal login | **Change** (D7) — M2b, next slice; design in [ADR-029](ADR-029-lease-future-and-people.md) D2 |
| Property dimension | Lease → unit → property chain; E2 unit shares | Every posting names a property | **Keep**; make property mandatory on GL postings in B1 |
| GL, AP, banks, reconciliation | Absent | Built in | **Build** (ADR-026 B1–B5) |
| Trust/escrow | Out of scope (RHP owns its properties) | Trust modules exist for third-party managers | **Keep** ADR-026 boundary; deposit liability still applies |

### D9 — The event vocabulary and the five classification questions

`docs/kernel/events.md` is the one posting matrix (event, actor, trigger, source document, idempotency
key, tenancy AR posting, GL posting, notification, audit, prohibition, reversal path). The five cutover
questions are answered there before B1: **expected payments post nothing**; **receipt status is not bank
settlement**; **opening credit vs prepayment are separate liability classes, and neither is a receipt**;
**future charges are not recognised before their due date**; **every posting is idempotent per explicit
source transition**. The deposit events are included.

### D10 — Platform consolidation is deferred

The seven signed-review flows, two notification stacks, three attachment stacks and six hand-rolled
scoping methods are real duplication, but they are not this change. They consolidate into
`apps/common/` later, one primitive per reviewed change, with the security tests written first.

## Consequences

**Positive**

- One answer each to "what did this tenant owe at cutover", "how is money applied", and "where does an
  opening charge come from"; the dual-path branches disappear from every balance.
- Deposits stop being a stored number that blocks the desk and become auditable money with a move-out
  outcome, matching what the desk's peers do.
- The event vocabulary and conformance table become the testable boundary between the tenant sub-ledger
  and the GL, so B1–B5 post from one matrix instead of re-deriving.
- Future work (E5/E6) lands on a party and lifecycle model that matches the industry rather than one
  the money has to work around.

**Negative / accepted**

- The E4 workflow is deleted; any E4 placement decisions become audit events rather than live rows.
  The active database has none; the archived original is preserved untouched.
- The allocation migration is irreversible by design (like ledger 0008): restore a backup instead of
  reversing it.
- `FUTURE` and the party split are staged, so for one release a future tenancy still reads `ACTIVE` and
  an ex-tenant is still a deactivated login. That is recorded, not hidden.
- Deposit money is tracked independently of AR for now; applying withheld funds to arrears waits for
  E5/B2, and the screens say so.

## Alternatives rejected

- **Keep both engines until "later"** — the branch cost is already in four balance properties and one
  review guard; every new money feature would have to be written twice. Rejected.
- **Keep E4 as a compatibility path** — its workflow is already unreachable from the UI (the URL serves
  the starting-account flow) and its table is empty in the working database; keeping it only keeps a
  second answer alive. Rejected.
- **Widen `create_charge` for all ended tenancies** — reopens the P4-Q3 hole that ADR-017 closed.
  Only the reviewed `OPENING` path is excepted. Rejected.
- **Records the deposit as tenant AR or as a negative charge** — makes held money look like credit or a
  correction, the exact two misreadings ADR-008 warned about. Rejected.
- **Leave deposits as a lease field until E5** — keeps settlement unreachable and keeps a money fact
  outside the money system; industry holds deposits as liabilities from move-in. Rejected.
- **Adopt a `FUTURE` status without a migration plan because "the study said so"** — a new status value
  without the guard, migration and audit would be a label, not a state. Staged (M2). Rejected as an
  immediate change.
- **Split person from login by adding a second user model** — forbidden by AGENTS and unnecessary; the
  person is not an authentication subject. Rejected.
- **Copy the study's screens, schema or vocabulary into RHP** — the study is evidence, not a
  requirement; only decisions cross the boundary, recorded here by citation. Rejected.

## Open items

- B1 chart/classification of the credit and prepayment controls (kernel events records the decision; the
  chart is B1 work).
- E5 remainder: forwarding address, final statement, and withholding applied to outstanding AR.
- Phase 12: scheduled posting of recurring charges, and the browser/print verification gaps already
  recorded in the cutover plan.
- M2 design detail (FUTURE promotion points; Person migration sequence) belongs to its own ADR when it
  lands, before E5/E6.

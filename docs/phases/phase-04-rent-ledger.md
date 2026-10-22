# Phase 4 — Rent ledger

**Status:** Complete
**Milestone:** 3 — Tenants see their balance and rent due; the ledger is authoritative
**Specification:** `docs/harness/master-spec.md`, `PHASE 4 — RENT LEDGER`

## Scope as specified

Transparent accounting without processing payments: a tenant ledger, recurring monthly rent charges, manual
charges, recorded payments, reversals and corrections, adjustments, and a view of a lease's ledger. States
must distinguish unpaid, partly paid, paid, overdue and pending. The balance is derived from the entries,
financial history is immutable or auditable, and no card or bank credential is ever stored. Payment provider
integration is explicitly Phase 11.

## What exists today

**E10 cutover release (owner-accepted for local merge October 21):** ADR-027 supersedes initial historical reconstruction with stated
debt/credit/zero, note and optional private evidence. Unknown aging is not dated arrears, and opening
credits are not receipts. Existing-history recovery remains compatible; accounting B1–B5 is not included.

**October 20 financial-clarity follow-up:** approved E9/E11 work shares both lease financial entry
routes and introduces amount-level meanings without changing ledger calculations or mutations.
The owner accepted the reading surface, expandable bills and reviewed history recovery for local
merge. Remaining entry/correction forms await separate review. See
[implementation record](../design/financial-implementation.md). Phase 4 remains complete.

- **Models** (`apps/ledger/models.py`): `Charge` (lease, kind, direction, amount, due date, description,
  optional responsibility link), `Payment` (lease, kind, status, method, amount, date, reference,
  reversal links), the recorded `FundsApplication`/repayment-plan rows, and the append-only
  `DepositEntry` register. Enumerations: `ChargeKind` (`RENT`, `NNN`, `RESPONSIBILITY`, `MANUAL`,
  `ADJUSTMENT`, `OPENING`), `Direction`, `ChargeState`, `PaymentKind`, `PaymentStatus`, `PaymentMethod`,
  `DepositKind`.
- **The one derivation** (`apps/ledger/services.py`): `build_ledger(lease) → LeaseLedger` reads the
  recorded application rows (there is no read-time allocation — ADR-028 D3), nets adjustments into the
  charge they correct (`StatementCharge`), groups a month into a card (`StatementMonth`), answers
  balance, due now, past due and upcoming amounts, and projects one chronological staff transaction
  ledger with a running balance. Nothing stores a balance; every screen and page reads this.
- **Actions:** `generate_charges` (rent, NNN, responsibilities, opening), `create_charge`,
  `create_adjustment`, `record_payment`, `clear_payment`, `void_payment`, `reverse_payment`, plus
  `rent_due_dates` / `generation_horizon` for the charging window.
- **Screens:** `/manage/ledger/` (every lease that can owe money, most urgent first), a lease's ledger with
  its charges, payments, merged activity and a History panel built from the audit trail, and the forms for
  a charge, a payment, an adjustment, clearing, voiding and reversing. The tenant's `/payments/` is their
  statement.
- **Settings:** `RHP_LEDGER_ACTIVITY_LIMIT`. There is no charging horizon: a charge falls due on its due
  date and is raised then, never ahead of it (P4-Q7, [`apps/ledger/services.py`](../../apps/ledger/services.py)).
- **Command:** `manage.py generate_rent_charges`, which Phase 12 can put on a schedule. Today charging is a
  deliberate act — activation, the ledger screen, or that command.

## Decisions that govern it

| Record | What it settled |
| --- | --- |
| [ADR-008](../decisions/ADR-008-rent-ledger.md) | Two tables with explicit directions, derived balances and states, first-in-first-out allocation, corrections as new entries, idempotent generation bounded by the term, and managers performing operational money work |
| [ADR-011](../decisions/ADR-011-tenant-statement.md) | The tenant's statement absorbs a correction into the charge it corrects, and shows paid and credited money separately |
| [ADR-012](../decisions/ADR-012-owed-now-and-coming-due.md) | A tenant's headline is what is due now; what is billed but not yet due is stated in a sentence |
| [ADR-014](../decisions/ADR-014-property-responsibilities.md) | P4-E2: responsibilities as a charge kind, with the tenant's month readable as rent, NNN and responsibilities |
| [ADR-016](../decisions/ADR-016-retroactive-onboarding.md) | P4-E4: the cutover, the opening position, and the guard that refuses to bill a past nobody has placed — the onboarding mechanism is retired by [ADR-028](../decisions/ADR-028-one-kernel.md); its cutover term remains |

*Amended October 21, 2026:* the ledger's allocation is now **only** persisted `FundsApplication` rows
(ADR-028 D3); the read-time FIFO projection is deleted. The deposit is tracked by a held-liability
register with a move-out outcome (ADR-028 D5), so settlement is no longer blocked without a path.

## Extensions filed under this phase

**P4-E2 — Property responsibilities** (register id `E2`, **In `main`**,
[ADR-014](../decisions/ADR-014-property-responsibilities.md)). Utilities and maintenance are billed to the
property, split across its units by share, and charged to each lease as `ChargeKind.RESPONSIBILITY` on a
cycle. Reaches into Phase 2 (the property's responsibilities and its CAM rate per square foot) and Phase 5
(the tenant reads one month, not three ledgers). Since 2026-10-15 the screen that sets the amounts shows each
unit's figure as both a dollar amount and a share of the bill, linked to each other, with the remainder
offered to the next unit down the list. **Superseded October 16:** the owner approved guided
bill details → explicit allocation → review and save, with a named remainder recipient (RHP
by default), an explicit dollar/percentage basis, no blank-field fallbacks, and concurrency
checks. See the amendments in [ADR-014](../decisions/ADR-014-property-responsibilities.md).

The replacement is implemented on `rhp-share-calculator`: one allocation service powers
plain-form and live previews, the named remainder recipient replaces row-order inference,
and a signed review binds the saved cents to a manager and a fingerprint of the current
bill, units, shares and tenancy facts. The responsibility row serializes saving and charge
generation. No migration or existing financial-data change is required.

**P4-E3 — Concessions** (register id `E3`, **Proposed**, no decision record yet). A month forgiven, or
moved to a later date, recorded as a decision rather than as a deleted charge. **Not built.** Its scope may
merge into the charge-lifecycle work below: forgiveness and deferral are charge-lifecycle decisions, and
answering P4-Q2 and P4-Q3 may settle most of E3's design.

**P4-E4 — Retroactive onboarding** (register id `E4`, **retired by
[ADR-028](../decisions/ADR-028-one-kernel.md)**, [ADR-016](../decisions/ADR-016-retroactive-onboarding.md)
historical). A live tenancy that began before RHP cannot be onboarded by activating it: the generator walks
from the term start and bills the whole past. The extension added `Lease.billing_start_date` as the cutover
that unlocks charging, `LeaseOnboarding` recording how the tenancy was placed, `ChargeKind.OPENING` for a
brought-forward line, two methods (raise the history and record what was received, or start at a date and
state the position), the `STATED` rent template, the rule that a hand-entered period survives regeneration,
and the guard that refuses to charge an unplaced retroactive tenancy. ADR-027 replaced the onboarding
workflow with the reviewed starting account; ADR-028 removes the E4 mechanism itself and keeps the
`billing_start_date`, `OPENING` entry and placement guard.

## Acceptance criteria and evidence

**E10 cutover refinement, October 21:** [Held credit and dated repayments](../design/held-credit-repayments.md)
replaces read-time allocation with durable applications. Held credit does not lower due-now totals until
explicitly applied. Agreed due dates/monthly installments schedule existing opening debt, not new charges.
Future installments stay in account balance but outside due-now/past-due figures. This is cutover scope,
not general concessions or the separately reviewed accounting implementation.

**Owner-approved existing-history recovery (October 20):** an active, open account with existing
charges but no billing start date now uses a signed review rather than the original setup form.
Managers choose a date/reason and explicitly confirm; only the date and audit event are saved.
Nothing is regenerated or inferred. See ADR-016. No live account is repaired automatically.

**October 20 bill-presentation refinement (E9/E11):** both staff lease entry routes and tenant
statements group all same-due-date charges into expandable bills. Totals and payment progress are
bill-level only; descriptions, icons, corrections and staff-only Adjust actions remain on components.
Payments stay separate. Grouping precedes date filtering/pagination and preserves full-history
running balances. This introduces no model, migration or financial-allocation change.

- [x] Balance is derived from ledger entries — no stored balance, no stored charge status
- [x] Financial history is immutable and auditable: append-only models, `PROTECT` keys, read-only in the
      Django admin, an audit event in the same transaction as every change
- [x] Corrections leave a trail: a reversal or an adjustment with an actor, a timestamp and a reason, shown
      on the lease's History panel
- [x] A tenant sees an understandable balance: what is owed (or credited), what is next, recent activity
- [x] States distinguish unpaid, partly paid, paid, overdue and pending
- [x] No card or bank credential is stored; the model leaves room for a provider

`tests/ledger/` covers allocation, adjustment absorption, reversal and void rules, the statement, the tenant
page, the authorization matrix, and the ledger screens.

## Deliberately not here

Proration (a part month is a one-off charge typed by the office); late fees and interest (manual charge with
a reason if ever needed — see `extensions.md`); invoicing, statements and receipts as documents (Phase 6
makes them possible); the E5 remainder of move-out settlement (final statement, forwarding address,
withheld-to-arrears) — the held-deposit register and outcome are now present (ADR-028 D5); any payment
provider (Phase 11).

## Known gaps and defects

**Fixed in P4-E5** — *"a new charge can be raised on an ended lease"*, the defect that started this work.
It was reproduced on 2026-10-06 (lease 14 ended at 22:00, charge #1081 created at 22:01) and is now
impossible: `Lease.can_be_charged` is consulted by `generate_charges` and `create_charge`, the screens no
longer offer the actions, and the tests refuse both paths including a direct POST. The tenancy-and-money
case study, with the evidence, is [`workflows/tenancy-and-money.md`](../workflows/tenancy-and-money.md).

What is still open here:

- **Post-tenancy charges with their just cause (E6) are blocked by Phase 6.** Reopening a financial
  account does not restore occupancy or permit recurring rent; E6 will add the evidence-backed exception.
- **Move-out settlement (E5) remains partial, but settlement now has a path.** A nonzero recorded deposit is
  tracked as a held liability with an explicit move-out outcome (ADR-028 D5); the financial account can
  settle once nothing is held and an outcome is recorded. The E5 remainder — forwarding address, final
  statement, and applying withheld funds to outstanding arrears — is still open.
- **A unit's ledger history (E7)** — the office can see a unit's tenancies one at a time, not as a history.
- The audit trail is written but has no browser until Phase 9.
- Lease 14 still carries the November charge raised under the old horizon rule. It is left alone; a
  close-out or an adjustment is how it goes away.

## Open questions for the owner

**The working area is in Plane** — the parent item *"Charge lifecycle — working area (Phase 4)"*, labelled
`charge-lifecycle`, with one child item per question below and a *DEFECT* item carrying the reproduction.
Answer there (a comment, or the item's own "Your answer" line) or here; either way the answer is written
into the table below and the implementation plan is written from it. The items are raised by hand, so the
mirror never rewrites them and `verify` reports them as the owner's work rather than as drift.

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P4-Q7 | Raise a month's rent on its due date, or a month ahead? | **On the due date** — the lease says what will be owed and the ledger records what is owed, so a future charge row buys nothing and creates the whole close-out problem. | **Yes, built.** Nothing is charged ahead of its due date; the horizon setting and `generation_horizon()` are gone. *"We'll address early notification systems like a '5 days until rent is due' system in Phase 8."* |
| P4-Q1 | What does "ending a lease" mean for money? | Ending freezes the **terms** and stops **new obligations**; money already charged stays and stays correctable. | **Separate states and a citable reason.** Occupancy is draft/active/ended; the account is open/settled. Ending takes a reason code and note. Settlement closes only the financial account ([ADR-020](../decisions/ADR-020-tenancy-lifecycle.md)). |
| P4-Q2 | What happens to rent already raised for months that will no longer happen? | Ending offers a **close-out**: each remaining charged month cancelled by a dated adjustment naming the reason. Append-only, visible, reversible — never a deletion. | **Yes, built as described.** *"We'll use your recommendation."* |
| P4-Q3 | Which money actions are allowed on an ended lease? | Payments and corrections yes; **new charges no**. | **Recurring charges stop; remedial ones are wanted, with their just cause.** That evidence-backed exception is **E6, blocked by Phase 6**. Reopening a settled account enables payment and correction work but never restores occupancy or recurring rent. |
| P4-Q4 | Where is that rule enforced? | In the **services** (`generate_charges`, `create_charge`), because the screens and the management command both pass through them; the screens then hide the actions and say why. | **As recommended.** *"Otherwise, we'll go with your recommendation."* |
| P4-Q5 | Does an ended lease still sit in Rent & Payments looking live? | Yes, but marked ended, with no charging actions, its final position stated. | **Yes, keep it — marked**, and *"a new tenant should not see the previous tenants ledger"* — a test pins that now. The unit ledger history the owner wondered about is **E7**. |
| P4-Q6 | Is there a move-out settlement — deposit, final statement, forwarding address? | Not in this phase: deposit returns and deductions are deliberately out of Phase 4. Its own extension, taken up after the guard lands. | **E5.** *"P4-E5 is good."* |

## How to verify it

`make test` (with `tests/ledger/`), then: open `/manage/ledger/`, create the missing charges for a lease,
record a payment (cleared and pending), reverse one, adjust a charge, and read the same lease as its tenant
at `/payments/` — the office balance and the tenant statement must agree, because both come from
`build_ledger`.

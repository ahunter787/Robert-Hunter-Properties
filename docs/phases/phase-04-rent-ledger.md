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

- **Models** (`apps/ledger/models.py`): `Charge` (lease, kind, direction, amount, due date, description,
  optional responsibility link) and `Payment` (lease, kind, status, method, amount, date, reference,
  reversal links). Enumerations: `ChargeKind` (`RENT`, `NNN`, `RESPONSIBILITY`, `MANUAL`, `ADJUSTMENT`,
  `OPENING`), `Direction`, `ChargeState`, `PaymentKind`, `PaymentStatus`, `PaymentMethod`.
- **The one derivation** (`apps/ledger/services.py`): `build_ledger(lease) → LeaseLedger`, which allocates
  cleared and pending money oldest-first (`_allocate`), nets adjustments into the charge they correct
  (`StatementCharge`), groups a month into a card (`StatementMonth`), and answers balance, what is due now,
  what is past due and what is coming due. Nothing stores a balance; every screen and page reads this.
- **Actions:** `generate_charges` (rent, NNN, responsibilities, opening), `create_charge`,
  `create_adjustment`, `record_payment`, `clear_payment`, `void_payment`, `reverse_payment`, plus
  `rent_due_dates` / `generation_horizon` for the charging window.
- **Screens:** `/manage/ledger/` (every lease that can owe money, most urgent first), a lease's ledger with
  its charges, payments, merged activity and a History panel built from the audit trail, and the forms for
  a charge, a payment, an adjustment, clearing, voiding and reversing. The tenant's `/payments/` is their
  statement.
- **Settings:** `RHP_CHARGE_HORIZON_MONTHS` (default 1 month — charges are raised a month ahead) and
  `RHP_LEDGER_ACTIVITY_LIMIT`.
- **Command:** `manage.py generate_rent_charges`, which Phase 12 can put on a schedule. Today charging is a
  deliberate act — activation, the ledger screen, or that command.

## Decisions that govern it

| Record | What it settled |
| --- | --- |
| [ADR-008](../decisions/ADR-008-rent-ledger.md) | Two tables with explicit directions, derived balances and states, first-in-first-out allocation, corrections as new entries, idempotent generation bounded by the term, managers record and admins correct |
| [ADR-011](../decisions/ADR-011-tenant-statement.md) | The tenant's statement absorbs a correction into the charge it corrects, and shows paid and credited money separately |
| [ADR-012](../decisions/ADR-012-owed-now-and-coming-due.md) | A tenant's headline is what is due now; what is billed but not yet due is stated in a sentence |
| [ADR-014](../decisions/ADR-014-property-responsibilities.md) | P4-E2: responsibilities as a charge kind, with the tenant's month readable as rent, NNN and responsibilities |
| [ADR-016](../decisions/ADR-016-retroactive-onboarding.md) | P4-E4: the cutover, the opening position, and the guard that refuses to bill a past nobody has placed |

## Extensions filed under this phase

**P4-E2 — Property responsibilities** (register id `E2`, **In `main`**,
[ADR-014](../decisions/ADR-014-property-responsibilities.md)). Utilities and maintenance are billed to the
property, split across its units by share, and charged to each lease as `ChargeKind.RESPONSIBILITY` on a
cycle. Reaches into Phase 2 (the property's responsibilities and its CAM rate per square foot) and Phase 5
(the tenant reads one month, not three ledgers).

**P4-E3 — Concessions** (register id `E3`, **Proposed**, no decision record yet). A month forgiven, or
moved to a later date, recorded as a decision rather than as a deleted charge. **Not built.** Its scope may
merge into the charge-lifecycle work below: forgiveness and deferral are charge-lifecycle decisions, and
answering P4-Q2 and P4-Q3 may settle most of E3's design.

**P4-E4 — Retroactive onboarding** (register id `E4`, **Built, in review** on `rhp-e4-onboarding`,
[ADR-016](../decisions/ADR-016-retroactive-onboarding.md)). A live tenancy that began before RHP cannot be
onboarded by activating it: the generator walks from the term start and bills the whole past. The extension
adds `Lease.billing_start_date` as the cutover that unlocks charging, `LeaseOnboarding` recording how the
tenancy was placed, `ChargeKind.OPENING` for a brought-forward line, two methods (raise the history and
record what was received, or start at a date and state the position), the `STATED` rent template, the rule
that a hand-entered period survives regeneration, and the guard that refuses to charge an unplaced
retroactive tenancy.

## Acceptance criteria and evidence

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
makes them possible); deposit returns and deductions; any payment provider (Phase 11).

## Known gaps and defects

**A new charge can be raised on an ended lease.** Ending a lease changes nothing about its money: the
`ledger_lease.html` Actions card is gated only on `DRAFT`, `generate_charges` refuses only a draft (and an
unplaced retroactive tenancy), and `create_charge` refuses nothing at all. `ledger_rows` excludes only
drafts, so an ended lease also sits in `/manage/ledger/` looking exactly as live as an active one.

Reproduced on 2026-10-06 against the dev database: lease 14 (1101 Hoodview / Austin/Ruiming) was ended at
22:00, and charge `#1081` "Test Fee" for $1,000.00 was created against it at 22:01 — one minute later. Rent
for November (`#53`) had already been raised, so the ended tenancy also carried a future obligation with
nothing to close it out.

This is **not only a bug**: the specification is silent on what ending a lease does to money, and the rule
that does exist — `_refuse_ended_terms`: *"An ended tenancy is history: its money stays correctable, its
terms do not"* — lives in the leases app and is enforced in neither. The full analysis, and the decisions it
needs, are in [the tenancy-and-money case study](../workflows/tenancy-and-money.md) and
[ADR-017](../decisions/ADR-017-charge-lifecycle.md), and the questions are P4-Q1 to P4-Q6 below. **The fix
is scheduled, not built**, pending your answers.

Also open, and smaller:

- An ended lease's *future* charges (raised inside the term but after the end date) have no close-out act.
- `RHP_CHARGE_HORIZON_MONTHS` is what puts charges into the future; with the default of one month, a tenancy
  ended today usually has one month already raised.
- The audit trail is written but has no browser until Phase 9.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P4-Q1 | What does "ending a lease" mean for money? | Ending freezes the **terms** and stops **new obligations**; money already charged stays and stays correctable. | *(awaiting)* |
| P4-Q2 | What happens to rent already raised for months that will no longer happen? | Ending offers a **close-out**: each remaining charged month inside the term cancelled by a dated adjustment naming the reason ("tenancy ended 2026-10-06"). Append-only, visible, reversible — never a deletion. | *(awaiting)* |
| P4-Q3 | Which money actions are allowed on an ended lease? | Payments yes; adjustments, reversals and voids yes; new charges — manual, generated rent, NNN, responsibility — no. | *(awaiting)* |
| P4-Q4 | Where is that rule enforced? | In the services (`generate_charges`, `create_charge`), because the screens and the management command both pass through them; the screens then hide the actions and say why, in the words the leases app already uses. | *(awaiting)* |
| P4-Q5 | Does an ended lease still sit in Accounting looking live? | Yes, but marked ended, with no charging actions and its final position stated. | *(awaiting)* |
| P4-Q6 | Is there a move-out settlement — deposit, final statement, forwarding address? | Not in this phase: deposit returns and deductions are deliberately out of Phase 4. It wants its own extension, filed under whichever phase builds it. | *(awaiting)* |

## How to verify it

`make test` (with `tests/ledger/`), then: open `/manage/ledger/`, create the missing charges for a lease,
record a payment (cleared and pending), reverse one, adjust a charge, and read the same lease as its tenant
at `/payments/` — the office balance and the tenant statement must agree, because both come from
`build_ledger`.

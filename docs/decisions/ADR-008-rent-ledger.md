# ADR-008: How the rent ledger is modeled

- **Status:** Accepted (Phase 4)
- **Date:** 2026-10-01
- **Context:** Phase 4 — charges, payments, reversals, adjustments, and a balance that can be trusted

## Context

Phase 3 stored what a tenancy *agreed* (rent, deposit, due day). Phase 4 records what actually
happened to that money, and the specification is explicit about the hard parts:

- "balance is derived from ledger entries"
- "financial history is immutable **or auditable**"
- "edits/corrections leave an audit trail"
- statuses must distinguish unpaid, partly paid, paid, overdue, and pending payment
- no card or bank credential is ever stored, and the architecture must leave room for a payment
  provider later

Five questions had to be answered before a screen could be written, and each has an answer that is
cheaper now and expensive later:

1. **One table or two?** A single `LedgerEntry` with signed amounts is compact; the specification's
   own domain model names `CHARGE` and `PAYMENT` separately, with different fields.
2. **Where does the balance live?** A stored column is fast and drifts. The specification forbids it.
3. **How is "partly paid" decided** when a single payment covers one charge and part of another?
4. **How does a correction happen** without rewriting the entry that was wrong?
5. **Who may do what** to money in a business where the manager runs the desk and the owner owns it?

## Decision

### Two tables, positive amounts, one explicit direction

`Charge` (rent, manual, adjustment) and `Payment` (received, reversal) are separate models because
their fields genuinely differ: a charge has a due date and a settlement state, a payment has a method,
a status and a provider reference.

Amounts are stored **positive**, with the direction carried by the data:
`Charge.direction` (`INCREASE`/`DECREASE`) and `Payment.kind` (`RECEIVED`/`REVERSAL`). The sign exists
in exactly one place, `balance_effect`, and every sum goes through it. A negative amount in a column
would be a direction hiding in a number, which is how "refund" quietly becomes "charge" in a report.

`Charge` is the only entry that may reduce what is owed, and only when it is an `ADJUSTMENT` — a
database `CheckConstraint` (`only_adjustments_reduce_a_charge`) says so.

### No balance is stored, and no charge status is stored either

The balance is `Σ charge.balance_effect − Σ cleared, unreversed payments`, computed by
`apps.ledger.services.build_ledger`. There is no `balance` column and no cached total anywhere, so a
wrong balance is always a wrong entry, and the ledger and the balance cannot disagree.

A charge's state (`UNPAID`/`PARTIAL`/`PENDING`/`PAID`/`OVERDUE`/`ADJUSTMENT`) is derived too. This is
the **opposite** of `Lease.status`, and deliberately so (ADR-007): a lease's status is a fact somebody
decided and must be recorded with a name against it, while a charge's status is a *function* of the
entries and the calendar — storing it would mean recomputing it on every payment, every day, forever,
and being wrong in between.

### Allocation is first-in, first-out; a credit settles its own charge

When one payment covers several charges, money is applied to the oldest charge first — what a rent
ledger does, and what makes "partly paid" meaningful: it is the charge at the front of the line.

A reducing adjustment is not pooled with payments. It corrects one charge, so it settles **that**
charge (`adjusts` is required for a reduction), which is why a credit against a late charge lowers the
overdue amount rather than sitting beside it as a second, negative debt. A credit line itself never
counts as overdue.

### Corrections are new entries, and the originals stay

- A charge is never edited: `Charge.save()` compares the stored financial fields and raises if any
  changed (`FROZEN_FIELDS`), and `Charge.delete()` raises outright.
- A payment is never edited either. The one permitted change is the pending lifecycle,
  `PENDING → CLEARED` or `PENDING → VOID`, because money that was expected either arrives or turns out
  never to have existed.
- A mistake is corrected by an **adjustment** (a new charge naming the charge it corrects, with a
  reason) or a **reversal** (a new payment naming the payment it reverses, `OneToOne`, so a payment is
  reversed once).
- Balances count only cleared, unreversed received payments. `PENDING` and `VOID` move nothing.
- `Lease`/`Charge`/`Payment` relationships are `PROTECT`, so no portfolio or back-office path can
  destroy money history: a unit with a ledger cannot be deleted, and a lease with entries cannot be
  deleted either — while a draft lease (the only deletable kind) can never have entries, because
  **nothing may be charged on a draft**.

Enforcement, honestly stated:

| Layer | Rule |
| --- | --- |
| `save()` | financial fields frozen; only the pending lifecycle may move |
| `delete()` | raises on both models; there is no delete route or button |
| Foreign keys | `PROTECT`, so a tenancy's money cannot be cascaded away |
| Django admin | `Charge`/`Payment` are registered read-only — no add, no change, no delete |
| Audit | every mutation appends an `AuditEvent` in the same transaction |
| Limit | `Model.objects.filter(...).delete()` bypasses `Model.delete()`. The application never calls it; it remains an operator action in a shell and is documented as such. Real database-level immutability would need triggers, which belongs to Phase 12 |

### The audit table arrives, because "immutable or auditable" needs a record

`apps.audit.AuditEvent` stores actor, action, target (`app.Model` + id), the tenancy it concerns, a
human summary, a small JSON payload and a timestamp. It is written by the service functions that make
the change, inside the same `transaction.atomic()`, so an event can never survive a rolled-back write
or go missing from a committed one. Events are append-only: `save()` refuses updates and `delete()`
raises. Lease activation and ending, every money action, and role changes are recorded.

### Rent charges are generated on demand, idempotently, and never beyond the term

`services.generate_rent_charges(lease, through=…)` creates one `RENT` charge per month whose due date
falls on or after the tenancy starts and on or before the earlier of the lease's end and the horizon
(current month plus `RHP_RENT_CHARGE_HORIZON_MONTHS`, default 1). A database constraint
(`one_rent_charge_per_month` on `(lease, due_date) where kind = RENT`) makes a second run, a
double-clicked button, or two managers at once harmless — `get_or_create` absorbs the race rather than
duplicating the charge. The same function backs the button on the ledger and
`manage.py generate_rent_charges`, so Phase 12 can put it on a schedule.

The month-end rule promised in the phase guide is implemented once, in
`apps.common.dates.due_date_in`: a due day of the 31st is the 28th in February (29th in a leap year)
and the 30th in April — "the last day", which is what the 31st means in a short month.

**Proration is deliberately absent.** A tenancy starting after its due day is not charged for that
month at all; the desk records a `MANUAL` charge for the part month. Proration is not in the
specification, and inventing a rule for it inside the ledger would make every later report argue about
which months are "full" months.

### Managers run the money; admins change what it means

- A **manager** may view every ledger, generate rent, add a manual charge, record a payment (cleared or
  pending), and clear or void a pending payment.
- An **admin** may additionally **adjust** a charge and **reverse** a payment.
- A **tenant** sees only their own balance and activity, on `/lease/`, with no id in the URL.
- A **maintenance** user has no access to the accounting area at all.

This follows the convention Phase 2 and 3 already set: routine desk work belongs to the manager,
history-changing acts belong to the admin (the same split as "record" versus "delete").

### A tenant never sees a draft

`visible_lease_for` now excludes `DRAFT`: a draft's rent and term can still change, so showing a tenant
those terms would be showing them an offer, not an agreement. This matters more in Phase 4 than it did
in Phase 3, because a draft also has no ledger — and "your balance is $0.00" on an unsigned lease is a
worse answer than "there is no lease on your account yet".

### Deposits stay off the ledger

Phase 3 stores the deposit amount on the lease; Phase 4 does **not** turn it into charges and payments.
A deposit is not rent: making it a charge would show a tenant "in credit" for money that is held, not
paid ahead, and deposit returns and deductions are their own rules (what is withheld, and why). The
field remains the record, and the open question stays open with a decision attached: when deposit
returns are needed, they get their own treatment rather than being smuggled into the rent balance.

## Consequences

**Positive**

- A balance cannot drift from the entries it is derived from, because it is not stored.
- A wrong number is always a wrong entry, and the correction is visible next to the original — which is
  what "immutable or auditable" asks for.
- The same functions answer the staff ledger, the tenant page, the lease panel and the landing
  counters, so four screens cannot hold four opinions.
- The database, not a form, prevents a second rent charge for the same month and a second reversal of
  the same payment.
- Provider integration has somewhere to land: `status`, `method` and `external_reference` already
  exist, and pending money is modeled as pending rather than assumed.

**Negative / accepted trade-offs**

- `build_ledger` computes in Python, so the accounting overview walks every live lease. At this
  portfolio size that is one page and two queries per lease page; a SQL aggregate is the optimisation
  if a large portfolio ever feels slow.
- FIFO is a policy, not a fact: if a payment is meant to settle a specific charge, the ledger cannot
  express that yet (an explicit allocation table would be the change, and Phase 11 is where it would
  earn its keep).
- Two tables mean the "activity" list is assembled in Python rather than by a union query.
- Nothing is ever deleted, so a mistake leaves a permanent pair of rows. That is the point, and it is
  why adjustments carry a required reason.
- `queryset.delete()` can still bypass the guards; only discipline and the audit trail stand in the way
  outside the application (see the table above).

## Alternatives considered

- **One `LedgerEntry` table with signed amounts**: fewer models, but a charge's due date and a payment's
  method become nullable columns, and "what is owed" has to be inferred from a sign. Rejected.
- **A stored `balance` or `Charge.status` column**: fast reads, and a second source of truth that is
  wrong between writes. Rejected — the same reasoning that rejected `Unit.is_occupied` (ADR-007).
- **An allocation table** (`PaymentAllocation(payment, charge, amount)`)**: expresses intent precisely,
  and adds a table, a form and an invariant that nothing needs yet. Deferred to Phase 11, when a
  provider supplies remittance detail that actually names charges.
- **Deleting or editing a mistaken entry** (with an audit row): simpler to explain to a user, and it
  destroys the evidence. Rejected: a reversal is one extra click and the record stays true.
- **Recording a payment as a negative charge**: one table, no distinction between money owed and money
  received, and every report has to guess which rows are which. Rejected.
- **Charging the whole lease term on activation**: fewer actions, and it bills a year of rent the day a
  tenancy is signed — inflating outstanding balances and making the ledger lie about what is due now.
  Rejected.
- **Prorating the first month**: nicer for a mid-month start, and a rule the specification does not
  contain; it would need its own decision about rounding and about which months count. Rejected for
  Phase 4, with a manual charge as the honest interim.
- **Ledgerising the deposit**: presents held money as a credit balance. Rejected.

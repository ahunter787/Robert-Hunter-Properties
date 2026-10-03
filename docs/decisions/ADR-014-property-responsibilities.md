# ADR-014: Property responsibilities, and the month a tenant reads

- **Status:** Accepted (extension E2, from the owner's extension document)
- **Date:** 2026-10-02
- **Context:** the landlord is billed per property; the unit carries its share

## Context

RHP is billed **per property** for utilities and maintenance — a quarterly water bill of $788 for the
building, a pruning bill, trash — and each unit carries its share of that cost, divided the way the lease
says. The owner's document
([`../RHP-5 Owner Requested Extension Spec.txt`](../RHP-5%20Owner%20Requested%20Extension%20Spec.txt)) describes the
practice: a utility is billed to the property every three months, Robert divides it by three for the
monthly figure, and allocates it to each unit. It also describes the case that resists a formula: one
property where each tenant's water is *not* proportionate — one unit is billed for its usage and the other
carries the remainder.

The document's target is the tenant's month, which mixes all of it:

```
Rent for August 2026                 $2,896.25
  Base Rent                          $2,122.56   (steps up in 1 month)
  NNN                                  $305.52   (updates in 2 months)
  Responsibilities                   $468.17
    Utilities                        $324.17
      Garbage  $70.17   Gas  $79.00   Electric $100.00   Water $75.00
    Maintenance                      $144.00
      Pruning $144.00
```

In commercial practice this package is **operating-expense recoveries** (*expense reimbursements*,
*pass-throughs*, *additional rent*); its maintenance pool is **CAM**, taxes and insurance make it the
**NNN** component, and the unit's portion is its **proportionate share** — usually by rentable square
footage, which is the document's 76%-of-3,500-sq-ft example.

## Decision

### A responsibility belongs to the property; its shares belong to a cycle

A new app, `apps/responsibilities`, holds three tables:

- **`PropertyResponsibility`** — a property's recurring cost: what it is called, its category (utility,
  maintenance, other), how many months one bill covers, and whether it is in use.
- **`ResponsibilityCycle`** — one bill, staged before its months arrive: the date it applies from, the
  months it covers, the property's total, and who entered it. The cycle in force keeps applying until the
  staged one's date, exactly as a triple-net lease's NNN does (ADR-013).
- **`ResponsibilityShare`** — **one unit's monthly amount for one cycle**: the figure the ledger charges.

The middle choice matters. A percentage stored on the unit and re-applied at charge time would be less
data, but it cannot express the water bill, and it re-derives money every month. Storing the amount per
cycle per unit means the office's decision *is* the record, a bespoke split is just a typed figure, and the
property screen can show the bill against what the units carry. RHP proposes the amounts — the unit's
square-foot share of the bill's monthly value — and the office overrides whatever is not a formula.

### Which months a bill pays for has one answer

A cycle covers **the first `months` rent due dates of a tenancy on or after its start date**, bounded by
the end of the tenancy. So a quarterly bill from 5 May on a lease due on the 5th charges May, June and
July; a tenancy that starts inside the cycle is charged only the months it is there for; and a tenancy that
ends inside it stops. The rule lives in `ResponsibilityCycle.covered_dates()`, and the generator and the
screens both read it.

### Only a tenancy is charged

Shares are per unit, and a charge needs a lease, so **a vacant unit's share is never billed** — it stays
on the property screen as what the landlord is carrying. A unit with no share row is not part of that
responsibility at all (that is the per-unit opt-in), and a zero removes it.

Unit amounts are proposed **independently**: typing one unit's figure does not silently move another's. The
office types both figures for a usage-based split, and the property screen says plainly when the units are
not carrying the whole bill ("$120.00 a month of this bill is not carried by a unit").

### Every responsibility is its own charge

`ChargeKind.RESPONSIBILITY` and `Charge.responsibility` (frozen with the rest of a charge's meaning) make
each cost its own entry, with a partial unique constraint on `(lease, responsibility, due_date)`. One
generator raises rent, NNN and responsibilities for the months it walks, so "Create charges" is still one
action and still idempotent. Nothing about allocation changes: a payment settles the oldest charge first,
across every kind.

Once a month has been charged, its cycle and shares are **locked**: restaging it, editing its total, or
changing the unit amounts is refused, and the screen names the correction path — an adjustment on the
ledger (ADR-008).

### CAM is a metric, not a charge

The document is explicit that CAM is folded into base rent. The property records a **rate per square foot**
and the property screen shows the derivation (the unit's size, its share, the rate); it never becomes a
charge of its own. What the lease says the rent is, is what the ledger charges.

### The month card is a second reading, not a new record

`LeaseLedger.statement` keeps ADR-011's row reading exactly as it was; E2 adds
`LeaseLedger.statement_months()`, which groups the charges that share a due date into one card: the month's
total, its state, and — opened — base rent, NNN, and responsibilities grouped by category with subtotals,
each carrying the lease's own news ("steps up in 1 month", "updates in 2 months"). It is server-rendered
with the browser's own `<details>`, because RHP has no JavaScript. A month with a single charge still
renders as that one row, so a simple tenancy looks exactly as it did.

The tenant's statement now paginates **months and payments, not charge rows** — a month counts as one
entry — and the dashboard's recent activity reads the same way.

### Acts and permissions

Reading a property's responsibilities is part of the property screen a manager already opens. **Staging a
bill and setting what a unit pays are admin acts**, because those figures become charges; the routes are
`AdminRequiredMixin`, and every change appends an audit event
(`RESPONSIBILITY_CHANGED`, `RESPONSIBILITY_CYCLE_STAGED`, `RESPONSIBILITY_SHARES_SET`).

`RHP_RENT_CHARGE_HORIZON_MONTHS` is renamed **`RHP_CHARGE_HORIZON_MONTHS`**: it has covered rent, NNN and
now responsibilities since E1, and nothing sets the old name in `.env` or `.env.example`.

## Consequences

**Positive**

- The property's bill is the record, the office's division is the record, and the tenant's charge is the
  record — three figures that can be compared on one screen instead of argued about.
- The usage-based water case is expressible without a usage-billing engine: two typed amounts.
- Nothing re-derives a percentage at charge time, so a share changed today cannot rewrite a month already
  billed, and a correction goes through the ledger's adjustment path.
- The tenant finally sees a month as a month: one figure, openable into what made it.

**Negative / accepted trade-offs**

- Three tables and a fourth charge kind, where "one bill, one number" might have done for a simpler
  landlord. The document's own example needs the breakdown.
- A cycle's unit amounts are re-entered (or proposed) every cycle rather than set once. Accepted: each
  cycle is a different bill, and the previous cycle's amounts pre-fill the form.
- A responsibility that a unit carries is invisible on the tenant's *lease* page until charges exist; the
  statement is where it appears.
- The month card is a second reading of the statement, and the two must stay in step. Contained the way
  ADR-011 contained its own: one derivation, one place, tests on both.
- CAM is displayed but not billed, so a tenant cannot see CAM as a line. That is what the lease says.

## Alternatives considered

- **One percentage per unit, applied when charging**: less data, no route for the water bill, and money
  re-derived every month. Rejected.
- **A usage/meter engine** (readings, rates, estimates): the document calls it a stretch goal, and it is a
  much larger extension. Rejected for now; the typed amount covers today's reality.
- **Folding every responsibility into one monthly charge**: simpler for the tenant, but a correction to
  the water would become a correction to the month, and the ledger would stop being able to say which cost
  changed. Rejected (the same reasoning as ADR-013).
- **Charging vacant units' shares to the remaining tenants**: the lease governs the division, and
  re-cutting it month by month would make a tenant's bill depend on their neighbour's vacancy. Rejected.
- **A separate `UnitResponsibility` allocation table, with the cycle amounts derived from it**: one more
  table and the same information as the stored share, with the water case still needing an override.
  Rejected.
- **Rewriting `LeaseLedger.statement` into months**: cleaner code, but it would break ADR-011's record of
  what a tenant reads and every test that pins it. A second reading is cheaper and honest.
- **Editing a charged cycle to fix a mistake**: forbidden by ADR-008's append-only rule; an adjustment is
  the correction, and both entries stay visible.

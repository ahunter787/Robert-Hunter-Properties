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

### Amended 2026-10-15 — the division is entered in either figure

The owner asked for it in these words: *"If the bill allocates $233.33 and I write $100 for Michael, an
adjacent field needs to calculate percentage share. Modifying percentage share would modify the 100. It
would also suggest downstream the remaining percentage share… a downstream calculator of share, which can be
easily seen and represented as both $ and %. Tidally locked."*

So the screen that sets what each unit pays shows every figure **as both a dollar amount and a share of the
bill**, and the two follow each other: type either one and the other is worked out. What is left of the bill
is offered to the **next unit down the list** and marked *Suggested*; the units below that wait their turn
until one of them is filled in. Nothing is suggested until the office types, and clearing a field still
falls back to the share the unit's size proposes.

Three things this decides, in the open:

- **The stored figure is still a dollar amount**, one per unit per cycle. A typed share is reconciled into
  an amount, and where the two disagree the share is the newer figure.
- **The arithmetic lives on the server** (`apps/responsibilities/services.py`), and the page asks the server
  to recompute as the office types — HTMX, which ADR-001 chose for interactivity and which no phase had
  needed until now (see `docs/architecture.md`). A rule in a browser script is a rule no test here can run.
  The answer is the **whole rows block**, swapped in one piece, rather than out-of-band pieces of it: a block
  swap is htmx's most exercised path, and it puts the caret back by the field's own id afterwards.
- **"Calculate the rest" does the same arithmetic as a plain form submit**, so the screen works with
  JavaScript off or with a browser that will not apply the swap, and the path is tested end to end rather
  than left to be checked by hand. It saves nothing; the office still presses Save.
- **A suggestion is a value, not a hint.** What the calculator puts in the fields is what *Save the unit
  amounts* stores; the marker and the summary say which figures RHP chose.

**Two corrections to this record while it was open.** Staging a bill and setting the unit amounts are
**manager** acts, not admin ones — every operational act on money moved to the desk in
[ADR-021](ADR-021-plain-language-interface.md), leaving destructive acts and role changes above it. And
**`RHP_CHARGE_HORIZON_MONTHS` no longer exists at all**: P4-Q7 removed the charging horizon, so a charge
falls due on its due date and is raised then.

### Amended 2026-10-16 — explicit allocation and review

Owner-approved replacement for the October 15 cascade: bill details → allocate the monthly
amount → review and save. Existing bills start with a read-only summary. Preview, Back and
Cancel do not write; only the reviewed final submission writes, atomically.

Each row explicitly identifies its input basis (dollars, percentage, or excluded). With
JavaScript, editing either numeric field selects that basis; without JavaScript the office
selects it. The selected input controls the other value; rounded display percentages never
override dollars. Size-based and equal allocation are explicit actions, not blank-field rules.
Existing allocations are preserved on entry; a blank required input is an error.

The remainder recipient is explicitly RHP (the default) or one named unit. Only that unit is
recalculated when another amount changes. No downstream manual amount is overwritten. Vacant
units retain their allocation and are not charged; their allocation is carried by RHP.

One server-side calculation drives previews, review and save. A small progressive enhancement
tracks input basis and serializes previews, discarding stale responses. Plain form submission
offers the same operations without JavaScript. Final saves recheck the reviewed bill, unit
roster, saved amounts and posted-cycle lock under database locks; concurrent changes require
another review. Monthly Decimal storage and rounding remain unchanged, with any period-total
rounding difference shown on review. No stored allocation presets, new accounting features,
tenant charges, or migrations are introduced by this correction.

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

# ADR-013: Lease templates, and how a term's rent is worked out

- **Status:** Accepted (extension E1, proposed during the Phase 5 review)
- **Date:** 2026-10-02
- **Context:** RHP writes three kinds of lease, and the specification models one

## Context

RHP's own leases are not one shape. The owner's extension document
([`../RHP-5 Owner Requested Extension Spec.txt`](../RHP-5%20Owner%20Requested%20Extension%20Spec.txt)) describes what
they actually write:

- **Fixed** — one rent for the whole term.
- **Step Up (escalating)** — a fixed monthly rent with a once-a-year step up, in a month the lease
  names; the term's amounts are known the day the lease is initialised.
- **Triple Net (NNN)** — a Step Up base rent **plus** an NNN amount that Robert works out each November
  and stages for the coming year.

The specification models a lease as one `monthly_rent`, and the ledger decides every figure from the
charges. So the question this record answers is not "how do we charge rent" — Phase 4 settled that — but
**where does the amount for a given month come from, and what happens when a lease changes mid-term.**

The owner's stated goal is clarity: "We have constant issues with the current system and ambiguity."

## Decision

### A lease has a template, and the template is a term of the agreement

`Lease.template` is `FIXED`, `STEP_UP` or `NNN`, defaulting to `FIXED` so every lease that already
exists keeps its present meaning. A step-up or triple-net lease carries the rule: the month the rent
steps up, and **exactly one** basis — a percentage or a fixed amount. A fixed lease carries none of
them, and refuses them if they are set.

### The whole term is worked out once, and stored

For a Step Up or NNN lease, activating the lease generates its **rent periods**: a dated amount is
stored for the starting rent and for every step-up date inside the term. Each year's figure is the
previous year's figure grown by the rule, rounded half-up to the cent, and then **stored**. Money is
never re-derived from a percentage later: a rounding change, or a change to the rule, cannot rewrite a
month that has already been billed.

A lease with **no** periods answers its stored `monthly_rent` for the whole term. That is the invariant
that makes this extension safe: every lease in the database today is exactly that case, and
`Lease.rent_for(on_date)` — the hook Phase 5's read-out already called — returns what it returned
before.

### An amount applies from a date rent falls due, and a charged period is never rewritten

A period or an NNN rate must start on a rent due date for that lease: never mid-month, never outside
the term. And once *any* rent or NNN charge has been raised for a period, that period is **locked**:
regenerating the schedule leaves it alone, and setting it by hand is refused with a message that says
what to do instead — correct the charge with an adjustment, so the record shows both what was charged
and what corrected it (ADR-008).

### NNN is a dated monthly amount, staged in advance

Triple-net charges are worked out each November for the year ahead, so `NnnRate` rows are dated and may
be in the future. The rate in force keeps applying until the staged one's date arrives, and the lease
screens show both ("in force now" / "staged from"). A rate of zero is meaningful: NNN suspended. The
screens say when nothing is staged, so a month is never quietly charged without its NNN.

NNN is stored as a **monthly** figure because that is how it is billed and how Robert thinks about it
(the document's example is `$305.52` alongside a `$2,122.56` rent). The annual figure is a note, not the
stored value: dividing an annual number by twelve invites a rounding argument every December.

### Every component is its own charge

Rent, NNN — and, from E2, each responsibility such as water or pruning — are **separate ledger entries**
on the same due date, not one large monthly charge. The owner's card ("Rent for August 2026 $2,896.25",
expandable into Base Rent, NNN and Responsibilities) is therefore a *reading* of a month's charges, not a
charge that has to stay consistent with its own breakdown. That keeps ADR-008 intact: a correction to one
responsibility is an adjustment against that charge, and the rent is untouched.

The grouped, expandable month card is **E2**, where responsibilities make it necessary. E1 gives each
component its own line and puts "how this rent is worked out" on the lease page.

### The tenant's next-due figure is what the month costs

`next_due_date` / `next_due_total` state the next date anything falls due and the whole of that date's
obligation, with the NNN part named beneath it; `next_rent_date` / `next_rent_amount` stay rent-only, and
`next_rent_charge` makes sure an NNN line can never stand in for "next rent due". A tenant told only the
rent would be told a number smaller than the bill — the same fault ADR-012 corrected for the term's
remainder.

### Acts and permissions

- The template and the step-up rule are lease terms: **Managers and above**, like the rest of the lease
  form, and immutable once the lease has ended.
- Working the schedule out, setting a period's amount by hand, and staging NNN are **Admin** acts — the
  document says "an Admin will need to log in and input these values", and they decide money.
- All three append audit events (`RENT_SCHEDULE_GENERATED`, `RENT_PERIOD_CHANGED`, `NNN_RATE_SET`), and
  activation and ending a lease now record `LEASE_ACTIVATED` / `LEASE_ENDED`, which the audit table had
  defined but never written.

## Consequences

**Positive**

- A four-year stepped lease is entered once and charged correctly for its whole term, with every month's
  amount visible and explained.
- Nobody has to remember a rise, and nobody can silently change one: an amount that has been billed is
  locked, and the correction path is the ledger's own.
- The NNN year can be staged in November without disturbing the year in force, which is how the office
  actually works.
- Existing leases are untouched: no backfill, no rewritten charge, no change to `monthly_rent`'s meaning
  for a fixed lease.

**Negative / accepted trade-offs**

- Two more tables and a second source of truth about rent (the schedule) that must agree with the
  template. Contained by generating the schedule in one function and testing the arithmetic against a
  worked four-year lease.
- A percentage rise is compounded on the previous year's stored figure. That is the common reading of
  "7% a year", and it is written down here because the alternative (7% of the first year's rent every
  year, i.e. simple interest) is a different number.
- Regeneration can remove periods the template no longer calls for. It never touches a period that has
  been charged, and the screen reports what it left alone.
- NNN is set per lease in E1. E2 may feed it from a property's pool of costs and a unit's share; the
  lease-level `nnn_for` seam is what makes that a change of source rather than a rewrite.

## Alternatives considered

- **Store a percentage and derive each month's rent when charging**: money would be re-derived on every
  generation, so a later rounding or rule change would rewrite what a past month should have been.
  Rejected.
- **One lease-level "current rent" field updated by hand each year**: what the office does today, and the
  source of the ambiguity the owner is complaining about. Rejected.
- **Fold base rent, NNN and responsibilities into a single monthly charge**: the tenant's card would be
  simpler and every correction would become an adjustment against the whole month, hiding which
  component changed. Rejected.
- **Store NNN as an annual figure and bill one twelfth**: creates a rounding remainder to reconcile every
  year, for a figure the office already works in monthly terms. Rejected for now; the note field carries
  the annual figure.
- **Generate every month's charges for the whole term at activation**: a four-year ledger of not-yet-due
  charges. Charges are raised through the charging horizon, as Phase 4 decided, and the *schedule* is
  what is generated up front.
- **Prorating a part month or charging a step mid-month**: unchanged from Phase 4 — a part month is a
  one-off charge typed by the office, and every amount here starts on a rent due date.

# RHP — extensions E1–E3

**Where this stands:** **E1 (lease templates) is built and in `main`.** **E2 (property responsibilities
charged to the unit) is built on the `rhp-responsibilities` branch** and awaiting the owner's testing.
**E3 (concessions) is unchanged** from the earlier proposal, at the owner's instruction.

The source document is [`RHP-5 Owner Requested Extension Spec.txt`](RHP-5%20Owner%20Requested%20Extension%20Spec.txt),
the working model compiled by the owner with Robert. The governing specification is
[`harness/master-spec.md`](harness/master-spec.md), and each built extension gets its own decision record in
[`decisions/`](decisions/).

| # | What it is | Kind | Status |
| --- | --- | --- | --- |
| **E1** | **Lease templates** — Fixed, Step Up, and Triple Net (NNN) | Core-semantic | **In `main`** — [ADR-013](decisions/ADR-013-lease-templates.md) |
| **E2** | **Property responsibilities charged to the unit** — utilities and maintenance recovered from the tenant, with the tenant's month readable | Additive | **Built** — [ADR-014](decisions/ADR-014-property-responsibilities.md), branch `rhp-responsibilities` |
| **E3** | **Concessions** — forgiveness and deferral | Additive | Proposed, unchanged — see [§4](#4-e3--concessions) |

---

## 1. How a change to the specification is handled

The specification is the contract every phase was built against. It says of itself: *"when a change is
genuinely needed, change it here first, in its own commit, with a note explaining why."* Proposals and
statuses live here instead, and an approved change is written into the specification's appendix.

1. **Nothing is built before it is written down and approved.** An entry moves
   Proposed → Approved → Building → Built; an entry is never deleted, so the decision history survives a
   dropped idea (Withdrawn / Superseded).
2. **Every entry is classified before code**, because the class decides how careful the change is:
   - **Additive** — a new table or capability; everything that exists today behaves exactly as it does now.
   - **Core-semantic** — changes what an existing field or figure *means*. These must carry an invariant: a
     lease that does not use the feature answers exactly as it does today.
   - **Presentation** — wording, labels, layout only.
3. **One extension = one entry = one branch**, named after the extension (`rhp-lease-templates`) rather
   than a new phase number: Phases 6–12 are already committed to, and renumbering them would invalidate
   every earlier plan and reference.
4. **Each entry carries its own acceptance criteria and tests**, and the full gate applies
   (`make test`, `make lint`, `make check`, `make check-deploy`, `makemigrations --check`). The owner tests
   it before it is folded into `main`.
5. **A non-goal is amended, never quietly bypassed.** If an extension contradicts one of the
   specification's explicit non-goals, the entry names it before approval.
6. **An extension may not break an existing phase's acceptance criteria.** If it would, the entry says
   which criterion changes and what replaces it.
7. **The money rules are not renegotiable per extension:** nothing stores a balance, nothing edits or
   deletes a ledger entry, corrections are new entries, and money is never a float.
8. **One decision record (ADR) per built extension**, linked from the entry.
9. **An approved change gets one appendix row in the specification**, so the contract and what was built
   stay in step.

---

## 2. E1 — Lease templates (Fixed, Step Up, Triple Net)

**Status: in `main`** (folded as one commit); the decision record is
[ADR-013](decisions/ADR-013-lease-templates.md). Core-semantic, with the invariant stated below.

### What was asked for

RHP writes three kinds of lease: **Fixed** (one rent for the term), **Step Up** (fixed monthly rent with a
once-a-year rise, in a month the lease names), and **Triple Net** (a Step Up base rent plus an NNN amount
that Robert works out each November and stages for the coming year). The term's amounts should be known
when the lease is initialised rather than remembered; the office should be able to stage next year's NNN
without disturbing this year's; and the tenant should be able to see how their rent is worked out, because
*"we have constant issues with the current system and ambiguity."*

### What was built

- `Lease.template` — Fixed, Step Up or Triple Net, defaulting to Fixed. A stepped lease records the month
  the rent rises and **one** basis: a percentage or a fixed amount.
- **The whole term's rent is worked out at activation and stored** as dated periods. Each year's figure is
  the previous year's grown by the rule, rounded half-up to the cent, and then stored — never re-derived.
- **A period that has been charged is locked.** Regenerating the schedule leaves it alone; setting it by
  hand is refused, and the screen says to correct the charge with an adjustment instead.
- **NNN is a dated monthly amount**, staged in advance and shown as *in force now* / *staged from*. A rate
  of zero suspends it, and the screens say when nothing is staged.
- **Rent and NNN are separate charges** on the same due date, each with its own kind, so a correction to
  one never touches the other.
- **The tenant's "next rent due" is the month's total** (rent plus NNN) with the NNN part named; the
  rent-only figure stays rent-only for the desk.
- **Activation raises the first charges** through the charging horizon, and both activation and ending a
  lease are now written to the audit table.
- The invariant: **a lease with no periods answers its stored rent for the whole term.** Nothing that
  exists today changes: no backfill, no rewritten charge.

### What it deliberately does not do

No late fees, interest, proration or mid-month changes; no automatic notice letters; no index-linked rent
(amounts are decided and stored); no rewriting of anything already charged; and no responsibilities or
expandable month card — those are E2.

---

## 3. E2 — Property responsibilities charged to the unit

**Status: built** on `rhp-responsibilities`; the decision record is
[ADR-014](decisions/ADR-014-property-responsibilities.md).

### What it is

RHP is billed per **property** for things like utilities and maintenance, and each **unit** carries its
share of that bill, divided according to the lease. The owner calls the package *Responsibilities*; in
commercial practice this is **operating-expense recoveries** (also *expense reimbursements*,
*pass-throughs*, or *additional rent*). Its maintenance component is **CAM** (Common Area Maintenance),
when taxes and insurance join it that is the **NNN** component, and the unit's portion is its
**proportionate share** — usually by rentable square footage, which is exactly the 76%-of-3,500-sq-ft
example in the owner's document.

The tenant should be able to expand a month's rent card and see what it is made of:

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

### What it would change

- **A responsibility attached to a property** — name, category (utility / maintenance), how often its cost
  is updated (the owner's example is every 3 months), the cycle start and end, the **current cycle** value
  and a **staged next cycle** value that an admin enters when the bill arrives. Robert's real flow: a
  utility is billed to the property every three months, divided by three for a monthly figure, and
  allocated to each unit.
- **An allocation per unit** — the lease (or the unit) says how the property's cost is divided: a
  proportionate share by square feet, a flat amount, or (as a stretch goal) a bespoke split such as the
  real case where one tenant is billed 1–2 CCF of water and the other the remainder.
- **A CAM formula**, since the owner's document gives one: property square feet, the unit's share of it,
  and a rate per square foot ($0.20). CAM is folded into the lease's base rent, so this is a *derivation
  the office can see*, not a charge of its own.
- **Monthly charges per responsibility**, on the unit's due date, alongside rent and NNN — each its own
  ledger entry, so one utility can be corrected without touching the rent.
- **The expandable month card**, read from the month's charges: base rent, NNN, and each responsibility,
  with "steps up in N months" / "updates in N months" labels.
- **The admin screen the owner sketched**: `/manage/properties/<id>/` gains the property's landlord
  responsibilities, each with its update cycle, current cycle, and a button to stage the next one.

### What was built

- **A responsibility on the property** — a label, a category (utility, maintenance, other), and how many
  months one bill covers; stopped with an "in use" switch rather than deleted.
- **Cycles staged in advance** — the property's bill, the months it covers, and the date it applies from;
  the one in force keeps applying until the staged one's date.
- **Each unit's monthly amount, stored per cycle** — proposed from the unit's square-foot share and
  editable, because the division is not always a formula. What the office stores is what the ledger
  charges; no percentage is re-applied later.
- **Charges raised alongside rent and NNN** by the one idempotent generator, each responsibility its own
  entry, so a correction is an adjustment against that cost.
- **The month card** — the tenant's statement groups a month's charges into one openable card: rent, NNN,
  and responsibilities by category with subtotals, each carrying the lease's own news ("steps up in 1
  month"). Pagination counts a month as one entry.
- **CAM as a metric** — the property records a rate per square foot and shows the derivation; it is folded
  into base rent, so it never becomes a charge of its own.
- **Locking** — a cycle whose months have been charged cannot be restaged or re-divided; the correction is
  an adjustment, as everywhere else.

### Decisions taken (recorded in ADR-014)

| # | Question | Taken as |
| --- | --- | --- |
| E2-D1 | Where a responsibility lives | **On the property** — that is how the bills arrive |
| E2-D2 | How the cost is divided | **Proportionate share by square feet, proposed; the office's typed figures win**, per unit and per cycle |
| E2-D3 | What is stored | **The property's cycle total and each unit's monthly amount**, so the bill and the division are both records |
| E2-D4 | When a staged cycle takes effect | **A date the office gives**, defaulting to the day after the last cycle ends |
| E2-D5 | Categories | **Utility / Maintenance / Other**, plus the free-text label the tenant reads |
| E2-D6 | Stopping one | **The "in use" switch** — months already charged are untouched |
| E2-D7 | The disproportionate water split | **Two typed amounts**; usage/meter billing stays a separate future extension |
| E2-D8 | What the tenant sees | **Their unit's share only**, named by category and label |
| E2-D9 | Who is charged | **Only units under a lease**; a vacant unit's share is shown as the landlord's |

### What E2 deliberately will not do

No metered/usage-based billing, no meter readings or estimates, no utility accounts, no utility invoices
or statements as documents (Phase 6), no landlord-side expense tracking or owner statements, no annual
reconciliation/true-up flow, and no re-cutting a vacant unit's share onto the occupied ones (a tenant's
bill must not depend on a neighbour's vacancy).

---

## 4. E3 — Concessions

**Status: proposed, unchanged.** The owner's document says it plainly: *"No changes to the current spec of
Concessions."*

The proposal stands as it was first written: a concession is a **decision** recorded once — forgiveness (a
charge credited) or deferral (a charge credited and re-raised on a later date) — with an office-facing
reason and a short note written for the tenant, wrapping the ledger's existing adjustment mechanics rather
than adding new arithmetic. One decision is still open from the earlier draft: **does the tenant see the
concession's wording?** (the recommendation was yes, from a note written for them, as a deliberate
exception to ADR-011's rule that an adjustment's free-text reason stays office-facing).

It will be planned properly once E2 is done.

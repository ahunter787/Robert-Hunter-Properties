# RHP — extensions E1–E4

**Where this stands:** **E1 (lease templates) and E2 (property responsibilities) are in `main`.** **E4
(retroactive onboarding) is approved** and is the next unit of work, because RHP's live tenancies cannot be
brought in without it. **E3 (concessions) remains proposed**, unchanged from the earlier proposal at the
owner's instruction, and is the entry after E4 unless the owner redirects.

The source document is [`RHP-5 Owner Requested Extension Spec.txt`](RHP-5%20Owner%20Requested%20Extension%20Spec.txt),
the working model compiled by the owner with Robert. The governing specification is
[`harness/master-spec.md`](harness/master-spec.md), and each built extension gets its own decision record in
[`decisions/`](decisions/).

| # | What it is | Kind | Status |
| --- | --- | --- | --- |
| **E1** | **Lease templates** — Fixed, Step Up, and Triple Net (NNN) | Core-semantic | **In `main`** — [ADR-013](decisions/ADR-013-lease-templates.md) |
| **E2** | **Property responsibilities charged to the unit** — utilities and maintenance recovered from the tenant, with the tenant's month readable | Additive | **In `main`** — [ADR-014](decisions/ADR-014-property-responsibilities.md) |
| **E3** | **Concessions** — forgiveness and deferral | Additive | Proposed, unchanged — see section 4 |
| **E4** | **Retroactive onboarding** — bringing a tenancy that started before RHP in, without inventing a debt | Core-semantic | **Approved** — see section 5 |

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
9. **A built extension gets one appendix row in the specification**, so the contract and what the code
   does stay in step. (E1's and E2's rows are there; E4's lands when E4 is built.)

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

### The real-world flow this models

Robert's practice, which the model follows: a utility is billed to the property every three months, divided
by three for a monthly figure, and allocated to each unit; and the division is not always a formula — one
property splits water by usage, one unit's figure and the other the remainder. CAM is the owner's document's
other case: a pro-rata share of taxes, insurance and maintenance, folded into the lease's base rent, which
is why RHP records it as a rate per square foot and shows the derivation rather than billing it.

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
than adding new arithmetic.

**The open decision is settled (2026-10-03): the tenant *does* see the concession's wording**, from a short
note written for them. That is a deliberate, recorded exception to ADR-011's rule that an adjustment's
free-text reason stays office-facing — a concession is a decision made *about* the tenant and communicated
to them — so the note is a separate field from the internal reason, and office shorthand never reaches a
tenant page.

**Sequencing (confirmed 2026-10-03): E4 first, then E3.** E4 went ahead because RHP's live tenancies cannot
be brought into the system without a cutover; E3 follows it. Nothing in E3 is blocked in the meantime: a concession is expressible today as an adjustment (forgiveness) or an
adjustment plus a new dated charge (deferral) — E3 is what makes the decision *legible*, not what makes it
possible.

---

## 5. E4 — Retroactive onboarding

**Status: approved 2026-10-03; not built.** Owner's words: *"all of the RHP tenants have a currently live
lease, and I do not intend to wait for their lease to expire to enroll them into this new system."*

### The problem, stated with the evidence

A live tenancy that started years ago cannot be onboarded by activating it and pressing "Create charges":
the generator walks from the term start, so it bills the whole past as if it were new. On a real lease
(Michael Ortolano, 910 SE Stark, June 2022 → May 2027) that produced **108 charges and a $100,536.18
"balance"**, of which $96,533.60 read as arrears — for a tenant who is paid up. That figure was reset on
2026-10-03 (see §6) and RHP must make it impossible, not merely discouraged.

The same lease exposed a second gap: its real schedule is **six amounts over irregular dates**, including a
mid-year change in November 2023 ("Extra Space", $1,852). E1 works a schedule out from a rule (a month plus
a percentage or a fixed amount) and cannot express that; and hand-entering a period at a date the rule does
not plan is **silently deleted by "Work the schedule out again"** — verified in a rolled-back transaction on
2026-10-03.

### Classification

**Core-semantic**, with one invariant: a lease with no cutover and no opening position behaves exactly as it
does today — charges from the term start, a schedule generated from the rule.

### What it will do

1. **A cutover date on the lease** (`billing_start_date`): the first month RHP raises charges for. Nothing
   before it is billed unless the office explicitly asks for the history.
2. **An opening position**, recorded once, with a reason and the date it speaks to:
   - **Model A (default — "books in RHP from day one"):** raise the historic charges and record the **total
     received to date** as one settling payment. The ledger's existing oldest-first allocation settles the
     past months and leaves the true current position; the tenant gets a complete, month-paginated
     statement.
   - **Model B (fallback — "state the position"):** start at the cutover and record one opening line:
     *balance brought forward $X*, or *paid through `<date>`*.
3. **A stated schedule.** A lease may say "the lease states the amounts" instead of "rise by a rule", and
   the office can add, change or remove a dated amount — which is what a mid-year step, an "Extra Space"
   change or a renegotiation needs. **The defect above is fixed with it**: a period the office entered by
   hand is never removed by regenerating, and a regression test pins that.
4. **An NNN series the office stages** — dated rates, adjusted when the lease says. The live lease says
   **October**; our earlier note (from the owner's first document) said November, and the docs are corrected
   to "whenever the lease says".
5. **The lease's own record, entered not reconciled.** A retroactive lease is entered as the paper reads:
   the rent due day the lease names (Michael's says the 1st; RHP had the 5th), the amounts it states, the
   square footage as it changed. Where the paper disagrees with itself (this lease says both "$305/month"
   and "$0.19/sf" for 2022 NNN), the office records what governs; RHP's job is to make the disagreement
   visible, not to pick a winner.
6. **Guard rails, before any of it:**
   - no charges may be raised before the cutover without an explicit "include the history" choice;
   - a retroactively-dated lease with no opening position tells the **office** that history is not set up,
     and never shows a tenant an unearned arrears figure;
   - the staff screen says which of A or B a lease was onboarded with.

### Acceptance criteria

- Onboarding Michael's lease produces the true position: his real schedule (six amounts), his NNN series,
  and either a settled history (A) or one stated opening line (B) — with no phantom balance at any point.
- A lease with no cutover behaves exactly as it does today (regression test).
- A hand-entered period survives regeneration; a period that has been charged still cannot be rewritten.
- A tenant cannot be shown a balance that the office has not stood behind, and the staff screen names the
  state of onboarding.
- The due day, amounts and square footage the lease states are what the portal shows.

### What E4 deliberately will not do

No late fees or interest (see §6), no usage/meter billing (E2's non-goal), no tax, depreciation or land
valuation (that is the owner-facing direction in §7), no rewriting of anything already charged once a lease
is onboarded, and no automatic reconciliation of the lease's internal inconsistencies.

### After E4

Every live RHP tenancy is onboarded the same way, Michael's first as the pilot. The reset that E4 replaces
was a manual database operation with a written record; E4 should ship the tool that makes that operation
unnecessary — a lease can be re-onboarded through the screens while it has no charges.

---

## 6. Recorded decisions

Decisions taken by the owner that are not entries of their own, kept here so nobody re-opens them by
accident.

- **Late fees and interest are not modelled (2026-10-03).** RHP's leases carry a clause — the live lease at
  910 SE Stark charges 24% a year after ten days plus a 10% late charge — but it has not been used in thirty
  years. The specification's Non-goal stands: if pressure on a tenant is ever needed, the office raises a
  **manual charge with the reason "late fee"**, and the entry is auditable like any other. Nothing is
  automatic.
- **The system records what the lease says; it does not reconcile discrepancies (2026-10-03).** RHP exists
  to make the owner's and the tenant's understanding of a live lease legible. Where a lease has drifted —
  values moved, an "Extra Space" change mid-term, two different NNN figures in one document — the record
  carries what governs, and the disagreement is visible to the office rather than silently resolved.
- **Michael Ortolano's lease history was reset (2026-10-03).** 108 charges ($100,536.18) and five invented
  rent periods, generated before E4 existed, were removed; his due day was corrected to the 1st; a note on
  the lease says history awaits E4. No other tenancy was touched. E4 should make this operation unnecessary.

---

## 7. Directions not yet proposed

Recorded so they are not lost, with **no design committed**: the owner intends to extend RHP *after Phase 12
(hardening)* into a tool for managing the business side of the portfolio — property taxes, depreciation
schedules, land values, and the tax and business data that is **owner-facing rather than tenant-facing**.
The owner will consult Robert before any of it becomes register entries.

Three things worth knowing when that work is planned, none of them decided here:

1. **It is a separate domain, not an extension of the rent ledger.** An owner's books hold assessments,
   cost basis, placed-in-service dates, depreciation methods and lives, and land-versus-building
   allocation. The tenant ledger stays rent, charges and payments (ADR-008) — mixing the two would put the
   tenant-facing figures that RHP has just made trustworthy at risk.
2. **Time becomes first-class in a way it is not today.** The ledger thinks in due dates; tax and
   depreciation think in *periods* — tax years, partial years, mid-month conventions.
3. **It needs its own visibility rule.** Today access is decided by role plus tenancy scoping; owner
   financials must be server-side owner/staff-only and never reachable by a tenant, and probably want their
   own area rather than appearing inside the portal tenants use.

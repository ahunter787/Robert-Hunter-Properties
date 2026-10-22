# RHP — extensions E1–E12

**Where this stands:** **E1, E2, E4 and E9 are built** — lease templates, property responsibilities,
retroactive onboarding and the plain-language interface — all four are in `main` now, on their own
branches until they were folded. **The tenancy-and-money work is built** too, but it is *not* an extension: it
is a specification amendment (the states and what they mean for money), recorded below and in
[ADR-017](decisions/ADR-017-charge-lifecycle.md) and
[ADR-020](decisions/ADR-020-tenancy-lifecycle.md). **Phase 6 (documents) is complete and in `main`**;
it is the phase E6 was waiting for, so **E6 is no longer blocked** — it follows **E5 (move-out settlement), which is the next piece**. **E3
(concessions) is proposed**, re-scoped by the owner's own 2022 example; **E7 (a unit's ledger history)
and E8 (early termination) are proposed; **E10 (property accounting) is building** — the owner's decision to
build it, and to export to an accountant rather than integrate an external ledger, is
[ADR-026](decisions/ADR-026-property-accounting.md), and the core-kernel consolidation is
[ADR-028](decisions/ADR-028-one-kernel.md).**

The source document is [`RHP-5 Owner Requested Extension Spec.txt`](RHP-5%20Owner%20Requested%20Extension%20Spec.txt),
the working model compiled by the owner with Robert. The governing specification is
[`harness/master-spec.md`](harness/master-spec.md), and each built extension gets its own decision record in
[`decisions/`](decisions/).

An extension is filed under the phase it extends, and the phase-scoped id is the intended form —
`P4-E1`, `P3-E2` and so on (ADR-018). The `#` column keeps the flat ids the Plane mirror's parser recognises
today; the phase-scoped id is written into each row's text, and the register is re-keyed in one go when that
parser accepts the longer form.

| # | What it is | Kind | Status |
| --- | --- | --- | --- |
| **E1** | **Lease templates** (`P3-E1`) — Fixed, Step Up, and Triple Net (NNN) | Core-semantic | **In `main`** — [ADR-013](decisions/ADR-013-lease-templates.md) |
| **E2** | **Property responsibilities charged to the unit** (`P4-E2`) — utilities and maintenance recovered from the tenant, with the tenant's month readable | Additive | **In `main`** — [ADR-014](decisions/ADR-014-property-responsibilities.md) |
| **E3** | **Concessions** (`P4-E3`) — forgiveness, a deferral plan, and the term extension that goes with them | Additive | Proposed, re-scoped — see section 4 |
| **E4** | **Retroactive onboarding** (`P4-E4`) — bringing a tenancy that started before RHP in, without inventing a debt | Core-semantic | **In `main`** — [ADR-016](decisions/ADR-016-retroactive-onboarding.md) |
| **E5** | **Move-out settlement** (`P4-E5`) — the deposit returned or withheld, deductions with their reasons, a final statement, a forwarding address | Additive | Proposed — next up; the owner's "P4-E5 is good" (P4-Q6) |
| **E6** | **Post-tenancy charges with their evidence** (`P4-E6`) — damage, cleaning, an unpaid balance, an NSF fee, an early termination fee, each carrying a reason code, the lease clause it rests on and its documents | Additive | **Proposed** — was waiting on Phase 6, which is now built; the owner's decision: a charge always has its evidence from the day it exists |
| **E7** | **A unit's ledger history** (`P4-E7`) — every tenancy that unit has had, expandable, for the admin. The tenant's own view never crosses tenancies | Additive | Proposed — the owner's "maybe", from P4-Q5 |
| **E8** | **A tenant's request for early termination** (`P3-E2`) — the tenant asks, RHP approves, and the early-termination clauses follow | Additive | Proposed — filed under Phase 3, because it changes a lease's terms |
| **E9** | **Plain-language interface** — portal-wide product vocabulary, due-now/account-balance hierarchy, and unified staff transaction ledger | Presentation | **Built** — [ADR-021](decisions/ADR-021-plain-language-interface.md); October 20 financial reading surface, expandable bills and history recovery owner-accepted for local merge; remaining forms deferred [record](design/financial-implementation.md) |
| **E10** | **RHP property accounting** — landlord-side income, expenses, reconciliation, and reporting for properties owned by RHP only | Additive | **Building** — tenant cutover, held credit and dated repayments owner-accepted for local merge October 21; the core-kernel consolidation is [ADR-028](decisions/ADR-028-one-kernel.md) with [kernel vocabulary](kernel/events.md); [record](design/held-credit-repayments.md), [ADR-027](decisions/ADR-027-simple-cutover.md); accounting [ADR-026](decisions/ADR-026-property-accounting.md) remains separately reviewed |
| **E11** | **Operations desk application migration** — persistent sidebar, unified Properties and existing portal workflows; RHP domain rules preserved | Presentation | In main — [owner accepted October 19, 2026](design/implementation.md); local merge authorized, no push |
| **E12** | **Tenant–RHP messaging** (`P8-E1`) — saved private conversations, attachments, per-user unread state, email alerts and announcement follow-up; no native app or push | Additive | In main — owner accepted for local merge; [Phase 8](phases/phase-08-communications.md), ADR-024 |

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
- **Guided bill allocation** (revised 2026-10-16) — bill details, monthly allocation, then
  review and save. Each unit has linked dollars and percentage inputs with an explicit input
  basis. Size-based allocation and equal division are explicit actions. The remainder goes
  only to a named recipient, defaulting to RHP, never implicitly to the next row. Existing
  amounts remain intact on entry and blank inputs require correction or explicit exclusion.
  Server-calculated live previews discard stale responses; plain form submissions perform
  the same calculations without JavaScript. Only the signed final review saves, after
  concurrency and posted-cycle checks. No tenant charges are posted by saving an allocation.
- **Charges raised alongside rent and NNN** by the one idempotent generator, each responsibility its own
  entry, so a correction is an adjustment against that cost.
- **The month card** — the tenant's statement groups a month's charges into one openable card: rent, NNN,
  and responsibilities by category with subtotals, each carrying the lease's own news ("steps up in 1
  month"). Pagination counts a month as one entry.
- **CAM as a metric** — the property records a rate per square foot and shows the derivation; it is folded
  into base rent, so it never becomes a charge of its own.
- **Locking** — a cycle whose months have been charged cannot be restaged or re-divided; the correction is
  an adjustment, as everywhere else.

### Calculator correction — approved 2026-10-16

The October 15 cascade is superseded by a guided bill-details, allocation, and review workflow.
Existing monthly amounts are preserved. Dollars or percentages explicitly control each row;
size-based allocation, equal allocation and exclusion are explicit actions. RHP is the default
remainder recipient; a named unit receives it only when selected. No other manual amount is
overwritten. Preview and navigation write nothing; only final review saves. Concurrent edits
and posted charges invalidate a review. Decimal monthly amounts and vacancy treatment remain
unchanged. See ADR-014's October 16 amendment for the full contract.

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

## 4. E3 — Concessions (`P4-E3`)

**Status: proposed, re-scoped 2026-10-07 by the owner's own example.**

*"An example concession happened in 2022 during COVID. Several of the tenants needed time to pay their rent,
so RHP deferred the lease for 6 months. The 2022 Q3 and Q4 payments were conceded and a 5th (Half) year were
tacked on. It was complicated to do practically without a mechanism governing it."*

That is three things at once, and the earlier proposal covered only the first:

1. **Forgiveness** — a charge credited, with a reason. Now available: the tenancy-and-money work
   ([ADR-017](decisions/ADR-017-charge-lifecycle.md)) gives every adjustment a reason and a date, and the
   close-out is the same mechanism with a different reason.
2. **A deferral plan** — six months of rent moved, an agreement about when it would be paid. This needs a
   place to record the agreement (what was deferred, until when, on what terms) rather than a note on a
   single charge.
3. **A term extension** — the fifth half-year tacked on in exchange. That changes the lease's terms, so it
   is the same family as P3-E2 (early termination) and P3-Q3 (renewal).

**The tenant *does* see the concession's wording**, settled 2026-10-03: a concession is a decision made *about*
the tenant and communicated to them, so the tenant-facing note is a separate field from the office's internal
reason, and office shorthand never reaches a tenant page. That remains a deliberate exception to ADR-011.

**It is no longer a candidate to fold into the charge-lifecycle work.** Its own design, informed by that
example, is the honest way to build it — and the parts it needs (a dated adjustment with a reason, and the
ability to extend a term) are the parts Phase 3 and Phase 4 are still missing.

---

## 5. E4 — Retroactive onboarding

**October 21, 2026 E10 refinement:** [Held credit and dated repayments](design/held-credit-repayments.md)
adds manager-confirmed credit application and payment dates/installments for starting debt only.
Installments never create charges. Broader E3 concessions and accounting remain separately reviewed.

**Status: built** — in `main`; the decision record is
[ADR-016](decisions/ADR-016-retroactive-onboarding.md). Owner's words: *"all of the RHP tenants have a
currently live lease, and I do not intend to wait for their lease to expire to enroll them into this new
system."*

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

### What was built

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
   hand is never removed by regenerating, and a regression test pins that. Moving a lease onto this
   template from a step-up or triple-net one drops the step-up rule the old template carried — the model
   refuses a rule on a template that has none, and the form used to leave the office holding that refusal
   with no way to save (ADR-016). The lease page says the rule was cleared and where the amounts go.
4. **An NNN series the office stages** — dated rates, adjusted when the lease says. The live lease says
   **October**; our earlier note (from the owner's first document) said November, and the docs are corrected
   to "whenever the lease says". **NNN is a term of the lease, not a rent template**: entering a lease whose
   paper states its own rent *and* charges NNN exposed E1's conflation of the two, so `Lease.carries_nnn`
   now records it independently of the template (ADR-013 amended, ADR-016). Michael's lease is `STATED` +
   NNN, which is what it says.
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

## 6. E5 — Move-out settlement (`P4-E5`)

**Status: proposed**, agreed in principle by the owner (P4-Q6: *"P4-E5 is good"*), and the next piece
now that the lifecycle work and Phase 6 are behind us.

The lifecycle correction now permits settlement of an ended, zero-balance account with no pending payment
and no nonzero recorded deposit. Managers can reopen only the financial account with a reason. That is
account closure, not the complete move-out workflow: deposit disposition, the final statement, and a record
of what was withheld or returned remain unbuilt. Any nonzero recorded deposit blocks settlement until E5
records its complete disposition. E5 is where the remaining workflow belongs:

- **The deposit** — returned, or applied against what is owed. Phase 4 deliberately kept it off the ledger
  ("held money is not rent paid ahead"), so this is the first piece of work that has to decide what a deposit
  *is* in the ledger's terms: a liability RHP holds, settled by a payment out or a write-off in.
- **Deductions** — each with a reason and, now that Phase 6 exists, its evidence: a filed document
  (E6's mechanism is the same one).
- **A final statement** — what was owed, what was paid, what was withheld, what was returned. A tenant
  leaving should be able to read one page and see the whole tenancy.
- **A forwarding address**, so the statement can be sent and the deposit returned.

It touches the tenant's statement (ADR-011), the deposit field (ADR-008), and documents (ADR-022, now
built), which is why it did not fold into the guard: the guard is small and correct now, and the
settlement deserves its own design and its own decision record.

---

## 7. E6 — Post-tenancy charges with their evidence (`P4-E6`)

**Status: proposed — no longer blocked.** Phase 6 is built (`apps/documents`,
[ADR-022](decisions/ADR-022-documents.md)), so the thing the owner was waiting for exists: a document can
be filed against a tenancy today. The owner decided the order: *"Wait for Phase 6 so a charge always has
its evidence."* That order has been honoured, and E6 is now a real next step rather than a blocked one.

One design question is left for E6 itself: a `Document` links to a tenancy, a property or a tenant — not
to a charge — so E6 has to decide how a post-tenancy charge points at the documents that support it
(most likely through the tenancy the charge belongs to, with the specific files named). Filing the
evidence is possible; citing it from a charge is E6's work.

The design, from the owner's own answer to P4-Q3 — the part E5 deliberately leaves out:

- **Charge types are separated by origin.** Recurring charges (rent, monthly fees) stop at the end of a
  tenancy. **Post-tenancy charges** — damage, cleaning, an unpaid balance, an NSF fee, an early termination
  fee — may be raised after it.
- **Each one carries its just cause:** a **reason code** (damage, cleaning, unpaid rent, NSF, early
  termination, other), **the lease clause it rests on**, and **supporting evidence** — photos, invoices, an
  itemised list. "This protects you in disputes," in the owner's words.
- **It relaxes exactly one line** — the refusal in `refuse_if_not_chargeable` — which is why that refusal is
  a named function with the seam marked rather than a condition buried in a view.
- Until it exists, ended tenancies accept payments and corrections only while their financial account is
  open. Reopening a settled account never restores occupancy or permits recurring rent.

---

## 8. E7 — A unit's ledger history (`P4-E7`)

**Status: proposed**, from the owner's answer to P4-Q5: *"Maybe all units have a ledger history that can be
expanded to show the details."*

Today a unit's tenancies are reachable one at a time from the lease list, and the ledger shows one tenancy.
What the owner describes is the unit as the unit of history: every tenancy it has had, with its final
position, expandable.

**The rule it must not break:** a tenant sees only their own tenancy (ADR-003). The history is an
office-facing view — the same answer the owner gave for the ledger itself — and the isolation test in
`tests/ledger/test_charge_lifecycle.py` already pins that a new tenant on a unit never sees the previous
tenancy's money. Reporting (Phase 10) and the admin dashboard (Phase 9) are where this belongs, because it is
a reading of settled history rather than new arithmetic.

---

## 9. E8 — A tenant's request for early termination (`P3-E2`)

**Status: proposed**, filed under Phase 3 because it changes a lease's terms. From the owner's answer to
P4-Q1: *"The tenant may also need a 'request early termination' button, which, if approved, would trigger the
early termination clauses. We may not have that in our current system."*

What it needs: a request from the tenant's own area, a decision by the office, an audit trail, and the
**early-termination clauses** the lease carries — which means reading a clause out of the lease's paper and
turning it into a charge and a date. The financial half is already prepared for it: `TENANT_EARLY` is one of
the end reasons, and an early-termination fee is one of the reason codes E6 will carry.

It is the same family as **P3-Q3 (renewal)** and the term-extension half of **E3**, and the three are worth
designing together: all of them change a lease's term after it was signed.

---

## 10. E9 — Plain-language interface

**Status: built.** This presentation extension removes development commentary from product pages, adopts the
vocabulary in ADR-021, and reorganizes the staff lease account around the questions an operator asks. It does
not change route paths, store a balance, add a payment provider, or add general-ledger accounting.

Future property accounting is limited to properties owned by RHP. Phase 11 is separately approved as an
optional 2027 capability for one-time ACH and ACH autopay using processor-hosted or tokenized bank linking;
RHP will never store bank credentials.

### October 20, 2026 — financial clarity follow-up

Owner authorized a separate audit of language, icons/color and manager editing workflows after the
Phase 9 local merge. [Findings](design/financial-audit.md), [vocabulary](design/financial-vocabulary.md)
and [proposed implementation units](design/financial-implementation.md) preserve the original Outline
notes. The owner subsequently approved the financial first implementation release for staff and
tenants. The delivered `codex/financial-clarity` checkpoint provides one shared lease financial
workspace, amount-only red/green/purple/black semantics, expandable due-date bills and reviewed
existing-history recovery. The owner accepted these changes and authorized local preservation and
squash into `main`. Remaining financial forms and nonfinancial editing findings remain deferred;
the owner's forthcoming onboarding solution will be reviewed separately. No push or deployment is authorized.

The audit's F05 identifies a separate legacy classification risk: starting credits are represented
as cleared payments and can appear in monthly received totals. An isolated test reproduces it; this
presentation study does not change financial rules, infer cash, or rewrite historical records.
New visual examples remain local until a permitted Outline upload path works; text publication and
ecosystem verification are separate from asset-publication completion.

## 11. E10 — RHP property accounting

**October 21 kernel decision — [ADR-028](decisions/ADR-028-one-kernel.md):** the E10 cutover's unfinished
deletion is completed on an **industry-standard basis** (owner direction: where RHP's early accounting
choices differ from established property-management practice, industry practice decides; the foundation
is kept, not rebuilt). One opening position (`LeaseOpeningRecord`; E4 onboarding retired), one allocation
engine (persisted applications), one charge write path, deposits as a held-liability register with a
move-out outcome, and the kernel vocabulary in [`docs/kernel/`](kernel/events.md). A `FUTURE` lease state
and a person/login split are accepted direction, staged before E5/E6. The conformance table in ADR-028
records what RHP keeps (append-only derived sub-ledger, corrections as entries, persisted applications,
due-date charging), what it changes (deposits, lifecycle, party) and what is operational work (scheduled
posting Phase 12; receipt vs bank settlement B3). B1–B5 remain separately reviewed.

**October 21 M2a accepted — [ADR-029](decisions/ADR-029-lease-future-and-people.md):** a signed tenancy
whose term has not begun is `FUTURE` (scheduled, not active, posting nothing), starts automatically by
date, and may coexist with the current active lease on its unit; a deposit may be received before
move-in. The person/login split (M2b) is the next slice. Evidence: TurboTenant's automatic
Upcoming/Draft statuses, AppFolio's pre-move-in resident checklist, PropertyBoss contacts with an optional
portal login, DoorLoop's independent portal access.

**October 21 refinement accepted for local merge:** [Held credit and dated repayments](design/held-credit-repayments.md)
keeps credits separate until manager-confirmed application and schedules existing opening debt without
new charges. Only due installments count as payable/overdue; full principal stays in account balance.
The tenant-cutover refinement does not implement B1–B5; financial expansion pauses for accounting review.

**Tenant-cutover implementation accepted for local merge October 21:** the owner approved ADR-027 and the simple first release
in `design/accounting-cutover-plan.md`. Manual stated balances do not require verified source history.
The development database is archived/restored before a fresh synthetic database is selected. B1–B5
accounting remains separately reviewed; no GL, bank matching or tax-readiness is delivered by cutover.

**Status: Building** — the decision for the stack is [ADR-026](decisions/ADR-026-property-accounting.md),
the kernel direction is [ADR-028](decisions/ADR-028-one-kernel.md), and the working blueprint is
[the property-accounting study](design/property-accounting.md).

This extension adds landlord-side accounting only for properties Robert Hunter Properties owns. It is not
third-party property-management accounting and does not change the tenant rent ledger. The owner's question
was whether to integrate established accounting software instead of building one; the answer, from the
products that do this for a living — Buildium, AppFolio, TenantCloud and Innago — is that **property
accounting is built in**, and QuickBooks is a one-way copy for an accountant. GnuCash was examined and
rejected as a backend: it is a single-user desktop ledger with no API, whose database must not be written
from outside its own libraries.

Built in: a chart of accounts, journals posted from the existing sub-ledger, bank accounts with statement
import and a three-way reconciliation, cash disbursements, security-deposit movements, an AR control that
must equal the tenant-ledger total, and statements (trial balance, income statement by property, balance
sheet, cash flow, Schedule E summary). Exported, not integrated: a journal CSV and a plain-text journal for
an accountant. Out of scope: trust/escrow accounting and management fees (RHP owns its properties),
third-party owner distributions, 1099 e-filing, depreciation and tax schedules (the separate business-side
domain in §13), and payment processing (Phase 11).

The design is sliced `E10-B1` … `E10-B5`, each with its own migration, tests and owner review; the blueprint
carries the chart, the posting rules, the controls and the build order.


---

## 12. Recorded decisions

### The tenancy lifecycle and what ending does to money — decided 2026-10-07

Owner-decided in Plane, one work item per question, and **written into the specification** rather than
registered here, because the specification was silent rather than wrong: it defined the states without
saying what they mean for money, and left the charging habit unstated.

- **A charge falls due on its due date and is raised then, never ahead of it.** The lease says what will be
  owed; the ledger records what is owed (P4-Q7).
- **Occupancy and money have separate states** — a tenancy is draft, active, or ended; its financial
  account is open or settled. Ending needs a citable reason (P4-Q1).
- **When a tenancy ends, the months it will not use are closed out by adjustment**, never deleted (P4-Q2).
- **Only a running tenancy takes new charges**; payments and corrections require an open account;
  post-tenancy charges need their just cause, so they wait for E6, which was itself waiting on Phase 6
  (P4-Q3, P4-Q4).
- **An ended tenancy stays in Rent & Payments**, marked with its account state and final position; a new
  tenant on the same unit never sees the previous tenancy's money (P4-Q5).
- **Move-out settlement is its own extension** (P4-Q6 → E5).

Records: [ADR-017](decisions/ADR-017-charge-lifecycle.md), [ADR-020](decisions/ADR-020-tenancy-lifecycle.md),
[the case study](workflows/tenancy-and-money.md), and the specification's own amendment notes in its Phase 3
and Phase 4 sections.


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

## 13. Directions not yet proposed

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

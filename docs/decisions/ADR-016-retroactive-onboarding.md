# ADR-016: Bringing a live tenancy into RHP

- **Status:** Accepted (extension E4, approved 2026-10-03)
- **Date:** 2026-10-03
- **Context:** every RHP tenancy is live now, and none of them began in RHP

## Context

RHP is being introduced under tenancies that are already running, some for years. The only path the
system had was "activate the lease, work the schedule out, create charges", and the generator walks from
the term's start — so it bills the whole past as if it were new.

On a real lease (Michael Ortolano, 910 SE Stark, June 2022 → May 2027) that produced **108 charges and a
$100,536.18 "balance"**, $96,533.60 of it reading as past due, for a tenant who is paid up. That figure was
removed by hand on 2026-10-03, with a written record — and a manual reset is not a feature.

The same lease exposed two more gaps:

- Its rent is **six stated amounts** at irregular dates, including a mid-year change (November 2023, "Extra
  Space"). E1 works a schedule out from a rule and cannot express that.
- Hand-entering a period at a date the rule does not plan was **silently deleted by "Work the schedule out
  again"** — verified in a rolled-back transaction, not inferred.

## Decision

### A lease has a cutover: the first month RHP bills for

`Lease.billing_start_date`. Blank means the term's start, which is what a tenancy that began inside RHP
does; the invariant is that **a lease with no cutover behaves exactly as it did before this decision**, and
a tenancy that starts this month or later never needs one.

Generation walks from `max(term start, cutover)`, so a tenancy taken on part-way through its term is never
billed for the months before the office took it on.

### The guard: an unplaced tenancy cannot be charged

A live lease that began before this month and has no cutover **refuses to raise charges**, with a message
that points at the lease page. That is what makes the phantom debt impossible rather than merely
discouraged. The cutover is what unlocks charging — an explicit decision by a person — while the onboarding
record says *how* the tenancy was placed.

### Two ways in, both recorded, neither inventing a debt

- **Raise the history** (default): the term's months are billed from its start, and everything the tenant
  had already paid is brought in as **one settling payment**. The ledger's existing oldest-first allocation
  does the rest, so the balance is the true position and the tenant has a complete statement. No new money
  arithmetic: a charge is a charge and a payment is a payment.
- **State the position** (fallback): charging starts at the cutover and the past is one line — a
  **brought-forward balance** (`ChargeKind.OPENING`, the month's own charge) or a **credit on account**
  (an ordinary payment, because money held for a tenant is money, not a charge).

Recording a credit as a payment rather than a negative charge is deliberate: the ledger already refuses a
reduction that is not an adjustment naming a charge, and a credit is not a correction — it is money on
account, and it should behave like one when future months are billed.

### The lease as written is entered, not reconciled

A **stated** lease (`LeaseTemplate.STATED`) says "this is what the paper names": the office adds and removes
dated amounts, and RHP never invents one. The same action is available on a stepped lease, because a
mid-term change is a real thing a rule cannot plan — and **a period the office entered by hand is never
removed by regenerating a schedule** (the defect above, now pinned by a test).

The due day, the amounts and the square footage are entered as the lease states them. Where a lease
disagrees with itself — Michael's says both "$305/month" and "$0.19/sf" for 2022 NNN — the office records
what governs. RHP's job is to make a drifted lease legible to both sides, not to pick a winner.

### NNN is a term of the lease, not a rent template

Entering RHP's own lease is what exposed this. Its base rent is stated — six amounts the paper names — and
its tenant still pays NNN. Under E1 the two were one field: NNN was a *template*, so a lease that wrote
its own rent could not carry it, and the office had to choose which half of the truth to record.

`Lease.carries_nnn` is now its own term, and `Lease.uses_nnn` answers "does this lease pass the property's
operating costs on to the tenant?" for the ledger, the NNN screen and the onboarding card. The `NNN`
template stays as the shorthand for the common case (a step-up rent *and* NNN), and choosing it records
the flag — on the model's `save()`, so no path can produce a triple-net lease whose flag says otherwise.
Every existing triple-net lease was migrated to it, so no lease's charges changed (ADR-013, amended).
Michael's lease is entered as `STATED` + `carries_nnn`, which is exactly what its paper says.

### Changing the template to one with no rule clears the rule

Moving RHP's own lease from "Triple net" to "the lease states the amounts" was **refused**, with the
message that the template has no step-up rule. Nothing was wrong with the change: the browser posts the
old month and percentage back, and the model — correctly — refuses a step-up rule on a template that has
none. What the office read was "this lease cannot be saved".

The form now drops a posted rule that the chosen template cannot carry, and the lease page says so: *the
step-up rule was cleared because this template has none; add the amounts the lease names on the lease
page.* The model's guard stays where it is, for the paths that are not this form. The rule is only ever
dropped when the template cannot hold it, so a step-up or triple-net lease still cannot be saved without
a month and exactly one basis.

### Acts and permissions

Placement, stating an amount and removing one are **admin** acts, like every other decision that becomes
money. The guard's message, the lease page's onboarding card and the ledger's refusal all say the same
thing in the same words, so nobody has to guess why a button did nothing.

## Consequences

**Positive**

- The phantom balance is structurally impossible: a tenancy cannot be billed before somebody places it.
- A live tenancy can be brought in with either a complete history or a single honest opening line, and the
  record says which, with who did it.
- Real leases with irregular steps, mid-year changes and an annually adjusted NNN are now representable.
- Nothing about the ledger's arithmetic changed: the opening entries are ordinary charges and payments.

**Negative / accepted trade-offs**

- One more lease field and one more table, plus a fourth template. The alternative was a special-case
  "import mode" that would have touched the ledger.
- A tenancy that is behind by a month or two still needs placing before it can be billed (method A with
  `received_total = 0` is the two-click answer). Accepted: the gesture is what keeps the phantom out.
- Method A's settlement follows oldest-first allocation, not the tenant's actual cheque order. The totals
  are right; the attribution of a shortfall is the ledger's existing rule (ADR-008).
- The onboarding record is written once and not edited. A tenancy placed wrongly is corrected the way money
  is: with adjustments, or by re-placing it while it has no charges.

## Alternatives considered

- **Leave it to the office not to press the button**: exactly what produced $100,536. Rejected.
- **Cutover only, with no way to bring the history in**: the tenant would never see their own past, and
  reports could not be run on it. Kept as the fallback rather than the default.
- **History only**: no way to place a tenancy whose payment records are unknown or unverifiable.
  Rejected.
- **Move the lease's start date forward to the cutover**: loses the real term — the document, the end date,
  the renewal option — and makes the tenancy's own record wrong. Rejected.
- **A brought-forward credit as a negative charge**: the model refuses a reduction that is not an
  adjustment naming a charge, and it should: the tenant's money is a payment, not a correction.
- **Prorating the cutover month**: unchanged from Phase 4 — a part month is a one-off charge typed by the
  office.

# ADR-017 — What ending a lease does to money

**Status:** Proposed — awaiting the owner's answers to P4-Q1 … P4-Q6
**Date:** 2026-10-06
**Supersedes:** nothing. Amends no earlier record, but fills a gap they left.
**Related:** [ADR-007](ADR-007-lease-modeling.md) (lease lifecycle), [ADR-008](ADR-008-rent-ledger.md)
(append-only ledger, corrections as entries), [ADR-011](ADR-011-tenant-statement.md) (corrections absorbed),
[the case study](../workflows/tenancy-and-money.md), [Phase 4 record](../phases/phase-04-rent-ledger.md)

## Context

`lease.status` is `DRAFT`, `ACTIVE` or `ENDED`, and ending a lease is a deliberate act by a person
(ADR-007). The ledger is append-only: charges are raised, money is recorded, and mistakes are corrected by
an adjustment or a reversal rather than an edit (ADR-008).

Nothing connects the two. The specification says nothing about what ending a lease does to money, so:

- a charge can be raised on an ended lease — `create_charge` validates nothing about the lease, and
  `generate_charges` refuses only a draft and an unplaced retroactive tenancy;
- an ended lease is listed in `/manage/ledger/` with the same actions as a live one, because `ledger_rows`
  excludes only drafts;
- rent already raised for months that will no longer happen has no close-out, so ending a tenancy leaves
  obligations standing for a term that is over;
- a lease whose term has passed but which nobody ended stays `ACTIVE`.

The leases app already holds the intended rule — `_refuse_ended_terms`: *"An ended tenancy is history: its
money stays correctable, its terms do not."* It guards the rent schedule, the NNN rates, onboarding and the
lease form. The ledger never asks it.

Evidence: on 2026-10-06, lease 14 was ended at 22:00 and a $1,000 manual charge (#1081) was created against
it at 22:01, with November's rent already raised. Full timeline in the case study.

## Decision — to be recorded when answered

Each question is recorded in the [Phase 4 record](../phases/phase-04-rent-ledger.md#open-questions-for-the-owner)
with a stable id, so it can be mirrored to Plane and answered there. The recommendation below becomes the
decision unless you change it; the specification gains a paragraph for it in the same commit, with a note,
because the specification is where a rule like this belongs.

### P4-Q1 — What "ending a lease" means for money

**Recommended:** ending freezes the **terms** and stops **new obligations**; it does not touch money already
charged, which stays correctable.

*Alternative considered:* ended means read-only, including money. Rejected — a tenancy ended with the wrong
final figure could then never be corrected, which contradicts ADR-008.

### P4-Q2 — Rent already raised for months that will not happen

**Recommended:** ending **offers a close-out** — each remaining charged month inside the term cancelled by an
adjustment dated at the end, naming the reason ("tenancy ended 2026-10-06"). Append-only, visible on the
statement, reversible by another adjustment.

*Alternatives considered:* (a) leave them and let the balance carry — this is what happens today and it
produces a debt for a month nobody occupied; (b) delete the charges — refused, because the ledger's whole
guarantee is that history is never erased; (c) block ending a lease while future charges exist — defensible
but it turns a paperwork act into a ledger puzzle.

### P4-Q3 — Which money actions an ended lease still allows

**Recommended:** payments **yes** (arrears get paid after a tenancy ends); adjustments, reversals and voids
**yes** (they correct history); new charges — manual, generated rent, NNN, responsibility — **no**.

### P4-Q4 — Where the rule is enforced

**Recommended:** in the **services** (`generate_charges`, `create_charge`), because the ledger screen, the
lease screen and `manage.py generate_rent_charges` all pass through them. A rule enforced only in a view is
a rule that the next caller will not know about. The screens then hide the actions and say why, in the words
`_refuse_ended_terms` already uses.

### P4-Q5 — How an ended lease reads in Accounting

**Recommended:** it stays listed — money is still owed or held, and hiding it would be worse — but marked
ended, with no charging actions and its final position stated instead of a next-due projection.

### P4-Q6 — Move-out settlement

**Recommended:** not in this work. Deposit returns, deductions, a final statement and a forwarding address
are a real need and a bigger design; they belong in their own extension, filed under the phase that builds
it. Recording it here keeps it from being smuggled into this decision.

## Consequences

**If the recommendations stand:**

- The phantom-obligation class of bug becomes structurally impossible, in the same way E4 made phantom
  arrears impossible for a retroactive tenancy: one predicate, consulted by every path that creates an
  obligation.
- Corrections keep working on ended leases, so a final figure can always be made right.
- Ending a lease becomes a two-part act — the paperwork and the money — and the screen must present that
  honestly, since the close-out changes what the tenant owes.
- The specification gains the rule it is missing, and P3-Q1 ("does a lease expire by date") becomes a
  smaller question, because an expired-but-active lease now has a screen that says so.
- **P4-E3 (concessions) may shrink:** forgiveness and deferral are charge-lifecycle decisions, and the
  close-out act is a special case of one. E3 should be re-scoped after this is answered rather than designed
  in parallel.

**Negative / accepted trade-offs:**

- One more guard to remember when adding a future charge kind: the predicate must be consulted, and a test
  should fail if a new kind ignores it.
- A close-out is a visible, dated money event the tenant will read on their statement; the wording matters
  as much as the arithmetic.

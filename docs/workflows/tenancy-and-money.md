# The tenancy and its money — a case study

**Status:** analysis complete, decisions open (P4-Q1 … P4-Q6)
**Owner's finding, 2026-10-06:** *"I tried ending the lease on unit Austin/Ruiming, and I was still able to
add charges to the unit even though the lease was ended."*
**Related:** [Phase 3 record](../phases/phase-03-lease-management.md), [Phase 4 record](../phases/phase-04-rent-ledger.md),
[ADR-007](../decisions/ADR-007-lease-modeling.md), [ADR-008](../decisions/ADR-008-rent-ledger.md),
[ADR-017](../decisions/ADR-017-charge-lifecycle.md)

## Why this document exists

Charges feel like they float. They are attached to a lease row, but nothing ties them to the *life* of the
tenancy: a charge can be raised on a lease that has ended, and a lease can end while obligations for months
that will never happen are still on the books. This is not a bug in one screen — it is a missing decision.
The specification never says what ending a lease does to money, so the code inherited the silence, and two
apps filled it in differently.

## The two lifecycles

**A tenancy** (`lease.status`, and the term dates):

| State | Reached by | What it means | What it permits |
| --- | --- | --- | --- |
| `DRAFT` | creating a lease | working copy; terms can still change | no ledger at all — the ledger screen says so |
| `ACTIVE` | a person activating it | the agreement is in force | charging, paying, correcting |
| `ENDED` | a person ending it | history; terms are read-only | **undefined for money** — this is the gap |
| term expired, still `ACTIVE` | the calendar passing `end_date` | the agreement has run out but nobody said so | charging is bounded by `end_date`, but the record still reads "active" (P3-Q1) |

**A charge** (`Charge`, append-only, `apps/ledger/models.py`):

| State | Meaning | How it changes |
| --- | --- | --- |
| raised | an obligation on a due date — rent, NNN, a responsibility share, a manual charge, an opening line | only by generating or creating more |
| outstanding / part-paid / paid | a *reading*, computed by `build_ledger` from charges, clearances and adjustments | never stored |
| corrected | an adjustment in the opposite direction, absorbed into the charge it corrects | a new row, never an edit |
| settled by money | a cleared payment allocated oldest-first | a reversal, never a deletion |

The two lifecycles share exactly one field: `Charge.lease`. Nothing in a charge says which *part* of the
tenancy's life it belongs to, and nothing in the tenancy says what should happen to charges when it ends.

## Every money action, and what it is

| Action | Code | Kind | On an ended lease today |
| --- | --- | --- | --- |
| Create the missing months | `generate_charges` | new obligation | **allowed** — refuses only a draft and an unplaced retroactive tenancy |
| Add a one-off charge | `create_charge` | new obligation | **allowed** — refuses nothing at all |
| Record money received or expected | `record_payment` | money in | allowed, and *should* stay allowed: arrears still get paid |
| Mark a payment cleared | `clear_payment` | money in | allowed |
| Correct a charge | `create_adjustment` | correction | allowed, and should stay allowed: history must be correctable |
| Reverse a payment | `reverse_payment` | correction | allowed |
| Void a payment | `void_payment` | correction | allowed |

So the line that needs drawing is **new obligations** versus **money in** versus **corrections** — not
"ended leases are read-only", which would make a genuine mistake uncorrectable.

## Where the two fail to meet

1. **A new charge can be raised on an ended lease.** `templates/management/ledger_lease.html` gates its
   whole Actions card on `DRAFT` alone; `generate_charges` refuses only a draft; `create_charge` refuses
   nothing.
2. **An ended lease still reads as live in Accounting.** `ledger_rows()` excludes only drafts, so
   `/manage/ledger/` lists it with the same actions, the same urgency ordering and no marker.
3. **Future obligations have no close-out.** `RHP_CHARGE_HORIZON_MONTHS` (default 1) means a month is
   usually already raised when a tenancy ends, and `rent_due_dates` bounds generation by `end_date` — but
   nothing cancels what was raised for months that will no longer happen.
4. **A lease that runs past its term stays `ACTIVE`.** The status word says active, so a screen that trusts
   status treats an expired tenancy as live (P3-Q1).

### Evidence, from the development database

On 2026-10-06, lease 14 (1101 Hoodview / Austin/Ruiming, a real imported tenancy used for testing):

| Time | What happened |
| --- | --- |
| 22:00 | the lease was ended (`LEASE_ENDED`, actor `rhpadmin`) |
| 22:01 | charge `#1081` "Test Fee", $1,000.00, kind `MANUAL`, was created against it |
| before that | charge `#53`, rent for **November 2026**, had already been raised |

The balance moved from $8,756.00 to $9,756.00 on an ended tenancy, with November's rent still to come. The
database is not a live system and the charge was a deliberate test (the owner's words: *"That was a bogus
charge to test functionality"*), which is why it is repaired as a cancelled charge rather than deleted — the
same way any correction is made.

**Repaired 2026-10-06, owner-approved:** the lease was restored to `ACTIVE` (audit event #1153) and the
$1,000 was cancelled by adjustment **#1082** (#1154), leaving the balance exactly where it was, at
$8,756.00, with the original charge still visible and nothing left to pay on it. The audit trail now reads
as the whole story: ended at 22:00, charged at 22:01, restored and corrected at 22:51.

Reproduction: open a lease's ledger, end the lease from the lease page, and return to the ledger — the
Actions card is still there and a charge still posts.

## What the code already believes

`apps/leases/views.py::_refuse_ended_terms` has the rule, and says it well:

> *"An ended tenancy is history: its money stays correctable, its terms do not."*

It guards the rent schedule, the NNN rates, onboarding and the lease form. The ledger never asks it. That is
the whole defect in one sentence — the rule exists, in one app, and is enforced in neither.

## What the specification says

Nothing. `PHASE 3` defines the three states and says expired leases remain historically available.
`PHASE 4` lists the ledger actions with no lifecycle coupling. The silence is the reason this needs a
decision record and a specification amendment, not just a guard: **the rule does not exist yet, so it cannot
simply be enforced.** When the questions below are answered, the rule goes into the specification first, in
its own commit, with a note — that is what the specification asks of any change to it.

## The decisions this needs

Recorded as questions with recommendations in [ADR-017](../decisions/ADR-017-charge-lifecycle.md) and in the
[Phase 4 record](../phases/phase-04-rent-ledger.md#open-questions-for-the-owner):

| # | Question | Recommendation |
| --- | --- | --- |
| P4-Q1 | What does "ending a lease" mean for money? | Freeze the terms, stop new obligations, leave charged money correctable |
| P4-Q2 | What happens to rent raised for months that will not happen? | A close-out act at the moment of ending: adjustments naming the reason, never deletions |
| P4-Q3 | Which money actions does an ended lease still allow? | Payments and corrections yes; new charges no |
| P4-Q4 | Where is the rule enforced? | In the services, so every screen and the management command obey it |
| P4-Q5 | How does an ended lease read in Accounting? | Listed, marked ended, no charging actions, final position stated |
| P4-Q6 | Is there a move-out settlement (deposit, final statement)? | Not in this phase; its own extension |

## What the fix will look like

Specified now, built only after the answers (its own branch, `rhp-charge-lifecycle`):

- one predicate on `Lease` beside `is_editable` and `needs_onboarding`, consulted by `generate_charges` and
  `create_charge`, refusing in the words the leases app already uses;
- a close-out action on the ledger (admin) that cancels the remaining charged months by adjustment, in one
  transaction, with one audit event naming the lease end;
- the ledger screen and the ledger list reading the lease's state instead of gating on `DRAFT` alone;
- tests: money and authorization first — a refused charge on both paths, a payment and an adjustment still
  accepted, a direct POST refused, and the close-out producing adjustments with the balance still correct.

**Not built yet, on purpose.** The owner's instruction was to document and decide first.

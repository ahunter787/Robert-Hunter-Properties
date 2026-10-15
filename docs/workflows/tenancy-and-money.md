# The tenancy and its money — a case study

**Status:** decided and built (P4-Q1 … P4-Q7), amended 2026-10-14 to separate occupancy from
the financial account — [ADR-017](../decisions/ADR-017-charge-lifecycle.md),
[ADR-020](../decisions/ADR-020-tenancy-lifecycle.md)

**Owner's finding, 2026-10-06:** *"I tried ending the lease on unit Austin/Ruiming, and I was still able to
add charges to the unit even though the lease was ended."*

## Why this document exists

The original product had one lease status trying to answer two different questions: whether the tenant
still occupied the unit, and whether RHP still had financial work to do. That made an ended lease accept
new charges and later made "settled" look like an occupancy state. The governing decision is now that the
two lifecycles are explicit and independent.

## The two lifecycles

| Lifecycle | State | Meaning |
| --- | --- | --- |
| Occupancy (`Lease.status`) | `DRAFT` | Working terms; no ledger activity |
| Occupancy (`Lease.status`) | `ACTIVE` | Current tenancy; scheduled and one-time charges may be posted |
| Occupancy (`Lease.status`) | `ENDED` | Occupancy stopped; terms and end facts are historical |
| Financial account (`Lease.account_status`) | `OPEN` | Payments and corrections may continue subject to the occupancy rules |
| Financial account (`Lease.account_status`) | `SETTLED` | Financially closed; every mutation is locked until explicit reopening |

The calendar does not change `Lease.status`; a staff member ends the tenancy and records the effective
date, reason code, and note. The signed term remains unchanged.

## Money actions

| Action | Active/open | Ended/open | Ended/settled |
| --- | --- | --- | --- |
| Post due scheduled charges | allowed | refused | refused |
| Add a one-time charge | allowed | refused until the evidence-backed P4-E6 workflow exists | refused |
| Record or clear a payment | allowed | allowed | refused |
| Void or reverse a payment | allowed | allowed | refused |
| Add an adjustment | allowed | allowed | refused |
| Settle the account | refused | allowed only when all prerequisites pass | already settled |
| Reopen the account | not applicable | not applicable | allowed with a reason; occupancy remains ended |

These rules live in services rather than templates, so direct requests, management commands, and screens
all enforce the same boundary. Ledger entries remain append-only; corrections are adjustments or
reversals, never edits or deletions.

## Ending and settlement

Ending closes out already-posted rent for periods after the effective end date with named adjustments.
It stops new obligations but keeps the open account available for arrears and corrections.

Settlement is a separate act. It requires:

- ended occupancy;
- a zero account balance, with no credit remaining;
- no pending payment; and
- no recorded security deposit, until P4-E5 records the deposit's complete disposition.

Settlement records the timestamp, manager, optional note, and an audit event. Reopening requires a reason,
records another audit event, and changes only `account_status` to `OPEN`. It never changes `ended_on`,
restores occupancy, or permits recurring rent on the ended tenancy.

## Manager and administrator boundary

Managers perform portfolio-wide operational work: lease terms and schedules, expense recoveries, tenant
activation, payments, corrections, settlement, and financial-account reopening. Administrators retain
role changes, Django administration, site configuration, and destructive deletion. Property assignments
for a future hired manager remain a stretch goal.

## Historical evidence

On 2026-10-06, development lease 14 (1101 Hoodview / Austin/Ruiming) was ended at 22:00 and accepted a
$1,000 manual charge one minute later. The test charge was corrected by an adjustment rather than deleted,
preserving the audit trail. This development database was not a live accounting system.

The defect led to three durable rules:

1. A charge is posted on its due date, never ahead of it.
2. New obligations stop when occupancy ends; future posted periods are closed out by adjustment.
3. A settled account is locked in the service layer and must be explicitly reopened before any financial
   mutation.

## Deliberately later

- P4-E5: deposit disposition, deductions, forwarding address, and final statement.
- P4-E6: post-tenancy charges carrying a reason code, governing lease clause, and supporting evidence.
- P4-E7: a staff-only unit ledger history spanning tenancies.
- P3-E2: tenant-requested early termination.
- Proration, automatic late fees, and general-ledger/property accounting.

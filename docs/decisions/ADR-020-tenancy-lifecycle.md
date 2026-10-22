# ADR-020 — Occupancy and financial-account lifecycles are separate

**Status:** Accepted (owner-directed, amended 2026-10-14; amended 2026-10-21 by
[ADR-028](ADR-028-one-kernel.md))
**Date:** 2026-10-07
**Related:** [ADR-007](ADR-007-lease-modeling.md) (the lease is ended by a person, never the calendar),
[ADR-017](ADR-017-charge-lifecycle.md) (what each state may do with money), [ADR-008](ADR-008-rent-ledger.md)
(append-only ledger), [Phase 3 record](../phases/phase-03-lease-management.md)

**October 21, 2026 amendment (ADR-028):** two changes, stated as direction and staged where noted.
(1) *Deposits (live now):* a nonzero recorded security deposit no longer blocks settlement forever — the
deposit register's held balance must be zero and a move-out outcome recorded, which is the path this ADR
previously said did not exist. The occupancy/account split itself is unchanged.
(2) *A future state (staged, M2):* a signed tenancy whose start date is ahead becomes `FUTURE`, so
occupancy **starting** is calendar-driven and idempotent while occupancy **ending** remains a person's
act with a citable reason. Until that change lands, the states remain `DRAFT/ACTIVE/ENDED` as below.

## Context

`LeaseStatus` was `DRAFT`, `ACTIVE` or `ENDED`, and `ENDED` carried no explanation and no way out. Ending a
tenancy was a single unadorned POST from the lease page: no reason, no record of when the tenancy actually
stopped as against the term it was signed for, and — once ended — no way back except a database edit.

The owner's finding, and the decision that followed: *"We need a system of ended, rather than simply 'Open /
Closed'. If an administrator ends the tenancy there needs to be a citable reason. The tenant may also need a
'request early termination' button, which, if approved, would trigger the early termination clauses."*

## Decision

### Two related state machines

| Occupancy state | Meaning |
| --- | --- | --- |
| `DRAFT` | the office's working copy |
| `ACTIVE` | the tenancy is running |
| `ENDED` | the tenancy has stopped permanently |

`LeaseAccountStatus` separately records `OPEN` or `SETTLED`. An ended tenancy normally has an open account
while payments and corrections finish. A settled account is locked against every financial mutation. Reopening
changes only the account to `OPEN`; it never restores occupancy or recurring rent.

### `ended_on` is not `end_date`

`end_date` stays the term the agreement was signed for. `ended_on` records the day the tenancy actually
stopped, which an end act sets (today by default, or the day the tenancy really ended). Ending early is
therefore **recorded rather than rewritten**: the tenancy reads "term to 31 December 2026 · ended 6 October
2026 (early)". Nothing in the ledger's history depends on the term being shortened. Reopening the financial
account never changes `ended_on` or any occupancy fact.

### Ending requires a citable reason

A `TextChoices` of `TENANT_EARLY`, `END_OF_TERM`, `EVICTION`, `SALE`, `MUTUAL`, `OTHER`, plus a **required
note**. Ending a tenancy is a decision somebody has to be able to cite later — in a dispute, in a report, or
in a conversation with the tenant — and the office is the only place that knowledge exists. Both appear on
the tenancy and in the audit event, with who did it and when.

### Ending is two steps on one screen

The first submit shows what the close-out would cancel for the date entered; the second ends the tenancy.
Changing the end date changes which months are being canceled, so the office sees that before it happens —
and a mistake is caught by the review rather than by an adjustment afterwards.

### Settling is an act; financial reopening is the escape hatch

- **Settle account** is manager-authorized and refused unless the tenancy is ended, its derived balance and
  credit are zero, no payment is pending, and no recorded security deposit awaits disposition. Until P4-E5
  records deposit disposition, any nonzero deposit blocks settlement. The current settlement timestamp,
  manager, and optional note are stored; every settlement remains in the append-only audit history.
- **Reopen financial account** is manager-authorized, requires a reason, and changes only the account from
  `SETTLED` to `OPEN`. The tenancy remains `ENDED`; recurring charges remain unavailable. Prior settlement and
  reopening events remain in the audit trail.
- Leases stored under the former combined `SETTLED` state migrate to `ENDED + OPEN` for manager review because
  the old data cannot prove that the security deposit was disposed of. The migration records a system event.

### Permissions

Managers have portfolio-wide operational authority: properties, units, leases, schedules, expense recoveries,
tenant invitations and activation, settlements, reopenings, and financial corrections. Administrators retain
role changes, Django administration, site configuration, and destructive deletion. Per-property manager
assignment is a future stretch goal.

## Consequences

**Good.** A tenancy's history is now legible end to end: why it ended, when it really stopped, what was
canceled, who closed it and who reopened it. The guard in ADR-017 has somewhere to point: it refuses new
obligations on `ENDED` occupancy and every mutation on a `SETTLED` account.

**Accepted.** One more condition for every screen to consider — a settled *account*, since the tenancy
itself is only ever ended — and a rule that it can only be reached deliberately, which means an office that
forgets to settle will simply see the tenancy in its Rent & Payments list until it does. That is the safe
direction.

**Not built, and why:** the tenant's **request early termination** — a button, an approval, and the early
termination clauses it triggers — is recorded as **P3-E2**, filed under Phase 3 because it changes a lease's
terms. The financial half is ready for it: `TENANT_EARLY` is an end reason and an early-termination fee is
one of the reason codes P4-E6 will carry.

**Deliberately unchanged:** a lease whose term has passed but which nobody ended stays `ACTIVE`, and
`rent_due_dates` bounds generation by the term, so nothing is raised beyond it. Whether a tenancy should
expire by date is P3-Q1, still open, and nothing here depends on it.

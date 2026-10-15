# Phase 9 — Admin dashboard

**Status:** Not started
**Milestone:** 5 — Communication and an operational dashboard for the RHP team
**Specification:** `docs/harness/master-spec.md`, `PHASE 9 — ADMIN DASHBOARD`

## Scope as specified

A useful operating overview — portfolio (properties, units, occupied, vacant), rent (due this month,
collected, outstanding), maintenance (open, in progress, over seven days), leases (expiring in 30 and 90
days) and a recent activity feed — with one hard rule: **every metric must lead to the underlying data**.
Decorative analytics are explicitly forbidden.

## What exists today

Nothing yet — this phase has not been built. What it builds on:

- **Derived counters already exist** on the staff landing page (`/manage/`): portfolio totals, occupancy,
  what is outstanding and what is late, each true for the role viewing it.
- **The reading that a dashboard needs** already exists as functions, not as stored numbers:
  `ledger_rows(...)`, `by_urgency(...)`, `totals(...)` and `build_ledger(...)` in
  `apps/ledger/services.py`, and `Lease.objects.current(...)` as the single definition of occupancy.
- **The audit table** (Phase 4) already records lease status changes, money movements and role changes —
  the recent activity feed reads it, and this phase is where the audit *browser* was promised.
- **The labelled panels** waiting for their data: the property maintenance summary and the unit's recent
  maintenance belong to Phase 7; the maintenance figures here depend on it.

## Decisions that govern it

No decision record exists for this phase yet. It needs one, mostly for the rule the specification already
states: every figure links to the records behind it, and a figure that cannot be explained is not shown.

## Extensions filed under this phase

None yet.

## Acceptance criteria and evidence

Not yet met — the phase is unbuilt. The specification's acceptance is by construction: no decorative
metrics, every tile drillable. This record adds the test the phase must pass:

- [ ] Every number on the dashboard is derived from the same functions the screens use, and clicking it
      lands on the list that produced it
- [ ] A role sees only the figures it may act on (a manager's dashboard is not an admin's)
- [ ] The activity feed reads the audit table rather than a second log

## Deliberately not here

Anything that cannot be drilled into; charts for their own sake; scheduled email digests (that is
Phase 8 + Phase 10); a tenant-facing equivalent (Phase 5 already answers the tenant's questions).

## Known gaps and defects

Nothing is broken — this phase does not exist yet. The gap it fills: the staff landing page answers "how
much is outstanding" but not "how is the portfolio doing, and what changed today", and the audit trail
written since Phase 4 has no browser.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P9-Q1 | What do you look at first, every day? | Rent: who is behind, and by how much. That should be the first tile, with the ledger list one click away. | *(awaiting)* |
| P9-Q2 | Does this replace the staff landing page, or sit beside it? | Replace it — two summaries of the same portfolio will disagree the moment one is missed. | *(awaiting)* |
| P9-Q3 | How current must the figures be — live, or refreshed hourly? | Live. Everything is derived from a handful of tables at this size, and a stale number is worse than a slow one. | *(awaiting)* |
| P9-Q4 | Should the audit browser be reachable from here, or from each record? | Both: a recent-activity feed here, and the full trail on the lease, the account and the charge. | *(awaiting)* |

## How to verify it

Not yet. When built: sign in as a manager and as an admin, confirm each figure matches the list it links to,
and that a manager cannot see a figure they may not act on.

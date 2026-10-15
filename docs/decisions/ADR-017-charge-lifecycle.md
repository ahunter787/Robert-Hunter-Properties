# ADR-017 — What ending a tenancy does to money

**Status:** **Accepted** (owner-decided, 2026-10-07) — the answers to P4-Q1 … P4-Q7 are recorded below
**Date:** 2026-10-06, decided 2026-10-07
**Related:** [ADR-007](ADR-007-lease-modeling.md) (lease lifecycle), [ADR-008](ADR-008-rent-ledger.md)
(append-only ledger, corrections as entries), [ADR-011](ADR-011-tenant-statement.md) (corrections absorbed),
[ADR-020](ADR-020-tenancy-lifecycle.md) (the states themselves), [the case study](../workflows/tenancy-and-money.md),
[Phase 4 record](../phases/phase-04-rent-ledger.md)

## Context

Ending a tenancy did nothing to its money. The specification defined the states and listed the ledger's
actions without connecting them, so:

- a charge could be raised on an ended tenancy — `create_charge` validated nothing about the lease, and
  `generate_charges` refused only a draft and an unplaced retroactive tenancy;
- an ended tenancy sat in `/manage/ledger/` with the same actions as a live one, because `ledger_rows`
  excludes only drafts;
- rent already raised for months that would no longer happen had no close-out;
- and a month's rent was raised a month *before* it fell due, so every tenancy that ended left an obligation
  to unwind.

Evidence: on 2026-10-06, lease 14 was ended at 22:00 and a $1,000 manual charge (#1081) was created against
it at 22:01, with November's rent already raised. Repaired the same day by adjustment, nothing deleted.

The answers were worked in Plane, one work item per decision, under *"Charge lifecycle — working area
(Phase 4)"*.

## The decisions, as answered

### P4-Q7 — Raise rent on its due date, not ahead of it

**Decided:** a charge falls due on its due date and is raised **then**, never before.
*Owner:* "We'll raise on the due date. We'll address early notification systems like a '5 days until rent is
due' system in Phase 8."

The lease says what will be owed; the ledger records what is owed. The tenant's "coming due" figures were
already derived from the lease (ADR-012), so billing the future bought nothing and created the whole
close-out problem. Implemented by removing the charging horizon entirely (`RHP_CHARGE_HORIZON_MONTHS`,
`generation_horizon`) in favour of one rule, `charges_due()`.

### P4-Q1 — Ending freezes the terms and stops new obligations

**Decided:** ending freezes the **terms** and stops **new obligations from the schedule**. Money already
charged stays and stays correctable.
*Owner:* "We need a system of ended, rather than simply 'Open / Closed'. If an administrator ends the
tenancy there needs to be a citable reason."

Occupancy and money now have separate state machines: a tenancy is draft, active, or ended, while its
financial account is open or settled. Ending carries a reason code and note. The split and settlement rules
are [ADR-020](ADR-020-tenancy-lifecycle.md).

*Alternative rejected:* ended means read-only, including money. A tenancy ended with the wrong final figure
could then never be corrected, contradicting ADR-008.

### P4-Q2 — A close-out, offered at the moment of ending

**Decided:** as recommended. Ending reviews what the money will do: every month the tenancy will not use is
cancelled by a **dated adjustment** naming the reason. Cancel all by default; keep one the tenant still owes.
Append-only, reversible, and the tenant's statement shows the charge and its correction.
*Owner:* "We'll use your recommendation."

*Alternatives rejected:* leave the charges and let the arrears sit (produces a debt for a month nobody
occupied); delete them (the ledger's promise is that history is never erased).

### P4-Q3 — Recurring charges stop; remedial charges need just cause

**Decided:** *recurring* charges (rent, NNN, a responsibility share) stop when the tenancy ends. A
**post-tenancy charge** — damage, cleaning, an unpaid balance, an NSF fee, an early termination fee — may be
raised after the end, but must carry its just cause: a **reason code**, the **lease clause** it rests on, and
its **supporting evidence**.
*Owner:* "Yes — design it so the tenant can still be charged after the tenancy ends… Separate charge types by
origin… Require justification and documentation."

**The evidence waits for Phase 6.** The owner's next decision was to *wait for Phase 6 so a charge always has
its evidence*, so this branch refuses **all** new charges on an ended tenancy and marks the single line the
post-tenancy mechanism will relax (`refuse_if_not_chargeable`). Reopening a settled financial account does
not restore occupancy or permit rent; evidence-backed post-tenancy charges remain unavailable until E6.

Money in and corrections remain allowed on an ended/open account. A settled account locks every mutation
until a manager reopens the financial account with a reason.

### P4-Q4 — The rule lives in the services

**Decided:** as recommended — one predicate, `Lease.can_be_charged`, consulted by `generate_charges` and
`create_charge`, so the ledger screen, the lease screen and `manage.py generate_rent_charges` all obey it.
*Owner:* "Unsure, maybe answered by my related answers. Otherwise, we'll go with your recommendation."

### P4-Q5 — Keep the tenancy in Rent & Payments, and keep the old ledger private

**Decided:** an ended tenancy stays listed and reachable, marked with its financial-account status and final
position. **A new tenant on the same unit must never see the previous tenancy's ledger.**
*Owner:* "Yes, keep the tenancy. A new tenant should not see the previous tenants ledger though. But the
admin should see it if they so wish. Maybe all units have a ledger history that can be expanded to show the
details."

The last sentence is a new idea — a unit-level ledger history — recorded as **P4-E7** and taken up with the
reporting work.

### P4-Q6 — Move-out settlement is its own extension

**Decided:** `P4-E5` — the deposit, deductions with reasons, a final statement, a forwarding address — taken
up after this guard lands. *Owner:* "P4-E5 is good."

## Consequences

**Good.** A charge now belongs to the period of the tenancy's life it was raised for. The phantom-obligation
class of defect is structurally impossible: one predicate, consulted by every path that creates an obligation.
A tenancy that ends leaves a citable reason and a closed-out ledger, and its money can still be paid and
corrected. Nothing was added to the ledger's arithmetic, and no table was added.

**Accepted.** A record edit is now a publish (`docs-sync`, `plane-sync`, `verify`). A settled *financial
account* is a condition every money path must consider — occupancy and money are separate lifecycles
(ADR-020), so the account can be closed while the tenancy's history stays exactly where it is — and the
tests say so. Until P4-E6, billing a debt found after move-out means reopening the **account**, not the
tenancy: occupancy stays ended, and rent never restarts.

**Deferred, each with its own register row:** P4-E5 (move-out settlement), P4-E6 (post-tenancy charges with
evidence, blocked by Phase 6), P4-E7 (a unit's ledger history), P3-E2 (a tenant's request for early
termination and its clauses).

**E3 (concessions) is bigger than this record assumed.** The owner's example: in 2022 several tenants were
given six months, two quarters were conceded, and a fifth half-year was tacked on — "complicated to do
practically without a mechanism governing it". So a concession is *forgiveness* (an adjustment, which this
work makes available) **and** a deferral plan **and** a term extension. It keeps its own design, informed by
that example, and is no longer a candidate to fold in here.

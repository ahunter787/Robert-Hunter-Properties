# Phase 3 — Lease management

**Status:** Complete
**Milestone:** 2 — The real portfolio is modeled: properties, units, tenants, leases
**Specification:** `docs/harness/master-spec.md`, `PHASE 3 — LEASE MANAGEMENT` (amended 2026-10-14: the
occupancy/account split, the citable end reason, `ended_on` against the signed term, settlement, and
financial-account reopening)

## Scope as specified

Make the lease the central connection between a tenant and a property: creation, editing, a
draft/active/ended state, one or more tenants per lease, rent, deposit, the rent due day, the term, and the
signed lease attached. The tenant's own page shows those facts. Electronic signatures are explicitly out
of scope. Acceptance includes that expired leases remain historically available and that an active lease
is easy to distinguish.

## What exists today

- **Models** (`apps/leases/models.py`): `Lease` (unit, term, monthly rent, template, step-up rule, billing
  cutover, deposit, rent due day, status, **`ended_on`**, **`end_reason`** and **`end_reason_note`**, lease
  file, notes), `LeaseTenant` (with exactly one primary contact per lease), `RentPeriod` and `NnnRate`
  (from P3-E1), and `LeaseOpeningRecord` (E10/ADR-027; the E4 `LeaseOnboarding` record is retired by ADR-028).
- **Two lifecycles** (P4-E5, [ADR-020](../decisions/ADR-020-tenancy-lifecycle.md); future state M2a,
  [ADR-029](../decisions/ADR-029-lease-future-and-people.md)): occupancy is `DRAFT`, `FUTURE`, `ACTIVE`, or
  `ENDED`; the financial account is `OPEN` or `SETTLED`. Ending records a citable reason and
  the day occupancy stopped while preserving the signed term. Managers may settle a zero-balance ended
  account or reopen that account with a reason; reopening never restores occupancy.
- **Database rules:** `one_active_lease_per_unit` (a `UniqueConstraint`, not a form rule), the term cannot
  end before it starts, and `PROTECT` on the unit and tenant links.
- **Rules in code:** a lease is drafted, activated and ended by a person — never by the calendar; the unit
  is frozen once the lease leaves draft; an ended lease (`Lease.is_editable` false) keeps its terms as
  history and refuses term edits (`_refuse_ended_terms`).
- **Staff screens** (`/manage/leases/`): list with search, detail, create, edit, activate, **end (a review
  of what the money will do)**, **settle**, **reopen**, delete a draft, the lease document, the rent schedule,
  the NNN rate, and the starting-account / existing-history workflow (E10, ADR-027; the old P4-E4
  onboarding screen was retired by ADR-028).
- **Tenant page** (`/lease/`): unit, term, rent, deposit, co-tenants, the lease document, and — since
  Phase 4/5 — the balance and activity. The document URL carries no id, so it cannot be pointed at
  somebody else's file.

## Decisions that govern it

| Record | What it settled |
| --- | --- |
| [ADR-007](../decisions/ADR-007-lease-modeling.md) | One active lease per unit as a database constraint; explicit status; the unit frozen after draft; co-tenants with one primary contact; one lease file; one definition of occupancy |
| [ADR-013](../decisions/ADR-013-lease-templates.md) | P3-E1: how a month's rent is decided — a stored schedule, not a rule re-derived each time; amended by E4 so NNN is a term of the lease rather than a template |
| [ADR-016](../decisions/ADR-016-retroactive-onboarding.md) | P4-E4: the billing cutover and the stated-amount template — this phase's terms, used by the ledger; the onboarding mechanism is retired by ADR-028, the terms remain |
| [ADR-020](../decisions/ADR-020-tenancy-lifecycle.md) | P4-E5: separate occupancy and account states, the citable end reason, settlement prerequisites, and financial-account reopening |
| [ADR-017](../decisions/ADR-017-charge-lifecycle.md) | P4-E5: what each state may do with money — the rule this phase's states exist to carry |

## Extensions filed under this phase

**P3-E1 — Lease templates** (register id `E1`, **In `main`**, [ADR-013](../decisions/ADR-013-lease-templates.md)).
The specification models one monthly rent for a term, which no real RHP lease obeys. The extension adds
`Lease.template` — Fixed, Step up, Triple net — a stored `RentPeriod` per change, and `Lease.rent_for()`
as the single place every caller asks what a month costs. Activating a stepped lease works the whole term
out once and stores it, so a later rounding or rule change cannot rewrite a month already billed.

Reached into this phase from other extensions: **P4-E4** added `LeaseTemplate.STATED` ("the lease states
the amounts"), `Lease.billing_start_date`, and the rule that a period entered by hand is never removed by
regenerating. Its `LeaseOnboarding` record is retired by [ADR-028](../decisions/ADR-028-one-kernel.md);
the starting-account workflow (ADR-027) is what places a tenancy now. **P4-E1's sibling NNN rule** —
`Lease.carries_nnn` — is also a lease term, recorded here and charged by Phase 4.

## Acceptance criteria and evidence

- [x] A unit cannot be rented twice — the constraint is in the database
- [x] A lease is ended by a person, never by the calendar; ended leases are read-only history
- [x] Co-tenants are supported with exactly one primary contact (a per-lease `UniqueConstraint`)
- [x] A tenant sees their own lease and document, and nothing else — no id in the document URL
- [x] Documents are never served by the proxy; both document views check permissions first
- [x] Staff can create a lease and attach tenants; an active lease is distinguishable in every list

`tests/leases/` covers the model rules, the desk screens, the tenant page, authorization route by route,
and (from P3-E1) the schedule arithmetic.

## Deliberately not here

Balances, charges and payments (Phase 4); the full tenant dashboard (Phase 5); the documents area
(Phase 6); electronic signatures (not in the specification); a formal amendment flow for the terms of a
lease that has already been charged.

## Known gaps and defects

- **Financial reopening** — *fixed in P4-E5*: a manager can reopen a settled account with a reason and an
  audit event. The tenancy remains ended, and the close-out and earlier settlement stay visible.
- **No renewal action.** A renewal is typed from scratch, which will become the most common repetitive job
  on the desk. Tracked in the phase guide since Phase 3.
- **No month-to-month state.** The term requires a start and an end date.
- **A lease that runs past its end date stays `ACTIVE`.** `is_current` goes false, so the screens read
  correctly, but the status word says active and the ledger overview lists it as a live tenancy. This is
  P3-Q1 below, and it is half of the tenancy-and-money problem in
  [the case study](../workflows/tenancy-and-money.md).
- **A signed tenancy that has not started now reads `FUTURE`** (M2a, [ADR-029](../decisions/ADR-029-lease-future-and-people.md)).
  Activating a future-dated lease schedules it; it posts nothing and is not occupancy, and a due
  scheduled tenancy starts automatically (the management command and the screens self-heal). A renewal may
  therefore be signed while the current tenancy runs. The person/login split (M2b) is still pending.
- **The E4 onboarding mechanism is retired by ADR-028.** Starting accounts are the E10/ADR-027 workflow;
  any old E4 placement decision is preserved as an audit event, not as a live record.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P3-Q1 | Does a lease expire by date, or only when a person ends it? | Keep "a person ends a lease, never the calendar" (ADR-007) and make the screens say loudly when the term has passed, with an "end this lease" action beside it. | *(awaiting)* — a lease whose term has passed still reads `ACTIVE`, and nothing in the ledger raises charges beyond the term, so this is presentation rather than money |
| P3-Q2 | Should an account closed by mistake be reopenable, and by whom? | Yes — a manager act, audited, requiring a reason, without changing occupancy. | **Yes, built** in P4-E5: managers can reopen the financial account; the tenancy remains ended and prior settlement and close-out events stay visible. |
| P3-Q3 | Do you want a "renew this lease" action that copies the term and tenants forward? | Yes, and as its own small piece of work rather than folded into another phase. | *(awaiting)* |
| P3-Q4 | Should a month-to-month tenancy be representable (no end date)? | Only if RHP takes them on; it touches the lease term and every report. | *(awaiting)* |

## How to verify it

`make test` (with `tests/leases/`), then: create a draft lease, activate it, open `/lease/` as the tenant,
and end it — the page keeps the history and `_refuse_ended_terms` refuses term edits while the money stays
correctable on the ledger.

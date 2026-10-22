# Kernel scope — the two spines and the boundary to the GL

**Status:** Approved direction, October 21, 2026 — [ADR-028](../decisions/ADR-028-one-kernel.md) D1, D6,
D9. The event vocabulary is [`events.md`](events.md); the accounting direction is
[ADR-026](../decisions/ADR-026-property-accounting.md) and the [blueprint](../design/property-accounting.md).

## Why two spines

RHP records two different stories about the same property, and they must never be merged into one
number:

- the **occupancy spine** — who occupies which unit, on what term, for what rent (leases, tenants,
  move-in/move-out);
- the **money spine** — what a tenancy owes and what it paid (tenant AR), and what the property earned
  and spent (the GL).

Industry products keep them separate for a reason: occupancy can end while money is still owed, and a
property can spend money that no tenancy will ever be charged for. RHP already separated the two
lifecycles ([ADR-020](../decisions/ADR-020-tenancy-lifecycle.md): occupancy `DRAFT/FUTURE/ACTIVE/ENDED`, account
`OPEN/SETTLED`); this document states how the money side reaches the GL.

## Where each piece lives

| Piece | Home | Role |
| --- | --- | --- |
| Occupancy: leases, terms, tenants | `apps/leases/` | The agreement and who is on it. No stored balance. |
| Tenant AR: charges, payments, applications, deposit register, statements | `apps/ledger/` | The tenant sub-ledger and the desk. The operational source of truth for tenant money. |
| Property accounting: chart, journals, banks, AP, reconciliation, reports | `apps/accounting/` (B1–B5) | The GL. Posts from the sub-ledger, never re-derives it. |
| Cross-cutting vocabulary and boundary | `docs/kernel/` | This document and `events.md`. |

Dependency direction that must survive any refactor: **`accounting` may depend on `ledger`; `ledger` may
depend on `leases`; `leases` must not depend on `ledger`'s internals.** Today `apps/leases` imports
`apps/ledger` for money actions and `apps/ledger` imports `apps/leases` for the tenancy; the deletion work
keeps the service-level calls but does not add module-level cycles. The eventual direction is stated here
so a later refactor has a target.

## The property spine

A property-level fact reaches the tenant ledger through **allocation**, never by copying the bill:

```
vendor bill (property) ──► cost allocated to units ──► unit's share
                                                        │
                       ┌────────────────────────────────┴───────────────┐
                       ▼                                                ▼
              tenant AR (responsibility charge)                 property GL (AP + expense)
```

- A bill names the property; B1/B2 require it. A bill without a property is a defect.
- Allocation splits a property cost into unit shares. E2's responsibility cycle already produces the
  tenant-facing monthly share; the GL slice records the AP and expense side. The **same** allocation
  feeds both, so a tenant's recovery and the property's books cannot disagree.
- A repair cost is a cost (property expense) and a recharge is a separate, reviewed obligation (tenant
  AR). Neither proves the other: a recorded cost is not a payment, and a recharge is not a repair.
- Every GL journal names a property and (where the chart distinguishes them) a unit/building dimension,
  so the three-way reconciliation closes against the property ledgers.

## Deposits

A security deposit is the tenant's money held by RHP until move-out. It is:

- **not AR** — it does not reduce what the tenant owes;
- **not a credit** — it is not available to pay rent and must never be applied automatically;
- **a liability** — the deposit register's derived balance (`received − returned − withheld`) is what RHP
  holds. An explicit `NOT_COLLECTED` entry says no money was held; it is never inferred from the lease
  term.

The sub-ledger register lands now (M1); the GL posts held-deposit liability, refunds and retained amounts
in B2, against a security-deposit bank account where state law requires one (a bank-account *kind*, not a
trust module — RHP owns its properties, so there are no third-party client funds; ADR-026 boundary).

Settlement of a tenancy's financial account requires the held balance to be zero and an outcome to be
recorded. Applying withheld money to an outstanding AR balance is an E5/B2 refinement; until then AR is
corrected with the existing adjustment path first, and the screens state the limitation.

## Credits and prepayments

- An **opening credit** is money held from before RHP's records began, stated by a manager
  (`LeaseOpeningRecord` CREDIT → a linked `OPENING` decrease). It is a credit liability, never a receipt.
- A **prepayment** is advance rent received inside RHP's records; it is a receipt held as a liability
  until the month it covers is charged.
- Both are **unapplied funds**: they become AR reductions only through a recorded `FundsApplication`
  (manager-reviewed), and that application is reversible. They are never income on receipt.
- A **withholding from a deposit** is not the same thing as a credit; it releases a deposit liability,
  not a credit.

## Receipts, deposits to the bank, and reconciliation

Tenant money moves in two steps that the system must not conflate:

1. **Receipt** — the office records that the tenant paid (`Payment` `CLEARED`). AR falls; an
   undeposited-funds clearing balance rises.
2. **Bank settlement** — the receipt is included in a bank deposit and later matched to a bank-statement
   line (B3). Only here does the bank balance move.

A pending payment posts nothing. A void posts nothing. A reversal reverses the receipt. Three-way
reconciliation (statement = cleared = adjusted from the ledgers) closes the loop; unexplained differences
stay visible and block approval — the software never invents a payment to erase a difference.

## The two "gates" are different questions

The deletion work retires E4 and leaves one placement predicate. They are documented together so they
cannot drift:

| Question | Predicate | Used by |
| --- | --- | --- |
| *Must this tenancy be placed before it can be charged?* | `Lease.needs_starting_account` — a currently active tenancy from before RHP's financial start with no starting account | `ledger.services.charge_refusal`; the lease and ledger screens; the management command |
| *May a starting account be recorded for this tenancy now?* | `leases.cutover.eligible` — active, open account, not already placed, no activity, cutover inside the term | the starting-account view/service only |

A tenancy can need placement while not yet being eligible (for example a draft, or an ended one): the
first predicate is what makes the desk say why charging is refused; the second is what protects the act.

## The GL boundary

The GL is a **posting target**, not a second calculation:

- It posts from the events in [`events.md`](events.md), each linked to its source row and property.
- It checks the **AR control** against the sub-ledger (sum of tenant balances) and the **AP control**
  against recorded costs less disbursements; a difference is reported, never plugged.
- It never re-derives a tenant balance from bank data, never re-allocates a payment, and never edits a
  posted journal: corrections are reversing entries, as everywhere in RHP.
- Cash basis is a report view over the same entries; it is not a second set of journals.

## Upcoming tenancies and people (ADR-029)

A signed tenancy whose start date is ahead is `FUTURE`: scheduled, not occupancy, and **not an
obligation**. It posts no rent, NNN or recovery, shows no arrears, and cannot be ended or settled; its
rent schedule is known up front, and the first charges are raised when it starts automatically. A
security deposit may be received and held before move-in — it stays deposit money, never rent. The party
model is now a `contacts.Person` on a lease membership (role: tenant, adult occupant, guarantor or
authorized contact), with the portal login an optional link on that membership (ADR-030; PropertyBoss /
DoorLoop pattern). A person with no login has no portal access.

## Known limitations (recorded, not hidden)

- Recurring charges are posted on demand by a command today; system scheduling is Phase 12 work. The rule
  (raise on the due date, never ahead) already matches industry practice.
- `Payment.CLEARED` means office-confirmed receipt, not bank settlement; the two-stage posting is B1/B3.
- Deposit withheld-to-AR application is E5/B2 (above).
- The party model is settled (ADR-030); merging duplicate people and enforcing guarantor liability are
  open items, not hidden behaviour.
- Trust/escrow modules, management fees and third-party owners are out of scope (ADR-026).

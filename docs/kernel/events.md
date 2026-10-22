# Kernel event vocabulary and posting matrix

**Status:** Approved direction, October 21, 2026 — [ADR-028](../decisions/ADR-028-one-kernel.md) D9.
This is the **one** matrix the tenant sub-ledger and the general ledger post from. The GL is built in
slices B1–B5 ([blueprint](../design/property-accounting.md)); rows marked *B1*/*B2*/*B3* are the slice
that implements the GL side. The tenant AR column is the sub-ledger fact that exists today (or is added
by the named change). Nothing here re-derives the sub-ledger: the GL posts from these events and is
checked against it (AR control).

Two rules for every row:

- **One posting per explicit source transition.** The idempotency key is `model:pk:transition`
  (`charge:42:created`, `payment:7:cleared`, `deposit:3:withheld`, `application:9:released`). A
  replayed confirmation, a double-clicked button and a retried command create nothing.
- **Balanced and sourced.** A GL journal names its source event, its property, its accounts and its
  amount; it is immutable, and a correction is a reversing entry. No unexplained equity plug is ever
  approved to force a control to agree.

The classification decisions below are settled before B1.

## The five classification questions

1. **Expected vs received.** An expected payment (`PENDING`) is a memo on the desk: it posts **nothing**
   to AR and nothing to the GL. Only a receipt moves money. Cancelling an expected payment
   (`PENDING → VOID`) similarly posts nothing.
2. **Receipt vs bank settlement.** A recorded receipt (`CLEARED`, office-confirmed) is **not** evidence
   that money reached a bank account. Receipt posts against tenant AR and an **undeposited-funds**
   clearing account (B1/B3); bank settlement posts at the bank deposit/reconciliation step (B3). A
   receipt may therefore be real while unsent to the bank, and clearing a bank statement never edits the
   receipt.
3. **Opening credit vs prepayment.** Both are liabilities, but they are different rows: an **opening
   credit** is manager-stated money held before RHP's records began (a linked opening credit, never a
   receipt and never AR); a **prepayment** is advance rent the tenant paid inside RHP's records. They
   post to separate control accounts (B1 classification) and are applied to bills only through a
   recorded application.
4. **Future-charge recognition.** No future rent is recognised. A charge exists when it is raised on its
   due date (P4-Q7); "coming due" is a projection from the lease, not a ledger row and not an accrual.
   The GL is accrual-basis for expenses, not for future rent.
5. **Per-event idempotency.** Keyed on the explicit source transition, stored with a uniqueness
   constraint on the GL source key. Re-running a command, replaying a signed review or retrying a bank
   import must be a no-op, not a second posting.

## Event matrix

`AR` = tenant sub-ledger effect; `GL` = journal the accounting kernel posts (slice in parentheses).
`—` means explicitly nothing. "Audit" means an append-only `AuditEvent` in the same transaction.

| event | actor | trigger | source document | idempotency key | posts (tenancy AR) | posts (GL) | notifies | audits | forbids | reversal path |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **lease signed** (draft approved) | manager | activate a draft | lease row | `lease:<id>:activated` | none (no money yet) | none | tenant welcome | `LEASE_ACTIVATED` | charging a draft | n/a — a draft cannot be ended with money |
| **occupancy starts** (`FUTURE → ACTIVE`, M2) | system, idempotent | start date reached, or manager act | lease row | `lease:<id>:started` | none | none | tenant | `LEASE_STARTED` | charging a future lease | n/a |
| **rent due** | — (clock) | due date arrives | lease term (`RentPeriod`/`monthly_rent`) | — (not an event; it is the trigger) | none until raised | none | reminder later (Phase 8) | none | raising before due date | n/a |
| **rent charged** | system/manager | generation on the due date | lease term and cutover | `charge:<id>:created` | `Charge` INCREASE (RENT) | Dr Tenant AR / Cr Rent income (B1) | none | `CHARGE_CREATED` | charging past the term, a draft, an ended tenancy, before the starting account | adjustment (decrease) naming the charge |
| **NNN / responsibility charged** | same | generation | lease term, responsibility cycle | `charge:<id>:created` | `Charge` INCREASE (NNN/RESPONSIBILITY) | Dr Tenant AR / Cr recovery income (B1) | none | `CHARGE_CREATED` | as above | adjustment naming the charge |
| **opening balance (debt / credit / zero)** | manager, reviewed | starting-account confirmation | `LeaseOpeningRecord`, optional evidence | `opening:<id>:confirmed` | debt: `OPENING` INCREASE; credit: `OPENING` DECREASE; zero: no row | debt: Dr Tenant AR / Cr Opening equity (B1); credit: Dr Opening equity / Cr Tenant credit liability (B1); zero: none | none | `LEASE_ONBOARDED` + `CHARGE_CREATED` when a charge exists | recording it twice; inferring history | linked correction entry (adjustment) |
| **payment expected** | manager | record a pending payment | receipt note | `payment:<id>:pending` | `Payment` PENDING — moves nothing | none | none | `PAYMENT_RECORDED` | treating pending money as received | void (no posting) |
| **payment received** | manager | record a cleared payment | receipt / remittance | `payment:<id>:recorded` | `Payment` CLEARED; applications to oldest due obligations | Dr Undeposited funds / Cr Tenant AR (B1); application rows are memo to AR | receipt acknowledgement (Phase 11 later) | `PAYMENT_RECORDED` | dating a new receipt before the financial start; recording a settled account | reversal (new payment) |
| **payment cleared from pending** | manager | confirm expected money arrived | bank/desk confirmation | `payment:<id>:cleared` | `PENDING → CLEARED`; allocation runs | Dr Undeposited funds / Cr Tenant AR (B1) | none | `PAYMENT_CLEARED` | clearing twice; clearing a voided payment | reversal |
| **payment voided** | manager | expected money never arrived | — | `payment:<id>:voided` | `PENDING → VOID`; no AR movement | none (nothing was posted) | none | `PAYMENT_VOIDED` | voiding a cleared payment (reverse instead) | n/a |
| **payment reversed** | manager | mistake/unwound receipt | reason | `payment:<id>:reversed` | reversal `Payment`; applications released | Dr Tenant AR / Cr Undeposited funds (B1) | none | `PAYMENT_REVERSED` | reversing twice (OneToOne); editing the original | reversal of the reversal is not allowed; record a new receipt |
| **credit held** | manager | opening credit recorded / overpayment | `LeaseOpeningRecord` or receipt | `charge:<id>:created` / `payment:<id>:recorded` | credit source available (no AR movement until applied) | Cr Tenant credit liability (B1) | none | existing event | treating credit as AR reduction automatically | no release needed |
| **credit applied** | manager, reviewed | apply held credit to a bill | signed review | `application:<id>:confirmed` | `FundsApplication` source → target | Dr Tenant credit liability / Cr Tenant AR (B1) | tenant sees "credit applied" | `CHARGE_ADJUSTED` (workflow `funds_application`) | applying unavailable credit; applying to another tenancy | release (exact reversal) |
| **credit released** | manager, reviewed | undo an application | signed review | `application:<id>:released` | releasing `FundsApplication` | Dr Tenant AR / Cr Tenant credit liability (B1) | none | `CHARGE_ADJUSTED` | releasing twice | re-apply |
| **bill received (property)** | manager | record a property bill | vendor bill document | `bill:<id>:recorded` | none | Dr Operating expense / Cr Accounts payable (B2) | none | new `BILL_RECORDED` (B2) | posting a bill without a property | reversing journal / bill credit (B2) |
| **bill allocated to units** | manager, reviewed | allocate a bill's cost to units | allocation review | `bill:<id>:allocated` | unit shares become property-accounting facts (E2 responsibility cycle) | Dr Unit/property cost / Cr Allocation clearing (B2) | tenants see their month | new (B2) | changing a saved allocation without a review | re-allocation version, original retained |
| **repair cost recorded** | maintenance | record a repair expense | invoice/receipt `Document` | `cost:<id>:recorded` | none | Dr Repair expense / Cr Accounts payable (B2) | none | `MAINTENANCE_COST` | inferring tenant liability from a cost | correcting cost entry (append-only) |
| **repair recharged** | manager, reviewed | charge a tenancy for a repair | signed recharge review | `recharge:<id>:confirmed` | `Charge` INCREASE (MANUAL) | Dr Tenant AR / Cr Repair recovery (B1) | tenant | `MAINTENANCE_RECHARGE` + `CHARGE_CREATED` | recharging without reviewed evidence | adjustment naming the charge |
| **deposit received** | manager | record money held (move-in/attestation) | receipt/reference, optional evidence | `deposit:<id>:received` | `DepositEntry` RECEIVED — held liability, **not AR** | Dr Cash/Undeposited funds / Cr Security deposit liability (B2) | tenant sees held deposit | `DEPOSIT_CHANGED` | inferring held funds from the lease term; editing/deleting an entry | new entry (no edits) |
| **deposit returned** | manager, ended tenancy | refund at move-out | disposition review + document | `deposit:<id>:returned` | `DepositEntry` RETURNED | Dr Security deposit liability / Cr Cash (B2) | tenant | `DEPOSIT_CHANGED` | returning more than held | new entry only; correction via another entry after reopen |
| **deposit withheld** | manager, ended tenancy | itemised deduction at move-out | disposition review + itemised reasons/documents | `deposit:<id>:withheld` | `DepositEntry` WITHHELD | Dr Security deposit liability / Cr income or AR recovery (B2 classification) | tenant | `DEPOSIT_CHANGED` | withholding more than held; withholding without a reason | new entry only |
| **deposit not collected** | manager, ended tenancy | explicit statement that none was held | disposition review | `deposit:<id>:not-collected` | `DepositEntry` NOT_COLLECTED (0) | none | none | `DEPOSIT_CHANGED` | inferring "not collected" silently | new entry (n/a) |
| **retained deposit applied to a bill** | manager, ended tenancy | apply part of a WITHHELD deposit against an unpaid obligation | signed credit review whose source is the deposit | `application:<id>:applied` | `FundsApplication` with `source_deposit`, target charge, `is_credit`; **no Payment** | Dr Security deposit liability / Cr Tenant AR for the applied amount (B2); any retained portion not applied becomes income at application/forfeiture (B2) | tenant sees it on the final statement / application history | `CHARGE_ADJUSTED` (review audit) | recording it as a new receipt; applying more than retained or more than is owed; applying on a settled account | undo creates a release row; the deposit entry is never edited |
| **move-out statement issued** | manager, ended tenancy | issue the final accounting to the tenant | statement screen | `audit:<id>:statement-issued` (each issue is a new act) | append-only audit snapshot (totals, deposit lines, forwarding address, outcome); no new balance | memo/report only; AR control is unchanged | tenant portal final statement | `MOVE_OUT_STATEMENT_ISSUED` | treating the snapshot as the ledger; editing an issued statement | issue again (new event, history retained) |
| **forwarding address recorded** | manager | record where the statement/refund goes | end review or statement screen | `lease:<id>:forwarding-address` | `Lease.forwarding_address`; audit | none | none | `MOVE_OUT_DETAILS_UPDATED` | inferring an address; mailing without one | supersede with another audited value |
| **move-out** | manager | end the tenancy | end review (reason code + note) | `lease:<id>:ended` | close-out adjustments cancel unused months; deposit becomes disposable | reversing/close-out journals (B1/B2) | tenant | `LEASE_ENDED` | charging new recurring rent after the end | reopen account (occupancy stays ended) |
| **settlement** | manager | settle the financial account | settlement act | `lease:<id>:settled` | locks AR; requires balance 0, credit 0, no pending, deposit held 0 and outcome recorded | control check: AR = 0 (B1) | none | `LEASE_SETTLED` | settling with anything outstanding or undisposed | reopen account (reason, audited) |
| **account reopened** | manager | reopen a settled account | reason | `lease:<id>:reopened` | unlocks AR; occupancy stays ended | none | none | `LEASE_REOPENED` | restoring occupancy/rent | settle again |
| **write-off** | manager, reviewed | forgive an uncollectable balance | reason, optional evidence | `adjustment:<id>:created` | `Charge` ADJUSTMENT DECREASE naming the charge | Dr Bad debt / Cr Tenant AR (B1) | none | `CHARGE_ADJUSTED` | deleting a charge instead | new adjustment to reinstate |

Notes:

- **Tenant credit is never income and never negative AR.** It is a liability until applied or returned;
  the held-credit refinement ([`design/held-credit-repayments.md`](../design/held-credit-repayments.md))
  already implements that in the sub-ledger.
- **Deposit money is outside AR.** Applying a withheld amount to an outstanding AR balance is an E5/B2
  refinement (a new funds source or a GL allocation); until then the desk corrects AR with the existing
  adjustment path first, and the kernel scope records the limitation.
- **Property is mandatory on every GL journal** (B1). A journal that cannot name a property is a defect,
  not a default.

## Idempotency and replay

| transition | key | stored on |
| --- | --- | --- |
| charge created | `charge:<id>:created` | charge row (creation is the only write; `get_or_create` for rent) |
| payment transitions | `payment:<id>:<pending|recorded|cleared|voided|reversed>` | payment row's lifecycle is one-way; reversal is `OneToOne` |
| opening record | `opening:<id>:confirmed` | `LeaseOpeningRecord.review_key` (unique) |
| application/release | `application:<id>:<confirmed|released>` | `FundsApplication` row; `reverses` is `OneToOne` |
| deposit entry | `deposit:<id>:<received|returned|withheld|not-collected>` | `DepositEntry` row |
| deposit application | `application:<id>:applied` | `FundsApplication` row with `source_deposit` |
| statement issue | each issue is a new explicit act (not deduplicated); the audit event id is the identity | `audit_auditevent` snapshot |
| GL journal | `<source model>:<pk>:<transition>` | journal source key, unique (B1) |

A replayed confirmation returns the existing row rather than writing a second one; a retried management
command is a no-op; a bank import that matches an already-reconciled line is refused, not re-posted.

## What the GL must never do

- Recompute the sub-ledger balance for its AR control: it posts from these events and reconciles.
- Force a control to agree with an unexplained equity plug; differences stay visible and block approval.
- Post a receipt as bank settlement, an opening credit as a receipt, or a deposit term as held money.
- Post a future rent obligation before its due date.

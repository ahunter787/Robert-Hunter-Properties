# ADR-031 — Move-out settlement: apply the deposit, state the whole account

- **Status:** Implemented, 2026-10-22 (E5 remainder; builds on ADR-008, ADR-017, ADR-028 D5, ADR-030).
- **Date:** 2026-10-22
- **Related:** [ADR-008](ADR-008-rent-ledger.md) (append-only sub-ledger), [ADR-017](ADR-017-charge-lifecycle.md)
  (what ending does to money), [ADR-028](ADR-028-one-kernel.md) D5 (held-deposit register), [ADR-029](ADR-029-lease-future-and-people.md)
  (lifecycle), [ADR-030](ADR-030-people-and-portal-logins.md) (people), [ADR-026](ADR-026-property-accounting.md)
  (GL, B1–B5), kernel vocabulary in [`docs/kernel/events.md`](../kernel/events.md) and
  [`docs/kernel/scope.md`](../kernel/scope.md).
- **Evidence (public, product and accounting practice):** APM Help's Buildium deposit guide; Elite Recovery
  Group's resident-ledger glossary; Blue Cloud CPA's security-deposit accounting guide. The study at
  `../tenantcloud/findings/` supplies the product observation that deposits are a separate ledger. None is
  copied into RHP; they establish method only.

## Context

ADR-028 D5 gave RHP a held-deposit register with an explicit move-out outcome, which unblocked
settlement. It deliberately stopped there: a retained deposit was money released from the liability, but
there was no way to apply it against what a tenant still owes, no final statement, and nowhere to send
either. E5 is the remainder: apply the deposit against final charges, refund the rest, and issue one
itemised accounting to the tenant, with a forwarding address.

The kernel rule that decides the shape: **a deposit is the tenant's money held as a liability, not rent
received.** Applying it is a reclassification against a bill, not a second receipt. RHP must not create a
new `Payment` (that would double-count cash), and it must not silently drop the retained money (that
would lose the liability release).

## Evidence — how the industry does move-out

| # | Practice | Source | What it shows |
| --- | --- | --- | --- |
| 1 | A deposit is a liability; three lawful outcomes, itemised | [APM Help: security-deposit accounting in Buildium](https://www.apmhelp.com/blog/buildium/security-deposit-accounting-in-buildium-setup-recording-and-the-escrow-reconciliation) | Deposits sit in a separate Deposits area and are reported as a liability, not as rental income. Move-out has exactly three outcomes: full refund, itemised deductions with a partial refund, or full withholding — each with a documented reason. Most states require a written itemisation within a set window, and the article treats the state deadline as a legal parameter, not a product preference. |
| 2 | Two ledgers: rent ledger and deposit ledger; applying moves classification, not cash | [Elite Recovery Group: resident ledger terms](https://ergroupllc.com/blog/resident-ledger-terms-explained) | A resident account has two jobs: the rent/resident ledger (amounts owed) and the security-deposit ledger (money held for the resident, a liability). A deposit transfer or "payment moved to deposit ledger" reclassifies money already received; applying a deposit to charges changes accounting classification without moving cash on its own. The memo should name the payment, amount, reason and both balances. |
| 3 | Deposit accounting lifecycle: receipt → application → return | [Blue Cloud CPA: is a security deposit a liability?](https://bluecloudcpa.com/guides/property-management-security-deposits-accounting-tax) | At receipt: deposit liability, no income. On lawful application against unpaid rent or damage: reduce the liability and recognise income (and the offsetting repair expense separately). On refund: reduce liability and cash, no income effect. Deductions must be supported by actual itemised costs, not estimates; state statutes set the return deadline (commonly 14–30 days) and documentation standards, and those vary by state. |

What the evidence does not settle for RHP: the applicable state's return deadline and documentation rules,
because that depends on the owner's jurisdiction — a business fact, not a method choice. RHP therefore
does not hard-code a deadline and records that as an open item.

## Decision

### D1 — Applying a retained deposit is a reviewed credit, never a new receipt

1. `FundsApplication` gains an optional `source_deposit` alongside `source_payment` and `source_charge`.
   The database allows exactly one source. A deposit-sourced application is `is_credit=True` and settles
   an obligation exactly like a held credit; it does **not** create or imply a `Payment`.
2. The existing reviewed credit action (`ledger:credit-apply`) lists a retained (`WITHHELD`) deposit as a
   source with its remaining available amount, applies the manager's chosen amount to the chosen bill
   oldest-first, records the signed review, and can be undone through the same review. The ledger reads
   it as a reduction of the balance, and the tenant's spendable "credit" figure excludes it (it is the
   tenant's held money being applied, not a cash credit available to spend).
3. A retention first releases the held liability (`DepositEntry` `WITHHELD`, with a reason and optional
   document); applying part of it to a bill then moves that part against the charge. Any retained amount
   not applied stays as a released liability (income recognition belongs to the GL slices B2/B3); RHP
   does not invent a charge for damage here — that is E6.
4. Everything is append-only: the application is a new row, an undo is a release row, and the deposit
   entry itself is never edited. The same tenant-scoping and manager-only authorization as every money
   action applies.

### D2 — One final statement, derived and issued

1. The **move-out statement** is derived from the same ledger (`build_ledger`) and deposit register:
   charged over the tenancy, paid, deposit received/applied/returned/withheld/not collected, what is
   still held, and the resulting outcome — tenant owes RHP, RHP owes the tenant, or neither.
2. It is not a second balance and stores no totals of its own. A manager screen shows the live statement
   with links to the deposit register, the reviewed credit action, and settlement.
3. **Issuing** the statement records an append-only audit event (`MOVE_OUT_STATEMENT_ISSUED`) whose
   metadata is an immutable JSON snapshot: totals, forwarding address, deposit entries with reasons, and
   the outcome. A correction after issue is a new statement event, never an edit; the latest issue is
   shown, every issue stays in history. Issuing requires an ended tenancy.
4. The tenant sees the same statement read-only in their portal, scoped through their own lease
   (`visible_for`), including the itemised deposit reasons. Staff-only evidence links are never rendered
   to the tenant.

### D3 — The forwarding address is part of the move-out, not a guess

1. `Lease.forwarding_address` is captured on the end-tenancy form (optional) and can be added or changed
   on the move-out statement screen; both writes are audited (`MOVE_OUT_DETAILS_UPDATED`).
2. The statement warns when no forwarding address is recorded. RHP does not withhold the statement for
   lack of one because the portal is itself a delivery path; the address is what makes mailing possible.
3. **No statutory deadline is enforced.** The return/itemisation window and deduction documentation rules
   are jurisdiction-specific (evidence rows 1 and 3). RHP records the statement date and shows it;
   encoding a deadline needs the owner's jurisdiction as a business fact, and enforcement without it
   would be a fabricated rule. This is recorded as a residual unknown.

### D4 — Settlement stays the same gate

Settlement still requires ended occupancy, a zero balance, no held credit, no pending payment, nothing
left held on the deposit register, and a recorded deposit outcome. After the retained deposit is applied
to arrears and the remainder refunded (or explicitly not collected), those conditions hold and the account
can settle. Issuing the statement is a separate act and is not a prerequisite for settlement — the tenant
can be sent the statement before or after the account closes, and the move-out screen links both.

### D5 — Scope

Not here: post-tenancy damage/cleaning charges and their evidence (E6); refund disbursement or bank
transfer (B3); GL posting of the retained amount and of the deposit liability (B2); email/postal delivery
of the statement; state-specific deadline automation. Retained amounts not applied to AR are a released
liability whose income recognition is a GL concern, not a second sub-ledger outcome.

## Consequences

- A final balance can actually reach zero at move-out: deposit money applied to arrears reduces the
  balance, and the remainder is returned or retained with a reason. This closes the loop ADR-028 opened.
- No new cash is fabricated: payment metrics and the statement's "paid" line still count only real
  receipts; the deposit appears on its own lines.
- The tenant receives one readable accounting instead of a balance and a separate deposit number, and
  the office has an auditable issue history and a scoping-safe tenant copy.
- The ledger's `credit` figure excludes retained-deposit availability, so tenant-facing "available
  credit" keeps its cash meaning; the move-out screen and the reviewed credit form show the deposit
  source explicitly.
- A state deadline or a damage-charge deduction is visibly absent rather than silently wrong; both are
  recorded as open items (the first needs the owner's jurisdiction, the second is E6).

## Alternatives rejected

- **Record the retained deposit as a `Payment` with "deposit" as its method.** It would double-count cash
  in receipts and payments; a deposit was received once and is being reclassified.
- **Auto-apply the deposit to the oldest charge at move-out.** Application against a bill is a manager
  decision (the same rule as held credit, ADR-008); auto-application would hide the decision and make the
  tenant's statement unauditable.
- **Store a second "final statement" balance snapshot as the truth.** Two balances is the disease ADR-028
  removed; the audit event stores what was issued, the ledger stays the one derivation.
- **Hard-code a 14/21/30-day deadline.** The evidence shows the rule is state-specific; guessing would
  invent law for a jurisdiction RHP has not been told.

## Open items

- Owner business fact needed for deadline/documentation automation: the operating jurisdiction (and any
  local deposit rules). Until then the statement records the date and the screen says nothing it cannot
  know.
- E6 will let a post-tenancy damage/cleaning charge carry its reason code, lease clause and evidence;
  only then can a withheld deposit be applied against a *new* charge rather than existing arrears.
- Refund disbursement (bank/cash out) is B3; the statement currently records `RETURNED` as an outcome,
  not a cleared bank transfer.
- Statement delivery by email/print is a presentation follow-up; the tenant portal copy exists.

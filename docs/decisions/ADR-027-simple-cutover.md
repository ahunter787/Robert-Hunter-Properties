# ADR-027 — Starting balances, not reconstructed history

Status: Accepted for implementation, October 20, 2026. E10 tenant-cutover release only.

Owner acceptance, October 21: preserve and merge the verified cutover locally, including the held-credit
and repayment refinement. Preserve the separate accounting blueprint commit. No push, deployment or
accounting go-live approval; outstanding manual verification gaps remain recorded.

**October 21 amendment:** [Held credit and dated repayments](../design/held-credit-repayments.md)
supersedes automatic opening-credit application and the blanket exclusion of opening debt from
overdue totals. Agreed repayment dates govern payable/overdue amounts without fabricating history.

The owner approved manual starting balances, a cutover note and optional evidence. Figures are
manager-entered, not independently verified. An explicit zero is distinct from missing information.

One immutable RHP financial start date bounds native recurring charges. Real lease dates are preserved.
Each imported lease receives an immutable opening record. Nonzero amounts use a linked OPENING ledger
entry with debit/credit direction, never a fabricated payment. For legacy undated opening debt, unknown
historical aging is excluded from dated overdue totals while the debt remains payable. Newly agreed
due dates and installment schedules govern current payable/overdue amounts without claiming original
historical dates. Corrections remain linked entries.
Signed reviews bind actor, lease, amount, note and current state; confirmation locks and revalidates.
Readiness is durable, not inferred from a lease becoming older than the current month.

ADR-016 remains historical. Its initial onboarding controls and the inferred-payment proposal are
superseded. Existing financial records are never rewritten automatically; reviewed history recovery
remains available on compatible legacy databases. Staff-only evidence reuses private Documents.

Archive the original RHP database and private files, verify a scratch restore, then use a separate fresh
development database. Never delete the original or ecosystem stores. Future live initialization requires
its own explicit confirmation. No automated production reset or reset button is permitted.

Accounting B1–B5 remains separately reviewed. Expected payments are not receipts; receipt status is not
bank settlement; lease deposit terms are not evidence of held funds. Google/Calendar/messaging study
work is independent. The bank/fiscal-year/accountant questions are later accounting-release prerequisites.

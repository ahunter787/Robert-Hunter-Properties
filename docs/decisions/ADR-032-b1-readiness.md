# ADR-032 — B1 readiness: one chart, one posting contract, one AR control

- **Status:** Proposed for owner/accountant review, 2026-10-22. **Readiness only — no B1 code, schema or
  production change.** B1 implementation remains separately reviewed and is blocked on the business facts
  and external sign-off in §10 of the readiness document.
- **Date:** 2026-10-22
- **Related:** [ADR-026](ADR-026-property-accounting.md) (accounting slices), [ADR-028](ADR-028-one-kernel.md)
  (one kernel, one allocation engine, kernel events), [ADR-031](ADR-031-move-out-settlement.md) (retained
  deposit register), [property-accounting blueprint](../design/property-accounting.md),
  [B1 readiness document](../design/b1-readiness.md), [kernel events](../kernel/events.md).
- **Evidence:** the readiness document's §1 table — NARPM Accounting Standards chart (2019), REA chart and
  accrual guides, Loopfour AR-control reconciliation, APM Help Buildium deposit accounting and trust
  bookkeeping, Elite Recovery Group ledger terms, Blue Cloud CPA deposit accounting, Oracle JD Edwards
  posted-journal controls, and idempotency-key practice. Method only; no source copied.

## Context

The blueprint and ADR-026 named B1 as "chart, mappings, balanced immutable journals, explicit source-event
posting, trial balance and dated AR controls", and listed prerequisites before it could be implemented:
expected payments post nothing; receipt is not bank settlement; deposit terms are not held money; opening
credit/prepayment classification, future-charge recognition and event-specific idempotency resolved;
opening controls not posted twice or forced equal by an equity plug; bank accounts, fiscal year and reviewer
obtained.

The kernel is now stable: one charge writer, one opening record, one allocation engine and an append-only
deposit register (ADR-028), a future-lease lifecycle and people/logins (ADR-029/030), and an explicit
move-out deposit disposition with a final statement (ADR-031). The remaining work before B1 code is to
settle the accounting contract — not to invent more product behaviour.

## Decision

### D1 — The chart is a numbered owner chart with system control accounts

Adopt the chart in the readiness document §2: bank accounts under 111x, undeposited funds 1450, tenant AR
control 1200, AP control 2100, security deposits held 2300, tenant credits held 2400, equity/opening equity
3000/3070, income 4xxx and expenses 5xxx. System accounts cannot be deleted while they carry history.
Property is a mandatory dimension on every income, expense, AR, AP and deposit line whose source has a
property; one chart plus a property dimension, not a chart per property. This follows NARPM's numbered
structure and undeposited-funds/control-account model (#1) and REA's rental-owner chart (#2), adapted to a
self-managed owner (no PM fee/trust-owner ledger structure, no tax schedules in B1).

### D2 — Accrual GL, one journal set, cash-basis reports as a view

The GL is accrual: a charge accrues income when raised (due date), a vendor bill accrues expense when
recorded, cash movements are separate. Future rent is never recognised; expected payments post nothing.
Cash-basis reporting is a view over the same journals, not a second set. The professional/platform
standard for multi-property books is accrual (#3); the fiscal year and tax basis are owner/accountant
facts and do not change the journal set.

### D3 — Journals are sourced, balanced, immutable and idempotent by event transition

Every journal has the unique source key `<model>:<pk>:<transition>` (e.g. `charge:42:created`,
`payment:7:recorded`, `application:9:applied`, `opening:3:confirmed`) and posts inside the transaction that
creates or advances the source event. Replaying the same transition returns the existing journal; the
database enforces uniqueness and the service treats an `IntegrityError` as replay. Journals are immutable;
a correction is a linked reversal plus a new source event, never an edit (Oracle #9). No journal exists
without a source; no source transition exists without its journal.

### D4 — No manual postings to control accounts

No admin or manager form may create a journal line against AR, AP, deposits held, tenant credits,
undeposited funds or a bank account. Those move only from kernel source events. Manual journals are
limited to owner draws/contributions, reviewed opening batches, and reviewed non-control
reclassifications, with actor and reason. A direct AR journal is the documented common cause of subledger
breaks (#4), so it is refused rather than tolerated.

### D5 — The AR control must tie exactly, and reconciliation is a procedure

After every posting and at least weekly/monthly, `1200 Tenant AR` must equal the sum of lease sub-ledger
balances, portfolio-wide and by property; `2300` must equal the held-deposit register; `2400` the
available-credit sources; `2100` the vendor-bill sub-ledger. Daily/on-demand, undeposited funds and bank
clearing are compared; monthly, the bank statement, GL bank and clearing are reconciled three-way with
exceptions explained (#4, #8). Differences are never erased by an adjusting entry; they are found. Opening
balances post through a reviewed batch to opening equity, which must clear to zero; no unexplained equity
plug is approved.

### D6 — The retained-deposit GL follows the documented charge-then-apply method

The method is decided by the industry evidence, not guessed and not left to an owner opinion: raise the
move-out charges first (unpaid rent, damage, cleaning) as receivables with reasons and evidence, then apply
the security deposit against those charges; the retained portion is income through the charges, the
returned portion reduces the liability and cash. A clearing account is rejected and removed from the
chart. Because RHP does not yet raise post-tenancy damage/cleaning charges (E6), B1 must not post
withheld-deposit journals; B2's deposit disposition waits for E6. The register remains a sub-ledger fact and
the pending disposition is a visible reconciliation exception until then. This is an implementation
dependency (E6), not an unresolved accounting question.

### D7 — Owner facts are onboarding data, not design blockers

Fiscal year, entity/tax basis, opening balances, state deposit rules and bank accounts are operating facts
about Robert's business. The builder is not the owner and must not answer them or treat them as inputs to
the software design. RHP collects them through a guided, audited **go-live onboarding questionnaire** at the
owner account's creation (readiness §11): values are data, incomplete answers are visibly incomplete, and
the go-live checklist refuses accounting readiness while required sections are blank. B1/B3 implementation
may proceed with fixtures and configuration placeholders; go-live waits for the owner to complete the
questionnaire. The owner has a CPA, but whether that CPA is the authority over the system is the owner's
call; RHP neither requires nor appoints a reviewer. Bank accounts are B3 data entered through the registry
and provider-agnostic connection adapter, not code constants (readiness §2.1).

## Implementation note (2026-10-22)

The B1 engine is now implemented in development on `rhp-e10-kernel` (no UI yet, no B2/B3):

- `apps/accounting` adds `ChartAccount`, `AccountMapping`, `JournalEntry` and `JournalLine`, with
  the chart and mappings seeded by a data migration.
- `post_journal` is the only writer: unique `source_key`, balanced lines, same-transaction posting,
  replay returns the existing journal, and journals/lines are immutable. Manual journals to control
  accounts are refused.
- The kernel hooks post `Charge` creation (rent, NNN, responsibility, manual, adjustment, opening
  debt/credit), generated scheduled charges, cleared/cleared-later/reversed payments, and opening-credit
  applications/releases. Receipt applications remain allocations (the receipt is already in AR).
- `ar_control_tie()` compares `1200 AR − 2400 tenant credits` to the lease sub-ledger; the test suite
  asserts the difference is zero. `trial_balance()` and `account_balance()` derive every figure from
  lines.
- `manage.py accounting_sync` bridges existing sub-ledger history idempotently;
  `manage.py accounting_status` prints the trial balance, AR tie and unposted events. A pytest
  fixture reseeds the chart in flushed transaction-test databases.
- Staff screens now exist under `/manage/accounting/`: overview with trial balance and AR tie, chart,
  journal list/detail, the control page, and the reviewed opening-balance sheet. They are manager-only and
  derived entirely from lines. The opening screen posts one balanced immutable opening journal and audits
  it (`ACCOUNTING_OPENING_POSTED`).
- B2 is implemented: received/returned deposits post through the kernel (retention waits for E6; an
  applied retained deposit moves 2300 to AR) and vendor bills/payments post expense/AP/cash-clearing,
  with `deposit_control_tie` and `ap_control_tie` exposing differences. B3 bank accounts and
  reconciliation, write-off as a first-class action and a production data load remain next slices.

## Consequences

- B1's scope is now a closed contract: chart, journal shape, source keys, control restrictions, matrix,
  ties, and the tests to write. An implementation can be estimated and reviewed without redesign.
- The retained-deposit method is decided (charge-then-apply); only the E6 prerequisite remains, so B1 can
  implement every other posting row without waiting on an accounting opinion.
- Owner facts are onboarding data collected at go-live; they do not block design or implementation, and no
  question asks the owner or the builder how accounting should work.
- No code or schema changed: status, backlog and extension records now say "B1 ready for review, not
  started", and the blueprint's ambiguities are superseded by the readiness document where they conflict.

## Alternatives rejected

- **Start B1 and settle the chart/mapping during implementation.** The blueprint explicitly requires the
  posting matrix and idempotency contract first; changing account codes or journal identity after rows
  exist is a migration and a reconciliation break.
- **Use a third-party property-management company chart verbatim.** NARPM's chart is for a management
  company with trust/owner ledgers and fee income; RHP is a self-managed owner. The structure (numbered
  types, undeposited funds, control accounts, opening equity) is adopted; the PM-specific accounts are
  not.
- **Let a manager post a journal to AR to fix a difference.** That is the documented top cause of
  subledger/GL divergence (#4).
- **Invent a withheld-deposit journal.** The evidence is clear on the method: charges first, then the
  deposit. A clearing account was considered as an adaptation but rejected because it is not the
  documented method; waiting for E6 is the implementation order, not an alternative accounting method.
- **Treat cash basis as a second set of books.** It is a report view; mixing methods is a known defect
  (#3).

## Open items carried to B1 review

- B1 implementation plan and estimate (separate review).
- Go-live onboarding questionnaire (readiness §11) for owner facts; answers intentionally unknown until
  the owner's account is created.
- Optional owner-designated CPA review of the chart/opening journal; the builder does not appoint or
  decide the CPA's authority.
- E6 (post-tenancy damage/cleaning charges with evidence), which is the prerequisite for the retained-
  deposit GL posting; B1 does not post that row until then.
- B2/B3/B4/B5 remain later, separately reviewed slices; nothing here authorizes production initialization.

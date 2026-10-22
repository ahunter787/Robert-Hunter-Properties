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

### D6 — The retained-deposit GL mapping is a recorded unknown, not a guess

B1 may post everything in the readiness posting matrix except the withheld-deposit disposition. The E5
register releases a retained deposit before a manager applies it to AR (ADR-031), and RHP does not yet
raise post-tenancy damage/cleaning charges (E6); the industry evidence assumes charges exist first and the
deposit is applied against them (#5–#7). A clearing-account adaptation (2500) is plausible but is RHP's
adaptation, not an evidenced industry method. Until the external reviewer agrees to it — or instructs RHP
to wait for E6 — B1 must not post withheld-deposit journals; the register stays a subledger fact and the
pending disposition is a visible reconciliation exception. This is the one evidence conflict that stops a
complete posting matrix and is exactly the kind of unknown the kernel process retains rather than hides.

### D7 — Go-live is gated on owner facts and external review, not on code completion

B1 implementation does not start until the owner supplies only business facts — fiscal year and
entity/tax basis, opening-balance source (non-bank first), external reviewer, and the operating state's
deposit rules — and that reviewer confirms the chart, Schedule E mapping, opening journal and
retained-deposit mapping. These are recorded in §10 of the readiness document. No owner opinion on
accounting method is requested; the reviewer confirms the method against the evidence and RHP's facts.

**The owner's actual bank accounts are not one of those B1 facts.** They are data entered in B3: a bank
account is a record with a chart account, property/payout assignment and connection status, not a code
constant. TenantCloud adds accounts and assigns properties (#11 in the readiness evidence); Buildium links
existing accounts through a provider and imports transactions (#12). B1 posts receipts to undeposited funds
and needs no bank account at all; B3 builds the registry and a provider-agnostic statement/feed adapter
(CSV/OFX first, connection service later). This avoids hard-coding any owner institution and lets the
office add or reconnect accounts without a code change.

## Consequences

- B1's scope is now a closed contract: chart, journal shape, source keys, control restrictions, matrix,
  ties, and the tests to write. An implementation can be estimated and reviewed without redesign.
- The one unresolved accounting conflict (retained deposits) is visible and blocks only that row, not the
  whole slice; B1 can proceed after review with that row explicitly deferred to E6 if the reviewer agrees.
- Owner facts are reduced to a short, factual list; no answer asks the owner how property accounting
  should work.
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
- **Invent a withheld-deposit journal.** The evidence conflict is real; a clearing account or waiting for
  E6 both need reviewer agreement, and guessing would create a permanent classification error.
- **Treat cash basis as a second set of books.** It is a report view; mixing methods is a known defect
  (#3).

## Open items carried to B1 review

- B1 implementation plan and estimate (separate review).
- Owner business facts in §10 of the readiness document (not bank accounts — those are B3 data).
- External reviewer's confirmation of the chart, Schedule E mapping, opening journal, reconciliation
  procedure and retained-deposit mapping.
- E6 (post-tenancy damage/cleaning charges with evidence) if the reviewer prefers charge-then-apply over
  the clearing-account adaptation.
- B2/B3/B4/B5 remain later, separately reviewed slices; nothing here authorizes production initialization.

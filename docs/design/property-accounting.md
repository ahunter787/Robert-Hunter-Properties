# Property accounting — the blueprint (E10)

## October 20 cutover amendment (governs the earlier draft below)

The owner approved ADR-027: tenant cutover first, with manual manager-stated debt/credit/zero, note and
optional private evidence. No historical reconstruction, CSV import engine or verified-history claim.
Fresh synthetic development data follows a verified archive/restore of the existing database/files.

Before B1, replace the pending-payment posting row below: expected payments post nothing. Confirmation
of receipt does not prove bank settlement. Opening credits are explicit noncash entries, not payments.
Deposit terms do not prove held deposits. Journal idempotency identifies individual source transitions,
and dated AR controls must distinguish future charges from earned income. Opening AP/bank outstanding
items need evidence; no unexplained equity plug is approved. Resolve prepayment/control classification
before the separately reviewed B1 implementation. Reconciliation and external approval gate accounting
go-live, not tenant setup. Fiscal year, opening balances and reviewer remain actual information to
obtain; the owner's bank accounts are B3 data entered through a registry/connection, not a launch constant.

## October 22 B1 readiness amendment (governs the earlier draft below)

The B1 contract is now written down in [B1 readiness](b1-readiness.md) and
[ADR-032](../decisions/ADR-032-b1-readiness.md). Where this blueprint's earlier draft differs, the
readiness document governs:

- **Chart:** readiness §2 (numbered owner chart, undeposited funds, AR/AP/deposit/credit control accounts,
  opening equity, property dimension). The draft chart in §3.2 is historical.
- **Posting matrix:** readiness §5, including receipt vs bank settlement, opening debt/credit counterparts,
  write-off and deposit rows. The draft table in §4 is historical.
- **Journal identity:** readiness §4 (`<model>:<pk>:<transition>`, unique, balanced, immutable, same
  transaction), not a mutable row identity.
- **AR control:** readiness §6 — the GL control must tie exactly to the subledger; no direct journal to AR,
  AP or any control account.
- **Retained deposit:** readiness §9 — the documented charge-then-apply method is adopted (raise the E6
  charge first, apply the deposit, recognise retention through the charge, no clearing account). B1 does
  not post withheld deposits until E6 exists.
- **Owner facts:** readiness §10–§11 — fiscal year, tax basis, opening balances, deposit-law rules and bank
  accounts are go-live onboarding data, not design blockers. RHP ships a questionnaire for them; B1/B3 can
  be built with fixtures and configuration placeholders.

**Status:** B1 journal engine and manager screens implemented in development (ADR-032); the opening-
balance UI and B2–B5 are later slices. The decision is [ADR-026](../decisions/ADR-026-property-accounting.md); this is the working
blueprint for `E10-B1` … `E10-B5`. Each slice gets its own owner review before the next.

**The one-sentence version:** RHP keeps the tenant sub-ledger it already has, adds a real double-entry
general ledger that posts from it, reconciles the bank against it, and prints the statements — the way
Buildium and AppFolio do it — and exports a journal for an accountant rather than outsourcing the books to
one.

## 1. How to read this

Section 3 is the accounting template (chart, dimensions, basis). Section 4 is the posting table — the heart
of the design. Sections 5–6 are the model and the invariants the tests will assert. Sections 7–9 are the
procedures (opening balances, reconciliation, cash out). Sections 10–11 are the outputs. Section 12 is the
build order. Section 13 is what we deliberately do not build.

## 2. Where RHP is today

| Exists (operational sub-ledger) | Missing (the GL) |
| --- | --- |
| Charges: rent, NNN, responsibility recoveries, brought-forward, manual, adjustments | Chart of accounts |
| Payments: received, pending/cleared/void, reversed, by method | Journal entries and a trial balance |
| Derived allocations, statements, overdue states, charge generation | Bank accounts, statements and reconciliation |
| Repair costs with vendors, invoices attached, recharge reviews | Accounts payable and cash disbursements |
| Audit events, immutability, `Decimal` everywhere | Income statement, balance sheet, cash flow |
| Lease security deposit as a stored figure | Deposit liability and its movements |

The sub-ledger answers *"what does this tenancy owe?"*. The GL answers *"what did the property earn and
spend, what is in the bank, and what is the owner's position?"*. Both are needed; the sub-ledger is already
built and stays authoritative for its own question.

**Vocabulary** — the same records, two readings, so nobody has to learn a second language:

| RHP today | Accounting term |
| --- | --- |
| Charge posted | Invoice / receivable accrual |
| Confirmed payment recorded | Receipt, not proof of bank settlement |
| Expected payment | Expected money, not a receipt or bank transaction |
| Bank deposit (separate evidence/event) | Movement into the bank account |
| Repair cost recorded | Vendor bill / expense accrual |
| Vendor payment (new) | Bill payment / disbursement |
| Security deposit held (new movements) | Deposit liability |
| Tenant statement | Statement of account (operational) |
| — | Financial statements (P&L, balance sheet, cash flow) |

## 3. The template

### 3.1 Shape

```
 tenant sub-ledger                        general ledger
 charges, payments, adjustments  ──post──▶  journal entries (balanced, immutable)
 repair costs, recharges         ──post──▶    ├─ chart of accounts
 disbursements, deposit events   ──post──▶    ├─ property dimension on every line
                                              └─ bank accounts + reconciliation
                                                       │
                                          reports ◀────┘   (trial balance, P&L by property,
                                                            balance sheet, cash flow, Schedule E)
```

- **Sub-ledgers stay**: tenant AR (the ledger), vendor AP (repair costs), security deposits.
- **GL posts from them**, never re-derives a balance that the ledger already computes.
- **Every line names a property where the source has one**; portfolio-level lines (owner draws, bank
  transfers) carry no property and never appear in property reports.

### 3.2 The default chart of accounts — superseded by [B1 readiness §2](b1-readiness.md#2-chart-of-accounts-proposed-locked-for-b1)

The table below is the earlier working draft, kept for context. The locked proposal is readiness §2; do not
implement from this table.

| Code | Name | Kind | Normal | Schedule E (proposed) |
| --- | --- | --- | --- | --- |
| 1000 | Operating bank ★ | Asset | Debit | — |
| 1010 | Undeposited funds ★ | Asset | Debit | — |
| 1100 | Tenant accounts receivable ★ | Asset | Debit | — |
| 2000 | Security deposits held ★ | Liability | Credit | — |
| 2100 | Vendor accounts payable ★ | Liability | Credit | — |
| 3000 | Owner's equity ★ | Equity | Credit | — |
| 3100 | Owner draws ★ | Equity | Debit | — |
| 4000 | Rent income | Income | Credit | Line 3 — Rents received |
| 4100 | NNN recoveries | Income | Credit | Line 3 / other income — confirm |
| 4200 | Utility recoveries | Income | Credit | Line 3 / other income — confirm |
| 4300 | Maintenance recoveries | Income | Credit | Line 3 / other income — confirm |
| 4900 | Late fees and other income | Income | Credit | Line 3 / other income — confirm |
| 5000 | Repairs and maintenance | Expense | Debit | Line 13 — Repairs |
| 5100 | Utilities | Expense | Debit | Line 16 — Utilities |
| 5200 | Property taxes | Expense | Debit | Line 15 — Taxes |
| 5300 | Insurance | Expense | Debit | Line 9 — Insurance |
| 5400 | Mortgage interest | Expense | Debit | Line 11 — Mortgage interest |
| 5500 | Professional and admin | Expense | Debit | Line 18 — Other |
| 5600 | HOA dues | Expense | Debit | Line 18 — Other |
| 5900 | Other expenses | Expense | Debit | Line 18 — Other |
| 9000 | Opening balance equity ★ | Equity | Credit | — |

Depreciation and tax schedules are **not** accounts here — they belong to the separate business-side domain
in [extensions §13](../extensions.md).

### 3.3 Dimensions

- **Property** (required on income/expense lines whose source has one) — enables P&L by property and the
  portfolio roll-up.
- **Vendor** on expense lines (the `Vendor` record that repair costs already carry).
- **Tenancy** kept on AR lines via the journal source link, for drill-down; never shown to another tenant.
- No unit dimension: the unit's share is already inside the charge, and the property is the reporting level
  the owner uses.

### 3.4 Basis

**Accrual.** Charges accrue income when due (the sub-ledger already thinks this way); repair costs accrue
expenses when incurred; payments and disbursements move cash. This makes the AR and AP control accounts
meaningful and testable. A **cash-basis report view** (and a Schedule E cash summary) is a later additive
report over the same journals — not a second set of entries.

## 4. Posting rules

> **Superseded by [B1 readiness §5](b1-readiness.md#5-posting-matrix-for-b1) and §4 (journal contract).**
> The table below is the earlier working draft, kept for context. In particular: a receipt credits
> undeposited funds (not AR directly), bank settlement is a separate B3 event, opening credits use the
> tenant-credit liability account, and retained-deposit disposition is an open unknown (readiness §9).

Each explicit source event posts **exactly once**. Identity must distinguish receipt confirmation,
cancellation, reversal and actual bank movement, not only the mutable source row's primary key.
The exact event-key contract is approved before B1. Posted journals remain immutable.

| Source event | Debit | Credit | Property | Notes |
| --- | --- | --- | --- | --- |
| Charge, `RENT` | 1100 AR | 4000 Rent income | ✓ | |
| Charge, `NNN` | 1100 AR | 4100 NNN | ✓ | |
| Charge, `RESPONSIBILITY` (utility) | 1100 AR | 4200 Utility recoveries | ✓ | By `ResponsibilityCategory` |
| Charge, `RESPONSIBILITY` (maintenance) | 1100 AR | 4300 Maintenance recoveries | ✓ | |
| Charge, `RESPONSIBILITY` (other) | 1100 AR | 4900 Other income | ✓ | |
| Charge, `MANUAL` | 1100 AR | mapping chosen at entry, default 4900 | ✓ | Admin/manger picks the income account |
| Charge, `ADJUSTMENT` | reverse the original charge's income line | 1100 AR | ✓ | Uses the `adjusts` link; a reduction is a debit to income |
| Starting debt (`OPENING`) | Opening AR control | Approved opening counterpart | ✓ | Noncash; part of reviewed opening books, never new rental income |
| Starting credit | Approved opening counterpart | Approved credit/prepayment control | ✓ | Exact classification is a B1 review prerequisite; never a receipt |
| Payment expected (`PENDING`) | — | — | ✓ | No financial posting: money has not been received |
| Confirmed payment (current `CLEARED`) | Receipt/clearing account | Tenant control | ✓ | Receipt is not evidence that a bank deposit occurred; finalize mappings before B1 |
| Actual bank deposit (B3) | Bank | Receipt/clearing account | ✓ | Separate evidenced bank movement; never inferred from the payment status label |
| Expected payment canceled (`VOID`) | — | — | ✓ | No receipt was posted to undo |
| Confirmed receipt corrected/reversed | Reverse the receipt's approved posting | | ✓ | Not a payout or refund; actual bank facts remain separately reconciled |
| Repair cost, `INCREASE` | 5000 Repairs | 2100 AP (vendor) | ✓ | |
| Repair cost, `DECREASE` (correction) | 2100 AP | 5000 Repairs | ✓ | Uses `corrects` |
| Repair recharge to tenant | 1100 AR | 4300 Maintenance recoveries | ✓ | The expense stays an expense; the recovery is income |
| **Disbursement** (new) | 2100 AP | 1000 Bank | ✓ | Vendor bill paid |
| **Deposit event** received (new) | 1000 Bank (or deposit account) | 2000 Deposits held | ✓ | |
| **Deposit event** refunded / withheld (new) | 2000 Deposits held | Bank / income or repair offset | ✓ | Withheld amounts follow the settlement decision |
| Owner draw / contribution | 3100 Draws / Bank | Bank / 3000 Equity | — | Manual journal entry (admin) |
| Year-end close | income and expense accounts | 3000 Equity (retained) | — | Closing entries; next year starts clean |

## 5. The data model

New app `apps/accounting/` (never an empty placeholder). All money `DecimalField(12,2)`; all mutations write
an audit event in the same transaction; posted records are append-only.

| Table | Fields (essential) | Invariants |
| --- | --- | --- |
| `accounting_chart_account` | `code`, `name`, `kind` (asset/liability/equity/income/expense), `normal_side`, `is_system`, `is_active` | unique code; system accounts cannot be deleted |
| `accounting_account_mapping` | `event_key`, `chart_account` | one row per event key; the poster refuses unmapped events |
| `accounting_journal_entry` | `number`, `date`, `memo`, `source_type`, `source_id`, `created_by`, `created_at` | unique `(source_type, source_id)`; immutable |
| `accounting_journal_line` | `entry`, `account`, `property`, `amount`, `memo` | entry balances (service + test); signed amounts by normal side, never a negative display |
| `accounting_bank_account` | `name`, `kind` (operating/deposits), `chart_account`, `opening_balance`, `opening_date`, `is_active` | one chart account per bank account |
| `accounting_bank_statement` | `bank_account`, `period_start`, `period_end`, `opening_balance`, `closing_balance`, `imported_at`, `imported_by` | period does not overlap another reconciled period |
| `accounting_statement_line` | `statement`, `date`, `description`, `amount`, `journal_line` (nullable) | matched once; unmatched lines block reconciliation |
| `accounting_reconciliation` | `statement`, `cleared_total`, `adjusted_balance`, `difference`, `reconciled_by`, `reconciled_at` | only when statement = cleared = adjusted |
| `accounting_disbursement` | `date`, `amount`, `method`, `vendor`, `cost` (nullable), `bank_account`, `memo`, `actor` | append-only; reverses by correction |
| `accounting_deposit_event` | `lease`, `kind` (received/refunded/withheld), `amount`, `date`, `bank_account`, `memo`, `actor` | append-only; the deposit register sums them |

Balances are **never stored**: every balance, trial balance and report is derived from journal lines. The
chart of accounts and mappings are seeded by a data migration with the table in §3.2 so a fresh install is
usable immediately.

## 6. Controls and invariants (what the tests assert)

1. **Every journal entry balances** — debits equal credits, to the cent.
2. **Dated tenant controls tie to the dated subledger** on the same effective-date basis. The B1
   specification defines separate credit/prepayment classification. Do not compare an unfiltered
   current statement containing upcoming charges with an as-of earned-income/AR report.
3. **AP control**: `2100` = Σ recorded repair costs (net of corrections) − Σ disbursements.
4. **Deposits**: the liability equals approved held-deposit openings plus received − refunded −
   withheld movements. `Lease.deposit` is the contractual requirement, not proof of funds held.
5. **Three-way reconciliation**: statement closing balance = cleared balance = adjusted cash balance, else
   reconciliation refuses.
6. **Posting is idempotent** per explicit source event; re-running creates nothing and later transitions
   are not suppressed by an earlier event for the same payment row.
7. **Immutability**: posted entries cannot be edited or deleted; a correction is a reversing entry with an
   actor and reason, and both entries are visible.
8. **Authorization**: chart and mappings admin-only; journals and disbursements manager-and-above;
   reconciliation manager-and-above; **no tenant route touches any of it**.
9. **Decimal only**, no floats, no `float()` conversion anywhere.
10. **Audit**: `ACCOUNTING_POSTED`, `ACCOUNTING_RECONCILED`, `ACCOUNTING_CHART_CHANGED`,
    `ACCOUNTING_EXPORTED` (extend `AuditAction`).

## 7. Opening balances (starting the books mid-year)

Tenant cutover is separate from approval of accounting books (ADR-027). Manager-stated opening figures
are allowed without historical evidence for tenant setup, and never presented as independently verified.
Accounting starts at an explicitly reviewed as-of boundary, not automatically when tenant setup finishes:

1. **AR** — the sum of tenant-ledger balances per tenancy at the as-of date.
2. **Deposits** — actual held funds, verified for accounting; not copied from lease deposit terms.
3. **Bank** — the operating account's balance from the last bank statement before the as-of date.
4. **AP, bank outstanding items and remaining balances** — reconcile the complete opening trial balance
   and control details. Do not use an unexplained equity plug; approved opening counterparts need evidence.
5. One **opening journal batch**, with the reconciliation evidence attached (statement PDF in Documents),
   posted once and immutable; later corrections are normal entries.

The procedure is a reviewed service (admin), not a shell command, and it is tested: after it runs, §6's
invariants 2 and 4 hold immediately.

## 8. Bank reconciliation

1. Import the account's **statement as CSV** (bank-provided export; columns mapped in a review step:
   date, description, amount, optional reference).
2. **Match** each statement line to a journal line in the bank account: automatic candidates by amount and
   date (± a few days), then matched by hand where ambiguous.
3. Unmatched statement lines and unrecorded journal lines are **named**, not hidden — the review screen
   lists both.
4. **Three-way check**: statement closing = cleared balance = adjusted cash balance (derived from the
   property ledgers). Only then can the period be marked **reconciled**, with an audit event.
5. A reconciled period is closed for that account; a later correction needs a new entry and a re-open with
   a reason (mirroring the ledger's settled-account rule).

Statement import is CSV first, per the Phase 10 convention; no bank feed and no aggregator in this
extension. A bank account is a **data record** (name, institution, last four, kind, chart account,
property/payout assignment, active, connection status), created in the office. The import/matching layer is
provider-agnostic: CSV/OFX first, and a bank-feed adapter can be added later without changing the ledger or
hard-coding a bank. The owner's actual accounts are entered when B3 starts, not before B1.

## 9. Cash out and deposit movements (the new records)

Two things make the GL reconcileable, and RHP does not record either today:

- **Disbursements** — money leaving the bank to a vendor. Without them the AP accrual never clears and the
  bank can never reconcile. Screens: record a payment against a repair cost (or unallocated), with the
  receipt attachment reusing the documents rules.
- **Deposit events** — received, refunded, withheld. `Lease.deposit` is a stored figure with no movement
  behind it; the liability cannot move without events. The withheld case is also the input E5 (move-out
  settlement) needs.

Both are append-only with actor, date, bank account and a reason where they correct something.

## 10. Reports

| Report | Grouping | Reconciles to |
| --- | --- | --- |
| Trial balance | account | journal |
| Income statement | property / portfolio / category | journal income and expense lines |
| Balance sheet | assets, liabilities, equity | journal balances; AR and AP controls (§6) |
| Cash flow | operating / investing (simple) | bank and undeposited-funds movements |
| Schedule E summary | proposed lines (§3.2) | income statement lines, mapped |
| AR aging / statement | tenancy | the tenant ledger (same numbers, no second arithmetic) |
| AP aging | vendor | recorded costs less disbursements |
| Security deposit register | tenancy | deposit events and `Lease.deposit` |
| Owner equity and draws | period | equity accounts |

Each report is a **reading of journal lines**, never a stored total — the same rule the ledger already
follows. CSV export on every report; PDF only where it earns its place (Phase 10 convention).

## 11. Exports for an accountant

- **Journal CSV** — date, entry number, account code, account name, property, memo, debit, credit, source
  — the universal hand-off.
- **Plain-text journal** (hledger/beancount compatible) — an accountant or the owner can run reports
  without any additional software, and it is diffable and testable.
- One-way, period-scoped, checksummed, recorded in an `ExportBatch` row and audited. RHP remains the source
  of truth; nothing is imported back.

QuickBooks Online/Xero APIs are **not** built now: a CSV hand-off covers the accountant case, and adding a
SaaS dependency would re-create the coupling this decision avoids. Revisit only if an accountant requires
it.

## 12. Build order

| Slice | Scope | Acceptance |
| --- | --- | --- |
| **E10-A** (this doc + ADR) | Decision, blueprint, register and doc links | ADR accepted and published; no product code |
| **E10-B1** | Chart, mappings, journals, poster for charges/payments/adjustments/costs, manual entries, trial balance | Invariants 1, 2, 6, 7, 8, 9, 10; owner review |
| **E10-B2** | Disbursements, deposit events, AP and deposit registers | Invariants 3, 4; owner review |
| **E10-B3** | Bank accounts, statement CSV import, matching, three-way reconciliation | Invariant 5; owner review |
| **E10-B4** | Income statement, balance sheet, cash flow, Schedule E summary, aging tie-outs, CSV exports | Every report ties to the journal; owner review |
| **E10-B5** | Closing entries, owner draws/contributions, accountant CSV and plain-text journal exports | Export round-trip in a text ledger; owner review |

Every slice carries its own migration, tests, docs update, the full gate and a live screen walk.

## 13. Deliberately not built

Trust/escrow accounting and management fees (RHP owns its properties), third-party owner distributions,
1099 e-filing, depreciation and tax schedules (separate domain per extensions §13), payment processing
(Phase 11), bank feeds/aggregators, multi-currency, and any tenant-facing change. The GL never appears in
the tenant portal.

## 14. Open questions

1. **Schedule E mapping** — confirm with the owner's accountant before B4 (the chart is editable; the
   default is a proposal).
2. **Bank setup (B3)** — which operating/deposit accounts the office registers; whether it wants automatic
   feeds or CSV/OFX first and which provider, if any. Accounts are data, never code constants; the
   column-mapping review handles statement variation.
3. **Deposit account separation** — does state law require deposits held in a separate account? The model
   supports it; the owner decides whether to use it.
4. **Disbursement discipline** — who records vendor payments, and with what evidence, so reconciliation is
   not a monthly archaeology exercise.
5. **Closing cadence** — annual closing entries are assumed; a monthly soft close can follow if useful.
6. **Accountant and onboarding** — the owner may designate an accountant/CPA for review and will provide
   the onboarding facts at account creation (fiscal year, tax basis, opening balances, deposit rules, bank
   setup). The builder does not supply or decide these; the export format becomes the acceptance test for
   B5 if a reviewer is designated.

## 15. Risks

| Risk | Mitigation |
| --- | --- |
| Scope: this is the largest extension | Sliced, owner review between slices, B1–B2 useful without B3–B5 |
| Double-posting or a broken control total | Unique source keys, invariant tests (AR/AP tie-outs), reconcile to the sub-ledger every run |
| Bad opening balances | Reviewed admin procedure, evidence attached, immediate invariant check |
| Statements that do not match the accountant's view | Editable chart, Schedule E mapping confirmed before B4 |
| New data discipline (cash out) | Screens designed for the office's actual workflow; reconciliation names what is missing |

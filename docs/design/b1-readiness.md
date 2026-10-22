# B1 readiness — chart, posting contract, control and reconciliation

**Status:** proposed for owner/accountant review, 2026-10-22. **No B1 code, migration or GL table exists
yet.** This document is the readiness gate the [property-accounting blueprint](property-accounting.md) and
[ADR-026](../decisions/ADR-026-property-accounting.md) require before the separately reviewed B1 slice.
The decision record is [ADR-032](../decisions/ADR-032-b1-readiness.md).

The goal is narrow: settle what B1 must build — the chart of accounts, the posting contract, the
idempotency identity of a journal, and how the general ledger proves it agrees with the tenant
sub-ledger — and name exactly which business facts and external review remain. It does **not** build the
GL, touch the live database, or promise a go-live date.

## 1. Evidence

All sources are public product, accounting-practice or standards material. They establish method; none is
copied into RHP, and none replaces the owner's or accountant's review of RHP's own facts.

| # | Source | What it establishes for this design |
| --- | --- | --- |
| 1 | [NARPM® Accounting Standards — Chart of Accounts & Conversion Guide (2019)](https://www.narpm.org/docs/members/NAS/Doc2-Chart-of-Accounts.pdf) | A property-management industry chart uses numbered account ranges by type (assets, liabilities, equity, income, expense), with **undeposited funds** as a clearing asset for money received but not banked, **accounts receivable** and **accounts payable** as control accounts, **cash** accounts, owner equity, and a dedicated **opening balance equity** account that must be cleared rather than left as a plug. It separates trust cash from operating cash. |
| 2 | [REA — chart of accounts for rental property](https://rea.co/chart-accounts-rental-property-complete-setup-guide/) | A rental-owner chart is organised by the same five types and uses four-to-five-digit numbering; security deposits are a **liability, never income**; property-level reporting comes from a **property/class dimension**, not a separate chart per property; repairs versus capital improvements must be separate accounts or categories. |
| 3 | [REA — accrual vs cash basis for rental properties](https://rea.co/accrual-cash-basis-accounting-rental-property-properties/) | Accrual is the professional/platform standard for multi-property and lender-facing books and is what AppFolio/Buildium/Yardi-style systems assume; cash basis is simpler for a small single-entity landlord; **mixing methods is a defect**, and choosing the tax method is an entity/tax-advisor decision. |
| 4 | [Loopfour — reconciling the AR subledger to the GL control](https://loopfour.ai/articles/how-do-i-reconcile-the-ar-subledger-to-the-gl-control-account) | The AR subledger and the GL AR control account are two views of one number and **must tie exactly**. The most common break is a journal posted **directly to the AR control account**, bypassing the invoice/payment transaction types; AR adjustments belong through transaction types (credit memo/adjustment), and reconciliation should run at least monthly and after any direct AR journal. |
| 5 | [APM Help — security-deposit accounting in Buildium](https://www.apmhelp.com/blog/buildium/security-deposit-accounting-in-buildium-setup-recording-and-the-escrow-reconciliation) | Deposits sit in a separate Deposits area as a **liability**; move-out has three outcomes (refund, itemised deductions, full withholding) with documented reasons; escrow/trust reconciliation compares the deposit liability to the bank. |
| 6 | [Elite Recovery Group — resident ledger terms](https://ergroupllc.com/blog/resident-ledger-terms-explained) | Two ledgers: the rent/resident ledger (what is owed) and the security-deposit ledger (money held for the resident). Applying a deposit reclassifies money already received; it does **not** create a second receipt or move cash by itself. |
| 7 | [Blue Cloud CPA — is a security deposit a liability?](https://bluecloudcpa.com/guides/property-management-security-deposits-accounting-tax) | Deposit lifecycle entries: receipt = liability; lawful application against unpaid rent/damage = reduce liability and recognise income (and the repair cost separately); refund = reduce liability and cash, no income. State law governs deadlines/documentation. |
| 8 | [APM Help — trust accounting and bookkeeping](https://www.apmhelp.com/services/trust-bookkeeping) | Operational control practice: daily bank reconciliations, and a **three-way reconciliation** of bank balance, book balance and tenant/owner sub-ledgers; move-in/move-out accounting is where deposits and transfers most often break. |
| 9 | [Oracle JD Edwards EnterpriseOne General Accounting guide](https://docs.oracle.com/cd/B31039_02/jded/acrobat/e1_812aga-b_0406.pdf) | Posted journal entries cannot be revised; corrections are a **void/reversing journal entry**, and the system maintains an audit trail. This supports RHP's append-only journal design. |
| 10 | [CommunityPay — what an idempotency key is](https://www.communitypay.us/concepts/what-is-an-idempotency-key/) and [Apideck — Intuit Enterprise Suite idempotency](https://developers.apideck.com/apis/accounting/intuit-enterprise-suite/gotchas) | Retried writes must be deduplicated by a caller/source-supplied key; the accounting ecosystem treats repeated requests with the same key as the same transaction (Intuit carries the key as its request id). RHP adapts this to posting source events. |
| 11 | [TenantCloud — assign a property to a bank account](https://support.tenantcloud.com/en/articles/11909479-how-do-i-assign-a-property-to-a-bank-account) | Bank accounts are **added by the user as data**, not hard-coded: the first becomes the main operating account, properties are linked to an account, and income and deposit payouts can be routed to different accounts. Accounts can be reassigned later, including the deposit/liability account. |
| 12 | [APM Help — Buildium bank feeds](https://www.apmhelp.com/blog/bank-feeds-buildium-automatic-import) | Established PM products connect the user's existing bank accounts through a provider (not a fixed bank list in the product), import transactions, match them, and fall back to CSV/OFX for history or unsupported institutions. Bank-connection credentials are held by the provider, not by the PM application. |

What the evidence does **not** settle for RHP: the entity's tax basis, fiscal year, bank-account structure,
opening balances and reviewer (owner/accountant facts); and the GL mapping for a retained deposit that is
applied to AR **after** retention when the damage charge does not yet exist (E6 gap). Those are listed as
blocking unknowns in §9–§10, not guessed.

## 2. Chart of accounts (proposed, locked for B1)

Account type and normal balance follow double entry; codes follow the industry's numbered ranges (NARPM
#1, REA #2) adapted to a self-managed owner rather than a third-party management company. Accounts
marked ★ are **system accounts**: they may be renamed but not deleted once they carry history.

| Code | Name | Type | Normal | System | Used for | Evidence / note |
| --- | --- | --- | --- | --- | --- | --- |
| 1110 | Operating bank | Asset | Debit | ★ | The operating bank account; each additional bank account gets its own 111x account | Owner fact for actual accounts |
| 1120 | Deposit/escrow bank (only if used) | Asset | Debit | ★ | A separate bank account for held deposits; the liability is 2300 either way | Bank fact + state/lease requirement, not assumed |
| 1450 | Undeposited funds | Asset | Debit | ★ | Money received but not yet evidenced as banked; cleared only by a bank-deposit event | NARPM #1; kernel receipt-vs-bank rule |
| 1200 | Tenant accounts receivable | Asset | Debit | ★ | **Control account** for what tenants owe; only kernel AR events post here | NARPM #1, Loopfour #4 |
| 1300 | Prepaid expenses (later) | Asset | Debit | | Annual insurance etc., when B2/B4 needs it | Not required by B1 |
| 2100 | Accounts payable | Liability | Credit | ★ | **Control account** for vendor bills (B2) | NARPM #1 |
| 2300 | Security deposits held | Liability | Credit | ★ | **Control account** for money held for tenants; never income | REA #2, APM #5, Blue Cloud #7 |
| 2400 | Tenant credits held | Liability | Credit | ★ | Opening credits and overpayments available to apply; not AR | Kernel credit classification |
| 2500 | Deposit disposition clearing | Liability | Credit | ★ | **Only if the retained-deposit mapping in §9 uses it**; zero at period end | Open review item |
| 3000 | Owner's equity | Equity | Credit | ★ | Capital/retained position | NARPM #1 |
| 3070 | Opening balance equity | Equity | Credit | ★ | Counterpart for reviewed opening balances; must be cleared by the opening journal, never a plug | NARPM #1 |
| 3100 | Owner draws/contributions | Equity | Debit | ★ | Owner money in/out, no property dimension | NARPM #1 |
| 4000 | Rent income | Income | Credit | | Rent charges | REA/Schedule E mapping |
| 4100 | NNN recoveries | Income | Credit | | NNN charges | Blueprint |
| 4200 | Utility recoveries | Income | Credit | | Responsibility charges (utility) | Blueprint |
| 4300 | Maintenance recoveries | Income | Credit | | Responsibility/recharge charges | Blueprint |
| 4350 | Deposit forfeitures and damage recoveries | Income | Credit | | Deposit retained for damage/cleaning not applied to AR | Blue Cloud #7; subject to §9 review |
| 4900 | Late fees and other income | Income | Credit | | Manual/other income | Blueprint |
| 5000 | Repairs and maintenance | Expense | Debit | | Repair costs | REA #2 |
| 5100 | Utilities | Expense | Debit | | Utility costs | Schedule E |
| 5200 | Property taxes | Expense | Debit | | Tax bills | Schedule E |
| 5300 | Insurance | Expense | Debit | | Insurance | Schedule E |
| 5400 | Mortgage interest | Expense | Debit | | Interest only; principal is a liability movement | Schedule E |
| 5500 | Professional and administrative | Expense | Debit | | Legal, accounting, software | Schedule E |
| 5600 | HOA dues | Expense | Debit | | Association dues | Schedule E |
| 5700 | Bad debt | Expense | Debit | | Write-offs (charge adjustment) | Loopfour #4 write-off via transaction type |
| 5900 | Other expenses | Expense | Debit | | Fallback | Schedule E |

Not in this chart: depreciation, capital assets, mortgage principal, sales tax, PM fee income, trust
owner ledgers. Those belong to the separate business/tax domain or are out of RHP's owner-only scope
([extensions §13](../extensions.md)); adding them later is additive.

**Property dimension is mandatory** on every income, expense, AR, AP and deposit line whose source has a
property. Bank/equity lines may be property-less only when the source is owner-level. The evidence (#2)
prefers one chart plus a property dimension over a chart per property.

### 2.1 Bank accounts are data, not a launch constant

A bank account is a **record** created by the office (name, institution, last four, kind, ledger account,
property/payout assignment), not a Python setting, a list in source, or an owner fact that B1 needs in
order to compile. This is how the products do it: TenantCloud adds accounts and assigns properties to
them (#11); Buildium links existing bank accounts through a provider and imports their transactions (#12).

- **B1 needs no actual bank account.** B1 posts receipts to `1450 Undeposited funds`; moving money into a
  bank is the separate bank-deposit event in B3 (kernel events). B1's opening journal can start with
  AR/AP/deposits/credits/equity and leave bank opening balances to B3.
- **B3 builds the registry**, not hard-coded banks: a `BankAccount` record (data) with one chart account
  per bank account, property/payout assignment, opening balance/date, active flag, and connection status.
  The office adds an account in a screen; nothing ships with an owner's account baked in.
- **The bank connection is an adapter, not a bank list.** Start with CSV/OFX statement import (no new
  dependency), then a provider-backed connection service if the owner wants automatic feeds (B3/B5 scope,
  needs a dependency/credential decision). Credentials/tokens stay with the provider, never in RHP; the
  adapter exposes "accounts, statements, transactions" and the rest of B3 is provider-agnostic.
- **Owner's actual accounts are a B3 setup task, not a B1 coding prerequisite.** When B3 starts, the
  office registers the operating account and any separate deposit account; B1 can be built and tested
  before that, with no owner bank data at all.

## 3. Basis and periods

1. **The GL is accrual.** A charge accrues income when the charge is raised (its due date), a vendor bill
   accrues expense when recorded, and cash movements are separate. This is the platform/professional
   standard for multi-property books (#3) and makes AR/AP control accounts meaningful (#4).
2. **No future rent is recognised.** A lease's future schedule is a projection, not a journal
   ([kernel events](../kernel/events.md)). "Coming due" posts nothing.
3. **Cash-basis reports are a view** over the same journals (receipts/disbursements), not a second set of
   entries. The owner/accountant confirms the tax basis; RHP does not mix methods (#3).
4. **Fiscal year** is an owner business fact. B1 posts dated journals; the closing slice (B5) uses the
   confirmed year end. Until then, reports are dated-range reports, not closed-year statements.

## 4. Posting contract

### 4.1 The journal

A planned `JournalEntry` has: `source_key` (unique), `event_type`, `posted_on` (date), `property`
(nullable only for owner-level lines), `lease` (nullable, memo/drill-down), `memo`, `created_by`,
`created_at`, `reversal_of` (nullable, one-to-one), and `lines`. A line has `account`, `debit`, `credit`,
optional `property`, and a party/lease memo. Amounts are `Decimal`, two places.

Rules:

- **Balanced:** for every journal, `Σ debit = Σ credit`, both > 0, and at least two lines. A line is debit
  xor credit, never both, never negative.
- **Sourced:** every journal names an existing source event and a `source_key`; there is no journal without
  a source.
- **One posting per transition:** `source_key` is unique in the database. Replaying the same event —
  double-click, retried command, repeated sync — returns the existing journal and creates nothing.
- **Immutable:** no update or delete. A correction is a new **reversal** journal linked to the original
  (Oracle #9); the reversal carries the same accounts and swapped sides, and a fresh correct source event
  is posted separately. A reversed source event cannot be posted again.
- **Same transaction:** the journal posts inside the database transaction that creates/advances the source
  event, so a committed source always has its journal and a rolled-back source never does.
- **Posting date:** the source event's business date (charge due date, receipt date, deposit date), never
  "today" by convenience; future-dated source events are not posted early.
- **Authorization:** only the kernel service posts. No manager screen and no admin form can create a
  journal line against a control account.

### 4.2 Source-key grammar and event transitions

`<model>:<pk>:<transition>` — for example `charge:42:created`, `payment:7:recorded`,
`payment:7:reversed`, `application:9:applied`, `application:9:released`, `opening:3:confirmed`,
`lease:12:ended`, `lease:12:settled`, `adjustment:5:created`. The transition vocabulary is the event
matrix's transition column, not an API verb. A row that is edited (a charge correction) creates a new
adjustment row with its own key; the original key is never reused.

- The unique constraint is on `source_key` alone (global; source models have unique pks).
- The posting service looks up the key first; `get_or_create` inside the source transaction is the
  implementation shape, with `IntegrityError` as the replay race guard.
- A reversal journal has its own source key (`<original key>:reversed` or the reversing event's key); the
  original and reversal are both retained.
- Event-specific idempotency is per explicit transition, not per row: recording a payment and later
  clearing it are two keys, each posted once.

### 4.3 Control-account restriction

No manual journal may touch `1200 Tenant AR`, `1450 Undeposited funds`, `2100 Accounts payable`,
`2300 Security deposits held`, `2400 Tenant credits held`, or a bank account. Those move only from kernel
source events. Manual journals are limited to owner draws/contributions, reviewed opening balances, and
reviewed reclassifications between non-control accounts; each requires a reason, an actor and a source
document. This is Loopfour's rule (#4): a direct AR journal is the most common cause of a subledger break
and is a red flag, not an adjustment method.

## 5. Posting matrix for B1

B1 builds charge, receipt, application, write-off and opening journals. B2/B3 extend the same engine for
bills, deposits and bank deposits; rows are shown so the contract is complete, with the slice named.

| Source event | Debit | Credit | Property | Slice | Notes |
| --- | --- | --- | --- | --- | --- |
| Charge `RENT` | 1200 AR | 4000 Rent income | ✓ | B1 | Charge due date |
| Charge `NNN` | 1200 AR | 4100 NNN | ✓ | B1 | |
| Charge `RESPONSIBILITY` (utility) | 1200 AR | 4200 Utility recoveries | ✓ | B1 | By category |
| Charge `RESPONSIBILITY` (maintenance) | 1200 AR | 4300 Maintenance recoveries | ✓ | B1 | |
| Charge `RESPONSIBILITY` (other) | 1200 AR | 4900 Other income | ✓ | B1 | |
| Charge `MANUAL` | 1200 AR | chosen income (default 4900) | ✓ | B1 | Manager chooses account |
| Charge `ADJUSTMENT` (decrease) | reverse the original income line | 1200 AR | ✓ | B1 | Exact reversal using `adjusts`; never edits original |
| Opening debt (`OPENING`) | 1200 AR | 3070 Opening balance equity | ✓ | B1 | Reviewed opening only; never rent income |
| Opening credit | 3070 Opening balance equity | 2400 Tenant credits held | ✓ | B1 | Never a receipt |
| Payment expected (`PENDING`) | — | — | — | B1 | Posts nothing |
| Payment recorded/cleared | 1450 Undeposited funds | 1200 AR | ✓ | B1 | Receipt ≠ bank settlement |
| Payment reversed | 1200 AR | 1450 Undeposited funds | ✓ | B1 | Reversal journal for the receipt |
| Bank deposit evidenced | 1110/112x Bank | 1450 Undeposited funds | ✓ | B3 | Separate bank fact, never inferred from status |
| Credit applied | 2400 Tenant credits held | 1200 AR | ✓ | B1 | Reviewed application |
| Credit released | 1200 AR | 2400 Tenant credits held | ✓ | B1 | Undo the application |
| Write-off | 5700 Bad debt | 1200 AR | ✓ | B1 | Via adjustment naming the charge |
| Move-out close-out adjustment | reverse income line | 1200 AR | ✓ | B1 | Cancels unused months exactly |
| Deposit received | 1450 Undeposited funds | 2300 Deposits held | ✓ | B2 | Liability; not AR |
| Deposit returned | 2300 Deposits held | 1450/Bank as evidenced | ✓ | B2/B3 | Cash movement is B3 |
| Deposit retained/applied | see §9 | see §9 | ✓ | B2 | **Open mapping — blocked for B1** |

## 6. AR control and reconciliation

### 6.1 The control equation

At every point in time, for the portfolio and for each property:

```
1200 Tenant AR balance
  = Σ lease sub-ledger balances (charges − effective payments − applied credits − write-offs/corrections)
```

The statement of account, the arrears/aging reports and the GL all read the same facts. The GL control is
not allowed to be adjusted to make the report agree; a difference is a defect to find. This is the AR
control rule in Loopfour (#4) and the reason the kernel has one charge writer and one allocation engine.

### 6.2 Reconciliation procedures (planned)

| Frequency | Check | Pass condition |
| --- | --- | --- |
| Every posting (automated) | Journal balanced; source key unique; journal created with source | No unbalanced/unsourced/orphan journal |
| Daily / on demand | `1450 Undeposited funds` equals receipts not yet banked; no negative clearing balance | Tie to receipt/bank-deposit list |
| Weekly | 1200 AR control = sum of lease balances, by property | Difference zero; exceptions listed |
| Monthly | 2300 Deposits held = sum of `DepositEntry` held; 2400 credits = sum of available credit sources; 2100 AP = sum of vendor bills | Each tie zero |
| Monthly | Bank statement vs 111x bank GL vs 1450 clearing (three-way, APM #8) | Outstanding items explained; no invented entries |
| On any manual journal | Journal does not touch a control account | Refused by service |
| Month-end close | Trial balance, AR aging, deposit control, P&L by property, balance sheet | Reviewed and signed |

Outstanding items are expected timing differences (uncashed checks, undeposited receipts); an unexplained
difference remains visible and blocks approval. Software never invents a payment to clear a difference
(accounting-cutover-plan rule).

### 6.3 Opening balances

Opening books are a reviewed, owner/accountant-supplied set of facts, not a reconstruction:

- The opening journal is a single reviewed batch per property/account with a source document for each
  balance (bank statement, closing statement, accountant trial balance, or a prepared schedule).
- It posts to 3070 Opening balance equity (or the approved counterpart), and 3070 must return to zero after
  all opening batches are posted. An unresolved difference is a visible exception, never a balancing plug.
- Opening AR/AP/deposits/credits are entered through their own reviewed source events (`OPENING` charge,
  opening credit, deposit opening entry), not by direct control-account journals.
- No opening row is inferred from a lease term or a deposit requirement; deposit terms are not proof funds
  were held (kernel rule).
- Opening balances cannot be posted twice: each batch has a source key and is reviewed.

## 7. Idempotency and invariants to test (when B1 is built)

Planned invariant tests, named now so B1's review can check them:

1. **Balance:** every journal has equal debits/credits; a malformed journal cannot be inserted.
2. **Uniqueness:** posting the same `source_key` twice creates one journal and returns the same identity;
   concurrent creation raises one `IntegrityError` and is treated as replay.
3. **Atomicity:** a source event rolled back leaves no journal; a journal failure rolls back the source.
4. **Immutability:** update/delete on a posted journal is impossible at the database/service boundary; a
   reversal is a new linked journal and the original remains.
5. **No direct control postings:** the posting service and any admin path refuse AR/AP/deposit/credit/
   bank/undeposited-funds accounts as manual journal lines.
6. **AR tie:** after every seeded event sequence, 1200 control equals the sum of lease balances (portfolio
   and per property), including adjustment/reversal/write-off paths.
7. **Deposit/credit ties:** 2300 equals the held-deposit register; 2400 equals available credit sources
   after applications/releases.
8. **Tenancy isolation:** a tenant-scoped journal/report query never returns another tenancy's AR; manager
   authorization is server-side.
9. **No future income:** posting a future charge/lease start does not create rent income before its due
   date; expected payments post nothing.
10. **Reversal:** a reversed source cannot be reposted; a correction is a new event and both histories
    remain visible.

The B1 implementation is expected to add these as real tests; this readiness document does not claim they
exist today.

## 8. What B1 will not do

No production initialization, no import of historical books, no bank feed/CSV matching (B3), no vendor
bills (B2), no financial statements or tax schedules (B4/B5), no depreciation/capital assets, no owner
distribution automation, no second user model, no external ledger integration. B1 is the journal engine,
chart, opening journal and AR control only.

## 9. Blocking residual unknown — retained-deposit GL mapping

The E5 register records a `WITHHELD` deposit **before** a manager may apply part of it to an existing AR
bill (ADR-031). The accounting evidence (#5, #6, #7) assumes a different order: the move-out charges
(damage, cleaning, unpaid balance) are raised first, then the deposit is applied against those charges;
the retained portion becomes income when kept. RHP does not yet raise post-tenancy damage/cleaning charges
(E6), so at the moment of withholding there may be no AR bill for the retained amount to settle.

Consequences for B1:

- A withheld deposit cannot be mapped unambiguously to `Cr AR` (if it will be applied later) versus
  `Cr income` (if it is retained) at the moment of withholding.
- A clearing account (2500) could hold the retention until the statement is issued and the split is final,
  then clear to AR/income; that is a defensible control, but it is **RHP's adaptation**, not something the
  cited industry sources describe. It needs the external reviewer's agreement.
- Until that agreement, the B1 posting engine must **not** post withheld-deposit journals. The register
  remains a subledger fact; AR control and deposit liability reconciliation must show the pending
  disposition as an explicit exception.

This is the one evidence-conflict that stops a complete B1 posting matrix. It is recorded, not hidden.

## 10. Go-live boundary — facts only the owner/accountant can supply

B1 implementation does not need the owner's actual bank accounts (see §2.1). It waits on the following
**business facts and review**, not on industry-method opinions:

1. **Fiscal year and entity.** Fiscal year end; entity type (sole proprietor/LLC/S-corp); tax basis the
   accountant requires (cash or accrual) and confirmation of the Schedule E mapping for the chart.
2. **Opening balances (non-bank first).** The date RHP's GL begins; the source of each opening AR, AP,
   deposit, credit and equity balance (closing statement, prior accounting system, accountant-prepared
   trial balance, or prepared schedule); who prepares and who reviews it. Bank opening balances can arrive
   with B3's bank registry; they do not block B1.
3. **External reviewer.** Name and role of the accountant/CPA who will review the chart, opening journal,
   reconciliation procedure and go-live sign-off; the reports/format they require.
4. **Deposit rules.** The operating state's deposit return/itemisation deadline and whether a separate
   trust/escrow account is required (carried from ADR-031).
5. **Retained-deposit mapping.** Reviewer's agreement to the clearing-account adaptation in §9, or an
   instruction to wait for E6 charges first.
6. **B3 bank setup (when B3 starts, not B1).** Which operating and deposit accounts to register; whether
   the office wants automatic bank feeds or CSV/OFX first; which provider (if any); and who authorises the
   connection. These are data and scope decisions, not code constants.

Until then, the B1 status is **ready for review, not ready to build**. No GL table, no migration, no owner
data import and no production change is included in this readiness pass.

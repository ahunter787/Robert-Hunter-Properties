# E10 accounting and controlled cutover — working proposal

Archived owner-answer record, not the current implementation scope. Owner answers are unchanged;
the local decision link is rebased for this archive directory. ADR-027 governs the approved release.

**Status:** Draft for owner decisions, October 20, 2026. No product implementation authorized by this record.

This proposal joins the committed E10 accounting design to the owner's migration strategy. It does not
replace either source, approve unanswered choices, or fold another agent's branch into this checkout.
The concurrent TenantCloud feature study remains independent: Google sign-in, Calendar and expanded
messaging are neither dependencies nor deliverables here.

## 1. Owner questions

The first three questions were originally asked only in chat. They are recorded here so they can be
answered by ID without relying on a transient question widget. Recommendations are not owner answers.

| ID | Decision needed | Recommendation or information needed | Owner answer |
| --- | --- | --- | --- |
| CUT-Q1 | Tenant starting balances first, or one coordinated operational/accounting launch? | Build reviewed tenant cutover first, then accounting in reviewed slices. Keep accounting explicitly unavailable until its opening books reconcile and are approved. A tenant rehearsal does not authorize production launch. | Use recommended  |
| CUT-Q2 | What supplies the verified opening figures? | Identify paper/check records, spreadsheets/CSV, or an existing accounting export. Start with guided manual entry and a documented CSV template; do not build vendor-specific adapters without real sample formats. |   Minimal. Not verified. Just a cutover note, with optional document upload. We just need to get to current. Can't trace it. |
| CUT-Q3 | What should happen to current partially accurate development transactions?  | Preserve the existing database; rehearse in a separate disposable database. Do not automatically promote test transactions, delete them, or treat their calculated balances as verified source balances. Review actual source records before choosing the launch dataset. | We can archive the existing database and build a new one. Its all inaccurate test data anyways. Finally, when RHP goes live, we'll clear it again and start from scratch, and I'll use true-live data from Robert  |
| CUT-Q4 | What bank accounts, property/account relationships and fiscal year are actually used? | Supply an account inventory without credentials, identify where tenant deposits are held, and confirm the fiscal year. Propose one RHP-wide cutover; do not assume one bank account per property or independently dated property conversions. | Use recommended.|
| CUT-Q5 | Who verifies the opening books and supplies accounting evidence? | Name the owner/accountant responsible for the closing trial balance, bank reconciliation and deposit/AP controls. Preserve the strategy's accountant-approval gate before accounting go-live; do not substitute software validation for professional approval. | We'll try this recommendation. I don't know how the bank reconciliation will work|

The cutover date is deliberately unset. December 31, 2026 closing / January 1, 2027 opening is an example,
not an approved deadline. Select the date after source inventory and rehearsal.

## 2. Sources and current state

- Owner strategy: `RHP_Migration_Opening_Balances_Harness.md`, supplied October 20, 2026. SHA-256:
  `3f92d9bb60e5b85e9875c583475f59cc693734ca40476fb12976b5683feb1ef1`.
- Accounting design: branch `rhp-e10-accounting`, commit `a5b1cd5`, directly based on local `main`
  `93254ac`. Its ten changed files are documentation and publisher registration, not accounting code.
  ADR-026 and its property-accounting blueprint exist on that branch, not yet on `main`.
- Existing [onboarding decision](../../decisions/ADR-016-retroactive-onboarding.md) supports historical
  charge generation or a balance-forward entry. A negative starting balance currently becomes a cleared
  payment. That is not a safe representation of an imported credit for accounting or received-money totals.
- The newly accepted existing-history recovery only records a reviewed billing start date. It does not
  verify the history or establish a migration baseline. Preserve it while replacing initial migration setup.
- The current billing-readiness guard depends on whether the lease began before the current month.
  Replace that heuristic with durable setup state: a normal new lease must not require migration merely
  because the calendar rolled over.

An accounting start date with bank opening balances, outstanding bank items and tenant carry-forward
balances is an established pattern: [DoorLoop's setup guide](https://support.doorloop.com/en/articles/6119391-set-up-an-accounting-start-date-for-your-bank-accounts-and-leases).
This supports cutover rather than historical reconstruction; it does not prescribe RHP's exact model.

## 3. Amend the E10 blueprint before code

Retain its approved direction: a bounded in-app double-entry ledger for RHP-owned properties, with
one-way accountant exports. Reconcile these issues in ADR-026, the blueprint, governing specification,
E4/E10 records, architecture, database and security documentation before implementation:

- **Expected is not received.** Current pending payments mean money expected. They produce no receipt,
  bank or undeposited-funds journal. Existing confirmed-payment status also does not independently prove
  bank settlement. Receipt recognition and bank-deposit/reconciliation evidence need distinct events.
- **Opening credit is not a new receipt.** Introduce explicit opening debit/credit records and provenance;
  never implement a credit by inventing a payment, refund or current income. Document whether tenant
  prepayments use a liability control or signed AR before implementing the poster; obtain accountant review.
  Show debts and credits separately by tenancy even where a control reconciliation uses their net total.
- **Due date, recognition date and import date differ.** Define dated AR and journal tie-outs. Do not
  equate a today's statement containing future-due charges with an as-of trial balance, recognize future
  rent early, or backdate old income simply because an opening item retains its original due date.
- **Source transitions need separate identities.** One payment row can be confirmed, canceled or reversed.
  Journal idempotency must bind each explicit source event, not suppress later transitions through a
  single unique payment ID. Avoid reconstructing missing events by parsing notes or audit prose.
- **Deposit required is not deposit held.** Keep lease deposit terms separate from verified held funds,
  liability and associated cash. Imported held deposits are opening liabilities, not new receipts.
- **Complete opening books.** Include verified AR, credits, AP, held deposits, cash, outstanding checks and
  deposits, and other evidenced balance-sheet accounts. Import a balanced closing trial balance; do not
  silently force an unexplained equity plug. Identify any opening-equity amounts and resolve them through
  reviewed evidence. Journal balance and control-account variances are hard commit blockers.
- **Historical control balances are not new activity.** Existing unpaid repair bills enter opening AP
  without accruing their old expense again. Classify bank outstanding items without counting opening cash
  twice. Retain existing fixed-asset/loan balances where required by the trial balance, without building
  depreciation schedules, asset management or loan-servicing features.
- **One role matrix.** Resolve the blueprint's inconsistent manual-journal wording. Proposed boundary:
  managers perform ordinary accounting operations and reconciliation; administrators maintain the chart,
  mappings and migration approval. Do not add an accountant login role merely to capture external sign-off.

## 4. Proposed implementation sequence

These are E10/cutover work units, not new numbered product phases. Finish and review each before the next.
No accounting code is started during this planning pass. Preserve the other agent's committed branch and
all future study work; baseline integration requires explicit authorization.

### A. Reconciled design and source inventory

Preserve the supplied strategy and original owner feedback as source material. Resolve the questions above,
write a migration ADR and amend ADR-016 rather than deleting its history. Mark full-history onboarding and
the inferred-prior-payment calculator as superseded proposals for initial migration, not approved work.
Publish the combined proposal/questions through the existing scoped Design and engineering/Plane workflows
after reconciling the E10 baseline. Do not publish a checkout missing the other agent's accounting records
over a newer published baseline.

Deliver sample manual-entry and CSV contracts using synthetic data, a worked opening AR/deposit/AP/bank
reconciliation and an explicit posting/event matrix. Resolve recognition, control-account and receipt/bank
semantics before B1 implementation. Keep accounting unavailable in production until the complete opening
approval gate, even if earlier slices are useful in development.

### B. Cutover staging and historical sources

Create a bounded migration workspace under staff routes, administrator-only initially. Reuse existing
identity, private-file serving and audit infrastructure; do not introduce multi-organization SaaS models.
Use one RHP cutover record, versioned staged batches and explicit source-to-existing-record mappings.
Do not silently merge people or leases by names, or create duplicate production identities during preview.

Provide manual entry and validated CSV first. Separate source inventory, mappings, validation, staged
opening items, reconciliation controls, review and finalization. Preserve source IDs, checksums, original
dates, source line references, mapping versions, actors and approval evidence. Deduplicate across repeated
uploads and batches using source identity plus explicit conflict handling, not filename alone.

Archive documents and optional structured historical rows separately from operational charges/payments.
No archive object participates in balances, allocation or charge generation. Stage files privately;
enforce limits and quarantine failures. Never execute spreadsheet content; guard CSV exports against formula
injection. Do not claim existing file-type validation performs malware scanning. Satisfying the strategy's
scan requirement needs an approved scanner path before quarantined source files become available; ask
before adding any dependency. XLSX processing and universal column-mapping engines are not first-release
requirements.

### C. Tenant opening state and billing readiness

Import or explicitly map verified properties, units, people and leases while retaining real term dates,
amendments and rate schedules. Keep the business's first native financial date separate from original
due dates, import timestamps and later lease starts.

Stage unpaid opening items at their verified remaining amount, with original due dates for aging and
optional original-invoice/paid-to-date evidence. Use one reviewed balance-forward item when detailed open
items are unavailable; state that historical aging is unknown rather than inventing it. Preserve credit
ownership, held-deposit evidence and references. Do not recreate paid components, synthetic receipts or
future bills for the rest of a lease.

Extend the authoritative tenant-ledger services to include explicit opening debits/credits. Keep normal
payment allocation rules and same-date expandable-bill presentation; do not introduce component-selectable
payments. Tenant statements distinguish "Balance brought forward" from native bills and payments, with
authorized historical documents where available. Opening credits never enter received-payment metrics.

Use explicit durable readiness for imported leases and ordinary new leases. Retain existing route paths
where practical, retire full-history migration controls and ensure every generator respects the cutover
boundary. Imported active leases are not ready merely because their dates or status happen to pass a
calendar heuristic. Later newly created leases do not reopen the organization-wide migration.

### D. E10-B1/B2 — journal foundation and opening controls

Build the chart, mappings, immutable balanced journals, explicit source-event poster, manual-journal
controls and trial balance. Add AP, disbursement and deposit movements in the reviewed B2 slice. Every
schema change receives a migration. Retain authoritative operational services; do not maintain stored
balances or a second tenant allocation engine.

Use one explicit bridge per approved opening item/control amount. If tenant opening state was finalized
earlier, bind the accounting opening to that exact approved version and reconcile all intervening native
events through the shared effective-date/event policy. Do not replay all old charges into revenue or post
both a control total and its subledger detail twice. Unsupported source classification blocks posting.

### E. E10-B3 — banks and coordinated financial finalization

Add bank accounts, CSV statement import, reviewed matching, outstanding-item treatment and reconciliation.
Keep bank balances tied to explicit bank events, not to the tenant payment status label. Bank opening date,
statement balance and ledger book balance are distinct facts, with named reconciling items.

Final review identifies the exact cutover, records affected, source checksums, mappings, evidence, trial
balance, gross tenant debts/credits, AP, deposits, cash and variances. Bind approval to a version/fingerprint;
lock and revalidate affected state in a database transaction. Duplicate submissions are idempotent; stale
or tampered reviews fail. Database finalization is atomic; file availability is checked before commit and
failure cleanup is explicit. Notifications and external writes are not part of the financial transaction.

Produce an immutable downloadable manifest with approval identity/time and integrity checksum. This is
audited approval, not an unimplemented claim of legal digital-signature certification. Finalized records
are corrected through reviewed linked adjustments/reversals, never silent re-import or deletion.

### F. E10-B4/B5 — reports, closing and accountant handoff

Add financial statements, aging/control tie-outs, scoped CSV exports, closing and owner-equity operations
in the existing reviewed slices. Confirm fiscal year, chart and report mappings with the accountant.
Do not promise cash-basis or tax-ready outputs merely because accrual journals exist.

Provide the accountant CSV first. Treat hledger and Beancount as distinct target formats: choose and test
an actual export adapter before claiming compatibility, rather than labeling one generic text file as both.
Historical monthly/annual summaries and combined legacy/native analytics remain optional later work;
archived records never silently populate current financial reports.

## 5. Verification and acceptance gates

- A 2022 lease retains its dates, begins native billing at the approved cutover and does not acquire
  years of reconstructed bills. New leases remain ready across month rollover. No future lease-end bill
  build is introduced. Signed existing-history recovery stays safe while its replacement is reviewed.
- Opening debt, credit, mixed open items, original aging, unknown aging, held versus required deposits,
  unpaid vendor bills and outstanding bank items reconcile without fabricated cash or duplicate controls.
- A pending payment posts no receipt; confirmation, actual bank movement, cancellation and reversal each
  have correct, independently idempotent treatment. Starting credits do not inflate dashboard receipts.
- Trial balance balances; dated AR/AP/deposit/bank controls tie to approved source evidence and subledgers.
  Unexplained variances, stale source data and missing mappings prevent approval. Future-due charges do not
  silently become earned current-period rent.
- Re-upload, cross-batch duplicates, repeat confirmation, concurrent edits, stale review, rollback and
  crash/retry cannot partially import or duplicate money. Finalized corrections retain their lineage.
- Administrators alone finalize migration; managers retain existing operational permissions. Workers and
  tenants cannot access staging or accounting. Archive/download access remains tenancy-scoped, including
  former tenants and new occupants. Unauthorized IDs and CSV/file attacks are tested server-side.
- Rehearse backup/restore and a complete synthetic cutover outside the current development database.
  Inspect staff/tenant desktop and phone views, keyboard and script-disabled operation. Preserve approved
  amount colors, bill disclosures, inline corrections and all existing financial/maintenance regressions.
- Each implementation slice runs full tests, lint, Django and deployment checks, CSS build, migration
  checks/application and smoke start. Publish approved records and run ecosystem verification; report
  publication gaps separately. Accountant approval is an accounting launch gate, not a substitute for tests.

## 6. Boundaries and next approval

This draft adds no application models, migrations, dependencies or live financial data. It does not merge,
commit, push or deploy either branch. The current development database remains untouched.

Exclude third-party property management, universal legacy adapters, decades of synthetic transactions,
native mobile apps, bank feeds, payment processing, TenantCloud integrations, depreciation automation and
loan servicing. Preserve enough verified opening balances for complete books without expanding those
excluded domains.

First approval requested: answer CUT-Q1 through CUT-Q5 and approve the reconciled design/source-inventory
work unit. Subsequent product implementation remains separately reviewable; unanswered recommendations
must not become silently implemented policy.

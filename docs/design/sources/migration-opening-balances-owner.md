# RHP — Historical Data Migration & Opening Balances

**Implementation brief for AI harness**  
**Status:** Proposed | **Prepared:** October 2026

> Core rule: preserve real-world history, establish a reconciled opening state at a controlled cutover, and only post native transactions after go-live.

## 1. Purpose and decision

RHP must onboard established rental-property businesses without recreating decades of transactions. Implement a controlled historical-data migration and financial cutover capability as foundational architecture—not an afterthought. True lease dates and property histories must remain intact, even when the RHP financial ledger begins later. The migration process must not silently transform archived transactions into live postings.

## 2. Three distinct data classes

Historical archive: source PDFs, CSVs, reports, legacy ledgers, documents and optional read-only historical rows. These are searchable but never affect live balances.
Opening state: as-of-date positions for tenant receivables, deposits, liabilities, outstanding vendor bills, bank reconciliation, property and unit status, and accounting balances. These are explicitly approved migration entries.
Native operational history: RHP-issued charges, receipts, credits, adjustments and journal entries occurring under RHP after the cutover.

## 3. Cutover semantics

Support an explicit accounting cutover date per organization (and only allow independently scoped cutovers if the ledger architecture supports them safely). For example, December 31, 2026 is the legacy closing date and January 1, 2027 is the first native accounting date; this is illustrative, not a prescribed deadline. Maintain historical lease start/end dates separately. Capture effective dates, import dates, source-system IDs, and provenance independently. Never rewrite genuine historical commencement dates to match cutover.

## 4. Lease and tenant conversion

Import property, unit, tenant, occupancy, lease, lease versions/amendments, rental rate schedules, recurring charges and deposit obligations. A lease beginning in 2022 remains a 2022 lease even when RHP opens in 2027. For unpaid balances, prefer open-item detail (rent, late fees, credits, unapplied cash, payer ownership, aging/due dates) over a single balance-forward amount when accounting allocation or dispute handling requires detail. Settled pre-cutover charges/payments should remain archived, not recreated. Do not double-count deposit cash, deposit liabilities or receivables in GL and subledgers.

## 5. General ledger conversion

Import a reconciled, balanced opening trial balance as of the cutover boundary and post via clearly identified opening journal entries. Preserve chart-of-accounts mappings and fiscal periods. Subledger detail must tie exactly to control accounts: tenant AR, vendor AP, deposit liability, cash and fixed assets. Handle outstanding checks/deposits in transit for future bank reconciliation and retain the last completed bank reconciliation. Retain loan-level principal terms and fixed-asset cost basis/accumulated depreciation, when included in scope. Do not create a fake current-period revenue/expense transaction to force balance equality. Accountant approval required before ledger go-live.

## 6. Summary history without synthetic transactions

Optionally ingest annual or monthly financial aggregates for prior-year reporting, labeled as LEGACY_SUMMARY. Such aggregates are analytics-only and must not be posted to the live general ledger. Display source, period, completeness and precision flags. Users must be able to distinguish native RHP financial reports from combined reports incorporating archived summaries.

## 7. Migration workspace and stages

Create an admin-only workspace with stages: (1) create migration/cutover, (2) upload and inventory sources, (3) preview and map columns/accounts/IDs, (4) validate/deduplicate, (5) stage data, (6) reconcile against source control totals, (7) review and sign off, (8) atomically commit, (9) record immutable outcome/manifest. Support dry runs and cancellation before commit; after commit changes require explicit reversal or controlled adjustment, not silent re-import. The tenant portal must not show unapproved staged data.

## 8. Import safety and provenance

Each imported row needs migration_batch_id, source_system, source_file, source_record_key, content checksum, effective_date, original identifier, import timestamp, mapping version, actor and status. Ensure stable natural-key/idempotency behavior per import batch; duplicate uploads must not duplicate financial postings. Quarantine malformed rows and report actionable errors. Never execute formulas/macros embedded in CSV/XLSX, never trust file names or tenant-provided IDs, and scan uploaded documents before making them available. Archived records remain read-only and cannot auto-post.

## 9. Reconciliation and lock

Require source-to-target reconciliation at minimum for: trial balance debits=credits; GL control accounts vs subledger totals; tenant AR by tenant/open item; security deposits by tenant/property and associated cash where applicable; AP by vendor/open bill; cash with outstanding items; unit/lease occupancy counts. Show legacy total, staged RHP total, variance and source report citation/attachment. Block commit when nonzero financial variances exist unless an authorized, documented exception is explicitly allowed by policy; journal postings still must balance. On finalization, produce a signed exportable migration report and lock source baselines.

## 10. UX requirements

The tenant portal should show a clear opening-balance line with cutover date and a link to historical records where available, not a fabricated multi-year payment history. Admin users get a migration dashboard with batch status, conflict resolution, mappings, affected-property preview, reconciliation and audit events. Display a prominent banner when a report combines legacy summary data with native ledger activity. Ensure granular role-based access; tenants may only view their own authorized lease/ledger documents.

## 11. Proposed conceptual entities

migration_job(id, organization_id, cutover_date, status, source_system, created_by, approved_by, approved_at)
migration_batch(id, migration_job_id, type, source_file_id, checksum, mapping_version, imported_at, status)
legacy_document(id, organization_id, tenant_id?, lease_id?, property_id?, source_metadata, blob_ref, access_policy)
legacy_ledger_row(id, batch_id, source_record_key, tenant_id?, effective_date, original_type, original_amount, original_balance?, raw_payload, search_fields)
opening_ledger_item(id, job_id, tenant_id, lease_id?, due_date, item_type, amount, remaining_amount, source_ref, posting_id)
opening_journal(id, job_id, entry_date, account_id, debit, credit, source_ref)
legacy_financial_summary(id, job_id, period, property_id?, account_id, amount, source_ref, summary_granularity)
reconciliation_control(id, job_id, control_type, scope_id?, legacy_value, target_value, variance, evidence_ref, approval_status)
migration_audit_event(id, job_id, actor_id, occurred_at, action, previous_status, next_status, details)
These are conceptual starting points. Normalize tables, money types, account mappings and transactional integrity to match the final technology stack.

## 12. Guardrails for implementation

Use integer minor monetary units or a fixed-precision decimal type, never binary float. Financial postings must be balanced and atomic. Separate transaction date, effective date, import date and posted date. Enforce organization-level scoping and auditability in all queries. Prevent backdating native activity across the lock boundary without privileged adjustments. Support attachment retention, export, backups and restore testing. Check jurisdiction-specific landlord/tenant record-retention and trust-accounting rules with qualified counsel/accountants before production.

## 13. Delivery phases for the AI harness

Phase A — Domain design: cutover state machine; mapping contracts; tenancy, GL and deposit invariants; security model; migration ADR.
Phase B — Staging infrastructure: validated CSV upload, document archive, schema mapping, dry-run results, provenance and deduplication.
Phase C — Operational opening state: tenant/lease import, recurring charges, open items, deposits and clear balance-forward display.
Phase D — Financial opening state: chart-of-accounts mapping, opening trial balance, AP/AR control reconciliation, bank outstanding items, fixed assets/loans if applicable.
Phase E — Reconciliation and approval: variances, evidence, blockers, approval, atomic commit, adjustment workflow and exported report.
Phase F — Historical visibility: legacy read-only ledger search, archived documents and optional summarized reporting.
Phase G — Hardening: permission tests, batch retry/idempotency, large-file handling, failure injection, rollback/reversal semantics and data export.

## 14. Acceptance tests / definition of done

1. A lease dated 2022 can be imported with its real start date while RHP postings start in 2027.
2. A 54-month closed history need not be re-entered; an opening tenant balance is accurate and traceable.
3. Open rent and fee items retain original due dates and aging.
4. Repeated upload or repeated commit cannot duplicate balances.
5. Legacy CSV rows can be searched but never affect GL, tenant balance or payment allocation.
6. Deposit detail totals reconcile to associated control accounts, and deposits cannot be implicitly treated as rent revenue.
7. A deliberately mismatched subledger/control account blocks approval.
8. Partial database failures cannot leave half-committed opening journal entries.
9. An admin can export the migration manifest, mapping, reconciliation evidence and approvals.
10. A tenant cannot access another tenant’s historical documents or balances.
11. Optional summarized history remains visibly distinguished from native transactional reports.
12. Subsequent corrections are audited adjustments rather than hidden changes to a finalized import.

## 15. Non-goals and open decisions

Non-goals: universal integration with every accounting platform; automatic reinterpretation of all old ledger events; reconstructing 1987-present transactions; using archived data to auto-bill tenants; replacing professional accounting/legal review.
Decide before implementation: Is GL inside RHP or in external accounting software? Are bank accounts / trust funds held per property or entity? What is the fiscal year? Which source systems and export formats exist? What retention/access controls apply to personally identifiable tenant records? Which historical financial views need monthly versus annual granularity?

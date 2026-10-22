# E10 refinement — held credit and dated repayments

**October 21 consolidation (ADR-028):** the allocation snapshot described below is now the only engine;
the read-time projection and the `AllocationAccount` marker are deleted. Credits remain held until a
manager applies them, exactly as specified here.

Owner approved October 21, 2026. Implemented and verified on `codex/e10-cutover`; the owner subsequently
authorized local preservation and merge on October 21. No push, external deployment or database reset
authorized. Preserve the accounting blueprint commit and outstanding cutover work. Recorded manual
verification gaps remain open; local merge acceptance is not accounting go-live approval.

## Approved behavior

Credits remain available until explicitly applied by a manager/admin. Immutable source-linked
applications and releases are not receipts, refunds or transfers. New confirmed payments cover the
oldest currently due obligations; surplus stays held when later bills arrive. Pending payments supply
no available credit. Whole bills—not rent/NNN components—are the manager's allocation boundary.
A $1,000 unpaid bill plus $200 held credit means $1,000 due, $200 available, $800 net position.
Credit coverage is labeled credit applied, not payment received. Tenants may view, not apply credits.

Opening debt has a separately confirmed payment due date or monthly repayment agreement. Only due
installments count as due now; earlier unpaid installments count as past due. Full unpaid principal
remains in account balance. Future repayments are not upcoming rent charges. Dates clamp to short
months using the original due day; exact Decimal principal determines the final smaller installment.
Record agreement date/source, tenant-visible explanation and private staff reason. A new agreement
does not assert original historical due dates. Existing undated debt remains explicit until reviewed.

Schedule changes preserve immutable versions and completed applications. Corrections use linked
adjustments and review the resulting remaining schedule together; no negative installments or silent
rewriting of missed dates. No duplicate charges, interest, fees, automatic acceleration or term changes.
Ending occupancy leaves existing repayments intact; settled accounts remain locked.

## Implementation and acceptance

Add schema migrations for source-linked applications, reversals, allocation initialization and dated
repayment versions/installments. Serialize mutations on the tenancy, reauthorize server-side, sign
reviews with state fingerprints and actor binding, reject stale/duplicate/tampered confirmations and
derive all balances. Reads never write. Preserve legacy-derived applications explicitly and preserve
settled history; existing applications may be released only through reviewed actions.

Test credit hold/apply/undo, surplus, corrections, receipt reversals, $11,500 at $500 = 23 repayments,
ordinary rent alongside installments, past/future dates, early repayment, cent rounding, month clamping,
cross-tenancy access, former tenants, locks, concurrency, rollback and legacy reconciliation. Review
both portals and shared dashboard metrics on desktop/phone/plain forms; run full project gates,
migration checks, smoke start and ecosystem verification. After owner review pause financial expansion
until the full accounting extension and industry-practice audit. Earlier test results do not certify
this refinement.

## Local review and compatibility

- [Held-credit practice](http://localhost:8000/manage/ledger/leases/9/): $1,000 due, $200 held credit,
  $800 net account position. Browser QA applied and then released the $200; both events remain visible.
- [Monthly-repayment practice](http://localhost:8000/manage/ledger/leases/8/): $11,500 opening debt,
  23 repayments of $500 from November 5, 2026, plus the separate $2,300 October rent/NNN bill.
  Current due/past due: $2,300; full account balance $13,800; future repayments $11,500.
- Both are separate synthetic examples. Existing practice leases, original database/archive and private
  files were not reset. Existing legacy-derived credit applications remain until reviewed undo.
- New additive migrations: ledger 0007 (allocation accounts, applications/releases, plan versions and
  installments) and 0008 (reconciled legacy snapshot). Original charges/payments are not rewritten.
  Backward migration refuses operational agreements/applications; restore a backup instead. Only an
  untouched legacy-derived snapshot can be rebuilt for historical migration verification.
- No dependencies, GL, banking, payment processing or general concessions were added.

## Changed components

- Ledger: models, authoritative services/projections, new `applications.py`, `finance_reviews.py`,
  `finance_views.py`, management routes, and adjustment routing; migrations 0007/0008.
- Starting accounts: `apps/leases/cutover.py`, `cutover_views.py`, starting form/review template.
- Staff/tenant surfaces: financial summary, repayment/application disclosure, ledger actions/overview,
  tenant dashboard/statement and financial-review template; shared staff-dashboard credit metric.
- Tests: held-credit/repayment suite, current-cutover expectations, receipt factory and future-credit
  regression. Governing ADR/specification/architecture/security/database/phase/extension records and
  scoped Design publisher/index updated; unrelated accounting blueprint and owner sources preserved.

## Verification notes

Final full regression gate: **1,185 passed, 5 opt-in browser suites skipped**, 362.62 seconds. The
additional targeted cutover/HTTP/privacy/backfill/documentation run passed 56 tests. Lint/format,
system/deployment checks, CSS build, migration generation/application checks and fresh application
health passed. Shared two-lease projections use six queries, not per-row lookups. Read-only November
5/6 rollover moved the $500 installment into due-now/past-due totals without creating any entries.

Earlier runs exposed an irreversible derived-snapshot migration blocking historical migration tests,
unclosed test-thread database connections, and a POST fixture containing None rather than an empty
value. Those were corrected; the final full gate is clean. Snapshot reversal still refuses genuine
operational agreements/applications. No original money records are removed to make tests pass.

Authenticated manager browser QA covered desktop and 390px phone, native keyboard review, Back retaining
the draft, Cancel, credit application/release and unchanged receipt totals. Temporary QA access was
signed out, deactivated and given an unusable password. Tenant privacy/plain-form behavior is tested
server-side; a separate tenant browser login, script-disabled browser, 200% zoom and print-preview checks
were not completed. Screenshots were inspected in the browser but not uploaded/published as artifacts.
No application error is being waived by those browser/publication gaps.

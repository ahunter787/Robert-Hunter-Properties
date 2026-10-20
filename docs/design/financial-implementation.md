# Financial clarity — first implementation release

**Status:** Owner-accepted reading-surface checkpoint, expandable bills and reviewed existing-history
recovery, October 20, 2026. Local commits and squash into `main` are authorized from
`codex/financial-clarity`. Remaining financial task forms are not implemented and await separate
review, including the owner's forthcoming onboarding solution. No push or deployment is authorized.
**Related:** [Audit](financial-audit.md), [vocabulary and cues](financial-vocabulary.md), E9 / E11.
**Baseline:** Phase 9 is locally merged as `caf1281`; outstanding audit sources are preserved.

## Approved first checkpoint

### Owner-approved recovery — keep existing account history

An older active lease can have existing charges/payments but no billing start date. The charging
guard then demands setup while the original setup service refuses existing charges. The owner
approved an explicit recovery at the existing setup URL: review the recorded history, choose a
billing start date and give a reason, then confirm a signed review. Only the billing start date
and an append-only audit event change. No opening balance, inferred receipt, generated charge,
payment or replacement history is created. Do not silently repair live records.

Bind the review to the manager, lease, chosen date/reason and current financial/lease state.
Revalidate under the lease lock; reject stale, expired, forged and replayed confirmations.
Preview, Back and Cancel write nothing. Existing history remains visible before/after the date;
the date controls where subsequent explicit charge posting checks for missing periods. This is
a narrow recovery, not approval for the deferred prior-payment calculator or setup redesign.

### Bill and recovery verification — October 20, 2026

Implemented in this accepted checkpoint: a shared due-date bill projection in `apps/ledger/presentation.py` with
read-model support in `services.py`, native bill summary/component templates for both portals,
separate payment templates, whole-card progressive enhancement and responsive styles. The existing
Adjust form no longer presents per-component paid/remaining figures; its mutation rules and initial
amount behavior remain unchanged pending the separately approved correction-form redesign.

Recovery adds `apps/leases/history_recovery.py`, `ExistingHistoryForm`, the existing onboarding
view's recovery branch, `lease_existing_history.html`, and matching staff notices. It writes only
the billing start date and audit event after explicit confirmation. Existing two-method setup stays
available for accounts without charges. No model, migration or dependency was added.

Verification: 68 focused bill/financial tests passed; 47 recovery/onboarding/bill tests passed.
The bill-only full gate passed 1,126 tests, and the final combined full gate passed **1,136 tests,
five opt-in browser tests skipped, 327.56 seconds**. The initial full run found three obsolete
presentation assertions; all were reconciled and the final full run has no failures. Lint, Django
and deployment checks, CSS build, JavaScript syntax and migration checks passed.

Disposable authenticated browser review covered staff/tenant bill displays, the exact $2,510.56
example, separate $1,000 receipt and $1,510.56 bill remainder, independent disclosures, ordinary-content
clicks, keyboard expansion, selecting text, component Adjust navigation, native script-blocked
disclosures, desktop/tablet/phone layout and tenant privacy. Recovery review, Back/retained input and
explicit confirmation kept the synthetic $840 balance and original entries, removed the setup prompt
and recorded the audit event. QA used a separate test database/cookie names and safe mail backend;
all disposable records and agent-created QA servers/tabs were torn down. No real account was changed.

Current captures: `bills-desktop.jpg`, `bills-phone.jpg`, `bills-tenant-desktop.jpg`,
`history-recovery-phone.jpg` and `history-recovery-confirmed-phone.jpg` under
`docs/design/financial-clarity/captures/`. They are synthetic local review artifacts. The prior
Outline asset-upload limitation remains; actual 200% zoom and print-preview verification remain
unverified. E10 branch `rhp-e10-accounting` / commit `02142cb` was not merged, rewritten or published.

Changed test coverage includes new `tests/ledger/test_bill_presentation.py` and
`tests/leases/test_history_recovery.py`, the opt-in financial browser fixture, and updated intentional
copy/grouping assertions in ledger, lease and expense-recovery tests. Governing specification,
architecture/security, ADR-011/014/016, Phase 4/5 and financial vocabulary/gallery records are reconciled.

### Owner-approved refinement — expandable bills

Charges sharing a tenancy and exact due date appear as one expandable bill, including one-time
charges. The October 5, 2026 example totals $2,510.56 across rent, NNN, gas, electricity, garbage
and water. Payments (received, expected, canceled or undone) remain separate dated records.
Show payment progress and remaining amount only for the bill, never for individual components.
Keep component descriptions, icons, inline corrections and authorized Adjust actions; there is no
bill-level Adjust action. Cards start collapsed and open independently. Noninteractive card content
toggles disclosure, but actions, links, controls and text selection do not. Native summary controls
remain keyboard accessible and work without JavaScript.

Use one read-only grouping projection for staff and tenants. Sum signed corrected charge effects;
preserve credits and full-history running balances, with bills before payments on shared dates.
Group before filtering/pagination. Existing Decimal allocation, immutable entries, settlement locks,
tenant privacy and dashboard definitions remain unchanged. No invoice model, migration or accounting
feature is introduced. E10 accounting work on `rhp-e10-accounting` remains isolated and untouched.
The owner subsequently authorized local preservation and squash of this implemented checkpoint;
push and deployment remain unauthorized. Remaining task proposals below are not acceptance of unbuilt work.

### Owner-requested refinement — icon mapping and transaction history

The owner confirmed that the earlier screenshot/layout difference was simply synthetic test data.
The real entry point is `/manage/leases/<id>/?section=ledger` or the equivalent
`/manage/ledger/leases/<id>/`; port 8014 remains the separate older prototype, not the live portal.

- Replace the download-like payment tray arrow with a banknote/check, and the document-like generic
  rent glyph with a house/dollar. Expense recoveries use a receipt/dollar; other charges use a
  dollar/plus circle. Clock, crossed clock, correction arrow and account book distinguish expected,
  canceled, corrected and starting entries. Both portals use the same charge-kind mapping.
- Display **Expense Recovery** wherever the ledger charge type appears, including its correction
  and end-tenancy review. Keep stored identifiers and actual bill descriptions unchanged.
- Default staff transactions to newest first and the past 12 months, retaining upcoming entries.
  Date order and History controls offer oldest first and all history using ordinary GET forms.
  Show an explicit older-history link/count when rows are hidden. Retain sort/history across local
  lease sections and browser Back; unknown values safely fall back to the defaults.
- Derive running balances from the entire chronological account before filtering/reversing rows.
  A shorter display never changes account totals or erases an older charge/payment/correction.
  A period without rows says so rather than pretending the account has no history.
- These are read-only presentation refinements, not approval to start the remaining financial forms
  or alter another agent's accounting design documents. No model or migration is needed.

Verification of this refinement: 55 icon/statement/expense-display tests passed; 50 workspace/ledger
regressions passed; 19 focused financial-clarity tests passed after the new history coverage was added.
Disposable authenticated browser QA passed, including default newest-first/year view, all-history
oldest-first, full-history balances, Back, carried section filters, script-blocked form submission and
390px layout. The screenshot is synthetic and the test database was torn down. The normal portal
container is confirmed to mount this checkout at `/app`, run the development server and serve the
current stylesheet. No live tenant record was modified. The full project rerun passed:
**1116 passed, five opt-in browser tests skipped, 313.31 seconds**. Financial browser QA passed
separately. Lint, Django/deployment checks, CSS build and migration checks passed; no migration exists.

Refinement files: the existing financial presentation/template helpers, lease view/workspace context,
SVG component, staff transaction table, tenant statement rows/components, and tests were updated.
`templates/management/ledger_adjust.html` and `lease_end.html` receive the charge-label correction only;
their workflows and mutation rules are unchanged. Local captures are `icons-history-{desktop,phone}.jpg`.

Implement the shared staff lease financial workspace and equivalent tenant summaries first, then
present populated states for owner review before propagating financial entry/correction forms.
Keep the middle lease navigation and remove only its Unit workspace and Full-width ledger links.
Both existing financial entry URLs must render the same lease workspace. Keep transactions at the
available content width, corrections inline, and existing routes and authorization unchanged.

Approved amount-only meanings: owed/due/recorded cost red; received payment/credit balance green;
explicit correction delta purple; scheduled rent, expected payments, labels and percentages black.
No blue or orange financial meanings. Pending means “Expected—not received.” Upcoming posted
charges belong to the account balance; unposted scheduled rent does not. An empty account is not
evidence of payment. The scope includes staff and tenants, not just manager screens.

Remaining task flows below follow this review checkpoint. Nonfinancial editing-screen findings
(Unit 4) are deferred, as are the proposed prior-payment calculator and F05 classification change.

### Checkpoint implementation and verification

- Both existing staff entry routes use `LeaseDetailView` and the same lease workspace/template.
  The ledger URL forces the financial section; existing local section/filter URLs remain addressable.
  Primary navigation identifies the lease consistently. Middle navigation retains its five sections,
  photos and identity; only Unit workspace / Full-width ledger links are removed.
- `apps/ledger/presentation.py` reads the authorized ledger. Posted upcoming totals never fall back to
  unposted rent. The scheduled-rent line is black and outside recorded balance totals. Empty, paid,
  corrected-to-zero, expected-payment, overdue and credit states have explicit treatments.
- Transactions and audit history span the workspace below the account header/actions. Browser review
  caught the initial laptop-width clipping; this revision fits the running-balance column at 1265px.
  On smaller screens the labeled, keyboard-focusable table region retains horizontal scrolling.
- Shared amount classes and first-party line icons support staff transactions and tenant statements.
  Tenant lease/statement/dashboard use the same summary meanings without staff controls, correction
  reasons or administrative history. Tenant dashboard structure and staff dashboard definitions remain.
- No financial mutation service, model or dependency changed. No migration is needed. Existing entry,
  posting, clearing, cancellation, reversal, settlement and setup forms remain for the next checkpoint;
  their existing labels/actions have not yet been propagated to the approved new task flows.
- Focused runs: 56 financial/tenant-dashboard tests passed; 18 workspace tests passed after the
  full-width correction. The first full suite reported 1108 passed, five skipped and three old-copy
  assertion failures; all three were updated and passed when rerun. A subsequent run was stopped after
  another obsolete statement-count assertion; that assertion was updated too. The final full suite
  passed: **1111 passed, five opt-in browser tests skipped, 327.09 seconds**. No test failure remains.
- Disposable authenticated browser QA passed twice (one before the width correction, one after).
  Final review covered 1265px desktop, 768px tablet and 390px phone, six populated staff states,
  tenant credit/expected-payment pages, both entry URLs, Terms/Back, keyboard disclosure/focus and a
  server-enforced script-blocked workspace. Test records were torn down; cookies were separate from
  normal portal sessions and mail used the in-memory test backend. No real financial data was edited.
- Lint, Django checks, deployment checks, CSS build and migration checks passed; fresh loopback smoke
  health/sign-in passed. Actual 200% browser zoom and print-preview validation remain unverified.
  Synthetic captures are local; the previously documented Outline asset-upload limitation remains.

The owner's concurrent accounting decision/blueprint work is separate and must be preserved. This
checkpoint adds no accounting code, classifications or changes to accounting design records. No
commit, merge, push, deployment, reset or cleanup of another agent's files was performed.

**Owner review:** compare navigation, amount-only colors, upcoming-versus-scheduled distinction,
credit/pending/empty states and inline corrections. Approval of this reading surface precedes entry,
correction, starting-record, allocation and repair-cost form propagation. It is not acceptance of the
entire financial first release.

### Changed components in this checkpoint

- Views/context: `apps/common/context_processors.py`, `apps/common/templatetags/rhp_format.py`,
  `apps/leases/views.py`, `apps/leases/workspace.py`, `apps/ledger/views.py` and new
  `apps/ledger/presentation.py`.
- Shared workspace: `templates/management/lease_workspace.html`, `lease_detail.html`,
  `lease_ledger_content.html`, compatibility `ledger_lease.html` and new
  `lease_financial_history.html` in the same directory.
- Shared display components: `templates/components/amounts_due.html`, `statement_row.html`,
  `statement_month.html`, `statement_component.html`, new `financial_summary.html` and
  `financial_icon.html`; tenant `templates/account/dashboard.html` and `templates/tenancy/payments.html`.
- Styles/cache version: `assets/css/input.css` and `templates/base.html`; generated CSS is rebuilt,
  not tracked. No JavaScript or financial mutation service changed.
- Tests: new `tests/ledger/test_financial_clarity.py`, `tests/test_financial_clarity_browser.py`;
  approved copy assertions in `tests/accounts/test_dashboard.py`, `tests/leases/test_lease_desk.py`,
  `test_lease_templates.py`, `test_onboarding.py`, `tests/ledger/test_tenant_area.py` and
  `test_tenant_payments.py`. The carried-over audit characterization remains unchanged.
- Records: master specification, architecture, security, ADR-021, Phase 4/5 records, E9 extension
  entry, Design index/audit/vocabulary/owner-note/implementation/gallery sources and publication
  manifest. Synthetic example builder, editable scene book, vector/PNG/PDF exports and new QA captures
  are under `docs/design/financial-clarity/`. Existing audit tooling and original captures are preserved.

## Preserve the accepted system

Start from locally merged Phase 9. Implement a separately authorized E9 presentation/workflow follow-up
on its own branch; do not start Phase 10, landlord accounting or the prior-activity calculator.
Preserve existing URLs/names, Decimal services, role gates, immutable corrections, settlement locks,
tenant audience isolation and signed allocation/recharge reviews. Do not change Django administration.

## Unit 1 — Financial meaning and correction safety

Resolve F01–F12 and F28 before lower-risk copy polish.

- Render one shared lease Rent & Payments layout with a consistent identity header and full-width
  account table through both existing entry paths. Navigation context is validated URL state, never
  authorization. Do not replace either existing route with a new competing account.
- Distinguish posted upcoming charges from unposted scheduled rent using existing projection flags.
  Do not label empty records as evidence of payment. Keep the approved dashboard totals unchanged.
- Add reusable type/status icon-label treatments from the proposed matrix. Received payments, credits,
  costs and corrections remain distinct; no Paid out button or bank-payment implication.
- Reword pending/cleared/void/reversal actions around outcomes. Keep exact existing payment mutations,
  but provide amount, tenant and resulting-balance review for consequential corrections.
- Charge correction asks direction and change amount, showing current corrected total and resulting
  total. Quick-fill controls do not submit; final confirmation invokes the existing adjustment service.
- Explain settlement blockers in plain language and show credit balances without negative-debt wording.

**Separate decision gate:** F05's legacy starting-credit/payment representation must not be “fixed” by
guessing from text, modifying historical entries or changing dashboard cash classification in this UI
unit. Characterize it, disclose starting-record provenance, and obtain a separate domain/reporting
decision if monthly received totals need different semantics.

## Unit 2 — One-time starting records

Resolve F13–F15 using existing onboarding capabilities, not the proposed reconciliation calculator.

- Step 1 selects Full history or Starting balance and shows when to use it.
- Step 2 shows only that method's applicable dates, actual prior-receipt total or known balance, and
  source note. Retain existing eligibility and date rules; do not add receipt derivation.
- Step 3 reviews generated charges, aggregate historical payment or brought-forward entry, cutover,
  resulting account effect and what will remain absent. Use existing pure calculations and a signed,
  stale-safe review before the current atomic save. Repeated submission must not duplicate setup.
- Back, Cancel and validation retain input without writes. Plain forms provide all steps. On completion,
  show setup in history rather than continuing to promote it as routine work.

## Unit 3 — Bills, allocations and repair costs

Resolve F10–F11 and F16–F19 without changing allocation arithmetic or liability decisions.

- Existing bills open at allocation with compact bill context; new bills retain their detail step.
  Use “Assign remainder,” explicit saved/proposed labels and smaller phone ring placement.
- Preserve per-field basis, explicit recipient, exclusions, vacancy funding, unit colors, rounding,
  over-allocation errors, stale-response handling and signed review/save. Saving never posts charges.
- Separate new repair costs from corrections and tenant-charge preparation. Keep recorded cost,
  proposed tenant charges and actual payments unmistakably distinct. Reuse reviewed recharge services.

## Deferred — Remaining editing screens

Resolve F20–F27 using grouped fields, consistent headings and short operational explanations.
Property/unit forms group identity, photos, physical details and service state. Tenant access controls
stay under Account & access. Document upload shows Related to and explicit visibility. Maintenance
publication names the tenancy; announcements make all-versus-selected scope explicit. Delivery failures
retain uncertain-outcome warnings. Preserve contact-edit restrictions and restricted deletion.

## Verification and release gates

- Test old/new entry-point equivalence, due-now/upcoming/credit states, empty accounts, received versus
  expected payments, reversals, inline corrections and settlement locks across all authorized roles.
- Test correction quick-fill without writes, stale/tampered reviews, concurrent changes and duplicate
  submissions. Verify the amount shown in confirmation equals the existing service result.
- Test both starting-record methods, validation persistence, missing rent/NNN/bills, no inferred cash,
  Back/Cancel, repeated setup and wrong/ended/settled account eligibility.
- Retain the exact $79 / $55 / $24 allocation regression, protected third units, percentages, vacancy,
  rounding and posted locks. Verify property/tenancy/document/audience context cannot be forged.
- Review populated desktop/phone and tablet pages, keyboard, 200% zoom, script-blocked forms, contrast,
  non-color interpretation and print. Synthetic screenshots and diagram sources stay separate from
  private development records; documentation print rules never constrain live website color.
- Run full tests, lint, Django/deployment checks, CSS build, migration checks and smoke start. No model
  or dependency change is presumed; any discovered need returns for scope review first.
- Publish source-backed records and synthetic review material through scoped Design publication;
  synchronize Outline/Plane and verify. Owner accepts each unit before the next broad propagation.

The implemented first checkpoint is owner-accepted for local preservation and squash into `main`.
Remaining financial tasks require the next reviewed scope; do not preempt the owner's onboarding
proposal. Push and deployment remain unauthorized.

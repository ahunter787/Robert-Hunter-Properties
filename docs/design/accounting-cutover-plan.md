# E10 — Simple cutover first, accounting in reviewed stages

**October 21 kernel consolidation:** [ADR-028](../decisions/ADR-028-one-kernel.md) finishes the cutover's
deletion on an industry-standard basis — one opening position, one allocation engine, one charge write
path, and deposits as a held-liability register with a move-out outcome — and records the conformance
table behind the GL slices. The cutover release below is otherwise unchanged; B1–B5 remain separately
reviewed.

**Status:** Tenant-cutover and [held-credit/dated-repayment refinement](held-credit-repayments.md)
implemented and verified; owner accepted for local preservation and merge October 21. Final gate: 1,185 passed, 5 opt-in browser
suites skipped. Earlier verification below describes the initial release. Further financial expansion
pauses for the separately reviewed accounting extension and industry-practice audit.
**Branch:** `codex/e10-cutover`, based on committed E10 design `a5b1cd5`. Preserve that accounting design
commit independently in local `main`, then squash the cutover implementation. No push or deployment.

## Approved owner decisions

The original answers and broader proposal are preserved (with the local decision link rebased) in
[sources/accounting-cutover-owner-answers-20261020.md](sources/accounting-cutover-owner-answers-20261020.md).
The supplied harness is preserved in
[sources/migration-opening-balances-owner.md](sources/migration-opening-balances-owner.md).
[ADR-027](../decisions/ADR-027-simple-cutover.md) governs this first release; the old broad import draft
is not implementation scope.

| ID | Owner answer and effect |
| --- | --- |
| CUT-Q1 | Tenant starting accounts first; accounting follows in separately reviewed slices. |
| CUT-Q2 | Minimal, unverified information: stated balance, cutover note, optional supporting document. No tracing or historical reconstruction required. |
| CUT-Q3 | Archive development data and start fresh with synthetic examples. Actual launch will use Robert's real data after a separately confirmed initialization. |
| CUT-Q4 | Follow the recommended inventory process. Actual bank-account relationships and fiscal year are still facts to obtain before accounting configuration, not defaults inferred from this answer. |
| CUT-Q5 | Try external review for opening books. Explain reconciliation before implementing it; reviewer identity/evidence remain accounting-release prerequisites, not blockers for tenant setup. |

## Tenant-cutover release

- One administrator-reviewed RHP first native financial date. Real lease dates remain unchanged.
- Manager reviews a starting debt, credit or explicit zero with a note and optional existing private
  lease document. Use the existing upload workflow to add evidence; no import engine is introduced.
- Preview and Back write nothing. Signed confirmation binds the actor, lease and financial state.
  Confirmation locks and revalidates; repeat confirmation is idempotent.
- `FinancialCutover` and `LeaseOpeningRecord` are immutable protected records. Nonzero opening records
  link ordinary immutable OPENING ledger entries; a credit uses the decrease direction, never Payment.
  Existing adjustment controls provide linked corrections.
- Unknown original historical aging stays explicit. Manager-confirmed payment dates/repayment schedules
  now govern due-now and past-due amounts. Legacy undated debt remains payable but outside dated
  overdue totals until reviewed. Starting entries do not enter new-charge or received-payment totals.
- Superseded October 21: opening credits remain held until explicitly applied; see the refinement.
  They are not cash refunds, new receipts or another tenancy's money.
- Native generation respects cutover, lease term and today. No whole-lease past/future bill build.
  Durable readiness survives calendar rollover. New ordinary leases are marked ready at activation.
- New receipts require initial setup and cannot be dated before cutover. Existing legacy charges/payments
  are retained, and reviewed existing-history recovery remains compatible, including payment-only history.
- Preserve URLs, amount colors, expandable bills, separate payments, inline corrections and permissions.
  Supporting notes remain staff-only; tenants see their opening entry/date and explicitly shared files.

## Accounting remains later work

The in-app accounting direction remains approved in ADR-026. The separately reviewed slices are:

| Slice | Deliverable |
| --- | --- |
| B1 | Chart, mappings, balanced immutable journals, explicit source-event posting, trial balance and dated AR controls. **Readiness complete (ADR-032); implementation not started — see [B1 readiness](b1-readiness.md).** |
| B2 | Vendor bills/payments, held-deposit movements, AP and deposit registers. |
| B3 | Bank accounts, statement CSV import, matching, outstanding items and approved reconciled opening books. |
| B4 | Property/portfolio statements, control tie-outs, aging and accountant-reviewed report mappings. |
| B5 | Closing, owner equity and tested accountant exports. |

Before B1, finish the posting matrix: expected payments post nothing; receipt status is not bank
settlement; deposit requirements are not proof of held funds. Opening credit/prepayment classification,
future-charge recognition and event-specific idempotency must be resolved before its implementation.
Opening controls cannot be posted twice or forced into equality by an unexplained equity plug.
**October 22:** these are resolved in [B1 readiness](b1-readiness.md) and
[ADR-032](../decisions/ADR-032-b1-readiness.md), except the retained-deposit disposition mapping, which
is a recorded unknown pending external review; B1 implementation remains not started and waits on the
owner facts and reviewer sign-off in readiness §10.

Bank reconciliation means matching actual bank-statement lines to recorded receipts and payments.
Outstanding checks/deposits explain timing differences. Unexplained differences remain visible and
block approval; software must never invent a payment to erase a difference.

No GL, bank matching, tax-ready reports or external sign-off is delivered by tenant cutover. The
TenantCloud/Google/Calendar/messaging study is independent, not a dependency or a work item here.

## Development archive and local review

- Original database `rhp` and uploaded files retained; no original records deleted.
- Restricted archive/restore manifest:
  `.uv-cache/cutover-backups/20261020T235016Z_35246782/manifest.json`.
- Database restored into an isolated scratch database; table counts matched. All 14 restored private
  upload files matched the archive bytes. The archive is local, not an off-host disaster-recovery copy.
- Fresh development database: `rhp_cutover_dev_20261020`. Active administrator logins retained for
  access; no old tenant, portfolio or financial records copied. New examples are explicitly synthetic.
- Fresh uploads use `/app/media/cutover-dev-20261020`; original upload storage remains intact.
- Synthetic review financial date is October 1, 2026, not an approved production cutover date.
- Database/archive tooling never drops databases or edits settings itself, refuses production settings,
  and requires explicit apply. No ecosystem stores or configuration changed.

Local review starts at [Leases](http://localhost:8000/manage/leases/) and
[financial start](http://localhost:8000/manage/financial-start/) (administrator only).
Debt/credit/zero and later native activity are demonstrated with synthetic examples.

## Verification and handoff

Initial-release full gate (historical evidence): **1,162 passed, 5 opt-in browser suites skipped**, 369.13 seconds. The additional
targeted cutover/legacy/migration run passed 81 tests. Lint/format, Django/deployment checks, CSS build,
migration generation/application checks and restarted application health passed. Two additive migrations
were applied to the fresh database: leases 0011 and ledger 0006. No new dependency or accounting app.

Earlier runs exposed superseded copy expectations and a historical-schema test using the live model;
those tests were corrected. One run crossed UTC midnight and exposed pre-existing import-time TODAY
assumptions in date-sensitive tests. The final clean run after midnight passed; that test-timing
limitation is not a change to the application's date rules.

Manual browser review covered 390px phone, 1024px tablet and desktop, with separate 127.0.0.1 QA cookies
instead of the owner's localhost session. Back retained amount/note; confirmation wrote one starting
record; keyboard Return expanded the card; $200 credit offset $1,000 native rent to $800 without a
receipt. Temporary QA login is deactivated at handoff. Browser script-disabled/200% zoom and published
screenshot uploads remain verification gaps; plain-form server behavior is covered by tests.

Published Design records use the existing scoped workflow. The older calculator Design page contains
owner edits and was deliberately left untouched when its protection check stopped publication. Its
superseded status is recorded here and in the engineering copy. No owner notes or old documents removed.

Tests cover opening states, no receipts, unknown aging, allocation, corrections, invalid/missing
choices, stale/tampered/expired reviews, replay, actor/object scope, retained evidence, rollback,
settled/ended accounts, readiness and bounded generation. Retain all existing financial, privacy,
maintenance and communications regressions.

Review examples: [starting-balance practice](http://localhost:8000/manage/leases/6/onboarding/),
[opening debt example](http://localhost:8000/manage/leases/1/),
[opening credit example](http://localhost:8000/manage/leases/5/),
[explicit zero](http://localhost:8000/manage/leases/3/), and
[credit applied to native rent](http://localhost:8000/manage/ledger/leases/2/).

Run full tests, lint, Django/deployment checks, CSS build, migration checks and fresh smoke start.
Publish through scoped Design and engineering/Plane workflows from this combined checkout, then verify.
The owner accepted the cutover checkpoint for local merge October 21. Do not proceed into B1 without
its separately reviewed implementation plan. No new dependencies, production initialization, push or
external deployment is included. Browser/print/publication gaps above remain recorded.

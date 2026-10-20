# Financial clarity and manager-workflow audit

**Status:** Audit complete. Financial first release approved; shared reading-surface checkpoint in
progress on `codex/financial-clarity`. Original findings below remain the audit evidence, not a claim
that every issue is already fixed. Nonfinancial editing findings remain deferred.
**Date:** October 20, 2026. **Register:** E9 follow-up, with E11 presentation context; not Phase 10.
**Baseline:** local `main` squash commit `caf1281`; audit branch `codex/financial-clarity-audit`.

## Start here

The arithmetic and safeguards are not the principal usability problem. RHP repeatedly asks an operator
to understand the implementation before recognizing a task. The most important improvements are:

1. One recognizable lease financial view, not a narrow view and a different full-width destination.
2. Separate charges, recorded payments, expected payments, credits and historical setup figures.
3. Turn prior-lease setup and corrections into focused tasks with an explicit consequence before save.
4. Give money received, costs, pending work and overdue accounts distinct icons and labeled colors.

Keep the accepted dashboards, unit allocation colors, inline corrections, private data boundaries and
existing money services. This is not a request for full accounting or automatic payment processing.

Read the [vocabulary and visual specification](financial-vocabulary.md),
[implementation proposal](financial-implementation.md), and
[original owner notes](financial-clarity-owner-notes.md). The owner’s
[Accounting Design Audit](http://10.60.0.227:8090/doc/accounting-design-audit-8ceuIRgYSF)
and its five original attachment references are preserved, not rewritten.

The [synthetic visual-example guide](financial-clarity/README.md) lists the five color/grayscale
examples and captures, with an explicit Outline asset-upload limitation.

## Method and confidence

**B** = authenticated rendered browser observation using disposable synthetic records; **S** = source
inspection, including forms, templates and services; **T** = isolated characterization test. A source
finding is not represented as a completed browser transaction. Severity P1 means financial
misunderstanding risk, P2 means workflow/density friction, P3 means local copy inconsistency. No P0
security, arithmetic or data-loss defect was established by this design audit.

Browser review used separate QA cookies, a test database and a safe mail backend. It visited the lease
workspace, full-width ledger, payment form and expense-recovery allocation, including the existing
read-only allocation step. No financial save, charge, reversal, upload or notification was performed
in the development portfolio. Desktop screenshots and a 390px phone review were synthetic.

## Prioritized findings

| ID / severity | Screen and current wording | Actual behavior and likely misunderstanding | Recommendation | Evidence |
| --- | --- | --- | --- | --- |
| F01 / P1 | Lease Rent & Payments and “Full-width ledger” | The same content partial is reached through different headers, sidebars and main-navigation selections. Operators can interpret these as different accounts. | One full-width financial reading surface, consistent lease identity and local navigation; preserve both existing URLs as compatible entry points. | B+S: lease workspace, ledger lease, lease workspace context |
| F02 / P1 | “Upcoming” beside Account balance | Lease `next_due_total` may be expected rent not posted; dashboard Upcoming charges is unpaid posted future charges. Same-looking figures have different populations. | Label unposted expectation “Next scheduled rent — not yet added to account”; label recorded future amounts “Upcoming charges — included in account balance.” Do not alter either calculation. | B+S: lease ledger content and next-due projection |
| F03 / P1 | “Paid in full” with no transactions | A zero derived balance says nothing about whether earlier activity was entered or cash received. The synthetic empty lease shows Paid in full and expected rent together. | Empty account: “No charges or payments recorded.” Paid account: retain Paid in full when recorded charges are actually covered. Preserve real zeroed/corrected-account distinctions. | B+S |
| F04 / P1 | “Post due charges,” “Not posted,” “nothing can be posted” | Posting creates ledger charges; it does not collect money, pay a bill, send a bank transfer or imply delivery of a notice. | Retain the recognizable Post charges term with a short consequence and count/date/amount review where necessary; say exactly what setup is missing. | B+S: ledger overview, lease ledger, charge generation |
| F05 / P1 | “Received before RHP,” “one settling payment” | Setup records historical receipts as one cleared payment; a negative opening balance is also represented by a cleared Payment. This can resemble cash newly received on the setup date. | Show “Historical setup” explicitly and do not infer bank cash movement. Investigate monthly cash-summary classification separately before changing service rules or historical records. | S+T: isolated $200 starting credit appears as $200 in monthly cleared payments |
| F06 / P1 | “Date received” alongside “Pending — the money is expected” | The same field asks for receipt date even when no receipt has occurred. Pending rows do not reduce the balance. | Label by state: Received on versus Expected on. Show pending as expected, never money received. Preserve the stored date and service semantics. | B+S: PaymentForm and payment services |
| F07 / P1 | “Reverse,” “Void,” “Mark cleared” | These correct or complete a recorded payment; they are not refunds or bank instructions. | “Undo recorded payment,” “Cancel expected payment,” and “Confirm payment received,” each with amount, tenant, resulting balance and no-transfer explanation. Retain technical labels in secondary history when useful. | B+S; correction actions source-reviewed, not submitted |
| F08 / P1 | Adjust charge: “What this does,” “Add the adjustment,” full-amount secondary submit | Direction and amount are easy to confuse with replacement total; the alternate submit posts a correction rather than merely filling a field. | Ask Reduce or Increase charge; show original, previous corrections, change and resulting total. Any quick-fill control must fill only, not unexpectedly save. Explicit review/confirm is separate. | S: AdjustmentForm, charge-adjust view/template |
| F09 / P1 | “Settle financial account,” “complete disposition” | Settlement locks operations; nonzero deposit currently blocks it. Copy can imply a deposit workflow or refund capability that does not exist. | Proposed “Close financial account” with secondary state “Settled.” Explain exact blockers; say “A security deposit is recorded; its return/deductions must be recorded through the move-out workflow before closure.” Do not offer nonexistent deposit actions. | S: settle template and settlement service |
| F10 / P1 | “Send the remaining monthly amount to…” | This selects which allocation absorbs the remainder. No money is sent. | “Assign the remaining monthly amount to…” with Unit/RHP names and calculated-recipient label. Preserve the explicit recipient and Decimal calculator. | B+S |
| F11 / P1 | “Repair expenses,” “Net tenant charges posted,” “Prepare tenant recharge” | Recorded cost and tenant liability are independent; neither proves a vendor was paid. | “Repair cost recorded,” “Charges added to tenant accounts,” “Charge a tenant for this repair.” Use a receipt/cost icon, not a payment-out arrow. | S: costs, recharge forms and signed review |
| F12 / P1 | End tenancy: “Position today,” signed amount “owed” plus credit “held” | A credit can be described as a negative amount owed and also held, rather than one clear credit balance. | One conditional “Account balance” or “Credit balance,” and “Charges after the move-out date” review. Preserve cancellation choices and existing proration boundaries. | S: lease_end template |
| F13 / P2 | Prior-lease setup renders both methods in one form | Method-specific inputs remain visible together; prose below the Save button explains what the task meant. | Choose Full history or Starting balance first, then relevant fields, then review effects. Plain forms must provide the same steps. Keep the separate calculator proposal out of implementation. | S: OnboardingForm, lease_onboard and onboard_lease |
| F14 / P2 | Lease edit: large explanatory paragraph and flat field list | Rules, dates, rent model and tenant membership compete for attention. “Nothing RHP invents” explains implementation rather than a manager task. | Group Location/term, Rent, Tenants; reveal only relevant rent inputs and keep eligibility warnings next to the affected choice. | S: LeaseForm and lease_form |
| F15 / P2 | “Stated rent,” “Rent now, as RHP reads the lease,” “NNN so far” | Ordinary contract amounts sound like internal interpretations; NNN is not expanded at each independent entry point. | “Rent amounts entered from the lease,” “Current monthly rent,” “Triple-net (NNN) amount history.” Keep contractual rent schedules and existing locks. | S: lease setup, rent schedule and NNN form |
| F16 / P2 | Allocation: read-only Bill details confirmation before every edit | Existing saved bills require a largely duplicated step; saved allocations are called “Unsaved allocation” before any edit. | Start existing-bill editing at allocations with a compact read-only bill summary. Distinguish Saved amounts from Proposed changes. Keep review and signed save. | B+S |
| F17 / P2 | Tall allocation ring before controls on a phone | The ring and legend consume most of the first viewport; editable amounts and remainder choice are below it. | Compact ring/summary on phones; recipient and first editable row earlier. Keep all labels, exact amounts and unit colors. | B: 390px allocation view |
| F18 / P2 | “Use size-based allocation” and “Split equally” replace all amounts | These are deliberate bulk replacements, unlike normal manual edits. | Keep the existing warning; add a clear replacement summary/confirmation for already-edited drafts in the proposal. Never silently replace unrelated manual values. | B+S; no arithmetic defect reproduced |
| F19 / P2 | Repair cost form combines “New expense,” correction target and direction | New costs and correction entries use the same technical controls, with instructions to infer the correct combination. | Separate Record repair cost from Correct recorded cost; use service-backed review with immutable originals. | S: CostForm, maintenance form and expense partial |
| F20 / P2 | Documents: “File a document,” “Filing against,” three link selectors | A user has to translate association language and understand visibility independently. | “Upload document,” “Related property / tenancy / tenant,” then an explicit Who can see this summary. Retain current association/visibility validation. | S: DocumentForm and document_form |
| F21 / P2 | Property/unit edit forms are mostly flat lists | Identification, photos, physical facts and service state receive equal visual weight. | Group Basics, Photos, Details and Service status; keep map help in a disclosure and consequential state changes separate. | S: forms and edit templates |
| F22 / P2 | Property clear button is immediate; other photo removals use checkboxes | Similar tasks have different save semantics; a photo action can discard unrelated unsaved edits. | Inventory each photo workflow, propose consistent Replace/Clear language and an unsaved-changes warning where a separate action navigates away. Do not undo the owner-approved immediate banner-clear behavior. | S: property, unit and tenant photo forms |
| F23 / P2 | Tenant access actions mixed with identity on legacy forms | Invitation/account-state consequences need stronger emphasis than routine contact context. | Retain people-first tabs; confirmations say who can sign in and what email will be sent. No new staff contact-edit capability. | S: tenant account form/views |
| F24 / P2 | Maintenance “Publish,” “audience,” internal-note controls | Publication is a privacy boundary, not just an editing mode. | Name the selected tenancy and “Share a copy with tenants”; keep internal note and conversation actions visibly separate. Do not merge audiences or copy attachments automatically. | S: PublishForm, UpdateForm, request sections |
| F25 / P2 | Announcement scope: blank Properties means all current tenancies | Empty selection has a broad consequence that a casual reader may not anticipate. | Explicit All current tenancies versus Selected properties, with the existing recipient review retained. This is presentation of existing targeting, not a new audience model. | S: DraftForm and publish review |
| F26 / P2 | Email failures/retry use uncertain-delivery terminology | Ordinary retries and ambiguous outcomes have different duplication risks. | Plain “Delivery failed” versus “Delivery outcome unknown”; retain the existing explicit duplicate-email warning and authorization recheck. | S: communication/maintenance retry pages |
| F27 / P3 | “Why,” “Say…,” “untick,” “for good,” “the property carries…” | Colloquial sentences are inconsistent with direct American-English task labels. | Use Reason, Enter…, clear/select, retained in history, and RHP share. Rewrite service validation/flash messages too, not only page headings. | S: domain forms and templates |
| F28 / P2 | Mostly text-only financial actions and status cells | Green is used for payment/credit cells; no consistent icon separates cash receipt from a noncash credit. | Use the proposed semantic icon/color matrix with textual type labels; preserve overdue status and unit allocation identity as separate dimensions. | B+S: ledger and allocation views |

## What is and is not a defect

Confirmed presentation/workflow problems: F01–F04, F06–F28 as evidenced above. They do not establish
an incorrect ledger balance. F05 is a **legacy representation/reporting risk**, not just copy: opening
credits and aggregated prior receipts are stored using Payment, so a cash-received interpretation may
be misleading. Do not silently exclude records by free-text reference or rewrite historical rows.
Any accounting/reporting classification correction needs a separate approved, tested scope.

## Competitor evidence — patterns, not a universal standard

| Source | Verified pattern | RHP recommendation / limit |
| --- | --- | --- |
| [TenantCloud getting started](https://support.tenantcloud.com/en/articles/11897075-let-s-get-started) | Money In/Out groups, transaction statuses, and separate financial views. | Borrow clear direction and status cues, but do not imply RHP can pay vendors or refund deposits. |
| [TenantCloud demo, accounting chapter](https://www.youtube.com/watch?v=88HxwrktOOU&t=355s) | Transcript 5:54–6:22 distinguishes transaction details, balances and recurring transactions; owner screenshot shows green/red direction controls. | Separate current account activity from future schedules. Historical video is a design reference, not proof of current feature parity. |
| [Buildium charge guide](https://help.buildium.com/hc/s/article/How-do-I-add-charges-to-a-tenant-s-lease-ledger-1557495015862) | Charge records money owed; one-time and recurring charges are separate, with posting as an account event. | Keep charge/payment distinction and explain Post; do not label every charge an actual receipt. |
| [Innago FAQ](https://innago.com/faq/) | Invoices/ledger and manual recording of offline payments coexist. | Keep manual check/cash recording recognizable without suggesting RHP processed the payment. |
| Rently | Product not identified; several unrelated products share the name. | Unverified; no invented comparison. Earlier design records also name Rentler, which is not assumed to be this reference. |

These are established product examples, not a claim that one interface or exact term is an industry
requirement. RHP's one-lease financial scope is retained; no combined person-level account is proposed.

## Coverage and limits

Audit-specific evidence on October 20: **16 passed** across the characterization, example-contract,
quote-reflow protection, existing Design-tooling and document-contract tests. Lint and Django/deployment
checks passed on the audit branch. No application code changed. The disposable authenticated browser fixture
completed **1 passed**, with test data torn down. Phase 9 preservation gates ran independently:
**1,094 passed, 4 skipped**, plus lint, checks/deploy checks, CSS build, migration checks and smoke.
An earlier full-suite attempt terminated with signal 143; only the successful rerun is counted.

All five exported example pages were visually inspected in color and grayscale, with no clipping
or text overlap. The Outline upload chooser timed out through both supported controls; documents
are published, but new visual assets remain local pending a working permitted upload path.

| Area | Reviewed | Remaining verification |
| --- | --- | --- |
| Lease financial paths, payment entry | Source + rendered desktop | Populated charge/reversal screens browser review before implementation |
| Prior activity, charge correction, ending/settlement | Form/template/service source | Full guided flow is a proposal, not an implemented or usability-tested feature |
| Expense recovery | Source + rendered details/allocation; phone; keyboard Menu | Script-blocked calculator and 200% zoom not re-exercised in this audit |
| Repair expenses and tenant charges | Form/template/service source | Manager expense/recharge interaction review before rollout |
| Properties, units, tenants, documents | Forms, contextual templates and permission boundaries | Full browser inventory for each role/state before implementation |
| Maintenance and communications | Forms, audience/privacy controls, confirmations/retry source | Do not claim all possible conversations/announcements were browser-tested |
| Visual recommendations | Synthetic diagram examples and measured text colors | Production accessibility, actual print dialog and owner comprehension testing remain pending |

The audit does not change live data, financial services, application templates, routes, permissions,
models or migrations. Recommendations must pass the separate implementation review. Original owner
screenshots remain in Outline; new local captures contain synthetic data only.

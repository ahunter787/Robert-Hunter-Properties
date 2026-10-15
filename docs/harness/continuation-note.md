# note

```yaml
kind: harness_continuation
snapshot_date: 2026-10-14
workspace: /home/captain/Code/RHP
branch: rhp-charge-lifecycle
git_state: dirty_uncommitted
commits_authorized: false
pushes_authorized: false
application_is_live_system: false
target_release: 2027
scope_of_this_note: engineering_only_no_credentials_or_tenant_records
```

## Resume context

The owner approved the RHP Lifecycle and Plain-Language Interface Plan. Implementation and verification
are complete in the working tree, pending owner review and authorized commits. Do not interpret the older
read-only audit request as current: the later implementation request authorized the changes. Preserve all
working-tree changes. Re-read AGENTS.md, README.md, docs/roadmap.md, docs/extensions.md, phase records,
ADR-020, ADR-021, and ecosystem/AGENT-BRIEFING.md before continuing. Use the project-ecosystem skill for
Plane/Outline work. Never stop, prune, or reconfigure ecosystem containers. No subagents were requested.

## Approved decisions

- Occupancy: LeaseStatus DRAFT / ACTIVE / ENDED. Financial account: LeaseAccountStatus OPEN / SETTLED.
- Settlement requires ended occupancy, zero derived balance/credit, no pending payment, and no nonzero
  recorded deposit until P4-E5 supplies complete deposit disposition.
- Reopening requires a reason, changes only financial account status, preserves ENDED occupancy and end
  facts, and never restarts recurring rent. Every financial service mutation refuses settled accounts.
- Managers have portfolio-wide operational authority including corrections, schedules, expense
  recoveries, tenant invitations/activation, settlement, and reopening. Role changes stay superadmin-only;
  Django administration, configuration, and destructive deletion remain privileged. Property-assigned
  hired managers remain a stretch goal.
- RHP-owned properties only. General-ledger/property accounting is future E10, not implemented here.
- Phase 11 approved but optional for 2027: one-time ACH and ACH autopay using hosted/tokenized bank
  linking. No payment provider or bank credentials added. PayPal/card fees are not a priority.
- Final-product language: Rent & Payments; Expense recoveries; Post due rent charges; Record payment;
  Add one-time charge; Current/Upcoming; Account balance; Credit balance; Paid in full; Settled account;
  Triple-net (NNN) on first use; tenant; American English; Mon D, YYYY dates.

## Implemented state

Lease account status, settlement metadata, ended-account DB constraint, settle_account/reopen_account,
manager operational permissions, service locks, due-now/upcoming/account-balance summaries, ledger
projection, public homepage, removal of UI development placeholders, portal copy updates, and governing
records are implemented. Ledger entries remain immutable and balances derived.

Owner refinement: ledger status colors restored; adjustments nested beneath original charges, showing
original amount and correction date/amount/reason. Running balances use corrected amounts as of today;
they are not historical-at-time balances. Payment reversals remain explicitly linked entries. Tenant
expense recoveries group under Property charges with actual charge names.

Uploaded lease documents now have lease_document_name display metadata. New uploads retain their original
filename unless staff supply a title. Randomized private storage paths remain unchanged. Staff detail,
edit widget, tenant lease, and download response use readable names and permission-checked routes.
Legacy names cannot be reconstructed automatically; staff must supply them. The owner-supplied display
name for an existing development document was entered without changing its content or storage path.

The confusing prior-activity sentence now says earlier charges/payments have not been entered and offers
recreating charges plus prior payments or an opening balance. Expense-recovery bill note uses the owner's
requested phrasing, with grammatical possessive "its". Mobile ledger scrolling is contained within its
table wrapper. CSS rebuilt; base stylesheet URL includes version query 20261014 to invalidate stale cache.

## Migrations

- audit.0006_alter_auditevent_action
- audit.0007_alter_auditevent_action
- leases.0006_lease_account_status_lease_settled_at_and_more
- leases.0007_alter_leaseonboarding_method_alter_rentperiod_origin
- leases.0008_alter_lease_billing_start_date_and_more
- leases.0009_lease_lease_document_name_alter_lease_lease_file
- responsibilities.0002_alter_propertyresponsibility_is_active

All seven applied to development DB. Legacy SETTLED leases migrate to ENDED + OPEN for review with system
audit events because deposit disposition was unproven. Rollback preserves those append-only audit events.

## Verification already run

- make test: 739 passed, 172.85 seconds (2026-10-14).
- Final focused suite: 70 passed, 18.61 seconds, covering final statement grouping/date wording,
  onboarding, migration audit preservation, and product-copy guard.
- make lint: passed; make check with reachable development DB: passed; make check-deploy: passed.
- makemigrations --check --dry-run: no changes; migrate --check: passed; git diff --check: passed.
- Runtime smoke: make up, wait-ready, health; application and database healthy at localhost:8000.
- Browser review at 1440x900 and 390x844: public home, staff dashboard, staff lease/ledger, tenant
  dashboard/lease/payments. Ledger horizontal overflow fixed and verified. Synthetic review accounts,
  lease, unit, and property were removed. Browser viewport reset and temporary tab closed.
- Outline/Plane publication and make -C ecosystem verify passed before this documentation-only update.

These are historical results; rerun relevant checks after future edits. No application code changed in
the follow-up task to improve Plane descriptions and publish this note.

## Remaining work and workflow caveats

1. Owner review, then explicit authorization before commits/pushes/merge. The requested sequence was
   lifecycle merge followed by a separate presentation branch. Both units currently coexist uncommitted
   on rhp-charge-lifecycle; branch/commit separation has NOT been completed. Preserve the working tree and
   arrange the reviewable units before merging when authorized.
2. Do not mark P4-E5 complete: deposit disposition, deductions, final statements, and forwarding address
   are still pending. P4-E6 evidence-backed post-tenancy charges waits for Phase 6; reopening an account
   never provides a workaround to bill rent on ended occupancy.
3. Phase 6 remains next; do not start later-phase features while a phase is open. Renewal, month-to-month,
   automatic expiration, concessions, and per-property manager assignments retain their recorded status.
4. Keep historical staff notes and audit text intact even if they contain old development wording. The
   product-copy guard targets static rendered product copy, not a license to rewrite financial history.
5. New document name input/widget lives in apps/leases/templates/components/lease_document_input.html
   because Django's widget renderer uses app template directories. Streaming response.close() closes
   test DB connections, so any additional requests in that test must precede closing the response.
6. Docs publisher uses git ls-files. New Markdown files need git add -N (intent to add only) before
   publication; this is not commit authorization. ADR-021 already has intent-to-add status.
7. Existing ecosystem extension sync publishes only a short register summary. This follow-up enriches
   Plane descriptions directly from the authoritative extension sections without changing plans/states.
   A future register-row change followed by plane-sync can overwrite that enrichment. Reapply the detailed
   source description if it does. A durable publisher improvement is a separate ecosystem change requiring
   scope authorization under the skill. Ecosystem code was not changed in this task.
8. Lifecycle question/defect tickets retain owner discussion and historical descriptions. A current-status
   annotation is added rather than overwriting prior answers. No new owner answers are inferred.

## Ecosystem continuation

Description-audit receipt for this follow-up: 22 Plane descriptions updated and verified by read-back.
Mirrored Phase 1 and 2 items were republished from corrected source records. Extensions E1–E10 were
expanded from their source sections (E9 also includes ADR-021). Ten manually created lifecycle items
received a current-status annotation with their previous discussion preserved. Names, states, priorities,
comments, and owner answers were not changed. The plan-format tests passed (9 tests). Outline read-back
confirmed this document's title is "note" and it contains the branch and harness-continuation marker.

```yaml
outline_note_path: /doc/note-qLEcv686K7
plane_updated_sequence_ids: [92, 93, 104, 105, 106, 107, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124]
extension_enrichment_strategy: source_derived_description_only_patch
manual_ticket_strategy: current_annotation_plus_preserved_history
one_shot_enrichment_script: /tmp/rhp-enrich-plane-descriptions.py
script_is_durable_repository_tooling: false
```

Repository plan remains authoritative. Use make -C ecosystem docs-sync ARGS=--apply and plane-sync
ARGS=--apply for mirrored records, then verify. Engineering collection: RHP Engineering. Plane project:
RHP / RHPDEV. This source file publishes as Outline document title "note" and can be found by searching
that title or source path docs/harness/continuation-note.md. No secrets belong in this note or the wiki.
```
resume_order: inspect_git_then_read_records_then_review_existing_diff
do_not_repeat: already_completed_implementation_or_synthetic_fixture_creation
do_not_infer: commit_permission_or_new_phase_permission_or_provider_selection
```

# RHP modifications from the TenantCloud / TurboTenant study

**Status:** E15 and E16 approved; E17 approved with the owner's narrowed scope (proof intake and manager
decision only, no automated screening). Implementation has not yet shipped when this line is read on a
feature branch; the kernel itself is complete in development.

This is the second half of the task the accounting kernel was built for: the kernel is
feature-complete in development (B1–B5, 1,315 passing tests at the time of writing), so the
TenantCloud/TurboTenant research is now used to plan the remaining product work rather than to
guide the ledger.

The evidence is the workspace study at `tenantcloud/findings/`, especially:

- `11-messaging-study.md` — TenantCloud's first-party Messenger and the live TurboTenant chat kit;
- `12-tenant-timeline-study.md` — TenantCloud's per-entity timeline versus TurboTenant's missing one;
- `14-tenant-side-study.md` — the live renter portal, role-gated chat controls and notification settings;
- `15-renters-insurance-study.md` — the live insurance requirement, upload, review and reminder cycle;
- `10-capability-parity.md` and `07-rhp-applicability.md` — the adopt/adapt/avoid decision table.

Those findings are observations of another product, not instructions. RHP keeps its own rules:
server-rendered Django, PostgreSQL, `Decimal` money, append-only history, server-side authorization,
tenancy-scoped queries, no new dependency without approval. Nothing here is copied wholesale.

## 0. Pre-go-live basis

The accounting kernel is **pre-go-live in development**: B1–B5 are implemented and gated by 1,315 passing
tests, clean lint/check/deploy checks and applied migrations. "Pre-go-live" here means the kernel's
functional scope is complete and controlled; it does not mean Robert's production data exists. The
remaining operational items are the owner onboarding questionnaire, opening/setup data, manual bank-match
and bank-feed follow-ups, a first-class write-off action and the go-live screen walk. None of those
changes the ledger contract this plan builds on.

## 1. What the kernel baseline gives us

The accounting kernel now has a complete double-entry ledger with controls that this plan builds on:

| Capability | RHP state |
| --- | --- |
| Chart, immutable journals, source keys | B1, `apps/accounting` |
| Tenant AR, receipts, opening credits, adjustments | ADR-028 / B1 hooks |
| Vendor bills/AP/payments, deposit movements | B2 |
| Bank accounts, CSV import, reconciliation | B3 |
| Trial balance, statements, aging, Schedule E, deposit register | B4 |
| Closing, owner contributions/draws, CSV and plain-text exports | B5 |

The product work below must reuse those records and authorization rules. It must not invent a second
money model, a second timeline arithmetic, or a second document store.

## 2. Gap summary

| Area | What RHP already has | What the study shows is missing | Decision |
| --- | --- | --- | --- |
| Messaging | E12: private/shared tenancy conversations, append-only messages and attachments, read positions, work state, email delivery, announcements, move-out follow-up | Quick replies, archive/mute, transcript export, shared-media index, staff-only internal notes, maintenance-request context | **E15** — adopt the operational subset; keep RHP's authorization and polling |
| Tenant history | Audit events, ledger activity, maintenance updates/comments, documents and message history on separate screens | One date-grouped, actor-attributed timeline per tenancy, with manual staff activity and explicit tenant visibility | **E16** — new read model and manual notes |
| Renters insurance | No lease requirement, proof record or workflow | Requirement toggle, tenant proof upload with policy dates, persistent status, staff review, warnings/reminders, timeline events | **E17** — compliance-only proposal, conditional on the owner amending the written non-goal |

## 3. E15 — messenger enhancements

### 3.1 Current state

`apps/communications` already provides conversations fixed to one lease, named participants,
private/shared visibility, append-only messages and private attachments, per-user read positions,
Needs RHP/Waiting/Handled work state, email delivery attempts, announcements, and scoped move-out
follow-up. Tenant routes are under `/account/communications/`; staff routes under
`/manage/communications/`. ADR-024 explicitly excludes typing/presence, read receipts, SMS, push and
a realtime chat service.

The study's own comparison (`11-messaging-study.md`) lists the useful gaps as quick replies,
per-conversation archive/block, chat export, shared media, an optional maintenance-request thread, and
a staff-only internal note. It also shows the tenant side must **not** expose owner-only tooling:
TurboTenant hides Quick Reply, Archive, Block and Export from the renter.

### 3.2 E15 implementation status

Implemented in development on `rhp-e15-messenger`: staff quick replies, per-user archive/mute,
conversation transcript exports (text/CSV), shared-media index and staff-only internal notes, with tests
for manager/tenant/other-lease isolation. The optional maintenance-request context remains deferred; it
is not required for the approved daily-inbox value.

### 3.3 E15 increments

#### E15.1 Quick replies (staff only)

- New `QuickReply` model in `apps/communications`: `label`, `body`, optional `property` scope,
  `created_by`, `created_at`, `is_active`, immutable body versions or append-only revisions.
- Staff-only list/create/edit/disable screens under `/manage/communications/quick-replies/`.
- A staff composer button inserts the template body into the textarea. The user can edit before send;
  the sent `Message` remains the authoritative immutable content.
- No tenant route, no tenant API, no tenant-side template list. This matches the live role split.
- Tests: manager create/use/disable; tenant 403; body appears in composer only when staff; no template
  data in tenant responses.

#### E15.2 Archive and mute (per staff user)

- `ConversationArchive` (`conversation`, `user`, `archived_at`) with one row per user/conversation.
- `/manage/communications/?archived=1` lists archived threads for that user only; archiving never
  freezes, deletes or hides history from the tenant or other staff.
- A **mute** flag on the same per-user record suppresses future message email for that user; it does
  not suppress the in-app unread state. If a quiet-hours/notification-preference feature is added later,
  this is its natural home.
- Tests: per-user isolation, unarchive, tenant never sees archive state, email delivery respects mute,
  archive does not alter `Conversation.state`.

#### E15.3 Transcript export

- Staff action on one conversation: download a text/CSV transcript of messages and attachment names.
- Reuse the export discipline from B5: period/conversation scope, checksum in the response header or an
  `ExportBatch`-style audit row, manager-only, no raw storage URL in the transcript.
- Attachments are referenced by authorized download links, never embedded bytes; a tenant requesting
  their own transcript is a later, separately-authorized feature.
- Tests: manager export, tenant 403, attachment names not files, checksum/audit, no cross-lease rows.

#### E15.4 Shared-media index

- A conversation detail panel/section grouping existing `Attachment` rows by file type
  (images / PDFs / other) with authorized download links.
- No new storage; query is restricted to the conversation's messages and the same download view.
- Tests: only that conversation's attachments; tenant sees only tenant-visible messages; deleted files
  absent; no orphan rows.

#### E15.5 Staff-only internal notes

- New append-only `InternalNote` (conversation, author, body, created_at) or a visibility field on
  `Message`; the separate table is preferred so tenant message queries cannot accidentally include it.
- Staff-only UI thread; no tenant route, template, API, export or email. Notes appear in E16's staff
  timeline (and optionally in the conversation export) but never in the tenant timeline.
- Tests: tenant cannot read/write/search/export notes; staff-only rendering; history immutable.

#### E15.6 Maintenance request context (optional, after E15.1–E15.4)

- Add an optional `maintenance_request` FK on `Conversation` and a "Message about this request" action
  from the maintenance detail. One conversation still has one lease; the link is a filter/context, not
  a merge of maintenance updates into chat.
- Tests: link preserves tenancy authorization; no permission change on the maintenance record.

### 3.4 E15 acceptance and exclusions

- One extension branch; no change to immutable message semantics; no new dependency.
- Tests cover authorization first (tenant/other staff/other lease), then UI, then email behavior.
- **Excluded:** typing/presence, read receipts, reactions, threads inside threads, voice/video, SMS,
  external chat SDK, realtime service, e-sign/notices. Those remain outside ADR-024's owner decisions.

## 4. E16 — tenant timeline

### 4.1 Why this is differentiator, not parity

TenantCloud has per-entity timelines including the Contact/tenant feed; TurboTenant has none unified.
RHP already has the raw facts but not one view. The value is an **authorized read model**, not a second
audit table or a copy of the audit rows.

### 4.2 Event sources (derive; do not re-implement money)

| Source | Existing record | Timeline event |
| --- | --- | --- |
| Lease | `Lease` status/start/end, onboarding, settlement | created, upcoming, active, ended, settled |
| Money | `Charge`, `Payment`, `FundsApplication`, `Charge` adjustments | charge raised, payment received/cleared, correction, reversal, opening credit applied |
| Maintenance | `MaintenanceRequest`, updates/comments, `Cost` | created, status changed, note, cost recorded |
| Documents | `Document` | added, visibility changed |
| Communications | `Conversation`, `Message`, `Announcement` recipients | conversation started, message sent, announcement published |
| Insurance (after E17) | `InsuranceProof` | required, proof uploaded, review result, removed, expiring |
| Manual activity | new `TimelineEntry` | note, task, call, meeting with optional attachment |

Money events render the ledger's own figures and links; the timeline never computes a balance.

### 4.3 Data model and routes

- New `apps/timeline` (`TimelineEntry` manual activity, service/read model). `TimelineEntry` fields:
  `lease`, `kind` (`NOTE`, `TASK`, `CALL`, `MEETING`), `body`, `occurred_at`, `author`,
  `visible_to_tenant`, optional `document` (staff-only evidence, reusing the private document store),
  `created_at`. Edits create a new entry/revision; no deleted history.
- No materialized event table for system facts in v1. A single service `timeline_for(lease, viewer)` merges
  and sorts the sources, with stable keys and pagination. If performance later requires a materialized
  read model, it is additive and can be rebuilt from the sources.
- Staff route `/manage/tenants/<id>/timeline/` (or lease page tab); tenant route
  `/account/timeline/` scoped to their active/ended tenancy. Filters: event type, author, shared-only
  for tenant; date grouping; pagination; empty state.
- Manual entry UI is staff-only. Tenant sees only `visible_to_tenant=True` manual entries plus
  tenant-visible system events; internal notes never cross the boundary.

### 4.4 Implementation status

Implemented in development on `rhp-e16-timeline`: `apps.timeline` with an append-only manual-activity
model, a read service merging lease/ledger/maintenance/document/message events, staff and tenant routes,
tenant-visibility filtering and tests for tenant isolation, manual sharing and staff access. Source links,
filters and a materialized read model remain later refinements; the read model is not materialized.

### 4.5 Rules

- Authorization is a query scope, not a template check: tenant timeline uses the same lease membership
  scope as documents and communications.
- No cross-tenancy search; no platform/admin events; no e-sign/screening events.
- System events are immutable; manual entries are append-only with a visible author/date.
- Every rendered event links to the authorized source record (or no link when the viewer cannot see it).
- Tests: tenant sees own tenancy only, other tenant's timeline 403/404, staff sees portfolio, hidden
  notes excluded, filters/pagination, money event figures equal the ledger, no N+1 on the timeline page.

## 5. E17 — renters-insurance proof (approved, narrowed)

### 5.1 Approved scope

The owner approved a deliberately small feature and drew the distinction clearly:

- RHP **requires** renters insurance as a lease obligation and warns while proof is missing.
- The tenant uploads proof; a manager reviews it. RHP does **not** screen the policy automatically and
  is **not responsible for insurance advice, sales, quotes or underwriting**.
- The tenant-visible state is three-state:
  1. **Missing** — no proof has been supplied; a warning and onboarding to-do are shown.
  2. **Submitted — pending manager review** — proof exists and waits for a human decision.
  3. **Reviewed — accepted or rejected** — the manager's decision is visible, with the rejection reason
     when rejected.
- The feature contributes to the tenant timeline and the onboarding checklist.
- A future automatic screening step is explicitly out of scope for the first go-live.

This resolves the earlier non-goal conflict without requiring an insurance product: RHP stores and shows
the evidence and the manager's decision. No partner funnel, AI audit, scoring or policy advice is built.

### 5.2 Data and state

- `Lease.renters_insurance_required` (default `False`), set during lease setup/onboarding.
- `InsuranceProof` in `apps/documents` (or a small `apps/insurance` app): lease FK, `document` FK to the
  existing private `Document` store with a new `INSURANCE` category, submitted_by/at, optional policy
  start/end dates, `status` (`SUBMITTED`, `ACCEPTED`, `REJECTED`), `reviewed_by`, `reviewed_at`,
  `review_note` (required when rejected), and an append-only replacement link.
- The **lease-level tenant state** is derived: accepted current proof → reviewed/accepted; a submitted
  proof → pending; no proof → missing; rejected latest proof → reviewed/rejected with reason. There is no
  separate fourth "expired" state in this first slice.
- One current proof per lease; a new upload supersedes the previous one by append-only history, and the
  manager decision applies to that submission.
- Tenant cannot edit a submitted proof; a replacement is a new submission. Staff decisions are immutable
  once recorded; a correction is a new review event, not an edit.

### 5.3 Screens and behavior

- Tenant `/account/insurance/` (and dashboard to-do): requirement copy, three-state chip, upload/replace
  form (PDF/JPG/PNG + optional policy dates), rejection reason when rejected. No quote/sales link.
- Manager lease/tenant tab: proof list, private download, Accept/Reject action with note; no automated
  screening result to "override".
- Staff dashboard/lease warning while a required proof is missing or rejected. Reminder sending reuses
  the existing communications/delivery path, recorded as an attempt.
- Onboarding checklist: "Renters insurance proof" item shown when the lease requires it, clearing only on
  an accepted proof (or an explicit manager waiver outside this slice? No — this slice has no waiver;
  decide later if needed).
- Timeline (E16) events: requirement set, proof submitted, accepted, rejected, replaced.
- File access uses the existing private document serve view and tenancy authorization; no public URL.

### 5.4 Tests and exclusions

- Requirement off means no warning and no tenant to-do; requirement on and no proof shows missing.
- Tenant sees only own lease; staff sees portfolio; download requires authorization.
- Upload creates SUBMITTED; manager Accept/Reject writes immutable review; rejection needs a note; tenant
  sees persistent decision and reason.
- Replacement history is append-only; onboarding item and timeline events follow the decision.
- **Never in this slice:** automatic screening, policy OCR/AI, insurance sales, partner quotes,
  underwriting, premium collection, a fourth expiry/waiver state.

## 6. Sequencing and ownership

| Order | Workstream | Why this order | Branch |
| --- | --- | --- | --- |
| 1 | **E15.1 Quick replies** | Smallest, independent, immediately useful in the existing inbox | `rhp-e15-messenger` |
| 2 | **E15.2 Archive/mute + E15.4 shared media** | Same app; low schema risk; improves daily inbox | same branch |
| 3 | **E15.3 Export + E15.5 internal notes** | Export depends on the message query; notes are the bridge to E16 | same branch |
| 4 | **E16 timeline** | Consumes E15 message events plus existing ledger/maintenance/document facts | `rhp-e16-timeline` |
| 5 | **E17 insurance proof** | Approved narrow scope; timeline should already exist for its events | `rhp-e17-insurance` |

Each extension follows the repository rule: one extension = one entry = one branch, tests before UI,
full gate (`make test`, `make lint`, `make check`, `make check-deploy`), docs and Plane published, no
push/deploy without instruction.

## 7. Smaller study items deliberately not in this plan

The study also suggests a rent roll, lease-expiration report, report settings, global search, Google
Sign-in, ICS calendar and payment-provider work. Some are already covered by B4 reports; the remainder
are separate proposals (`E13`, `E14`, Phase 10) and are **not** mixed into the messenger/timeline/insurance
branches. The explicit non-goals remain: listings, applications, screening, e-sign, lease-template
library, marketplace/lead generation, insurance **sales**, realtime chat, GraphQL, microservices.

## 8. Definition of done for this planning pass

- This document is published and linked from the extension register.
- E15, E16 and E17 are registered as **Approved** with their scope boundaries.
- E17 records the approved narrow three-state scope and the no-screening boundary.
- Plane mirrors the approved items; implementation branches are named in the register.
- The implementation order, acceptance criteria, tests and exclusions are specific enough for an
  engineer to start E15 without re-reading the whole study.

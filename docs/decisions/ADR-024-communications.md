# ADR-024: Announcements and tenancy-scoped messaging

- **Status:** Accepted for implementation
- **Date:** 2026-10-19
- **Phase:** 8 / E12; `rhp-8`, after accepted E11 local baseline `1e906b6`.

## Decision

One Communications workspace, after Maintenance and before Documents, contains Messages and
Announcements. Managers/admins operate a shared portfolio inbox; workers have no access. Tenants
contact RHP, not an individual manager. Use the approved full-color Operations Desk shell.

Conversations have a subject, one lease, fixed named participants and private/shared visibility.
Private defaults to one tenant plus RHP. Shared snapshots co-tenants explicitly before sending.
Tenant membership changes permanently freeze shared history; a different household starts a new
thread. Move-out makes ordinary threads read-only. Managers can explicitly enable/revoke scoped
follow-up, recording a reason; membership-frozen group history cannot be unfrozen. Settlement has
no effect on communications. History remains readable to recorded participants with active accounts.

Messages and attachments are append-only; corrections are subsequent messages. Work status is
Needs RHP reply, Waiting for tenant, or Handled. Reading never changes work status. New eligible
tenant replies reopen handled work. Per-user read positions move only forward and only by explicit
POST identifying a rendered message. Subject/tenant/property/unit/work/unread lookup is scoped.

Announcements have mutable staff-only drafts and immutable published revisions. Managers publish,
correct and withdraw; corrections/withdrawal require reasons. Publication review signs the exact
audience and content and rejects stale confirmations. Snapshot named people and leases using
current occupancy, not a future dynamic property query. Expired/withdrawn notices leave the active
feed but retain authorized history. Important versions email recipients; routine ones are portal-only.
No acknowledgment, public discussion, scheduled sending or announcement attachments. Follow-up is
a private conversation linked to the announcement and selected recipient tenancy.

## Implementation boundaries

Conventional Django/PostgreSQL records: conversations/participants, append-only messages and private
attachments, per-user read positions, lifecycle events, immutable announcement versions/recipients
and durable notification attempts. Integer audit identities and UUID public routes are not permission.
Tenant `/communications/`, staff `/manage/communications/`; mutations are CSRF-protected POSTs.
Membership lifecycle hooks permanently freeze existing shared threads; send-time eligibility and
lease/conversation locks protect races. Maintenance records and permissions remain unchanged.

Allow JPEG/PNG/WebP/PDF, ten files per message, existing per-file limit, randomized storage names
and readable downloads. Require subject and text or attachments, escape text, retain unsuccessful
composer text. Unique actor/composer tokens bind retries to payload fingerprints. Limit send attempts
per user in PostgreSQL (default 30 in five minutes). No new dependency or cache service.

Plain forms are complete. Poll the active thread every 15 seconds only while visible, without
overlapping requests, replacing the composer or advancing reads past rendered messages. Preserve
scroll/focus and page boundaries. Lists/history are paginated.

Persist notification intent in the write transaction; dispatch after commit. Tenant messages alert
managers and other tenant participants; staff messages alert tenant participants, never the sender.
Use neutral portal-link emails and isolated recipients. Recheck authorization at delivery/retry.
Recorded SENT deliveries never resend. Persist STARTED attempts before contacting SMTP: abandoned
attempts are ambiguous, and explicit retry requires a duplicate-delivery warning. No exactly-once
SMTP delivery, delivery-proof, legal notice or emergency-dispatch claim.

## Owner answers and exclusions

Owner selected in chat: private + shared; manager-enabled post-move-out replies; publication snapshot;
important-only notice email; full manager notice authority; no acknowledgment; freeze old shared
threads on membership changes; subject-based work; one Communications navigation destination.
These supersede earlier shared-only/admin-only withdrawal recommendations.

No native app, push, SMS, inbound mail, cross-tenancy groups, typing/presence, read receipts,
automatic retry worker, accounting, payment or reporting feature. No Phase 8 commit/merge/push/deploy
without subsequent instruction. Existing financial and maintenance rules remain unchanged.

The owner subsequently accepted Phase 8 and explicitly authorized local commit/merge after replacing
the interface term “scoped follow-up” with **Allow messages after move-out**. This is a presentation
correction only: internal identifiers, authorization, reasons and immutable history remain unchanged.
No push or external deployment was authorized. Phase 9 is planning-only until separately approved.

## Verification

Test roles/forged IDs, co-tenants/new occupants/move-outs, explicit follow-up, attachment privacy,
snapshot notices, stale reviews, versions/withdrawal/expiration, concurrent sends/reads, duplicate
tokens, rollback/file cleanup, limits and failed/ambiguous email retries. Browser QA uses disposable
data, separate cookies and safe mail, including keyboard/plain forms. Run full gates/migrations/smoke;
publish and verify engineering/Plane records. Implementation results belong in the phase record.

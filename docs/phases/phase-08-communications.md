# Phase 8 — Communications

**Status:** Complete — owner accepted for local merge
**Milestone:** 5 — Communication and an operational dashboard for the RHP team
**Specification:** `docs/harness/master-spec.md`, `PHASE 8 — COMMUNICATIONS`
**Extension:** E12 / P8-E1 — tenant–RHP messaging, scope approved October 17, 2026.
Implementation authorized October 19, 2026 after E11 local baseline `1e906b6`; branch `rhp-8`.
Governing decision: [ADR-024](../decisions/ADR-024-communications.md).

## Scope as specified

Lightweight property communication, announcements first: a water shutoff, parking maintenance, an
inspection notice, a holiday schedule, an office closure. An announcement targets everyone or one property,
appears only to the intended tenants, disappears from the normal tenant view when it expires, and an
important one can be highlighted. The owner has now approved extending this phase with saved
tenant–RHP messaging, attachments, unread indicators, email notifications and modest open-page
refresh. No native mobile app or push-notification service is included. Announcements remain
one-way; asking about one starts a private conversation rather than a public comment thread.

### E12 / P8-E1 — capability and functionality

**Messaging**

- Current tenants and managers can start a conversation and send replies. Tenants contact **RHP**,
  not a manager's personal account; portfolio-wide managers/admins can handle the shared inbox.
  Identify the actual author on every message. Maintenance workers receive no general inbox access.
- Associate each conversation with its tenancy and property/unit context. Persist explicit tenant
  participants; membership changes must never silently expose prior messages to new occupants.
  Private defaults to one tenant; shared conversations explicitly snapshot co-tenants.
- Retain chronological message history with author and server timestamp. Sent content is not silently
  overwritten or deleted; corrections are new messages. Do not add destructive deletion controls.
  Administrative audit facts remain distinct from tenant-readable conversation content.
- Accept protected attachments using existing validation/private-serving utilities, readable display
  names and randomized storage names. Initial allowlist: JPEG, PNG, WebP and PDF, with the
  existing per-file upload limit and at most ten files per message. Never expose storage URLs.
- Track unread state per user, using a monotonic last-read position. One co-tenant reading does not
  mark another's messages read. Provide unread counts and staff unread/answered-work indicators
  without prescribing their placement or visual treatment. Reading is not proof of understanding.
- Provide paginated conversation history and basic conversation lookup by tenant/property/unit.
  No cross-tenant search exposure or full-text message-search platform is required.
- Prevent accidental duplicate sends on retries. Validate content and attachment limits server-side,
  escape message text, and impose reasonable send/upload limits. Preserve unsuccessful composer
  input so ordinary errors do not lose a tenant's message.
- Link a conversation to its originating announcement when applicable. Maintenance conversations
  stay on their requests: do not create dummy maintenance requests or duplicate their messages in
  general chat. General messaging does not grant entry permission, create repair assignments or
  change financial obligations.

**Announcements and private follow-up**

- Publish to one or selected properties, or all eligible portfolio tenancies, with title, body,
  publication time, optional expiration and importance. Eligibility and publication permissions
  must follow the owner answers below. Show the proposed audience/count before publishing.
- Keep expired announcements out of the active feed while retaining authorized history. Withdrawal
  and corrections preserve author/time/reason and the original audience; no silent history rewrite.
- “Contact RHP about this announcement” creates or opens an appropriately scoped private conversation,
  not a property-wide reply thread. Other tenancies cannot see replies, identities or attachments.
- Do not include public comments, likes, reactions, view-count analytics or enforced acknowledgment.
  An announcement is a portal communication, not a promise of legal notice delivery or emergency dispatch.

### Technology and delivery boundary

- Add a conventional Django communications app with PostgreSQL models, services, forms and
  permission-scoped views. Suggested records: Conversation, Participant, Message, Attachment,
  ReadPosition, Announcement, AnnouncementRecipient, Notification and NotificationAttempt. Names and
  precise schema belong in the implementation ADR. Every model change requires a migration.
- Use internal IDs compatible with the audit trail and UUID public conversation/attachment identifiers.
  UUIDs do not replace authorization. Scope every list, detail, send, read-state and download operation.
- Reuse existing identity, tenancy context, mail configuration, file validation and audit utilities.
  Phase 7 supplies patterns, not a drop-in messaging backend: its Update, Attachment and Notification
  rows are request-specific and its notification recipient logic is tenant-directed. Adapt deliberately
  without changing existing maintenance visibility or leaking costs/internal notes.
- Persist message/publication and notification intent atomically. Notify authorized tenants of staff
  replies and managers of incoming tenant messages, excluding the sender. Do not expose other
  recipients' email addresses. Important announcement versions also email their recorded recipients.
- Send email after commit using the existing Django mail backend. Keep email content minimal and link
  back to the permission-checked portal. Persist attempts/failures, recheck recipient authorization
  before dispatch/retry, and provide explicit manager retry without duplicate successful deliveries.
  Email failure never rolls back a message. No automatic retry worker, digest scheduler or notification
  preference engine is required initially. Test through a safe backend/Mailpit, never real tenants.
- Plain form submissions and normal links provide complete reading/sending functionality. HTMX may
  poll for new messages/unread state while a conversation is open; stop polling when hidden, avoid
  overlapping requests, and preserve focus, scroll and unsent text. Pagination and ordering must
  prevent missed or duplicated displayed messages. The approved open-thread interval is 15 seconds.
- No React SPA, WebSockets, ASGI conversion, Redis, Celery, broker or external messaging provider is
  required. This adds a domain to the existing app, not a full application rework. Reconsider delivery
  infrastructure only if measured volume makes synchronous post-commit email unsuitable.
- Use the accepted E11 Operations Desk shell, one Communications sidebar destination and
  Messages/Announcements sections. The documentation diagram skill imposes no
  print-efficiency constraints on the live messaging interface.

## What exists today

Implementation is verified and owner-accepted for local merge from `rhp-8`:

- Tenant `/communications/` and staff `/manage/communications/`, private/shared subject threads,
  explicit recipient review, protected attachments, paginated history and scoped inbox filters.
- Per-user unread positions, shared work states, permanent shared-household freezes, manager-only
  scoped follow-up and immutable messages. No message or participant editing/deletion controls.
- Staff draft/review/publication, named publication snapshots, immutable corrections, withdrawal
  reasons, active/archive feeds and private announcement-linked conversations.
- Durable neutral emails after commit, fresh recipient authorization, known-failure and uncertain
  outcomes, explicit manager retry and no resend of recorded success. Safe locmem tests only.
- Tenant/staff dashboard summaries and 15-second visible-only polling, alongside complete plain
  forms and explicit POST read actions. Workers have no Communications navigation or endpoint access.
- Additive migrations `communications/0001_initial` and `audit/0010_alter_auditevent_action`;
  no changes to existing financial or maintenance records and no new dependencies.

Existing foundations reused:

- **The property → unit → lease structure** is the audience: "one property" is a query over that, and
  "everyone" is every tenancy.
- **The tenant area** (`/account/`, `/lease/`, `/payments/`) and its navigation, where an announcement will
  appear, plus the label the dashboard already carries for the panel that belongs here.
- **The email backend**, with console mail by default and the ecosystem Mailpit sink available for
  explicitly configured verification, so notifications can be tested without sending anything real.
- **The audit table** for who published, changed or withdrew an announcement.
- **Phase 7 maintenance** tenancy-scoped conversations, private attachments and durable email attempts.

## Decisions that govern it

ADR-024 records the approved implementation and the owner answers below.
The owner approved the recommended bounded messaging capability on October 17, 2026 after a read-only
review of the Innago tenant demonstration. Native apps and social/community features are excluded.
The October 19 answers resolve audience/lifecycle choices and select the accepted Operations Desk
components. Phase 7 and E11 are locally merged. Phase 8 code belongs only on `rhp-8`.

## Extensions filed under this phase

**E12 / P8-E1 — tenant–RHP messaging** is additive and implemented. The capability,
technology boundary, resolved decisions and acceptance criteria live in this record. See the
[extension register](../extensions.md). It replaces the original “evaluate messaging later” deferral;
it does not expand the project into a general chat platform.

## Acceptance criteria and evidence

Implemented, locally verified and owner-accepted for local merge; manual gaps remain explicit below:

- [x] An announcement appears only to the intended tenants
- [x] An expired announcement disappears from the normal tenant view
- [x] An important announcement is labeled in the feed and detail
- [x] Authorized tenants and managers exchange messages, including protected attachments
- [x] Explicit participants, co-tenants, new occupants and former tenants follow approved access rules
- [x] Unread state is per user; concurrent reads cannot move the read position backward
- [x] Announcement follow-up is private; no cross-tenancy conversation or attachment exposure
- [x] Retry/double-submit does not duplicate messages or successful notification deliveries
- [x] Manager incoming-message alerts and tenant reply alerts persist failures and support safe retry
- [x] Plain forms work; optional polling preserves composer state, ordering, focus and pagination
- [x] Existing maintenance, document, ledger and role-access regressions pass

### Evidence — October 19, 2026

- `make test`: **1,079 passed, 3 skipped** in 304.57 seconds. Skips are opt-in browser fixtures.
  The older sidebar-order assertion was updated to include the approved Communications destination.
- Final communications/navigation/documentation subset: **58 passed**; final communications-only
  rerun after attachment-error wording: **25 passed**, including real PostgreSQL concurrent sends,
  duplicate publication, co-tenant notification locks and monotonic concurrent reads.
- `make lint`, `make check`, `make check-deploy`, `make assets`, migration drift and applied-migration
  checks passed. A fresh loopback server returned `/healthz` 200 and anonymous staff inbox 302.
- Opt-in authenticated browser fixtures passed separately with JavaScript enabled and with scripts
  blocked by CSP. Both used dedicated disposable test databases, isolated QA session/CSRF cookies
  and in-memory mail; no real tenant communications or financial records were changed.
- Browser exercised named shared-recipient review, tenant send, manager reply, handled/reopened
  work, publication review, important-notice publication, private notice follow-up and co-tenant
  inbox isolation. Polling appended the manager response while retaining an unsent tenant draft.
  Plain forms supported replies, explicit read updates and work actions without scripts.
- Visually inspected desktop, 768px tablet and 390px phone layouts, keyboard attachment focus and
  no horizontal overflow. Synthetic review captures remain local; no private snapshot was published.

### Changed components

`apps/communications/` contains the models, lifecycle hooks, calculation-free transactional
services, forms, views, URL configurations, delivery handling and dashboard projection.
Integration changes are in `config/urls.py`, `config/settings/base.py`, `.env.example`,
`apps/common/context_processors.py`, `apps/accounts/views.py`, `apps/audit/models.py` and the two
dashboard templates. `templates/communications/` and `static/js/communications.js` implement the
workspace and optional refresh. Tests are `tests/test_communications.py`, the opt-in
`tests/test_communications_browser.py`, and the updated sidebar assertion in
`tests/properties/test_operations_desk.py`. Governing documentation includes ADR-024, the
specification, roadmap/register, phase guide, architecture, database and security records.

## Deliberately not here

Native iOS/Android apps, browser/mobile push, SMS, inbound email replies or email-client synchronization,
public or cross-tenancy group chat, announcement comments/reactions, typing/presence indicators,
voice/video, delivery guarantees, enforced read receipts and emergency dispatch. No scheduled sending,
automatic digests, automatic email retry worker or elaborate draft/approval workflow. No bank/payment,
property-accounting or maintenance workflow changes. Announcements remain unidirectional.

## Known gaps and defects

The owner accepted the “Allow messages after move-out” correction and authorized local commit/merge.
Browser file-picker upload was not exercised; upload
limits, private downloads and failed-write cleanup were verified through automated tests. Actual
200% browser zoom and physical print review remain manual checks; no such review is claimed.
Review captures have not been uploaded to Outline. No production SMTP acceptance/delivery guarantee
is claimed; ambiguous
outcomes require explicit duplicate-warning acknowledgment before retry. Attachment text survives
validation errors, but browsers require files to be reselected. No automatic retry worker exists.

Phase 8 was developed on `rhp-8`; the owner authorized committing and folding it into local `main`.
E11 is preserved as earlier local `main` commit `1e906b6`. No push or external deployment is authorized.
Phase 9 may be planned, but its implementation requires a separately approved plan and phase branch.

### Owner wording correction

Use **Allow messages after move-out**; its paired action is **Turn off messages after move-out**.
The form help, review, read-only/allowed states and validation use this language too. The setting
applies only to the named conversation and keeps its reason requirement, fixed audience and lease/
financial-account boundaries. Internal action names, event types and saved history are unchanged.
No migration is required for this wording correction. This is RHP plain-language copy, not a claim
that another product uses the identical exception or label. Industry comparison used official
[Innago messaging terminology](https://innago.com/innago-releases-chat-feature/) and
[DoorLoop permission wording](https://support.doorloop.com/en/articles/10148841-troubleshoot-tenant-portal-login-and-access-issues).

After this correction, `make test` passed **1,080 tests**, with three opt-in browser fixtures
skipped (308.55 seconds). The new rendered-page test checks the form, staff controls and tenant
state text. Lint, Django/deployment checks, CSS build, migration checks and a fresh smoke start
also passed. This wording correction adds no migration; the two Phase 8 migrations remain additive.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P8-Q1 | Announcement audience when occupants change? | Snapshot recipients at publication. | Publication snapshot — selected in chat October 19. |
| P8-Q2 | Announcement email? | Important announcements also email. | Important only — selected in chat October 19. |
| P8-Q3 | Who may publish/correct/withdraw? | Original recommendation reserved withdrawal to admins. | Full manager operations — selected in chat October 19; supersedes original recommendation. |
| P8-Q4 | Explicit acknowledgment? | No acknowledgment. | No acknowledgment — selected in chat October 19. |
| P8-Q5 | Private/shared conversations? | Original recommendation was shared only. | Private + shared, private by default — selected in chat October 19. |
| P8-Q6 | Former-tenant replies? | Read-only with manager-enabled follow-up. | Manager-enabled replies — selected in chat October 19. |
| P8-Q7 | Household membership changes? | Freeze old shared thread. | Freeze old thread — selected in chat October 19. |
| P8-Q8 | Organization? | Subject-based threads. | Subject-based threads — selected in chat October 19. |
| P8-Q9 | Navigation? | One workspace with Messages/Announcements. | Communications workspace — selected in chat October 19. |

All listed decisions are resolved. Original superseded recommendations are identified above.
No acknowledgment, legal-delivery claim or general maintenance inbox is authorized.

## How to verify it

Publish one announcement to a single property and one to everyone, confirm a tenant of
another property never sees the first, that an expired one vanishes, and that the mail sink shows the email
where one was sent.

Exercise tenant-to-manager replies, attachments, unread counts, announcement follow-up and email failure/
retry with disposable records. Test forged IDs/downloads, inactive accounts, maintenance-role exclusion,
co-tenant membership changes, new occupants and move-outs against the owner-approved policy. Verify
duplicate/concurrent sends, read races, stale polling, partial upload rollback, escaping and rate limits.
Review desktop/tablet/phone and keyboard/plain-form behavior using the accepted Operations Desk shell.
Run the full implementation gates, migration checks and smoke start, then publish and verify the ecosystem.

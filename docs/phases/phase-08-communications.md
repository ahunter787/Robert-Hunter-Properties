# Phase 8 — Communications

**Status:** Not started
**Milestone:** 5 — Communication and an operational dashboard for the RHP team
**Specification:** `docs/harness/master-spec.md`, `PHASE 8 — COMMUNICATIONS`
**Extension:** E12 / P8-E1 — tenant–RHP messaging, scope approved October 17, 2026.
This is a capability specification, not implementation authorization or a visual-design decision.

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
  Co-tenant versus individual visibility is an open decision below, not an implementation default.
- Retain chronological message history with author and server timestamp. Sent content is not silently
  overwritten or deleted; corrections are new messages. Do not add destructive deletion controls.
  Administrative audit facts remain distinct from tenant-readable conversation content.
- Accept protected attachments using existing validation/private-serving utilities, readable display
  names and randomized storage names. Proposed initial allowlist: JPEG, PNG, WebP and PDF, with the
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
  recipients' email addresses. Announcement email policy remains P8-Q2.
- Send email after commit using the existing Django mail backend. Keep email content minimal and link
  back to the permission-checked portal. Persist attempts/failures, recheck recipient authorization
  before dispatch/retry, and provide explicit manager retry without duplicate successful deliveries.
  Email failure never rolls back a message. No automatic retry worker, digest scheduler or notification
  preference engine is required initially. Test through a safe backend/Mailpit, never real tenants.
- Plain form submissions and normal links provide complete reading/sending functionality. HTMX may
  poll for new messages/unread state while a conversation is open; stop polling when hidden, avoid
  overlapping requests, and preserve focus, scroll and unsent text. Pagination and ordering must
  prevent missed or duplicated displayed messages. No exact refresh interval is committed here.
- No React SPA, WebSockets, ASGI conversion, Redis, Celery, broker or external messaging provider is
  required. This adds a domain to the existing app, not a full application rework. Reconsider delivery
  infrastructure only if measured volume makes synchronous post-commit email unsuitable.
- E11 still owns presentation selection. This scope chooses no inbox layout, navigation shell,
  palette, bubble style or responsive composition. The documentation diagram skill imposes no
  print-efficiency constraints on the live messaging interface.

## What exists today

No general messaging or announcements yet — this phase has not been built. What it builds on:

- **The property → unit → lease structure** is the audience: "one property" is a query over that, and
  "everyone" is every tenancy.
- **The tenant area** (`/account/`, `/lease/`, `/payments/`) and its navigation, where an announcement will
  appear, plus the label the dashboard already carries for the panel that belongs here.
- **The email backend**, with console mail by default and the ecosystem Mailpit sink available for
  explicitly configured verification, so notifications can be tested without sending anything real.
- **The audit table** for who published, changed or withdrew an announcement.
- **Phase 7 maintenance** tenancy-scoped conversations, private attachments and durable email attempts.

## Decisions that govern it

No communications ADR exists yet. Write it before implementation, incorporating the answers below.
The owner approved the recommended bounded messaging capability on October 17, 2026 after a read-only
review of the Innago tenant demonstration. Native apps and social/community features are excluded.
Approval does not resolve the audience/lifecycle questions or select the E11 visual direction.
Phase 7 remains open; this record does not authorize starting Phase 8 code on `rhp-7`.

## Extensions filed under this phase

**E12 / P8-E1 — tenant–RHP messaging** is additive, approved in scope but unbuilt. The capability,
technology boundary, open decisions and acceptance criteria live in this record. See the
[extension register](../extensions.md). It replaces the original “evaluate messaging later” deferral;
it does not expand the project into a general chat platform.

## Acceptance criteria and evidence

Not yet met — the phase is unbuilt. From the specification:

- [ ] An announcement appears only to the intended tenants
- [ ] An expired announcement disappears from the normal tenant view
- [ ] An important announcement can be highlighted
- [ ] Authorized tenants and managers can exchange messages, including protected attachments
- [ ] Explicit participants, co-tenants, new occupants and former tenants follow approved access rules
- [ ] Unread state is per user; concurrent reads cannot move the read position backward
- [ ] Announcement follow-up is private; no cross-tenancy conversation or attachment exposure
- [ ] Retry/double-submit does not duplicate messages or successful notification deliveries
- [ ] Manager incoming-message alerts and tenant reply alerts persist failures and support safe retry
- [ ] Plain forms work; optional polling preserves composer state, ordering, focus and pagination
- [ ] No maintenance, document, ledger or role-access regression

## Deliberately not here

Native iOS/Android apps, browser/mobile push, SMS, inbound email replies or email-client synchronization,
public or cross-tenancy group chat, announcement comments/reactions, typing/presence indicators,
voice/video, delivery guarantees, enforced read receipts and emergency dispatch. No scheduled sending,
automatic digests, automatic email retry worker or elaborate draft/approval workflow. No bank/payment,
property-accounting or maintenance workflow changes. Announcements remain unidirectional.

## Known gaps and defects

Nothing is broken — this phase does not exist yet. The gap it fills: RHP has no way to tell the right
tenants something inside the portal outside a maintenance request, or hold general saved conversations.
All criteria above are planned, not passing implementation evidence. An ADR, resolved access/lifecycle
choices and an approved implementation plan are required before build work starts.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P8-Q1 | Who is the audience when an announcement is published — the tenants on the lease **now**, or whoever lives there while it is live? | The tenancy live at the moment it is published, recorded; a tenant who moves in later does not receive history they were never told. | *(awaiting)* |
| P8-Q2 | In-portal only, or email as well? | Both, for an announcement marked important; in-portal for the rest, so the portal stays the record. | *(awaiting)* |
| P8-Q3 | Who may publish — managers and above, or admins only? | Managers and above may draft and publish to their portfolio; an admin may withdraw one. | *(awaiting)* |
| P8-Q4 | Should a tenant be able to acknowledge an announcement (e.g. "I have read the inspection notice")? | Not now. It turns a notice into a to-do list and implies enforcement RHP does not want. | *(awaiting)* |
| P8-Q5 | Are general conversations shared with every co-tenant, private to one tenant, or both? | Start with explicitly labeled tenancy-shared conversations; any individual channel must be separately identified, never implicitly shared | *(awaiting)* |
| P8-Q6 | May former tenants continue sending messages after move-out? | Preserve read-only history while accounts remain active; allow a manager to explicitly enable a scoped follow-up conversation, independent of financial settlement | *(awaiting)* |

The audience snapshot, email and permission recommendations remain unanswered; accepting the feature
scope is not a blanket answer to these questions. P8-Q3's original admin-only withdrawal recommendation
also needs reconciliation with the approved manager operational-authority boundary before build.
Likewise P8-Q4 is retained as an explicit confirmation question; this extension contains no enforced
acknowledgment capability.

## How to verify it

Not yet. When built: publish one announcement to a single property and one to everyone, confirm a tenant of
another property never sees the first, that an expired one vanishes, and that the mail sink shows the email
where one was sent.

Exercise tenant-to-manager replies, attachments, unread counts, announcement follow-up and email failure/
retry with disposable records. Test forged IDs/downloads, inactive accounts, maintenance-role exclusion,
co-tenant membership changes, new occupants and move-outs against the owner-approved policy. Verify
duplicate/concurrent sends, read races, stale polling, partial upload rollback, escaping and rate limits.
Review desktop/phone and keyboard/plain-form behavior without selecting a production visual concept.
Run the full implementation gates, migration checks and smoke start, then publish and verify the ecosystem.

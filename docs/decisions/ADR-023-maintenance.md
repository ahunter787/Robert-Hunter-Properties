# ADR-023 — Maintenance work, private conversations, and repair costs

- **Status:** Accepted — owner-approved implementation plan, October 16, 2026
- **Phase:** 7, RHPDEV-98

## Decision

Keep location, reporter, assignment, expense, and tenant recharge distinct. Tenants and
managers/admins can create requests against properties or units. The reporting tenancy is
authorization context, not a liability determination. Managers can record work at vacant units.

Requests have an integer primary key for the audit trail and UUID public identifier. A
request names a property and optionally one of its units. Tenancy audience rows are explicit:
tenant submissions share with their own tenancy, staff submissions start private. Sharing
never carries forward to a new occupant. Former tenants retain read-only history. Shared
property requests have tenancy-isolated replies and attachments; no audience can enumerate
another audience, its identities, financial records, or conversation.

Managers operate portfolio-wide. Maintenance employees see assigned work only and cannot
access costs, recharges, general documents, or tenant administration. All sensitive services
validate actors and object scope, not just views. Tenants create only for a current tenancy's
unit or property, and cannot change operational status directly.

Statuses: OPEN, ACKNOWLEDGED, SCHEDULED, IN_PROGRESS, WAITING, COMPLETED, CLOSED.
Managers assign, prioritize, schedule, close and reopen; assigned workers record progress,
waiting reasons, updates and completion. A schedule needs a date/window; waiting needs a
reason. Backward transitions and reopening require a reason. Tenant unresolved flags enter
the queue without changing status; a manager acknowledges or reopens them explicitly.
Priority is Low, Normal, High or Urgent. This is not emergency dispatch.

Updates are internal or explicitly addressed to tenancy audiences. Tenants' replies remain
within their own tenancy. Staff edit their own notes, managers can correct staff notes;
revisions and actors remain in append-only history. Publishing an internal note creates a
separate addressed update, never changes its historical visibility. Permission to enter
defaults to No and changes retain an actor/time. Raw audits are never a tenant timeline.

Attachments use random storage names and UUID routes, with readable original names. Photos
are JPEG/PNG/WebP; managers can attach PDF cost evidence. Existing per-file size and image
dimension limits apply, with at most ten files per act. Downloads authorize through their
parent update/audience or manager-only expense. Admin-only erroneous-upload removal needs a
reason and keeps metadata/audit history; requests have no deletion route.

Costs are append-only Decimal entries with dated, reasoned corrections. Totals are derived.
Vendor records contain name, contact, trades and active status; used vendors are retired.
Recharges are a separate manager action: manually select eligible tenancies and amounts,
review cost, prior net ledger charges, proposed split, due dates and reasons, then confirm a
signed state-bound review. Variances from cost are highlighted, not assigned as liability.
Existing occupancy/account guards remain: no draft/ended/settled charging. Request locks,
atomic transactions and unique batch/lease links prevent duplicate posts; ledger adjustments
correct posted charges. No recurring allocation, vendor payment or general ledger is added.

Tenant submission confirmations and public-update emails are persisted per event/recipient,
sent after commit, with individual append-only attempt outcomes, visible failures and explicit retry.
Delivery rechecks audience and
account access. Emails contain a neutral notice and portal link, never raw notes, attachments
or financial evidence. No Redis, job server, general chat, vendor portal or scheduling
integration. SMTP acceptance is not proof of inbox delivery; an interrupted SMTP transaction
can require operator review before retry.

## Owner review corrections — October 17, 2026

RHPDEV-98: staff select a required property before an optional unit. Unit choices are scoped
to that property in both forms and services. A location-only GET step precedes descriptions
and uploads; HTMX refreshes unit choices, with a plain-form fallback and no writes.

Entry permission means tenant authorization for RHP staff and assigned repair professionals
for this request, not RHP authorizing itself. Use an unchecked-by-default checkbox; editing
loads the selected tenancy's saved value. Managers recording or withdrawing offline consent
must supply a staff-only source note. Preserve existing values, actors and timestamps, and
append changes to the tenancy timeline and staff audit. No notice-law exemption is implied.

The separately approved E11 design study produces alternatives only. It must not roll out
new navigation or change maintenance history before the owner selects a direction.

## Verification requirements

Tests must cover tenant/co-tenant, cross-tenancy and reassignment boundaries; public UUID
forgery; ended-tenancy history; all mutations via services and HTTP; image/file limits;
revisions and deletion; status/schedule/entry permission; cost corrections, signed recharge
reviews, duplicate posts, concurrency and rollback; notification failures and content privacy.
Review desktop/mobile and plain-form flows. Run the full project gates, migration checks,
smoke start, documentation publication and ecosystem verification. No commit/merge/push
without explicit owner instruction.

# ADR-033: Messenger operational enhancements (E15)

- **Status:** Accepted
- **Date:** 2026-10-22
- **Extension:** E15, branch `rhp-e15-messenger`
- **Depends on:** ADR-024 (communications), the TenantCloud/TurboTenant study in
  [`design/tenantcloud-modifications-plan.md`](../design/tenantcloud-modifications-plan.md)

## Decision

Extend the existing E12 communications app rather than add a chat product:

1. Staff may maintain **quick replies** (a label and editable body) and insert one into the composer.
   Templates are staff-only; a tenant never receives them, and the sent `Message` remains the immutable
   record.
2. A staff user may **archive or mute** a conversation for themselves. The row is per user; it does not
   freeze, delete or hide history from the tenant or other staff. Mute suppresses that user's future
   message emails, not unread state.
3. Staff may download a **transcript** of a conversation (text and CSV) with attachment names, not file
   bytes. Exports are manager-only, audited/checksummed as appropriate, and never include another
   tenancy.
4. The conversation view gains a **shared-media index** over its existing attachments, using the same
   permission-checked download view.
5. Staff may add **internal notes** that are append-only and never visible to tenants, included in tenant
   exports or delivered by email. A separate table is used so tenant message queries cannot accidentally
   include notes.
6. Optionally link a conversation to the maintenance request it is about; the link is context, not a
   merge of maintenance updates into chat.

## Boundaries

No typing/presence, read receipts, reactions, nested threads, voice/video, SMS, realtime service,
external chat SDK, e-sign/notices or changes to message immutability. No new dependency. Tenant routes
remain tenancy-scoped; all mutations are CSRF-protected POSTs.

## Verification

Tests cover manager/tenant/other-lease authorization, per-user archive/mute isolation, template use,
transcript contents and checksum/audit, shared-media scoping, internal-note invisibility to tenants, and
the full gate: `make test`, `make lint`, `make check`, `make check-deploy`, migrations and a smoke start.

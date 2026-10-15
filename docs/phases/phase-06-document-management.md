# Phase 6 — Document management

**Status:** Next
**Milestone:** 4 — Documents and maintenance requests work end to end
**Specification:** `docs/harness/master-spec.md`, `PHASE 6 — DOCUMENT MANAGEMENT`

## Scope as specified

Create safe document access: upload, categorise (lease, addendum, notice, receipt, inspection,
correspondence, other), associate with a lease, a property or a tenant, choose tenant visibility, serve
downloads through permission checks, record metadata, and give staff search and filter. The specification
is emphatic on one point: **never expose an uploaded document by guessing a public media URL.**

## What exists today

Nothing yet — this phase has not been built. What it builds on:

- **A single lease file, already permission-checked.** `Lease.lease_file` with `LeaseDocumentView` (the
  tenant's own, no id in the URL) and the staff document view, both served through `document_response(...)`
  rather than by the proxy or the web server.
- **Two working upload paths to generalise:** the property banner photo and the tenant photo — validated
  for type, size and dimensions in `apps/common/images.py`, stored under randomised names, deleted when
  replaced or when the owner row goes.
- **Settings and storage:** `RHP_MAX_UPLOAD_MB`, `MEDIA_ROOT`/`MEDIA_URL`, and a production path that
  already refuses to serve media from Caddy.
- **The pieces the rest of the phase needs:** the permission mixins and `tenant_scope`, the audit table,
  the tenant area and its navigation, and the Tailwind card/form components.

## Decisions that govern it

| Record | What it will have to respect |
| --- | --- |
| [ADR-007](../decisions/ADR-007-lease-modeling.md) | One lease file today; this phase turns that into rows |
| [ADR-009](../decisions/ADR-009-tenant-photos.md) | The photo pattern: randomised name, permission-checked view, validated upload |
| [ADR-006](../decisions/ADR-006-unit-types-maps-and-banners.md) | The banner-photo validation and deletion rules |

No decision record exists for this phase yet. It needs one before it is built: the document model, the
visibility rule, and how a lease's existing single file becomes a document row.

## Extensions filed under this phase

None yet.

## Acceptance criteria and evidence

Not yet met — the phase is unbuilt. From the specification:

- [ ] A tenant cannot access documents belonging to another tenancy
- [ ] An administrator can control tenant visibility
- [ ] Files persist through deployments
- [ ] File type and upload size restrictions exist
- [ ] No document is reachable by guessing a URL, and none is served by the web server or the proxy

## Deliberately not here

Document generation (statements, receipts, notices) unless it earns its keep in Phase 10; virus scanning
(Phase 12 decides whether it is worth it); e-signature of any kind.

## Known gaps and defects

The gap this phase inherits: **a lease has exactly one document**. A signed lease with an addendum, a
notice and an inspection photo cannot be recorded, so the office keeps them outside RHP. The migration path
matters — the existing `lease_file` must become a categorised document row without losing a file or a link.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P6-Q1 | Default visibility for an uploaded document: tenant-visible or staff-only? | **Staff-only by default**, with an explicit "tenant can see this" choice on upload — a misfiled internal document is worse than a document the tenant has to ask for. | **As recommended** — staff-only unless the uploader ticks the tenant-visible box (2026-10-15). |
| P6-Q2 | Should documents attach to a **tenancy** (lease), a **property**, or a **person**? | All three, as the specification says, but a tenancy is the default and the only one a tenant sees. | **As recommended** — all three, tenancy the default. |
| P6-Q3 | Do you want a receipt per recorded payment, generated from the ledger entry? | Yes, eventually — it is the first genuinely useful generated document, and Phase 10 is where it belongs. | **As recommended** — yes, but Phase 10, not here. |
| P6-Q4 | Should a superseded document (an old lease version) be replaced or kept alongside? | Kept alongside, with a date — history is the whole point, and the ledger already refuses to erase. | **Kept alongside — and a document uploaded in error can be removed: an admin may remove one, with a note. Not a manager, and nothing lower.** |

## How to verify it

Not yet. When built: upload each category against a tenancy, confirm the tenant sees only the
tenant-visible ones on `/lease/`, and that the URL cannot be walked, while `tests/` covers the isolation
and the upload restrictions.

# Phase 6 — Document management

**Status:** Built — awaiting the owner's fold
**Milestone:** 4 — Documents and maintenance requests work end to end
**Specification:** `docs/harness/master-spec.md`, `PHASE 6 — DOCUMENT MANAGEMENT`

## Scope as specified

Create safe document access: upload, categorise (lease, addendum, notice, receipt, inspection,
correspondence, other), associate with a lease, a property or a tenant, choose tenant visibility, serve
downloads through permission checks, record metadata, and give staff search and filter. The specification
is emphatic on one point: **never expose an uploaded document by guessing a public media URL.**

## What exists today

Built on `rhp-6-documents`, awaiting the fold into `main`. The decision is
[ADR-022](../decisions/ADR-022-documents.md); the code is `apps/documents/` and `apps/common/files.py`.

- **One row per file.** `Document` (`apps/documents/models.py`) carries `title`, `category` (the seven
  the specification names), `file`, `original_name`, optional `lease`/`property`/`tenant` links (at
  least one, enforced by `clean()`; a tenancy is the default), `tenant_visible`, `document_date`,
  `note`, `uploaded_by` and `created_at`. The stored name is randomised — `document_path` writes
  `documents/<uuid4hex><suffix>` and never the client's filename; the name it arrived with is kept in
  `original_name`.
- **Staff-only unless somebody says so.** `tenant_visible` defaults to `False`. The upload form carries
  the explicit "The tenant can see this", and `Document.clean()` refuses a tenant-visible document that
  is attached only to a property: there is no tenant to show it to.
- **Every download is a permission-checked view.** `apps/common/files.py::document_response` (moved out
  of `apps/leases/views.py`) serves with `Cache-Control: private, max-age=300` and
  `X-Content-Type-Options: nosniff`, named from the document's title. Staff read any document by id
  (`documents:download`); a tenant goes through `Document.objects.visible_to(user)`, so another
  tenancy's id is a **404, not a 403**. A row whose bytes are missing answers 404 rather than 500, and
  no media URL is routed.
- **The upload rules live in one place.** `apps/common/files.py::validate_document_upload` enforces the
  allow-list (PDF, JPEG, PNG, WebP, Word, Excel, CSV and text) and `RHP_MAX_UPLOAD_MB` (default 5);
  `DocumentForm.clean_file` uses it.
- **Removal is an admin's act, with a required note** (the owner's Q4 answer). `DocumentRemoveView`
  mixes in `AdminRequiredMixin`, so a manager gets 403; `apps/documents/services.py::remove_document`
  deletes the row *and* the stored bytes, and writes a `DOCUMENT_REMOVED` audit event carrying the
  title, category, attachment, who removed it and why. A superseded document is kept alongside instead
  (the other half of Q4).
- **Screens.** `/manage/documents/` lists with search, category, visibility and property filters, 25 to
  a page; `/manage/documents/upload/` presets the attachment from `?lease=`/`?property=`/`?tenant=`;
  `/manage/documents/<pk>/download/` and `/manage/documents/<pk>/remove/` complete the office side. A
  tenancy's page lists its documents with a "File a document" action. The tenant has
  `/lease/documents/` and `/lease/documents/<pk>/download/` under the `tenant_documents` namespace, and
  "Documents" is in both navigations.
- **The migration, not a re-upload.** `documents/0002_lease_files_become_documents` turned each
  `Lease.lease_file` into a `Document` row — category `LEASE`, `tenant_visible=True` because tenants
  could already open it, the same storage path, and a title from `lease_document_name` or "Signed
  lease". Nothing was moved. `leases/0010` then dropped `lease_file` and `lease_document_name`;
  `Lease.document_name` and the old `leases:lease-document` / `tenancy:document` routes are gone.
  `apps/leases/models.py::lease_document_path` survives only because the applied migrations serialise
  it — no upload uses it.

## Decisions that govern it

| Record | What it constrains |
| --- | --- |
| [ADR-022](../decisions/ADR-022-documents.md) | The decision for this phase: one row per file, staff-only unless ticked, permission-checked serving, the lease-file migration, and removal by an admin with a required note |
| [ADR-007](../decisions/ADR-007-lease-modeling.md) | The lease model the single file belonged to; a tenancy is the axis a tenant's documents are scoped by |
| [ADR-009](../decisions/ADR-009-tenant-photos.md) | The photo pattern reused here: randomised name, permission-checked view, validated upload |
| [ADR-006](../decisions/ADR-006-unit-types-maps-and-banners.md) | Banner validation and deletion; the document rules live beside the image rules in `apps/common/` |
| [ADR-003](../decisions/ADR-003-role-on-user-model.md) | Roles: managers file documents, admins remove them |

ADR-022 (accepted 2026-10-15) is this phase's decision record, and it answers the four questions below.
The earlier records above still govern what they always did: this phase generalises their patterns, it
does not change the portfolio, the lease model, the photos or the roles.

## Extensions filed under this phase

None yet. **E6** (post-tenancy charges with their evidence) was waiting on this phase, but it is an
extension of Phase 4 and stays filed there — see [`docs/extensions.md`](../extensions.md).

## Acceptance criteria and evidence

All five are met by the code on `rhp-6-documents`; the specification's list, with what meets it:

- [x] A tenant cannot access documents belonging to another tenancy — both tenant screens query
      `Document.objects.visible_to(user)` (`apps/documents/models.py`), and
      `TenantDocumentDownloadView` resolves `get_object_or_404` over that scope, so another tenancy's id
      is a 404 rather than a refusal that admits the document exists.
- [x] An administrator can control tenant visibility — `tenant_visible` defaults to `False`, the upload
      form carries "The tenant can see this", and `Document.clean()` refuses a tenant-visible
      property-only document.
- [x] Files persist through deployments — uploads land under `MEDIA_ROOT`, which both Compose files back
      with the `media_data` volume at `/app/media`; the migration points rows at the storage paths that
      already held the files instead of moving them.
- [x] File type and upload size restrictions exist — `validate_document_upload` enforces the extension
      allow-list and `RHP_MAX_UPLOAD_MB`, and the form calls it for every upload.
- [x] No document is reachable by guessing a URL, and none is served by the web server or the proxy —
      stored names are random, Caddy never serves `/media` and `MEDIA_URL` is routed only in
      development, and every download goes through `document_response` behind a permission check.
      The tenant-facing URL does carry a pk, which ADR-022 decided deliberately; the tenancy scope
      resolves it, so a guessed id answers 404.

## Deliberately not here

Document generation (statements, receipts, notices) unless it earns its keep in Phase 10; virus scanning
(Phase 12 decides whether it is worth it); e-signature of any kind.

## Known gaps and defects

The gap this phase inherited is **closed**: a tenancy is no longer limited to one document.
`documents/0002_lease_files_become_documents` turned each `Lease.lease_file` into a categorised document
row — the same storage path, nothing re-uploaded — and `leases/0010` dropped `lease_file` and
`lease_document_name`, so one concept (a document) remains rather than two. What stays outside the phase:

- **Generated documents.** A receipt produced from a recorded payment is still Phase 10 (P6-Q3); the
  `RECEIPT` category exists, but a receipt is filed by hand like any other file.
- **Virus scanning** is Phase 12's decision, and e-signature remains excluded from the product.
- **The property and person screens do not list their documents yet.** A document filed against a
  property or a tenant is found in `/manage/documents/` (filter by property) and, for a tenant who can
  see it, on the tenant's `/lease/documents/`; only the tenancy's office page lists its documents inline.
- **A property-only document can never be tenant-visible** — that is the rule, not a gap: there is no
  tenant to attach it to (ADR-022).

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P6-Q1 | Default visibility for an uploaded document: tenant-visible or staff-only? | **Staff-only by default**, with an explicit "tenant can see this" choice on upload — a misfiled internal document is worse than a document the tenant has to ask for. | **As recommended** — staff-only unless the uploader ticks the tenant-visible box (2026-10-15). |
| P6-Q2 | Should documents attach to a **tenancy** (lease), a **property**, or a **person**? | All three, as the specification says, but a tenancy is the default and the only one a tenant sees. | **As recommended** — all three, tenancy the default. |
| P6-Q3 | Do you want a receipt per recorded payment, generated from the ledger entry? | Yes, eventually — it is the first genuinely useful generated document, and Phase 10 is where it belongs. | **As recommended** — yes, but Phase 10, not here. |
| P6-Q4 | Should a superseded document (an old lease version) be replaced or kept alongside? | Kept alongside, with a date — history is the whole point, and the ledger already refuses to erase. | **Kept alongside — and a document uploaded in error can be removed: an admin may remove one, with a note. Not a manager, and nothing lower.** |

## How to verify it

As a manager, on the running app:

1. **File one of each category.** Open a tenancy at `/manage/leases/<pk>/`, choose "File a document"
   (the attachment is preset from `?lease=`) and upload one file per category — LEASE, ADDENDUM, NOTICE,
   RECEIPT, INSPECTION, CORRESPONDENCE and OTHER — using a PDF, an image and an office format among them.
   Each appears in the tenancy's Documents list and in `/manage/documents/`; the list's search, category,
   visibility and property filters each narrow it, and every document opens from its title through
   `/manage/documents/<pk>/download/`.
2. **Tick visibility, and check the default.** Upload one document without "The tenant can see this" and
   one with it. The first is absent from the tenant's pages; the second is on `/lease/documents/` and
   linked from the tenant's `/lease/` page. Try ticking it on a property-only document: the form refuses,
   because there is no tenant to show it to.
3. **Walk another tenancy's id.** Signed in as a tenant on tenancy A, request
   `/lease/documents/<pk>/download/` for a document that belongs to tenancy B: the answer is **404**, not
   403. The tenant's own list never shows it.
4. **Push the upload rules.** Upload a `.svg` (or any extension outside the allow-list) and a file over
   `RHP_MAX_UPLOAD_MB`: both are refused with the message from `apps/common/files.py`, before any row is
   written.
5. **Try the removal rules.** As a manager, `/manage/documents/<pk>/remove/` is a **403**. As an admin,
   submitting it with an empty note is refused; with a note, the row and its stored file are gone, and
   the History panel of the tenancy's Rent & Payments page shows a `DOCUMENT_REMOVED` event carrying the
   title, category, attachment, the admin and the note. A superseded document is not removed — file the
   new version alongside it.
6. **Look at the suite.** The document tests live in `tests/documents/` and `tests/leases/`: isolation
   (another tenancy's id is a 404, a staff-only document is not listed), the allow-list and the size cap,
   randomised storage names, the migration turning `lease_file` into a `Document` without moving the
   file, and admin-only removal with its audit event.

# ADR-022 — Documents: one row per file, and who may see or remove it

**Status:** Accepted (owner-answered 2026-10-15)
**Date:** 2026-10-15
**Related:** [ADR-007](ADR-007-lease-modeling.md) (the single lease file this replaces), [ADR-009](ADR-009-tenant-photos.md)
(the photo pattern: randomised name, permission-checked view, validated upload), [ADR-006](ADR-006-unit-types-maps-and-banners.md)
(banner validation and deletion), [ADR-003](ADR-003-role-on-user-model.md) (roles), [Phase 6 record](../phases/phase-06-document-management.md)

## Context

Phase 6 asks for documents that can be uploaded, categorised (lease, addendum, notice, receipt,
inspection, correspondence, other), attached to a lease, a property or a tenant, made visible to a tenant
or not, downloaded only through a permission check, and searched — with one emphatic rule: *never expose an
uploaded document by guessing a public media URL.*

RHP has exactly one document today: `Lease.lease_file`, a single file per tenancy, served through
`document_response(...)` by two views (staff and the tenant's own, which has no id in its URL). A signed
lease with an addendum, a notice and an inspection photo cannot be recorded at all, so those live outside
RHP. The owner answered the four questions the record had been holding (P6-Q1 … P6-Q4) — three of them "as
recommended", and one with an addition of his own.

## Decisions

### One row per file, attached to a tenancy, a property or a person

A `Document` carries the file, its readable title, the category, the date on the paper, an office note, who
uploaded it and when, and optional links to a **lease**, a **property** and a **tenant** (P6-Q2). At least
one link is required, and a tenancy is the default. The stored path is randomised — never the client's
filename — exactly as photos and the lease file already are.

### Staff-only unless somebody says otherwise

`tenant_visible` defaults to **false** (P6-Q1). The upload screen has an explicit "the tenant can see this"
choice, and only staff have it. A property-only document can never be tenant-visible: there is no tenant to
attach it to, and the tenant's own screens resolve documents through their tenancy.

### Every download is a permission-checked view

No document is reachable by URL guesswork: files live under `MEDIA_ROOT` with randomised names, the reverse
proxy refuses to serve media in production, and every download runs through `document_response(...)` with
`Cache-Control: private`.

- **Staff** read any document, by id.
- **A tenant** reads a document only when it is `tenant_visible` **and** scoped to their own tenancy —
  `Document.objects.get(pk=..., lease__tenants=request.user)`, the authorization scope rather than a bare
  primary key. Somebody else's id answers **404, not 403**: the refusal must not confirm that the document
  exists.

That a tenant-facing URL carries an id is a deliberate change from the two views it replaces. The rule the
specification sets is about *guessing media paths*, and the risk it names is a document served by the web
server; an id that is resolved through the tenancy scope, with a test that walks another tenancy's id, meets
it. The tenant's own lease is one row among these now, so the old "no id anywhere" view cannot survive the
general case.

### The existing lease file becomes a document row

Each `Lease.lease_file` becomes a `Document`: category **lease**, title from the display name (or "Signed
lease"), attached to the tenancy and its property, and **tenant-visible — because tenants can already see
it**, and the migration must not take something away.

The file is **not moved**: the row points at the same storage path, so nothing is re-uploaded and no link
breaks. Then `lease_file` and `lease_document_name` are dropped, and the lease screens read documents
instead. One concept, not two — which is why the phase's risk is in the migration, and why the migration is
tested.

### Superseded documents are kept; a mistake can be removed

An old version of a lease is **kept alongside the new one**, with its date (P6-Q4): history is the point, and
the ledger already refuses to erase.

But a document uploaded **in error** is not history, and the owner's instruction is specific:

> *"Yes, with provision for documents uploaded in error. An Admin can remove, perhaps, with a note. Not a
> manager, or lower privilege."*

So removal is a **separate act, by an admin or above, with a required note**. It removes the row **and the
stored file** — a file known to be wrong has no business lingering in storage — and writes an audit event
carrying the title, the category, what it was attached to, who removed it and why. That event is the durable
record; the file is not.

*Alternatives rejected.* A tombstone row (a document that exists only to say it does not exist) keeps either
the file or a row with no meaning. Manager-level removal (destructive acts stay above the desk, as the
specification already says of deletion). A soft "hidden" flag (it leaves the bytes in place, which is the
thing that must not happen).

### One place for what RHP accepts

The accepted types and the size limit live beside the image rules, in `apps/common/files.py`, for the same
reason those do: a rule written twice will disagree with itself. PDF, JPEG, PNG and WebP, plus the office
formats (Word, Excel, CSV, plain text), capped by `RHP_MAX_UPLOAD_MB`.

## Consequences

**Good.** The office stops keeping addenda, notices and inspections outside RHP. A tenant sees exactly what
the office chose to show them, and only their own. Uploads are validated and named safely, downloads cannot
be walked, and a mistake can be corrected without a database edit — by the one role the owner named, with the
reason recorded.

**Accepted.** Phase 6 adds a table, an app and a second upload path; the lease's document card becomes a
list, and its tests move with it. A tenant-facing document URL carries an id, scoped and tested.

**Deliberately not here:** generating documents (receipts — Phase 10, P6-Q3), virus scanning (Phase 12),
e-signature (still excluded), and any change to what a *photo* is (banners and tenant photos stay where they
are, ADR-006/009).

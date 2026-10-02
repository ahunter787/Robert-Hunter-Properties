# ADR-009: Tenant photos

- **Status:** Accepted (review round on Phase 4)
- **Date:** 2026-10-02
- **Context:** staff asked for a face beside a name on the tenant screens

## Context

A tenant list and an account page are read by people who deal with tenants by name and by sight: "which
one is Ada?" is a real question at a desk with a queue. Adding a photo seems trivial and is not, because
a photo of a person is the first piece of **personal data** RHP stores that is not a business record:
it must not be reachable by guessing a URL, it must not be served by the reverse proxy, and it must not
leak between tenants.

## Decision

### Uploaded by staff, on the tenant's account page

The photo is set by an **admin** on `/manage/accounts/<pk>/`, alongside the other account actions. This
follows the rule Phase 1 already set: managers read accounts, administrators change them. It also means a
photo is a record the office keeps, not a self-published avatar.

`TenantProfile.photo` is an `ImageField`, so it sits with the tenant's contact details rather than on
`User` — staff accounts do not hold tenant profile data.

### The same upload rules as every other image, from one place

The banner rules (size ceiling `RHP_MAX_UPLOAD_MB`, JPEG/PNG/WebP only, 6000×6000 pixels, `seek(0)` after
Pillow reads it) were restated in the photo form for a while and then extracted:
`apps/common/images.py: validate_image_upload(...)` is now the single implementation, used by the property
banner and the tenant photo. SVG stays refused, because it can carry script.

Files are stored under `tenant_photos/<uuid><ext>` — never the client's filename — and the previous file
is deleted when a photo is replaced or removed, so uploads do not accumulate as orphans.

### Served only through permission-checked views

Two views, both returning a `FileResponse` with `Cache-Control: private, max-age=300` and
`X-Content-Type-Options: nosniff`:

- `GET /manage/accounts/<pk>/photo/` for staff (manager and above — they may already read the account);
- `GET /account/photo/` for the tenant themselves, with **no id in the URL**: the session decides which
  file is served, the same pattern as the tenancy document (ADR-007).

There is no tenant-facing directory, so a tenant can only ever fetch their own photo, and the
`private` cache directive keeps a person's photograph out of shared caches.

### A placeholder rather than a stored default

When there is no photo, `templates/components/avatar.html` draws an **inline SVG silhouette** with the
avatar's size. Nothing is stored, nothing is served, there is no file to clean up, and there is no static
asset to keep in step with the design tokens — the `static/` tree is build output.

## Consequences

**Positive**

- A tenant is recognisable at the desk, which is the whole point.
- Personal data follows exactly the rules already written for documents and banners, so there is one
  upload story rather than three.
- The shared validator means a change to the image rules reaches every upload at once.
- The placeholder cannot be broken by a missing file or a stale media volume.

**Negative / accepted trade-offs**

- A photo can go stale (an old picture of a person). Accepted: staff maintain it, and it is not used for
  identification.
- Admins must upload on the tenant's behalf; a tenant cannot set their own photo yet. The same
  `TenantProfileForm` and `accounts:photo` view would support self-service, so this is a small change if
  the owner wants it.
- The image is stored as uploaded: no thumbnailing or cropping, so a large portrait is served whole to a
  list of 25 tenants. Phase 6's document work is where resizing belongs (ADR-006 already defers banners
  the same way).
- Nothing deletes a photo when the *account* goes away, because accounts are deactivated, never deleted
  (Phase 1). If accounts ever become deletable, a `post_delete` receiver is the missing piece.

## Alternatives considered

- **`User.photo` instead of `TenantProfile.photo`**: one field for every account, including staff, and
  tenant profile data spread across two models. Rejected for now; a staff photo has no screen asking for
  it.
- **Tenant self-service upload**: nice for the tenant, and it makes the photo something a tenant
  publishes rather than something the office keeps. Deferred, not rejected — the code is one view away.
- **Serving from `/media/`**: faster, and it breaks the single rule that keeps tenant documents private
  (docs/security.md).
- **A Gravatar-style external URL**: no upload to store, and it sends a tenant's email address to a third
  party on every page view. Rejected.
- **Storing a placeholder file for every tenant without a photo**: rows of identical files, and something
  to go wrong. Rejected in favor of drawing the silhouette.

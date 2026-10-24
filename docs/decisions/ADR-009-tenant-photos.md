# ADR-009: Account photos

- **Status:** Accepted (review round on Phase 4); amended 2026-10-24
- **Date:** 2026-10-02
- **Context:** staff asked for a face beside a name on the tenant screens; account holders later asked
  for the same identity on their own account and in the sidebar

## Context

A tenant list and an account page are read by people who deal with tenants by name and by sight: "which
one is Ada?" is a real question at a desk with a queue. A photo of a person is the first piece of
**personal data** RHP stores that is not a business record: it must not be reachable by guessing a URL,
it must not be served by the reverse proxy, and it must not leak between accounts.

The original decision stored the photo on `TenantProfile`, uploaded only by staff. It left staff
accounts without a photo, gave tenants no way to set their own, and made the account page depend on the
tenant profile existing. The account photo is now a property of the **account**, not of a tenancy role.

## Decision

### One account-level photo

`accounts.User.photo` is the canonical `ImageField` for every account, including staff and tenants.
`TenantProfile.photo` is retained as a legacy column: migration `accounts.0005_user_photo` copies each
existing tenant photo's stored name to the account and leaves the file on disk untouched. New uploads,
replacements and removals act on `User.photo`; the legacy column is not read by the application.

### Who may change it

- Any signed-in account may upload, replace or remove **its own** photo from **Profile & account**.
- An **admin or superadmin** may upload, replace or remove the photo on **any** account from
  `/manage/accounts/<pk>/?section=contact`.
- A **manager or tenant** may see account photos they are already authorized to see, but cannot change
  another account's photo. The management upload route is admin-only.
- Replacing a supplied photo is always allowed by the account owner: an admin's choice does not lock the
  account owner out of choosing a different image.

### The same upload rules as every other image, from one place

`apps/common/images.py: validate_image_upload(...)` enforces size ceiling `RHP_MAX_UPLOAD_MB`,
JPEG/PNG/WebP only, 6000×6000 pixels and the seek/reset behaviour. SVG stays refused because it can
carry script. Files are stored under `account_photos/<uuid><ext>` — never the client's filename — and
the previous file is deleted when a photo is replaced or removed.

### Served only through permission-checked views

Both views return a `FileResponse` with `Cache-Control: private, max-age=300` and
`X-Content-Type-Options: nosniff`:

- `GET /manage/accounts/<pk>/photo/` for staff (manager and above — they may already read the account);
- `GET /account/photo/` for the signed-in account, with **no id in the URL**: the session decides which
  file is served, the same pattern as the tenancy document (ADR-007).

There is no public directory, so an account can only fetch its own photo through the session route, and
the `private` cache directive keeps a person's photograph out of shared caches.

### A placeholder rather than a stored default

When there is no photo, `templates/components/avatar.html` draws an **inline SVG silhouette** with the
avatar's size. Nothing is stored, nothing is served, there is no file to clean up, and there is no static
asset to keep in step with the design tokens.

## Consequences

**Positive**

- Every account, including `rhpadmin`, can carry the same identity in the sidebar and account pages.
- Admins can set a photo for any account; the account owner can later replace it themselves.
- Personal data follows the rules already written for documents and banners: one validated upload story
  and permission-checked delivery.
- The data migration preserves existing tenant photos without moving or duplicating files.

**Negative / accepted trade-offs**

- A photo can go stale (an old picture of a person). Accepted: the account owner and admins maintain it,
  and it is not used for identification.
- The legacy `TenantProfile.photo` column remains until a later cleanup migration; keeping it makes this
  migration reversible without losing historical metadata.
- The image is stored as uploaded: no thumbnailing or cropping, so a large portrait is served whole to a
  list. Phase 6's document work is where resizing belongs.
- Nothing deletes a photo when the *account* goes away, because accounts are deactivated, never deleted.

## Alternatives considered

- **Keep `TenantProfile.photo` and add a staff-only `User.photo`**: avoids a migration, but splits one
  concept across two fields and makes staff photos a second, weaker path. Rejected.
- **Admin-only uploads**: simpler, but it makes the account owner unable to replace a supplied photo,
  which the owner explicitly rejected.
- **Serving from `/media/`**: faster, and it breaks the single rule that keeps tenant documents private.
- **A Gravatar-style external URL**: no upload to store, but it sends an email address to a third party
  on every page view. Rejected.
- **Storing a placeholder file for every account without a photo**: rows of identical files and something
  to go wrong. Rejected in favor of drawing the silhouette.

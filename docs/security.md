# Security

RHP will hold tenant identity data, lease documents, and financial records. Security is a
first-class requirement, not a hardening phase: the rules below are binding from the first feature
phase onward. Phase 12 adds the operational layer (backups, monitoring, MFA, penetration testing).

## Authorization

Roles (defined in the master specification): `SUPERADMIN`, `ADMIN`, `MANAGER`, `MAINTENANCE`, `TENANT`.

Rules:

1. **Server-side enforcement, always.** Hiding a link, a button, or a navigation section is UX, never
   authorization. Every view re-checks permission for the object it is about to return.
2. **Scope the query, do not filter after the fact.**

   ```python
   # Wrong: fetches anything, then hopes the check is correct
   document = Document.objects.get(pk=pk)
   if document.lease.tenant_id != request.user.id:
       raise PermissionDenied

   # Right: the database never returns another tenancy's row
   document = get_object_or_404(Document, pk=pk, lease__tenants=request.user)
   ```

3. **Never trust input that decides access**: URL ids, hidden form fields, submitted role values,
   `?next=` targets, or anything from the client. Validate both *what* the object is and *whether*
   this user may touch it.
4. **Least privilege for staff**: `MAINTENANCE` sees the tickets assigned to them and the minimum
   property/tenant context needed to do the work; it does not get portfolio-wide access.
5. **Staff privilege is role-based**, not `is_staff`-based: Django's `is_staff`/`is_superuser` gate the
   admin site, while RHP's own screens check the role model (Phase 1).
6. **Deactivation beats deletion** for people and property; deletion is for mistakes, and destructive
   operations require explicit confirmation.
7. **Destructive operations are admin-only and POST-only**, behind a confirmation page that names the
   record (ADR-005). Managers can take a property or unit out of service but cannot delete it, and a
   property with units cannot be deleted at all: `on_delete=PROTECT` makes that a database refusal
   rather than a UI convention.
8. **Reading is not the same as changing.** Managers may read tenant records to do their job; creating
   accounts, inviting, deactivating, and changing roles remain with admins, and the views enforce that
   independently of whether the buttons are rendered.

## Identifiers and enumeration

Externally exposed resources that a tenant could enumerate (documents, maintenance requests,
attachments, lease files) use `UUIDField` primary keys or a random slug. Sequential integer ids stay
internal. Authorization is enforced regardless — unguessable ids are defense in depth, not the control.

The tenant lease document is the strongest form of this: its URL is `/lease/document/` with **no id at
all**, so there is nothing to enumerate and the view can only ever return the document of the one lease
the caller is on.

## Uploads

In force since Phase 2's banner photos, extended in Phase 3 by lease documents; the general document
work arrives in Phase 6 and maintenance photos in Phase 7:

- Allow-list extensions and content types; reject everything else. Banners and tenant photos accept
  JPEG, PNG, and WebP only — SVG is refused because it can carry script. Lease documents accept PDF,
  JPEG, and PNG. The image rules are implemented once, in `apps/common/images.py`.
- Enforce a maximum size at the form (`RHP_MAX_UPLOAD_MB`, default 5), plus a maximum pixel dimension;
  the reverse-proxy body limit is Phase 12.
- Store under a randomized filename (`property_banners/<uuid>.<ext>`, `lease_documents/<uuid><ext>`,
  `tenant_photos/<uuid><ext>`); never reuse the client-supplied name on disk.
- Never execute uploaded content; never serve it with a content type that browsers execute.
- **Every download is permission-checked.** Uploaded files are never reachable through a static file
  handler or the reverse proxy, and `MEDIA_URL` is only wired up in development. Banners are served by
  `PropertyBannerView`, lease documents by `LeaseDocumentView` (staff) and `TenantLeaseDocumentView`
  (the tenant on that lease); each checks its permission first (ADR-006, ADR-007).
- Downloads carry `Cache-Control: private` and `X-Content-Type-Options: nosniff`, so a shared cache
  never holds a tenant document or photo and a browser never sniffs one into a different type.
- **A tenant photo is personal data** (ADR-009). It is uploaded by an administrator on the tenant's
  account page, served only through `TenantPhotoView` (staff) or `OwnPhotoView` (the tenant, whose URL
  carries no id), and never shown to another tenant — there is no tenant-facing directory.
- Keep uploaded files outside the web root (`media_data` volume, mounted privately).
- Replacing or removing an image deletes the stored file, and deleting a property deletes its banner;
  replacing a lease document, or deleting its lease, deletes the old file, so uploads do not accumulate
  as orphans.

## Maps and third-party requests

Property pages can embed a Google map. RHP itself never calls Google: the pin is stored data entered by
staff, and the browser loads the map. That means a visitor's browser contacts Google when a map is
displayed — disclosed on the page, and an explicit allow-list entry when Phase 12 adds a
content-security policy. If `GOOGLE_MAPS_EMBED_API_KEY` is configured, the key is a browser-visible
embed key, not a server secret; restrict it by referrer in the Google console.

**Outbound requests.** RHP makes exactly one kind of outbound request, and only when a *shortened*
Google Maps link (`maps.app.goo.gl`, `goo.gl`, `g.co`) is saved as a property pin: the link is expanded
so its coordinates can be read. Every other link shape is parsed locally.

That request is treated as hostile input, because the URL comes from a user:

- redirects are followed by hand, at most five hops, and **only to Google's own hosts** (`*.google.*`);
  a redirect anywhere else is refused without being requested, so a shared link cannot be turned into a
  request to an internal address (link-local metadata endpoints included);
- no credentials, cookies, or auth headers are ever sent;
- the timeout is 5 seconds and the body is never read — only the final URL matters;
- `RHP_RESOLVE_MAP_SHORT_LINKS=0` disables it entirely for a host with no outbound network.

Tests feed the resolver a redirect to `169.254.169.254` and assert it refuses *and* never issues the
request.

## Secrets

- All secrets live in `.env` (gitignored, dockerignored) or the hosting platform's secret store.
- No credential ever gets a default in `config/settings/production.py`; a missing or placeholder
  `DJANGO_SECRET_KEY` stops the boot.
- `DJANGO_SECRET_KEY` is 64 random bytes (`make env` generates it). Rotating it invalidates sessions
  and password-reset links; that is the intended effect.
- Never log secrets, session ids, password-reset tokens, or tenant PII.
- Database credentials follow the same rules; the application role is not a PostgreSQL superuser.

## Transport and browser hardening

Production settings enforce: `SECURE_SSL_REDIRECT`, HSTS (1 year, subdomains, preload) once TLS is
on, `Secure` + `HttpOnly` + `SameSite=Lax` cookies, `SECURE_CONTENT_TYPE_NOSNIFF`,
`SECURE_REFERRER_POLICY=same-origin`, and `X_FRAME_OPTIONS=DENY`. CSRF protection is on for every
unsafe method. TLS terminates in Caddy with automatic certificates.

Because gunicorn is reached over plain HTTP inside the Compose network, the forwarded-proto header is
what marks a request as secure. Enabling SSL redirection without that header is a misconfiguration
that the production settings reject at startup.

## Sessions and authentication

- Django's session framework with database-backed sessions; no tokens in URLs. Sessions last 12 hours
  in production, with `HttpOnly`, `SameSite=Lax`, and `Secure` cookies.
- Passwords hashed with Django's default hasher (never reversible storage) and validated by Django's
  four default validators (length, common passwords, numeric-only, similarity to the account).
- Sign-in failures always return the same generic message, whether the account exists, is inactive,
  or the password is wrong - no user enumeration. Successful and failed attempts are logged.
- Password reset returns the same page and the same message for a known and an unknown address, and
  the link is single-use and expires (see the rate-limiting section below and ADR-004).
- Sign-out requires a POST, so a link or image cannot sign a user out.
- Staff accounts get MFA in Phase 12, before real tenant data is loaded.
- Admin-created tenant accounts and invitations are the only way tenants get access; there is no
  public sign-up. Staff never choose or see a tenant password: the invitation asks the tenant to set
  one.

## Rate limiting and lockouts

The application-level floor is implemented in `apps/accounts/throttle.py` (ADR-004):

| Control | Default | Setting |
| --- | --- | --- |
| Failures before a lockout | 5 | `RHP_LOGIN_MAX_ATTEMPTS` |
| Rolling window that counts failures | 15 min | `RHP_LOGIN_WINDOW_MINUTES` |
| Lockout duration after the last failure | 15 min | `RHP_LOGIN_LOCKOUT_MINUTES` |
| Honours `X-Forwarded-For` for the client address | off | `RHP_TRUST_PROXY_HEADERS` |

- Failures are counted **per account and per address**, so both password spraying across accounts and
  hammering one account are slowed.
- The check runs before authentication, so a locked-out client never reaches the password hasher, and
  the refusal message is generic.
- A successful sign-in clears that account's recorded failures; a retry while locked does not extend
  the lockout.
- The ledger is a database table (`LoginAttempt`), not a cache, because RHP runs several gunicorn
  workers without Redis - an in-process cache would multiply the effective budget per worker.
- `X-Forwarded-For` is trusted only when a proxy is actually in front of the app. The production
  Compose stack enables it for Caddy and the production settings warn when a TLS proxy is configured
  with the flag off, because every request would otherwise appear to come from the proxy and one
  attacker could exhaust the shared budget.
- **Support path**: `python manage.py reset_login_attempts <username>` (or `--ip <address>`) clears
  the ledger for an account or address. Locked-out users are told to wait; staff can clear it.
- Phase 12 adds proxy-level limiting, alerting on repeated lockouts, and MFA.

## Invitations and account lifecycle

- A tenant account is created by staff (`/manage/accounts/new/`, or `manage.py create_tenant`) with an
  unusable password and an invitation link that the tenant uses to choose their own password.
- Invitation tokens are single-use (Django's password-reset signature changes as soon as a password
  is set or the invitee signs in), expire with `RHP_LINK_TIMEOUT_DAYS` (7 days), and are signed with
  a distinct salt so an invitation link can never be replayed as a password-reset link.
- Deactivating an account invalidates its outstanding invitation immediately, and a deactivated
  account cannot sign in.
- Accounts are deactivated, never deleted, so history and audit trails survive. Invitations and
  resets are addressed by the account's email, which is why the create form requires a unique
  address.

## Financial integrity

Charges and payments are append-only. Corrections are reversal or adjustment rows with an actor and a
timestamp; history is never rewritten in place. Balances are derived from ledger entries, so a wrong
balance is a wrong entry, not a wrong number (ADR-008).

- **Nothing stores a balance, and nothing stores a charge's status.** Both are computed from the
  entries by `apps.ledger.services.build_ledger`, so four screens cannot hold four opinions and a
  nightly recalculation cannot go stale.
- **Amounts are positive with an explicit direction** (`Charge.direction`, `Payment.kind`), never a
  negative number, and always `DecimalField(12,2)`. A float never touches money, including inside the
  audit trail, where amounts are stored as strings.
- **Immutability is enforced in layers**: `save()` freezes financial fields once written (the only
  permitted change is a payment's `PENDING → CLEARED`/`VOID` lifecycle), `delete()` raises on both
  models, both foreign keys to `leases_lease` are `PROTECT`, and both models are registered read-only
  in the Django admin. There is no edit or delete route anywhere.
- **Known limit, stated rather than implied:** `Model.objects.filter(...).delete()` bypasses
  `Model.delete()`. The application never calls it; it remains possible from a shell, and true
  database-level immutability would require triggers (Phase 12). Nothing in the application can
  rewrite or remove an entry.
- **Every mutation writes an audit event** (actor, action, target, tenancy, summary, small metadata,
  timestamp) inside the same transaction as the change, so an event can never describe a write that
  rolled back. `AuditEvent` itself refuses updates and deletions.
- **Money that only exists as a promise is modeled as such.** A `PENDING` payment moves no balance;
  only cleared, unreversed money does. Voiding and reversing are separate acts, each recorded.
- **Who may do what:** managers may view ledgers, generate rent, add a manual charge, record a payment
  and clear or void a pending one; **adjustments and reversals are admin-only**, because they change
  what history means. A maintenance user has no access to the accounting area.
- **No card or bank credential is ever stored** — not a number, not a token. A payment records an
  amount, a date, a method label and a free-text reference. Phase 11 integrates a provider; when it
  does, the credential belongs to the provider, never to this database.

## Dependencies and updates

Runtime dependencies are pinned in `uv.lock` and built into the image; the front-end build pins one
package (`@tailwindcss/cli`). Updates go through a branch, CI, and a rebuild — never a hot patch in a
running container. `python manage.py check --deploy` runs in CI.

## Tests that must exist for each phase

- A tenant cannot read another tenant's object (lease, document, charge, ticket, attachment).
- A tenant cannot reach staff routes; a maintenance user cannot reach admin routes.
- A guessed or enumerated id for another tenancy returns 404, not the object.
- Internal notes are never visible to tenants.
- Balance calculations, partial payments, reversals, and overdue determination (Phase 4).
- Uploads reject disallowed types and oversize files (Phase 6/7).

Phases 1–3 satisfy the first four: the tests live in `tests/accounts/`, `tests/properties/` and
`tests/leases/`. The lease suite asserts the role matrix route by route (403 for the wrong area, 302 to
sign-in when anonymous), that a tenant who is not on a lease gets 404 from the tenant area, that the
tenant document URL carries no id, and that an ended lease refuses a direct POST as well as hiding the
form.

Phase 4 satisfies the fifth, in `tests/ledger/`: the balance is the charges minus the cleared payments
(including part payments, credits and overpayments), a reversal restores the balance while leaving the
original untouched, overdue is only ever money still owed past its due date, and a charge or payment
cannot be edited, deleted, reversed twice, or written on a draft. `tests/audit/` asserts the trail: an
actor and an action per change, amounts recorded without floating point, and events that refuse to be
changed or removed. `tests/ledger/test_authorization.py` walks every accounting route for each role,
including that a manager cannot reverse or adjust.

## Reporting a problem

Security issues are handled privately: note the affected version, the reproduction steps, and the
potential impact, and send it to the RHP maintainer rather than opening a public issue.

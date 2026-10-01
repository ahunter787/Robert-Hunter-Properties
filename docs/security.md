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

## Identifiers and enumeration

Externally exposed resources that a tenant could enumerate (documents, maintenance requests,
attachments, lease files) use `UUIDField` primary keys or a random slug. Sequential integer ids stay
internal. Authorization is enforced regardless — unguessable ids are defence in depth, not the control.

## Uploads

Applies from Phase 6 (documents) and Phase 7 (maintenance photos):

- Allow-list extensions and content types; reject everything else.
- Enforce a maximum size at the form, the view, and the reverse proxy.
- Store under a randomized filename; never reuse the client-supplied name on disk.
- Never execute uploaded content; never serve it with a content type that browsers execute.
- **Every download is permission-checked.** Uploaded files are never reachable through a static file
  handler or the reverse proxy, and `MEDIA_URL` is only wired up in development.
- Keep uploaded files outside the web root (`media_data` volume, mounted privately).

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

- Django's session framework with database-backed sessions; no tokens in URLs.
- Passwords hashed with Django's default hasher (never reversible storage).
- Login: generic error messages (no user enumeration), rate limiting, and audit logging of failed
  attempts land in Phase 1; password reset is implemented without revealing whether an account exists.
- Staff accounts get MFA in Phase 12, before real tenant data is loaded.
- Admin-created tenant accounts and invitations are the only way tenants get access; there is no
  public sign-up.

## Financial integrity

Charges and payments are append-only. Corrections are reversal or adjustment rows with an actor and a
timestamp; history is never rewritten in place. Balances are derived from ledger entries, so a wrong
balance is a wrong entry, not a wrong number.

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

## Reporting a problem

Security issues are handled privately: note the affected version, the reproduction steps, and the
potential impact, and send it to the RHP maintainer rather than opening a public issue.

# Security

## General ledger — ADR-032

Only the accounting posting service writes journals. It refuses manual entries against tenant AR,
accounts payable, deposits held, tenant credits, undeposited funds or bank accounts; those move only from
kernel source events. Journals and lines are immutable, source-keyed and posted in the same transaction as
their source. The accounting screens (`/manage/accounting/`: overview, chart, journals, controls, opening balances) are
manager-only on the server; journals carry a lease/property dimension and are never exposed through a
tenant-scoped query. Opening balances are a reviewed manager action, audited and immutable once posted. Security-deposit
received/returned movements post through the same kernel contract; a retention posts nothing until its E6
charge, and the deposit control difference is reported rather than adjusted.

## Move-out settlement — ADR-031

A retained deposit is applied to a bill only through the same manager-only signed review as held credit;
the action lists the deposit as its source, validates availability and the target obligation server-side,
and records an append-only application (an undo is a release row). The final statement is derived from
the scoped ledger and deposit register; issuing it is manager-only and appends an immutable audit snapshot
with the forwarding address and itemised deposit reasons. A tenant sees only their own statement through
`visible_for`, and staff-only deposit evidence links are never rendered to them. The forwarding address is
personal data stored on the lease and shown on the staff statement screen; it is not exposed to other
tenants. No statutory deadline is enforced until the owner supplies the operating jurisdiction.

## People and portal logins — ADR-030 M2b

A lease party is a `contacts.Person`; a portal login is an optional link on that person's lease
membership and is the only path to tenant-scoped data. Linking an account is manager-only, validated
server-side (tenant role, active account, not linked elsewhere), and atomically updates the person and
every membership that mirrors the link. A person without a login has no portal identity and therefore
no scoped rows — that is the access model, not a display rule. The People screen is manager-and-above;
creating a tenant account creates its person, and account/role changes keep their existing gates.

## Upcoming tenancies — ADR-029 M2a

A `FUTURE` tenancy is visible to its own tenant (the same `visible_for` scoping as any lease) but posts no
money, so there is nothing to expose or protect on the payment page. It cannot be ended or settled, and a
manager screen read that starts a due tenancy is an idempotent, audited transition with a null actor
(system). Deposits received before move-in use the same manager-only register and audit event as any
deposit.

## Accounting kernel consolidation — ADR-028

Single allocation engine: balances are read from recorded `FundsApplication` rows; the retired read-time
projection cannot allocate. Opening charges are created only by `ledger.services.create_charge`, which
re-checks the account state and records `CHARGE_CREATED`; the reviewed starting-account workflow is the
only `openings` path and is manager-authorized. No direct charge write exists outside the ledger app.

Security deposits are manager-only: `apps/ledger/deposits.record` reauthorizes the act through the view's
manager gate, refuses a settled account and any release beyond what is held, requires a reason for a
retention or a "not collected" statement, and appends `DEPOSIT_CHANGED` in the same transaction. Entries
are append-only (`save()` refuses edits, `delete()` raises); evidence is a private, lease-scoped staff
document. Tenants see the held amount, never another tenancy's deposit, and the register is not a credit
they can apply. The agreed deposit cannot be edited below money already held. Settlement is refused
while anything is held or the agreed deposit has no recorded outcome.

## Held credit and repayments — October 21

Manager/admin confirmation is required to apply/release held credit or set/replace repayment terms.
Services lock the tenancy, validate source/target scope and available amounts, and reject stale signed
reviews. Tenants see their own public schedule/application history; private agreement source/reasons
remain staff-only. Settled locks and immutable correction history apply to all new mutations.

## Simple cutover — ADR-027

Only administrators set the installation financial date; manager-and-above roles review and confirm
individual starting accounts. Services reauthorize active actors, lock state and verify signed reviews.
Notes/evidence are staff-only; tenant views expose only their account entry and explicitly shared files.
Evidence selection is scoped to the lease and revalidated at confirmation. Opening credits are not
receipts. Archived development backups include private data and stay in restricted ignored storage.

## Reviewed existing-history recovery — October 20, 2026

Manager/admin recovery of a missing billing start date uses a 30-minute signed review bound to
the actor, lease, date, reason and financial/lease-state fingerprint. Confirmation revalidates under
the lease lock. Wrong actors/leases, stale state, signature changes, expiry and replay cannot save.
Ended/settled accounts and records without existing charges are ineligible. Preview, Back and Cancel
write nothing. Confirmation only saves the billing start date and audit event; charges/payments and
their existing authorization, balances and history remain unchanged. No live repair runs automatically.

## Existing portal safeguards

Phase 8 communications follow ADR-024: explicit tenant participants, frozen household conversations,
snapshot announcement recipients, private UUID downloads, append-only messages/versions, and manager
only operational controls. Every read/send/read-position/download is independently scoped. New lease
members never inherit old conversation or announcement history. Follow-up is explicit and independent
of settlement. Email uses neutral links, rechecks authorization and excludes the sender; ambiguous
delivery is not proof of failure or permission for silent duplicate retry. Workers have no inbox.

RHP will hold tenant identity data, lease documents, and financial records. Security is a
first-class requirement, not a hardening phase: the rules below are binding from the first feature
phase onward. Phase 12 adds the operational layer (backups, monitoring, MFA, penetration testing).

## Authorization

Phase 9 metric/detail and activity endpoints independently require manager access. Role-change
events are superadmin-only. Activity renders action labels and whitelisted object context, never
unrestricted summaries/metadata, communications bodies or private attachments. Missing targets do
not grant guessed links. Worker/tenant direct access remains forbidden (ADR-025).

Maintenance entry permission records a tenant's request-specific authorization for RHP staff
and assigned repair professionals, not landlord self-authorization or an exemption from entry
notice requirements. Manager-recorded offline authorization/withdrawal requires a source note
enforced by the service. The note is append-only audit metadata, never a tenant timeline body
or email; the public change retains the recording actor and permission state. Property/unit
selectors are scoped in forms as well as checked by the request-creation service.

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
   document = get_object_or_404(Document.objects.visible_to(request.user), pk=pk)
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
   Empty-property deletion additionally requires the exact typed phrase `confirm delete`, validated
   on the server. The normal removal action is taking the property out of service; neither that
   action nor this presentation migration deletes its units, lease history, or financial entries.
8. **Operations are not site administration.** Managers can create/invite tenant accounts, maintain
   tenant details and activate/deactivate them. Role changes, Django administration, site configuration
   and destructive deletion remain administrator duties. Maintenance workers cannot use tenant-account
   administration or read general portfolio documents; their access is assigned-request context only.

## Identifiers and enumeration

E11 request sections do not widen access: conversation IDs must belong to the authorized UUID
request and, for tenants, their own audiences. Internal notes and administrative/financial sections
are rejected server-side when forbidden. Tenant write controls resolve the selected tenancy's current
occupancy; another current tenancy does not make a former tenancy writable. Historical request
headers use a location icon if the existing own-tenancy photo endpoint refers to a different lease.
Workers get no general portfolio-photo URL. Maintenance milestones are scoped existing updates,
never a tenant rendering of raw audit records. Account sections retain the existing manager gate,
with role changes still superadmin-only.

Maintenance routes use UUID public identifiers. Managers see the portfolio; employees see
assigned requests only. Tenant visibility is an explicit tenancy audience, never inferred
from a current unit occupant. Audience-specific replies/files cannot leak across tenancies.
Costs, invoices and recharge controls are manager-only; raw audits never enter tenant views.
Services enforce these boundaries for every mutation. See ADR-023.

Externally exposed resources that a tenant could enumerate (maintenance requests, attachments, lease
files) use separate UUID public identifiers or a random slug, and sequential integer ids stay internal where a
new surface can afford it. Authorization is enforced regardless — unguessable ids are defense in depth,
not the control.

**Documents are the deliberate exception** ([ADR-022](decisions/ADR-022-documents.md)). A `Document` has
an integer primary key and the tenant's download URL carries it (`/lease/documents/<pk>/download/`). The
rule the specification sets is about *guessing a media path*, not about ids, and the control is the
tenancy scope rather than the id: `Document.objects.visible_to(user)` filters to `tenant_visible=True`
and the caller's own lease or tenant, and the view resolves `get_object_or_404` over that scope — so
another tenancy's id answers **404, not 403**, because a refusal must not confirm that the document
exists. The old "no id in the URL" lease-document view is gone: the lease is now one document row among
many, so the general case cannot keep that shape.

## Uploads

E11 adds one optional unit photo. Only managers/admins write it through the validated unit form;
the Django admin excludes this field. Staff reads use `/manage/units/<pk>/photo/` and require a
manager role. Tenant reads use `/lease/location-photo/unit/` or `…/property/`, resolving only the
same authorized non-draft lease shown by the tenant portal (current, otherwise latest).
There is no tenant-submitted unit id and no worker portfolio-photo access. Files remain private,
randomly named, JPEG/PNG/WebP under existing upload/dimension limits. Replaced/removed unit photos
are deleted after commit, and failed portal writes clean up new bytes. Missing files return 404.

A document has a readable `title` independent of its randomized storage path, and keeps the name it was
uploaded with in `original_name` (`apps/documents/models.py`). Staff supply the title; when it is blank
the uploaded name is used. Templates escape both, and viewing or downloading still passes through the
permission-checked document view. A friendly name never grants access to a file.

In force since Phase 2's banner photos and extended in Phase 3 by the lease document; the document rules
moved into `apps/common/files.py` in Phase 6 ([ADR-022](decisions/ADR-022-documents.md)), and maintenance
photos arrive in Phase 7:

- Allow-list extensions and content types; reject everything else. Banners and tenant photos accept
  JPEG, PNG, and WebP only — SVG is refused because it can carry script. Documents accept PDF, JPEG,
  PNG, WebP, Word, Excel, CSV and plain text (`DOCUMENT_EXTENSIONS`). The image rules are implemented
  once, in `apps/common/images.py`; the document rules once, in
  `apps/common/files.py::validate_document_upload`, which the upload form calls.
- Enforce a maximum size at the form (`RHP_MAX_UPLOAD_MB`, default 5) for documents as well as images,
  plus a maximum pixel dimension for images; the reverse-proxy body limit is Phase 12.
- Store under a randomized filename (`property_banners/<uuid>.<ext>`, `tenant_photos/<uuid>.<ext>`,
  `documents/<uuid4hex><ext>`); never reuse the client-supplied name on disk.
- Never execute uploaded content; never serve it with a content type that browsers execute.
- **Every download is permission-checked.** Uploaded files are never reachable through a static file
  handler or the reverse proxy, including in development. Banners are served by
  `PropertyBannerView`, tenant photos by `TenantPhotoView`/`OwnPhotoView` (each with its own small
  response helper), and documents by `DocumentDownloadView` (staff, any id) and
  `TenantDocumentDownloadView` (the tenant, through `Document.objects.visible_to`); each checks its
  permission first, and documents all serve through `apps/common/files.py::document_response`
  (ADR-006, ADR-007, ADR-009, ADR-022). A document whose bytes are missing answers **404, not 500**,
  on both document views.
- **Removing a document is an admin's act, with a required note** (the owner's P6-Q4). Managers may file
  and read documents; `DocumentRemoveView` mixes in `AdminRequiredMixin`, so a manager gets **403**.
  `apps/documents/services.py::remove_document` refuses an empty note, deletes the row *and* the stored
  bytes, and writes a `DOCUMENT_REMOVED` audit event carrying the title, the category, what it was
  attached to, the actor and the reason. A superseded document is kept alongside instead.
- Downloads carry `Cache-Control: private` and `X-Content-Type-Options: nosniff`, so a shared cache
  never holds a tenant document or photo and a browser never sniffs one into a different type.
- **A tenant photo is personal data** (ADR-009). It is uploaded by staff on the tenant's
  account page, served only through `TenantPhotoView` (staff) or `OwnPhotoView` (the tenant, whose URL
  carries no id), and never shown to another tenant — there is no tenant-facing directory.
- Keep uploaded files outside the web root (`media_data` volume, mounted privately).
- Replacing or removing an image deletes the stored file, and deleting a property deletes its banner. A
  document row's file is deleted when the row is deleted (a `post_delete` signal in
  `apps/documents/signals.py`), so an admin's removal takes the bytes with it; a lease or a property
  that still has documents cannot be deleted at all — those foreign keys are `PROTECT` — so uploads do
  not accumulate as orphans.

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

The October 20 financial-clarity reading surface shares existing authorized lease views and
already-scoped ledger projections. Template styling never authorizes access or changes balances.
Tenant summaries do not receive staff controls, correction reasons or raw audit history. Expected
payments remain excluded from balances; colors make no claim of bank verification or cash movement.

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
- **Who may do what:** managers perform portfolio operations, including charges, payments, adjustments,
  reversals, tenant invitations and activation, settlement, and financial reopening. Administrators retain
  role changes, Django administration, site configuration, and destructive deletion. A maintenance user has
  no access to the financial area.
- **A settled account is locked in services.** Posting charges, recording/clearing/voiding/reversing a
  payment, and creating an adjustment all refuse until a manager explicitly reopens the financial account
  with a reason. Reopening never restores occupancy.
- **No card or bank credential is ever stored by RHP.** A payment records an
  amount, a date, a method label and a free-text reference. Phase 11 integrates a provider; when it
  does, bank linking and tokens belong to the provider, never to this database.
- **Property accounting (E10) is a second reading, not a second set of money.** Journals post from the
  ledger's own records once per source row and are immutable once posted; a correction is a reversing entry
  with an actor and a reason. The AR control account must equal the sum of tenant-ledger balances (a tested
  invariant), so the two readings cannot drift. The chart of accounts and manual journals are administrator
  acts; journals, disbursements and reconciliation are manager-and-above; **no tenant route reaches any
  accounting record**. Imported bank statements are reconciled against entries and never rewrite them; a
  reconciled period is reopened with a reason, as a settled account is ([ADR-026](decisions/ADR-026-property-accounting.md)).

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
- Uploads reject disallowed types and oversize files (documents in Phase 6, maintenance photos in
  Phase 7).

Phases 1–3 satisfy the first four, and Phase 5 extends the first to money: a tenant's dashboard and
payment history show only their own tenancy (there is no id in either URL), and the tests live in
`tests/accounts/`, `tests/properties/` and `tests/leases/`. The lease suite asserts the role matrix route
by route (403 for the wrong area, 302 to sign-in when anonymous, and a staff account sent on to
`/manage/` from the tenant pages), that a tenant who is not on a lease gets 404 from the tenant area, and
that an ended lease refuses a direct POST as well as hiding the form.

Phase 4 satisfies the fifth, in `tests/ledger/`: the balance is the charges minus the cleared payments
(including part payments, credits and overpayments), a reversal restores the balance while leaving the
original untouched, overdue is only ever money still owed past its due date, and a charge or payment
cannot be edited, deleted, reversed twice, or written on a draft. `tests/audit/` asserts the trail: an
actor and an action per change, amounts recorded without floating point, and events that refuse to be
changed or removed. `tests/ledger/test_authorization.py` walks every accounting route for each role,
including that managers may reverse and adjust while destructive deletion and role changes remain restricted.

Phase 6's tests cover the last item, in `tests/documents/` and `tests/leases/`: the allow-list and the
size cap refuse a disallowed or oversize upload before a row is written, a stored name is randomised and
the uploaded name is kept only as metadata, a staff-only document is absent from the tenant's list,
another tenancy's id answers 404 from the download (and never appears in the list), the file is served
only through the permission-checked view, and removal is refused to a manager and writes an audit event
when an admin does it with a note. The migration that turns each lease's single file into a document row
is covered where the lease suite lives.

## Reporting a problem

Security issues are handled privately: note the affected version, the reproduction steps, and the
potential impact, and send it to the RHP maintainer rather than opening a public issue.

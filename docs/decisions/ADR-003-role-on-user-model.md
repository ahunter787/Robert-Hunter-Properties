# ADR-003: One `role` field on the user model gates the portal

- **Status:** Accepted (Phase 1)
- **Date:** 2026-10-01
- **Context:** Phase 1 authentication and authorization

## Context

The specification defines five roles — `SUPERADMIN`, `ADMIN`, `MANAGER`, `MAINTENANCE`, `TENANT` —
with different areas of the application, and requires that authorization be enforced server-side
rather than by hiding navigation. Phase 1 also has to separate tenant-facing screens from staff
screens structurally, and decide what an unauthorized request should return.

Django already ships `is_staff` (may enter the admin site) and `is_superuser` (bypasses permission
checks) plus a groups/permissions system.

## Decision

1. **One `role` field on `accounts.User`** (`CharField` with `TextChoices`, default `TENANT`,
   indexed), not a groups/memberships table and not a second profile table. The model exposes
   `is_rhp_staff`, `is_admin_or_above`, `is_superadmin`, and `is_tenant` for the checks views need.
2. **`is_staff`/`is_superuser` keep gating `/admin/`; `role` gates the RHP portal.** They are related
   but separate: the Django admin stays the back office, while RHP screens check the role.
   As a safety net, a `is_superuser` account passes every role check regardless of its `role` value,
   so a stale role can never lock out a superuser.
3. **Route separation by URL prefix and namespace**: `/account/` (sign-in and self-service) and
   `/manage/` (staff). Staff-only views mix in a permission mixin; nothing relies on template
   conditionals.
4. **Two distinct denial responses**:
   - authenticated user reaching an area their role may not use → **403** (`templates/403.html`);
   - an individual record outside the caller's tenancy → **404**, so ids cannot be probed.
5. **Role changes require `SUPERADMIN`**; account administration (list, create, deactivate,
   re-invite) requires `ADMIN` or above; `MANAGER` and `MAINTENANCE` reach `/manage/` only.
6. Tenant-owned rows are read through `tenant_scope(user, queryset, owner_field)`, which returns the
   full queryset for staff and the owner-filtered queryset for a tenant. Phase 2+ reuses it for
   leases, charges, documents, and maintenance requests.

## Consequences

**Positive**

- Permission checks are one-line reads (`if request.user.is_admin_or_above`) and trivial to test.
- Role changes are a single row update with an audit log entry, not a membership join.
- The 403/404 split gives tenants a clear "you can't go there" while making record enumeration
  useless.
- Adding a role later is a `TextChoices` addition plus its gate.

**Negative / accepted trade-offs**

- **One role per person.** A maintenance technician who is also a manager needs two accounts, or a
  future role-composition change. Nothing in Phases 1–12 requires that yet; a membership table can
  replace this without touching call sites if the helper properties stay the interface.
- Role checks live in mixins/decorators, so a new view can forget one. Mitigated by the authorization
  test module, which asserts every management route by role, and by `tenant_scope` for object access.
- Emails are unique per account (`TenantCreateForm`), so a household sharing one address needs a
  separate address or a superadmin edit. Chosen deliberately: invitations and password resets are
  addressed by email, and duplicates make "which account is this?" ambiguous.

## Alternatives considered

- **Django groups + permissions**: more machinery than five fixed roles need, and every check becomes
  a permission lookup plus fixtures. Rejected for now; if RHP ever needs per-object permissions,
  Django's permission framework is still available alongside `role`.
- **A separate `Role` model with a membership table**: supports multiple simultaneous roles, at the
  cost of joins on every request and more UI. Not justified by the specification.
- **403 for everything**: leaks which record ids exist.
- **404 for everything**: makes "you are signed in but not allowed here" indistinguishable from a
  broken link, which is worse support and worse security communication.

# Phase 1 — Authentication and authorization

**Status:** Complete
**Milestone:** 1 — A deployed portal where RHP can create tenant accounts and tenants can sign in safely
**Specification:** `docs/harness/master-spec.md`, `PHASE 1 — AUTHENTICATION AND AUTHORIZATION`

## Scope as specified

Sign-in and sign-out, password reset, accounts created by RHP for tenants, an invitation path that does
not email a password, and a role model that decides what each person can reach. Staff and tenant areas
are separated by route, and authorization is enforced on the server for every sensitive object.

## What exists today

- **Models** (`apps/accounts/models.py`): `User` (role on the user, `AUTH_USER_MODEL`), `Role`
  (`SUPERADMIN`, `ADMIN`, `MANAGER`, `MAINTENANCE`, `TENANT`), `TenantProfile` (contact details and a
  preferred contact method), `LoginAttempt` (the throttle).
- **Permissions** (`apps/accounts/permissions.py`): `RoleRequiredMixin` and its concrete subclasses
  (`StaffRequiredMixin`, `ManagerRequiredMixin`, `AdminRequiredMixin`, `TenantRequiredMixin`,
  `SuperadminRequiredMixin`), `TenantAreaMixin` for the tenant pages, `role_required` for function views,
  and `tenant_scope(...)` for querysets. Wrong area → **403**; a record outside the caller's tenancy →
  **404**; staff on a tenant page → redirected to the management area.
- **Screens:** `/account/` (login, logout, password reset, invitation acceptance, profile, dashboard),
  `/manage/` (staff landing and account administration: list, create, deactivate, re-invite, role change,
  photo).
- **Invitations:** a single-use link with an expiry, sent through the configured email backend; a
  deactivated account cannot sign in; password reset never reveals whether an address exists.
- **Throttling:** `LoginAttempt` plus `ThrottledLoginView`.
- **Operational authority:** managers create and invite tenants and activate or deactivate tenant
  accounts. Admins maintain account photos for any account; managers and tenants maintain their own
  photo. Role changes remain superadmin-only; Django administration, site configuration, and destructive
  deletion stay outside manager authority (ADR-003, ADR-020).

## Decisions that govern it

| Record | What it settled |
| --- | --- |
| [ADR-003](../decisions/ADR-003-role-on-user-model.md) | Role as a field on the user, the route/namespace split, 403 for the wrong area and 404 for someone else's record; amended by E4 so staff on a tenant page are redirected instead |
| [ADR-004](../decisions/ADR-004-invitations-and-throttle.md) | Single-use invitation links, no passwords by email, throttled sign-in |
| [ADR-009](../decisions/ADR-009-tenant-photos.md) | Account photos stored under randomized names and served through permission-checked views; admins may set any account's photo, account owners may replace their own |

`docs/security.md` carries the threat model and the per-role matrix.

## Extensions filed under this phase

None. (P3-E1, P4-E2 and P4-E4 all build on this phase's permission classes but change other phases.)

## Acceptance criteria and evidence

- [x] A tenant cannot reach management routes — `tests/accounts/`, `tests/leases/test_authorization.py`
- [x] Tenant A cannot read tenant B's data (scoped queries; 404 rather than 403, so ids cannot be probed)
- [x] A maintenance user reaches `/manage/` and nothing administrative
- [x] An admin can administer accounts: list, create, invite, deactivate, re-invite
- [x] Role changes require a superadmin; invitations and resets are single-use
- [x] A deactivated account cannot sign in, and password reset does not confirm an address

## Deliberately not here

Two-factor authentication for staff, session hardening and log retention (Phase 12); tenant-visible
account history. Staff "view as tenant" is not a feature: a staff account is sent to the management area
instead, because it has no tenancy of its own to show.

## Known gaps and defects

- A tenant's **contact notes** are recorded but only surface on the management account screens; the phase
  guide has carried this as "surface them on the tenancy screens" since Phase 5.
- There is no self-service **email change** or account closure for a tenant; both are management acts.
- `TenantAreaMixin` denies *all* staff, including a staff member who is also a tenant of RHP. Nobody is
  both today; if that changes, the rule needs a tenancy check rather than a role check.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P1-Q1 | Should a staff account that is also a tenant be able to use the tenant pages? | Not now — no such account exists, and the redirect keeps one rule. Revisit if it happens. | *(awaiting)* |
| P1-Q2 | Do you want tenants to change their own email address, or is that a management act? | Keep it a management act: it is how an invitation and a reset reach the right person. | *(awaiting)* |

## How to verify it

Sign in as `rhpadmin` (management) and as a tenant; try `/manage/` as the tenant (403, and the tenant pages
redirect staff to `/manage/`). `make test` covers the matrix in `tests/accounts/` and
`tests/leases/test_authorization.py`. The mail sink at `http://10.60.0.227:8025` shows invitation and reset
email without sending anything real.

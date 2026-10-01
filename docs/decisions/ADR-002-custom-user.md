# ADR-002: A custom user model exists from Phase 0

- **Status:** Accepted (Phase 0)
- **Date:** 2026-09-30
- **Context:** Phase 0 foundation; relied on by Phase 1 (authentication and authorization)

## Context

Phase 0's rule is that domain apps are created only when their phase begins, so the repository does
not fill up with empty packages. Phase 1 introduces the RHP role model (`SUPERADMIN`, `ADMIN`,
`MANAGER`, `MAINTENANCE`, `TENANT`) and the tenant profile, which belong on the user model.

Django's documentation is explicit: `AUTH_USER_MODEL` must be set at the start of a project because
changing it after the first migration is not supported — the swap requires manual surgery on every
foreign key that points at the user table, plus migration-history repair.

## Decision

Create `apps/accounts` in Phase 0 containing **only** the custom user model:

```python
class User(AbstractUser):
    """Phase 1 adds roles, the tenant profile, and staff permissions."""
```

and set `AUTH_USER_MODEL = "accounts.User"` before the first migration is applied anywhere.

No role field, no profile fields, and no authentication views are added yet: an empty subclass is the
smallest thing that fixes the model identity. Phase 1 fills it in.

## Consequences

**Positive**

- Phase 1 adds roles and profiles with ordinary `AddField` migrations instead of an unsupported model
  swap.
- Tenant/staff identity lives on one model from the beginning, so `request.user` is always the RHP
  user.
- The app label is pinned (`label = "accounts"`), keeping the table name `accounts_user` and the
  `"accounts.User"` reference stable regardless of the package path (`apps.accounts`).

**Negative / accepted trade-offs**

- The "no app before its phase" rule gains one documented exception. It is recorded here so a future
  reader does not treat it as an accident.
- Phase 0 ships a model with no behaviour of its own; its only job is to exist and be migrated.

**Operational requirement**

Because `AUTH_USER_MODEL` is fixed now, any database created before this decision (there is none in
production) must be recreated rather than migrated. Development databases are disposable; in Phase 0
the only data that exists is the superuser created by `make superuser`.

## Alternatives considered

- **Use Django's default `auth.User` and swap in Phase 1**: rejected — that is precisely the
  unsupported migration Django warns about, and it would put the swap in the middle of the project
  when the most real data exists.
- **Use the default user and attach roles through a `Profile` one-to-one**: workable, but it splits
  identity across two tables forever, complicates permissions and admin, and still cannot add
  required fields to the user itself.
- **`AbstractBaseUser` with a hand-written manager**: maximum control, but it re-implements password
  hashing, permissions, and admin integration that `AbstractUser` already provides. Not worth it
  before a single requirement demands it.

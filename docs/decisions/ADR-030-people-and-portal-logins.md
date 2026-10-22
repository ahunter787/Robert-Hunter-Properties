# ADR-030 — People are master data; a portal login is optional

- **Status:** Implemented, 2026-10-22 (M2b of [ADR-029](ADR-029-lease-future-and-people.md) D2).
- **Date:** 2026-10-22
- **Related:** [ADR-029](ADR-029-lease-future-and-people.md) (M2 decision and evidence),
  [ADR-008](ADR-008-rent-ledger.md) (tenant scoping and append-only history), [ADR-003](ADR-003-role-on-user-model.md)
  (one user model, role on the account), [ADR-016](ADR-016-retroactive-onboarding.md) (retired E4),
  [ADR-028](ADR-028-one-kernel.md) (party conformance row).
- **Evidence:** the product observations recorded in ADR-029 D2 — PropertyBoss's Contacts Navigator
  (tenants, adult occupants, guarantors, authorised contacts, with an optional per-contact portal login),
  DoorLoop's portal access managed independently of the tenancy, AppFolio's resident identity running
  from application through move-in and renewal. No new vendor research was needed; this ADR is the
  implementation record for that decision.

## Context

RHP's tenancy party was `LeaseTenant.tenant → accounts.User`. That single link made the login the
person: a co-occupant, guarantor or authorised contact could not be recorded without an account, and
the party's name lived on the account row. The kernel rule is the opposite — a person is who owes or
occupies; a login is a permission to see the portal. The E10/M2 evidence in ADR-029 established the
target shape; this record fixes where the data lives and how existing rows move.

## Decision

1. **New app `apps/contacts`, model `Person`.** Master data only: first/last name, email, phone,
   optional `portal_user` (one-to-one to `accounts.User`, `SET_NULL`), timestamps. No password, no
   role, no second authentication model. A person can exist with no login; a login can belong to at
   most one person (database one-to-one).
2. **`LeaseTenant` is a membership**: `person` (required, `PROTECT`), `role`
   (`TENANT`/`ADULT_OCCUPANT`/`GUARANTOR`/`AUTHORIZED_CONTACT`), `is_primary`, and an optional
   `tenant` link to the account. The account link mirrors `person.portal_user`, enforced on save and
   by the linking service, so portal scoping stays one indexed join and cannot drift. The database
   keeps `one_primary_tenant_per_lease` and adds `person_once_per_lease`; the old `tenant_once` rule
   is replaced.
3. **Tenant-scoped reads are unchanged in shape.** Everything that asks "which leases may this user
   see?" still filters `lease_tenants__tenant=user`; only memberships with a linked login match. A
   person without a login simply has no portal identity and no scoped rows, which is the correct
   answer rather than a special case.
4. **The person owns the account link; the membership mirrors it.** `contacts.services.link_portal_account`
   is the one act that attaches an existing tenant account: it validates the account's role, refuses
   an account already linked elsewhere, updates the person, and updates every membership that mirrors
   the link in one transaction. `person_for_user` creates or reuses the person for an account.
5. **Account creation creates the person.** `TenantAccountCreateView` creates the account, its
   `TenantProfile`, and the linked person atomically, so a newly invited tenant can go straight onto
   a lease. The People screen can also create a person without access, and can later link an existing
   unlinked tenant account.
6. **Migration.** `contacts/0001` creates the table. `leases/0014` (non-atomic, because PostgreSQL
   cannot alter the referencing table with pending trigger events in the same transaction):
   every tenant account becomes one person (name/email from the account, phone from its profile);
   each existing membership keeps its login as the membership link and is set to role `TENANT`;
   the membership then becomes person-required and the optional-login shape is recorded. The reverse
   keeps people and links; it cannot invent a login for a party that has none.
7. **Scope of this slice.** The People list/create/detail/edit screens, optional invitation in the
   create form, and account linking. Deliberately not here: guarantor liability enforcement,
   applications/screening, owner/vendor parties, merging duplicate people, and moving communications
   participants from `User` to `Person` (portal conversations remain between accounts). These are
   recorded as open items rather than half-built.

## Consequences

- A lease can record an adult occupant or guarantor without creating an account, and a tenant can
  exist before their login does.
- Existing portal users see exactly the same leases: their memberships kept the account link.
- `lease.tenants`/`tenant_names`/`primary_tenant` now return people; display code reads person names
  and photos through the optional portal link. The lease form selects people and records a role.
- Deleting an account no longer risks erasing the party (person is `PROTECT`-independent); deleting a
  person with tenancy history is refused, as history is append-only.
- Tenancy history is now attached to the person, so a future person merge/rename is a master-data
  correction rather than a rewrite of the ledger.

## Alternatives rejected

- **Keep `LeaseTenant.tenant` and add denormalised names only.** No place for a login-less party,
  and names would drift from the account.
- **Rename `LeaseTenant.tenant` to `portal_user` and drop the mirror.** Every scoped query would
  become a two-hop join and would need a migration of all callers; the mirrored membership link is
  the indexed path and the one the kernel documents.
- **A separate tenant identity model.** Rejected by the one-user-model non-negotiable (ADR-003).

## Open items

- Inviting a person who already exists but has no login is done by linking an existing unlinked
  tenant account; a direct "invite this person" flow from the person screen is a UX follow-up.
- Communications and maintenance audiences still identify people by their portal account, which is
  correct for portal access; a person with no login has no portal conversation by design.
- Person merge/deduplication is not implemented; creating two people for the same human is possible
  and is visible on the People list.
- Guarantor liability is represented (a role) but not enforced in settlement or reporting.

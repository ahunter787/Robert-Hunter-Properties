# ADR-029 — A lease has a future, and a person is not a login

- **Status:** Accepted for staged implementation, 2026-10-21. Owner-directed: industry practice decides
  the method; RHP keeps its Django monolith and its one-user-model rule.
- **Date:** 2026-10-21
- **Related:** [ADR-007](ADR-007-lease-modeling.md) (lease lifecycle), [ADR-020](ADR-020-tenancy-lifecycle.md)
  (occupancy vs financial account), [ADR-028](ADR-028-one-kernel.md) D2/D7 (this is the staged M2 slice),
  [ADR-016](ADR-016-retroactive-onboarding.md) (retired E4), [ADR-008](ADR-008-rent-ledger.md)
  (append-only money); kernel vocabulary in [`docs/kernel/events.md`](../kernel/events.md) and
  [`docs/kernel/scope.md`](../kernel/scope.md).
- **External research (read-only, outside this repository):** the TenantCloud/TurboTenant study at
  `../tenantcloud/findings/` — `02-domain-model.md`, `07-rhp-applicability.md`, `10-capability-parity.md`.
  It is observation and judgement, not a specification; nothing from it is copied here.

## Context

ADR-028 identified two remaining structural gaps in RHP's tenancy model and deferred them to M2:

1. **A signed tenancy that has not started has nowhere to live.** `LeaseStatus` is
   `DRAFT`/`ACTIVE`/`ENDED`. Activating a lease for a future start date stores `ACTIVE`, which the
   screens call active even though the tenant is not in occupancy; and the database's
   `one_active_lease_per_unit` constraint forbids the ordinary renewal case — signing next year's lease
   while this year's is still running. That is not a UI problem: it is a domain state missing from the
   model.
2. **A lease party and a portal login are the same database row.** `LeaseTenant.tenant` points at
   `accounts.User`. That means an adult occupant, a guarantor, or an authorised contact cannot exist on
   the lease without a login, and a person cannot be on two tenancies through two identities. Every
   tenant-facing query is scoped through that one link, so the conflation is load-bearing.

The question is not "what would be convenient" but what the products that do this for a living model,
and then how to reach it without adding a second authentication model (a non-negotiable) or rewriting
the ledger.

## Evidence — how established products model this

| # | Practice | Source | What it shows |
| --- | --- | --- | --- |
| 1 | An upcoming lease is a distinct state, derived automatically from the start date | [TurboTenant: lease profiles](https://support.turbotenant.com/en/articles/4004083-how-to-create-and-manage-lease-profiles-in-turbotenant) | Statuses are assigned automatically: **CURRENT LEASE** (started), **UPCOMING LEASE** ("the lease has a start date and at least one tenant, but the start date is in the future"), **DRAFT** (missing start date or tenants), **PAST**. The landlord cannot pick a status manually. The upcoming profile's only actions are review/complete setup; creating the first charge belongs to the current state. |
| 2 | Pre-move-in money and pre-move-in identity exist before the tenancy starts | [AppFolio Resident Onboarding](https://www.appfolio.com/product-demos/resident-onboarding) | New residents complete a guided checklist *before move-in* — lease signing, **security deposit**, insurance, utilities — inside their own portal identity. The resident account runs "from application through renewal", separate from the lease record. |
| 3 | Lease status includes a future state in an API, not only a screen label | Buildium developer API, lease status enum observed via its published MCP tool description ([list_leases](https://glama.ai/mcp/servers/luthersystems/mcp-server-buildium/tools/list_leases)); official reference: [developer.buildium.com](https://developer.buildium.com/) | Lease status values include `Active`, `Future`, `Past` — a future lease is a first-class record, not an active one with a later date. |
| 4 | Contacts are master data; portal access is a per-contact permission | [PropertyBoss: Tenants](https://support.propertyboss.com/support/solutions/articles/44002816879) | The Contacts Navigator manages "tenants, adult occupants, guarantors, authorized contacts" per lease. A contact record holds communication history and lease associations; **"Allow Login to Web Portal" is a checkbox per contact**, and a portal email is stored separately from the tenant email. Not every lease contact has (or needs) a login. |
| 5 | Portal access is managed independently of the tenancy record | [DoorLoop: portal access after move-out](https://support.doorloop.com/en/articles/13226645-enable-access-to-the-tenant-portal-after-a-lease-ends-or-a-tenant-moves-out) | Tenant portal access ends by default when the lease ends, and can be extended per company/property/lease. Individual tenants can be moved out while the lease continues ("only works if there are multiple tenants on the lease"). The login is a permission on a person, not a property of the tenancy. |
| 6 | Observed in the study: upcoming/past states and a contact/user split | `../tenantcloud/findings/02-domain-model.md`, `07-rhp-applicability.md`, `10-capability-parity.md` | TenantCloud has a lease `FUTURE` state and distinguishes a `Contact` from a `User`; TurboTenant has Upcoming/Current/Past. RHP's single `ACTIVE` bucket and `LeaseTenant→User` link are the outliers. |

What the evidence does **not** say: how RHP should name the status, whether to auto-end a lease at its
term, or how to migrate its existing rows. Those are implementation choices recorded below.

## Decision

### D1 — `FUTURE` is a lease state (M2a, implemented in this slice)

1. `LeaseStatus` gains `FUTURE`. Its meaning is narrow: *the terms are agreed and the tenancy is
   scheduled, but its term has not begun*. `DRAFT` stays the office's incomplete working copy (missing
   dates, missing tenants); a complete scheduled lease is `FUTURE`, not `DRAFT` and not `ACTIVE`.
2. Status is **assigned automatically from the dates**, never hand-picked. Activating a draft with a
   future start date schedules it as `FUTURE`; one whose start date has arrived becomes `ACTIVE`.
   A `FUTURE` lease becomes `ACTIVE` when its start date arrives through an idempotent activation
   (`leases.services.activate_due_leases`) invoked by the management command and, as a fallback, by the
   manager and tenant screens that read leases. This is the same rule TurboTenant applies, implemented
   without a task queue.
3. **A future tenancy takes no obligations.** It is not occupancy (`LeaseQuerySet.current()` stays
   `ACTIVE`-only), creates no rent/NNN/recovery charges, shows no arrears or due-now money, and cannot
   be ended or settled. Its rent schedule is generated up front so the future amounts are known, but
   the first charges are raised when it starts. This follows the kernel rule that a future charge is not
   owed yet.
4. **A future lease may coexist with the active one on the same unit.** The
   `one_active_lease_per_unit` constraint is unchanged and still applies only to `ACTIVE`: signing next
   year's lease while this year's runs is the normal case the missing state was blocking. Nothing else
   is loosened — two `ACTIVE` leases still cannot share a unit.
5. **Deposit money may be received before move-in.** The held-deposit register accepts `RECEIVED` for an
   `ACTIVE` *or* `FUTURE` tenancy; a future lease with money held cannot be settled or ended until the
   normal outcome path (return/withhold/not collected after ending). AppFolio's pre-move-in checklist is
   the industry basis for collecting a deposit before the term begins.
6. **The tenant sees the upcoming lease, but no money.** A tenant on a `FUTURE` lease sees the terms and
   documents read-only, labelled as upcoming; there is no statement, no due amount, and no action that
   posts money. When the lease starts, the same session begins to see the normal statement. This mirrors
   "UPCOMING LEASE: review or complete setup" and the pre-move-in resident identity.
7. **Editing and deletion stay draft-like until start.** A `FUTURE` lease is editable by a manager
   (terms can still change before possession), cannot be ended (nothing has begun), and may be deleted by
   an administrator while it has no money. Once `ACTIVE`, the existing lock-and-history rules apply.
8. **Ending stays explicit.** Established products often move a lease to Past automatically when its end
   date passes. RHP keeps the explicit end action for now because ending is what starts the move-out
   outcome (deposit disposition, final statement, E5); auto-ending without that would strand the account
   in a `Past` state with unsettled money. This is a deliberate, bounded divergence recorded here, to be
   revisited with the E5 move-out workflow.

### D2 — The person is not the login (M2b, next slice)

1. Introduce a person/contact record as the lease party, separate from `accounts.User`: a person has a
   name and contact details, can be on more than one lease over time, and **may or may not have a portal
   login**.
2. `LeaseTenant` becomes a membership of a person on a lease with a role — tenant, adult occupant,
   guarantor, authorised contact — a primary flag, and an optional link to the portal account. A login is
   per-person and optional; this is the PropertyBoss "Allow Login to Web Portal" model, not a role field
   on the lease.
3. `accounts.User` remains the only authentication model. There is no second user table, no second
   password, and no parallel login. Tenant-scoped queries move from `LeaseTenant.tenant` to the person's
   optional portal link, so a logged-in user still sees only the leases they are a party to, and an
   occupant without a login simply has no portal identity.
4. The migration maps each existing `LeaseTenant` row to one person (name/email captured from the user),
   links the user as that person's portal account, and preserves the one-primary-contact rule. The
   tenant invitation/activation flow keeps its current security properties, now attaching the login to a
   person.
5. Out of scope: applications, screening, guarantor liability enforcement, owner/vendor as parties.

### Staging

- **M2a (this slice):** `FUTURE` state, automatic scheduling, no-obligation behaviour, pre-move-in
  deposit, screens/copy, migration, tests.
- **M2b (next slice):** person/contact + optional portal link, data migration, scoped reads, lease form
  and tenant pages, tests. It gets its own implementation record when done; no person table is created
  before that design is written into the tree.

## Consequences

- A signed renewal is representable without abusing `ACTIVE`; the unit's current occupancy is unchanged.
- Existing data: any `ACTIVE` lease whose term has not started is converted to `FUTURE` by migration.
  That is the only data change; `ACTIVE` leases that have started are untouched.
- The lazy activation must be reliable: forgetting to run it is visible as a lease still labelled
  upcoming on its start day. The command runs at deploy and every manager/tenant screen read
  self-heals. This is documented in the phase record as a known operational limit, not hidden.
- Future leases never appear in arrears, occupancy, or "due now" reports, because those read
  `ACTIVE`/due charges only. No report needs a special case.
- A tenant can hold a future lease and an active lease at once only across different units (the normal
  renewal shape); the tenant portal still shows their current tenancy first, then the upcoming one.
- M2b will replace `LeaseTenant.tenant` with an optional portal link; that is the largest tenancy
  migration after E10 and is deliberately not bundled here.

## Alternatives rejected

- **Keep storing future leases as `ACTIVE` and special-case screens.** The unique constraint still
  blocks the renewal case, and every report would need to know the difference. The missing state is the
  bug.
- **Auto-end at the term date now** (as TurboTenant does). It would produce a `Past` lease before the
  deposit has an outcome; RHP's settlement gate would then block forever. Explicit ending is retained
  until E5, recorded as divergence.
- **Add a second `Tenant` authentication model** (some products separate owner/tenant portals). RHP's
  non-negotiable is one user model; the party record plus optional portal link gets the same result.
- **Put person data on `LeaseTenant` (names/emails copied per lease).** It duplicates people across
  tenancies and their history, which is the exact problem a contact record solves.

## Open items

- Whether a `FUTURE` lease may be deleted or must be "cancelled" with a reason. Implementation allows
  administrator deletion while no money is attached, which matches the absent-history case; revisit if
  the owner wants a cancellation record.
- Whether automatic activation should also generate all charges due on the start day, or only rent. This
  slice reuses the existing generation path, so any obligation due by the activation date is posted
  (rent, NNN, recoveries) — the same rule as a manual activation.
- M2b's person model needs its own ADR/implementation record covering the app home (`contacts` vs
  `leases`) and the invitation UX before any table is created.

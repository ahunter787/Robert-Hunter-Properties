# ADR-007: How a lease is modelled

- **Status:** Accepted (Phase 3)
- **Date:** 2026-10-01
- **Context:** Phase 3 — lease management: the first record that ties a person to a unit and to money

## Context

`Lease` is the record the property business actually runs on: it connects a unit to the people renting
it, and it is the first place in RHP where a sum of money is stored and where a tenant has a page of
their own. Four questions had to be settled before the screens could be written, and each has a
tempting answer that would be wrong later:

1. **When is a unit let?** If two active leases can exist on one unit, the rent roll double-counts and
   two tenants hold the same key. A rule in a form is not a rule: a second lease must be impossible,
   not merely discouraged.
2. **Does a lease end because a date passed, or because someone said so?** Deriving status from the
   calendar is less typing today and more trouble in Phase 4, when the ledger has to bill the month a
   lease ran over and history must not rewrite itself at midnight.
3. **What may be changed after the fact?** An ended lease is the evidence of what was agreed. Editing
   it turns the record into an opinion.
4. **How are co-tenants represented, and who does the office ring?** Two people on one lease is the
   normal case, not an edge case, and one of them is the primary contact.

## Decision

### One active lease per unit, enforced by the database

`Lease` carries `UniqueConstraint(fields=["unit"], condition=Q(status="ACTIVE"),
name="one_active_lease_per_unit")`. Drafts are unlimited — several half-written leases on one unit are
a normal Tuesday. The unit picker in the lease form also hides units that already have an active lease,
so the mistake is hard to make, but the constraint is what makes it *impossible*: two simultaneous
activations race, and a database constraint is the only thing that survives a race.

`Lease.unit` is a `ForeignKey(..., on_delete=PROTECT, related_name="leases")`. Deleting a unit that has
tenancy history is refused by the database, exactly as deleting a property with units is refused.

### Status is explicit, not inferred from the calendar

`LeaseStatus` is `DRAFT`, `ACTIVE`, `ENDED`, moved by a named action (`Activate lease`, `End lease`),
both POST-only. A lease whose end date has passed is **not** silently ended: it appears as *ending soon*
or *overdue to end* and waits for a person. This matters because

- the ledger (Phase 4) must be able to bill a holdover month, and a lease that ends itself at midnight
  cannot be invoiced;
- a status that changes without a user action cannot be written to the audit table with a person's name
  against it (Phase 4 adds that table);
- dates are stored as data and can be corrected, whereas a derived status cannot be corrected at all.

Dates decide exactly one thing, in exactly one place: whether a unit is *currently occupied*.

### Occupancy has one definition

`LeaseQuerySet.current(on_date=None)` answers "does an ACTIVE lease's term cover this date?" and
is the **only** implementation of occupancy. `Lease.is_current`, `Unit.current_lease`,
`Unit.occupants`, `Unit.is_vacant` and `Unit.is_occupied` all read it, and so do the counters on the
staff landing page. Two definitions of "occupied" (a stored flag and a query, say) is how a dashboard
starts disagreeing with the page it links to.

A unit that is **out of service** is a third state, not a vacancy: its tenancy stays in the records
(retiring a unit is not an eviction), but it is counted as neither occupied nor vacant, because it
cannot be let. The unit page shows "Out of service" for exactly that case.

### Ended leases are history

`is_editable` is `status != ENDED`. An ended lease is readable forever and refused for writing — on the
page **and** on the POST, because a guard that only hides a form is decoration. A correction is a new
lease, not a rewrite. Deletion is narrower still: only a **draft** may be deleted, and only by an
**admin**; an active or ended lease is ended instead, so the history stays.

### The unit is frozen once a lease is activated

While a lease is a draft its unit can change — that is the point of a draft. Once it is active the unit
is part of what was agreed, so the form disables the field and `LeaseForm` compares the **posted** value
against the stored one and refuses a tampered submit out loud. Silently ignoring the posted value would
be safe but would leave a user who did edit the page's HTML believing the move had happened.

### Co-tenants are a link table, with exactly one primary contact

`LeaseTenant(lease, tenant, is_primary)`:

- `UniqueConstraint(lease, tenant)` — the same person cannot be on one lease twice;
- `UniqueConstraint(lease, condition=Q(is_primary=True))` — at most one primary contact per lease; the
  formset requires at least one tenant, so in practice exactly one;
- `lease` is `CASCADE` (removing the tenancy removes its links), `tenant` is `PROTECT` — a person with
  tenancy history cannot be deleted.

The primary contact is who the office rings; it is deliberately **not** a payment-responsibility field.
Who is liable for rent is a Phase 4 question and will not be smuggled into a checkbox.

### Money and dates are stored the way the rest of RHP stores them

`monthly_rent` and `deposit` are `DecimalField(max_digits=12, decimal_places=2)` — never a float.
`rent_due_day` is an integer 1–31 and is *stated* on screen ("1st of every month", via the shared
`ordinal` helper); the month-end clamping rule (a due day of the 31st in February) is a **billing**
rule and arrives with the ledger in Phase 4, where it can be written once and tested.

### One lease document, for now

A signed lease can be attached as a PDF or a JPEG/PNG scan, at most `RHP_MAX_UPLOAD_MB`, stored under a
randomised name in `lease_documents/<uuid><ext>` and served **only** through a permission-checked view
(`LeaseDocumentView` for staff, `TenantLeaseDocumentView` for the tenant on that lease), with
`Cache-Control: private` and `X-Content-Type-Options: nosniff`. Replacing it deletes the old file; a
`post_delete` receiver deletes it when the lease is deleted. Phase 6 replaces this single field with the
documents area (categories, visibility, several files) and migrates what exists.

### The tenant area begins here

`/lease/` is the first page a tenant sees that is *theirs*. It shows their unit, term, rent, deposit,
co-tenants and document, resolved through `tenant_scope(...)`-style filtering, never by a bare primary
key. The tenant document URL carries **no id at all** (`/lease/document/`), so there is nothing to
enumerate: a tenant can only ever fetch the document of a lease they are on.

## Consequences

**Positive**

- A unit cannot be let twice, even under concurrency, and the constraint is named in the database.
- Nothing about a tenancy changes without a person's action, which is what makes the Phase 4 audit
  table meaningful and what keeps history stable.
- Occupancy is one query, so the dashboard, the property page, the unit page and the tenant portal
  cannot disagree.
- The money stored in Phase 3 is the money Phase 4 bills; no field needs reshaping when the ledger
  arrives.

**Negative / accepted trade-offs**

- Staff must end leases by hand. Accepted: a self-ending lease is a silent change to a financial
  record, and month-to-month holdovers are normal in this business.
- The property page runs one occupancy query per unit (no `Prefetch` of `current_lease` yet). Accepted
  at this size; it is the obvious optimisation if a large portfolio feels slow.
- One lease document per tenancy is less than a documents area. Accepted until Phase 6 rather than
  building half of Phase 6 now.
- `rent_due_day` can say "31st", which is not a real date in every month. Accepted: the value describes
  the intent of the agreement, and Phase 4 owns the arithmetic.
- A tenant cannot yet sign anything, contest anything, or see a balance. Deliberate.

## Alternatives considered

- **Derive status from dates** (`ACTIVE` while `start <= today <= end`): no stored state and no actions
  to take, but it cannot represent a holdover, cannot be corrected, cannot end early, and rewrites
  history at midnight. Rejected.
- **A stored `is_occupied` flag on `Unit`**: fast and simple, and a second source of truth that drifts
  from the leases. Rejected — the query is cheap and correct by construction.
- **Enforce one active lease in the form only**: the current state of most small property systems, and
  the reason double-bookings exist. Rejected.
- **A `lease` foreign key on `User`/tenant instead of a link table**: one tenant per lease, or a second
  table for co-tenants. Rejected.
- **`is_primary` as payment responsibility**: tempting, and wrong — liability is a Phase 4 decision
  about money, and conflating it with "who we ring" would be hard to undo once invoices exist.
- **Soft-delete an ended lease** (`is_archived`): keeps one meaning of "delete" but hides history behind
  a filter that every query must remember. Rejected; ended leases stay visible.
- **Store the document in the database**: one artefact to back up, but it bloats every backup and the
  file still has to be served through a view. Rejected, consistent with ADR-006.

# Phase 7 — Maintenance system

**Status:** Not started
**Milestone:** 4 — Documents and maintenance requests work end to end
**Specification:** `docs/harness/master-spec.md`, `PHASE 7 — MAINTENANCE SYSTEM`

## Scope as specified

A complete maintenance workflow. A tenant can submit a request with a category, title, a detailed
description, photos and an indication of permission to enter, and can follow its status and the management
updates. Staff get a queue filtered by property, status and age, with assignment to an employee or a
vendor, priority, status transitions (`OPEN → ACKNOWLEDGED → SCHEDULED → IN_PROGRESS → WAITING →
COMPLETED → CLOSED`), internal notes, and tenant-visible updates. The request reads as a timeline.
**Internal comments are never exposed to tenants**, and attachments are permission-checked.

## What exists today

Nothing yet — this phase has not been built. What it builds on:

- **The tenant area and its navigation**, the permission mixins, and `tenant_scope` for scoping a tenant's
  own rows.
- **The photo pipeline** (`apps/common/images.py`) for attachment validation, and the permission-checked
  download pattern for anything a tenant uploads.
- **The audit table**, which already records who did what and when — the basis for a timeline that must
  distinguish tenant-visible from internal events.
- **The counters and panels deliberately left waiting for this phase:** the property maintenance summary,
  the unit's recent maintenance, and the open-requests counter on `/manage/` are labelled as belonging
  here.
- **The mail sink** (`http://10.60.0.227:8025` in development) for notification email.

## Decisions that govern it

No decision record exists for this phase yet. It needs one before it is built, and it has more real
questions than most phases (see below) — mainly: what a request is attached to, who sees what, and how a
maintenance **cost** relates to the ledger.

## Extensions filed under this phase

None yet. **P4-E2** (property responsibilities) is adjacent and needs a deliberate boundary: a
`ResponsibilityCycle` already models "a recurring property cost, split across the units", which is how RHP
recovers maintenance from tenants. A Phase 7 request is work *to be done*; a P4-E2 cycle is cost *to be
recovered*. If a single repair should end up both fixed and recharged, that is a link between the two, and
it belongs in this phase's design — not in the ledger's.

## Acceptance criteria and evidence

Not yet met — the phase is unbuilt. From the specification:

- [ ] A tenant sees changes clearly (status and tenant-visible updates only)
- [ ] Staff have an actionable queue with the filters and assignment the specification lists
- [ ] Internal comments are never exposed to tenants — including in an API-shaped response or a shared URL
- [ ] Images and attachments are permission-checked, like every other upload

## Deliberately not here

Direct messaging with a tenant (Phase 8 evaluates it), a vendor portal, and any scheduling or dispatch
integration. Cost accounting belongs to the ledger and P4-E2, not here.

## Known gaps and defects

Nothing is broken — this phase does not exist yet. The gap it fills: RHP has no way to receive or track a
maintenance request inside RHP, and no record of what was done to a unit.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P7-Q1 | Is a request about a **unit**, a **tenancy**, or a **property** (a shared roof, a parking lot)? | The request names a unit or a property; a common-area request is property-level. Tying it to a tenancy hides it the moment the tenant moves out. | *(awaiting)* |
| P7-Q2 | Should a maintenance **cost** be recorded in RHP, and should it be rechargeable to the tenant? | Record the cost on the request and let it *offer* a recharge — charged as a one-off ledger charge, linked back to the request. That link is what P4-E2's cycles cannot express. | *(awaiting)* |
| P7-Q3 | Who may add an internal note versus a tenant-visible update, and can a manager edit the other's? | Any staff role may add either; internal notes are visible to staff only and never editable by a tenant. An edit leaves the audit trail. | *(awaiting)* |
| P7-Q4 | Do you want vendors as records (name, contact, trades), or just a free-text name? | Records, but minimal: name, contact, trades, active. Reuse them from the request and report on them in Phase 10. | *(awaiting)* |
| P7-Q5 | Do you want notification email to the tenant, or is seeing it in the portal enough? | Email on submission and on each tenant-visible update; the tenant can be told to reply in the portal. The mail sink makes this safe to develop. | *(awaiting)* |

## How to verify it

Not yet. When built: submit a request with photos as a tenant, work it through every status as staff, and
confirm the tenant never sees an internal note and can access only their own attachments.

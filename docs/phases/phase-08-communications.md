# Phase 8 — Communications

**Status:** Not started
**Milestone:** 5 — Communication and an operational dashboard for the RHP team
**Specification:** `docs/harness/master-spec.md`, `PHASE 8 — COMMUNICATIONS`

## Scope as specified

Lightweight property communication, announcements first: a water shutoff, parking maintenance, an
inspection notice, a holiday schedule, an office closure. An announcement targets everyone or one property,
appears only to the intended tenants, disappears from the normal tenant view when it expires, and an
important one can be highlighted. Direct messaging is to be **evaluated later**, not built prematurely.

## What exists today

Nothing yet — this phase has not been built. What it builds on:

- **The property → unit → lease structure** is the audience: "one property" is a query over that, and
  "everyone" is every tenancy.
- **The tenant area** (`/account/`, `/lease/`, `/payments/`) and its navigation, where an announcement will
  appear, plus the label the dashboard already carries for the panel that belongs here.
- **The email backend**, which in development sinks into Mailpit at `http://10.60.0.227:8025` — so
  notification email can be built and read without sending anything real.
- **The audit table** for who published, changed or withdrew an announcement.

## Decisions that govern it

No decision record exists for this phase yet. It needs one before it is built, and the phase guide already
records the shape of the decision: announcements cover the real need, a chat system is a much bigger
commitment and is deferred.

## Extensions filed under this phase

None yet.

## Acceptance criteria and evidence

Not yet met — the phase is unbuilt. From the specification:

- [ ] An announcement appears only to the intended tenants
- [ ] An expired announcement disappears from the normal tenant view
- [ ] An important announcement can be highlighted

## Deliberately not here

Direct messaging, push notifications, SMS, and any scheduling or drafting workflow. Announcements are
unidirectional by design: RHP tells tenants something.

## Known gaps and defects

Nothing is broken — this phase does not exist yet. The gap it fills: RHP has no way to tell the right
tenants something inside the portal, so property-wide notices live outside RHP entirely.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P8-Q1 | Who is the audience when an announcement is published — the tenants on the lease **now**, or whoever lives there while it is live? | The tenancy live at the moment it is published, recorded; a tenant who moves in later does not receive history they were never told. | *(awaiting)* |
| P8-Q2 | In-portal only, or email as well? | Both, for an announcement marked important; in-portal for the rest, so the portal stays the record. | *(awaiting)* |
| P8-Q3 | Who may publish — managers and above, or admins only? | Managers and above may draft and publish to their portfolio; an admin may withdraw one. | *(awaiting)* |
| P8-Q4 | Should a tenant be able to acknowledge an announcement (e.g. "I have read the inspection notice")? | Not now. It turns a notice into a to-do list and implies enforcement RHP does not want. | *(awaiting)* |

## How to verify it

Not yet. When built: publish one announcement to a single property and one to everyone, confirm a tenant of
another property never sees the first, that an expired one vanishes, and that the mail sink shows the email
where one was sent.

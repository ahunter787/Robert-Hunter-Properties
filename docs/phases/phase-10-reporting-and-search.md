# Phase 10 — Reporting and search

**Status:** Not started
**Milestone:** 6 — Reporting, search, and production hardening
**Specification:** `docs/harness/master-spec.md`, `PHASE 10 — REPORTING AND SEARCH`

## Scope as specified

Search across tenants, properties, units and leases; and reports for rent roll, balances due, payment
history, lease expirations, maintenance aging and property occupancy. Export CSV first, and PDF only where
it earns its keep.

## What exists today

Nothing yet — this phase has not been built. What it builds on:

- **Search has one working example:** `lease_search(term)` in `apps/ledger/services.py` matches a lease by
  unit, property and tenant name, and powers the ledger's search box. The pattern — one `Q` builder per
  domain, used by the list screen — is what this phase generalises.
- **The arithmetic a report needs is already derived**, not stored: `build_ledgers(...)`, `totals(...)`,
  `by_urgency(...)`, and `StatementMonth`/`StatementCharge` for payment history. A report is another
  reading of the same functions, which is how it cannot disagree with the screens.
- **The dimensions:** `Unit.square_feet` and the amenities list for sizing; `Property.is_residential` for
  classification; `LeaseStatus` and the term for expirations; `Lease.objects.current(...)` as the single
  definition of occupancy; retirement flags on properties and units so history stays reportable.
- **The audit table** for "who changed what, when".
- **The obligation from Phase 7:** maintenance aging needs the maintenance system, so that report lands
  after Phase 7 exists and is only as good as its data.

## Decisions that govern it

No decision record exists for this phase yet. It needs one for the export path (CSV first, and what a
column means), for who may export what (a rent roll is not tenant-facing), and for whether a report is a
screen or a saved query.

## Extensions filed under this phase

None yet. Two things the phase guide marks as belonging here: **bedrooms and bathrooms** are used for
sizing and the rent roll, and **retired properties and units** must stay in reports as history.

## Acceptance criteria and evidence

Not yet met — the phase is unbuilt. From the specification, with the test this record adds:

- [ ] Search finds a tenant, property, unit or lease by any of the names a person would type, and never
      crosses a tenancy boundary
- [ ] Each report exists as a screen and exports to CSV
- [ ] A report's figures equal the corresponding screen's figures, because both call the same functions
      (`make test` should prove this rather than a person comparing two pages)
- [ ] A retired property or unit appears in historical reports with a marker, not missing

## Deliberately not here

A report builder, scheduled email digests, and dashboards (Phase 9). PDF is deferred until a specific
document earns it — the first candidate is a statement or receipt from Phase 6.

## Known gaps and defects

Nothing is broken — this phase does not exist yet. The gap it fills: RHP cannot answer "what is the rent
roll", "what is due", or "which leases expire this quarter" without reading screens one at a time.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P10-Q1 | Which reports will you actually use monthly, and which are wishful? | Start with rent roll, balances due and lease expirations — the three that answer "what do I do this week". Payment history and occupancy follow; maintenance aging after Phase 7. | *(awaiting)* |
| P10-Q2 | Who may export money data — managers, or admins only? | Managers may read and export their portfolio's data; the account and role administration stays with admins. | *(awaiting)* |
| P10-Q3 | Where does a CSV go when it is exported — download, or emailed? | Download. Email turns a report into a data-protection question and nothing here needs it yet. | *(awaiting)* |
| P10-Q4 | Do you need reports for a **period** (this month, this quarter), or always "as of now"? | Both: occupancy and balances "as of now", money reports for a chosen month. The ledger's dates already support it. | *(awaiting)* |

## How to verify it

Not yet. When built: run each report, export it, and check the totals against the ledger screens they were
derived from.

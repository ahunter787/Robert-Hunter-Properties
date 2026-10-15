# Phase 5 — Tenant dashboard

**Status:** Complete
**Milestone:** 3 — Tenants see their balance and rent due; the ledger is authoritative
**Specification:** `docs/harness/master-spec.md`, `PHASE 5 — TENANT DASHBOARD`

## Scope as specified

The tenant's landing page: what is due now, when the next rent falls due and how much, when the lease ends,
quick actions, and recent activity — working well at phone width, with no unnecessary density, and with the
critical information visible without digging. The specification also lists maintenance and announcements
here; both belong to later phases and are labelled rather than faked.

## What exists today

- **`/account/`** (`apps/accounts/views.py`, `TenantDashboardView`): what is due now — or that the tenant is
  in credit, or that nothing is owing — the next rent and its date, when the lease ends, quick actions, and
  the recent activity. Staff are redirected to `/manage/` rather than shown a tenant page (ADR-010).
- **`/payments/`** (`apps/ledger/views.py`, `TenantPaymentsView`): the tenant's own statement, paginated by
  month, showing rent, NNN and responsibilities as one month; expected money labelled "expected" and not
  moving the balance; voided entries hidden; a correction absorbed into the charge it corrects.
- **`/lease/`**: the lease detail page beside them (Phase 3/4).
- **Tenant navigation:** Dashboard, Lease, Payments — the tenant area became real here.
- **No data of its own.** Every figure is a reading of the ledger (`build_ledger`) and the lease.

## Decisions that govern it

| Record | What it settled |
| --- | --- |
| [ADR-010](../decisions/ADR-010-tenant-dashboard.md) | What the dashboard is, what is deliberately a sentence rather than a screen, and where the boundaries are |
| [ADR-011](../decisions/ADR-011-tenant-statement.md) | Charges and payments as one statement; corrections absorbed; the statement's own arithmetic |
| [ADR-012](../decisions/ADR-012-owed-now-and-coming-due.md) | "Due now" as the headline, "coming due" as a sentence, and the office keeping the whole balance |

Review rounds while the phase was open (all in `roadmap.md`): the greeting and display-timezone copy were
removed; a correction reads "$0.00, nothing to pay" rather than a charge and an opposing credit; paid and
credited money are shown separately; "next rent due" is the incoming month, dated from the lease when the
office has not raised it yet.

## Extensions filed under this phase

None filed here. **P4-E2** changed what this phase reads: a month is now rent, NNN and responsibilities
together, and the tenant's card names each part rather than showing one blended figure.

## Acceptance criteria and evidence

- [x] Works well at phone width — single column, full-width tap targets, list rows rather than tables
      (the final check was the owner's own phone)
- [x] No unnecessary information density — three figures, three actions, five recent rows
- [x] The tenant's critical information is visible without digging: it is the page they land on
- [x] Expected money never moves the balance; voided entries are never shown
- [x] The two panels belonging to later phases are labelled, not faked

`tests/ledger/test_tenant_area.py` and `tests/ledger/test_tenant_payments.py` cover the tenant's view,
including that one tenant never sees another's figures.

## Deliberately not here

Maintenance requests (Phase 7), announcements (Phase 8), documents (Phase 6), payments taken through the
site (Phase 11). Phase 5 adds no data of its own, and it changed no office-side figure: the ledger, the
audit trail and every balance stayed as they were.

## Known gaps and defects

- The tenant sees their balance and activity but **not the history of changes** to their own lease. Decided
  as "easy to add later, better decided with real usage in front of us" — see the phase guide.
- Nothing on the tenant side produces a document: no statement or receipt PDF (Phase 6/10).
- A tenant has no way to tell RHP "I have paid this" — money is recorded by the office until Phase 11.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P5-Q1 | Should a tenant see the history of corrections to their own charges? | Not by default — the statement already shows the net effect. Offer it as a disclosure on the month, not a separate page. | *(awaiting)* |
| P5-Q2 | Do you want a "print or save my statement" action before Phase 11? | Yes, and cheaply: the browser's own print stylesheet on `/payments/` rather than a PDF pipeline. | *(awaiting)* |

## How to verify it

Sign in as a tenant on a phone-width window: `/account/` answers the three questions, `/payments/` opens the
statement, `/lease/` shows the term and document. `make test` covers the figures and the isolation.

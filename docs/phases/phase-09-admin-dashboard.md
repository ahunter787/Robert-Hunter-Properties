# Phase 9 — Admin dashboard

**Status:** Complete — owner accepted October 20, 2026; local preservation and merge authorized
**Milestone:** 5 — Communication and an operational dashboard for the RHP team
**Specification:** `docs/harness/master-spec.md`, `PHASE 9 — ADMIN DASHBOARD`

## Scope as specified

A useful operating overview — portfolio (properties, units, occupied, vacant), rent (due this month,
collected, outstanding), maintenance (open, in progress, over seven days), leases (expiring in 30 and 90
days) and a recent activity feed — with one hard rule: **every metric must lead to the underlying data**.
Decorative analytics are explicitly forbidden.

## What exists today

Implementation starts from the accepted Operations Desk and Phase 8 local baseline `6aa8bf6`.
Existing foundations (not empty placeholders):

- **Derived counters already exist** on the staff landing page (`/manage/`): portfolio totals, occupancy,
  what is outstanding and what is late, each true for the role viewing it.
- **The reading that a dashboard needs** already exists as functions, not as stored numbers:
  `ledger_rows(...)`, `by_urgency(...)`, `totals(...)` and `build_ledger(...)` in
  `apps/ledger/services.py`, and `Lease.objects.current(...)` as the single definition of occupancy.
- **The audit table** (Phase 4) already records lease status changes, money movements and role changes —
  the recent activity feed reads it, and this phase is where the audit *browser* was promised.
- **Maintenance and communications summaries** already work; Phase 9 consolidates their operational
  populations without changing their histories or permissions.

Implementation now includes `apps/dashboard/` read-only projections, metric detail views and a safe
activity browser, with templates under `templates/dashboard/`. Existing staff home delegates to the
new projection; tenant and assigned-worker dashboards are retained. No model/dependency changes.

## Decisions that govern it

[ADR-025](../decisions/ADR-025-operational-dashboard.md) records the approved implementation.
Owner selected rent first, all posted charge categories and searchable history. Approval of the
complete implementation plan also confirms replacing the staff landing page, per-request live
calculations, and retaining record-level histories alongside a portfolio activity browser.

Monthly charges follow original due dates with existing adjustments; effective cleared payments
follow payment dates. These are different populations, not operands for an invented monthly balance.
Credits never offset other tenancies' debts. Metrics and their detail views share one projection.
Role-change events remain superadmin-only; no raw audit metadata or message bodies are exposed.

## Extensions filed under this phase

None yet.

## Acceptance criteria and evidence

Implemented and owner-accepted October 20, 2026 for local preservation and merge:

- [x] Every dashboard figure links to its shared read-only population; original ledger links retain
      inline corrections. Credits and monthly charges/payments remain distinct.
- [x] Managers/admins receive portfolio operations; workers retain assigned maintenance only and
      tenant dashboards are unchanged. Role-change history remains superadmin-only.
- [x] Ten recent operational events and a 25-per-page filtered browser read the existing audit table.
      Arbitrary summaries/metadata are never rendered; missing records and actors remain explicit.
- [x] Regression coverage includes all charge categories, pending/void/reversed payments, original
      due-date adjustments, timezone month boundaries, occupancy, maintenance follow-ups, personal
      unread state, invalid identifiers, pagination, read-only endpoints and bounded query growth.
- [x] Disposable authenticated browser review at desktop, 768px tablet and 390px phone widths;
      keyboard Menu operation, financial drill-down and activity filtering, including scripts blocked.
- [x] Owner acceptance and explicit local commit/squash-merge authorization.
- [ ] Actual 200% browser zoom and print-preview inspection; screenshot publication.

Implementation files: `apps/dashboard/{services,activity,views}.py`, staff home and URL integration in
`apps/accounts/`, `templates/dashboard/` and `templates/management/home.html`, regression tests in
`tests/test_operational_dashboard.py`, disposable browser fixture in `tests/test_dashboard_browser.py`
and updated existing dashboard assertions. Governing records include ADR-025, specification,
architecture, security, roadmap and README. No models, migrations or dependencies were added.

Verification on October 20, 2026:

- `make test`: **1,094 passed, 4 skipped**, 303.81 seconds. Skips are opt-in browser fixtures.
- Preservation recheck: **1,094 passed, 4 skipped**, 323.00 seconds. A preceding recheck was
  terminated with signal 143 during existing migration tests; it was not counted as a pass.
  Lint, Django/deployment checks, CSS build, migration checks and fresh smoke start passed again.
- Focused dashboard/legacy dashboard tests: **20 passed**; focused dashboard/document-contract run:
  **23 passed**. The dashboard's opt-in browser fixture was separately exercised twice, with
  JavaScript and with scripts blocked: **1 passed** each; both disposable databases were torn down.
- `make lint`, `make check`, `make check-deploy`, `make assets`: passed.
- Migration generation check: no changes detected; application check: no unapplied migrations.
- Fresh loopback smoke start: `/healthz` returned 200; anonymous `/manage/activity/` returned 302.
- Outline/Plane publication and `make -C ecosystem verify`: passed for the implementation records.

Synthetic captures remain local under `/tmp/`; no real
tenant data or normal-session cookies were used for browser QA, and no financial records were changed
in the development database.

## Deliberately not here

Anything that cannot be drilled into; charts for their own sake; scheduled email digests (that is
Phase 8 + Phase 10); a tenant-facing equivalent (Phase 5 already answers the tenant's questions).

## Known gaps and defects

Owner accepted the implementation and authorized local preservation and squash merge on October 20,
2026. No push or deployment is authorized. Actual 200% zoom, print preview and screenshot publication
are not verified. Application
checks are independent of those gaps. No historical audit events are reconstructed, and missing
targets remain labeled unavailable. Page-load calculations intentionally have no automatic refresh.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P9-Q1 | What do you look at first, every day? | Original recommendation: rent first. | Rent first — selected in chat. |
| P9-Q2 | Does this replace the staff landing page, or sit beside it? | Replace it. | Replace the existing staff dashboard — approved implementation plan. |
| P9-Q3 | How current must the figures be — live, or refreshed hourly? | Live. | Recalculate on page load, not continuous polling — approved plan. |
| P9-Q4 | Should the audit browser be reachable from here, or from each record? | Both. | Searchable history plus recent feed; retain existing record-level histories — selected in chat and approved plan. |
| P9-Q5 | Which monthly charge categories? | All posted categories. | All charges with categories identified separately — selected in chat. |
| P9-Q6 | Who may read operational/security history? | Preserve existing role boundary. | Managers/admins operational history; role changes superadmin-only — approved plan. |

## How to verify it

Sign in as a manager at `/manage/`. Follow each figure to its exact matching list, then to the original
record. Review monthly charge corrections without subtracting payments; compare shared reply state
with personal unread state. Open `/manage/activity/` and combine date, person, type, property and
tenancy filters. Verify role changes are unavailable except to superadmins. Workers must see only
assigned work and receive 403 at the metric and activity endpoints.

Automated reproduction: `make test`, `make lint`, `make check`, `make check-deploy`, `make assets`,
`uv run python manage.py makemigrations --check --dry-run`, `uv run python manage.py migrate --check`.
The opt-in browser fixture documents separate QA cookies and teardown; use a disposable test database
and local live-server port, never ordinary development records.

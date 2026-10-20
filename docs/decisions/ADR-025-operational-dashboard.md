# ADR-025 — Operational dashboard and readable activity

Status: Accepted for implementation, October 19, 2026.

Phase 9 on `rhp-9`, from accepted local Phase 8 baseline `6aa8bf6`. Owner accepted the result and
authorized local commit and squash merge October 20, 2026; no push or deployment. Owner chose rent first, all charge categories and
searchable operational history. The approved plan replaces `/manage/`, recalculates on page load,
and preserves worker/tenant boundaries and the Operations Desk design.

One read-only projection supplies metrics and paginated detail pages under
`/manage/dashboard/<metric>/`. Every figure links to precisely that metric's underlying records;
record links lead to existing authorized workspaces. No stored totals or new business models.
Use existing ledger projections, effective payments and current-lease occupancy. Calendar-month
charge totals follow original due dates and absorb adjustments inline; cleared payments follow
payment dates and exclude reversed, voided and pending entries. Never subtract these two totals to
invent an outstanding balance or offset separate tenancies' credits.

Maintenance summaries use existing unresolved/status/priority/age/follow-up definitions; messages
distinguish personal unread from shared work. Lease windows are cumulative 30/90 days. All metrics
are manager/admin operational reads; workers keep assigned work only and tenants are unchanged.

`/manage/activity/` reads existing audit events with 25 per page, ten recent authorized operational
events on the dashboard, and date/actor/type/property/tenancy filters. Role changes are superadmin
only. Render action labels and explicitly selected context, not arbitrary audit summaries or raw
metadata: existing summaries can contain internal notes or reasons. Bulk-resolve whitelisted object
types and link only to existing authorized workspaces. Missing records remain visible as historical
events without invented actors, context or links. Do not reconstruct missing history.

No new dependency, queue, polling, accounting, forecasting, exports or custom reporting. Test
metric/detail agreement, monetary edge cases, date boundaries, missing objects, role/privacy limits,
bounded query growth and responsive/plain-form operation. Full gates and ecosystem verification
precede owner handoff. Known browser/print verification gaps must be reported, never implied passed.

# ADR-034: Tenant timeline (E16)

- **Status:** Accepted
- **Date:** 2026-10-22
- **Extension:** E16, branch `rhp-e16-timeline`
- **Depends on:** E15 (message events), ADR-024, ADR-031; study in
  [`design/tenantcloud-modifications-plan.md`](../design/tenantcloud-modifications-plan.md)

## Decision

Build one authorized, date-grouped tenant timeline as a **read model** over existing records, not a
second audit table. The feed merges:

- lease lifecycle and onboarding/settlement events;
- tenant-ledger charges, payments, applications, corrections and reversals, rendered from the ledger's
  own figures and links (never recomputed);
- maintenance creation/status/notes/costs, documents, messages and announcements;
- E17 insurance events when that extension exists;
- staff manual activity (`NOTE`, `TASK`, `CALL`, `MEETING`) stored as append-only `TimelineEntry` rows with
  an explicit `visible_to_tenant` flag.

Staff see the portfolio scope; a tenant sees only their own tenancy and only tenant-visible events.
Internal notes never cross that boundary. Date grouping, filters, pagination, empty state and links to
authorized source records are required. No cross-tenancy search, platform/admin events, e-sign or
screening events. System history is immutable; manual edits create a new entry/revision.

## Verification

Tests cover tenant/other-tenant/staff scopes, hidden notes, money figures equal to the ledger, event
ordering/grouping/pagination, empty states, query-count sanity and the full gate. The timeline does not
change existing records or authorization; it is additive.

# ADR-035: Renters-insurance proof and manager decision (E17)

- **Status:** Accepted (owner-approved narrow scope)
- **Date:** 2026-10-22
- **Extension:** E17, branch `rhp-e17-insurance`
- **Depends on:** E16 timeline, existing private document storage, communications delivery
- **Supersedes for this slice:** the blanket "insurance" exclusion only to the extent of **proof intake
  and a manager decision**; it does not authorise insurance sales, quotes or underwriting.

## Decision

RHP treats renters insurance as a lease obligation with evidence:

- `Lease.renters_insurance_required` (default off) is set during lease setup.
- The tenant supplies proof (PDF/JPG/PNG + optional policy dates) through the tenant area. Proof files use
  the existing private document store and permission-checked serve path.
- A manager reviews the submitted proof and records **Accepted** or **Rejected** with a note (a rejection
  note is required). RHP does **not** screen, score, OCR, advise on, sell or underwrite insurance.
- The tenant-visible state is three-state:
  1. **Missing** — no proof supplied; warning/onboarding to-do.
  2. **Submitted — pending manager review**.
  3. **Reviewed — accepted or rejected** (with the rejection reason).
- A replacement is a new append-only submission. The manager decision is immutable; a correction is a
  new review record.
- The requirement, submissions and decisions appear on the tenant timeline (E16), and an onboarding
  checklist item clears only on an accepted proof.

## Boundaries

No automated screening in this slice, no fourth expiry/waiver state, no partner quote/sales funnel, no
insurance product recommendation. No new dependency. Tenant routes are lease-scoped; staff routes are
manager-only; downloads never bypass document authorization.

## Implementation note (2026-10-22)

Built in development on `rhp-e17-insurance`: `apps.insurance` with `InsuranceProof` (append-only
submissions, one-time manager decision), lease flag, tenant upload and status page, manager review list
and detail, dashboard to-do, timeline events and private document download. The tenant view is exactly
missing / submitted-pending-review / accepted-or-rejected; a rejection reason is required and visible.

## Verification

Tests cover requirement off/on, missing warning and onboarding item, tenant upload and own-lease scope,
manager accept/reject, required rejection reason, persistent tenant status/reason, replacement history,
private download authorization, timeline events and the full gate.

# Prior lease activity calculator — scoped proposal

**Status:** Planning only. Owner requested this separate scope on October 18, 2026.
No onboarding arithmetic, historical entry, or financial service is changed by E11.

## Purpose and boundaries

Help a manager reconcile an existing tenancy before its first tracked billing date. Keep the
existing recreate-history and opening-balance methods; this is an optional setup aid, not a new
recurring billing mechanism. Once setup is complete, show it as historical setup information rather
than a daily task. Never hide its audit record or remove the ability to explain the opening figure.

## Proposed calculation and review

1. Choose the existing lease, billing cutover and reconciliation date. Show the unit, tenants,
   lease term and affected period explicitly. Do not infer dates from the current day alone.
2. Preview rent from the existing schedule, recorded triple-net amounts and known expense-recovery
   charges. Identify missing bills/rates or existing ledger entries before deriving a result.
   Permit reviewed supplemental historical amounts with dates and reasons, not silent estimates.
3. Enter the known opening balance (positive amount owed, negative credit) and any known noncash
   credits/corrections. Keep security deposits separate; they are not rent receipts.
4. Show the reconciliation: historical charges minus opening balance equals the net reduction
   needed to reconcile. Subtract separately identified noncash credits before proposing receipts.
   This equation does **not** prove cash was received. Label unverified results “Implied prior
   receipts — verify against your records,” never actual payments solely because the math balances.
5. Review the date range, charge components, credits, implied receipts, known balance, missing
   information, and resulting ledger state. Require a manager to confirm the figures and source
   before invoking existing onboarding services. Offer Back and Cancel without writes.

The authoritative server uses Decimal and the existing schedule/charge rules. Do not duplicate
their arithmetic in JavaScript. Review must bind the actual component facts, cutover, tenant/unit,
existing ledger and actor; reject stale or repeated confirmations appropriately. Save atomically,
using existing immutable entry and audit conventions, without charging any period twice.

## Decisions still needed before implementation

- Should receipt reconciliation require a reference/source note? Recommended: yes, and explicitly
  distinguish confirmed cash from adjustments rather than silently creating a payment.
- How should an incomplete historical expense bill be handled? Recommended: block a claim that
  reconciliation is complete; allow the existing opening-balance-only method with a clear note.
- Do any opening balances include security deposits? Recommended: separate those figures before
  this calculator can propose receipts; do not conflate rent credit and held deposits.

## Acceptance

Test stepped/fixed rent, triple-net changes, recovery-period boundaries, partial months under
existing rules, credit opening balances, existing charges/payments, noncash credits, missing bills,
rounding, simultaneous changes, duplicate submits and unauthorized/ended/settled cases. Verify
preview/review agreement and zero writes before confirmation. No migration is presumed until a
reviewed implementation plan determines whether existing onboarding metadata is sufficient.

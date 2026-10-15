# ADR-021 — Plain-language product vocabulary and account-first information design

**Status:** Accepted (owner-directed, 2026-10-13)
**Date:** 2026-10-13
**Related:** [ADR-020](ADR-020-tenancy-lifecycle.md), [E9](../extensions.md#9-e9--plain-language-interface)

## Context

The portal exposed implementation history and ambiguous accounting shorthand. In particular, a lease page
could call a future charge “Balance due” while also saying it was not due. Labels such as “raise,” “stage,”
“position,” and “responsibility” required the operator to infer what an action would do.

## Decision

RHP uses American English, sentence case, direct verbs, `Mon D, YYYY` dates, and the word “tenant.” Product
screens never mention phases, roadmap files, release sequencing, or implementation rationale. Actions name
their outcome and consequential actions explain the affected account and resulting state before confirmation.

The staff financial area is **Rent & Payments**. The routine verbs are **Post due rent charges**, **Record
payment**, and **Add one-time charge**. Property costs billed to tenants are **Expense recoveries**; bills are
entered and their billing periods scheduled. “Triple-net (NNN)” is expanded on first use.

Every financial summary separates **Due now**, **Past due**, **Upcoming**, and **Account balance**. A future
charge may be included in the account balance but is never presented as currently due. A zero balance reads
“Paid in full”; money held for the tenant is a “Credit balance.”

The staff lease account presents identity and states first, then the financial summary, routine actions, one
chronological transaction ledger with a derived running balance, and a separate administrative audit history.
Routes remain stable.

Owner refinement, 2026-10-14: charge adjustments appear inline beneath their original charge, with the
original amount, correction amount, date, and reason retained. Running balances use corrected charge
amounts as of today. Status colors distinguish past due, partly paid, paid, and pending entries, with text
labels preserving their meaning without color. Uploaded leases display a readable document name;
private storage continues to use randomized filenames and permission-checked serving.

## Consequences

Copy across templates, forms, validation, alerts, email, and error pages follows one vocabulary. Tests reject
development-only language on rendered product pages. The running balance is a projection of immutable entries,
not a stored field. Workflow changes remain limited to presentation except where the old hierarchy obscured the
difference between due-now and total balance.

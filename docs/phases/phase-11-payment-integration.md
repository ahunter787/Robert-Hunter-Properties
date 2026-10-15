# Phase 11 — Payment integration

**Status:** Not started — approved, optional for 2027
**Milestone:** 2027 — one-time ACH and ACH autopay after the ledger is approved
**Specification:** `docs/harness/master-spec.md`, `PHASE 11 — PAYMENT INTEGRATION`

## Scope as specified

Payment processing is approved as a desirable but non-blocking 2027 capability. Prioritize one-time ACH
and ACH autopay; PayPal and fee-heavy card methods are not priorities. A provider still must be selected
before implementation. RHP must never store card numbers, bank account credentials, or bank login
credentials: bank linking must be provider-hosted or tokenized, webhook events must be verified, and every
payment must reconcile to a ledger entry.

## What exists today

Nothing yet — this phase has not been built. It is approved but optional, and follows full application and
ledger testing rather than blocking the rest of the 2027 portal. What it builds on:

- **The ledger already models what a provider sends.** `Payment` carries an amount, a date, a method, a
  free-text reference, a status (cleared, pending, void) and a reversal link, and `record_payment` is the
  one way money enters the books (ADR-008). A provider integration becomes another caller of it.
- **Expected money is already representable:** a pending payment does not move the balance, which is
  exactly the state a webhook-driven ACH payment sits in for a day or two.
- **The tenant's statement** (`/payments/`) is where a "pay now" action would live, and Phase 5 left it
  reading from the same derivation as the office ledger.
- **No credential is stored anywhere today**, and no dependency in `pyproject.toml` talks to a payment
  provider.

## Decisions that govern it

| Record | What it constrains |
| --- | --- |
| [ADR-008](../decisions/ADR-008-rent-ledger.md) | Money enters through `record_payment`; corrections are reversals, never edits — a webhook may not rewrite history |
| [ADR-011](../decisions/ADR-011-tenant-statement.md) | The statement already distinguishes expected from cleared money |

No provider decision record exists for this phase yet, and it needs one **before** implementation: the
provider, the flow (hosted page or tokenized fields), the webhook verification rule, and how a remittance
settles the ledger.

## Extensions filed under this phase

None yet.

## Acceptance criteria and evidence

Not yet met — the phase is approved but unbuilt. From the specification:

- [ ] No card number and no bank credential is ever stored by RHP
- [ ] Only provider-hosted or tokenized mechanisms are used
- [ ] Webhook events are verified before they move money
- [ ] Every provider payment reconciles to exactly one ledger entry, and a reconciliation failure is visible
      rather than silent

## Deliberately not here

Storing credentials of any kind; choosing a provider; autopay defaults; fees and their accounting. All of
these wait for your decision.

## Known gaps and defects

Nothing is broken — this phase is deliberately unbuilt. The known **readiness** gap: Phase 4 applies money
oldest-first (FIFO), which is what a rent ledger does, but a provider sending remittance detail may want a
payment applied to a **named charge**. That would be an allocation table, and the phase guide already
records that Phase 11 is where it earns its keep. Deciding it late is expensive; it belongs in this phase's
decision record.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P11-Q1 | Is online payment wanted at all, and by when? | Treat it as a desirable but optional 2027 capability after the ledger is approved. | **Yes, ideally; it is not a launch blocker.** |
| P11-Q2 | ACH, card, or both? | ACH first: rent is a recurring bank transfer, and card fees on a monthly rent are hard to justify. | **ACH one-time payments and autopay; PayPal and fee-heavy methods are not priorities.** |
| P11-Q3 | Should a payment be applied to a named charge, or keep oldest-first? | Keep oldest-first as the default, and add explicit allocation only if a provider's remittance makes it necessary. | *(awaiting)* |
| P11-Q4 | Who absorbs the processing fee — RHP, or the tenant? | RHP absorbs it, and it is recorded as a business cost outside the tenant's ledger rather than as a charge. | *(awaiting)* |

## How to verify it

Nothing to verify yet. When approved, the phase must be verified against a provider sandbox, including a
replayed and a forged webhook, before any real money moves.

# ADR-012: What is owed now, and what is coming due

- **Status:** Accepted (review round on Phase 5)
- **Date:** 2026-10-02
- **Context:** "Next rent due" named the oldest unpaid month, and the headline named the whole term

## Context

The owner read their own tenancy's page — 11 monthly charges of $2,084, two months credited, one payment
of $10,000 — and reported two separate faults that turned out to be one:

> The next rent due should be the incoming month… It should still display $2084.00.

> The balance is calculating the remainder of the entire lease, so it looks like an overwhelming amount of
> money that is owed… This can be oppressive if read by a human.

Both come from the same mistake: the ledger asked **one** question — *what does this tenancy owe over its
whole term?* — and the screens used that single number to answer **three** different questions. So:

- `balance_due` ($8,756) was the headline. Arithmetic on the term, not a bill: most of it was not due for
  months, so the page read as a demand for money nobody was asking for yet.
- `next_due` was the *soonest unsettled charge*, which in a tenancy that is behind is the **oldest unpaid
  month** — July, when the tenant was reading in October. The label said "next", the number said
  "arrears". A tenant reading "Next rent due July 5" reasonably concludes the app has lost four months.
- `overdue_amount` existed, but as smaller print under the wrong headline.

The published specification models one monthly rent and one balance (ADR-008); nothing in it describes a
"coming due" figure, an aged-bucket view, or a forecast. This ADR is therefore a **clarification of what
the existing figures mean**, not a new feature: no model, no migration, no new stored number.

## Decision

### One ledger, three answers, each with its own name

`LeaseLedger` keeps one derivation and now exposes the three questions separately, so a screen can never
be tempted to reuse one number for another:

| Question | Property | Definition |
| --- | --- | --- |
| What should the tenant pay **now**? | `due_now` | every charge line dated today or earlier, read net, less what settled it |
| How much of that is **already late**? | `arrears` | the part of `due_now` whose date is **before** today |
| What is the **next** thing, and when? | `next_charge`, `next_rent_date`, `next_rent_amount` | the soonest charge dated after today that still owes; if none has been raised, the lease's own next due date and amount |
| What is billed but **not due yet**? | `not_yet_due` | charges dated after today — stated in a sentence, never a headline |

### Due today is due now, not late

The boundary is exact and tested as a table: dated before today → arrears; dated today → due now, and not
late; dated after today → not yet due. A charge that is fully covered — by a payment, a credit, or both —
is never late and is never "the next thing due". Money that is merely *expected* does not reduce any of
these figures, exactly as it does not reduce the balance (ADR-008).

`arrears_oldest` names the oldest unpaid charge and `arrears_age_days` its age, because the desk works the
oldest money first, and age is what says so.

### The lease answers when nothing has been raised

The office raises charges a month at a time, so the incoming month usually has no entry. A tenant should
not see an empty card because nobody pressed a button, so `LeaseLedger.next_rent_date` falls back to
`apps.ledger.services.upcoming_rent_date(lease)`, which reads the lease: the stored due day, clamped to a
day the month actually has (`apps.common.dates.due_date_in`, already the Phase 4 rule), never before the
term starts, never after it ends, and only for an active lease. `next_rent_amount` is what is left on a
raised charge, or otherwise `Lease.rent_for(date)` — deliberately asked of the lease rather than read from
the field, so the rent-schedule extension (stepped rent, not yet built) has one place to answer.

The forecast is a reading of the agreement, not a promise about the ledger: when the charge is raised, its
own date and amount take over, and if the office raises something different, the ledger is right and the
forecast was only ever a projection.

### What each surface shows

- **Tenant** (`/account/`, `/lease/`, `/payments/`): *Due now* as the headline, with *"$4,588.00 past due
  · since July 5, 2026"* beneath it when any of it is late; *Next rent due* as a date and an amount; and a
  muted sentence for what is billed but not yet due. The three surfaces share one component
  (`templates/components/amounts_due.html`), so they cannot tell three stories.
- **Office** (`/manage/ledger/`, the lease ledger, the lease panel): the **whole balance** is still shown —
  a desk wants the ledger total — alongside *Past due* with the age of the oldest unpaid charge, and
  *Coming due* dated whether or not it has been raised, marked "not billed". The aging that matters to a
  desk stays on the desk's screens.

The specification's dashboard sketch labels the first card *Current Balance* and asks the tenant "How much
do I owe?". The card keeps its place and the layout is unchanged; it is now labelled **Due now**, because
that is what the question means to the person asking it, and the whole-term figure the old label named is
what made the page read as a demand. The change is a clarification of the existing figure, not a new
capability, so the specification itself is untouched.

### Vocabulary

- **Overdue** stays the state of *one charge* whose date has passed and which still owes money
  (`ChargeState.OVERDUE`). The tenant-facing label for that row is now **Past due**.
- **Arrears / past due** is the *sum* whose date has passed — the number to chase.
- **Coming due** is the *next* obligation — the date and amount to expect.
- **Balance** remains the whole ledger, and is an office figure.

## Consequences

**Positive**

- The tenant's headline is the amount actually being asked for now ($4,588), not the term's remainder
  ($8,756). The figure a person is meant to act on is the figure in the largest type.
- "Next rent due" is true in every state: a raised incoming month shows its own date and what is left on
  it, an unraised one shows the lease's date, and an ended lease says no further rent falls due.
- Arrears and the next rent can no longer be confused, because they are different properties with
  different names; a screen that shows both reads as two facts rather than one contradiction.
- Nothing about allocation, immutability, or the audit trail changed: this is a second reading of the same
  `ChargeLine` allocation, and every figure is still derived per request.

**Negative / accepted trade-offs**

- A tenant no longer sees the whole term's balance anywhere. Accepted deliberately: it is not a bill, and
  the office can always state it. If the owner wants it back it belongs in an expandable "how this is
  worked out" panel, not in the headline.
- The forecast can differ from what the office later raises (a mid-term rent change, a credit raised
  instead of a charge, a manual charge that lands first). Accepted: on the day the entry exists the entry
  wins, and the ledger is never wrong about what it holds.
- Two more derived figures to keep in step with the ledger. Contained the same way as ADR-011: one
  derivation over one `LeaseLedger`, with an explicit boundary table and a regression test built from the
  owner's own numbers.
- `upcoming_rent_date` needs the lease's status, term, and due day, so the ledger's answer now depends on
  the lease as well as its entries. That is why it lives in the ledger service and not in a template.

## Alternatives considered

- **Keep one balance and add "due now" as smaller print**: the wrong number stays the biggest thing on the
  page, which was the complaint. Rejected.
- **Redefine "next rent due" as the oldest unpaid month**: what it already did, and what the owner
  identified as wrong — it is arrears wearing the wrong label. Rejected.
- **Show nothing when the incoming month has not been raised**: makes the portal's answer depend on an
  office action, so the tenant sees a blank where a date belongs. Rejected.
- **A 1–30 / 31–60 / 61–90 / 90+ aged-bucket table on the tenant page**: standard on a collections desk
  and a debt-collection posture to show a resident. The age is kept for the desk (`arrears_age_days`);
  reminders and buckets belong to a later phase, with the wording decided then.
- **A separately stored "amount due" column**: a second place for the truth to live, and a nightly job to
  drift. Rejected on ADR-008's principle — nothing stores a balance.
- **Calling the new figure "amount due"**: close to "balance due", which the office already uses for the
  ledger total. *Due now* / *past due* / *coming due* say which question each one answers.

# RHP — proposed extensions (E1–E3)

**Status: proposed. For the owner's review after consulting RHP's leasing requirements. Nothing in this
document is built, and nothing will be built until each entry below is approved.**

Prepared 2 October 2026, from the owner's review of Phase 5 and the product conversation around it.

This document is the register of additions to RHP that are **not** in the governing specification
([`harness/master-spec.md`](harness/master-spec.md)). The specification models a lease as one term, one
monthly rent, and a ledger of charges and payments. Real tenancies do a few more things than that, and
these three entries are the ones RHP has actually been asked for:

| # | What it is | Why it exists | Kind | Status |
| --- | --- | --- | --- | --- |
| **E1** | **Rent schedule (stepped rent)** | A 4-year lease whose rent rises about 7% a year | Core-semantic | Proposed |
| **E2** | **Standing charges (utilities and other recurring amounts)** | Water, trash, parking, pet rent — repeating amounts that are not rent | Additive | Proposed |
| **E3** | **Concessions (forgiveness and deferral)** | Relief granted to a tenant — a month credited, or moved | Additive | Proposed |

How to read this:

- **Each entry starts with the business question**, then what the tenant and the office would see, then
  the decisions that are yours to make, then what the entry deliberately does *not* do.
- **"Implementation notes" are collected in the appendix** at the end. They are for the person building
  it and can be skipped when forwarding this document.
- **The one section to fill in is "Decisions I need from you"**, near the end. It is written so you can
  answer it in a reply.

---

## 1. How a change to the specification is handled

The specification is the contract every phase was built against. It says of itself: *"when a change is
genuinely needed, change it here first, in its own commit, with a note explaining why."* That rule is
honoured — but proposals, open questions and statuses do not belong in the contract text, so they live
here instead:

1. **Nothing is built before it is written down and approved.** An entry moves
   Proposed → Approved → Building → Built, and an entry is never deleted, so the decision history stays
   visible even if an idea is dropped (Withdrawn / Superseded).
2. **Every entry is classified before code**, because the class decides how careful the change is:
   - **Additive** — a new table or capability; everything that exists today behaves exactly as it does now.
   - **Core-semantic** — changes what an existing field or figure *means* (for example, "monthly rent"
     stops being the whole story). These must carry an invariant: a lease that does not use the new
     feature must answer exactly as it does today.
   - **Presentation** — wording, labels, layout only; no data change.
3. **One extension = one entry = one branch.** Branches are named after the extension
   (`rhp-rent-schedule`), not after a new phase number: Phases 6–12 are already committed to, and
   renumbering them would invalidate every earlier reference and plan.
4. **Each entry carries its own acceptance criteria and tests**, in the same style as the phases. The same
   gate applies, and you test it before it is folded into `main`.
5. **A non-goal is amended, never quietly bypassed.** If an extension would contradict one of the
   specification's explicit non-goals, the entry has to say which one and why, before approval.
6. **An extension may not break an existing phase's acceptance criteria.** If it would, the entry names
   the criterion and what replaces it.
7. **The money rules are not renegotiable per extension:** nothing stores a balance, nothing edits or
   deletes a ledger entry, corrections are new entries, and money is never a float.
8. **One decision record (ADR) per built extension**, written when it is built; the register links to it
   and records the outcome.
9. **When an entry is approved, the specification gains a one-line appendix row** naming the change and
   the ADR, so the contract and what was built stay in step.

---

## 2. E1 — Rent schedule (stepped rent)

### The business question

A four-year lease does not usually hold one rent for four years. RHP needs to record "rent is X until
this date, then Y, then Z" and have the ledger charge the right amount each month without anyone
remembering the numbers.

**Classification: core-semantic.** Today "monthly rent" is the rent, full stop. After E1, it means "the
rent at the start of the term", and the schedule carries the changes. The invariant that makes this safe:
**a lease with no schedule behaves exactly as it does today, to the cent.**

### Worked example

A four-year tenancy at $2,084.00 a month due on the 5th, rising 7% on each anniversary:

| Period | Monthly rent | How it is decided |
| --- | --- | --- |
| 2027 | **$2,084.00** | The lease's starting rent |
| 2028 | **$2,229.88** | 7% on the previous amount |
| 2029 | **$2,385.97** | 7%, rounded to the cent |
| 2030 | **$2,552.99** | 7%, rounded to the cent |

Deciding to round each new rent to the nearest dollar instead gives $2,084.00 / $2,230 / $2,386 / $2,553.
That is a decision to make (see the questionnaire); either way, **the amount is decided once and stored**,
and the ledger charges what is stored. RHP never re-derives money from a percentage after the fact, so a
later change to the rounding rule can never rewrite a past month.

### What the tenant sees

- Their lease page: the rent today, **and the next change** — "Monthly rent $2,084.00 · rises to
  $2,229.88 on 5 January 2028" — plus the remaining schedule in a short list.
- Their dashboard's "Next rent due" card: automatically the right amount for the month it falls in.
- Their statement: each month's charge at the amount that actually applied to that month.

### What staff do

- On the lease, add a dated amount whenever the rent changes; remove one that was entered wrongly
  (before it has been charged).
- Create the rent charges as they do today: the button fills in every missing month **at the amount that
  applies to that month**.
- A month that was already charged is **never rewritten** when a schedule changes. If a raise was entered
  late and a month was charged at the old rent, the office corrects that month with an adjustment, so the
  record shows what was charged and what corrected it (the existing rule).

### Decisions to make

| # | Question | Options | Recommendation |
| --- | --- | --- | --- |
| E1-D1 | How is a change entered? | (a) The new monthly amount and the date it starts; (b) a percentage and the app works out the amount | **(b) with (a) available** — type "7% from 5 Jan 2028", see the figure RHP calculated, then save the decided amount |
| E1-D2 | Rounding of a percentage-derived rent | Nearest cent, nearest dollar, nearest $5 | **Nearest dollar** is what tenants and leases usually state; nearest cent is the default if you prefer exactness |
| E1-D3 | Does "monthly rent" on the lease change when the rent rises? | (a) It stays the starting rent and the schedule shows the rises; (b) it is overwritten by the current rent | **(a)** — the original agreement stays legible, and the current rent is always shown alongside it |
| E1-D4 | Who may change the schedule, and when? | Managers and admins; only admins; only before the lease is activated | **Managers and admins, any time before the tenancy ends**, with every change recorded in the tenancy's history |
| E1-D5 | Does the tenant see the whole remaining schedule? | Only the next change; the next change plus the rest | **Next change plus the rest** — three lines on a four-year lease is information, not noise |

### What E1 deliberately does not do

- No late fees or interest, no proration of a part month, no mid-month rent change (a rise always applies
  from a rent due date).
- No automatic notice letters when the rent rises (a letter is a document — Phase 6 territory).
- No index-linked rent (CPI and similar). Amounts are decided and stored, not computed from a public
  figure.
- No rewriting of anything already charged.

### Acceptance criteria

- A lease with no schedule charges, and reads, exactly as it does today (a regression test, not an
  intention).
- A worked four-year lease with three rises generates the exact right amount for every month.
- A percentage rise is stored as a decided amount, rounded once, and never re-derived.
- A rise dated outside the tenancy, or on a day that is not a rent due date, is refused.
- A rise entered after a month was charged leaves that charge untouched.
- An ended tenancy's schedule is read-only.
- The tenant sees the current rent and the next change; the dashboard's next-rent card matches the
  ledger.

---

## 3. E2 — Standing charges (utilities and other recurring amounts)

### The business question

Some tenancies include amounts that repeat every month and are not rent: water, trash, a parking space,
a storage unit, pet rent, a recurring amenity fee. Today each one has to be typed in as a one-off charge
every month, which is easy to forget and easy to get wrong.

**Classification: additive.** Nothing about rent, the balance, or an existing charge changes. RHP gains a
new kind of repeating instruction and a new charge category.

### Worked example

Water $60.00 and trash $25.00 a month, due on the same day as the rent, for a tenancy whose rent is
$2,084.00:

- The tenant's **statement** lists "Water $60.00" and "Trash $25.00" as their own lines each month.
- Their **Due now** figure includes them once their date arrives.
- Their **"Next rent due"** card still says rent — a utility does not take over that card.
- The office's ledger shows them like any other charge, and payments settle oldest-first across rent and
  utilities together, exactly as today.
- Stopping a utility (the tenant moves out of the parking space) stops future months; the months already
  charged stay on the record.

### Decisions to make

| # | Question | Options | Recommendation |
| --- | --- | --- | --- |
| E2-D1 | Which repeating amounts to support | A fixed list (water, trash, parking, storage, pet rent…); a free-text label; both | **A free-text label with a short category** — RHP will not know every name in advance, and the label is what the tenant reads |
| E2-D2 | When is it due? | Same day as the rent; its own day | **Its own day, defaulting to the rent's day** — some utilities are billed mid-month |
| E2-D3 | Should a utility appear on the tenant's dashboard cards? | Only in the statement and in Due now; also as its own card | **Only in the statement and Due now** — three cards stay three cards; a fourth figure invites a fourth question |
| E2-D4 | How does one stop? | End date; an "active" switch; delete it | **An end date** (with a one-click "stop after this month"); nothing already charged is affected |
| E2-D5 | Are utilities charged for a vacant unit? | No — the tenant ledger only | **No.** What RHP pays while a unit is empty is an owner expense, not a tenant charge; recording owner expenses would be its own entry |

### What E2 deliberately does not do

- No metered billing (usage × rate), no estimated reads, no meter readings at all.
- No utility invoices or statements as documents (that is Phase 6), and no utility account management.
- No splitting one bill between co-tenants — the tenancy is the payer, as it is today.
- No landlord-side expense tracking or owner statements.

### Acceptance criteria

- Charging twice for the same month creates one charge, not two.
- Nothing is charged before the start date, after the end date, or after the tenancy ends.
- A utility due before the rent does not appear as "next rent due".
- Stopping a repeating amount leaves every charge already raised untouched, and its history intact.
- A utility is settled by a payment in the same oldest-first order as everything else.

---

## 4. E3 — Concessions (forgiveness and deferral)

### The business question

Sometimes RHP grants relief: a month credited because of a hardship, a repair that made the unit
unusable, a goodwill gesture, or a month moved to a later date rather than forgiven. The ledger can
already express both — a credit against a charge, and a new charge dated later — but it records them as
two unrelated entries, and nobody can later answer "how much relief did we grant, and to whom, and why?"

**Classification: additive, with one presentation change.** The money mechanics are unchanged. What is
new is that the *decision* is recorded once, with its reason and a wording the tenant is shown.

### Worked example

April's rent is $2,084.00.

- **Forgiveness:** the April charge reads **$0.00 — "Concession: April rent credited (repair works)"**,
  and the concession is recorded on the tenancy with the amount, the date and the internal reason. The
  balance falls by $2,084.00 exactly as it would have with a plain credit.
- **Deferral:** the April charge reads $0.00 with the same note, and a new charge appears dated
  1 October for $2,084.00 — "Deferred April rent". The tenant sees both the credited month and the month
  it moved to, rather than two amounts they have to reconcile.

### Decisions to make

| # | Question | Options | Recommendation |
| --- | --- | --- | --- |
| E3-D1 | Does the tenant see the concession's wording? | Yes, always; yes but only a short generic phrase ("Concession granted"); no | **Yes**, from a short tenant-facing note written for them — the internal reason stays office-only. (This is a deliberate exception to the current rule that an adjustment's free-text reason is not shown: a concession is a decision *about* the tenant, and they were told about it.) |
| E3-D2 | Deferral shape | One later date; a repayment plan in instalments | **One later date** in this entry; a repayment plan would be its own entry with its own rules |
| E3-D3 | Who may grant one? | Managers and admins; admins only | **Admins only**, matching who may already credit a charge, so the everyday act is the manager's and the act that changes what is owed is not |
| E3-D4 | Can a concession be undone? | Yes, by a correcting entry that says why; no | **Yes, by a correcting entry** — mistakes are visible corrections, never deletions (the existing rule) |

### What E3 deliberately does not do

- No approval workflow (one authorised person grants it, and it is recorded).
- No hardship assessment, scoring, or eligibility rules — RHP records the decision a person made.
- No instalment/repayment plans, and no automatic waiving of late fees.
- No concession letters or agreements as documents (Phase 6), and no bulk granting across tenancies.

### Acceptance criteria

- A forgiven charge shows at its reduced figure, and the concession is recorded once with its reason.
- A deferral creates exactly one future charge, linked to the month it defers.
- Crediting more than is actually left on the charge is refused.
- An ended tenancy can still be granted a concession (it is a money correction).
- Only an admin can grant one; the tenant sees the tenant-facing note and never the internal reason.
- A mistaken concession is corrected by a new entry that says why; nothing is edited or deleted.

---

## 5. Decisions I need from you

Answer in a reply, in any order. Everything else in this document follows from these.

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| 1 | **E1**: are rent rises entered as a new amount and a date, or as a percentage the app works out? | Percentage *with* the decided amount shown and stored | |
| 2 | **E1**: how should a percentage-derived rent be rounded? | To the nearest dollar | |
| 3 | **E1**: does "monthly rent" on the lease stay the starting rent, with the schedule showing rises? | Yes | |
| 4 | **E1**: who may change the schedule, and up to when? | Managers and admins, until the tenancy ends | |
| 5 | **E1**: does the tenant see only the next rise, or the whole remaining schedule? | The next rise plus the rest | |
| 6 | **E2**: which repeating amounts do you actually bill, and what are they called on a tenant's statement? | Free-text label with a short category | |
| 7 | **E2**: same due day as the rent, or its own? | Its own, defaulting to the rent's day | |
| 8 | **E2**: should repeating utilities get their own dashboard card? | No — statement and "Due now" only | |
| 9 | **E2**: how is one stopped? | An end date set to the month you want it to stop | |
| 10 | **E3**: does the tenant see a concession's wording? | Yes, from a short note written for them | |
| 11 | **E3**: is a deferred month a single later date, or a payment plan? | Single later date for now | |
| 12 | **E3**: who may grant a concession? | Admins only | |
| 13 | **Process**: is this the right way to add things to RHP — register, approve, one branch, one decision record? | Yes | |

Two questions that are not mine to answer, and that would change the list above if the answer is yes:

- **Do RHP leases ever escalate by a formula rather than a stated amount** (CPI, a published index, a
  market review)? If so, E1 needs a rule for who supplies the figure each year.
- **Does RHP ever need to bill a tenant for a *recovered* cost** (a recharge for damage, a submetered
  usage share)? Those are one-off charges today; only repeating amounts are E2.

---

## 6. What this document is not

Not proposed here, and each would be its own entry with its own questions:

- late fees, interest, or penalties;
- proration of a part month;
- lease renewals or a "copy this lease forward" flow;
- repayment plans and instalment schedules;
- online payment processing (Phase 11, and it stays behind an explicit decision);
- owner expenses, owner statements, or anything that is not a tenant charge.

Two of these are already answered in the specification's own way: a part month is a one-off charge typed
by the office, and the deposit is held money that never touches the rent ledger.

---

## Appendix — implementation notes (for the engineer)

Current code the entries build on: `Lease.rent_for(on_date)` already exists and every caller asks the
lease rather than reading `monthly_rent`; `Charge` is append-only with frozen financial fields and a
`(lease, due_date, kind=RENT)` uniqueness rule that makes rent generation idempotent; `AuditEvent.action`
is a free 32-character field, so new action values need no migration; `build_ledger` is still the single
derivation of every money figure, and `docs/decisions/` holds one record per decision.

### E1

- **Model** (`apps/leases/models.py`): `RentIncrease` — `lease` (PROTECT, `related_name="rent_increases"`),
  `effective_date` (the rent due date the new amount starts from), `amount` (12,2, ≥ 0.01), `reason`,
  `created_by`, `created_at`; unique `(lease, effective_date)`; ordered by date.
- **Semantics**: `monthly_rent` = the rent at the start of the term; `rent_for(on_date)` returns the latest
  row dated on or before `on_date`, otherwise `monthly_rent`. No rows → today's behaviour exactly.
- **Validation**: `effective_date` must fall inside the term **and** on a rent due date for that lease
  (via `apps.common.dates.due_date_in`), so a rise can never apply half a period.
- **Generation**: `generate_rent_charges` asks `lease.rent_for(due)` instead of `lease.monthly_rent` —
  one call site. Existing charges are never rewritten.
- **Query cost**: cache the rows per instance; prefetch `rent_increases` wherever ledgers are built in
  bulk; a `django_assert_num_queries` test for the tenant dashboard and the ledger overview (there is
  precedent for that kind of test).
- **Screens**: a "Rent schedule" section on the lease detail/edit pages (Manager+, read-only once ended);
  the tenant's lease page and the office's ledger header show the current amount and the next change.
- **Audit**: new `RENT_SCHEDULE_CHANGED` action; schedule rows are lease terms (editable, audited), not
  ledger entries (append-only).
- **Tests**: no-schedule regression; worked four-year example; rounding stored once; off-term and
  off-due-date refusals; a charged month untouched by a later rise; ended lease read-only; permission
  checks; query counts.

### E2

- **Model** (`apps/ledger/models.py`): `RecurringCharge` — `lease` (PROTECT), `label`, `kind` (default a
  new `ChargeKind.UTILITY`), `amount`, `due_day` (1–31, clamped, defaulting to the lease's `rent_due_day`),
  `starts_on`, `ends_on` (null = open), `notes`, `created_by`, `created_at`. `Charge` gains
  `recurring` (FK, null, PROTECT) and it joins `FROZEN_FIELDS`; a partial unique constraint
  `(recurring, due_date)` keeps generation idempotent in the database, exactly as
  `one_rent_charge_per_month` does for rent.
- **Generation**: one action generates everything recurring on the lease (rent and standing charges),
  bounded by the term, the end date and the horizon; per-kind counts in the message; every created charge
  audited with its source.
- **Interface fix E2 forces**: `next_charge` is the soonest charge of *any* kind and currently feeds
  "next rent due". E2 splits out a rent-specific sibling so a utility due before the rent cannot take
  over the tenant's rent card; the office's "coming due" column keeps the any-kind figure.
- **Settings**: `RHP_RENT_CHARGE_HORIZON_MONTHS` becomes `RHP_CHARGE_HORIZON_MONTHS` (nothing sets it in
  `.env` or `.env.example`, so no deployment is affected).
- **Screens**: a "Standing charges" section on the lease detail/ledger pages (add, change the amount, stop
  with an end date); no new tenant card.
- **Tests**: double generation creates nothing twice; nothing outside start/end/term; utility before rent
  does not become the next rent; stopping leaves raised charges intact; FIFO allocation across kinds;
  permission checks.

### E3

- **Model**: `Concession` — `lease`, `kind` (`FORGIVENESS` | `DEFERRAL`), `charge` (the charge conceded,
  PROTECT), `amount`, `deferred_to` (required for deferral, refused for forgiveness), `reason`
  (office-facing), `tenant_note` (what the tenant reads), `adjustment` and `deferred_charge` (OneToOne
  links to the entries it created), `created_by`, `created_at`.
- **Service**: `grant_concession(...)` in one transaction creates the credit against the named charge and,
  for a deferral, the new dated charge, links both back to the concession, and writes a
  `CONCESSION_GRANTED` audit event. It wraps the existing adjustment service rather than adding new money
  arithmetic.
- **Presentation**: the tenant's statement row gains one line for the concession note; the office's lease
  history shows the decision. The internal reason is never rendered on a tenant page.
- **Corrections**: a mistaken concession is corrected by an opposing entry linked to the same charge, with
  its own reason — nothing is edited or deleted.
- **Tests**: forgiveness nets the charge and records the decision once; deferral creates exactly one future
  charge; over-crediting refused; ended lease allowed; admin-only; the tenant sees the note and not the
  reason; correction path.

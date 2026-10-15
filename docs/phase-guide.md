# RHP phase guide

This is the **long-horizon** view of how RHP is being built: **which later phase will come back and change
something that already works**, and the questions that are deliberately left open until there is real usage
to decide them with. Use it to see the churn coming before it happens.

Companion documents:

- [`phases/README.md`](phases/README.md) — **the index of phase records.** One record per phase: scope,
  what exists today, the decisions that govern it, its gaps, and the questions waiting on you. Start there
  for a single phase.
- [`roadmap.md`](roadmap.md) — the same phases as a terse status checklist, and the milestones.
- [`extensions.md`](extensions.md) — additions the specification does not cover, filed under the phase they
  extend.
- [`harness/master-spec.md`](harness/master-spec.md) — the original specification every phase is measured
  against. It governs.

## How to read this

- **A phase is a chunk of work with a finish line.** Nothing from a later phase is built early, and a phase
  is finished only when its acceptance criteria are tested and you have looked at it.
- **Status words** (the same closed set the tooling maps into Plane): *Complete* = built, tested, in `main`,
  signed off. *Built* / *In review* = built and tested, not yet signed off; work continues on a branch.
  *Next* = about to be built. *Building* = in progress. *Not started* = planned. *Withdrawn* = dropped.
  *Blocked* = waiting on an explicit decision from you.
- **Every phase follows the same path:** work happens on a branch (`rhp-1`, `rhp-2`, …, `rhp-e4-onboarding`
  for an extension), you test it, then it is squashed into `main` as a single commit and the branch is
  deleted. A phase squashed into `main` is finished; new work always starts from `main`.
- **Nothing here is archaeology.** If a decision in an earlier phase is making later work awkward, the fix
  happens in the phase that needs it, and this document records that in advance.

Where each phase stands right now is the table at the top of [`phases/README.md`](phases/README.md), kept
in step with the roadmap.

## Cross-phase change map

Things that will be revisited, and by which phase. This is the quickest way to see where churn is coming.

| Element | Built in | Revisited by | What changes |
| --- | --- | --- | --- |
| Tenant dashboard | Phase 5 | Phase 6, 7, 8, 9 | Gains documents, live maintenance and announcements; Phase 9 consolidates the dashboards |
| Reading money as a tenant | Phase 5 review | Phase 10, 11 | The statement nets corrections and pages; reports and a payment provider will each need their own reading of the same records (ADR-011) |
| Tenant payment history | Phase 5 | Phase 11 | May gain a "pay now" action once a provider is chosen |
| Single lease file | Phase 3 | Phase 6 | Becomes documents in the documents table (categories, visibility, multiple files) |
| Lease document access rule | Phase 3 | Phase 6, 12 | Generalised to all documents; included in the security test pass |
| Tenant `/lease/` page | Phase 3 | Phase 4, 5 | Phase 4 added the balance and activity; Phase 5 added the dashboard beside it, so this page stays the lease detail |
| Occupancy / vacancy definition | Phase 3 | Phase 9, 10 | Reported on in the dashboard and the occupancy report |
| Staff landing counters | Phases 2, 3, 4, 7 | Phase 9 | Replaced by the real admin dashboard (P9-Q2) |
| Rent due day (stored) | Phase 3 | Phase 4 | Done: the month-end clamping rule lives in `apps.common.dates.due_date_in` |
| Lease status changes | Phase 3 | Phase 4 | Done: they are written to the audit table, not only the log |
| **Charging an ended lease** | Phase 4 | **This branch's successor** | **Ending a lease changes nothing about its money today** — a new charge can still be raised, and rent raised for months that will not happen has no close-out. The fix waits on P4-Q1…P4-Q6; see [`workflows/tenancy-and-money.md`](workflows/tenancy-and-money.md) |
| Structured security logs | Phases 1, 2 | Phase 4, 12 | Phase 4 added the audit table; Phase 12 decides retention and whether the append-only rules need database enforcement (P12-Q5) |
| Banner photo | Phase 2 | Phase 6, 12 | Thumbnails and resizing; content-security policy for the map |
| Map pin | Phase 2 | Phase 12 | The Google embed becomes an explicit security-policy entry |
| Bedrooms / bathrooms | Phase 2 | Phase 10 | Used for sizing and rent-roll reporting |
| Tenant contact notes | Phase 1 | Phase 5+ | Surface on the tenancy screens once tenants have a dashboard |
| Invitations and passwords | Phase 1 | Phase 12 | Two-factor authentication for staff (P12-Q3); session hardening |
| Property / unit retirement | Phase 2 | Phase 10 | Retired records stay in reports as history (P2-Q1) |
| Residential/commercial designation | Phase 2 | Phase 4 review | Moved from the unit to the property; the unit list is grouped by building (ADR-006 revision) |
| Unit size and amenities | Phase 2 | Phase 4 review, 10 | Square feet feeds sizing reports; the amenity list is maintained in the back office |
| Tenant photo | Phase 1 | Phase 4 review, 12 | Admin-set for now; Phase 12 puts personal data through the security pass (ADR-009) |
| Money fields | Phase 3 | Phase 4, 11 | Phase 4 reads them in the ledger; Phase 11 reconciles provider payments against entries |
| Balance and charge states | Phase 4 | Phase 9, 10, 11 | Reported on in the dashboard and the money reports; a provider may need payments applied to named charges rather than oldest-first (P11-Q3). Phase 5's review split the one balance into what is due now, what is past due and what is coming due (ADR-008, ADR-012) |
| Audit trail | Phase 4 | Phase 9, 12 | Phase 9 adds the audit browser; Phase 12 decides retention (P12-Q4) |
| Property responsibilities vs maintenance cost | P4-E2 | Phase 7 | A cycle recovers a recurring cost; a Phase 7 request is work done. If one repair should be both fixed and recharged, that link is Phase 7's design (P7-Q2) |

## Questions deliberately left open

Collected so nothing is forgotten and nothing is decided by accident. **Each one is owned by a phase
record** — the record carries the id, my recommendation and your answer, and this list is the cross-phase
view of them.

- **Charging an ended lease** — P4-Q1 (what ending means for money), P4-Q2 (what happens to rent already
  raised for months that will not happen), P4-Q3 (which money actions an ended lease still allows), P4-Q4
  (where the rule is enforced), P4-Q5 (how it reads in Accounting). The case study is
  [`workflows/tenancy-and-money.md`](workflows/tenancy-and-money.md).
- **A lease ended by mistake** — P3-Q2: reopenable by a superadmin, audited? Today only a database edit
  restores it.
- **Does a lease expire by date, or only when a person ends it** — P3-Q1.
- **Renewing a lease** — P3-Q3. There is still no "copy this lease forward" action, so a renewal is typed
  again from scratch; once real tenancies roll over this will be the most common repetitive job on the desk.
- **Month-to-month leases** — P3-Q4. The term currently needs both a start and an end date.
- **Proration and late fees** — rent escalation is **answered** (P3-E1 added templates and a stored
  schedule). Proration and late fees are still not in the specification: a tenancy starting mid-month is not
  prorated, and the desk records a one-off charge for the part month. Either would be its own extension.
- **Deposits** — P4-Q6. Decided in Phase 4: the deposit stays a field on the lease and is deliberately
  **not** on the ledger, because held money is not rent paid ahead. When returns and deductions are needed
  they get their own treatment (what was withheld, and why).
- **A move-out settlement** — P4-Q6. The end of a tenancy has no final-statement moment today, which is why
  the ended-lease work has nowhere to hang one.
- **Who is liable for the rent** — a lease records a primary *contact*, not a payer, and Phase 4 puts the
  balance on the **lease**, shared by everyone on it. If RHP needs joint-and-several liability, split
  responsibility, or a guarantor, that reaches back into the lease's tenant rows and into how a payment is
  attributed. **Not yet asked as a question**; it needs a phase to own it, and the honest answer may be "not
  yet".
- **Applying a payment to a named charge** — P11-Q3. Phase 4 applies money oldest-first, which is what a rent
  ledger does; a provider sending remittance detail is where an allocation table would earn its keep.
- **Invoices, statements and receipts** — P6-Q3 and P10-Q1. Nothing in the ledger produces a document yet.
  Phase 6 makes it possible; whether RHP wants it is your call.
- **Direct messaging** — P8-Q4 and the Phase 8 record: announcements cover the real need; a chat system is a
  much bigger commitment and is explicitly deferred.
- **Payment provider** — P11-Q1. Phase 11 waits for your decision, and nothing else is blocked by it.
- **How much tenants should see** — P5-Q1. Phase 4 shows a tenant their balance, the next amount and
  activity, but not the audit trail behind it. Whether a tenant ever sees the history of changes to their own
  lease is easy to add later and better decided with real usage in front of us.

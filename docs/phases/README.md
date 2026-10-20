# RHP phase records

One record per phase. Each one says what the phase is, what exists in the code today, the decisions that
govern it, what it deliberately leaves out, what is broken or missing, and **what I need you to decide**.

These records do not replace anything. The specification (`harness/master-spec.md`) governs; the plan and
its status live in `roadmap.md`; the register of approved additions is `extensions.md`; the *reasons* are
in `decisions/`. A record **cites** those and adds the working knowledge that was previously scattered
across four documents: the paths, the screens, the tests, and the open questions.

**Status words are a closed set**, because the tooling maps them to Plane states and anything else becomes
"backlog" silently: `Complete`, `Built`, `In main`, `Next`, `Building`, `Not started`, `Withdrawn`,
`Blocked`.

## The phases

| Phase | Record | Status | What you can do with it today |
| --- | --- | --- | --- |
| 0 | [Foundation](phase-00-foundation.md) | Complete | Run RHP anywhere, deploy it, check its health |
| 1 | [Identity and access](phase-01-identity-and-access.md) | Complete | Staff and tenants sign in, tenants are invited, roles decide what each sees |
| 2 | [Portfolio](phase-02-portfolio.md) | Complete | Record properties and units, photograph them, pin them on a map |
| 3 | [Lease management](phase-03-lease-management.md) | Complete | Put tenants on a lease, activate it, read it as that tenant |
| 4 | [Rent ledger](phase-04-rent-ledger.md) | Complete | See what each tenancy owes, charge rent, record payments, correct mistakes without erasing them |
| 5 | [Tenant dashboard](phase-05-tenant-dashboard.md) | Complete | What is due now, what is next, when the lease ends, and the statement — on a phone |
| 6 | [Document management](phase-06-document-management.md) | Complete | File a lease, an addendum, a notice or an inspection against a tenancy, choose whether the tenant sees it, and hand it back only through a permission check |
| 7 | [Maintenance](phase-07-maintenance.md) | Complete | Requests, private conversations, work tracking, costs and reviewed recharges |
| 8 | [Communications](phase-08-communications.md) | Complete | Private/shared messages, announcements, protected files and email delivery review |
| 9 | [Admin dashboard](phase-09-admin-dashboard.md) | Complete | Rent-first operational dashboard and searchable history |
| 10 | [Reporting and search](phase-10-reporting-and-search.md) | Not started | — |
| 11 | [Payment integration](phase-11-payment-integration.md) | Not started — approved, optional for 2027 | One-time ACH and ACH autopay; processor-hosted bank linking |
| 12 | [Production hardening](phase-12-production-hardening.md) | Not started | — |

Milestones group the phases: 0+1, 2+3, 4+5, 6+7, 8+9, 10+12, with 11 later. The milestone table is in
`roadmap.md`.

## Extensions, filed under the phase they extend

An extension is an approved addition the specification does not cover. They are numbered **per phase** —
`P4-E1` is the first extension to Phase 4 — so that reading a phase record shows everything that changed
it. The register (`extensions.md`) keeps the flat ids `E1…E4` for now, because the Plane mirror's parser
only recognises that pattern; the phase-scoped id is recorded here and lands in the register when the
tooling accepts it.

| Phase-scoped | Register now | What it is | Status |
| --- | --- | --- | --- |
| P3-E1 | `E1` | Lease templates: Fixed, Step Up, Triple net (NNN), and amounts the lease states | In `main` — [ADR-013](../decisions/ADR-013-lease-templates.md) |
| P4-E2 | `E2` | Property responsibilities charged to the unit, read as one month by the tenant | In `main` — [ADR-014](../decisions/ADR-014-property-responsibilities.md) |
| P4-E4 | `E4` | Retroactive onboarding: a live tenancy brought in without inventing a debt | In `main` — [ADR-016](../decisions/ADR-016-retroactive-onboarding.md) |
| P4-E3 | `E3` | Concessions: a month forgiven or deferred | Proposed |
| P8-E1 | `E12` | Tenant–RHP messaging: private conversations, attachments, unread state and email | Approved scope — unbuilt; decisions pending |

Extensions are listed in the record of the phase whose deliverable they changed most. Several reach
across phases — P4-E2 also touched the portfolio, P4-E4 also touched lease terms — and each record names
what it reached into.

## How to ask me something, and how I ask you

The working agreement, now that Plane is a two-way surface rather than a mirror:

- **A question** is answered in Plane — comment on the phase's work item, or edit the answer cell if you
  prefer — or just tell me here. I write your answer into the record's table, then write the implementation
  plan for that phase or extension from it. Nothing is built from a recommendation that still says
  *(awaiting)*.
- **A bug** is raised in Plane as its own ticket, in your own words. `verify` counts only the items the
  mirror owns, so a ticket you raise is never read as drift; I reproduce it here, fix it on a branch, and
  settle the ticket with what changed. If it turns out to be a *decision* rather than a defect, it becomes a
  question in the record of the phase that owns it.
- **A record is the source for three things** — the Outline page, the Plane description and the checkout —
  so a change to one is published to all three (see below).

Each record ends with an **Open questions for the owner** table: a stable id (`P4-Q1`), my recommendation,
and a cell for your answer. **The whole record is what Plane shows as the work item's description**, so
everything below the item's title is this file.

A defect found while testing is not a question: it goes in **Known gaps and defects** with the steps that
reproduce it, and its fix is scheduled like any other work.

## Editing a record, and what it moves

A record is the source for three things, so a change to one is published to all three:

```bash
make -C ecosystem docs-sync ARGS=--apply     # the record as an Outline page
make -C ecosystem plane-sync ARGS=--apply    # the record as its phase's Plane description
make -C ecosystem verify                     # the exit criterion: all three agree
```

`verify` fails naming the file or the item if they do not, and it reports when a sync would still change
something — so "I published it" is a checked claim rather than an assertion.

## Checking the record set is intact

`tests/docs/test_plan_contract.py` compares these records with the plan: every phase in the roadmap has a
record, its `**Status:**` word matches the roadmap row, every question id is unique and well formed, and
the two tables the tooling parses still have the headers it expects. `make test` runs it.

The ecosystem side is checked with `make -C ecosystem verify`, as above.

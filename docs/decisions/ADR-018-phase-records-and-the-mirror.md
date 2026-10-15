# ADR-018 — One phase record per phase, and what the mirror reads

**Status:** Accepted (owner-directed, 2026-10-06)
**Date:** 2026-10-06
**Related:** [ADR-015](ADR-015-development-tooling-is-external.md) (the tooling is external; amended here in
spirit), [ADR-017](ADR-017-charge-lifecycle.md), [`docs/phases/`](../phases/README.md)

## Context

The knowledge needed to work on one phase was spread across four documents: the specification (scope), the
roadmap (status and a narrative for completed phases), the phase guide (narrative and the cross-phase map),
and the ADRs (reasons) — plus the code and the tests, which held the parts nobody had written down. Three
problems came out of that:

1. **It was asymmetric.** Phases 0–5, being complete, had delivered-and-acceptance narratives. Phases 6–12
   had two sentences each. A phase you have not built is exactly the one you need to think about, and it had
   the least written down.
2. **The mirror carried almost nothing.** The tooling mirrors one Plane work item per phase: a one-line
   scope, a status word and a link to the Outline home. Everything else lived nowhere a person would look.
3. **Decisions had no home of their own.** A question like "what does ending a lease do to money?" had no
   place to be *asked*. It surfaced as a bug in testing, was answered in conversation, and would have been
   recorded — if at all — as an ADR that skipped the conversation that produced it.

## Decision

**One record per phase, in this checkout, at `docs/phases/phase-NN-<name>.md`, with a fixed set of sections.**
It cites the specification and the roadmap rather than replacing either; it adds the working knowledge
(paths, screens, tests, migrations), the decisions in force, the deliberate exclusions, the known defects
with reproduction steps, and the open questions.

**The record is the channel for questions.** Each one carries a stable id (`P4-Q1`), my recommendation, and a
cell for your answer. Records are the source of truth for what a phase *is*; the roadmap remains the source
of truth for its *status word*, and the contract test compares the two so they cannot drift.

**The record is also the Plane description** (added the same day, owner-directed). The tooling converts
`docs/phases/phase-NN-*.md` to the HTML Plane keeps and writes it as that phase's work item description, so
the item is readable without leaving Plane and the questions are visible where development is discussed. Two
things follow: Plane does not parse markdown, so a converter lives in the tooling
(`integrations/md-to-html.py`, standard library only); and a record edit now moves three things — the
Outline page, the Plane description and the checkout — so publishing is
`docs-sync --apply` → `plane-sync --apply` → `verify`, which is the exit criterion rather than a courtesy.

**Three tables are the contract with the mirror** — the roadmap's phase table, the register, and the records'
`## Open questions` tables. The roadmap and register are mirrored today, and the records are mirrored as
descriptions; reading an *answer* back out of Plane is the remaining piece, so nothing is written back for
the plan and only the answer to a question will travel inward.

**`docs/phase-guide.md` becomes the long-horizon view** — the cross-phase change map and the collected open
questions — rather than a second per-phase narrative. Two records per phase would drift; one will not.

**Extensions are filed under the phase they extend** (`P4-E1`), not in one flat sequence, so reading a phase
shows everything that changed it. The register keeps the flat ids (`E1`) until the mirror's parser accepts
the phase-scoped form, because a row it does not recognise is silently skipped while `verify` still counts
it — a mismatch that would show up as a count failure rather than a wrong page.

## Consequences

**Good.**

- A phase is one page: what it is, what exists, what governs it, what is missing, what waits on you.
- Phases 6–12 now carry their scope, their dependencies on what exists, and their real design questions,
  which is the cheapest possible time to answer them.
- Plane can carry substance rather than one line, and Outline gets a navigable set of pages instead of a
  flat list of thirty.
- Questions stop being conversational. An answered question is a decision with a home, and the
  implementation plan is written from the answer.
- A defect found in testing has a place to live that is not a chat log: **Known gaps and defects**, with the
  steps that reproduce it, scheduled like any other work.

**Costs, accepted.**

- Thirteen more documents to keep honest. Mitigated by the fixed section set, by a test that compares each
  record's status with the roadmap, and by the rule that a record never introduces a *rule* — rules are
  amended in the specification first, and decisions are ADRs.
- A record edit is now a publish, not just a commit: `docs-sync`, `plane-sync`, `verify`. That is three
  commands for a typo fix, and it is the price of the same text standing in two places without drifting.
- Something in the tooling now understands markdown (`integrations/md-to-html.py`). It covers only what the
  records use and fails safe — anything unrecognised comes through as text — but it is a small, real
  dependency on the shape of these documents, and the reason the section headings are fixed.
- Two changes are still needed before an **answer** travels: the register's id pattern (`P4-E1` is silently
  skipped today) and `verify` counting mirrored items rather than every item in the Plane project, so that a
  ticket you raise by hand is not read as drift. Reading answers back follows those.

## Alternatives considered

- **Put the working knowledge in Plane and let the records be thin.** Rejected: the plan's source of truth is
  the checkout, which is versioned with the code and reviewed in a diff. Plane is a working surface, not the
  record.
- **One record per milestone (six) instead of per phase.** Rejected: a milestone is a delivery grouping, and
  questions and defects belong to a phase's scope.
- **Extend `docs/phase-guide.md` rather than adding a tree.** Rejected: one 900-line document is what the
  problem already was — it cannot be one Outline page per phase, and a phase's questions cannot be mirrored
  from a table inside a section of it.

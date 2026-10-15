# ADR-015: Development tooling lives outside this repository

- **Status:** **Superseded by [ADR-019](ADR-019-ecosystem-in-the-workspace.md) (2026-10-06)** — the tooling
  now lives in the workspace at `ecosystem/`, ignored by git and excluded from images and lint. This record
  is kept because it explains why it was extracted, and that reasoning still holds for *what is in the
  repository*: the ecosystem is not part of the checkout's history. The 2026-10-06 amendment below (one-way
  for the plan, two-way for questions) was itself folded into ADR-018 and ADR-019.
- **Date:** 2026-10-03
- **Context:** Plane, Outline and Mailpit were stood up inside this repository, and the coupling cost more
  than it bought

## Context

RHP's development is tracked in Plane and documented in Outline, with Mailpit as the local mail sink for
both. They were first stood up under `infra/` **in this repository**, as three Compose projects beside the
application, and for a while that looked harmless: nothing in the application imported them, and they ran
in their own networks with their own ports.

What that arrangement actually created was coupling that has nothing to do with the product:

- **The application image.** RHP's `Dockerfile` ends in `COPY . .`. Keeping the tooling's generated
  secrets out of the `rhp-web` image depended on a single `.dockerignore` line, because the repository's
  existing `.env` patterns are anchored to the root and did not match an env file at depth.
- **The gate.** `make lint` runs `ruff check .` over the whole tree, so the tooling had to be policed — no
  Python there, plus an exclusion in `pyproject.toml` — to avoid changing the application's own result.
- **The branch workflow.** Phases are developed one at a time, each on its own branch, with uncommitted
  work in the tree. Tooling files in the same checkout meant a second workstream sharing one `HEAD`:
  switching branches deleted the tooling from the working tree, and a test existed solely to stop a
  `git add -A` sweeping generated secrets into a phase commit.
- **The deliverable.** RHP is a property-management and tenant portal. The tooling its developers use to
  plan and document it is not part of what it is, and a clone should not carry it.

None of that was a fault in Plane or Outline. It was the cost of keeping two unrelated things in one
repository.

## Decision

The tooling lives in **its own repository**, outside the RHP checkout, with its own history, secrets and
lifecycle. This repository contains the product and nothing else.

The two meet at exactly one point: `RHP_REPO`, a path the tooling is configured with, pointing at an RHP
checkout. The relationship is **read-only** — the tooling publishes this repository's tracked markdown to
Outline and mirrors the phase table in `docs/roadmap.md` and the register in `docs/extensions.md` into
Plane. Nothing is ever written back, and no RHP code, setting or Compose project refers to the tooling.

This repository therefore carries exactly two things about it: the short section in `AGENTS.md` pointing at
the tooling and its agent briefing, and this ADR.

## Amendment, 2026-10-06 — one-way for the plan, two-way for questions

Two things changed, and the separation itself did not.

**An agent in this checkout now drives the tooling.** The tooling repository was brought up to the same
standard as the per-project ecosystem seed (a `verify` command, idempotent syncs, no tooling pages in the
project's documentation), and the `project-ecosystem` skill was installed here at
`.agents/skills/project-ecosystem/`. `AGENTS.md` points at it. An agent runs
`make -C <tooling-path> {health,docs-sync,plane-sync,verify}` itself, publishes the documents it changed, and
reports `verify`'s verdict rather than asserting that the two sides agree. The earlier rule that an agent
must not touch the tooling repository was written when there was no skill and no `verify`; it now means
*do not edit the tooling's code*, not *do not use it*.

**Questions travel in the other direction.** Plane was a pure mirror: change the documents, re-run the sync,
never the reverse. That stays true of the **plan** — the phases and the register are edited in this checkout
and mirrored out, and nothing writes a phase's status back. But a phase record can carry **open questions
for the owner**, each with a stable id (`P4-Q1`), and those are mirrored to Plane as items so the owner can
answer them there. The answer is read back into the record, and the implementation plan for that phase or
extension is written from it. So: one-way for the plan, two-way for questions.

This does not weaken the first decision. Nothing about the product refers to the tooling; the checkout still
contains the portal, and the meeting point is still the documents and `RHP_REPO`. What it changes is who
turns the crank, and it makes the questions part of the plan instead of living in a conversation.

See [ADR-018](ADR-018-phase-records-and-the-mirror.md) for the document contract this creates.

## Consequences

**Good.** A clone of RHP is the product: no tickets, no wiki, no mail sink, no infrastructure secrets, and
no tooling directory to reason about in the Docker build context. RHP's gate, its branches and its
dependency set contain nothing that exists to *build* RHP rather than to run it. The tooling can be
versioned, backed up and eventually shared independently, and a phase branch can never collide with it.

**Costs, accepted.** The tooling is cloned and started separately, and `RHP_REPO` must point at a real
checkout — the sync scripts fail loudly rather than silently reading the wrong tree. Its secrets and
backups now live in a second place and need their own backup story. An agent working in RHP will not see
the tooling unless it reads the pointer in `AGENTS.md`, so its briefing is handed over deliberately rather
than stumbled upon.

**History.** The tooling was stood up inside this repository and lived there for three commits. It was
extracted before anything was pushed, so no published history was rewritten; those commits remain on the
local `rhpdev-infra` branch as the extraction source. This ADR keeps the number 015 because the in-flight
E2 extension branch claims 014.

## Related

- The tooling repository's `README.md` — the runbook, the first-run notes for both products, and the traps
  found in each.
- The tooling repository's `AGENT-BRIEFING.md` — what an agent working in this checkout must not disturb.

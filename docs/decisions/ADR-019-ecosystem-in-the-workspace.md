# ADR-019 — The development ecosystem lives in the workspace

- **Status:** Accepted (owner-directed, 2026-10-06)
- **Date:** 2026-10-06
- **Supersedes:** [ADR-015](ADR-015-development-tooling-is-external.md) (development tooling lives outside
  this repository). ADR-015 is kept: it is why the tooling was extracted, and it was right at the time.
- **Related:** [ADR-018](ADR-018-phase-records-and-the-mirror.md), `AGENTS.md`, `.agents/skills/project-ecosystem/`

## Context

ADR-015 moved Plane, Outline and Mailpit out of this repository into `~/Code/rhp-tools`, for good reasons:
the Dockerfile ends in `COPY . .`, so keeping generated secrets out of the image depended on one
`.dockerignore` line; `ruff check .` and `pytest` had to police a tree that is not the product; and a second
workstream sharing one `HEAD` meant switching branches disturbed the tooling.

What that decision did not account for is the **runtime** cost of a directory outside the working tree. An
agent working inside the RHP workspace could read the tooling, but every operation that writes — the sync
state after a publish, a description change in the sync, a backup, a one-line fix — needed an approval
escalation, because the sandbox is scoped to the workspace. The owner's words: *"It's not going to work when
you need 10+ permission checks at all times."*

So the constraint that matters is not *repository* membership, it is *workspace* membership. Those are
different things, and ADR-015 conflated them.

## Decision

The ecosystem lives at **`ecosystem/` inside this workspace**, and **outside this repository's history**:

- **Ignored by git** (`.gitignore` → `ecosystem/`). It keeps its own git repository and history inside,
  including the commits that describe it. A clone of RHP is still the portal and nothing else, and
  `git status` stays readable rather than listing a live database and thousands of vendored files.
- **Excluded from the Docker build context** (`.dockerignore` → `ecosystem`). This is the line ADR-015 was
  worried about, and it is now explicit rather than implied: the stack's `.env`, `secrets/` and Plane's
  database never enter an image.
- **Excluded from the lint and test tree** (`pyproject.toml` → ruff `exclude`). Its Python is checked by its
  own repository, not by RHP's gate. `pytest` already collects only `tests/`.
- **Exempt from the container-readability check** (`Makefile` → `check`, `perms`), like `.env`: the
  containers never read it, and `make perms` must never make the stack's generated secrets world-readable.
- **Driven by one verb**: `make -C ecosystem {health,docs-sync,plane-sync,verify,backup,mailbox,ps,logs}`,
  the same commands the `project-ecosystem` skill documents. The shared network and project names are
  explicit in the Compose files (`rhp-infra`, `rhp-outline`, `plane-app`), so moving the directory does not
  rename a project and does not orphan a volume.

The relationship with the checkout is unchanged: the ecosystem only ever *reads* it — the tracked markdown
published to Outline, and `docs/roadmap.md` + `docs/extensions.md` mirrored into Plane — and the checkout
stays the source of truth for the plan (ADR-018).

## Consequences

**Good.** An agent can publish, sync, back up and repair the ecosystem without leaving the workspace, which
is what made the tooling usable rather than merely present. The coupling ADR-015 objected to is contained by
four explicit exclude rules instead of by distance.

**Costs, accepted.** Four places must remember the directory exists (`.gitignore`, `.dockerignore`,
`pyproject.toml`, `Makefile`), and a new one would need the same treatment. A clone does not carry the
tooling, so a fresh machine must copy `ecosystem/` in by hand — the same as before the move, only now it
lands inside the workspace. And the tooling's own repository is now nested inside another working tree,
which is fine while it is ignored but means it must never be added to RHP's index.

## The move, for the record

Done on 2026-10-06 with the stack stopped cleanly (`make down`, never `down-hard`):

1. `make backup` first — Plane's database (3.3 MB), Outline's (960 KB), MinIO files, both `.env` files and
   the Mailpit mailbox, into `ecosystem/backups/`.
2. `mv ~/Code/rhp-tools ~/Code/RHP/ecosystem` — the same filesystem, so nothing was copied.
3. `make -C ecosystem up` from the new path, with the same project names, so the same volumes and the same
   bind-mounted Plane data were reused.
4. `make -C ecosystem verify`: **17 mirrored Plane work items, 43 Outline documents, both syncs
   idempotent** — and independently: Plane served its 17 items with each phase's record still embedded, and
   Mailpit still held its mailbox. One `verify` failure during the restart was Plane's API still booting;
   it passed a minute later, which is why the check is worth re-running rather than trusting the first
   answer.

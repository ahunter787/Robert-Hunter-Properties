# RHP — agent instructions

RHP is the self-hosted **property-management and tenant portal for Robert Hunter Properties**.
This file is the operating contract for any coding agent working in this repository.

- Full product specification (vision, non-goals, domain model, Phases 0–12, security rules):
  `docs/harness/master-spec.md`
- Phase plan and current status: `docs/roadmap.md`
- **One record per phase** — scope, what exists, the decisions, the gaps, and the questions waiting on the
  owner: `docs/phases/README.md`
- Architecture and structure: `docs/architecture.md`
- Additions that are **not** phases — the register of owner-approved extensions and recorded
  clarifications: `docs/extensions.md`

## How work happens

Work **one phase at a time**. Never start a later phase's features while a phase is open.

Before changing anything:

1. Inspect the repository.
2. Read `README.md`, `docs/roadmap.md`, the record for the phase you are touching
   (`docs/phases/README.md`), and the architecture sections your change touches. The record carries the
   questions still waiting on the owner — do not implement a recommendation that has not been answered.
3. State the phase you are implementing and the current state of the code in one short paragraph.
4. List the files and components you expect to change.

While implementing:

5. Implement only that phase's scope — no opportunistic features.
6. Add database migrations for every model change.
7. Add tests for the behavior you introduce; authorization and money first.
8. Run `make test`, `make lint`, and `make check` (and a smoke start when the change affects runtime).
9. Update the documentation your change makes stale.
10. **Do not commit unless explicitly instructed.**

When finished, report exactly: implemented, files changed, migrations, tests, known limitations.
Never claim a test passed without having run it, and never leave a known failure unstated.

## Development tooling (in the workspace, not in the repository)

Ticketing, versioning and documentation for RHP's development — Plane, Outline and a Mailpit mail sink —
run from **`ecosystem/` in this workspace**. It is a checkout of its own with its own git history,
generated secrets and a live database, and it is **ignored by git**, excluded from the Docker build
context and from `ruff`: a clone of RHP is still the portal and nothing else, and `git status` stays
readable ([ADR-019](docs/decisions/ADR-019-ecosystem-in-the-workspace.md), which supersedes
ADR-015).

```bash
make -C ecosystem health        # what answers, and which port belongs to whom
make -C ecosystem docs-sync     # dry run: what would change in Outline (ARGS=--apply to write)
make -C ecosystem plane-sync    # dry run: what would change in Plane (ARGS=--apply to write)
make -C ecosystem verify        # the exit criterion: the plan, the documents and the copies agree
make -C ecosystem mailbox | backup | ps | logs S=plane
```

The ecosystem only ever *reads* this checkout: the tracked markdown it publishes to Outline, and the phase
table in `docs/roadmap.md` and the register in `docs/extensions.md` that it mirrors into Plane. Nothing
about the product refers to it. The plan travels one way — change the documents, re-run the sync, never
edit the plan in Plane — while the **open questions and bugs raised in Plane** are where the owner works,
and the answers come back into the records (ADR-018).

Its containers must not be stopped, pruned or reconfigured, and its ports — `8080`, `8090`, `1025`,
`8025`, `8443`, `10025`, `10465`, `10587` — are not available to RHP. Never `docker system prune` or
`docker volume prune`: Plane's and Outline's datastores look unused whenever the stack is stopped.
`AGENT-BRIEFING.md` inside `ecosystem/` is the long version; ADR-019 records why it was brought back and
ADR-015 why it was extracted in the first place.

A skill for this is installed at `.agents/skills/project-ecosystem/`: it knows the commands and how to tell
that this checkout and the published copies agree. Agents that do not read skills should follow it by hand.

## Branches

`main` is always a working, released state. **Every phase gets its own branch**: `rhp-1` for Phase 1,
`rhp-2` for Phase 2, and so on.

1. Branch from an up-to-date `main`: `git checkout main && git pull && git checkout -b rhp-2`.
2. Commit per unit of work on that branch — never mix two phases in one branch.
3. Run the full gate (`make test`, `make lint`, `make check`, `make check-deploy`) and exercise the
   affected screens before merging.
4. **Squash the branch into `main`** so each phase is one commit there, then delete the branch:
   ```bash
   git checkout main && git pull
   git merge --squash rhp-2
   git commit                      # "Phase 2 — ..." with the phase summary
   git push origin main
   git branch -d rhp-2 && git push origin --delete rhp-2
   ```
   The granular commits stay visible on the branch while it is open (and on GitHub until it is
   deleted), which is where review happens. A pull request is the alternative when review is wanted
   before the merge.
5. Never rewrite `main`'s history (no force pushes), and do not commit or push unless asked.

## Non-negotiables

- **Money is `Decimal`**, never a float. Existing financial history is immutable: correct it with a
  reversal or adjustment entry, never by editing the original.
- **Authorization is enforced server-side** on every sensitive object. Never rely on hidden
  navigation, URL obscurity, hidden form fields, or client-side checks.
- **Tenant data is scoped to the tenancy**: query with the authorization scope
  (`Document.objects.get(pk=id, lease__tenants=request.user)`), not by bare primary key.
- **Uploaded documents and photos are never served by the web server or the reverse proxy.** They go
  through permission-checked views (Phase 6/7).
- **No secrets in the repository.** No credential ever gets a default in `config/settings/production.py`.
- **`django.contrib.auth` uses `accounts.User`** (`AUTH_USER_MODEL`). Do not add a second user model.
- Do not add Kubernetes, microservices, Kafka, Redis (unless a measured need proves it), a React SPA,
  GraphQL, or the explicitly excluded product features: listings, applications, screening,
  background/credit checks, insurance, lead generation, or marketplace features.
- Prefer boring, well-supported Django and standard-library solutions over new dependencies. Ask
  before adding a dependency that is not already in `pyproject.toml`.

## Layout

| Path | Purpose |
| --- | --- |
| `apps/<domain>/` | One Django app per domain, created in the phase that needs it |
| `config/settings/` | `base.py`, `development.py`, `production.py` |
| `templates/`, `assets/css/` | Django templates and the Tailwind entry point |
| `tests/` | pytest suite (runs against PostgreSQL) |
| `docs/` | Architecture, database, deployment, security, roadmap, ADRs, harness spec |
| `docker/` | Container entrypoint and healthcheck |

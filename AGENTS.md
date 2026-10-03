# RHP — agent instructions

RHP is the self-hosted **property-management and tenant portal for Robert Hunter Properties**.
This file is the operating contract for any coding agent working in this repository.

- Full product specification (vision, non-goals, domain model, Phases 0–12, security rules):
  `docs/harness/master-spec.md`
- Phase plan and current status: `docs/roadmap.md`
- Architecture and structure: `docs/architecture.md`
- Additions that are **not** phases — the register of owner-approved extensions and recorded
  clarifications: `docs/extensions.md`

## How work happens

Work **one phase at a time**. Never start a later phase's features while a phase is open.

Before changing anything:

1. Inspect the repository.
2. Read `README.md`, `docs/roadmap.md`, and the architecture sections your change touches.
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

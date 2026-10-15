# Phase 0 — Foundation and architecture

**Status:** Complete
**Milestone:** 1 — A deployed portal where RHP can create tenant accounts and tenants can sign in safely
**Specification:** `docs/harness/master-spec.md`, `PHASE 0 — FOUNDATION AND ARCHITECTURE`, and the
implementation notes in its closing section

## Scope as specified

A Django project that runs anywhere, deploys, and can be checked: split settings, PostgreSQL, Docker
Compose for development and production, a reverse proxy with TLS in production, a Makefile workflow, a
readiness probe, logging, linting and tests in CI, a design system, and the documentation set. The
specification is explicit that nothing else is built here — no domain app beyond what `AUTH_USER_MODEL`
requires.

## What exists today

- **Project:** Django 6.1, Python 3.14, PostgreSQL 17, `uv` for dependencies; `config/settings/` with
  `base.py`, `development.py`, `production.py` (fail-fast, no secret defaults).
- **Runtime:** `docker-compose.yml` plus an override for development, a `docker/` entrypoint that migrates
  then serves, Caddy for TLS and static files in production, and `/healthz`.
- **Workflow:** `Makefile` targets (`init`, `up`, `down`, `migrate`, `migrations`, `test`, `lint`,
  `format`, `check`, `check-deploy`, `health`, `perms`, `assets`, `psql`, `shell`, `superuser`, `up-prod`,
  `down-prod`, `prod-logs`), ruff at 100 columns, pytest with `filterwarnings = error`.
- **CI:** `.github/workflows/ci.yml` — lint and the suite against a PostgreSQL service; no secrets.
- **Design system:** Tailwind v4 built from `assets/css/` into `static/css/rhp.css`; `templates/base.html`
  and `templates/components/`; error pages `403.html`, `404.html`, `500.html`.
- **Documentation:** this record set, `architecture.md`, `database.md`, `deployment.md`, `security.md`,
  `roadmap.md`, `extensions.md`, the specification, and the ADRs.

## Decisions that govern it

| Record | What it settled |
| --- | --- |
| [ADR-001](../decisions/ADR-001-monolith.md) | One deployable Django monolith, not services |
| [ADR-002](../decisions/ADR-002-custom-user.md) | `accounts.User` is `AUTH_USER_MODEL` from the first migration; no second user model |
| [ADR-015](../decisions/ADR-015-development-tooling-is-external.md) | Development tooling (Plane, Outline, Mailpit) lives outside this checkout and only reads it |

## Extensions filed under this phase

None. Phase 0 is deliberately empty of product behaviour.

## Acceptance criteria and evidence

- [x] A clean clone launches from the documented instructions (`make init`) — proven by cloning the pushed
      repository into a fresh directory and running the first-run path: stack up, migrations applied,
      `/healthz` 200, landing page, static CSS, admin login, the suite green.
- [x] PostgreSQL persists across container restarts (named volume).
- [x] The application starts with no manual steps (the entrypoint migrates, then serves).
- [x] Tests run against PostgreSQL (`make test`).
- [x] No secrets in the repository (`.env` gitignored and dockerignored; CI holds none).
- [x] Development and production settings are separated and production fails fast on a missing secret.

`tests/test_settings.py`, `tests/test_health.py`, `tests/test_user_model.py` pin the production-settings
rules, the probe, and the user-model decision.

## Deliberately not here

Any property, lease, money or tenant feature; any app other than `apps/accounts`. Those are Phases 1–5.

## Known gaps and defects

- `tests/infra/` is an empty directory (a stale `__pycache__` inside) left behind when the development
  tooling moved out of this checkout (ADR-015). It is untracked, harmless, and not worth a cleanup commit
  on its own; it should go the next time that tree is touched.
- The container-readability rule (`make check` fails on a file only its owner can read) was only learned
  during E4, when a template written with a private umask raised `PermissionError` in the browser. It is
  enforced now; the docs describe it in `README.md`.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| *(none)* | Nothing is waiting on you for this phase. | — | — |

## How to verify it

```bash
make init                 # first run end to end, from an empty checkout
make test && make lint && make check && make check-deploy
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/healthz    # 200
```

# Phase 12 — Production hardening

**Status:** Not started
**Milestone:** 6 — Reporting, search, and production hardening
**Specification:** `docs/harness/master-spec.md`, `PHASE 12 — PRODUCTION HARDENING`

## Scope as specified

Everything that must be true before real tenants use RHP: HTTPS, production secret management, secure
cookies, database backups, media backups, off-machine backups, a restore procedure, audit logging, admin
MFA, brute-force mitigation, email configuration, monitoring, error reporting, application health checks,
dependency updates, file upload restrictions, log retention, a privacy review and disaster-recovery
documentation — plus a security test battery: tenant isolation, authorization bypass attempts, document
access, maintenance attachment access, id enumeration and session handling.

## What exists today

Nothing yet — this phase has not been built, though several of its foundations are already in place:

- **HTTPS and secrets:** `config/settings/production.py` fails fast on a missing secret and has no
  credential defaults; Caddy terminates TLS and serves static files; `docker-compose` has a production
  profile with gunicorn.
- **Health and CI:** `/healthz`, `make health`, `make check-deploy`, and GitHub Actions running lint and the
  suite against PostgreSQL.
- **Audit logging:** the `audit` app has recorded lease status changes, money movements and role changes in
  the same transaction as the change since Phase 4 — the phase decides retention and whether the append-only
  rules need database-level enforcement.
- **Upload restrictions:** type, size and dimension validation already exists for photos and the lease file
  (`apps/common/images.py`, `RHP_MAX_UPLOAD_MB`), and media is already refused by the proxy.
- **The permission model to be attacked:** mixins, `tenant_scope`, 403/404 discipline (ADR-003), and the
  route separation between `/manage/` and the tenant area.
- **Documented operating knowledge:** `docs/deployment.md`, `docs/security.md`, and
  [ADR-015](../decisions/ADR-015-development-tooling-is-external.md) for what runs outside this checkout.

## Decisions that govern it

No decision record exists for this phase yet. It needs several, and they are mostly yours: which monitoring
and error reporting you accept, where backups go, how MFA is delivered to staff, and how long logs and
personal data are kept.

## Extensions filed under this phase

None yet.

## Acceptance criteria and evidence

Not yet met — the phase is unbuilt. From the specification, plus what this record adds:

- [ ] A tested restore: the database **and** the media, restored into a clean environment and verified
      against the ledger, not merely "a backup ran"
- [ ] The security battery above is automated, so it runs on every change rather than once by hand
- [ ] Every secret lives outside the repository and outside the image; no production setting has a default
- [ ] Log retention and the audit trail's retention are decided and enforced, not accidental
- [ ] A privacy review of what RHP stores about a person, and why, with the answer in writing

## Deliberately not here

High availability, multi-region failover, and a staging environment maintained in parallel with production
(it would drift). One well-backed-up host with a tested restore is the target; RHP is a small portfolio, and
complexity here would be its own risk.

## Known gaps and defects

Nothing is broken in development. What is missing for production, beyond the list above: **no backup
automation or restore procedure of any kind yet**, no monitoring or error reporting, and
**admin MFA does not exist** — a staff account is protected by a password and the login throttle alone.
Note also that the development database holds real imported lease data; before production use, the privacy
review must cover what was imported and whether it should be carried over deliberately rather than by
migration.

## Open questions for the owner

| # | Question | My recommendation | Your answer |
| --- | --- | --- | --- |
| P12-Q1 | Where may backups go, and are you willing to accept an off-machine destination (a second disk, a NAS, or a hosted bucket)? | A hosted bucket with versioning, encrypted, plus a local copy. Off-machine matters more than which provider. | *(awaiting)* |
| P12-Q2 | Error reporting: a hosted service, or self-hosted? | Self-hosted if you want no third party seeing tenant data; otherwise a hosted service with personal data scrubbed before it leaves. Your call, and it is the one place I would accept an external dependency. | *(awaiting)* |
| P12-Q3 | Staff MFA: TOTP app, or email codes? | TOTP. Email codes are only as good as the mailbox, and invitations already use email. | *(awaiting)* |
| P12-Q4 | How long should logs, audit events and uploaded documents be kept? | Audit events and money records: indefinitely (they are the legal history). Application logs: 90 days. Documents: as long as the tenancy plus a defined tail. | *(awaiting)* |
| P12-Q5 | Should the audit trail be enforced in the database (append-only grants), or by convention? | Enforce what is cheap: revoke update and delete on the audit table for the application role, so the rule survives a bug. | *(awaiting)* |

## How to verify it

Not yet. When built: restore a backup into a clean environment and reconcile it, run the security battery in
CI, and confirm that a production start with a missing secret fails rather than defaults.

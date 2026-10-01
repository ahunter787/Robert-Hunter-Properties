# ADR-004: Invitation tokens and a database-backed login throttle

- **Status:** Accepted (Phase 1)
- **Date:** 2026-10-01
- **Context:** Phase 1 authentication and authorization

## Context

Two Phase 1 requirements have no built-in Django answer:

1. **Administrator-created tenant accounts with an invitation.** Staff creates the account; the
   tenant must choose their own password. Django ships password *reset* but no invitation flow, and
   RHP must never email or store a password a human chose.
2. **Login rate limiting.** The specification asks for a documented rate-limiting strategy and says
   Redis should not be introduced unless a measured need proves it. RHP runs gunicorn with several
   workers, so an in-process cache is per-worker and would let a distributed attacker (or simply
   round-robin scheduling) multiply the effective budget.

## Decision

### Invitations — a distinct token generator built on Django's

`InvitationTokenGenerator` subclasses `PasswordResetTokenGenerator` with:

- a **different `key_salt`**, so an invitation link can never be replayed as a password-reset link
  (or vice versa) — asserted by a test;
- **`is_active` mixed into the signed value**, so deactivating an invited account immediately
  invalidates its outstanding link;
- everything else inherited: the password hash and `last_login` are already part of the signature,
  which makes the link **single use** — it stops verifying the moment a password is set, and again
  once the invitee signs in.

Invitations and password resets therefore **share one expiry window**
(`settings.PASSWORD_RESET_TIMEOUT`, default 7 days). Django hardcodes that setting inside
`check_token`, and giving invitations their own, longer window would mean copying security-sensitive
verification logic; one window is the smaller risk.

### Throttling — a small database ledger

`LoginAttempt` records one row per attempt (lowercased username, client address, outcome, timestamp).
`LoginThrottle` counts failures in a rolling window for the **username or the address**; when the
budget is spent (`RHP_LOGIN_MAX_ATTEMPTS`, default 5 inside `RHP_LOGIN_WINDOW_MINUTES`, default 15)
the account/address is locked for `RHP_LOGIN_LOCKOUT_MINUTES` (default 15).

- The check runs **before** authentication, so a locked-out attacker never reaches the password
  hasher, and the message is generic (no account enumeration).
- A successful sign-in clears that account's failures; a throttled retry is **not** recorded as
  another failure (otherwise retrying would extend the lockout forever).
- Attempt rows older than 24 hours are pruned opportunistically as new ones are written; Phase 12
  adds a scheduled cleanup if volume ever justifies it.
- The client address comes from `REMOTE_ADDR` unless `RHP_TRUST_PROXY_HEADERS` is on, in which case
  the first `X-Forwarded-For` entry is used. The production Compose stack enables it because Caddy
  is the only thing in front of the app; production settings warn loudly if a TLS proxy is configured
  with the flag off (that combination would key every request to the proxy's address).
- `manage.py reset_login_attempts <username|ip>` is the support escape hatch.

## Consequences

**Positive**

- No new dependency, no Redis, and the limit holds across workers and restarts.
- Attempts are auditable in the database and visible in the Django admin (read-only).
- Invitation links inherit Django's hardened token primitives and are single-use by construction.

**Negative / accepted trade-offs**

- One extra database write per sign-in attempt, and one read per sign-in. Acceptable at RHP's scale;
  the indexes on `(username, created_at)` and `(ip, created_at)` keep the counting query cheap.
- A database outage fails the throttle open (sign-in cannot work anyway, because authentication also
  needs the database).
- One shared expiry window for invitations and resets rather than two tunables.
- `password__startswith="!"` is used to find never-accepted invitations, because Django exposes
  unusable passwords only as that prefix. It is asserted by tests and commented at the call site.

## Alternatives considered

- **Cache-based throttle (LocMemCache)**: per-worker, so effectively a 3× budget under gunicorn, and
  reset on deploy. Rejected.
- **`django-axes`**: capable, but a new dependency and its own migrations/backends for a problem this
  small; also added to the "ask before adding a dependency" list in AGENTS.md.
- **Proxy-level limiting only (Caddy)**: necessary in Phase 12, but it does not protect the
  application from credential stuffing through allowed paths, and a VM-based deployment may front
  the app with something else later.
- **Emailing a generated temporary password**: rejected outright — it puts a human-chosen secret in
  email, which is exactly what the invitation flow exists to avoid.

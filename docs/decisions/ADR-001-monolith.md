# ADR-001: Django + PostgreSQL monolith deployed with Docker Compose

- **Status:** Accepted (Phase 0)
- **Date:** 2026-09-30
- **Context:** Phase 0 foundation

## Context

RHP is a self-hosted property-management and tenant portal for a small, real property-management
business. It will hold tenant identities, lease documents, maintenance tickets, and financial
records. It has to run today on a local VM (possibly Proxmox) and move later to a small cloud VPS —
possibly operated by one person who is not a full-time systems administrator.

The reference product (Innago) is a multi-tenant SaaS. RHP needs a small subset of its tenant
experience and none of its marketplace machinery.

## Decision

Build RHP as a **single Django application with a single PostgreSQL database**, serving
server-rendered templates with HTMX for interactivity, packaged as one container image and deployed
with **Docker Compose** (Caddy reverse proxy + gunicorn + PostgreSQL).

- Django provides authentication, permissions, migrations, admin tooling, file handling, and form
  validation out of the box.
- One deployable artefact is identical on the development workstation, the local VM, and a cloud VPS;
  only environment variables and Caddy differ.
- PostgreSQL is used from day one (no SQLite stepping stone) so tests, constraints, and `Decimal`
  behavior match production exactly.
- Tailwind CSS is compiled at image-build time; there is no JavaScript application.

## Consequences

**Positive**

- One process to reason about, one database to back up, one image to ship. Failures have a single
  place to look.
- Deployments on a VM and a VPS differ only by `.env` and TLS — no "works locally, not in production".
- Django's admin gives the RHP team a working back office before custom screens exist.
- Adding a domain (leases, ledger, maintenance) is a new app, not a new service.

**Negative / accepted trade-offs**

- Server-rendered pages reload on navigation; HTMX covers the interactions that matter, but RHP will
  never feel like a single-page app.
- Vertical scaling only. Acceptable: the workload is tens of properties, not tens of thousands of
  concurrent users.
- A monolith requires discipline about module boundaries (app-per-domain, no cross-app imports of
  private helpers) rather than network boundaries enforcing them.

## Alternatives considered

- **React/Vue SPA + REST API**: doubles the surface area (two builds, token/CORS/session design,
  duplicated validation) for interactions a server-rendered portal does not need. Rejected.
- **Microservices / Kubernetes / Kafka / Redis**: no measured need at this scale; each adds an
  operational failure mode for a business with one application. Rejected, and recorded in the
  specification's non-goals.
- **SQLite now, PostgreSQL later**: would hide dialect and concurrency differences until the painful
  moment. Rejected.
- **A managed property-management SaaS**: rejected by the requirement to self-host and own the data.

# ADR-010: The tenant dashboard

- **Status:** Accepted (Phase 5)
- **Date:** 2026-10-02
- **Context:** Phase 5 — the primary tenant experience, and the first mobile-first screen in RHP

## Context

The specification asks Phase 5 for one page that immediately answers five questions — *how much do I
owe, when is it due, where is my lease, is my maintenance request being handled, has management sent me
anything* — with acceptance criteria about **phone width**, **information density**, and **critical
information without digging**.

Only three of those five are answerable today. Maintenance is Phase 7 and announcements are Phase 8, and
RHP's rule since Phase 2 has been to **label a gap rather than fake it** (a zero, or a button that goes
nowhere, is worse than a sentence saying when the thing arrives). That tension — a five-question page in a
three-question world — is the main decision this phase has to make.

Two smaller questions came with it: where the dashboard lives, and what a tenant's "payment history"
quick action actually opens.

## Decision

### It is the tenant's landing, at `/account/`

`/account/` was already the role-aware landing and the value of `LOGIN_REDIRECT_URL`, so a tenant who
signs in arrives at the dashboard with no new plumbing, and there is no second "home" to keep in step.
Staff hitting it are still **redirected** to `/manage/` rather than shown a 403 for a page they were
sent to. The account page proper stays at `/account/profile/`, one tap away from the user menu.

The view lives in `apps/accounts`, which already hosts the staff landing and documents why: it *is* the
cross-domain landing page, aggregating other apps' public models. Phase 9 revisits where dashboards live.

### Answer in the specification's order, and label what is not built

The page reads top to bottom: greeting, then the three figures, then the actions, then recent activity,
then the two panels that are not ready. Maintenance and announcements are one honest sentence each — no
"coming soon" button, because a button that does nothing teaches people to distrust the ones that work.

### Mobile-first is a set of constraints, not a feeling

- One column below `sm`, two at `sm`, three at `lg`; nothing is hidden at small widths.
- Primary actions are full-width buttons on a phone (`w-full sm:w-auto`) with the existing button padding
  for a comfortable target.
- **No tables in the tenant's path.** Money is rendered as stacked list rows with the amount
  right-aligned, because a four-column table on a 375 px screen is a horizontal scrollbar.
- No information available only on hover, and no fixed-width element that could push the page sideways.
- The specification's acceptance criterion is a real check on a real phone — the owner's — so the tests
  assert the structure (the responsive classes, the absence of tables) rather than pretending to measure
  pixels.

### The tenant's payment history is its own page, at `/payments/`

The specification's quick action needs somewhere to go, so Phase 5 adds the tenant-facing ledger in
`apps/ledger/urls_tenant.py` (namespace `payments`, mirroring how `apps/leases` owns `/lease/`). It
renders `apps.ledger.services.build_ledger` — **the same derivation the office reads**, so the tenant and
the desk cannot be shown different numbers — with no id anywhere in the URL, and voided entries hidden
because they are office bookkeeping rather than the tenant's business.

A pending payment is labelled *expected* rather than *received*, in the activity list and on this page:
money that has not arrived must not read as money that has.

### The greeting reads a display timezone

`TIME_ZONE` is UTC, so a greeting computed from it would wish an Oregon tenant good evening at lunch.
`RHP_DISPLAY_TIME_ZONE` (default `America/Los_Angeles`) exists for this one purpose; `apps.common.dates.greeting()`
takes an already-converted moment. Business dates remain plain dates and are untouched by it.

### One lookup decides whose tenancy a tenant sees

`visible_lease_for` moved from a view function onto `LeaseQuerySet.visible_for`, so the lease page, the
dashboard and the payment history resolve "the tenant's lease" through one implementation — including its
draft-exclusion rule (ADR-007 revision). A tenant can only ever be shown a lease they are on, and a draft
remains invisible until it is activated.

### No schema change

Phase 5 adds no model, no migration and no dependency. Every figure on the dashboard and the payment
history is derived from Phases 3 and 4.

## Consequences

**Positive**

- A tenant's two most common questions — *what do I owe* and *when is it due* — are answered on the page
  they land on after signing in, with no navigation and no digging.
- The tenant portal now has a real shape (Dashboard, Lease, Payments), which Phases 6–8 extend rather
  than replace.
- One derivation of the balance serves both audiences, so the tenant's page cannot disagree with the desk.
- Mobile-first constraints are written down, so later phases have something to conform to rather than a
  preference to rediscover.

**Negative / accepted trade-offs**

- Two of the five questions are answered with a sentence rather than a screen. Accepted deliberately: the
  alternative is building fragments of Phase 7 and 8 out of order.
- The dashboard renders in a single request with no caching; at this scale that is a few small queries per
  visit, and the ledger's per-lease derivation is the same work the office screens already do.
- A display timezone is a second timezone in a system that deliberately keeps one. It is confined to a
  greeting and documented as presentation only.
- "Works well on a phone" is signed off by a person, not by a test. The automated checks keep the
  structure honest; the acceptance is the owner's, as with every phase.

## Alternatives considered

- **A new `/dashboard/` URL**: cleaner separation from "account", and it would mean either two landing
  routes or a redirect chain from the post-login target. Rejected for a page that is, in practice, simply
  where a tenant starts.
- **Making `/lease/` the dashboard**: fewer pages, and the lease detail (terms, document, co-tenants) is
  not what a tenant checks most often. Rejected — the two pages answer different questions, and the
  specification's own quick action is "View Lease" *from* the dashboard.
- **Placeholder cards with zeros for maintenance and announcements**: looks complete and lies about the
  state of the product. Rejected, consistently with Phase 2.
- **A disabled "Maintenance Request" button**: a control that cannot act is worse than a sentence.
  Rejected.
- **Rendering the tenant's money in a table like the desk's**: consistent with the staff screens and
  unusable on a phone, which is where tenants actually are. Rejected.
- **Computing the greeting in the browser**: needs JavaScript, and RHP is server-rendered first.
- **Storing a "last seen" or dashboard cache**: a second source of truth for no benefit at this size.

## Revision: no personality, and a statement instead of an activity feed

**Date:** 2026-10-02, while Phase 5 was open, after the owner read the dashboard on a phone.

The first version greeted the tenant by their time of day and led with an eyebrow reading "Your home".
On a real phone that read as the application performing familiarity it had not earned, and it pushed the
only facts on the screen — which unit, which building — below the fold. Two changes followed.

### The greeting goes

`apps.common.dates.greeting()` and `RHP_DISPLAY_TIME_ZONE` are **removed**, not hidden: the setting had
exactly one consumer, and leaving it behind would invite the greeting back. RHP does not greet, thank, or
otherwise address the reader; "in credit — thank you" became "in credit" for the same reason.

The header is now a **thin banner carrying the facts**: the unit identifier as the page's heading, the
property beside it. That is enough for a tenant to confirm they are looking at their own tenancy, and it
costs one line instead of a third of the screen. The tenant's own name stays in the navigation, where the
user menu belongs.

*Recorded because it will be proposed again*: a greeting is a cheap way to make a page feel finished, and
this decision says no to it deliberately. The portal's warmth is in its clarity, not its voice.

### The activity feed became a statement

The dashboard's "recent activity" showed the office's entries — a charge and, beside it, the adjustment
that corrected it, as `+$2,084.00` and `−$2,084.00`. A tenant reading that experiences earning and losing
money rather than a bill being corrected. The reading, not the record, was wrong: see
[ADR-011](ADR-011-tenant-statement.md), which replaces that list on every tenant-facing page with a
statement where an adjustment is absorbed into the charge it corrects.

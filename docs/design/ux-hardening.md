# E18 — Portal UX hardening

**Status:** Built in development — owner review pending. The E18-0 baseline, E18-A shell/navigation,
E18-B messenger, E18-C dashboard/onboarding and E18-D accessibility/browser QA are implemented on
`rhp-e18-ux`. Nothing has been merged into `main`.
**Baseline:** [ux-baseline.md](ux-baseline.md), tag `ux-baseline-2026-10-22`.
**Before/after captures:** [baseline](artifacts/ux-baseline-2026-10-22/README.md) and
[E18 review](artifacts/ux-e18-review/).

## What changed

### E18-A — shell and navigation

The staff sidebar is grouped by the job being done instead of listing every model in one stack:
Dashboard; Portfolio; People; Leasing; Money; Work; Communications; Workspace. Stable URLs and
authorization are unchanged. Messages has an authorized unread badge computed through the existing
communications read projection. Tenants receive a compact bottom navigation at phone width
(Home, Pay, Messages, Repairs, More) with the full grouped sidebar still available through More.
The sidebar utility block is now one profile link: the account photo (or the same neutral stand-in used
elsewhere) sits above the name and role, the whole block opens Profile & account, the separate
"Profile & account" text link is gone, and Site administration/Sign out remain separate utilities. This
was verified for both a manager and a superadmin (`rhpadmin`). Account photos are now stored on the
account (`User.photo`), so the same image appears in the sidebar and account pages. Every account can
upload/replace its own photo from Profile & account; admins can set any account's photo from Contact &
photo; managers and tenants cannot change another account's photo. The browser tab uses the RHP mark as
SVG favicon with PNG fallbacks and an Apple touch icon.

### E18-B — messenger

- Two-pane desktop inbox/thread; the conversation page keeps the visible inbox rail and highlights the
  selected conversation. Mobile shows one pane with a back link.
- Dense conversation rows: initials, participant, subject, latest-message snippet, relative time,
  unread count, work state and unit context.
- Chat shell: day separators, author-grouped bubbles, own/other alignment, attachment links, compact
  header/actions, persistent details drawer for staff media, internal notes and history.
- Composer: pinned, auto-growing, Enter sends, Shift+Enter adds a line, multiple attachments, quick
  replies and inline errors. Sending is progressively enhanced: the normal POST remains the fallback,
  while JavaScript sends the same form asynchronously and reconciles the server's returned message batch.
  The existing send token remains the idempotency key.
- Polling is every 4 seconds while the thread is visible, never overlapping, and pauses when hidden.
  New messages append without replacing the composer; a new-message control appears when the reader is
  scrolled away. Automatic read receipts use the existing signed read route. The manual button remains
  available when JavaScript is unavailable.
- No typing indicator, read receipt or presence was added; ADR-024's exclusions stand.

### E18-C — action-first dashboard

- The application content is capped at **2500px** and centered inside the workspace, so an ultra-wide
  monitor stops stretching the page and the information columns do not drift apart. List/table pages
  (Properties, People) use a tighter **2000px** content cap so their columns stay readable instead of
  either stretching indefinitely or collapsing into a narrow column. Asset query versions were bumped so
  an already-open browser does not keep the pre-E18 stylesheet.
- Manager metric cards are now uniform boxes at every group depth, with a 4-column maximum at wide
  widths instead of a mix of boxed and unboxed rows.
- Manager dashboard now leads with a small "Needs attention today" rail (past due, missing insurance,
  conversations needing a reply, unread messages, draft leases, open maintenance) before the metric
  groups. Each item links to the existing, authorized record view.
- Tenant dashboard leads with "Things to do" (insurance proof, unread messages, payment due, lease ending)
  before the card stack.
- A compact owner "Set up RHP" checklist appears until property, unit, tenant and lease setup are present;
  it derives completion from existing records and gives one next action per step.
- Shared empty/attention/list primitives and small-screen bottom navigation are available for the
  remaining list/dashboard slices.

### E18-C visual pass — People, Timelines and Renters insurance

A ChatGPT 6.1 Sol design pass restyled the three staff list screens to the Tenants pattern: full-width
list page inside the 2000px cap, simple page heading, bordered search/explainer card, white table card
with caption and row/column scopes, initials/identity, semantic status pills, explicit Open/Review
actions, useful empty states and horizontal table scrolling on small screens. People keeps its
server-side search and exposes its existing pagination; Timelines and Insurance have no real filter
context, so they explain the population instead of showing fake controls. No view, query,
authorization, service, model, migration, shared CSS or dependency changed.

The companion [site-wide visual consistency review](chatgpt-ux-consistency-review.md) records the
remaining priorities: one inline-link treatment, preserving messaging filter state, consolidating page
headers/width rules, unifying form field/error primitives, and a mobile 44–48px control-size baseline.

### E18-C accounting workspace

The accounting overview now follows the standard accounting-dashboard shape instead of a row of ten
equal buttons: a section tab strip, four KPI cards (journals, active accounts, unposted source events and
AR-control state), a trial-balance table with scoped headers and a total row, an AR-control card with a
clear tied/needs-attention state, and a short accounting-tasks list. The underlying journals, controls,
queries and routes are unchanged; the page still derives every figure from the ledger.

The browser tab now carries the RHP mark: an SVG favicon with a 32px PNG and a 180px Apple touch icon,
all using the same forest-green rounded square and serif R as the portal mark, plus a theme colour. The
standalone 500 page carries the same icon.

## What this did not change

No money arithmetic, ledger service, authorization rule, tenancy scope, document access, message
immutability, insurance scope or database schema. No new dependency. No realtime service, external chat
SDK, native app, SMS, AI, listings, applications, screening, e-sign or marketplace feature.

## Verification and limitations

- The full Django suite passes after the E18-A/B/C/D changes: **1,348 passed, 5 opt-in browser suites
  skipped**. E18-specific tests cover grouped navigation, unread badges, chat shell, AJAX send/fallback,
  tenant/staff scope, next steps, attention ordering and the no-JavaScript read/composer fallback.
- Visual review used disposable synthetic data at 1440px and 390px; no real tenant data is in the
  committed captures.
- E18-D: the thread has a labelled live log, focus stays in the composer after send, the composer has
  visible keyboard hints, and the app honours `prefers-reduced-motion`. A headless Chrome review
  confirmed: AJAX send adds one message, clears the composer and reports “Sent.” with no console
  exceptions; the 390px layout has no horizontal overflow, hides the rail, shows the back control and
  opens the sidebar from the bottom-nav More button; a real Enter-key send clears the composer and returns
  focus to it; and with JavaScript disabled the manual read control is visible and the normal composer form
  remains. The Chrome accessibility tree exposes the conversation as a “Conversation messages” log, the
  composer as a “Message” textbox, and the Send/Attach controls by name. The final owner review remains.
- The baseline tag remains available for rollback; no schema migration is required for the current E18
  slices.

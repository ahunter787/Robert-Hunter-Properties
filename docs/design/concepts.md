# Three interface concepts

**Status:** B — Operations desk + persistent sidebar selected for iterative planning October 18, 2026.
No concept is the new production shell; finer design decisions and implementation approval remain open.
Every book presents staff maintenance queue, request detail, tenant maintenance and lease ledger,
each at desktop and phone proportions. Fixtures and dollar figures are identical across concepts.

## A — Portfolio workspace

Persistent left portfolio navigation, page-context tabs and a wide working area. Tenant pages use
a shorter shell. A familiar, low-risk structural evolution of RHP's existing interface.

- Strength: clear location within the portfolio and space for financial tables.
- Tradeoff: sidebar occupies desktop width; phone needs an explicit Menu disclosure.
- Effort: medium; shared shell and contextual navigation change, workflows largely remain.

## B — Operations desk

A tenant-centered staff workspace for moving between work, people and property context without
repeatedly starting over. Persistent, compact domain navigation anchors the app; the selected domain
provides an overview, a scannable list and focused record detail. A retained property/unit list or
maintenance queue sits beside detail when comparing or processing several records is useful. This
is an operations pattern, not a requirement to divide every page into two columns or pack every
screen with controls.

### What the Innago references show

The four owner-added screenshots in [Screenshots and annotated observations](http://10.60.0.227:8090/doc/screenshots-and-annotated-observations-5LeE4MBxKQ)
are **closest to B, with A's persistent sidebar**. These are overlapping design patterns, not
exclusive product categories:

- **Dashboard:** collection, occupancy and open-maintenance summaries organize operational work,
  with direct actions such as Record payment. This supports B's task-first overview, though summary
  cards alone do not distinguish it from A.
- **Properties list:** aligned rows bring rent, lease condition, occupancy and open work together;
  a secondary summary/quick-filter area supports scanning before opening a record.
- **Unit detail:** the property/unit navigator remains beside the selected unit's lease, tenant,
  collection and maintenance context. This retained list/detail relationship is the strongest
  evidence for B rather than simply A's sidebar plus independent detail pages.
- **Lease conditions:** labeled color indicators make conditions scannable. RHP should pair color
  with readable status and dates, and provide essential explanations without hover. The screenshot
  is evidence of the treatment, not proof of its accessibility or print behavior.

The owner's note interprets Innago as tenant-focused and prioritizes Dashboard, Properties (with
Units beneath), Tenants, then Leases. The screenshots support prominent tenant context within a
staff workspace; they do not establish the vendor's research findings or a tested navigation order.
Here, **tenant-centered** means staff can identify the tenancy and its situation quickly, not that
tenants receive the same dense management shell.

### RHP adaptation, still proposed

- Keep portfolio navigation stable. Evaluate Dashboard, Properties with nested Units, Tenants and
  Leases as the primary record hierarchy, alongside clearly reachable Maintenance, Rent & Payments,
  Expense recoveries and Documents. Do not hide daily tasks just to imitate the reference's order.
- Make the staff dashboard an actionable overview: work needing attention, overdue accounts and
  useful next actions, rather than a wall of equal-weight statistics.
- Carry property, unit, tenant and lease identity into detail. Keep conversation primary on repairs;
  status milestones, internal notes and administrative history retain their separate hierarchy.
- Retain queue filters, selected item and scroll position when returning from detail. Provide a
  stable detail URL, visible selection and sensible keyboard focus. Normal links and plain forms
  remain usable without JavaScript; a split pane is a progressive enhancement, not an SPA mandate.
- Use full available width for the ledger, keeping due now, upcoming and account balance distinct,
  plus existing labeled status colors and inline financial corrections. Do not force it into a
  narrow maintenance-style detail pane.
- On phones, show list then detail with a clear Back to results action and retained context, not
  squeezed columns. Tenant maintenance stays simple: active requests, one submission action and
  expandable history; no staff queue, financial evidence or portfolio navigation.
- Print the selected record with identity and meaningful status labels, omitting navigation and
  queue controls. Preserve grayscale meaning. Leave structural room for future RHP accounting,
  but add no accounting, messaging, listings or screening features or placeholder destinations.

- Strength: supports repeated staff triage and cross-record work with fewer context switches;
  keeps tenant information close to the operational decision.
- Tradeoff: nested context can consume width and create competing summaries. Split panes should
  earn their space; compact must not mean small text, tiny targets or endless dashboard cards.
- Effort: high for the full queue/detail behavior; a sidebar and ordinary linked lists alone are
  closer to A and medium effort. Selection URLs, focus, Back and plain-form behavior need testing.

The current B wireframes illustrate the maintenance queue/detail version of this pattern. They
have not been redrawn to reproduce Innago's dashboard or property workspace; this description
clarifies the wider direction without implying those screens already exist or are approved.

## C — Calm portal

Short grouped top navigation and a local section menu, generous spacing and progressively disclosed
details. The tenant shell is intentionally simpler than the staff shell.

- Strength: easy reading, low visual pressure, clear major actions.
- Tradeoff: longer staff pages; frequent operators may want denser queues.
- Effort: medium; disclosure and grouped navigation must retain clear page identity.

## Comparison

| Criterion | Portfolio workspace | Operations desk | Calm portal |
| --- | --- | --- | --- |
| Staff navigation | Persistent portfolio sidebar + context tabs | Stable domains + retained list/detail context where useful | Grouped domains + local section menu |
| Density | Balanced | Scannable staff summaries; focused detail | Spacious |
| Phone | Menu + one working column | Queue-to-detail with explicit Back | Short nav + disclosed sections |
| Ledger | Full-width table within workspace | Ledger uses full detail area, not maintenance split | Wide table; summaries above |
| Print | Suppress menus; retain identity and labels | Print selected request, not queue chrome | Expand essential content, omit controls |
| Accessibility work | Menu focus and current-page semantics | Above plus split-view focus/selection | Disclosure state and focus |
| Expected effort | Medium | High | Medium |

Across all three: maintenance attention may use soft yellow plus a status label; internal notes use
a text label and dashed rule; ledger overdue/paid/pending colors also have wording; corrections
stay inline. The grayscale books verify that hierarchy does not depend on hue.

The owner selected **Operations desk + persistent sidebar** as the planning baseline on October 18,
superseding the initial low-risk recommendation of Portfolio workspace. The supplied Innago references
inform navigation and information hierarchy beyond maintenance, not a carbon-copy interface. The
[working plan](navigation.md) narrows the remaining choices step by step; see [decisions](decisions.md).

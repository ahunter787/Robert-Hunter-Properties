---
name: rhp-live-ui
description: Apply and preserve RHP's live-screen layout primitives when changing management or tenant pages — disclosures, page-wide column tracks, action bars and button hierarchy. Use for implementation and visual review of the running Django portal, not for Outline/Plane diagrams or printable exports.
---

# RHP live UI patterns

This skill keeps the live website coherent. It is a checklist, not an automatic fix: the CSS primitives
and the tests are what enforce the result.

## Scope

Use this skill for RHP screens served by `templates/`, `assets/css/input.css` and the live Django app. Do
not apply it to diagrams, documentation wireframes or printable form exports; use
`rhp-design-diagrams` for those.

Read `docs/design/principles.md` and `docs/design/layout-primitives.md` before changing a screen. Prefer
an existing primitive over a page-specific flex/grid rule.

## Rules

### Local expansion

- Expand/collapse that changes only the current page is a native `<details>`/`<summary>` disclosure.
- Do not use an anchor with a fragment, a server round-trip or a full page reload for transient state.
- Render the content once; set the server's initial `open` state; let the browser toggle it.
- The control must keep the reader's scroll position.

### Comparable columns

- Three comparable values use `.workspace-row-grid`, not `display:flex; justify-content:space-between`.
- The owning workspace sets `--workspace-row-columns` once; separate cards on the same page share it.
- Do not use `max-content` for a middle or trailing track when two cards must align; use a fixed track or
  a shared token.
- Collapse to one column at the agreed mobile/tablet breakpoint and verify no horizontal page overflow.
- Actual tables use `.rhp-table`; a parent-owned grid may use `subgrid`.

### Peer actions

- Put peer actions in `.rhp-action-bar`.
- Use one variant (normally `.rhp-btn-secondary` for peers) and keep a single `.rhp-btn-primary` only
  where there is a clear next action.
- Never mix a `.rhp-btn` with a plain `.rhp-link` in the same action row.
- Keep the bar transparent. Reset form margins; keep button heights equal.
- Secondary hover stays neutral in the action bar, with a visible focus ring.

### Existing routes

- Do not convert a page-navigation menu into in-page tabs as a drive-by change. Accounting's tab strip
  remains a separate, later design task.

## Workflow

1. Inspect the current markup and the existing primitives; do not add a new class for a one-off.
2. Change the smallest owning CSS/template scope.
3. Add or update a rendered-HTML test for the primitive usage.
4. Run the full gates.
5. Inspect the real page at 1440px and 390px; for column/action changes, measure positions rather than
   trusting the template classes alone. Capture before/after screenshots under
   `docs/design/artifacts/ux-e18-review/`.
6. If a new pattern is genuinely needed, add it to the primitives and document it; never leave the next
   page to rediscover the same fix.

# Layout primitives: disclosures, rows and actions

These are the small, reusable rules that keep an RHP screen from moving under the reader, making a
row's values look randomly indented, or mixing two visual languages in one action group. They are
deterministic CSS and semantic HTML — not an AI layout engine and not per-page pixel fixes.

## 1. Local expansion is a disclosure, not navigation

An expand/collapse control changes only what is already on the page. It must not reload, change the URL,
or jump to a fragment. Use a native `<details>`/`<summary>` pair:

```html
<details class="navigator-units-details" {% if open %}open{% endif %}>
  <summary class="navigator-toggle">
    <span class="navigator-toggle-open">▸ Expand</span>
    <span class="navigator-toggle-close">▾ Collapse</span>
    Property name units
  </summary>
  <div class="navigator-units">…</div>
</details>
```

Rules:

- render both the closed and open content once in the document; let `open` decide what is visible;
- do not put `#property-<id>` on a toggle link — the browser will scroll that anchor;
- do not use a server round-trip for transient disclosure state;
- if a future control must remember state across navigation, update the URL with
  `history.replaceState` or persist it deliberately, not through an anchor hash;
- style the summary as a button-like row; remove the native marker consistently.

The property navigator now follows this. The old link round-tripped to a new URL ending
`#property-<pk>`, so the browser jumped to the property. The replacement expands downward in place and
keeps the scroll position unchanged.

## 2. Tabular rows get page-wide column tracks

`display: flex; justify-content: space-between` distributes **leftover** space between children. The
middle child's x position therefore changes with the width of the first and last children. That is why
the rent/status column looked randomly indented.

Use a grid with the same tracks on every row. The property workspace owns one shared token so separate
cards on the same page line up with each other:

```css
.properties-workspace {
  --workspace-row-columns: minmax(0, 1.25fr) minmax(0, .75fr) 12rem;
}
.workspace-row.workspace-row-grid {
  display: grid;
  grid-template-columns: var(--workspace-row-columns);
  gap: 20px;
  align-items: center;
}
.workspace-row-grid > :last-child { justify-self: end; text-align: right; }
```

Rules:

- use `.workspace-row-grid` for three-column informational rows;
- use a **fixed last track** (or a shared token), not `max-content`, when different cards need the middle
  column to start at the same place;
- set the token on the page/workspace that owns the comparison, not inline on each row;
- use `.rhp-table` for actual tables; use `.portfolio-grid`/`subgrid` where a shared parent owns the
  tracks;
- do not use free-space flex distribution for columns that readers compare down a page;
- below 1000px collapse the tracks to one column and let the row read top-to-bottom;
- keep the column structure in CSS, not in per-template inline styles.

## 3. Peer actions use one action bar

Actions that sit together and do the same kind of work must use the same primitive and the same button
variant. Do not put a button beside a plain inline link in one row.

```html
<div class="rhp-action-bar">
  <a class="rhp-btn rhp-btn-secondary" href="…">Lease workspace</a>
  <a class="rhp-btn rhp-btn-secondary" href="…">Lease ledger</a>
</div>
```

Rules:

- use `.rhp-action-bar` for a group of peer actions inside a card or section;
- use `.rhp-btn-primary` for one clear primary action per context and `.rhp-btn-secondary` for the
  others; do not mix `.rhp-btn` with `.rhp-link` in the same bar;
- reset form margins with `.rhp-action-bar > form { display:flex; margin:0; }`;
- keep the bar transparent; the card, not the action bar, is the surface;
- secondary hover in the bar is a neutral tint (`#f7faf8`), not a large green fill; preserve the
  visible focus ring and border.

The lease-ledger Actions card and account tenancy card both use this primitive. The prior tenancy card
mixed a secondary button with a plain link, and the ledger's group read like an unintended green panel
on hover.

## 4. Verification

- A rendered-HTML test asserts the disclosure markup exists and no `#property-` anchor is emitted
  (`tests/properties/test_operations_desk.py`).
- A rendered-HTML test asserts the tenancy card and ledger Actions card use `.rhp-action-bar` with
  matching button variants.
- Browser QA clicks a closed disclosure after scrolling, then asserts scroll position is unchanged.
- Browser QA measures the second and third column x-positions in the Occupants and Units cards; they
  must match within 1px.
- Browser QA checks the 390px layout has no horizontal page overflow.
- Screenshots: `docs/design/artifacts/ux-e18-review/properties-navigator-expanded.png`,
  `properties-column-alignment.png`, `tenancy-actions.png`, `ledger-actions.png`.

The point is a **shared primitive**: future list rows use the same grid instead of solving alignment
again, future disclosure controls use the same native pattern instead of inventing another anchor, and
peer actions use the same bar instead of a button/link mixture.

Accounting's top tab strip still navigates to separate pages. Converting it to in-page section
switching is a separate, later change; this document only defines the row, disclosure and action
primitives it will use.

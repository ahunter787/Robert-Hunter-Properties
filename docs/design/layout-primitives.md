# Layout primitives: disclosures and aligned rows

These are the small, reusable rules that keep an RHP screen from moving under the reader or making a
row's values look randomly indented. They are deterministic CSS and semantic HTML — not an AI layout
engine and not per-page pixel fixes.

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

## 2. Tabular rows get explicit column tracks

`display: flex; justify-content: space-between` distributes **leftover** space between children. The
middle child's x position therefore changes with the width of the first and last children. That is why
the rent/status column looked randomly indented.

Use a grid with the same tracks on every row:

```css
.workspace-row.workspace-row-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(140px, .8fr) max-content;
  gap: 20px;
  align-items: center;
}
.workspace-row-grid > :last-child { justify-self: end; text-align: right; }
```

Rules:

- use `.workspace-row-grid` for three-column informational rows;
- use `.rhp-table` for actual tables; use `.portfolio-grid`/`subgrid` where a shared parent owns the
  tracks;
- do not use free-space flex distribution for columns that readers compare down a page;
- at phone width collapse the tracks to one column and let the row read top-to-bottom;
- keep the column structure in CSS, not in per-template inline styles.

## 3. Verification

- A rendered-HTML test asserts the disclosure markup exists and no `#property-` anchor is emitted
  (`tests/properties/test_operations_desk.py`).
- Browser QA clicks a closed disclosure after scrolling, then asserts scroll position is unchanged.
- Screenshot: `docs/design/artifacts/ux-e18-review/properties-navigator-expanded.png`.

The point is a **shared primitive**: future list rows use the same grid instead of solving alignment
again, and future disclosure controls use the same native pattern instead of inventing another anchor.

---
name: rhp-design-diagrams
description: Create or revise diagrams, documentation wireframes and comparison sheets for RHP Outline/Plane records with editable sources and print-friendly exports. Also applies to printable tenant/manager form exports, never the live website's design language.
---

# RHP design diagrams

## Scope boundary

Apply this skill only to diagrams and supporting visual artifacts created for Outline/Plane
documentation, and to the print layout of exported forms a tenant or manager may use. It is not
a website design-system skill. Do not apply its monochrome defaults, ink-saving rules, paper sizes
or restrained decoration to live pages, interactive forms, CSS, branding or screen-oriented mockups
intended to decide the website's visual language. The website will take full advantage of color;
screen design is governed by usability, accessibility and owner-selected product direction, not
print efficiency. Documentation wireframes illustrate structure, not a required site palette.
When a task includes both an interface and an export, limit this skill to the export/documentation
portion; preserve the full-color screen design and original reference screenshots.

Read `docs/design/principles.md` and the relevant study record before authoring. Keep authored
documentation sources under `docs/design/`; examples are synthetic, never actual tenant or financial
data. Actual form-export implementation remains in its appropriate application component.

Choose the smallest useful visual. Default to white, black text and restrained gray structure.
Avoid decorative icons, gradients, shadows, elaborate connectors and unnecessary boxes.
Use color only for deliberate semantic meaning, paired with a label or non-color cue. A soft
yellow maintenance treatment is appropriate when illustrating that proposed product treatment;
it is not a rule to tint every maintenance diagram. State whether a treatment is proposed or approved.

Keep reading order obvious, labels short, type legible, and diagrams unclipped on US Letter.
Use landscape when needed. Preserve original screenshots; annotate copies. Never label a
wireframe as a screenshot or imply a concept already exists in the application.

## Rendering

`scripts/render.py` renders a JSON scene book to vector SVG pages and a Letter PDF. Each page
has a title, subtitle and elements (`text`, `rect`, `line`) in top-left-origin point coordinates.
Supply `width`/`height` for portrait or landscape Letter. Text elements support `size`, `bold`,
`fill`; rectangles support `stroke`, `fill`; lines support `stroke`, `dash`. Use at least 9pt
for annotations and larger body type. All elements must remain inside a 30pt page margin.

Run with the bundled document Python runtime (reportlab), not RHP's application environment:

```
<bundled-python> .agents/skills/rhp-design-diagrams/scripts/render.py <book.json> <output-stem>
pdftoppm -scale-to 1600 -png <output-stem>.pdf <output-stem>
```

The renderer also creates grayscale SVG pages and a grayscale PDF. Render those with Poppler
for review. Visually inspect every page for overlap, truncation, contrast and meaningful
grayscale status cues; successful rendering alone is not acceptance. Retain sources, vector
exports, PNG previews and print PDFs. Avoid embedding private local paths in published links.

## Publication

Use the project-ecosystem skill for Outline/Plane. Publish only the Design manifest into the
Design collection; do not repoint the engineering publisher or change ecosystem configuration.
Keep source markers, stable document IDs, captions, source URLs and proposal/approval status.
Re-publishing must update documents rather than duplicate them. Verify uploaded assets load
and downloadable files match their source. Missing upload authorization is a reported blocker,
not permission to broaden an API key or make files public.

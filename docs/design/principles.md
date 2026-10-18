# Design principles and visual language

## Approved constraints

RHP is a working tool for a small family property business and its residential and commercial
tenants. Staff need operational context; tenants need a few clear answers, not a portfolio console.
Retain ADR-021's language: tenant, Rent & Payments, Expense recoveries, due now versus account
balance, direct action names, American English and dates such as Oct 17, 2026.

## Documentation and printable exports only

The diagram skill's print-efficiency constraints apply to diagrams and comparison sheets made for
Outline/Plane documentation, not the website's design language. Study wireframes communicate
structure; their monochrome appearance is not a proposed production palette. Printable/exported
forms intended for tenants or managers may use the same print-friendly treatment; that treatment
does not constrain the interactive form or surrounding website.

Default these documentation artifacts to white, black text and light gray structure. Color is a
signal, never a substitute for a label. Avoid gradients, decorative graphics and ink-heavy backgrounds
in these print-oriented artifacts; preserve original screenshots rather than recoloring them.
Use soft yellow for a maintenance attention treatment when that meaning is intentional; label it
with status or a follow-up message. This is a proposed component treatment, not a blanket yellow
background for every maintenance screen. Urgency must not be inferred from yellow alone.

Print on US Letter with at least 30pt margins. At actual print size, annotations are at least 9pt,
body copy 11pt, and page headings 18pt. Keep vector sources, PNG previews and printable PDFs.
Diagrams must survive grayscale printing without losing category or status meaning.

## Proposed product tokens, pending theme selection

The live website will take full advantage of color. It is not subject to ink-efficiency, monochrome
or US Letter constraints. Brand colors, colored surfaces and visual hierarchy should be evaluated
for screen use, usability and accessibility. The tokens below are initial proposals, not limits
imposed by the documentation skill; a fuller color system remains open for owner review. Color must
not be the only way to communicate a status or action, for accessibility rather than print economy.

| Token | Treatment | Meaning |
| --- | --- | --- |
| Canvas | White / warm near-white | Reading surface |
| Text | Charcoal, secondary gray with sufficient contrast | Primary and supporting information |
| Structure | Fine gray rules; whitespace before containers | Group related tasks without card clutter |
| Primary action | Existing forest-green with text label | One routine next action per context |
| Maintenance attention | Soft yellow `#fff3cd`, dark label | Work or follow-up needing attention |
| Past due / error | Dark red plus explicit wording | Overdue money or an action that failed |
| Paid / completed | Dark green plus explicit wording | Completed or cleared state |
| Pending / internal | Neutral label; internal also uses a dashed border | Pending money or staff-only material |

These proposals preserve existing financial status colors and inline corrections. A blue or
green brand alternative must not recolor paid, pending or overdue states into ambiguous meanings.

## Reusable components

- Navigation: portfolio menu, page-level tabs and separate account controls. Tenant navigation is
  short; mobile uses a labeled Menu rather than an unlabeled icon or horizontal overflow.
- Page header: identity, state and one primary action. Do not repeat the request title in every card.
- Forms: visible labels, inline checkbox labels, errors next to fields, clear consequences before save.
- Tables: aligned numeric columns, sticky headers only where useful, text status labels, mobile rows
  retaining labels. A financial table is not replaced with decorative summary cards.
- Timeline: public conversation first, short status milestones, explicit staff-only notes, revisions
  and delivery details disclosed on demand. Group display events without rewriting stored history.
- Empty states: explain the current state and give one appropriate next action. No placeholder features.
- Feedback: state the completed action and object; avoid transient toast-only confirmations.
- Accessibility: semantic landmarks, visible focus, meaningful names, 44px target preference on phones,
  and text contrast checked at implementation. Static wireframes are not proof of WCAG conformance.

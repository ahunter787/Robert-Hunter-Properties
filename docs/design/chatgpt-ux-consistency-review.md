# RHP — E18 visual consistency review

## Scope and outcome

Source-based review of the shared shell and representative staff/tenant surfaces; not a browser audit or accessibility certification. The focused implementation changes only [People](<../../templates/management/people_list.html>), [Timelines](<../../templates/timeline/staff_list.html>) and [Insurance](<../../templates/insurance/staff_list.html>). Recommendations below are follow-up work, not additional changes in this pass.

The reference is [Tenants](<../../templates/management/account_list.html>): simple heading, bordered search card, white table card, readable identity, semantic status and explicit Open action. The three updated lists use the existing 2000px `.list-page-width`, table spacing and header typography, `.rhp-avatar`, `.rhp-status` and `.rhp-empty`. Tables retain every column in a keyboard-focusable horizontal scroll region on small screens. Initials are decorative; full names remain visible. Lease numbers distinguish repeat tenancies.

People retains its existing server-side search and now exposes the view's existing pagination, preserving the search between pages. Portal state follows the Tenants precedence: deactivated, active with a usable password, otherwise invitation pending; no linked account is separate. Timelines and Insurance have no search/filter context in their existing views. Their matching bordered cards explain the current population instead of presenting fake controls. Both include upcoming, active and ended leases, excluding drafts. Insurance says explicitly that submitted proof needs manager review, uses Review only for submitted proof, and never equates an empty queue with accepted coverage.

No view, query, authorization, service, model, migration, shared CSS or dependency changes. Tenancy names are evaluated once per row and reused for initials, identity and accessible action names.

## Top five priorities

1. **P1 — Make inline links consistently recognizable.** [The stylesheet](<../../assets/css/input.css>) has contextual `.rhp-link` rules but no base definition. [Dashboard record links](<../../templates/dashboard/detail.html>) and [messenger toolbar/attachment links](<../../templates/communications/conversation.html>) can therefore depend on inherited styling, while workspace links are explicitly green and underlined. Define one reusable inline-link treatment: primary color, persistent underline, hover and visible keyboard focus. Keep whole-row navigation and buttons distinct.
2. **P1 — Preserve messaging filter context.** [The inbox](<../../templates/communications/index.html>) replaces query parameters when choosing All/Unread/Archived; its search/status form omits active archive/unread modes. Searching can unexpectedly leave the chosen population. Generate merged querystrings, preserve mode in the form, reset only pagination, and add an explicit Clear filters action. Expose active chips programmatically, not only through `.active`.
3. **P2 — Consolidate page headers and width rules.** [Properties](<../../templates/management/property_list.html>) and [Dashboard](<../../templates/dashboard/home.html>) use `.workspace-page-heading`; [communications](<../../templates/communications/base.html>) and Tenants use utility headings, alongside a third `.rhp-page-header` scale in [CSS](<../../assets/css/input.css>). Tenants and [Documents](<../../templates/management/document_list.html>) still lack the 2000px list cap. Standardize top-level title/subtitle/action spacing and list caps without widening task forms or flattening compact chat subheadings.
4. **P2 — Unify form fields and validation.** [Shared fields](<../../templates/components/field.html>) put errors below controls and use required stars; [maintenance fields](<../../templates/maintenance/fields.html>) put errors above and use “(required)”. Maintenance inputs also use a different text size/border treatment in [CSS](<../../assets/css/input.css>). Share field/error primitives and one required-field policy, retaining inline checkboxes and correct help/error associations. Check non-field errors and invalid POST states, not only pristine forms.
5. **P2 — Establish a mobile control-size baseline.** [CSS](<../../assets/css/input.css>) gives tenant bottom navigation 48px minimum targets but chat Attach is 38px square, quick replies use 11px text and small padding, and mobile Back gets minimal padding. Give messaging controls and list actions comfortable 44–48px targets while retaining compact icons. Verify with the software keyboard, zoom and long content; do not solve space pressure by hiding important information.

## Surface observations and follow-ups

### Navigation and shell

[The base shell](<../../templates/base.html>) already provides a viewport declaration, skip link and focusable main landmark. [The sidebar](<../../templates/components/sidebar.html>) uses job-based groups, current-page semantics and unread badges. The forest-green shell, white cards and neutral canvas are a strong RHP foundation. Preserve role-aware navigation and permission-checked routes. Clarify People (lease contacts) versus Tenants (portal accounts) through consistent subtitles, not another navigation layer. Apply priority 3 to content inside this stable shell.

### List pages

The three updated pages now share identity hierarchy, explicit actions, captions, column/row scopes and useful empty states. [Documents](<../../templates/management/document_list.html>) already follows much of the reference and preserves pagination filters; [Properties](<../../templates/management/property_list.html>) appropriately uses location rows, but its filters are unboxed. Standardize spacing, filter containers and empty-state recovery across list families without forcing location navigation into a person table. Tenants still uses inline rounded status utilities while these lists use shared pills: consolidate semantics and shape in a later shared pass. Introduce actual Timeline/Insurance filters only as separately approved behavior work.

### Detail pages

[Property records](<../../templates/management/properties_workspace.html>) have location headers and local tabs; [lease records](<../../templates/management/lease_workspace.html>) use a section rail. Keep those useful domain-specific patterns. [Person detail](<../../templates/management/person_detail.html>) remains a narrow card stack, and its portal-state text (“active” versus “invited / inactive”) does not distinguish the same states as Tenants and the new People list. [Insurance detail](<../../templates/insurance/staff_detail.html>) still shows mostly plain status text rather than the list pills. Reuse state vocabulary/pills and consistent return paths. Keep [timeline reading](<../../templates/timeline/lease.html>) comfortably narrow rather than applying list width indiscriminately.

### Dashboards

[The manager dashboard](<../../templates/dashboard/home.html>) already leads with attention/setup sections and limits metrics to four columns. Retain that task-first hierarchy and financial caveats. Its eyebrow metric labels, larger section headings and separate workspace header should align with the shared type scale. [Metric drill-downs](<../../templates/dashboard/detail.html>) use plain statuses and table headers without explicit scopes; bring their table semantics, actions and status presentation up to the list standard. Preserve financial color meanings rather than tinting whole rows.

### Forms

[Person forms](<../../templates/management/person_form.html>) correctly stay narrow and use shared controls with explicit Save/Cancel actions. Apply priority 4 across maintenance and ordinary forms, including required guidance, error order and non-field alerts. Preserve normal server-rendered submission and validation; a visual component is not authorization.

### Mobile

[Existing CSS](<../../assets/css/input.css>) stacks workspace facts/location rows, reserves tenant bottom-nav space and accounts for safe-area insets. The updated tables deliberately scroll instead of hiding contact, term or compliance columns; the People search field can shrink without a fixed minimum width. Follow up with 390px and 320px checks, 200% zoom, keyboard-only scrolling, long names/emails and large result sets. Check that only the table scrolls, not the entire page. No rendered mobile verification was performed in this pass.

### Messaging

[The conversation](<../../templates/communications/conversation.html>) already separates internal notes from shared messages, has a labelled live log, delivery/update status hooks and a normal POST fallback. [The inbox](<../../templates/communications/index.html>) is intentionally denser than directory tables; retain that distinction. Fix filter continuity (priority 2), inline-link affordance (priority 1) and small control targets (priority 5). Verify the fixed-height thread and details panel with a mobile keyboard before increasing density further.

## Verification and boundaries

Re-read all three edited templates. All three compiled with Django; 15 isolated render scenarios passed, covering empty/search states, People pagination and portal states, tenancy states, insurance states/actions, escaped names, captions/header scopes and once-per-row tenancy-name evaluation. These checks used a minimal base template and stub URL configuration, not the running application or database; they do not exercise authorization or prove browser layout. No test assertions were changed. Existing timeline/insurance tests primarily assert responses, authorization and workflows; those contracts should remain unchanged. The operations-desk navigation-order assertion is unrelated and should not need adjustment. The People list-only access assertion likewise remains valid. Exact copy/markup snapshots, if added elsewhere, may require intentional updates.

The full test suite was deliberately not run. No runtime/browser, generated stylesheet build, deployment, git commands, commits or pushes are part of this review. Rebuild CSS through the existing asset pipeline and visually verify the three screens before treating this as rendered sign-off.

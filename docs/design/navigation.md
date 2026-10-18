# Navigation maps and maintenance workflow

## Operations desk + persistent sidebar — working plan

**Direction selected for planning:** October 18, 2026. **Register:** E11.
The owner selected B's operational information strategy with a persistent sidebar, strongly informed
by the supplied Innago references but not a reproduction of its screens. This is the first planning
iteration, not permission to implement a production redesign. An isolated prototype is authorized.
Exact menus, density, colors, contextual
panes and tenant treatment remain reviewable. Existing diagram/PDF books predate this selection;
they are comparison artifacts, not an updated implementation blueprint.

### 1. Problem and design intent

The current shared header presents Management, Maintenance, Properties, Units, Leases, Documents,
Rent & Payments, Tenants and account controls at the same navigation level. Expense recoveries is
reached elsewhere. Property/unit pages emphasize banners, maps and physical details ahead of tenant
and operational context; tenant account detail emphasizes account administration. Staff must connect
people, places, leases and work by moving between independent pages. The workflows can be useful
without the overall information tree being strong enough.

Adopt the reference's useful structure: stable domains, property-to-unit drill-down, visible tenant/
lease context, scannable operational signals and retained list/detail context where it helps repeated
work. Keep RHP terminology and capabilities, including commercial leases, NNN, expense recoveries,
manual payments, corrections, private documents and maintenance. Do not copy Innago branding,
screens verbatim, social features, listings or screening. Reference observations are documented in
[the concepts](concepts.md) and the owner's unchanged [screenshots and notes](screenshots.md).

### 2. Navigation has three distinct jobs

1. **Global destination:** a persistent, labeled staff sidebar answers “Which part of RHP am I in?”
   Keep its order stable; active state, role and account controls are unambiguous.
2. **Object context:** a compact identity/header and local sections answer “Which property, unit,
   tenant, lease or request am I working on?” Use breadcrumbs for ancestry and cross-links for
   relationships; do not turn every section into another expanding global navigation tree.
3. **Work selection:** a scoped list/queue may remain beside the record when moving between nearby
   records is useful. It is not mandatory on forms, financial tables or every detail page. Avoid
   three competing narrow sidebars. On phones, show results then detail, not squeezed columns.

### 3. First staff sidebar proposal — not yet approved

| Primary destination | Local destinations / relationships | Existing capability to retain |
| --- | --- | --- |
| Dashboard | Prioritized attention and links to source records | Current maintenance, occupancy, lease and money summaries; not new Phase 9 analytics |
| Properties | All properties; All units; selected property and its units | Portfolio-wide unit access remains available, but Units need not compete as a separate primary domain |
| Tenants | Tenant list; selected person's contact/account and linked tenancies | Invitations, activation, profile and photo permissions; person is not the financial account |
| Leases | Lease list; overview; rent schedule; related documents; account link | Draft/active/ended occupancy, separate account state, prior activity and lease setup |
| Rent & Payments | Lease-account overview; selected lease ledger | Existing ledger, payments, corrections, settlement and financial reopening |
| Expense recoveries | Recovery agreements; bills/billing periods; allocation review | Existing guided calculator and charge-posting workflow; placement is an explicit owner question |
| Maintenance | Queue; selected request; vendors where authorized | Existing work, conversations, entry permission, costs and reviewed recharge actions |
| Documents | Portfolio document library; scoped document links from records | Existing categories, visibility and permission-checked downloads |

Account/profile and Sign out belong in a separate utility area. Authorized site administration is
separate from daily operational actions; managers do not acquire admin duties through navigation.
The proposed order is a starting point, not a claim about Innago's optimal ordering for RHP.

**Future fit, not placeholder UI:** Phase 8 will add communications/messages and announcements once
built; its capability scope is E12, not part of this redesign. Accounting, reports and online payments
retain their own phase/extension boundaries. Do not add disabled menu items or empty destinations.
Expense recoveries and maintenance repair costs must not be labeled as if full property accounting
already exists. Allow later additions without overloading a single “More” menu or renaming today's
Rent & Payments prematurely.

### 4. Information hierarchy by workspace

| Workspace | What comes first | Supporting detail / retained behavior |
| --- | --- | --- |
| Dashboard | Work needing attention, overdue accounts, leases needing review; clear next actions | Compact totals that link to existing scoped lists; use existing definitions, not decorative charts |
| Property | Property identity, occupancy, units and current tenant/lease context | Maintenance, related documents and recoveries; building facts, large photos and map move lower or into Details, not removed |
| Unit | Property/unit identity, occupancy, current tenants and lease; relevant work | Physical details/amenities secondary; show vacant/out-of-service explicitly; do not add the unapproved E7 tenancy-history feature |
| Tenant | Person/contact identity and links to the correct current tenancy or tenancies | Account invitation/status and existing administrative controls remain accessible; never combine different leases' money under a person without clear separation |
| Lease | Property/unit, tenants, dates, occupancy and financial-account state | Schedule, NNN, documents, prior activity and operational actions retain their existing semantics; ledger links to the exact lease |
| Lease ledger | Due now, past due, upcoming and account balance/credit; routine actions; transactions | Wide ledger, running balance, inline corrections and labeled financial colors; correction/admin history secondary, never erased |
| Maintenance | Queue urgency/age and selected request's location, tenant audience, status and entry permission | Tenant conversation first; compact milestones; unmistakable internal notes; costs, recharges and delivery evidence secondary and scoped |
| Expense recoveries | Property, expense, bill period, monthly allocation and review state | Keep the approved bill → allocate → review/save steps; improve surrounding context without redesigning the calculation model |
| Documents | Readable title, category, linked tenancy/property, visibility and document date | Existing upload/download/removal rules; no filename-based navigation or accidental publication of staff-only records |

These are presentation projections over existing records, not replacement models or stored totals.
Contextual sections only appear when their data and authorized workflow exist. New relational summary
queries may be needed, but they must not introduce accounting, worker access or lifecycle changes.

### 5. Preserve domain guarantees, redesign interactions

- Inventory existing capabilities, not menus to retain. All menus and task sequences may be redesigned;
  preserve calculations, relationships, authorization and financial safety guarantees.
- Keep meaningful labels, confirmation consequences, validation and safe primary actions. Group
  routine actions, corrections and restricted administration distinctly rather than moving everything
  into an unlabeled ellipsis menu. Existing non-JavaScript forms remain valid.
- Retain stable route paths, especially `/manage/ledger/` and `/payments/`, and existing deep links.
  Reorganizing a sidebar does not require renaming the URL tree. Use canonical record links.
- Preserve list filters, sort, page and selection on return where practical; expose active scope and
  a way to clear it. A cross-link must not silently carry an incompatible property filter or a
  hidden global property selection into an unrelated workflow. Any return URL must be validated.
- Opening a tenant's account, lease or ledger changes context explicitly. Property scope is a
  navigation aid, never a new authorization boundary; managers remain portfolio-wide.

### 6. Role, screen and visual boundaries

Managers/admins use the operational shell, with restricted controls still server-authorized.
Maintenance workers have only assigned-work navigation and necessary context. Tenants receive a
short own-tenancy shell; borrowing structure does not give them the staff console. Preserve their
simple maintenance count/cards/history and readable statement. Tenant-specific navigation details
are reviewed separately, not inferred from the staff sidebar decision.

The live interface is full-color and screen-first. Brand palette, surfaces, type, spacing, row
density and semantic colors need separate review in realistic screen examples. The printer-friendly
diagram skill does not constrain the website. Preserve financial color coding plus text, accessible
contrast and visible focus. D-Q3 approves low light yellow, normal yellow, high/urgent red and
completed green, with labels and separate unresolved-follow-up emphasis.
On narrow screens, a labeled Menu and a single working area replace permanent desktop columns.
Keyboard navigation, meaningful headings/current-page state, zoom and unsaved-form protection are
acceptance criteria, not reasons to make every screen dense or colorless.

### 7. Narrow the direction in reviewable rounds

| Round | Deliverable | Owner decision before the next round |
| --- | --- | --- |
| 1 — Navigation and task map | Inventory current capabilities and trace common journeys | Prototype sidebar, Units nesting and Expense recoveries main access accepted; no menu-preservation requirement |
| 2 — Record hierarchy | Property → unit → tenant/lease → ledger and maintenance list/detail reading order | Which information stays visible; where a retained list helps versus a full-width detail page |
| 3 — Screen language | Full-color, screen-oriented examples of the same representative staff/tenant tasks | Palette, density, tabs/sections, action grouping and mobile treatment; not monochrome document wireframes |
| 4 — Interaction prototype | Isolated full-color prototype with synthetic public captures and optional private local snapshot | Review new task sequences and navigation; preserve domain guarantees, not old workflows |
| 5 — Implementation plan | Component/file map, bounded work units, regression matrix and rollout acceptance | Explicit implementation authorization and sequencing after Phase 7 review; no later-phase feature work |

Candidate future implementation components: `templates/base.html`, `templates/components/nav.html`,
shared staff/tenant shells, page headers/local navigation and list/detail components, `assets/css/input.css`,
domain templates and narrowly scoped view projections/query optimization. Tests cover rendered role
navigation, deep links, selected/filter state, money and tenancy isolation. No new application dependency
or data migration is expected from navigation alone; revisit that assumption before any model change.
The isolated [prototype](prototype.md) now implements reviewable examples under its own tools folder.
Production components and behavior have not changed.

### 8. Representative journeys and acceptance

- Find a property, select a unit, identify its current tenants, open the correct lease/ledger and
  return to the same unit/list without losing location or exposing another tenancy's history.
- Find a tenant, distinguish multiple linked tenancies if present, reach the right account and
  record a payment through the existing service and confirmation.
- Select a maintenance request, read the right tenancy conversation, distinguish internal notes,
  inspect permitted cost evidence and return to the same queue/filter. Worker/tenant isolation holds.
- Enter a recovery bill, use the existing calculator/review, return to its property context; saving
  allocations still does not imply posting charges.
- Reach a document from the library and from a related record, with identical visibility checks.
- Repeat key paths at phone width, keyboard-only, zoomed and without JavaScript. Active context and
  Back behavior remain clear, forms do not lose input, and menus do not cover essential actions.
- Every current action has an identified destination; no capability disappears because it is absent
  from the reference product. No fake future capabilities, changed monetary results or weaker scopes.

The next review should settle the navigation tree first, not attempt to approve the whole redesign.
See [D-Q4–D-Q6 and remaining decisions](decisions.md).

## Role-aware structure

### Revised Properties interaction

All properties, property overview and unit detail share one photo-led property/unit navigator.
The middle column uses the owner-supplied composite screenshot's richer property blocks.
Property photo/name headers select the overview; separate disclosure controls expand/collapse units.
Several properties may remain open, independently of selection. URL state plus the temporary session
retain manual expansion; unit links carry the originating filter/return destination.
Selecting a unit changes the workspace's main content, not its navigation structure.
Overview, Details, Maintenance, Expense recoveries and Documents are local selections, not redirects
to global domains. Scoped sections show only the selected location's records; portfolio escape links
are explicit. On phones the tree is a labeled disclosure above a single content area.
All units remains a filtered portfolio list within this same workspace. Existing deep links remain.
All properties and All units are reached through the primary left sidebar; do not duplicate them
above the contextual navigator. Record-level Back-to-results and Back-to-queue controls are removed.
Navigation tiers and record cross-links remain; browser history and form-review Back/Cancel are intact.
Photos identify places/people; unit allocation colors and operational status colors retain separate
meanings. Missing photos use labeled type icons or initials, never an unexplained empty frame.

Staff: portfolio navigation identifies the domain; page tabs identify the current object's
context; account controls stay separate. Managers see portfolio operations, workers only assigned
maintenance. A hidden menu is not authorization: all existing server-side scopes remain.

Tenants: Home, Lease, Payments, Documents, Maintenance, Account. Do not show staff navigation or
future features. Former tenants retain their own history without a submission action when no
current tenancy exists. If multiple tenancies are visible, label the unit before each request.

The navigation book shows existing capabilities only. Future accounting may use the domain/menu
pattern later, but is not a disabled item or empty destination now.

## Maintenance reading order

1. Identity, location, status and entry permission.
2. Next action and latest meaningful update.
3. Tenant conversation and compact work milestones.
4. Explicit staff-only notes, with revisions available.
5. Manager-only costs, recharges and email evidence on secondary sections.

Completed or closed work with an unresolved follow-up remains in the active/attention group until
reviewed, using the existing unresolved queue rule. History excludes those flagged requests.
“0 active requests” remains a calm empty state with a submission action for an eligible tenant.

The workflow diagram deliberately separates a request, assignment, expense and reviewed recharge.
There is no arrow that automatically turns a request into tenant liability.

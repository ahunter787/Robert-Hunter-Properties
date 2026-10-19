# Design decisions and owner feedback

## Confirmed

- October 18, 2026: final E11 pass approved. Staff maintenance uses separate tenancy conversations,
  not an all-audience feed. Internal notes are a separate section, costs/delivery/history remain
  manager-only, and existing status/permission records provide compact milestones. Person records
  prioritize current tenancies and contacts; account administration remains secondary. No new contact
  editing, onboarding calculator, financial service, migration or dependency is authorized.

- October 18, 2026: Properties application slice accepted; continue E11 migration. Correct portrait
  URL reuse, aligned property columns, taller banners and lease second-tier navigation. Retain
  administrator-only deletion of empty mistaken/test property records, with crimson presentation
  and an exact typed confirmation. Taking a property out of service remains the normal removal
  path; linked units, leases and financial history stay protected. Prepare, but do not implement,
  the separate [prior-activity calculator proposal](prior-activity-calculator.md).
- October 18, 2026: owner accepted the revised prototype and authorized E11 application migration,
  locally merging the outstanding baseline without pushing. The approved plan covers the existing
  portal and one optional unit photo. Properties is the first implementation/review checkpoint;
  subsequent redesign work remains uncommitted until separately authorized.
- Correct property/unit selection and entry-permission wording before broader design work.
- Entry permission covers RHP staff and assigned repair professionals for the request.
- Managers recording offline authorization provide a private source note.
- Tenant maintenance has active requests and expandable history, not a large filtered search page.
- Separate navigation levels and reduce timeline clutter without erasing financial or work history.
- Create an Outline Design collection, a project diagram skill, editable sources and print exports.
- Use predominantly black-and-white documentation diagrams and comparison sheets, with intentional
  meaningful color and grayscale cues. This is not a website palette requirement.
- Owner clarification: the live website should take full advantage of color and is not designed for
  print efficiency. The diagram skill applies to Outline/Plane documentation artifacts; its
  print-friendly treatment may also guide exported tenant/manager forms, not their interactive UI.
- Produce three concepts; do not deploy a new theme before selection.
- October 18, 2026: use **B — Operations desk + a persistent sidebar** as the planning baseline.
  Strongly borrow the supplied Innago navigation/information strategies, not its branding or screens.
  Preserve RHP data, calculations, relationships and security, not existing menus or task sequences.
  An isolated interactive prototype is authorized; production rollout is not.

## Owner review questions

| ID | Decision | Recommendation | Owner answer |
| --- | --- | --- | --- |
| D-Q1 | Which structural concept should become the planning baseline? | Earlier recommendation was Portfolio workspace | B — Operations desk + persistent sidebar, selected October 18, 2026 for iterative planning; not blanket implementation approval |
| D-Q2 | Balanced maintenance rows or compact split view? | Balanced rows initially | Accepted; verbatim answer below |
| D-Q3 | Semantic maintenance attention colors? | Color plus labels | Accepted: low light yellow, normal yellow, high/urgent red, resolved green; original below |
| D-Q4 | Expense recoveries in main sidebar? | Direct access plus property links | Accepted; future accounting is separate; original below |
| D-Q5 | All units beneath Properties? | Yes, retain portfolio access | Accepted; original below |
| D-Q6 | Must existing menus/forms survive? | Preserve domain rules, not UI structure | No; design and workflow are fully redoable; original below |

## Original owner answers from Outline

Read October 18, 2026. Preserved verbatim; the table above records the implementation interpretation.

**D-Q2:** Recommended

**D-Q3:** Yes. Similar to the attention coloring innago uses in the screenshot about tenancy about to expire. I suppose a maintenance ticket could have a high priority on it, and be red. or a medium priority and be yellow, and a low priority on it and be light yellow. Resolved Green.

**D-Q4:** Expense Recoveries are part of the Property, but its a fast-access item, so lets have it be in the main sidebar. Just like Properties have dashboard that can drop down to Units, this will be similar to have properties drop down to expenses, property taxes, etc. It might end up being the “expenses” page.

**D-Q5:** Recommended.

**D-Q6:** I don't think we should keep any existing menus specifically. The redesign should be allowed to fully capture a new feel. For example, the expense recoveries we've made is very good, and the relationships of our data should work exactly the same, but the Innago style uses a Circular percentage ring with color coding. That would be a great way to display the electricity bill allocation. If the 910 Stark Property had 2 units, color code each unit (ie Blue + Pink), then fill the ring with blue and pink relative to the percentage allocated.For me, the information, the calculations, the data relationships are critical, But the design and workflow is completely re-doable

## Prototype authorization

Historical study authorization follows. The October 18 application-migration approval recorded
above supersedes its no-rollout boundary; the original prototype review remains preserved.

### Revision approved October 18, 2026

- Properties opens one workspace: a photo-led property/unit navigator remains beside either the
  portfolio summary, property overview or selected unit. A property header selects its overview.
- The owner's later “Austin Notes Continued” supersedes the single-expanded-property proposal:
  expansion is independent/manual and retained across selection. No duplicate Property overview
  link beneath each property; the property header itself selects that overview.
- Latest owner refinement: All properties and All units stay in the main left sidebar only, not
  above the middle navigator. Record pages have no Back-to-results/queue buttons; navigation tiers
  provide those destinations. Browser history and transactional Back/Cancel controls are retained.
- Local record sections remain inside Properties; leaving for portfolio tools is explicitly labeled.
- Photographic identity is a core screen requirement, with labeled icons/initials for missing images.
  Property banners, unit photos and tenant portraits are represented; other objects use type icons.
- Images plus fallbacks, not an uploaded-photo model for every entity. Synthetic images only in
  published examples. Property banners and tenant portraits already exist; unit uploads require a
  separately reviewed production model change.
- Explicit linked split is retained: choose the named remainder recipient once. A $79 bill with
  Studio B selected and Studio A entered as $55 results in $24 for Studio B. No automatic guessing.
- No slogans or “Operations Desk” navigation caption. Maintenance selectors apply immediately
  with JavaScript; plain forms remain available. Lease numeric headings align with their columns.
- This is another isolated E11 prototype review, not authorization to roll out production changes.
- Original and Revision 2 review material is consolidated in the Interactive Prototype page.
  The former Revision 2 URL remains only as a stable pointer; source backups preserve both reviews.

The owner approved the isolated interactive prototype: forest-green sidebar, staff workspaces and a
tenant dashboard sample; linked allocation ring without dragging; key journeys end to end. Current
RHP data may be used in a local read-only snapshot. Published examples must be synthetic/redacted.
No production page, financial record or Phase 7 behavior is changed, and no Phase 8 feature is started.

These questions gate the production redesign, not the approved maintenance fixes or study.
Record feedback in the E11 Plane item or this Design document, then reconcile it into repository
sources before implementation. The owner's navigation reference has now been visually reviewed:
it is branded Rentler and supports global navigation plus separate task context, not a mandate
to copy its branding or excluded features. It does not select a concept on the owner's behalf.

The structural planning direction is now selected; the first [working plan](navigation.md) defines
review rounds and explicitly separates proposals from approved choices. Balanced maintenance rows
are the starting treatment. The next review is a full-color prototype, not production rollout.
Future accounting remains E10, messaging E12/Phase 8 and payment processing Phase 11; none is
introduced by the design work.

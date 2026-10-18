# Operations Desk interactive prototype

**Register:** E11. **Status:** Isolated, full-color design review—not a production rollout.
This is the single working review page. The separate Revision 2 review has been consolidated here.
Owner feedback, including the later navigation mockup, is preserved below.

## Open and review

- [Properties workspace — synthetic demo](http://127.0.0.1:8014/properties/).
- [Staff dashboard](http://127.0.0.1:8014/).
- [Electricity allocation](http://127.0.0.1:8014/allocation/1/).
- [Private portfolio snapshot](http://127.0.0.1:8015/), only when separately launched.

These loopback links work on the development computer. Private examples are partially verified
development data, not audited records; do not publish screenshots from the private instance.

## Current interaction and feedback addressed

**One Properties workspace.** The middle navigator uses photo-led property blocks on both portfolio
and record pages. Clicking a property's photo/name header opens its overview and expands its units;
the separate Expand/Collapse control changes only that property's disclosure. Other properties retain
their state. A unit opens its dashboard on the right, not another competing navigation structure.
There is no separate “Property overview” link underneath each property.

**Manual, persistent expansion.** Several properties may stay expanded. Selecting Cedar House or
Apartment 1 does not collapse Alder Court. Expansion is carried in URLs and the temporary demo session,
including local sections, All units, Back/Forward, and returns from linked records. Legacy property
and unit deep links still work.

**Portfolio and local context.** Properties initially shows All properties and a portfolio summary.
All units retains search/property filtering. Overview, Details, Maintenance, Expense recoveries and
Documents remain within the selected location's workspace. Portfolio escape links are explicitly
named. All properties and All units appear only in the main left sidebar, not as a duplicated menu
above the middle navigator. Record pages rely on navigation tiers instead of Back-to-results/queue
buttons. Browser history and task-specific review Back/Cancel actions remain available.
Phones/tablets use a labeled location disclosure above one working area.

**Photos and labels.** Property banners/thumbnails, unit photos and tenant portraits establish identity.
Missing or broken images use labeled icons/initials. Fictional, locally bundled sample photos appear
only on synthetic records; private snapshots do not receive invented photo assignments.
Unit allocation colors are separate from maintenance/financial status colors. The website is full
color; printer-friendly documentation rules do not constrain it.

**Direct language and alignment.** Slogans and the sidebar concept caption are removed. Tenant
record pages no longer show redundant Back-to-results links. Numeric lease headings align with
their amounts. Maintenance status changes apply immediately with JavaScript; search uses Enter,
and ordinary Apply remains available without JavaScript.

**Linked electricity allocation.** Choose Studio B under “Send the remaining monthly amount to…”,
then enter $55 for Studio A: the $79 monthly amount becomes $55/$24, with 69.62%/30.38% and matching
ring segments. RHP remains the default recipient until explicitly changed. The selected unit is marked
calculated; other manual amounts are protected. Live preview, plain forms, review and confirmation
use the existing Decimal service. Rapid edits cancel/invalidate old responses.

## Capability/path audit

| Capability | Destination retained |
| --- | --- |
| Find/select a property | Photo/name header in the shared navigator; portfolio summary search |
| Expand/collapse units | Independent labeled control on each property; selection does not reset others |
| Portfolio-wide units | All units, with name/property filters and a preserved return |
| Property overview | Click the property header; units/occupancy and scoped work/bill summaries on the right |
| Unit, tenant and lease | Unit in navigator; tenant portrait/name; Open lease; View lease ledger |
| Vacant unit | Explicit vacancy and Start a lease preview |
| Building/unit facts, map/photos/amenities | Details section and existing Edit/details previews |
| Maintenance | Location-scoped local section, request detail with return, explicit portfolio queue link |
| Expense recovery | Scoped bills, existing allocation/review journey and return to the location |
| Documents | Scoped readable titles/visibility, labeled download preview, portfolio library link |
| Account/site administration | Existing separate utility/preview destinations; no new permissions |

No financial, tenancy, upload or maintenance service was replaced. Other unimplemented prototype
controls remain labeled previews, not simulated real operations. No unit-history, accounting,
messaging or payment-processing capability has been added.

## Verification and limits

The final navigation-cleanup gate passed **1005 tests, 1 opt-in maintenance-browser test skipped**
in 263.46 seconds. Focused prototype/design-tool/documentation checks passed **67 tests**.
`make lint`, `make check`, `make check-deploy`, migration generation/application checks and the live
application health smoke check passed. No application migration or dependency was introduced.

Browser review inspected 1440px desktop, 768px tablet and 390px phone layouts; independently expanded
properties and property-header selection; local location sections; the $55/$24 allocation/review;
keyboard location disclosure; aligned lease money columns;
and immediate maintenance Status filtering. Tablet/phone checks found no whole-page horizontal
overflow. The latest desktop check confirms aligned navigation and record headers without duplicated
portfolio links or record Back buttons. Five new synthetic captures plus the existing assets match
**56 uploaded files** by SHA-256.

The prototype uses a dummy database backend, blocked outgoing mail, a fixed static-asset allowlist,
and fixture-backed projections. Its loopback-only standard-library server handles concurrent requests;
idle connections time out after ten seconds. No live records, private files, uploads or notifications
are changed. Every simulated completion says “Prototype only—no RHP records changed.”

Plain-form operation is tested server-side. Actual JavaScript-disabled browser operation and 200%
zoom remain manual checks, not claimed passes or accessibility certification.

## Run, reset, and private data

```bash
uv run python -m tools.design_prototype serve --port 8014
```

Reset demo clears temporary state; restarting also clears server-side sessions. Staff/tenant selection
is a demonstration, not production authentication. Production remains on port 8000 unchanged.

Optional private snapshot:

```bash
uv run python -m tools.design_prototype export
uv run python -m tools.design_prototype serve --port 8015 --snapshot /tmp/EXPORTED-DIRECTORY/snapshot.json
```

Use the exact exported path. Export reads PostgreSQL in a read-only transaction and allowlists only
property/unit/tenant-display/lease, financial-summary and allocation fields. Snapshots stay outside
git in a restricted temporary directory. No credentials, private contacts, file contents, real messages
or sensitive payment references are exported. Runtime never queries the live database. Maintenance
conversations remain synthetic, and no fictitious transactions are attached to real lease accounts.

Image provenance/prompt set: `tools/design_prototype/static/IMAGES.md`.
The two studio samples intentionally share one interior photo; production unit-photo upload/storage
requires a later reviewed model change.

## Synthetic review captures

### Latest navigation cleanup

![Aligned property navigator without duplicated portfolio links or record Back buttons](http://10.60.0.227:8090/api/attachments.redirect?id=08f3c1b8-54c8-485d-8164-975bcb270fa0)

The left sidebar is the only menu containing All properties and All units. Property/unit selection
starts inline with the main record; navigation tiers replace record-level Back buttons.

The following earlier synthetic captures show the consolidated workflow before this final navigation
cleanup. They contain no real RHP records.
Their exact stored bytes are checked against the local source files.

### Unified portfolio workspace

![Unified Properties navigator and portfolio overview](http://10.60.0.227:8090/api/attachments.redirect?id=434cc8ea-1cc8-4718-8724-dd53544a37fe)

### Selected unit — desktop

![Photo-led property navigator with independently expanded properties and Studio A dashboard](http://10.60.0.227:8090/api/attachments.redirect?id=4bcdb391-c441-4b6e-81b9-bdf9d24420a3)

### Selected unit — phone

![Phone unit dashboard with keyboard-operable property selector and no page overflow](http://10.60.0.227:8090/api/attachments.redirect?id=b4aa3550-9d81-42f6-aab1-5eaa1f01222d)

### Linked allocation review

![Reviewed 79 dollar monthly bill split 55 dollars to Studio A and 24 dollars to Studio B](http://10.60.0.227:8090/api/attachments.redirect?id=875e6e21-a80a-4bb3-af13-27c7bf099ab8)

Earlier captures are retained as
reference links, not presented as the latest screens:

- [Earlier staff dashboard](http://10.60.0.227:8090/api/attachments.redirect?id=f7ce6c98-bfbc-4d50-bddf-543ebdaa13d1).
- [Earlier allocation](http://10.60.0.227:8090/api/attachments.redirect?id=7f5d9a55-b69b-4134-b24f-47bec57012d1).
- [Earlier unit context](http://10.60.0.227:8090/api/attachments.redirect?id=31d4c6f3-c121-48aa-87b4-347e41930010).
- [Earlier ledger](http://10.60.0.227:8090/api/attachments.redirect?id=d0b34fa2-cd55-4b50-90c2-a5024d837028).
- [Earlier maintenance phone](http://10.60.0.227:8090/api/attachments.redirect?id=b957e35f-876b-4603-85a5-13ee6f4b93e7).
- [Earlier tenant phone](http://10.60.0.227:8090/api/attachments.redirect?id=213b0e36-51e4-400b-a208-94d798f906f1).

## Original owner review — preserved

Original source backup: `docs/design/sources/prototype-owner-review-2026-10-18.md`.

EXCELLENT!

A few notes, we'll have to iron out the design again obviously...

\nThe monthly amount for an expense recovery allocation isn't calculating again. I have electricity at $79, and i put in for Studio A $55 as a change, and it warns over allocated. It should dynamically repopulate the percentages and the Studio B amounts.

Slogans are not to be added to RHP. All this stuff: A CLEAR VIEW OF YOUR PORTFOLIO Your operations, in focus. The work that needs you, and the records behind it. Get rid of all of it. Just show Portfolio / Dashboard at the very top like it has.

the extra "Operations Desk" on the left nav bar, remove it.

In the maintenance sections, the filters should not require an apply button. Just have the Status selector entry be the apply.

The Properties is a good start, but the left navigation tab, and the "open property" button is getting mixed up. I think the <http://127.0.0.1:8014/properties/1/?back=/properties/> is a better dashboard experience We Make more clear the "Alder Court" tab is the property. Photos are going to be very important to recognize properties/units, etc. Also, there should be indication that clicking on Properties focuses the "All Properties". And the units should be accessible within the focus of the. Instead of square cards, they should be large cards with the units expandable down. Basically, spawn the bulk of <http://127.0.0.1:8014/properties/1/?back=/properties/> inside the Alder Court Block (Which will need to take the full width). Cedar House will need to be below it, which clicking on open property will expand it out instead. Hopefully this is enough to see how we can better portray the Properties Tab.

\nTenants: remove: A person may have more than one tenancy. Each lease account stays separate. remove: PEOPLE & TENANCIES

Leases: Column's are not aligned. But it looks good Otherwise.

\nThe left side is called the navigation bar. What is the central system called? Is that the Operations Desk? I don't want the properties tabs, like inside Alder Court, to have those title tabs (Overview, Details, Maintenance, Expense Recoveries, Documents, to pop me out into another left side nav-bar screen. We should have that inner operations desk, if thats the name of that system.

Watch <https://youtu.be/utFRZfb-zW4?t=146> for a demo of the properties tab then the expanding units inner menus. They accomplish almost exactly what we're doing with a main nav bar, then a property unit "nav bar", then the Unit Details. That way there's that familiar folder structure for navigation. We don't need to copy the information layout they have inside the cards, I like ours. But we should copy that navigation hierarchy.

![Notice the folder hierarchy of Nav Bar -> Property Nav Bar -> units expand -> into main Unit Dashboard](http://10.60.0.227:8090/api/attachments.redirect?id=f581cab9-1448-4398-a168-6d78cc5c2d39)

![Notice the Misalignment](http://10.60.0.227:8090/api/attachments.redirect?id=16a47a32-1122-46af-9500-f9cfc731641a)

## Austin Notes Continued — preserved

Source backup: `docs/design/sources/prototype-owner-review-continued-2026-10-18.md`.
These later notes supersede the initial single-expanded-property proposal.

![Notice the Alignment Issue With "Back to Results"](http://10.60.0.227:8090/api/attachments.redirect?id=90c8c353-7de4-4371-8802-8a54682ae166)

Just like clicking on a tenant box opens that tenant page, I want to have each property box be clickable, and that causes it to expand. Right now, there is only a small button to expand “Alder court” But intuitively, clicking on the box that is Alder Court should expand it. \n\n ![Here is another one. See alder court is expanded? When I clicked on "Cedar house Property Overview" Alder court collapsed. So I opened it again to see it, but I'm on All Properties / Cedar house. I want manual control over expanding and collapsing properties. They should remain aware of their state when I move into a different one. So if I had Alder Court open on Property Preview, when I click on Cedar House Apartment 1, Alder Court should remain expanded. ](http://10.60.0.227:8090/api/attachments.redirect?id=c656aad1-faa1-4c53-b4d3-aa94669fb197)

 ![Properties (A)](http://10.60.0.227:8090/api/attachments.redirect?id=ba501de2-2d01-4572-b398-59a49dafd176) ![All Properties (B)](http://10.60.0.227:8090/api/attachments.redirect?id=ee19b939-4bd4-416e-9d12-3a44af886926)

These two workflows are clashing with each other. We need to consolidate them into a single workflow, and figure out if any information is unique on one of the pages. \n\nThe caption names are my reference names for the screenshot: A and B\nImagine Clicking Properties in the navbar brings you to the All Properties (B) page. That tiny 2nd navbar is turned into the ui of “Properties screenshot”. Then the actual dashboard changes into what we see in “All Properties” if a unit is selected. If a Property is selected, we see property overview page. Then we don’t have a specific property overview portion in the 2nd navbar section.

 ![This is the idea... Where clicking on Alder Court will take it to the property overview. Clicking on Studio A on the middle nav bar will open to the current screen. ](http://10.60.0.227:8090/api/attachments.redirect?id=7bb8fa4e-5902-42b1-995a-e6d64b023975)

Check for any menus or paths that become destroyed with this workflow, we’ll need to repair.

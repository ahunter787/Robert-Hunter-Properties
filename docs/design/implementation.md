# Operations Desk application migration

**Status:** Complete — owner accepted and locally merged October 19, 2026
**Register:** E11; not Phase 8, Phase 9, or property accounting.
**Owner approval:** October 18, 2026, approved implementation plan in chat.

## Delivery boundaries

The revised interactive prototype is accepted as the visual/navigation baseline. Commit and
locally merge the existing Phase 7 baseline, preserve the prototype and messaging-scope records
separately, then work on `codex/operations-desk`. Do not push. The owner subsequently accepted E11,
including the banner correction, and authorized its local commit/merge and starting `rhp-8`.
The Properties review checkpoint was accepted before propagating the remaining layouts. The shared
role-aware shell surrounds the completed record workspaces and existing operational forms.

The accepted application was preserved on `codex/operations-desk` as `9b90b7d` and squashed into
local `main` as `1e906b6`. Earlier local `main` commits were retained. The design branch remains
available for recovery; nothing was pushed or deployed. Phase 8 implementation now belongs to
`rhp-8` and does not reopen E11 or implement the separate prior-activity calculator proposal.

Owner-supplied unit photos added to the original interactive-review page remain there unchanged.
They are not copied into tracked assets or synthetic published application captures. That page is
excluded from migration-record updates so its newer owner material cannot be overwritten.

Use server-rendered Django, the existing Tailwind build, HTMX and small first-party enhancements.
No application dependency, fake action, synthetic production image, financial rewrite, or demo
authentication enters the application. Preserve existing URLs and authorization services.

## Capability and destination checklist

| Existing capability | Destination after migration | First checkpoint |
| --- | --- | --- |
| Portfolio search, status filters, pagination | Properties → All properties | Implemented |
| Portfolio-wide units/search/filters | Properties → All units | Implemented |
| Property/unit selection and identity | Unified middle navigator and record header | Implemented |
| Property/unit create, edit, retirement, restricted deletion | Record actions and existing forms | Preserve |
| Maps, square feet, amenities, property notes | Overview/Details local sections | Preserve |
| Unit photo | Unit form and authorized image views | Implemented additive field |
| Tenants and invitations/profile/photos | Overview, Tenancies, Contact & photo, Account & access | Implemented; account-level photos, self-service and admin-any-account upload |
| Lease lifecycle/schedule/NNN/prior activity | Lease second navigation tier and existing forms | Implemented |
| Payment recording/corrections/account lifecycle | Rent & Payments and existing confirmations | Implemented; services unchanged |
| Bills, allocation, review, charge posting | Expense-recovery property workspace; scoped property section | Implemented; signed calculation/review unchanged |
| Requests, sharing, work, costs, recharges, notifications/vendors | Request sections and scoped property/unit sections | Implemented; services unchanged |
| Private files, visibility, uploads/removal | Context-linked library and scoped property/unit sections | Implemented; private endpoints retained |
| Tenant dashboard, lease, statement, maintenance, documents | Short own-tenancy navigation | Implemented with existing workflows |
| Assigned maintenance worker requests | Assigned-work-only shell | Preserve |
| Sign-in/profile/password/invitations/errors | Matching minimal or authenticated shell | Shared foundation |
| Authorized Django administration | Separate utility link, unchanged admin | Preserve |

## First slice contract

- Forest-green persistent sidebar, light surfaces, aligned navigation and record headers.
- Properties contains All properties and All units only in the left sidebar. Independently
  expanded property blocks and selected records are represented in URLs; session defaults are
  navigation preferences, never access grants. Opening a property expands it without closing others.
- Local Overview, Details, Maintenance, Expense recoveries and Documents remain in Properties.
  Every related query uses the selected property's/unit's relationships. Portfolio exits are explicit.
- Browser history remains functional; no record Back buttons. Form Back/Cancel controls remain.
- One optional `Unit.photo` with randomized storage and existing image validation/size limits.
  Managers manage it; tenants read only images for their existing authorized lease context.
  Staff/tenant image routes enforce access independently. Workers gain no general photo endpoint.
- Replaced/removed unit images are deleted only after database commit; failed writes clean up
  newly written files. Deletion cleanup also runs after commit. Missing/broken images use labeled
  fallback icons, never unrelated property or synthetic unit photographs.
- Mobile Menu and property selector remain operable with keyboard and without JavaScript.
  JavaScript adds responsive disclosure/focus and scroll restoration, not business authority.

## Verification and handoff

The first slice is implemented in the real Django application, not the prototype: shared role-aware
shell, Properties workspace/local sections, independent property expansion, All units results,
optional unit-photo forms and private staff/tenant endpoints. The additive migration is
`properties/0005_unit_photo`, applied locally. No application dependency was added.

Focused new Properties authorization/navigation/upload/rollback checks: **21 passed**.
Final `make test`: **1027 passed, 2 skipped** in 272.98 seconds. Both skipped cases are opt-in
browser harnesses; the new E11 harness passed separately with scripts enabled and CSP-blocked.
`make lint`, `make check`, `make check-deploy`, CSS build, migration drift/application checks and
`git diff --check` passed. A fresh loopback-only process answered health/public requests with 200
and protected Properties with an authentication redirect; the temporary process was stopped.
Engineering/Plane synchronization and ecosystem verification passed (64 documents, 25 mirrored
items). Scoped Design text verification passed. Asset verification currently reports the two
new, unuploaded captures; their publication is pending permission, not claimed complete.
Authenticated disposable browser reviews passed with JavaScript enabled and separately with
scripts blocked by response CSP. Desktop 1440px, tablet 768px and phone 390px were inspected;
tablet/phone had no whole-page horizontal overflow. Verified keyboard disclosure, mobile Menu
focus/Escape, independent expansion, scoped maintenance/documents, plain-form search and browser
Back/Forward/filter restoration. Actual 200% browser zoom could not be applied through the browser
tool and remains an owner/manual check; no accessibility certification is claimed.

Two synthetic application captures are retained under `docs/design/artifacts/`. The normal Outline
file picker did not open through browser automation. Clipboard access was blocked by the safeguard;
existing clipboard contents were not read. Screenshot upload awaits the owner's answer about
temporarily replacing (without reading/restoring) the clipboard; text records are already published.

Add tests for navigation roles, URL state, scoping, no-JavaScript links/forms, image security,
upload/replacement/removal, transaction failure and migration compatibility. Review authenticated
desktop/tablet/phone layouts with disposable data, keyboard, 200% zoom and scripts disabled.
Run project gates, CSS build, migration drift/application checks and smoke start. Record exact
results and limitations, synchronize engineering/Plane records and publish only synthetic Design
evidence. Owner review of Properties precedes the remaining portal content migration.

## Owner review accepted — continuation

On October 18 the owner approved the Properties slice in chat and asked to continue.
Additional feedback was found in the Outline copy (not in new Plane comments). Preserve the
original notes and attached screenshots there; do not copy identifiable review images into git.

Immediate corrections: isolate each tenant portrait URL, align portfolio columns, double the
record banner height, and remove the redundant People label. Extend the second navigation tier
to leases: financial work in the center, with terms, rent schedule, tenants and documents reachable
without a cascading record page. Preserve operational actions, URLs, authorization and arithmetic.

The owner approved retaining restricted permanent deletion of empty mistaken/test properties,
with crimson styling and an exact typed confirmation. Taking a property out of service remains
the normal removal path. The owner requested a separate scoped calculator plan, not implementation:
[Prior lease activity calculator](prior-activity-calculator.md). Do not change onboarding arithmetic.
Existing property deletion is administrator-only and blocked by units; units with leases and
financial history remain protected. Taking a property out of service does not delete its units.

Industry comparison: [DoorLoop recommends making properties inactive](https://support.doorloop.com/en/articles/8439778-delete-a-property)
to preserve leases and transactions, with deletion reserved for mistaken/test records. RHP retains
its stricter immutable-financial-history rules; this is not permission to delete historical charges.

## Remaining approved work after review

### Final presentation pass authorized

The owner approved the remaining portal migration in chat: people-first account sections,
separate tenancy conversations and internal maintenance notes, scoped recovery workspaces,
document/context refinement and remaining forms. Preserve existing services, data and routes.
No new model, dependency, calculator implementation, commit, merge, push or deployment is authorized.
Staff maintenance conversation selection is validated against the authorized request's audiences;
tenant write eligibility belongs to the selected tenancy, not another currently occupied audience.
Status/permission milestones use existing scoped updates, never parsed free-text or raw tenant audits.

The Properties review checkpoint is accepted. Continue the remaining record layouts while preserving
the owner's original Outline feedback and separating new functional requests from presentation work.

### Continuation implemented and verified

- Fixed tenant-list portrait reuse without changing stored photos. Removed People labels, aligned
  portfolio columns, and increased record banner height from 170px to 340px.
- Lease details now use the second navigation tier: Rent & Payments, Terms, Rent schedule, Tenants,
  Documents. Financial content shares the original ledger template, running balance, inline
  corrections and operational services. Existing ledger URLs still provide the full-width view.
  Lease lists and tenant links use real unit photos/portraits with explicit fallback reset.
- Expense allocations render a server-derived segmented ring during editing and review. Stable
  unit colors match fields and legend; vacancies stay in their unit segment and only the remainder
  is neutral RHP. Zero/invalid/over-allocated states do not display a normalized ring. Plain-form
  calculations and the signed review/save workflow remain authoritative and unchanged.
- Staff maintenance uses balanced colored rows, immediate select navigation, Enter search and
  Apply fallback. Tenant maintenance shows active requests and expandable own-tenancy history,
  without staff filters. Tenant dashboard and lease photos use the existing scoped image endpoint.
- Property deletion requires an exact typed confirmation server-side; existing administrator and
  linked-record protections remain. The normal retirement workflow remains available. No additional
  model change or migration beyond the first slice's optional unit photo is introduced.

The scoped Design publisher preserves the known, reviewed migration owner-note appendix in Outline
while refusing edits to its authored prefix. It stores only hashes in the publication manifest,
never copies those tenant screenshots into tracked source, and retains other documents' edit guard.

Final continuation gate: `make test` **1045 passed, 2 skipped** in 274.44 seconds. The skips are
the opt-in browser fixtures. `make lint`, `make check`, `make check-deploy`, CSS build,
`makemigrations --check --dry-run`, `migrate --check` and `git diff --check` passed. A fresh
loopback process returned 200 for health/public pages and 302 for protected routes, then stopped.
The first full run exposed two legacy heading/capitalization assertions; these were updated while
retaining the actual monetary checks, and the final run above passed.

Disposable authenticated desktop/phone review verified lease sections, real image endpoints,
portrait isolation, the exact $79 → $55/$24 allocation with 69.62%/30.38%, rapid edits, review/Back
preservation, legend-to-field focus and no phone overflow. The script-blocked plain-form calculation
and review also passed separately. Staff select filtering/Enter search and browser Back were checked;
Back initially restored an obsolete select value onto earlier results, corrected with a filter-only
pageshow reset and rechecked against the URL's rendered defaults. No saved development allocation
was changed. QA uses disposable database records; its session/CSRF cookie names are separate from
the normal localhost portal cookies.

The synthetic ring review capture is local-only at `/tmp/rhp-operations-desk-allocation-review.png`.
The scoped asset verifier still reports the same two earlier missing Properties uploads. Clipboard
replacement is not authorized, so they remain local; no upload success is claimed. Actual browser
200% zoom and a full print-device review remain manual checks. New lease/tablet and remaining-form
reviews should accompany their next migration slice rather than being inferred from Properties QA.

### Final remaining-layout pass

People-first account sections now show current and historical memberships, location/lease/ledger
links and read-only contact information; account administration is secondary. Portraits have initials
or icon fallbacks, with independent image URLs. Existing invitation, activation and role permissions
remain unchanged. Account photos are now account-level (`User.photo`): the owner uploads or replaces
their own from Profile & account, and admins can set any account's photo from Contact & photo. Legacy
`TenantProfile.photo` rows are copied forward by migration 0005 and retained for reversibility.

Maintenance has Conversations, Work details and Internal notes; only managers receive Repair expenses
and Delivery & history. Each conversation resolves an Audience belonging to this authorized request;
tenants see only their own audiences. Defaults prefer the accessible reporting tenancy, otherwise the
first audience; staff-only requests open Internal notes. Former-tenant write controls depend on the
selected tenancy, not another current membership. Existing scoped status/permission updates appear
in an expandable history without parsing body text, losing revisions or moving stored records. Raw
audit summaries are manager-only. Workers receive no general property/unit photo URL, and tenant
headers never substitute a different current tenancy's photo for an historical request location.

The recovery sidebar workspace now shows property context, expenses, all recorded bill periods,
monthly amounts, allocation links and posted-cycle locks. URL navigation context is validated against
the authoritative cycle/property. Save and Cancel retain the originating recovery workspace or scoped
Properties section. Calculator arithmetic and signing are unchanged.

Documents display linked property/tenancy/person context and explicit visibility. Property filters
include lease-linked documents; unit filters are validated, and pagination retains filters. Upload
and Cancel return to the record's Documents section. Shared form help/errors have matching accessible
IDs; dashboards prioritize existing attention metrics, workers see assigned work, and public/auth/error
pages retain the common minimal shell. Photo inputs no longer expose raw storage links or duplicate
removal checkboxes; explicit removal controls and private photo endpoints remain. No new reporting,
staff contact-edit workflow or capability is introduced. No new migration or dependency is needed.

Disposable authenticated browser review covered 1440px desktop, 768px tablet and 390px phone layouts:
person/access/contact sections, missing-portrait initials, keyboard-operated mobile section selection,
separate maintenance conversations/internal notes/work/cost/delivery sections, and tenant privacy.
Saving an internal QA note returned to Internal notes; that note and manager-only sections were absent
from the tenant response. Recovery selection, allocation review and Cancel preserved property context;
the existing Python calculator reproduced $79 → $55/$24 and 69.62%/30.38% in preview and review.
A separate CSP script-blocked session verified sign-in, account navigation, clean photo inputs,
document titles/context/visibility, selected-conversation form defaults and Cancel. Both disposable
browser harness runs passed and were torn down; normal portal cookies and development records were
untouched. Browser review exposed and corrected a low-contrast primary link treatment.

The latest synthetic maintenance captures are local-only at
`/tmp/rhp-final-maintenance-conversation.jpg` and `/tmp/rhp-final-maintenance-phone.jpg`.
The two earlier Properties screenshot uploads remain pending a permitted upload path; no clipboard
access or replacement was attempted. Actual 200% browser zoom and full print-device review remain
manual checks, separately from responsive browser and application checks. This is an implemented,
uncommitted local migration awaiting owner acceptance, not a released or deployed redesign.

Final application gate: `make test` **1053 passed, 2 skipped** in 281.87 seconds. The two skips are
opt-in browser fixtures; the Operations Desk fixture passed separately in both scripted and
script-blocked sessions. `make lint` (264 formatted files), `make check`, `make check-deploy`,
`make assets`, `makemigrations --check --dry-run`, `migrate --check` and `git diff --check` passed.
A fresh loopback-only process returned 200 for health/public/sign-in and 302 for protected staff and
tenant routes, then stopped. An earlier full run found a stale worker-dashboard label assertion and a
duplicate-name test fixture; both were corrected before the successful final run. No financial or
maintenance service change was needed. The asset verifier still fails only on the two known missing
Properties uploads, separate from application gates and text synchronization.

Scoped publication covers the Design index, owner-decision record and this implementation record.
The separate prior-activity calculator document contains newer owner answers; its Outline copy is
left untouched for reconciliation in that proposal's own work, without implementing the calculator.
The migration's original Austin Notes appendix remains preserved. A publication attempt stopped on
that separate document's edit guard after publishing the migration records; their source prefixes
were verified before refreshing only their local publication metadata and retrying the scoped set.

Scoped Design text verification passed for those three records. Engineering/Plane synchronization
and `make -C ecosystem verify` passed: 65 documents, 25 mirrored work items, 10 separately raised
items, no sync drift. The post-publication documentation/owner-note/workspace regression group also
passed **19 tests**, and final lint/formatting and whitespace checks passed. No commit, merge, push
or deployment was performed.

## Recovery and changed components

### October 19, 2026 — property banner correction

Replacement uploads were saved, but the same permission-checked banner URL was cached for five
minutes, allowing the previous image to remain visible. Staff banner URLs now include a revision
derived from the randomized stored filename, without exposing its storage path; the endpoint also
requires private-cache revalidation. Property workspace, navigator, recovery and maintenance headers
use that revision. Existing endpoint paths and manager authorization remain unchanged.

The property form groups the banner preview, upload and **Clear banner photo** button. The old
removal checkbox is gone. Choosing a new photo replaces the banner on Save changes. Clear is an
explicit CSRF-protected POST on the existing edit endpoint; it changes only the saved banner and
discards unrelated unfinished form inputs. Old bytes are removed after transaction commit, not on
rollback. Clear owns a separate form, so Enter in a property field remains the Save action rather
than accidentally clearing the banner. No model field, migration, dependency or financial change is
introduced.

Focused banner/Properties tests passed (35 before the additional rollback test). Disposable browser
QA verified clearing with an unfinished name field and the consolidated controls. The upload picker
did not expose a valid selected file and browser submission was blocked by its safeguard; no workaround
or clipboard access was attempted. Replacement, cache revision and cleanup are tested server-side.
The reported property and its photos were not modified during QA. Synthetic control capture:
`/tmp/rhp-banner-controls.jpg`, local only.

Final `make test`: **1054 passed, 2 skipped** in 285.50 seconds. The skips are opt-in browser fixtures;
the disposable Operations Desk browser fixture passed separately. Lint, formatting, Django and
deployment checks, CSS build, migration drift/application checks, whitespace checks and fresh
loopback-only startup passed. No new migration, dependency, commit, merge, push or deployment.

The local baseline is `7603ba7` on `main`: Phase 7 squash `6a492b6`, Design/prototype `ccb0187`,
binary-artifact metadata `32b139d`, and Phase 8 scope-only `7603ba7`. Existing earlier local commits
are retained. No push was made. Redesign changes on `codex/operations-desk` are uncommitted.
Recovery should preserve the additive photo column and stored photos rather than destructively
reversing its migration; baseline application code does not use that optional column.

Changed application components: shared base/sidebar/location-image templates; Tailwind tokens and
application-shell styles; first-party navigation JavaScript and context processor; property/unit
views, read-only workspace projection, unit form/model/private image routes and cleanup signal;
read-only expense-recovery index. Properties templates replace the old independent detail pages;
existing financial and maintenance services are unchanged. Tests add authorization, navigation,
photo lifecycle, additive migration and a disposable browser harness; prior layout assertions now
target Details/recoveries sections and distinguish the portfolio navigator from scoped content.
Specification, architecture, security, database, roadmap and Design records are updated. Scoped
Design publishing/verification recognizes this new implementation record; ecosystem tooling is
unchanged.

Continuation components: `apps/leases/{views,workspace}.py`,
`apps/responsibilities/{forms,views,presentation}.py`, `apps/maintenance/views.py`,
`apps/properties/{forms,views}.py`; lease workspace/shared-ledger and allocation-ring templates;
tenant identity/photo components; account/lease/property/document/maintenance presentation;
`assets/css/input.css`, `static/js/portal.js` and base asset versions. Tests cover the new lease
sections, authoritative chart projection, portrait isolation, deletion phrase, tenancy queue privacy
and publisher owner-note guard. `tools/publish_design.py` recognizes the scoped calculator proposal
and preserves the migration appendix. Design/source/architecture/security records reflect this work.

Final-pass components: `apps/common/workspaces.py`, `apps/maintenance/workspace.py` and presentation
views in accounts/documents/maintenance/recoveries; record navigation and account-tenancy templates;
maintenance location/conversation/access/expense templates; document library/upload and recovery
workspace templates; shared form/avatar styles and dashboards. Tests add selected-audience privacy,
former-tenancy read-only controls, assigned-worker boundaries, scoped recovery/document navigation
and private-storage-name protection. Existing operational endpoint tests now address the appropriate
local section without weakening authorization or money assertions.

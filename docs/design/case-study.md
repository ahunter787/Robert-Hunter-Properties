# Current-interface audit and case study

**Evidence date:** October 17, 2026. **Source:** owner RHPDEV-98, source inspection, Phase 7 QA.
These are design findings and proposals, not claims of production usability testing.

## Why the initial shell no longer fits

The shared shell puts both roles into a `max-w-5xl` container. The staff navigation is a wrapping
top-level list spanning management, maintenance, properties, units, leases, documents, money,
tenants and account actions. More destinations compete at the same level; ledger columns and
multi-part request pages compete for the same narrow reading width. Making everything smaller
would move complexity onto the user rather than organize it.

The maintenance index uses the same property/status/priority/assignment/age filter interface for
staff and tenants. The owner's expected tenant workload is one to three active requests: most of
those controls cannot help. Default to active request cards and expandable history instead.

The request detail displays every visible Update as a full card. A work change produces an
internal status record and one public record per shared tenancy. Staff see repeated logical
milestones, while notes, revisions, attachments, expenses and delivery attempts compete below.
Introduce a presentation projection: group the status milestone, keep each conversation scoped,
and disclose administrative evidence separately. Do not delete or merge underlying records.

## Four representative tasks

| Task | Current friction | Proposed structure | Acceptance question |
| --- | --- | --- | --- |
| Find work needing attention | Global navigation and filters compete | Scoped staff queue; urgency and age first | Can a manager identify the next request without opening every item? |
| Understand a repair | Repeated status cards bury conversation | Summary, conversation, compact milestones, separate evidence | Can staff distinguish tenant-visible text from internal notes immediately? |
| Check my request | Tenant receives portfolio-style filters | N active requests, clear status, expandable history | Can a tenant find their next update in one screen? |
| Reconcile a lease | Narrow shell around a dense ledger | Wide staff account view; labeled mobile transactions | Are due now, upcoming and total balance unambiguous? |

## External references and limits

- [Buildium maintenance](https://www.buildium.com/features/property-management-maintenance-software/)
  presents requests, assignments and updates as an operational workspace. RHP adopts the separation
  of actionable work from supporting detail, not Buildium's full feature set.
- [AppFolio portal guidance](https://www.appfolio.com/help/online-portal) distinguishes maintenance
  submission, entry permission and status/detail review. This supports a short tenant overview
  leading into a conversation; it does not prove any one navigation pattern is universal.
- [DoorLoop request creation](https://support.doorloop.com/en/articles/7191970-create-a-tenant-request-maintenance-request)
  supports recording requests received outside the portal. Its
  [work-order overview](https://www.doorloop.com/features/work-orders) separates requests and repair
  tracking. RHP retains explicit human decisions rather than adopting vendor payment or automated liability.
- The owner's screenshot, originally called Rently in the ticket, is branded **Rentler**. The owner
  re-uploaded it into Outline on October 17, enabling visual review. It shows persistent left
  domain navigation, a separate Maintenance / New Request context header, grouped secondary help
  links, and a focused form with a quiet upload area and Back/Submit actions. These support
  Portfolio workspace's global/context separation. The screenshot does not establish contextual
  tabs or a split queue as industry requirements; those remain RHP alternatives. RHP does not
  copy its Applications/Favorites destinations, “Importance” wording, brand blue or marketing block.
  The original remains intact in the Calm portal gallery and is indexed under Screenshots.

- The owner added four **Innago** screenshots and notes to
  [Screenshots and annotated observations](http://10.60.0.227:8090/doc/screenshots-and-annotated-observations-5LeE4MBxKQ),
  visually reviewed October 17. They show a persistent domain sidebar, operational dashboard,
  property rows with lease/occupancy/work signals, and selected unit detail beside a retained
  property/unit navigator. This is closest to **B — Operations desk**, using **A's sidebar**.
  The decisive evidence is retained list/detail context, not merely cards, color or navigation
  position. No maintenance queue, phone layout or keyboard behavior is demonstrated by these images.
  The owner's tenant-focused interpretation informs the proposal; the screenshots do not establish
  vendor research findings. The expanded [B description](concepts.md) separates observation from
  RHP adaptation. Original attachments and owner notes remain unchanged in Outline.

The navigation and density proposals below are RHP design recommendations, not an industry mandate.
No competitor screenshots or proprietary interface assets are copied into the concepts.

## Recommended direction

The initial study recommended starting with Portfolio workspace as the lowest-risk structural change.
On October 18 the owner selected **Operations desk + persistent sidebar** for iterative planning,
strongly informed by Innago's navigation/information strategies while preserving RHP workflows.
The [working plan](navigation.md) develops property/unit, tenant/lease and operational context beyond
maintenance alone. Exact navigation, density and visual language remain reviewable; no production
implementation is authorized. Keep the simplified tenant hierarchy distinct from the staff workspace.

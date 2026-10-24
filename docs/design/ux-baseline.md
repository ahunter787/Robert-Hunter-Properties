# UX baseline — before E18

**Purpose:** preserve the pre-hardening portal exactly so the owner can compare or roll back. This is a
code and evidence snapshot, not a proposed design.

## Snapshot identity

| Fact | Value |
| --- | --- |
| Tag | `ux-baseline-2026-10-22` |
| Branch | `ux-baseline` (same commit as the tag) |
| Commit | `e4bb6ea` |
| E18 work branch | `rhp-e18-ux` (branches from the snapshot) |
| File manifest | [`artifacts/ux-baseline-2026-10-22/manifest.sha256`](artifacts/ux-baseline-2026-10-22/manifest.sha256) |

The tag is the immutable copy. The branch exists so the baseline is easy to check out or inspect; do not
rewrite either after E18 begins.

## What the baseline contains

- The flat staff sidebar and current tenant navigation.
- The card/table/form-first screens and the existing visual tokens.
- The pre-E18 Communications inbox, conversation and message-batch templates.
- The current `static/js/communications.js` polling/read behavior and `static/js/portal.js`.
- E15 quick replies/archive/mute/internal notes, E16 timeline and E17 insurance as they existed at the
  snapshot.

The manifest records SHA-256 hashes for the UX files that E18 is expected to change. It lets a reviewer
prove that a checked-out baseline matches the recorded one.

## Screenshot set

Captured from the tagged baseline with disposable QA data on October 23, 2026, at 1440px and 390px:

- `manager-dashboard.png` — metric-grid dashboard, flat sidebar, no attention rail;
- `manager-inbox.png` — card-list inbox and Apply-filters form;
- `manager-conversation.png` — blog-style conversation and manual read button;
- `tenant-dashboard.png` — card stack before the next-step/action treatment;
- `tenant-messages-phone.png` — phone-width inbox before the chat rebuild.

The existing reviewed captures under `docs/design/artifacts/` remain the visual record for the earlier
entry/operations-desk states. The after-views live under `docs/design/artifacts/ux-e18-review/`; this
baseline set is the rollback comparison.

## Restore

```bash
git switch -c restore/ux-baseline ux-baseline-2026-10-22
make assets
make test
make lint
make check
```

E18 is planned as presentation/interaction work with no schema changes, so this code restore does not
require data repair. If a future E18 slice adds a migration or stored preference, that slice must document
a reversible migration and a data-preservation step before implementation; do not silently make the
baseline restore data-unsafe.

## Review rule

Each E18 slice is reviewed against this baseline at desktop and phone widths. The baseline stays available
after E18 is folded; the owner may ask for a rollback or a selective revert rather than an all-or-nothing
choice.

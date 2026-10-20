# Financial clarity — synthetic review examples

**Status:** Owner-accepted financial reading surface, expandable bills and reviewed history recovery;
local preservation and merge authorized. Remaining task structures are proposals, not implemented.
The full regression gate passed:
1,136 tests, with five opt-in browser tests skipped; financial browser QA passed separately.
Synthetic records only.
**Date:** October 20, 2026. Original owner screenshots remain unchanged in their original document.

## Review material

- [Audit and prioritized findings](http://10.60.0.227:8090/doc/financial-clarity-and-manager-workflow-audit-uULKrnbLva)
- [Vocabulary, icons and color](http://10.60.0.227:8090/doc/financial-language-icons-and-color-proposed-specification-PabCAqPpru)
- [Implementation release and checkpoint](http://10.60.0.227:8090/doc/financial-clarity-proposed-implementation-sequence-mLtsyZofB0)
- [Original scratch sheet](http://10.60.0.227:8090/doc/accounting-design-audit-8ceuIRgYSF)

The five documentation examples illustrate (1) one lease financial view, (2) starting account records,
(3) received versus expected payments, (4) correcting a charge, and (5) allocating a $79 monthly bill.
Every example pairs desktop and phone information structure. These are not interactive screens or
pixel-perfect website proposals. The website remains full-color; the grayscale book tests whether
the labels still communicate meaning without color.

October 20 owner refinement: only amounts carry financial meaning. Debt/cost red, receipts/credit
balances green, correction deltas purple; labels, percentages, expected payments and unposted rent
black. Blue/orange financial semantics are removed. The $237 bill remains a three-month property
cost; the $79 allocation is monthly. Studio names and percentages are black, $55/$24 cost amounts red.

## Generated local files — upload gap

Color and grayscale five-page Letter PDFs, ten vector SVG pages, ten PNG previews and the editable
JSON scene book are retained in `docs/design/financial-clarity/`. Each page was visually inspected
in color and grayscale. Text contrast was calculated separately; no production WCAG certification
or physical print/200%-zoom validation is claimed.

- Color print book: `artifacts/financial-examples.pdf`.
- Grayscale print book: `artifacts/financial-examples-grayscale.pdf`.
- Editable scene book: `sources/financial-examples.json`.
- Rebuild: bundled Python + `build_examples.py`, then Poppler PNG rendering.
- Synthetic application captures: `captures/financial-audit-{lease,ledger,payment,allocation,allocation-phone}.png`.
- First implementation captures: `captures/checkpoint-*-desktop.jpg`, `checkpoint-pending-tablet.jpg`,
  `checkpoint-pending-phone.jpg` and `checkpoint-tenant-*-phone.jpg`. These show actual disposable
  authenticated application screens, not wireframes. The early audit captures remain historical.
- Icon/history refinement: `captures/icons-history-desktop.jpg` and `captures/icons-history-phone.jpg`.
  These show the replacement banknote/check, house/dollar and receipt/dollar icons, Expense Recovery
  wording, Date order / History controls and older-history access. Prior checkpoint images retain
  the superseded tray/document glyphs for historical comparison; they are not the current mappings.
- Expandable bills: `captures/bills-desktop.jpg`, `bills-phone.jpg` and `bills-tenant-desktop.jpg`.
  The current display combines same-due-date charges, shows payment progress only for the bill,
  and retains separate payment records. Older flat transaction captures are historical.
- Existing-history recovery: `captures/history-recovery-phone.jpg` and
  `history-recovery-confirmed-phone.jpg`. Synthetic review/confirmation keeps the $840 balance
  and existing entries unchanged; no real tenant account was repaired automatically.

The checkpoint screenshots verify financial states/navigation rather than the remaining form redesign.
One final text-only refinement changes the statement count from “months and payments” to “statement
entries”; captures taken immediately before that refinement retain the old count label.

**Not uploaded:** the authenticated browser's Upload file button and actual file input both failed to
open a file chooser. The API credential lacks attachment creation scope. No clipboard was read or
replaced, credentials were not broadened, and no alternate public asset service was introduced.
These are local deliverables; there are no working Outline image/download links for the new assets
yet. This limitation is separate from publication of the audit text and ecosystem synchronization.

Manual upload through a functioning authorized editor is the next publication step. Retain this
gallery and original filenames, append synthetic files only, then record attachment IDs/source hashes
and verify previews/downloads before claiming asset publication complete. Do not replace owner images.

## Reproduction

Use the bundled document Python runtime, which provides reportlab, to run `build_examples.py`.
Render each resulting PDF with `pdftoppm -scale-to 1300 -png`; retain both color and grayscale outputs.
The application environment gains no dependency. The builder uses the existing project diagram skill.

Evidence: audit characterization/document tests passed; the isolated starting-credit case records a
$200 credit as a cleared Payment and includes $200 in this month's payment metric. This is a
documented legacy classification risk, not an approved change to calculations or historical data.

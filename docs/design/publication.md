# Design publication and reproducibility

## Separation

`docs/design/` owns authored sources and exported evidence. The Outline **Design** collection is
a scoped review copy, not a replacement for RHP Engineering. The existing global engineering
sync remains unchanged; it may also mirror design markdown as engineering source records.
Only Design documents and assets are sent by the dedicated publisher. No ecosystem files change.

`tools/publish_design.py` supports dry run, apply and read-back verification. It uses the existing
Outline credential supplied through the environment; it never creates keys, prints tokens or
changes permissions. Source markers reconcile stable document IDs. It never deletes documents
or attachments. The existing token cannot create attachments: galleries are uploaded through
the normal authenticated Outline editor, without expanding the key's scope. Check existing
gallery contents before uploading again, and retain the same gallery document for revisions.
`tools/verify_design_uploads.py` reads only the four Design galleries' local attachment metadata
and hashes their stored files, because the scoped API token cannot list attachments. It makes
no service writes. `--record` writes a non-secret manifest of source hashes and attachment IDs
into this checkout. The publisher uses it to order pages, add captions and accessible image
descriptions, and reference only the current verified versions. Previous file revisions are
retained, not deleted. Run this verifier again after changing or re-uploading an artifact.
The index links to Design copies rather than broken repository-relative URLs. Owner-supplied
references are indexed in `references.json` and retained in their original gallery. Publication
records canonical text hashes and refuses to overwrite later human edits: feedback must be read
and reconciled into the source first. Unknown gallery attachments also stop an update rather
than being silently removed.

## Build

Use the bundled document Python runtime, which supplies reportlab. No RHP dependency is added.
Run `docs/design/build_study.py` to generate scene-book JSON, vector SVG and color/grayscale PDF
books. PNG previews are rendered with Poppler. The script uses the project diagram skill renderer.
Review all pages before publication; do not assume generated text fits merely because it rendered.

Each concept has eight pages: staff queue, request detail, tenant maintenance, lease account,
in desktop and phone treatments. Navigation and workflow are separate single-page books.
Phone layouts are printed at readable scale on Letter rather than treating 390 device pixels as
390 print points. The books are wireframes, not clickable or accessibility-certified applications.

## Acceptance

- Color and grayscale exports inspected for overlap, clipping, readable type and clear labels.
- All examples synthetic; no private portfolio screenshots or real financial records uploaded.
- Outline images render in the authenticated browser; stored attachments are checked against source files.
- Repeated publishing creates no duplicate Design documents or unchanged assets.
- Engineering sync, Plane mirror and `make -C ecosystem verify` remain independent and green.
- Missing attachment scope is reported, never fixed by silently broadening credentials.

## Current evidence

All 26 color pages and their grayscale counterparts were rendered and visually reviewed.
The review corrected a duplicated queue, an incorrect ledger navigation context and a print/SVG
dash-state inconsistency. The project skill validator passed. The dedicated Design publisher's
read-back check reports no source drift; its separate upload verifier checks all 45 published
files against source SHA-256 hashes. The owner additionally supplied the Rentler reference in
Outline; it was visually reviewed and retained separately, not counted as a generated artifact.
The second Plane screenshot remains an access limitation. No real tenant screenshots were published.
Automated browser PDF-download attempts timed out; the download links are present, and all stored
generated files match their source hashes, but a completed browser download was not verified.

The isolated Operations Desk prototype adds a ninth scoped source record, `prototype.md`, and six
synthetic screen captures. The upload verifier now checks the four existing galleries plus this
specific prototype document: 51 matching files in total. `publish_design.py --only` updates named
source records without touching galleries or unrelated owner edits, and preserves the rest of the
publication manifest. The prototype guide records screen-review evidence and outstanding manual
zoom/JavaScript-disabled browser checks. Its live screen design is not governed by print rules.

The later owner feedback consolidates the Properties overview and record browser into one workspace
with independently retained disclosures. Review material now lives on the Interactive Prototype page;
the separate Revision 2 page is only a stable pointer, with its original source archived locally.
Four additional synthetic JPEG captures are pasted through the normal Outline editor, with the
clipboard restored afterward. The upload verifier matches generic clipboard filenames by exact
SHA-256 bytes within the explicitly approved review documents; it does not adopt owner reference
screenshots or expand service credentials. The new total is 55 source-matched uploads.

The subsequent navigation cleanup adds one synthetic capture, bringing the total to 56. Earlier
captures are retained and labeled as preceding that cleanup; no owner attachment was replaced.

"""Scoped Design sync must not discard the owner's migration feedback."""

import pytest

from tools.publish_design import preserve_migration_notes, text_hash

MARKER = "Source record: `docs/design/implementation.md`"


def test_appended_owner_notes_are_retained_without_replacing_authored_source():
    old = "# Migration\nOld authored progress\n\n" + MARKER
    appendix = (
        "Austin Notes:\nKeep this review.\n![Example](/api/attachments.redirect?id=synthetic)"
    )
    doc = {"text": old.replace(MARKER, appendix + "\n\n" + MARKER)}
    updated = "# Migration\nNew authored progress\n\n" + MARKER
    merged, preserved = preserve_migration_notes(
        updated, doc, {"published_text_sha256": text_hash(old)}, "implementation.md"
    )
    assert preserved
    assert appendix in merged
    assert "New authored progress" in merged
    assert "Old authored progress" not in merged


def test_unreconciled_changes_outside_appendix_still_block_publication():
    doc = {"text": "Changed source\nAustin Notes:\nFeedback\n\n" + MARKER}
    with pytest.raises(RuntimeError, match="authored content changed"):
        preserve_migration_notes(
            "New\n" + MARKER,
            doc,
            {"published_text_sha256": text_hash("Original\n" + MARKER)},
            "implementation.md",
        )


def test_other_design_documents_do_not_get_an_owner_protection_bypass():
    text = "New source"
    assert preserve_migration_notes(
        text, {"text": "Old\nAustin Notes:\nFeedback"}, {}, "prototype.md"
    ) == (text, False)

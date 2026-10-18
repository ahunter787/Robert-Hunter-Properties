"""Design publication and exported scene invariants; no application dependency added."""

import json
from pathlib import Path

import pytest

from tools.publish_design import canonical, protect_owner_edits, text_hash

ROOT = Path(__file__).resolve().parents[1]


def test_outline_normalization_does_not_create_publication_drift():
    assert canonical("Paragraph wraps\nonto two lines.\n\n- Item") == canonical(
        "Paragraph wraps onto two lines.\n\n* Item\n"
    )
    assert canonical("| Key | Value |\n| --- | --- |\n| One | Two |") == canonical(
        "|Key|Value|\n|----|----|\n|One|Two|"
    )
    assert canonical("## Due now: $0.00") != canonical("## Due now: $840.00")
    assert canonical("[Link](https://example.com/a)") != canonical("[Link](https://example.com/b)")


def test_owner_feedback_is_not_overwritten_by_publication():
    prior = {"published_text_sha256": text_hash("Existing source\n\n- Item")}
    protect_owner_edits({"title": "Design", "text": "Existing source\n\n* Item"}, prior)
    with pytest.raises(RuntimeError, match="Owner edits need reconciliation"):
        protect_owner_edits({"title": "Design", "text": "Existing source\n\nOwner feedback"}, prior)


def test_concept_books_cover_identical_tasks_at_both_sizes():
    sources = ROOT / "docs/design/sources"
    for name in ("portfolio-workspace", "operations-desk", "calm-portal"):
        book = json.loads((sources / f"{name}.json").read_text())
        assert len(book["pages"]) == 8
        for pair, title in enumerate(
            ("Staff queue", "Request detail", "Tenant maintenance", "Lease ledger")
        ):
            for offset, size in ((0, (792, 612)), (1, (612, 792))):
                page = book["pages"][pair * 2 + offset]
                assert page["title"].endswith(title)
                assert (page["width"], page["height"]) == size
                for element in page["elements"]:
                    assert 0 <= element["x"] <= size[0]
                    assert 0 <= element["y"] <= size[1]
                    if element["type"] == "text":
                        assert element["size"] >= 9


def test_each_design_book_has_vector_preview_and_print_exports():
    base = ROOT / "docs/design/artifacts"
    for name in (
        "portfolio-workspace",
        "operations-desk",
        "calm-portal",
        "navigation",
        "maintenance-workflow",
    ):
        for mode in ("", "-grayscale"):
            assert (base / f"{name}{mode}.pdf").read_bytes().startswith(b"%PDF-")
            assert (base / f"{name}{mode}-01.svg").exists()
            assert (base / f"{name}{mode}-1.png").exists()

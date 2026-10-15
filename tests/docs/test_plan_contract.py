"""The plan's own contract: the documents the tooling parses must stay parseable.

`docs/roadmap.md`, `docs/extensions.md` and the phase records are read by scripts outside this
repository: the roadmap's phase table and the register become Plane work items, and the records'
open questions are meant to become work items too (ADR-018). A document that drifts out of shape
does not fail loudly there - the sync simply mirrors less, or skips a row - so the shape is asserted
here, where a change to it fails a test instead.

These tests read files and nothing else; no database.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
ROADMAP = DOCS / "roadmap.md"
REGISTER = DOCS / "extensions.md"
PHASES = DOCS / "phases"

#: The exact headers the sync scripts look for. Changing one is a tooling change.
ROADMAP_HEADER = "| Phase | Scope | Status |"
REGISTER_HEADER = "| # | What it is | Kind | Status |"
QUESTIONS_HEADER = "| # | Question | My recommendation | Your answer |"

#: The words the mirror maps to Plane state groups. Anything else becomes "backlog" silently.
STATUS_WORDS = (
    "Complete",
    "Built",
    "In main",
    "Next",
    "Building",
    "Not started",
    "Withdrawn",
    "Blocked",
)

#: Every record carries the same sections, so a reader and a parser both know where things are.
SECTIONS = (
    "## Scope as specified",
    "## What exists today",
    "## Decisions that govern it",
    "## Extensions filed under this phase",
    "## Acceptance criteria and evidence",
    "## Deliberately not here",
    "## Known gaps and defects",
    "## Open questions for the owner",
    "## How to verify it",
)

#: The register's id cell. Both forms are accepted while the phase-scoped rename lands.
EXTENSION_ID = re.compile(r"^(?:E[0-9]+|P[0-9]{1,2}-E[0-9]+)$")
QUESTION_ID = re.compile(r"^P([0-9]{1,2})-Q([0-9]+)$")


def table_rows(path: Path, header: str) -> list[list[str]]:
    """The rows of the first table under ``header``, split into their cells.

    Stops at the first line that is not a row, which is what the sync's awk does: the documents
    hold several tables and the one after this must not be mistaken for it.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index(header)
    rows: list[list[str]] = []
    for line in lines[start + 1 :]:
        if not line.startswith("|"):
            break
        if set(line) <= set("|-: "):  # the |---| separator
            continue
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def phase_records() -> dict[int, Path]:
    found = {}
    for path in sorted(PHASES.glob("phase-*.md")):
        found[int(path.name.split("-")[1])] = path
    return found


@pytest.fixture(scope="module")
def roadmap_rows() -> list[list[str]]:
    return table_rows(ROADMAP, ROADMAP_HEADER)


def test_the_roadmap_table_keeps_the_header_the_sync_looks_for():
    assert ROADMAP_HEADER in ROADMAP.read_text(encoding="utf-8")


def test_every_phase_row_has_three_cells(roadmap_rows):
    """A stray `|` inside a cell would split it and shift every column after it."""
    assert roadmap_rows, "the phase table is empty"
    for row in roadmap_rows:
        assert len(row) == 3, f"row is not three cells: {row}"


def test_every_phase_is_listed_once_with_a_known_status(roadmap_rows):
    phases = [int(row[0]) for row in roadmap_rows]
    assert phases == list(range(13)), f"phases listed: {phases}"
    for row in roadmap_rows:
        status = row[2].replace("*", "").replace("`", "")
        assert status.startswith(STATUS_WORDS), (
            f"phase {row[0]} has status {status!r}, which the mirror would map to backlog"
        )


def test_every_phase_has_a_record_with_matching_status(roadmap_rows):
    records = phase_records()
    assert sorted(records) == list(range(13)), f"records found for phases {sorted(records)}"

    by_phase = {int(row[0]): row[2].replace("*", "").replace("`", "") for row in roadmap_rows}
    for phase, path in records.items():
        text = path.read_text(encoding="utf-8")
        assert f"**Status:** {by_phase[phase]}" in text or by_phase[phase].startswith(
            status_of(text)
        ), f"{path.name} says {status_of(text)!r}, the roadmap says {by_phase[phase]!r}"


def status_of(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("**Status:**"):
            return line.removeprefix("**Status:**").strip()
    raise AssertionError("no **Status:** line")


def test_every_record_keeps_the_same_sections():
    for path in phase_records().values():
        text = path.read_text(encoding="utf-8")
        for section in SECTIONS:
            assert section in text, f"{path.name} is missing {section!r}"
        for line in ("**Status:**", "**Milestone:**", "**Specification:**"):
            assert line in text, f"{path.name} is missing {line!r}"


def test_the_register_keeps_the_header_the_sync_looks_for():
    assert REGISTER_HEADER in REGISTER.read_text(encoding="utf-8")


def test_every_register_row_is_an_id_the_sync_recognises():
    rows = table_rows(REGISTER, REGISTER_HEADER)
    assert rows, "the register is empty"
    for row in rows:
        assert len(row) == 4, f"row is not four cells: {row}"
        assert EXTENSION_ID.match(row[0].replace("*", "")), (
            f"{row[0]!r} is not an id the mirror parses - the row would be skipped silently"
        )


def test_question_ids_are_well_formed_unique_and_filed_under_their_phase():
    seen: dict[str, str] = {}
    for phase, path in phase_records().items():
        rows = table_rows(path, QUESTIONS_HEADER)
        for row in rows:
            assert len(row) == 4, f"{path.name}: question row is not four cells: {row}"
            question_id = row[0].replace("*", "")
            if question_id in {"(none)", "—", "-"}:
                continue
            match = QUESTION_ID.match(question_id)
            assert match, f"{path.name}: {question_id!r} is not a question id like P4-Q1"
            assert int(match.group(1)) == phase, (
                f"{path.name}: {question_id} belongs to another phase"
            )
            assert question_id not in seen, (
                f"{question_id} appears in {seen[question_id]} and {path.name}"
            )
            seen[question_id] = path.name
            assert row[2], f"{path.name}: {question_id} has no recommendation"
    assert seen, "no open questions are recorded anywhere - that is unlikely, and a bug if not"


def test_the_records_index_lists_every_phase():
    index = (PHASES / "README.md").read_text(encoding="utf-8")
    for path in phase_records().values():
        assert path.name in index, f"{path.name} is not listed in the records index"

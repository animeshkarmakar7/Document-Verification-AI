"""Unit tests for ClauseSegmenter.

Coverage:
- Numbered sections (1.  1.1  1.1.1)
- Lettered sub-clauses ((a)  A.)
- Named sections (Section, Clause, Article, Part)
- Block headings (Schedule, Exhibit, Annex, Appendix)
- Narrative markers (Recitals, Whereas, Definitions, Background, Preamble)
- ALL-CAPS heading detection
- Page-break (\f) stripping
- Minimum clause length guard
- Source span accuracy
- Empty / whitespace-only input
"""

import pytest
from app.services.clause_segmenter import ClauseSegmenter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def segment(text: str) -> list:
    return ClauseSegmenter().segment(document_id="doc-1", text=text)


# ---------------------------------------------------------------------------
# Numbered boundaries
# ---------------------------------------------------------------------------


def test_numbered_single_level():
    text = (
        "1. Rent\n"
        "The tenant shall pay rent monthly.\n\n"
        "2. Termination\n"
        "Either party may terminate with notice."
    )
    clauses = segment(text)
    assert len(clauses) == 2
    assert clauses[0].heading == "1. Rent"
    assert clauses[1].heading == "2. Termination"


def test_numbered_multi_level():
    text = (
        "1. Definitions\n"
        "Words used herein.\n\n"
        "1.1 Agreement\n"
        "Means this contract.\n\n"
        "1.1.1 Effective Date\n"
        "The date of signing."
    )
    clauses = segment(text)
    assert len(clauses) == 3
    assert clauses[0].heading == "1. Definitions"
    assert clauses[1].heading == "1.1 Agreement"
    assert clauses[2].heading == "1.1.1 Effective Date"


def test_lettered_parenthetical():
    text = (
        "(a) Notice Period\n"
        "Notice must be in writing.\n\n"
        "(b) Delivery\n"
        "Notice is effective on receipt."
    )
    clauses = segment(text)
    assert len(clauses) == 2
    assert clauses[0].heading == "(a) Notice Period"


def test_lettered_dot():
    text = (
        "A. Definitions\n"
        "As used herein.\n\n"
        "B. Term\n"
        "The agreement lasts one year."
    )
    clauses = segment(text)
    assert len(clauses) == 2
    assert clauses[0].heading == "A. Definitions"


# ---------------------------------------------------------------------------
# Named sections
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "keyword,label",
    [
        ("Section 1", "Section 1"),
        ("Clause 3", "Clause 3"),
        ("Article III", "Article III"),
        ("Part IV", "Part IV"),
    ],
)
def test_named_section_boundaries(keyword, label):
    text = (
        f"{keyword} Introductory Clause\n"
        "This is the body text.\n\n"
        "2. Next Section\n"
        "More body text here."
    )
    clauses = segment(text)
    assert len(clauses) == 2
    assert clauses[0].heading is not None
    assert clauses[0].heading.startswith(keyword)


# ---------------------------------------------------------------------------
# Block headings: Schedule / Exhibit / Annex / Appendix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "keyword",
    ["Schedule A", "Exhibit 1", "Annex I", "Appendix B"],
)
def test_block_heading_boundaries(keyword):
    text = (
        "1. Main Terms\n"
        "The main agreement body.\n\n"
        f"{keyword}\n"
        "This schedule describes the fee table."
    )
    clauses = segment(text)
    assert len(clauses) == 2
    assert clauses[1].heading is not None
    assert clauses[1].heading.startswith(keyword)


# ---------------------------------------------------------------------------
# Narrative markers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "marker",
    [
        "RECITALS",
        "WHEREAS",
        "DEFINITIONS",
        "BACKGROUND",
        "PREAMBLE",
    ],
)
def test_narrative_marker_boundaries(marker):
    text = (
        f"{marker}\n"
        "This section introduces the agreement.\n\n"
        "1. Main Terms\n"
        "The main agreement body."
    )
    clauses = segment(text)
    assert len(clauses) == 2, f"Expected 2 clauses for marker '{marker}'"
    assert clauses[0].heading == marker


# ---------------------------------------------------------------------------
# ALL-CAPS heading detection (no boundary pattern needed)
# ---------------------------------------------------------------------------


def test_all_caps_heading_detected():
    text = (
        "LIMITATION OF LIABILITY\n"
        "In no event shall either party be liable.\n\n"
        "1. Governing Law\n"
        "This agreement is governed by the laws of India."
    )
    clauses = segment(text)
    assert clauses[0].heading == "LIMITATION OF LIABILITY"


# ---------------------------------------------------------------------------
# Page-break artefact stripping
# ---------------------------------------------------------------------------


def test_form_feed_stripped_before_segmentation():
    text = (
        "1. Rent\n"
        "The tenant shall pay rent monthly.\f"
        "2. Termination\n"
        "Either party may terminate with notice."
    )
    clauses = segment(text)
    # \f is replaced with \n\n so both sections are still discovered
    assert len(clauses) >= 2


# ---------------------------------------------------------------------------
# Minimum clause length guard
# ---------------------------------------------------------------------------


def test_minimum_length_guard_skips_near_empty_paragraphs():
    text = (
        "1. Rent\n"
        "The tenant shall pay monthly.\n\n"
        "  \n\n"  # whitespace-only paragraph — must be skipped
        "2. Termination\n"
        "Either party may terminate."
    )
    clauses = segment(text)
    # Whitespace paragraph must not create a spurious clause
    assert all(len(c.text.strip()) >= 3 for c in clauses)


# ---------------------------------------------------------------------------
# Source span accuracy
# ---------------------------------------------------------------------------


def test_source_spans_reference_original_text():
    text = (
        "LEASE AGREEMENT\n\n"
        "1. Rent\n"
        "The tenant shall pay rent monthly.\n\n"
        "2. Termination\n"
        "Either party may terminate with notice.\n\n"
        "(a) Notice Period\n"
        "Notice must be in writing."
    )
    clauses = segment(text)
    for clause in clauses:
        extracted = text[clause.source_start : clause.source_end]
        assert extracted == clause.text, (
            f"Source span mismatch for clause {clause.clause_id!r}"
        )


# ---------------------------------------------------------------------------
# Stable clause_id
# ---------------------------------------------------------------------------


def test_clause_ids_are_stable_and_sequential():
    text = (
        "1. Rent\nPay monthly.\n\n"
        "2. Termination\nEither party may terminate."
    )
    clauses = segment(text)
    assert clauses[0].clause_id == "doc-1-clause-0001"
    assert clauses[1].clause_id == "doc-1-clause-0002"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_text_returns_no_clauses():
    assert segment("   \n\n   ") == []


def test_whitespace_only_text_returns_no_clauses():
    assert segment("\t\n   \r\n") == []


def test_single_paragraph_no_boundary_returns_one_clause():
    text = "This is an agreement between the parties."
    clauses = segment(text)
    assert len(clauses) == 1
    assert clauses[0].order_index == 1
    # No structural marker → heading should be None
    assert clauses[0].heading is None

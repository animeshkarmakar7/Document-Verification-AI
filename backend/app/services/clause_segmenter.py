import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Boundary detection
# ---------------------------------------------------------------------------
# Matches the first line of a paragraph when it starts a new legal clause.
# Supported patterns (case-insensitive):
#   Numbered:        1.  1.2  1.2.3  (i)  (A)  A.  A)
#   Named sections:  Section 1 / Section I / Clause 2 / Article III / Part 1
#   Block headings:  Schedule A / Exhibit 1 / Annex I
#   Narrative marks: RECITALS  WHEREAS  DEFINITIONS  BACKGROUND  PREAMBLE
# ---------------------------------------------------------------------------
_NUMBERED = r"(\d+(\.\d+)*[\.\)])"
_LETTERED_PAREN = r"(\([a-zA-Z0-9]+\))"
_LETTERED_DOT = r"([A-Z][\.\)])"
_NAMED_SECTION = (
    r"((?:section|clause|article|part)\s+[A-Z0-9IVXLC]+)"
)
_BLOCK_HEADING = (
    r"((?:schedule|exhibit|annex|appendix)\s+[A-Z0-9IVXLC]+)"
)
_NARRATIVE = (
    r"(recitals|whereas|definitions|background|preamble|"
    r"witnesses|witnesseth|now[\s,]+therefore)"
)

BOUNDARY_PATTERN = re.compile(
    rf"^({_NUMBERED}|{_LETTERED_PAREN}|{_LETTERED_DOT}"
    rf"|{_NAMED_SECTION}|{_BLOCK_HEADING}|{_NARRATIVE})"
    r"[\s:,\-–—]*",
    re.IGNORECASE,
)

# Lines that look like page headers/footers inserted by the PDF extractor:
# short lines (<= 80 chars) that appear alone between double newlines.
_PAGE_BREAK = re.compile(r"\f")
_LONE_SHORT_LINE = re.compile(
    r"(?<=\n\n)([^\n]{1,80})\n\n"
    r"(?=(?:Page\s+\d+|\d+\s+of\s+\d+|[-–—]{3,}|\Z))",
    re.IGNORECASE,
)

# Minimum non-whitespace characters for a paragraph to be kept.
_MIN_CONTENT_CHARS = 3


@dataclass(frozen=True)
class SegmentedClause:
    clause_id: str
    order_index: int
    heading: str | None
    text: str
    source_start: int
    source_end: int


@dataclass(frozen=True)
class Paragraph:
    text: str
    start: int
    end: int


class ClauseSegmenter:

    def segment(
        self,
        document_id: str,
        text: str,
    ) -> list[SegmentedClause]:

        cleaned = self._clean_text(text)
        paragraphs = self._paragraphs(cleaned)

        if not paragraphs:
            return []

        groups: list[list[Paragraph]] = []

        for paragraph in paragraphs:
            if self._is_boundary(paragraph.text) or not groups:
                groups.append([paragraph])
            else:
                groups[-1].append(paragraph)

        return [
            self._build_clause(
                document_id=document_id,
                order_index=index,
                paragraphs=group,
            )
            for index, group in enumerate(groups, start=1)
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clean_text(self, text: str) -> str:
        """Remove PDF page-break artefacts before segmenting."""
        # Strip form-feed characters
        text = _PAGE_BREAK.sub("\n\n", text)
        return text

    def _paragraphs(
        self,
        text: str,
    ) -> list[Paragraph]:

        paragraphs = []

        for match in re.finditer(
            r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", text, re.DOTALL
        ):
            paragraph_text = match.group(0).strip()

            if not paragraph_text:
                continue

            # Skip paragraphs that are effectively empty after stripping.
            if (
                len(paragraph_text.replace(" ", "").replace("\n", ""))
                < _MIN_CONTENT_CHARS
            ):
                continue

            leading_offset = len(match.group(0)) - len(
                match.group(0).lstrip()
            )
            trailing_offset = len(match.group(0).rstrip())

            paragraphs.append(
                Paragraph(
                    text=paragraph_text,
                    start=match.start() + leading_offset,
                    end=match.start() + trailing_offset,
                )
            )

        return paragraphs

    def _is_boundary(
        self,
        paragraph: str,
    ) -> bool:

        first_line = paragraph.splitlines()[0].strip()
        return bool(BOUNDARY_PATTERN.match(first_line))

    def _build_clause(
        self,
        document_id: str,
        order_index: int,
        paragraphs: list[Paragraph],
    ) -> SegmentedClause:

        source_start = paragraphs[0].start
        source_end = paragraphs[-1].end
        clause_text = "\n\n".join(
            paragraph.text for paragraph in paragraphs
        )
        first_line = paragraphs[0].text.splitlines()[0].strip()
        heading = self._heading(first_line)

        return SegmentedClause(
            clause_id=f"{document_id}-clause-{order_index:04d}",
            order_index=order_index,
            heading=heading,
            text=clause_text,
            source_start=source_start,
            source_end=source_end,
        )

    def _heading(
        self,
        first_line: str,
    ) -> str | None:
        """
        Return ``first_line`` as the clause heading when it clearly
        represents a structural title, otherwise return ``None``.

        A line qualifies as a heading when it:
        - Matches a structural boundary pattern (numbered, named, narrative),
        - OR is written entirely in UPPER CASE (common for section titles).

        The 255-character cap aligns with the ``heading`` DB column width.
        """
        if len(first_line) > 255:
            return None

        if BOUNDARY_PATTERN.match(first_line):
            return first_line

        if first_line.isupper() and len(first_line.split()) <= 15:
            return first_line

        return None

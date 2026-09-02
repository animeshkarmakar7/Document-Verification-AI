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

# Minimum non-whitespace characters for a paragraph to be kept.
_MIN_CONTENT_CHARS = 3

# Maximum characters in a single clause before it is force-split.
# Prevents LLM context overflow when the segmenter cannot find structural
# boundaries (e.g., academic texts, long running prose).
_MAX_CLAUSE_CHARS = 3000

# Split paragraphs on one or more blank lines (lines containing only
# whitespace).  This correctly handles trailing-space lines produced by
# pypdf (`"text \n\n"`) which the previous `\S…\S` regex could not
# match across, causing the whole document to become one giant paragraph.
_BLANK_LINE_SEP = re.compile(r"\n[ \t]*\n")


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
            current_len = (
                sum(len(p.text) for p in groups[-1]) if groups else 0
            )
            # Start a new group when:
            #   - There are no groups yet, OR
            #   - The paragraph starts a structural boundary, OR
            #   - The current group has grown beyond the size cap.
            if (
                not groups
                or self._is_boundary(paragraph.text)
                or current_len >= _MAX_CLAUSE_CHARS
            ):
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
        """Normalise line endings and remove PDF page-break artefacts."""
        # Normalise Windows/old-Mac line endings to Unix
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Replace form-feed page-break characters with a blank line
        text = _PAGE_BREAK.sub("\n\n", text)
        return text

    def _paragraphs(
        self,
        text: str,
    ) -> list[Paragraph]:
        """
        Split the document text into paragraphs on blank-line boundaries.

        **Why re.split instead of re.finditer?**

        pypdf appends a trailing space to every line it extracts
        (``"Some text \\n"``).  The previous regex ``\\S(?:.*?\\S)?`` required
        the match to both *start* and *end* on a non-whitespace character.
        When every line ends with ``" \\n"``, the trailing space prevents the
        match from reaching the ``\\n\\n`` separator, so the entire document
        was returned as a single match — one giant "paragraph" producing one
        giant clause that overflows the LLM context.

        ``re.split`` on blank lines is immune to trailing spaces: it looks
        for the separator pattern (``\\n[ \\t]*\\n``) regardless of what
        surrounds it.
        """
        paragraphs: list[Paragraph] = []
        offset = 0

        for chunk in _BLANK_LINE_SEP.split(text):
            chunk_stripped = chunk.strip()

            # Advance the running offset to find where this chunk sits in
            # the original cleaned text.
            chunk_start = text.find(chunk, offset)
            if chunk_start == -1:
                # Fallback: just keep advancing linearly.
                chunk_start = offset
            chunk_end = chunk_start + len(chunk)
            offset = chunk_end

            if not chunk_stripped:
                continue

            # Skip effectively-empty chunks (fewer than 3 non-whitespace chars).
            if (
                len(chunk_stripped.replace(" ", "").replace("\n", ""))
                < _MIN_CONTENT_CHARS
            ):
                continue

            # Compute tight start/end that exclude leading/trailing whitespace.
            leading = len(chunk) - len(chunk.lstrip())
            trailing = len(chunk.rstrip())

            paragraphs.append(
                Paragraph(
                    text=chunk_stripped,
                    start=chunk_start + leading,
                    end=chunk_start + trailing,
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

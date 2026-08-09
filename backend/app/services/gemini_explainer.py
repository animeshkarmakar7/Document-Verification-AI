import json
import logging
import math
import re
from dataclasses import dataclass

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config.settings import settings

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.65


class ExplanationError(Exception):
    pass


class ClauseExplanationItem(BaseModel):
    clause_id: str
    plain_summary: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_grounded: bool


class ClauseExplanationBatchOutput(BaseModel):
    explanations: list[ClauseExplanationItem]


@dataclass
class InputClauseToExplain:
    clause_id: str
    category: str
    text: str
    source_start: int
    source_end: int


def _flesch_kincaid_grade(text: str) -> float:
    sentences = max(len(re.findall(r"[.!?]+", text)), 1)
    words_list = re.findall(r"\b\w+\b", text)
    words = max(len(words_list), 1)
    syllables = sum(_count_syllables(w) for w in words_list)
    return 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59


def _count_syllables(word: str) -> int:
    word = word.lower()
    count = len(re.findall(r"[aeiou]+", word))
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


class GeminiExplainer:

    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    def explain_batch(
        self, clauses: list[InputClauseToExplain]
    ) -> list[ClauseExplanationItem]:
        if not clauses:
            return []

        if not self.client:
            return [self._explain_fallback(c) for c in clauses]

        prompt = (
            "You are a legal document expert who writes plain-English explanations for non-lawyers.\n"
            "For each clause below, write a 2-3 sentence plain summary that:\n"
            "- Uses no legal jargon\n"
            "- Explains what the clause means for the user in practical terms\n"
            "- Is strictly grounded in the clause text (do not add facts not in the text)\n"
            "- Sets confidence to < 0.65 and is_grounded to false if the clause is too vague to explain reliably\n\n"
            "Return JSON with 'explanations' array matching the schema.\n\n"
            "Clauses:\n"
        )
        for c in clauses:
            prompt += f"--- Clause ID: {c.clause_id} | Category: {c.category} ---\n{c.text}\n\n"

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ClauseExplanationBatchOutput,
                    temperature=0.2,
                ),
            )
            raw = response.text or "{}"
            parsed = json.loads(raw)
            batch = ClauseExplanationBatchOutput(**parsed)

            result_map = {item.clause_id: item for item in batch.explanations}
            results = []
            for c in clauses:
                if c.clause_id in result_map:
                    results.append(result_map[c.clause_id])
                else:
                    results.append(self._explain_fallback(c))
            return results
        except Exception as e:
            logger.warning(f"Gemini explanation failed, using fallback: {e}")
            return [self._explain_fallback(c) for c in clauses]

    def _explain_fallback(self, clause: InputClauseToExplain) -> ClauseExplanationItem:
        word_count = len(clause.text.split())
        if word_count < 10:
            return ClauseExplanationItem(
                clause_id=clause.clause_id,
                plain_summary="This clause is too brief to summarize reliably. Please consult a professional.",
                confidence=0.3,
                is_grounded=False,
            )
        summary = (
            f"This clause covers {clause.category.replace('_', ' ').lower()} terms. "
            f"It establishes obligations or rights related to this area of the agreement. "
            f"Review this section carefully with a legal professional to understand your specific obligations."
        )
        return ClauseExplanationItem(
            clause_id=clause.clause_id,
            plain_summary=summary,
            confidence=0.55,
            is_grounded=False,
        )

    def compute_readability(self, text: str) -> float:
        return round(_flesch_kincaid_grade(text), 2)

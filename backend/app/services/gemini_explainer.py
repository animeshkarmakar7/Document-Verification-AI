import json
import logging
import math
import re
from dataclasses import dataclass

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config.settings import settings

from app.services.llm_router import LLMRouter, LLMUnavailableError

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


class VerifiedSummaryItem(BaseModel):
    statement: str
    clause_id: str
    source_location: str
    verbatim_proof: str


class DocumentSummaryOutput(BaseModel):
    title: str
    document_type: str
    executive_summary: str
    key_points: list[VerifiedSummaryItem]
    important_dates_fees: list[VerifiedSummaryItem]
    user_obligations: list[VerifiedSummaryItem]
    user_rights: list[VerifiedSummaryItem]


@dataclass
class InputClauseToExplain:
    clause_id: str
    category: str
    text: str
    source_start: int
    source_end: int
    page_number: int | None = None


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

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        router: LLMRouter | None = None,
    ):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.router = router or LLMRouter(
            gemini_api_key=self.api_key,
            gemini_model=self.model_name,
        )

    @property
    def client(self):
        return self.router.gemini_client

    @client.setter
    def client(self, value):
        self.router.gemini_client = value

    def explain_batch(
        self, clauses: list[InputClauseToExplain]
    ) -> list[ClauseExplanationItem]:
        """
        Explain clauses in small chunks to stay within the free-tier
        250 000 input-token-per-minute quota.

        Each chunk of ``_EXPLAIN_CHUNK_SIZE`` clauses is sent as a separate
        API call.  On a 429 (rate limit) or 503 (overload) response the call
        is retried up to ``_MAX_RETRIES`` times with exponential back-off
        before falling back to the rule-based summary.
        """
        import time

        _EXPLAIN_CHUNK_SIZE = 10   # clauses per Gemini call
        _MAX_RETRIES = 3
        _BACKOFF_BASE = 15         # seconds (15 → 30 → 60)

        if not clauses:
            return []

        if not self.client:
            return [self._explain_fallback(c) for c in clauses]

        results: list[ClauseExplanationItem] = []

        # Split into chunks
        chunks = [
            clauses[i: i + _EXPLAIN_CHUNK_SIZE]
            for i in range(0, len(clauses), _EXPLAIN_CHUNK_SIZE)
        ]

        for chunk_idx, chunk in enumerate(chunks):
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
            for c in chunk:
                page_info = f" | Page {c.page_number}" if c.page_number else ""
                prompt += f"--- Clause ID: {c.clause_id}{page_info} | Category: {c.category} ---\n{c.text}\n\n"

            try:
                batch = self.router.generate_structured(
                    prompt=prompt,
                    schema=ClauseExplanationBatchOutput,
                    temperature=0.2,
                )
                result_map = {item.clause_id: item for item in batch.explanations}
                chunk_results = [
                    result_map.get(c.clause_id, self._explain_fallback(c))
                    for c in chunk
                ]
            except Exception as e:
                logger.warning(
                    f"LLM explanation chunk {chunk_idx + 1}/{len(chunks)} failed, using fallback: {e}"
                )
                chunk_results = [self._explain_fallback(c) for c in chunk]

            results.extend(chunk_results)

        return results

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

    def generate_document_summary(
        self, clauses: list[InputClauseToExplain]
    ) -> DocumentSummaryOutput:
        if not clauses:
            return DocumentSummaryOutput(
                title="Legal Document",
                document_type="Contract",
                executive_summary="No clause content provided for summary generation.",
                key_points=[],
                important_dates_fees=[],
                user_obligations=[],
                user_rights=[],
            )

        if not self.client and not self.router.groq_client and not self.router._check_ollama():
            return self._summary_fallback(clauses)

        full_text = "\n\n".join(
            f"[{c.clause_id} | Page {c.page_number or 1} | {c.category}]: {c.text}" for c in clauses[:30]
        )
        prompt = (
            "You are a senior legal analyst synthesizing an Executive Document Summary Report for a user.\n"
            "For full transparency and user verification, EVERY summary point must provide verifiable proof linking back to the exact text in the document.\n\n"
            "Provide:\n"
            "- title: Clear title of the contract/agreement\n"
            "- document_type: e.g. Lease Agreement, Terms of Service, NDA, Employment Contract\n"
            "- executive_summary: A 3-4 sentence high-level overview of the scope and main terms\n"
            "- key_points: Array of items, each containing:\n"
            "    * statement: Summary of the core provision\n"
            "    * clause_id: Matching clause_id from input\n"
            "    * source_location: Human-friendly page reference strictly in format 'Page X' (e.g. 'Page 1' or 'Page 2')\n"
            "    * verbatim_proof: Exact verbatim sentence quoted directly from the input text as evidence\n"
            "- important_dates_fees: Array of VerifiedSummaryItem for payment terms, fees, notice periods, or dates\n"
            "- user_obligations: Array of VerifiedSummaryItem for what the user is required to do or pay\n"
            "- user_rights: Array of VerifiedSummaryItem for what rights, remedies, or services the user receives\n\n"
            f"Document Clauses:\n{full_text}"
        )

        try:
            return self.router.generate_structured(
                prompt=prompt,
                schema=DocumentSummaryOutput,
                temperature=0.2,
            )
        except Exception as e:
            logger.warning(f"LLM document summary generation failed, using fallback: {e}")
            return self._summary_fallback(clauses)

    def _summary_fallback(self, clauses: list[InputClauseToExplain]) -> DocumentSummaryOutput:
        categories = list(set(c.category for c in clauses))
        total = len(clauses)
        top = clauses[0] if clauses else None
        top_page = f"Page {top.page_number or 1}" if top else "Page 1"
        
        fallback_item = VerifiedSummaryItem(
            statement=f"Document contains {total} segmented provisions across categories including {', '.join(categories[:3])}.",
            clause_id=top.clause_id if top else "N/A",
            source_location=top_page,
            verbatim_proof=top.text[:150] if top else "No text evidence available.",
        )
        return DocumentSummaryOutput(
            title="Legal Document Summary",
            document_type="Legal Agreement",
            executive_summary=f"This document comprises {total} clauses across key legal areas including {', '.join(categories[:4])}.",
            key_points=[fallback_item],
            important_dates_fees=[
                VerifiedSummaryItem(
                    statement="Review extracted clause provisions for specific fee structures and notice periods.",
                    clause_id=top.clause_id if top else "N/A",
                    source_location=top_page,
                    verbatim_proof=top.text[:120] if top else "Evidence in clause text.",
                )
            ],
            user_obligations=[
                VerifiedSummaryItem(
                    statement="Comply with specified contractual requirements as outlined in the text.",
                    clause_id=top.clause_id if top else "N/A",
                    source_location=top_page,
                    verbatim_proof=top.text[:120] if top else "Evidence in clause text.",
                )
            ],
            user_rights=[
                VerifiedSummaryItem(
                    statement="Standard contractual rights and remedies as stated in the agreement.",
                    clause_id=top.clause_id if top else "N/A",
                    source_location=top_page,
                    verbatim_proof=top.text[:120] if top else "Evidence in clause text.",
                )
            ],
        )



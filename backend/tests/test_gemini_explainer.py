from unittest.mock import MagicMock
import pytest

from app.services.gemini_explainer import (
    ClauseExplanationItem,
    GeminiExplainer,
    InputClauseToExplain,
)


def test_explain_fallback_short_clause():
    explainer = GeminiExplainer(api_key="")
    explainer.client = None
    clauses = [
        InputClauseToExplain(
            clause_id="doc-1-clause-0001",
            category="TERMINATION_EXIT",
            text="See above.",
            source_start=0,
            source_end=10,
        )
    ]
    results = explainer.explain_batch(clauses)
    assert len(results) == 1
    assert results[0].confidence < 0.65
    assert results[0].is_grounded is False


def test_explain_fallback_normal_clause():
    explainer = GeminiExplainer(api_key="")
    explainer.client = None
    clauses = [
        InputClauseToExplain(
            clause_id="doc-1-clause-0002",
            category="PENALTY_FEES",
            text="The tenant shall pay a late fee of 10% of the monthly rent for any payment received more than five days after the due date.",
            source_start=0,
            source_end=120,
        )
    ]
    results = explainer.explain_batch(clauses)
    assert len(results) == 1
    assert "penalty" in results[0].plain_summary.lower() or "fees" in results[0].plain_summary.lower()


def test_explain_gemini_success():
    explainer = GeminiExplainer(api_key="mock_key")
    explainer.client = MagicMock()

    mock_response = MagicMock()
    mock_response.text = '{"explanations": [{"clause_id": "c1", "plain_summary": "If you pay late, you owe a 10% extra fee.", "confidence": 0.92, "is_grounded": true}]}'
    explainer.client.models.generate_content.return_value = mock_response

    clauses = [
        InputClauseToExplain(
            clause_id="c1",
            category="PENALTY_FEES",
            text="Late payment incurs a 10% surcharge.",
            source_start=0,
            source_end=36,
        )
    ]
    results = explainer.explain_batch(clauses)
    assert len(results) == 1
    assert results[0].clause_id == "c1"
    assert results[0].confidence == 0.92
    assert results[0].is_grounded is True


def test_readability_score_returns_float():
    explainer = GeminiExplainer(api_key="")
    score = explainer.compute_readability(
        "The party of the first part shall indemnify and hold harmless the party of the second part."
    )
    assert isinstance(score, float)
    assert score >= 0


def test_empty_batch_returns_empty():
    explainer = GeminiExplainer(api_key="")
    explainer.client = None
    assert explainer.explain_batch([]) == []

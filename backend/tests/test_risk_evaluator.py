from unittest.mock import MagicMock
import pytest

from app.models.enums import ClauseCategory, RiskFlagType, RiskLevel
from app.services.risk_evaluator import (
    ClauseRiskBatchOutput,
    ClauseRiskItem,
    GeminiRiskEvaluator,
    InputClauseToEvaluate,
)


def test_evaluator_fallback_high_risk():
    evaluator = GeminiRiskEvaluator(api_key="")
    evaluator.client = None
    clauses = [
        InputClauseToEvaluate(
            clause_id="doc-1-clause-0001",
            category=ClauseCategory.TERMINATION_EXIT,
            text="The landlord may terminate this lease at any time in its sole discretion without notice.",
        )
    ]
    results = evaluator.evaluate_batch(clauses)
    assert len(results) == 1
    item = results[0]
    assert item.clause_id == "doc-1-clause-0001"
    assert item.risk_level == RiskLevel.HIGH
    assert item.risk_score >= 0.7
    assert item.flag_type == RiskFlagType.ONE_SIDED


def test_evaluator_fallback_low_risk():
    evaluator = GeminiRiskEvaluator(api_key="")
    evaluator.client = None
    clauses = [
        InputClauseToEvaluate(
            clause_id="doc-1-clause-0002",
            category=ClauseCategory.GOVERNING_LAW,
            text="This Agreement shall be governed by the laws of the State of California.",
        )
    ]
    results = evaluator.evaluate_batch(clauses)
    assert len(results) == 1
    item = results[0]
    assert item.risk_level == RiskLevel.LOW
    assert item.risk_score <= 0.3
    assert item.flag_type == RiskFlagType.FAIR


def test_evaluator_gemini_success():
    evaluator = GeminiRiskEvaluator(api_key="mock_key")
    evaluator.client = MagicMock()

    mock_response = MagicMock()
    mock_response.text = '{"evaluations": [{"clause_id": "c1", "risk_level": "HIGH", "risk_score": 0.85, "risk_reason": "Unilateral termination", "flag_type": "UNFAIR_TERM", "suggested_mitigation": "Add 30 days notice"}]}'
    evaluator.client.models.generate_content.return_value = mock_response

    clauses = [
        InputClauseToEvaluate(
            clause_id="c1",
            category=ClauseCategory.TERMINATION_EXIT,
            text="Unilateral termination clause.",
        )
    ]
    results = evaluator.evaluate_batch(clauses)
    assert len(results) == 1
    assert results[0].clause_id == "c1"
    assert results[0].risk_level == RiskLevel.HIGH
    assert results[0].risk_score == 0.85

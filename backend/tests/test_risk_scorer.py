from unittest.mock import MagicMock
import pytest
from app.models.enums import RiskLevel
from app.services.gemini_risk_scorer import (
    ClauseRiskBatchOutput,
    ClauseRiskItem,
    GeminiRiskScorer,
    RiskScoringError,
)


def test_score_batch_success(monkeypatch):
    scorer = GeminiRiskScorer(api_key="test-key", model_name="gemini-3.6-flash")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = ClauseRiskBatchOutput(
        risk_scores=[
            ClauseRiskItem(
                clause_id="doc-1-clause-0001",
                risk_level=RiskLevel.HIGH,
                risk_reason="Unilateral termination without prior written notice.",
                similarity_score=0.85,
            )
        ]
    ).model_dump_json()

    mock_client.models.generate_content.return_value = mock_response
    monkeypatch.setattr(scorer, "_client", mock_client)

    clauses = [
        {
            "clause_id": "doc-1-clause-0001",
            "category": "TERMINATION",
            "heading": "1. Termination",
            "text": "Landlord may terminate immediately at any time.",
        }
    ]

    results = scorer.score_batch(clauses)

    assert len(results) == 1
    assert results[0].risk_level == RiskLevel.HIGH
    assert results[0].similarity_score == 0.85


def test_score_batch_empty():
    scorer = GeminiRiskScorer(api_key="test-key")
    assert scorer.score_batch([]) == []


def test_score_batch_api_error_raises(monkeypatch):
    scorer = GeminiRiskScorer(api_key="test-key")

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API error")
    monkeypatch.setattr(scorer, "_client", mock_client)

    with pytest.raises(RiskScoringError):
        scorer.score_batch([{"clause_id": "c1", "text": "text"}])

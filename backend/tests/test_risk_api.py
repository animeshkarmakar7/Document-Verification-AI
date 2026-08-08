from datetime import UTC, datetime
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import RiskFlagType, RiskLevel
from app.models.risk import ClauseRisk

client = TestClient(app)


def test_score_risk_api_not_found(monkeypatch):
    mock_service = MagicMock()
    from app.services.risk_service import DocumentNotFoundError
    mock_service.score_document_risk.side_effect = DocumentNotFoundError("Document not found")
    monkeypatch.setattr("app.api.risk.RiskService", lambda db: mock_service)

    response = client.post("/api/v1/documents/nonexistent-doc/score-risk")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Document not found"


def test_score_risk_api_success(monkeypatch):
    mock_service = MagicMock()
    mock_risk = ClauseRisk(
        id="risk-1",
        document_id="doc-123",
        clause_id="doc-123-clause-0001",
        clause_pk="clause-pk-1",
        risk_level=RiskLevel.HIGH,
        risk_score=0.8,
        risk_reason="Unfair notice requirement",
        flag_type=RiskFlagType.UNFAIR_TERM,
        suggested_mitigation="Add 30 day notice",
        created_at=datetime.now(UTC),
    )
    mock_service.score_document_risk.return_value = [mock_risk]
    monkeypatch.setattr("app.api.risk.RiskService", lambda db: mock_service)

    response = client.post("/api/v1/documents/doc-123/score-risk")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["clause_id"] == "doc-123-clause-0001"
    assert data[0]["risk_level"] == "HIGH"


def test_get_risk_dashboard_api_success(monkeypatch):
    mock_service = MagicMock()
    mock_service.get_risk_dashboard.return_value = {
        "document_id": "doc-123",
        "overall_risk_score": 75,
        "total_clauses": 2,
        "high_risk_count": 1,
        "medium_risk_count": 1,
        "low_risk_count": 0,
        "category_breakdown": {
            "TERMINATION_EXIT": {"HIGH": 1, "MEDIUM": 0, "LOW": 0},
            "PENALTY_FEES": {"HIGH": 0, "MEDIUM": 1, "LOW": 0},
        },
        "high_risk_clauses": [
            {
                "clause_id": "doc-123-clause-0001",
                "category": "TERMINATION_EXIT",
                "risk_level": "HIGH",
                "risk_score": 0.85,
                "risk_reason": "Unilateral termination",
                "flag_type": "UNFAIR_TERM",
                "suggested_mitigation": "Add 30 days notice",
            }
        ],
        "clauses": [
            {
                "clause_id": "doc-123-clause-0001",
                "clause_pk": "clause-pk-1",
                "risk_level": "HIGH",
                "risk_score": 0.85,
                "risk_reason": "Unilateral termination",
                "flag_type": "UNFAIR_TERM",
                "suggested_mitigation": "Add 30 days notice",
                "created_at": "2026-08-09T02:00:00Z",
            }
        ],
    }
    monkeypatch.setattr("app.api.risk.RiskService", lambda db: mock_service)

    response = client.get("/api/v1/documents/doc-123/risk-dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == "doc-123"
    assert data["overall_risk_score"] == 75

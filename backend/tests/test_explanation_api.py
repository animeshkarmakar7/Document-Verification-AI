from datetime import UTC, datetime
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.explanation import ClauseExplanation

client = TestClient(app)


def test_explain_api_not_found(monkeypatch):
    mock_service = MagicMock()
    from app.services.explanation_service import DocumentNotFoundError
    mock_service.explain_document.side_effect = DocumentNotFoundError("not found")
    monkeypatch.setattr("app.api.explanation.ExplanationService", lambda db: mock_service)

    response = client.post("/api/v1/documents/bad-doc/explain")
    assert response.status_code == 404


def test_explain_api_success(monkeypatch):
    mock_service = MagicMock()
    now = datetime.now(UTC)
    mock_expl = ClauseExplanation(
        id="expl-1",
        document_id="doc-1",
        clause_id="doc-1-clause-0001",
        clause_pk="clause-pk-1",
        plain_summary="The landlord can end the lease at any time without warning.",
        source_span_start=0,
        source_span_end=50,
        readability_score_original=14.5,
        readability_score_summary=6.2,
        confidence=0.92,
        is_grounded=True,
        model_version="gemini-3.6-flash",
        created_at=now,
    )
    mock_service.explain_document.return_value = [mock_expl]
    monkeypatch.setattr("app.api.explanation.ExplanationService", lambda db: mock_service)

    response = client.post("/api/v1/documents/doc-1/explain")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["clause_id"] == "doc-1-clause-0001"
    assert data[0]["is_grounded"] is True
    assert data[0]["confidence"] == 0.92


def test_readability_report_api(monkeypatch):
    mock_service = MagicMock()
    mock_service.get_readability_report.return_value = {
        "document_id": "doc-1",
        "total_clauses": 2,
        "average_original_grade": 16.3,
        "average_summary_grade": 7.1,
        "average_improvement": 9.2,
        "grounded_count": 2,
        "ungrounded_count": 0,
        "clauses": [],
    }
    monkeypatch.setattr("app.api.explanation.ExplanationService", lambda db: mock_service)

    response = client.get("/api/v1/documents/doc-1/readability-report")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == "doc-1"
    assert data["average_improvement"] == 9.2
    assert data["grounded_count"] == 2

"""API-layer unit tests for the Clauses router.

Uses FastAPI's TestClient with the real app; all service-layer calls are
monkeypatched so no database or storage is required.

Coverage:
- POST /documents/{id}/clauses/segment  → 200 success
- POST /documents/{id}/clauses/segment  → 404 document not found
- POST /documents/{id}/clauses/segment  → 409 not ready
- GET  /documents/{id}/clauses          → 200 with pagination metadata
- GET  /documents/{id}/clauses          → 404 document not found
- GET  /documents/{id}/clauses/{cid}    → 200 single clause
- GET  /documents/{id}/clauses/{cid}    → 404 clause not found
- GET  /documents/{id}/clauses/{cid}    → 404 document not found
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from app.main import app
from app.models.clause import Clause
from app.services.clause_service import (
    ClauseNotFoundError,
    ClauseSegmentationService,
    DocumentNotReadyForSegmentationError,
)
from app.services.ocr_service import DocumentNotFoundError
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "/api/v1/documents"

_NOW = datetime.now(UTC)


def _make_clause(
    document_id: str = "doc-1",
    clause_id: str = "doc-1-clause-0001",
    order_index: int = 1,
    heading: str | None = "1. Rent",
    text: str = "The tenant shall pay rent monthly.",
    source_start: int = 0,
    source_end: int = 33,
) -> Clause:
    clause = Clause(
        document_id=document_id,
        clause_id=clause_id,
        order_index=order_index,
        heading=heading,
        text=text,
        source_start=source_start,
        source_end=source_end,
    )
    clause.created_at = _NOW
    return clause


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /segment
# ---------------------------------------------------------------------------


def test_segment_returns_200(client, monkeypatch):
    clause = _make_clause()
    mock = MagicMock(spec=ClauseSegmentationService)
    mock.segment_document.return_value = [clause]
    monkeypatch.setattr(
        "app.api.clauses.ClauseSegmentationService",
        lambda db: mock,
    )

    response = client.post(f"{BASE}/doc-1/clauses/segment")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == "doc-1"
    assert body["clause_count"] == 1
    assert body["clauses"][0]["clause_id"] == "doc-1-clause-0001"
    assert body["clauses"][0]["char_count"] == len(clause.text)
    assert body["clauses"][0]["word_count"] == len(clause.text.split())


def test_segment_force_query_param_forwarded(client, monkeypatch):
    mock = MagicMock(spec=ClauseSegmentationService)
    mock.segment_document.return_value = [_make_clause()]
    monkeypatch.setattr(
        "app.api.clauses.ClauseSegmentationService",
        lambda db: mock,
    )

    client.post(f"{BASE}/doc-1/clauses/segment?force=true")

    mock.segment_document.assert_called_once_with(
        document_id="doc-1", force=True
    )


def test_segment_404_when_document_not_found(client, monkeypatch):
    mock = MagicMock(spec=ClauseSegmentationService)
    mock.segment_document.side_effect = DocumentNotFoundError("not found")
    monkeypatch.setattr(
        "app.api.clauses.ClauseSegmentationService",
        lambda db: mock,
    )

    response = client.post(f"{BASE}/doc-1/clauses/segment")
    assert response.status_code == 404


def test_segment_409_when_not_ready(client, monkeypatch):
    mock = MagicMock(spec=ClauseSegmentationService)
    mock.segment_document.side_effect = (
        DocumentNotReadyForSegmentationError("not ready")
    )
    monkeypatch.setattr(
        "app.api.clauses.ClauseSegmentationService",
        lambda db: mock,
    )

    response = client.post(f"{BASE}/doc-1/clauses/segment")
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# GET /clauses  (paginated list)
# ---------------------------------------------------------------------------


def test_list_clauses_returns_pagination_metadata(client, monkeypatch):
    clauses = [
        _make_clause(clause_id="doc-1-clause-0001", order_index=1),
        _make_clause(
            clause_id="doc-1-clause-0002",
            order_index=2,
            heading="2. Termination",
            text="Either party may terminate.",
            source_start=34,
            source_end=60,
        ),
    ]
    mock = MagicMock(spec=ClauseSegmentationService)
    mock.list_clauses_paginated.return_value = (clauses, 2)
    monkeypatch.setattr(
        "app.api.clauses.ClauseSegmentationService",
        lambda db: mock,
    )

    response = client.get(f"{BASE}/doc-1/clauses")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["offset"] == 0
    assert body["limit"] is None
    assert len(body["clauses"]) == 2


def test_list_clauses_passes_limit_offset(client, monkeypatch):
    mock = MagicMock(spec=ClauseSegmentationService)
    mock.list_clauses_paginated.return_value = ([_make_clause()], 5)
    monkeypatch.setattr(
        "app.api.clauses.ClauseSegmentationService",
        lambda db: mock,
    )

    client.get(f"{BASE}/doc-1/clauses?limit=1&offset=2")
    mock.list_clauses_paginated.assert_called_once_with(
        "doc-1", limit=1, offset=2
    )


def test_list_clauses_404_when_document_not_found(client, monkeypatch):
    mock = MagicMock(spec=ClauseSegmentationService)
    mock.list_clauses_paginated.side_effect = DocumentNotFoundError("nope")
    monkeypatch.setattr(
        "app.api.clauses.ClauseSegmentationService",
        lambda db: mock,
    )

    response = client.get(f"{BASE}/doc-1/clauses")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /clauses/{clause_id}
# ---------------------------------------------------------------------------


def test_get_clause_returns_200(client, monkeypatch):
    clause = _make_clause()
    mock = MagicMock(spec=ClauseSegmentationService)
    mock.get_clause.return_value = clause
    monkeypatch.setattr(
        "app.api.clauses.ClauseSegmentationService",
        lambda db: mock,
    )

    response = client.get(f"{BASE}/doc-1/clauses/doc-1-clause-0001")
    assert response.status_code == 200
    body = response.json()
    assert body["clause_id"] == "doc-1-clause-0001"
    assert body["heading"] == "1. Rent"
    assert "char_count" in body
    assert "word_count" in body


def test_get_clause_404_clause_not_found(client, monkeypatch):
    mock = MagicMock(spec=ClauseSegmentationService)
    mock.get_clause.side_effect = ClauseNotFoundError("no clause")
    monkeypatch.setattr(
        "app.api.clauses.ClauseSegmentationService",
        lambda db: mock,
    )

    response = client.get(f"{BASE}/doc-1/clauses/doc-1-clause-9999")
    assert response.status_code == 404


def test_get_clause_404_document_not_found(client, monkeypatch):
    mock = MagicMock(spec=ClauseSegmentationService)
    mock.get_clause.side_effect = DocumentNotFoundError("no doc")
    monkeypatch.setattr(
        "app.api.clauses.ClauseSegmentationService",
        lambda db: mock,
    )

    response = client.get(f"{BASE}/nonexistent/clauses/some-clause")
    assert response.status_code == 404

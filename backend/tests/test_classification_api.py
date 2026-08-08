from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.classification import ClauseClassification
from app.models.enums import ClauseCategory
from app.services.classification_service import (
    ClassificationNotFoundError,
    ClauseClassificationService,
    DocumentNotReadyForClassificationError,
)
from app.services.ocr_service import DocumentNotFoundError

BASE = "/api/v1/documents"
_NOW = datetime.now(UTC)


def _make_classification(
    document_id: str = "doc-1",
    clause_id: str = "doc-1-clause-0001",
    category: ClauseCategory = ClauseCategory.PAYMENT_TERMS,
) -> ClauseClassification:
    item = ClauseClassification(
        document_id=document_id,
        clause_pk="pk-1",
        clause_id=clause_id,
        category=category,
        model_version="gemini-2.0-flash",
        raw_response={"category": category.value},
        source_start=0,
        source_end=20,
    )
    item.created_at = _NOW
    return item


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_classify_returns_200(client, monkeypatch):
    mock = MagicMock(spec=ClauseClassificationService)
    mock.classify_document.return_value = [_make_classification()]
    monkeypatch.setattr(
        "app.api.classification.ClauseClassificationService",
        lambda db: mock,
    )

    response = client.post(f"{BASE}/doc-1/classify")
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == "doc-1"
    assert body["classified_count"] == 1
    assert body["classifications"][0]["category"] == "PAYMENT_TERMS"


def test_classify_404_doc_not_found(client, monkeypatch):
    mock = MagicMock(spec=ClauseClassificationService)
    mock.classify_document.side_effect = DocumentNotFoundError("not found")
    monkeypatch.setattr(
        "app.api.classification.ClauseClassificationService",
        lambda db: mock,
    )

    response = client.post(f"{BASE}/doc-1/classify")
    assert response.status_code == 404


def test_classify_409_not_ready(client, monkeypatch):
    mock = MagicMock(spec=ClauseClassificationService)
    mock.classify_document.side_effect = DocumentNotReadyForClassificationError("not ready")
    monkeypatch.setattr(
        "app.api.classification.ClauseClassificationService",
        lambda db: mock,
    )

    response = client.post(f"{BASE}/doc-1/classify")
    assert response.status_code == 409


def test_list_classifications_200(client, monkeypatch):
    mock = MagicMock(spec=ClauseClassificationService)
    mock.list_classifications.return_value = [_make_classification()]
    monkeypatch.setattr(
        "app.api.classification.ClauseClassificationService",
        lambda db: mock,
    )

    response = client.get(f"{BASE}/doc-1/classifications")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["classifications"][0]["clause_id"] == "doc-1-clause-0001"


def test_get_clause_classification_200(client, monkeypatch):
    mock = MagicMock(spec=ClauseClassificationService)
    mock.get_clause_classification.return_value = _make_classification()
    monkeypatch.setattr(
        "app.api.classification.ClauseClassificationService",
        lambda db: mock,
    )

    response = client.get(f"{BASE}/doc-1/clauses/doc-1-clause-0001/classification")
    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "PAYMENT_TERMS"


def test_get_clause_classification_404_not_found(client, monkeypatch):
    mock = MagicMock(spec=ClauseClassificationService)
    mock.get_clause_classification.side_effect = ClassificationNotFoundError("missing")
    monkeypatch.setattr(
        "app.api.classification.ClauseClassificationService",
        lambda db: mock,
    )

    response = client.get(f"{BASE}/doc-1/clauses/doc-1-clause-9999/classification")
    assert response.status_code == 404

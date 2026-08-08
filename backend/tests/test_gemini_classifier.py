from unittest.mock import MagicMock
import pytest
from app.models.enums import ClauseCategory
from app.services.gemini_classifier import (
    ClassificationError,
    ClauseClassificationBatchOutput,
    ClauseClassificationItem,
    GeminiClassifier,
)


def test_classify_batch_success(monkeypatch):
    classifier = GeminiClassifier(api_key="test-key", model_name="gemini-2.0-flash")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = ClauseClassificationBatchOutput(
        classifications=[
            ClauseClassificationItem(
                clause_id="doc-1-clause-0001",
                category=ClauseCategory.PAYMENT_TERMS,
                reasoning="Rent payment terms",
            ),
            ClauseClassificationItem(
                clause_id="doc-1-clause-0002",
                category=ClauseCategory.TERMINATION_EXIT,
                reasoning="Termination notice",
            ),
        ]
    ).model_dump_json()

    mock_client.models.generate_content.return_value = mock_response
    monkeypatch.setattr(classifier, "_client", mock_client)

    clauses = [
        {"clause_id": "doc-1-clause-0001", "heading": "1. Rent", "text": "Tenant pays monthly."},
        {"clause_id": "doc-1-clause-0002", "heading": "2. Term", "text": "Either party may terminate."},
    ]

    results = classifier.classify_batch(clauses)

    assert len(results) == 2
    assert results[0].clause_id == "doc-1-clause-0001"
    assert results[0].category == ClauseCategory.PAYMENT_TERMS
    assert results[1].clause_id == "doc-1-clause-0002"
    assert results[1].category == ClauseCategory.TERMINATION_EXIT


def test_classify_batch_empty():
    classifier = GeminiClassifier(api_key="test-key")
    assert classifier.classify_batch([]) == []


def test_classify_batch_handles_missing_api_key(monkeypatch):
    classifier = GeminiClassifier(api_key="", model_name="gemini-2.0-flash")
    with pytest.raises(ClassificationError):
        classifier.classify_batch([{"clause_id": "c1", "text": "text"}])


def test_classify_batch_api_error_raises_classification_error(monkeypatch):
    classifier = GeminiClassifier(api_key="test-key")

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API rate limit")
    monkeypatch.setattr(classifier, "_client", mock_client)

    with pytest.raises(ClassificationError):
        classifier.classify_batch([{"clause_id": "c1", "text": "text"}])

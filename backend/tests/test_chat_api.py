from datetime import UTC, datetime
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.chat import ChatMessage

client = TestClient(app)


def test_chat_api_not_found(monkeypatch):
    mock_service = MagicMock()
    from app.services.rag_service import DocumentNotFoundError
    mock_service.chat.side_effect = DocumentNotFoundError("not found")
    monkeypatch.setattr("app.api.chat.RAGService", lambda db: mock_service)

    response = client.post("/api/v1/documents/bad-doc/chat", json={"query": "What is rent?"})
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "not found"


def test_chat_api_success(monkeypatch):
    mock_service = MagicMock()
    now = datetime.now(UTC)
    mock_service.chat.return_value = {
        "message_id": "msg-1",
        "document_id": "doc-1",
        "query": "What is the notice period?",
        "answer": "Notice period is 30 days.",
        "citations": [
            {
                "clause_id": "doc-1-clause-0001",
                "source_span_start": 0,
                "source_span_end": 40,
                "quoted_text": "30 days notice required",
            }
        ],
        "confidence": 0.9,
        "created_at": now.isoformat(),
    }
    monkeypatch.setattr("app.api.chat.RAGService", lambda db: mock_service)

    response = client.post(
        "/api/v1/documents/doc-1/chat",
        json={"query": "What is the notice period?", "top_k": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Notice period is 30 days."
    assert data["confidence"] == 0.9
    assert len(data["citations"]) == 1


def test_chat_history_api(monkeypatch):
    mock_service = MagicMock()
    now = datetime.now(UTC)
    msg1 = ChatMessage(
        id="msg-1",
        document_id="doc-1",
        role="user",
        content="What is rent?",
        citations=None,
        confidence=None,
        created_at=now,
    )
    msg2 = ChatMessage(
        id="msg-2",
        document_id="doc-1",
        role="assistant",
        content="Rent is $1000 per month.",
        citations=[],
        confidence=0.9,
        created_at=now,
    )
    mock_service.get_chat_history.return_value = [msg1, msg2]
    monkeypatch.setattr("app.api.chat.RAGService", lambda db: mock_service)

    response = client.get("/api/v1/documents/doc-1/chat-history")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == "doc-1"
    assert data["total_messages"] == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"

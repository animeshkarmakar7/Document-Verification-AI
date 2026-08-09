import pytest

from app.models.clause import Clause
from app.services.embedding_service import ClauseEmbeddingService


def test_embedding_service_similar_match():
    service = ClauseEmbeddingService()
    clauses = [
        Clause(
            id="c1",
            document_id="doc-1",
            clause_id="doc-1-clause-0001",
            text="The tenant must pay a security deposit of $1,000 upon signing.",
            source_start=0,
            source_end=60,
            order_index=0,
        ),
        Clause(
            id="c2",
            document_id="doc-1",
            clause_id="doc-1-clause-0002",
            text="Either party may terminate this agreement with 30 days notice.",
            source_start=61,
            source_end=120,
            order_index=1,
        ),
    ]

    results = service.search_similar_clauses("deposit refund terms", clauses, top_k=2)
    assert len(results) == 2
    assert results[0].clause.id == "c1"
    assert results[0].score > results[1].score


def test_embedding_service_empty_clauses():
    service = ClauseEmbeddingService()
    assert service.search_similar_clauses("anything", [], top_k=3) == []

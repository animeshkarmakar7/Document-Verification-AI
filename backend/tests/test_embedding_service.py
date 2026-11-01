from unittest.mock import MagicMock

from app.models.clause import Clause
from app.services.embedding_service import ClauseEmbeddingService
from app.services.vector_store_service import VectorSearchResult


def test_embedding_service_returns_only_hybrid_retrieval_results():
    vector_store = MagicMock()
    vector_store.hybrid_search.return_value = [
        VectorSearchResult(
            clause_id="doc-1-clause-0001",
            chunk_id="chunk-1",
            text="The tenant must pay a security deposit of $1,000 upon signing.",
            score=0.9,
            source_start=0,
            source_end=60,
        )
    ]
    service = ClauseEmbeddingService(vector_store=vector_store)
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

    assert len(results) == 1
    assert results[0].clause.clause_id == "doc-1-clause-0001"
    vector_store.index_document_clauses.assert_called_once_with(
        "doc-1",
        clauses,
    )


def test_embedding_service_empty_clauses():
    service = ClauseEmbeddingService(vector_store=MagicMock())
    assert service.search_similar_clauses("anything", [], top_k=3) == []

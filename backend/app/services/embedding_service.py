import logging
from dataclasses import dataclass

from app.models.clause import Clause
from app.services.vector_store_service import VectorStoreService, VectorSearchResult

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    clause: Clause
    score: float


class ClauseEmbeddingService:
    def __init__(self, vector_store: VectorStoreService | None = None):
        self.vector_store = vector_store or VectorStoreService()

    def search_similar_clauses(
        self, query: str, clauses: list[Clause], top_k: int = 3
    ) -> list[SearchResult]:
        if not clauses:
            return []

        doc_id = clauses[0].document_id if clauses else ""

        # Index clauses if document_id available
        if doc_id:
            try:
                self.vector_store.index_document_clauses(doc_id, clauses)
            except Exception as e:
                logger.warning(f"Vector indexing failed during search: {e}")

        # Execute hybrid vector search
        v_results = self.vector_store.hybrid_search(
            document_id=doc_id, query=query, clauses=clauses, top_k=top_k
        )

        clause_map = {c.clause_id: c for c in clauses}
        results = []
        for vr in v_results:
            c_obj = clause_map.get(vr.clause_id)
            if c_obj:
                results.append(SearchResult(clause=c_obj, score=vr.score))

        # Fallback if no matching clause objects found
        if not results:
            results = [SearchResult(clause=c, score=0.5) for c in clauses[:top_k]]

        return results

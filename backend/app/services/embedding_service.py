from dataclasses import dataclass

from app.models.clause import Clause
from app.services.vector_store_service import VectorStoreService


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
        if top_k < 1:
            raise ValueError("top_k must be positive.")

        document_id = clauses[0].document_id
        self.vector_store.index_document_clauses(
            document_id,
            clauses,
        )
        retrieved = self.vector_store.hybrid_search(
            document_id=document_id,
            query=query,
            clauses=clauses,
            top_k=top_k,
        )
        clause_by_id = {clause.clause_id: clause for clause in clauses}
        results = []
        seen_clause_ids = set()

        for item in retrieved:
            clause = clause_by_id.get(item.clause_id)
            if clause is None or clause.clause_id in seen_clause_ids:
                continue
            seen_clause_ids.add(clause.clause_id)
            results.append(SearchResult(clause=clause, score=item.score))

        return results

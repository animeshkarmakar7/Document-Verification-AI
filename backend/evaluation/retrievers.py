from app.services.vector_store_service import VectorSearchResult, VectorStoreService


class RetrievalVariants:
    def __init__(self, vector_store: VectorStoreService):
        self.vector_store = vector_store

    def dense_only(self, document_id, query, clauses, top_k):
        candidate_k = max(top_k, settings.RETRIEVAL_CANDIDATE_K)
        return self.vector_store.dense_search(
            document_id=document_id,
            query=query,
            candidate_k=candidate_k,
        )[:top_k]

    def bm25_only(self, document_id, query, clauses, top_k):
        candidate_k = max(top_k, settings.RETRIEVAL_CANDIDATE_K)
        return self.vector_store.sparse_search(
            query=query,
            clauses=clauses,
            candidate_k=candidate_k,
        )[:top_k]

    def hybrid_rrf(self, document_id, query, clauses, top_k):
        results, _ = self.vector_store.hybrid_search_with_trace(
            document_id=document_id,
            query=query,
            clauses=clauses,
            top_k=top_k,
            candidate_k=max(top_k, settings.RETRIEVAL_CANDIDATE_K),
            apply_reranker=False,
        )
        return results

    def hybrid_reranked(self, document_id, query, clauses, top_k):
        results, _ = self.vector_store.hybrid_search_with_trace(
            document_id=document_id,
            query=query,
            clauses=clauses,
            top_k=top_k,
            candidate_k=max(top_k, settings.RETRIEVAL_CANDIDATE_K),
            apply_reranker=True,
        )
        return results

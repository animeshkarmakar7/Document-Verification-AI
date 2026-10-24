from app.services.vector_store_service import VectorSearchResult, VectorStoreService


class RetrievalVariants:
    def __init__(self, vector_store: VectorStoreService):
        self.vector_store = vector_store

    @staticmethod
    def _unique_by_clause(results, top_k):
        unique = []
        seen = set()
        for result in results:
            if result.clause_id and result.clause_id not in seen:
                unique.append(result)
                seen.add(result.clause_id)
            if len(unique) >= top_k:
                break
        return unique

    def dense_only(self, document_id, query, clauses, top_k):
        service = self.vector_store
        if service.collection is None:
            raise RuntimeError("ChromaDB collection is not initialized.")

        encoder = service._get_encoder()
        if encoder is None:
            raise RuntimeError(f"Could not load embedding model '{service.model_name}'.")

        query_embedding = encoder.encode([query], show_progress_bar=False).tolist()
        response = service.collection.query(
            query_embeddings=query_embedding,
            where={"document_id": document_id},
            n_results=min(max(top_k * 4, 10), 40),
        )
        documents = (response.get("documents") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        results = []
        for text, metadata, distance in zip(documents, metadatas, distances):
            score = max(0.0, 1.0 - float(distance)) if distance is not None else 0.0
            results.append(
                VectorSearchResult(
                    clause_id=metadata.get("clause_id", ""),
                    text=text or "",
                    score=score,
                    source_start=metadata.get("source_start", 0),
                    source_end=metadata.get("source_end", 0),
                    heading=metadata.get("heading") or None,
                    chunk_id=metadata.get("chunk_id"),
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return self._unique_by_clause(results, top_k)

    def bm25_only(self, document_id, query, clauses, top_k):
        return self._unique_by_clause(
            self.vector_store._sparse_keyword_search(query, clauses, top_k=top_k * 4),
            top_k,
        )

    def hybrid_rrf(self, document_id, query, clauses, top_k):
        dense = self.dense_only(document_id, query, clauses, max(top_k * 2, 10))
        sparse = self.vector_store._sparse_keyword_search(query, clauses, top_k=top_k * 4)
        fused = self.vector_store._rrf_fuse(dense, sparse, top_k=max(top_k * 2, 10))
        return self._unique_by_clause(fused, top_k)

    def hybrid_reranked(self, document_id, query, clauses, top_k):
        results = self.vector_store.hybrid_search(
            document_id=document_id,
            query=query,
            clauses=clauses,
            top_k=top_k,
            strict=True,
        )
        return self._unique_by_clause(results, top_k)

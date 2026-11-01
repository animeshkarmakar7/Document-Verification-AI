from app.services.vector_store_service import SearchReranker, VectorSearchResult


class FakeCrossEncoder:
    def predict(self, pairs, batch_size, show_progress_bar):
        return [0.1 if "payment" in passage else 2.5 for _, passage in pairs]


def test_cross_encoder_reranks_by_model_score_not_rrf_score():
    reranker = SearchReranker()
    reranker._model = FakeCrossEncoder()
    results = [
        VectorSearchResult(
            clause_id="clause-a",
            chunk_id="chunk-a",
            text="payment schedule",
            score=0.04,
            rrf_score=0.04,
            source_start=0,
            source_end=15,
        ),
        VectorSearchResult(
            clause_id="clause-b",
            chunk_id="chunk-b",
            text="termination notice period",
            score=0.02,
            rrf_score=0.02,
            source_start=16,
            source_end=42,
        ),
    ]

    ranked = reranker.rerank("termination notice", results, top_k=2)

    assert [result.chunk_id for result in ranked] == ["chunk-b", "chunk-a"]
    assert ranked[0].rerank_score == 2.5
    assert ranked[1].rrf_score == 0.04


def test_cross_encoder_failure_is_propagated():
    class BrokenCrossEncoder:
        def predict(self, pairs, batch_size, show_progress_bar):
            raise RuntimeError("reranker unavailable")

    reranker = SearchReranker()
    reranker._model = BrokenCrossEncoder()
    results = [
        VectorSearchResult(
            clause_id="clause-a",
            chunk_id="chunk-a",
            text="payment schedule",
            score=0.04,
            source_start=0,
            source_end=15,
        )
    ]

    try:
        reranker.rerank("payment terms", results, top_k=1)
    except RuntimeError as exc:
        assert "reranker unavailable" in str(exc)
    else:
        raise AssertionError("Cross-encoder errors must not invoke a fallback")

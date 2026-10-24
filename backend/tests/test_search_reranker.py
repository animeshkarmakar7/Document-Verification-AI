from app.services.vector_store_service import SearchReranker, VectorSearchResult


def test_reranker_scales_lexical_bonus_to_fused_score():
    results = [
        VectorSearchResult(
            clause_id="clause-a",
            text="termination notice period",
            score=0.02,
            source_start=0,
            source_end=30,
        ),
        VectorSearchResult(
            clause_id="clause-b",
            text="notice",
            score=0.019,
            source_start=31,
            source_end=37,
        ),
    ]

    ranked = SearchReranker().rerank("termination notice", results, top_k=2)

    assert [result.clause_id for result in ranked] == ["clause-a", "clause-b"]
    assert ranked[0].score == 0.021
    assert ranked[1].score == 0.019475

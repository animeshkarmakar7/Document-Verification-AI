from app.services.vector_store_service import SearchReranker, VectorSearchResult


def test_reranker_does_not_overturn_higher_fused_score():
    results = [
        VectorSearchResult(
            clause_id="clause-a",
            text="payment schedule",
            score=0.02,
            source_start=0,
            source_end=15,
        ),
        VectorSearchResult(
            clause_id="clause-b",
            text="termination notice period",
            score=0.0195,
            source_start=16,
            source_end=42,
        ),
    ]

    ranked = SearchReranker().rerank("termination notice", results, top_k=2)

    assert [result.clause_id for result in ranked] == ["clause-a", "clause-b"]
    assert [result.score for result in ranked] == [0.02, 0.0195]


def test_reranker_uses_lexical_overlap_only_to_break_ties():
    results = [
        VectorSearchResult(
            clause_id="clause-a",
            text="payment schedule",
            score=0.02,
            source_start=0,
            source_end=15,
        ),
        VectorSearchResult(
            clause_id="clause-b",
            text="termination notice period",
            score=0.02,
            source_start=16,
            source_end=42,
        ),
    ]

    ranked = SearchReranker().rerank("termination notice", results, top_k=2)

    assert [result.clause_id for result in ranked] == ["clause-b", "clause-a"]
    assert [result.score for result in ranked] == [0.02, 0.02]

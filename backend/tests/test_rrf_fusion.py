from app.services.vector_store_service import VectorSearchResult, VectorStoreService


def make_result(clause_id, text, score, start):
    return VectorSearchResult(
        clause_id=clause_id,
        text=text,
        score=score,
        source_start=start,
        source_end=start + len(text),
    )


def test_rrf_counts_each_clause_once_per_ranking():
    service = object.__new__(VectorStoreService)
    dense = [
        make_result("clause-a", "first chunk of A", 0.95, 0),
        make_result("clause-a", "second chunk of A", 0.90, 100),
        make_result("clause-b", "chunk of B", 0.85, 200),
    ]
    sparse = [
        make_result("clause-b", "full text of B", 8.0, 200),
        make_result("clause-a", "full text of A", 7.0, 0),
    ]

    fused = service._rrf_fuse(dense, sparse, top_k=2)

    assert [item.clause_id for item in fused] == ["clause-a", "clause-b"]
    assert fused[0].score == fused[1].score
    assert fused[0].text == "full text of A"
    assert fused[1].text == "full text of B"

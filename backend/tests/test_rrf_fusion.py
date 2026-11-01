from app.services.vector_store_service import VectorSearchResult, VectorStoreService


def make_result(clause_id, chunk_id, text, score, start):
    return VectorSearchResult(
        clause_id=clause_id,
        chunk_id=chunk_id,
        text=text,
        score=score,
        source_start=start,
        source_end=start + len(text),
    )


def test_rrf_fuses_by_chunk_id_and_preserves_chunk_evidence():
    service = object.__new__(VectorStoreService)
    dense = [
        make_result("clause-a", "chunk-a1", "dense chunk A1", 0.95, 0),
        make_result("clause-a", "chunk-a2", "dense chunk A2", 0.90, 100),
        make_result("clause-b", "chunk-b1", "dense chunk B1", 0.85, 200),
    ]
    sparse = [
        make_result("clause-b", "chunk-b1", "sparse chunk B1", 8.0, 200),
        make_result("clause-a", "chunk-a1", "sparse chunk A1", 7.0, 0),
    ]

    fused = service._rrf_fuse(dense, sparse, top_k=3)

    assert [item.chunk_id for item in fused] == ["chunk-a1", "chunk-b1", "chunk-a2"]
    assert fused[0].text == "dense chunk A1"
    assert fused[1].text == "dense chunk B1"
    assert fused[0].rrf_score == fused[0].score
    assert fused[0].dense_rank == 1
    assert fused[0].sparse_rank == 2


def test_rrf_rejects_candidates_without_chunk_ids():
    service = object.__new__(VectorStoreService)
    dense = [make_result("clause-a", "", "text", 0.9, 0)]

    try:
        service._rrf_fuse(dense, [], top_k=1)
    except ValueError as exc:
        assert "chunk_id" in str(exc)
    else:
        raise AssertionError("RRF must reject candidates without chunk IDs")

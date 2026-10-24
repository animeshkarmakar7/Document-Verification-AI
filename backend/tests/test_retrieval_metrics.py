import pytest

from evaluation.metrics import (
    evaluate_query,
    hit_rate_at_k,
    ndcg_at_k,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
)


def test_recall_at_k():
    assert recall_at_k(["a", "x", "b"], ["a", "b"], 2) == 0.5


def test_precision_at_k_uses_fixed_cutoff():
    assert precision_at_k(["a"], ["a"], 5) == 0.2


def test_hit_rate_at_k():
    assert hit_rate_at_k(["x", "b"], ["a", "b"], 2) == 1.0
    assert hit_rate_at_k(["x"], ["a"], 1) == 0.0


def test_unanswerable_recall_and_hit_rate_are_undefined():
    assert recall_at_k(["a"], [], 5) is None
    assert hit_rate_at_k(["a"], [], 5) is None


def test_reciprocal_rank():
    assert reciprocal_rank_at_k(["x", "b", "a"], ["a", "b"], 3) == 0.5


def test_ndcg_rewards_relevant_items_near_the_top():
    grades = {"a": 3, "b": 1}
    assert ndcg_at_k(["a", "b"], grades, 2) == pytest.approx(1.0)
    assert ndcg_at_k(["b", "a"], grades, 2) < 1.0


def test_percentile_interpolates():
    assert percentile([10, 20, 30], 50) == 20
    assert percentile([10, 20, 30], 95) == 29


def test_evaluate_query_contains_expected_metrics():
    result = evaluate_query(["a", "x"], ["a"])
    assert result["recall@5"] == 1.0
    assert result["mrr@10"] == 1.0

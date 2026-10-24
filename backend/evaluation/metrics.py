import math
from statistics import mean


def recall_at_k(retrieved, relevant, k):
    relevant = set(relevant)
    if not relevant:
        return None
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def precision_at_k(retrieved, relevant, k):
    if k <= 0:
        raise ValueError("k must be positive")
    relevant = set(relevant)
    return len(set(retrieved[:k]) & relevant) / k


def hit_rate_at_k(retrieved, relevant, k):
    relevant = set(relevant)
    if not relevant:
        return None
    return float(bool(set(retrieved[:k]) & relevant))


def reciprocal_rank_at_k(retrieved, relevant, k):
    relevant = set(relevant)
    for rank, item in enumerate(retrieved[:k], start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved, relevance, k):
    def dcg(grades):
        return sum(
            (2 ** grade - 1) / math.log2(rank + 1)
            for rank, grade in enumerate(grades, start=1)
        )

    actual = [float(relevance.get(item, 0)) for item in retrieved[:k]]
    ideal = sorted((float(value) for value in relevance.values()), reverse=True)[:k]
    ideal_dcg = dcg(ideal)
    if ideal_dcg == 0:
        return None
    return dcg(actual) / ideal_dcg


def summarize(values):
    valid = [float(value) for value in values if value is not None]
    return mean(valid) if valid else None


def evaluate_query(retrieved_ids, relevant_ids, relevance=None):
    relevance = relevance or {item: 1 for item in relevant_ids}
    return {
        "recall@5": recall_at_k(retrieved_ids, relevant_ids, 5),
        "recall@10": recall_at_k(retrieved_ids, relevant_ids, 10),
        "precision@5": precision_at_k(retrieved_ids, relevant_ids, 5),
        "precision@10": precision_at_k(retrieved_ids, relevant_ids, 10),
        "hit_rate@5": hit_rate_at_k(retrieved_ids, relevant_ids, 5),
        "mrr@10": reciprocal_rank_at_k(retrieved_ids, relevant_ids, 10),
        "ndcg@10": ndcg_at_k(retrieved_ids, relevance, 10),
    }


def percentile(values, percentile_value):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if not 0 <= percentile_value <= 100:
        raise ValueError("percentile_value must be between 0 and 100")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile_value / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

import math
import re
from dataclasses import dataclass

from app.models.clause import Clause


@dataclass
class SearchResult:
    clause: Clause
    score: float


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _vectorize(tokens: list[str], vocabulary: list[str]) -> list[float]:
    freq = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    return [float(freq.get(word, 0)) for word in vocabulary]


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class ClauseEmbeddingService:

    def search_similar_clauses(
        self, query: str, clauses: list[Clause], top_k: int = 3
    ) -> list[SearchResult]:
        if not clauses:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return [SearchResult(clause=c, score=0.0) for c in clauses[:top_k]]

        clause_tokens_list = [_tokenize(c.text) for c in clauses]
        all_words = set(query_tokens)
        for tokens in clause_tokens_list:
            all_words.update(tokens)

        vocab = list(all_words)
        query_vec = _vectorize(query_tokens, vocab)

        scored_results = []
        for clause, tokens in zip(clauses, clause_tokens_list):
            clause_vec = _vectorize(tokens, vocab)
            score = _cosine_similarity(query_vec, clause_vec)
            scored_results.append(SearchResult(clause=clause, score=round(score, 4)))

        scored_results.sort(key=lambda x: x.score, reverse=True)
        return scored_results[:top_k]

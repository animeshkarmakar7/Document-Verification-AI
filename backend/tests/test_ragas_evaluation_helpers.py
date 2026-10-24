from types import SimpleNamespace

from evaluation.run_ragas_eval import (
    abstention_prediction,
    citation_metrics,
    normalize_text,
)


def test_normalize_text_collapses_whitespace():
    assert normalize_text(" The   Tenant\nshall pay ") == "the tenant shall pay"


def test_citation_metrics_checks_clause_ids_and_quotes():
    clause = SimpleNamespace(
        clause_id="c1",
        text="The Tenant shall pay a refundable security deposit of INR 96,000.",
    )
    citations = [
        {
            "clause_id": "c1",
            "quoted_text": "The Tenant shall pay a refundable security deposit of INR 96,000.",
        }
    ]

    result = citation_metrics(citations, ["c1"], [clause])

    assert result["citation_precision"] == 1.0
    assert result["citation_recall"] == 1.0
    assert result["citation_quote_match_rate"] == 1.0


def test_unanswerable_question_without_citations_has_full_citation_precision():
    result = citation_metrics([], [], [])

    assert result["citation_precision"] == 1.0
    assert result["citation_recall"] is None
    assert result["citation_quote_match_rate"] is None


def test_abstention_prediction_uses_confidence_and_language():
    assert abstention_prediction("Cannot determine from the document.", 0.8)
    assert abstention_prediction("A possible answer.", 0.2)
    assert not abstention_prediction("The deposit is INR 96,000.", 0.9)

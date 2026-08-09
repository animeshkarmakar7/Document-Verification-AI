import logging

from app.models.enums import DocumentStatus
from app.models.explanation import ClauseExplanation
from app.repositories.clause_repository import ClauseRepository
from app.repositories.classification_repository import ClassificationRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.explanation_repository import ExplanationRepository
from app.services.gemini_explainer import (
    CONFIDENCE_THRESHOLD,
    GeminiExplainer,
    InputClauseToExplain,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _val(x) -> str:
    if x is None:
        return "OTHER"
    return x.value if hasattr(x, "value") else str(x)


class ExplanationServiceError(Exception):
    pass


class DocumentNotFoundError(ExplanationServiceError):
    pass


class InvalidDocumentStatusError(ExplanationServiceError):
    pass


class ExplanationService:

    def __init__(self, db: Session, explainer: GeminiExplainer | None = None):
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self.clause_repo = ClauseRepository(db)
        self.class_repo = ClassificationRepository(db)
        self.expl_repo = ExplanationRepository(db)
        self.explainer = explainer or GeminiExplainer()

    def explain_document(
        self, document_id: str, force: bool = False
    ) -> list[ClauseExplanation]:
        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document '{document_id}' not found")

        valid_statuses = {
            DocumentStatus.RISK_SCORED,
            DocumentStatus.EXPLAINED,
            DocumentStatus.CLASSIFIED,
        }
        if doc.status not in valid_statuses:
            raise InvalidDocumentStatusError(
                f"Document '{document_id}' status is '{doc.status.value}'. "
                "Must be RISK_SCORED, CLASSIFIED, or EXPLAINED."
            )

        existing = self.expl_repo.list_by_document(document_id)
        if existing and not force:
            return existing

        if existing and force:
            self.expl_repo.delete_by_document(document_id)

        clauses = self.clause_repo.list_by_document(document_id)
        if not clauses:
            return []

        classifications = self.class_repo.list_by_document(document_id)
        class_map = {c.clause_pk: c for c in classifications}

        inputs = []
        clause_map = {}
        for clause in clauses:
            classification = class_map.get(clause.id)
            cat = _val(classification.category) if classification else "OTHER"
            inputs.append(
                InputClauseToExplain(
                    clause_id=clause.clause_id,
                    category=cat,
                    text=clause.text,
                    source_start=clause.source_start,
                    source_end=clause.source_end,
                )
            )
            clause_map[clause.clause_id] = clause

        explained_items = self.explainer.explain_batch(inputs)

        entities = []
        for item in explained_items:
            clause_obj = clause_map[item.clause_id]
            original_fk = self.explainer.compute_readability(clause_obj.text)
            summary_fk = self.explainer.compute_readability(item.plain_summary)

            if item.confidence < CONFIDENCE_THRESHOLD:
                item = item.model_copy(
                    update={
                        "plain_summary": (
                            "We could not reliably summarize this clause. "
                            "Please consult a qualified legal professional."
                        ),
                        "is_grounded": False,
                    }
                )

            entities.append(
                ClauseExplanation(
                    document_id=document_id,
                    clause_id=item.clause_id,
                    clause_pk=clause_obj.id,
                    plain_summary=item.plain_summary,
                    source_span_start=clause_obj.source_start,
                    source_span_end=clause_obj.source_end,
                    readability_score_original=original_fk,
                    readability_score_summary=summary_fk,
                    confidence=item.confidence,
                    is_grounded=item.is_grounded,
                    model_version=self.explainer.model_name,
                )
            )

        saved = self.expl_repo.create_many(entities)
        doc.status = DocumentStatus.EXPLAINED
        self.db.commit()
        return saved

    def get_clause_explanation(self, clause_id: str) -> ClauseExplanation | None:
        expl = self.expl_repo.get_by_clause_id(clause_id)
        if not expl:
            expl = self.expl_repo.get_by_clause_pk(clause_id)
        return expl

    def get_readability_report(self, document_id: str) -> dict:
        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document '{document_id}' not found")

        explanations = self.expl_repo.list_by_document(document_id)
        if not explanations and doc.status in {
            DocumentStatus.RISK_SCORED,
            DocumentStatus.EXPLAINED,
            DocumentStatus.CLASSIFIED,
        }:
            explanations = self.explain_document(document_id)

        if not explanations:
            return {
                "document_id": document_id,
                "total_clauses": 0,
                "average_original_grade": None,
                "average_summary_grade": None,
                "average_improvement": None,
                "grounded_count": 0,
                "ungrounded_count": 0,
                "clauses": [],
            }

        originals = [e.readability_score_original for e in explanations if e.readability_score_original is not None]
        summaries = [e.readability_score_summary for e in explanations if e.readability_score_summary is not None]

        avg_orig = round(sum(originals) / len(originals), 2) if originals else None
        avg_sum = round(sum(summaries) / len(summaries), 2) if summaries else None
        avg_improvement = round(avg_orig - avg_sum, 2) if avg_orig and avg_sum else None

        return {
            "document_id": document_id,
            "total_clauses": len(explanations),
            "average_original_grade": avg_orig,
            "average_summary_grade": avg_sum,
            "average_improvement": avg_improvement,
            "grounded_count": sum(1 for e in explanations if e.is_grounded),
            "ungrounded_count": sum(1 for e in explanations if not e.is_grounded),
            "clauses": [
                {
                    "clause_id": e.clause_id,
                    "plain_summary": e.plain_summary,
                    "source_span_start": e.source_span_start,
                    "source_span_end": e.source_span_end,
                    "readability_score_original": e.readability_score_original,
                    "readability_score_summary": e.readability_score_summary,
                    "confidence": e.confidence,
                    "is_grounded": e.is_grounded,
                }
                for e in explanations
            ],
        }

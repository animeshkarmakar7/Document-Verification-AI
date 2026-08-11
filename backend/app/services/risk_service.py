import logging

from app.models.classification import ClauseClassification
from app.models.clause import Clause
from app.models.document import Document
from app.models.enums import DocumentStatus, RiskLevel
from app.models.risk import ClauseRisk
from app.repositories.classification_repository import ClassificationRepository
from app.repositories.clause_repository import ClauseRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.risk_repository import RiskRepository
from app.services.risk_evaluator import GeminiRiskEvaluator, InputClauseToEvaluate
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _val(x) -> str:
    if x is None:
        return "OTHER"
    return x.value if hasattr(x, "value") else str(x)


def _clamp_score(val) -> float:
    try:
        f = float(val)
        if f > 1.0:
            f = f / 100.0 if f <= 100.0 else 1.0
        return max(0.0, min(1.0, f))
    except Exception:
        return 0.5


class RiskServiceError(Exception):
    pass


class DocumentNotFoundError(RiskServiceError):
    pass


class InvalidDocumentStatusError(RiskServiceError):
    pass


class RiskService:

    def __init__(
        self,
        db: Session,
        evaluator: GeminiRiskEvaluator | None = None,
    ):
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self.clause_repo = ClauseRepository(db)
        self.class_repo = ClassificationRepository(db)
        self.risk_repo = RiskRepository(db)
        self.evaluator = evaluator or GeminiRiskEvaluator()

    def score_document_risk(
        self, document_id: str, force: bool = False
    ) -> list[ClauseRisk]:
        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document '{document_id}' not found")

        valid_statuses = {
            DocumentStatus.CLASSIFIED,
            DocumentStatus.RISK_SCORED,
            DocumentStatus.EXPLAINED,
        }
        if doc.status not in valid_statuses:
            raise InvalidDocumentStatusError(
                f"Document '{document_id}' status is '{doc.status.value}'. Must be CLASSIFIED, RISK_SCORED, or EXPLAINED."
            )

        existing_risks = self.risk_repo.list_by_document(document_id)
        if existing_risks and not force:
            return existing_risks

        if existing_risks and force:
            self.risk_repo.delete_by_document(document_id)

        clauses = self.clause_repo.list_by_document(document_id)
        if not clauses:
            return []

        classifications = self.class_repo.list_by_document(document_id)
        class_map = {c.clause_pk: c for c in classifications}

        inputs = []
        clause_obj_map = {}
        for clause in clauses:
            classification = class_map.get(clause.id)
            cat_str = _val(classification.category) if classification else "OTHER"
            inputs.append(
                InputClauseToEvaluate(
                    clause_id=clause.clause_id,
                    category=cat_str,
                    text=clause.text,
                )
            )
            clause_obj_map[clause.clause_id] = clause

        evaluated_items = self.evaluator.evaluate_batch(inputs)

        risk_entities = []
        for item in evaluated_items:
            clause_obj = clause_obj_map.get(item.clause_id)
            if not clause_obj:
                continue
            risk = ClauseRisk(
                document_id=document_id,
                clause_id=item.clause_id,
                clause_pk=clause_obj.id,
                risk_level=item.risk_level,
                risk_score=_clamp_score(item.risk_score),
                risk_reason=item.risk_reason,
                flag_type=item.flag_type,
                suggested_mitigation=item.suggested_mitigation,
            )
            risk_entities.append(risk)

        saved_risks = self.risk_repo.create_many(risk_entities)
        if doc.status != DocumentStatus.EXPLAINED:
            doc.status = DocumentStatus.RISK_SCORED
        self.db.commit()

        return saved_risks

    def get_risk_dashboard(self, document_id: str) -> dict:
        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document '{document_id}' not found")

        risks = self.risk_repo.list_by_document(document_id)
        if not risks and doc.status in {
            DocumentStatus.CLASSIFIED,
            DocumentStatus.RISK_SCORED,
            DocumentStatus.EXPLAINED,
        }:
            try:
                risks = self.score_document_risk(document_id)
            except Exception as e:
                logger.warning(f"Auto risk scoring during dashboard fetch failed: {e}")
                risks = []

        classifications = self.class_repo.list_by_document(document_id)
        class_map = {c.clause_pk: _val(c.category) for c in classifications}

        total_clauses = len(risks)
        high_count = sum(1 for r in risks if _val(r.risk_level) == "HIGH")
        medium_count = sum(1 for r in risks if _val(r.risk_level) == "MEDIUM")
        low_count = sum(1 for r in risks if _val(r.risk_level) == "LOW")

        if total_clauses > 0:
            avg_risk = sum(r.risk_score for r in risks) / total_clauses
            high_penalty = (high_count / total_clauses) * 40
            overall_score = min(round((avg_risk * 60) + high_penalty), 100)
        else:
            overall_score = 0

        category_breakdown = {}
        for r in risks:
            cat = class_map.get(r.clause_pk, "OTHER")
            r_level = _val(r.risk_level)
            if cat not in category_breakdown:
                category_breakdown[cat] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            if r_level not in category_breakdown[cat]:
                category_breakdown[cat][r_level] = 0
            category_breakdown[cat][r_level] += 1

        high_risk_details = [
            {
                "clause_id": r.clause_id,
                "category": class_map.get(r.clause_pk, "OTHER"),
                "risk_level": _val(r.risk_level),
                "risk_score": r.risk_score,
                "risk_reason": r.risk_reason,
                "flag_type": _val(r.flag_type),
                "suggested_mitigation": r.suggested_mitigation,
            }
            for r in risks
            if _val(r.risk_level) == "HIGH"
        ]

        return {
            "document_id": document_id,
            "overall_risk_score": overall_score,
            "total_clauses": total_clauses,
            "high_risk_count": high_count,
            "medium_risk_count": medium_count,
            "low_risk_count": low_count,
            "category_breakdown": category_breakdown,
            "high_risk_clauses": high_risk_details,
            "clauses": [
                {
                    "clause_id": r.clause_id,
                    "clause_pk": r.clause_pk,
                    "risk_level": _val(r.risk_level),
                    "risk_score": r.risk_score,
                    "risk_reason": r.risk_reason,
                    "flag_type": _val(r.flag_type),
                    "suggested_mitigation": r.suggested_mitigation,
                    "created_at": r.created_at,
                }
                for r in risks
            ],
        }

    def get_clause_risk(self, clause_id: str) -> ClauseRisk | None:
        risk = self.risk_repo.get_by_clause_id(clause_id)
        if not risk:
            risk = self.risk_repo.get_by_clause_pk(clause_id)
        return risk

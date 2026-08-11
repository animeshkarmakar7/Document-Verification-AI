import json
import logging
from dataclasses import dataclass
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.models.enums import ClauseCategory, RiskFlagType, RiskLevel

logger = logging.getLogger(__name__)


class RiskEvaluationError(Exception):
    pass


class ClauseRiskItem(BaseModel):
    clause_id: str
    risk_level: RiskLevel
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_reason: str
    flag_type: RiskFlagType
    suggested_mitigation: str | None = None


class ClauseRiskBatchOutput(BaseModel):
    evaluations: list[ClauseRiskItem]


@dataclass
class InputClauseToEvaluate:
    clause_id: str
    category: ClauseCategory
    text: str


HIGH_RISK_KEYWORDS = [
    "unilateral", "without notice", "at any time", "sole discretion",
    "non-refundable", "waive all rights", "indemnify and hold harmless",
    "entire liability", "arbitration", "penalty", "automatic renewal",
    "forfeit", "no liability", "unlimited liability", "without cause"
]

MEDIUM_RISK_KEYWORDS = [
    "may terminate", "late payment fee", "subject to change",
    "written notice", "interest rate", "grace period", "limitation of liability"
]


class GeminiRiskEvaluator:

    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    def evaluate_batch(
        self, clauses: list[InputClauseToEvaluate]
    ) -> list[ClauseRiskItem]:
        if not clauses:
            return []

        if not self.client:
            return [self._evaluate_fallback(c) for c in clauses]

        prompt = (
            "You are a top-tier legal risk evaluator analyzing contract clauses for consumer/business safety.\n"
            "Evaluate each clause based on fairness, liability exposure, exit penalties, and ambiguity.\n\n"
            "Return a JSON object containing 'evaluations' array matching the requested schema.\n"
            "For each clause evaluate:\n"
            "- risk_level: 'LOW', 'MEDIUM', or 'HIGH'\n"
            "- risk_score: float between 0.0 (safest) and 1.0 (most dangerous)\n"
            "- risk_reason: clear non-legalese explanation of the risk\n"
            "- flag_type: 'UNFAIR_TERM', 'ONE_SIDED', 'AMBIGUOUS', or 'FAIR'\n"
            "- suggested_mitigation: actionable advice to balance or neutralize the clause\n\n"
            "Clauses to evaluate:\n"
        )
        for c in clauses:
            cat_str = c.category.value if hasattr(c.category, "value") else str(c.category)
            prompt += f"--- Clause ID: {c.clause_id} | Category: {cat_str} ---\n{c.text}\n\n"

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ClauseRiskBatchOutput,
                    temperature=0.1,
                ),
            )

            raw_text = response.text or "{}"
            parsed = json.loads(raw_text)
            batch = ClauseRiskBatchOutput(**parsed)
            
            evaluated_map = {item.clause_id: item for item in batch.evaluations}
            results = []
            for c in clauses:
                if c.clause_id in evaluated_map:
                    results.append(evaluated_map[c.clause_id])
                else:
                    results.append(self._evaluate_fallback(c))
            return results
        except Exception as e:
            logger.warning(f"Gemini risk evaluation failed, using fallback: {e}")
            return [self._evaluate_fallback(c) for c in clauses]

    def _evaluate_fallback(self, clause: InputClauseToEvaluate) -> ClauseRiskItem:
        text_lower = clause.text.lower()
        high_matches = [kw for kw in HIGH_RISK_KEYWORDS if kw in text_lower]
        med_matches = [kw for kw in MEDIUM_RISK_KEYWORDS if kw in text_lower]

        cat_str = clause.category.value if hasattr(clause.category, "value") else str(clause.category)
        if high_matches or cat_str in {
            "TERMINATION_EXIT",
            "PENALTY_FEES",
            "LIABILITY_LIMITATION",
            "INDEMNIFICATION",
        }:
            if high_matches:
                risk_level = RiskLevel.HIGH
                risk_score = min(0.7 + len(high_matches) * 0.1, 0.95)
                flag_type = RiskFlagType.ONE_SIDED if "unilateral" in text_lower or "sole discretion" in text_lower else RiskFlagType.UNFAIR_TERM
                reason = f"High risk clause containing potentially unfair terms ({', '.join(high_matches)})."
                mitigation = "Negotiate bilateral terms or explicit written notice requirements."
            else:
                risk_level = RiskLevel.MEDIUM
                risk_score = 0.55
                flag_type = RiskFlagType.AMBIGUOUS
                reason = f"Category '{cat_str}' warrants review for hidden liabilities or strict penalties."
                mitigation = "Request clear cap on liabilities and symmetrical termination rights."
        elif med_matches:
            risk_level = RiskLevel.MEDIUM
            risk_score = 0.45
            flag_type = RiskFlagType.AMBIGUOUS
            reason = f"Contains terms ({', '.join(med_matches)}) that require careful monitoring."
            mitigation = "Ensure timeline and fee structures are clearly defined."
        else:
            risk_level = RiskLevel.LOW
            risk_score = 0.15
            flag_type = RiskFlagType.FAIR
            reason = "Standard contractual language with no immediate high-risk red flags detected."
            mitigation = "Maintain standard record of compliance."

        return ClauseRiskItem(
            clause_id=clause.clause_id,
            risk_level=risk_level,
            risk_score=risk_score,
            risk_reason=reason,
            flag_type=flag_type,
            suggested_mitigation=mitigation,
        )

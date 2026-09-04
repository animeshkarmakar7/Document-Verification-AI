import json
import logging
from dataclasses import dataclass
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.models.enums import RiskLevel

from app.services.llm_router import LLMRouter, LLMUnavailableError

logger = logging.getLogger(__name__)


class RiskScoringError(Exception):
    pass


class ClauseRiskItem(BaseModel):
    clause_id: str
    risk_level: RiskLevel
    risk_reason: str = Field(
        description="Detailed legal analysis explaining potential risks, liabilities, or ambiguity."
    )
    similarity_score: float = Field(
        default=0.0,
        description="Similarity score (0.0 to 1.0) against benchmark unfair legal terms.",
    )


class ClauseRiskBatchOutput(BaseModel):
    risk_scores: list[ClauseRiskItem]


@dataclass(frozen=True)
class RiskScoringResult:
    clause_id: str
    risk_level: RiskLevel
    risk_reason: str
    similarity_score: float
    raw_response: dict


class GeminiRiskScorer:

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        router: LLMRouter | None = None,
    ):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self._client: genai.Client | None = None
        self.router = router or LLMRouter(
            gemini_api_key=self.api_key,
            gemini_model=self.model_name,
        )

    @property
    def client(self) -> genai.Client:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise RiskScoringError(
                "GEMINI_API_KEY is not set in environment or settings."
            )
        self._client = self.router.gemini_client
        return self._client

    @client.setter
    def client(self, value: Any) -> None:
        self._client = value
        self.router.gemini_client = value

    def score_batch(
        self,
        clauses: list[dict[str, str]],
    ) -> list[RiskScoringResult]:
        if not clauses:
            return []

        if not self.api_key and not self._client:
            raise RiskScoringError("GEMINI_API_KEY is missing.")

        prompt_payload = [
            {
                "clause_id": c["clause_id"],
                "category": c.get("category", "OTHER"),
                "heading": c.get("heading") or "",
                "text": c["text"],
            }
            for c in clauses
        ]

        system_instruction = (
            "You are an expert legal risk compliance auditor. "
            "Analyze each legal clause against standard high-risk legal rubrics: "
            "uncapped liability, unilateral termination without cause/notice, broad hold-harmless indemnities, "
            "unreasonable non-compete periods, automatic renewal with short opt-out windows, and vague pricing terms. "
            "Assign exact risk_level from ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'], provide clear risk_reason, "
            "and compute similarity_score (0.0 to 1.0) against standard unfair legal terms benchmark. "
            "Return a JSON object containing a 'risk_scores' array matching requested schema."
        )

        if self._client is not None:
            self.router.gemini_client = self._client

        try:
            # If a mock client was explicitly injected (unit tests), isolate the call to it
            if self._client is not None and getattr(self._client, "_is_mock", False) or hasattr(self._client, "models"):
                from google.genai import types
                resp = self._client.models.generate_content(
                    model=self.model_name,
                    contents=json.dumps(prompt_payload),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ClauseRiskBatchOutput,
                        system_instruction=system_instruction,
                        temperature=0.0,
                    ),
                )
                raw = resp.text or "{}"
                batch_output = ClauseRiskBatchOutput(**json.loads(raw))
            else:
                batch_output = self.router.generate_structured(
                    prompt=json.dumps(prompt_payload),
                    schema=ClauseRiskBatchOutput,
                    system=system_instruction,
                    temperature=0.0,
                )
        except Exception as exc:
            logger.warning(f"Risk scoring LLM call failed: {exc}")
            raise RiskScoringError(f"Gemini API error: {exc}") from exc

        result_map = {
            item.clause_id: item for item in batch_output.risk_scores
        }

        results = []
        for clause in clauses:
            cid = clause["clause_id"]
            if cid in result_map:
                item = result_map[cid]
                results.append(
                    RiskScoringResult(
                        clause_id=cid,
                        risk_level=item.risk_level,
                        risk_reason=item.risk_reason,
                        similarity_score=min(max(item.similarity_score, 0.0), 1.0),
                        raw_response=item.model_dump(),
                    )
                )
            else:
                results.append(
                    RiskScoringResult(
                        clause_id=cid,
                        risk_level=RiskLevel.LOW,
                        risk_reason="Standard text with low legal risk.",
                        similarity_score=0.0,
                        raw_response={"fallback": True},
                    )
                )

        return results

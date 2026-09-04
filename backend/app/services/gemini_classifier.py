import json
import logging
from dataclasses import dataclass
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.models.enums import ClauseCategory

from app.services.llm_router import LLMRouter, LLMUnavailableError

logger = logging.getLogger(__name__)


class ClassificationError(Exception):
    pass


class ClauseClassificationItem(BaseModel):
    clause_id: str
    category: ClauseCategory
    reasoning: str = Field(
        default="",
        description="Brief legal reasoning for assigned category",
    )


class ClauseClassificationBatchOutput(BaseModel):
    classifications: list[ClauseClassificationItem]


@dataclass(frozen=True)
class ClassificationResult:
    clause_id: str
    category: ClauseCategory
    raw_response: dict


class GeminiClassifier:

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
            raise ClassificationError(
                "GEMINI_API_KEY is not set in environment or settings."
            )
        self._client = self.router.gemini_client
        return self._client

    @client.setter
    def client(self, value: Any) -> None:
        self._client = value
        self.router.gemini_client = value

    def classify_batch(
        self,
        clauses: list[dict[str, str]],
    ) -> list[ClassificationResult]:
        if not clauses:
            return []

        if not self.api_key and not self._client:
            raise ClassificationError("GEMINI_API_KEY is missing.")

        prompt_payload = [
            {
                "clause_id": c["clause_id"],
                "heading": c.get("heading") or "",
                "text": c["text"],
            }
            for c in clauses
        ]

        system_instruction = (
            "You are an expert legal contract analyst. "
            "Classify each provided legal clause into exactly one category from the allowed taxonomy: "
            f"{[e.value for e in ClauseCategory]}. "
            "Return a JSON object containing a 'classifications' array matching the requested schema."
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
                        response_schema=ClauseClassificationBatchOutput,
                        system_instruction=system_instruction,
                        temperature=0.0,
                    ),
                )
                raw = resp.text or "{}"
                batch_output = ClauseClassificationBatchOutput(**json.loads(raw))
            else:
                batch_output = self.router.generate_structured(
                    prompt=json.dumps(prompt_payload),
                    schema=ClauseClassificationBatchOutput,
                    system=system_instruction,
                    temperature=0.0,
                )
        except Exception as exc:
            logger.warning(f"Classification LLM call failed: {exc}")
            raise ClassificationError(f"Gemini API error: {exc}") from exc

        result_map = {
            item.clause_id: item for item in batch_output.classifications
        }

        results = []
        for clause in clauses:
            cid = clause["clause_id"]
            if cid in result_map:
                item = result_map[cid]
                results.append(
                    ClassificationResult(
                        clause_id=cid,
                        category=item.category,
                        raw_response=item.model_dump(),
                    )
                )
            else:
                results.append(
                    ClassificationResult(
                        clause_id=cid,
                        category=ClauseCategory.OTHER,
                        raw_response={"fallback": True, "reason": "Missing in LLM response"},
                    )
                )

        return results


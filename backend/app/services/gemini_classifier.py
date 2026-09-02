import json
import logging
from dataclasses import dataclass
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.models.enums import ClauseCategory

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
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise ClassificationError(
                    "GEMINI_API_KEY is not set in environment or settings."
                )
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def classify_batch(
        self,
        clauses: list[dict[str, str]],
    ) -> list[ClassificationResult]:
        """
        Classify a batch of clauses via Gemini.

        Retries up to 3 times with exponential back-off (15 s, 30 s, 60 s)
        on 429 RESOURCE_EXHAUSTED or 503 UNAVAILABLE before raising.
        The caller (ClauseClassificationService) handles the final failure.
        """
        import time

        _MAX_RETRIES = 3
        _BACKOFF_BASE = 15  # seconds

        if not clauses:
            return []

        if not self.api_key:
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

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=ClauseClassificationBatchOutput,
            temperature=0.0,
        )

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=json.dumps(prompt_payload),
                    config=config,
                )

                if not response.text:
                    raise ClassificationError("Empty response from Gemini classification API.")

                parsed_data = json.loads(response.text)
                batch_output = ClauseClassificationBatchOutput.model_validate(parsed_data)

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
                                raw_response={"fallback": True, "reason": "Missing in Gemini response"},
                            )
                        )

                return results

            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                is_retryable = (
                    "429" in err_str
                    or "503" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "UNAVAILABLE" in err_str
                )
                if is_retryable and attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        f"Gemini classification hit rate limit "
                        f"(attempt {attempt + 1}/{_MAX_RETRIES}), retrying in {wait}s: {exc}"
                    )
                    time.sleep(wait)
                else:
                    break

        logger.warning(f"Gemini classification failed: {last_exc}")
        raise ClassificationError(f"Gemini API error: {last_exc}") from last_exc


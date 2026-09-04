
from __future__ import annotations

import json
import logging
import time
from typing import Any, Type

import httpx
from pydantic import BaseModel

from app.config.settings import settings

logger = logging.getLogger(__name__)

_GEMINI_FALLBACK_SIGNALS = ("429", "503", "404", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "NOT_FOUND")
_RETRY_SIGNALS = ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")
_MAX_RETRIES = 2
_BACKOFF_BASE = 5  # seconds


class LLMUnavailableError(Exception):
    """Raised when both Gemini and LLaMA3 (Groq/Ollama) are unavailable."""


class LLMRouter:
    """
    Unified LLM gateway: Gemini primary -> LLaMA3 fallback.
    """

    def __init__(
        self,
        gemini_api_key: str | None = None,
        gemini_model: str | None = None,
        gemini_client: Any = None,
        groq_api_key: str | None = None,
        groq_model: str | None = None,
        groq_client: Any = None,
        ollama_base_url: str | None = None,
        ollama_model: str | None = None,
    ) -> None:
        self._gemini_api_key = gemini_api_key if gemini_api_key is not None else settings.GEMINI_API_KEY
        self._gemini_model = gemini_model or settings.GEMINI_MODEL
        self._gemini_client = gemini_client

        self._groq_api_key = groq_api_key if groq_api_key is not None else getattr(settings, "GROQ_API_KEY", "")
        self._groq_model = groq_model or getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
        self._groq_client = groq_client

        self._ollama_base_url = ollama_base_url or getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_model = ollama_model or getattr(settings, "OLLAMA_MODEL", "llama3")

    # ── Lazy client properties ───────────────────────────────────────────────

    @property
    def gemini_client(self) -> Any:
        if self._gemini_client is None and self._gemini_api_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=self._gemini_api_key)
            except Exception as e:
                logger.warning(f"Could not initialise Gemini client: {e}")
        return self._gemini_client

    @gemini_client.setter
    def gemini_client(self, value: Any) -> None:
        self._gemini_client = value

    @property
    def groq_client(self) -> Any:
        if self._groq_client is None and self._groq_api_key:
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=self._groq_api_key)
            except Exception as e:
                logger.warning(f"Could not initialise Groq client: {e}")
        return self._groq_client

    @groq_client.setter
    def groq_client(self, value: Any) -> None:
        self._groq_client = value

    # ── Public API ───────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        """
        Generate text: Gemini -> Groq LLaMA3 -> Ollama LLaMA3.
        """
        # 1. Try Gemini
        if self.gemini_client:
            res = self._gemini_generate(prompt, system, temperature)
            if res is not None:
                return res

        # 2. Try Groq LLaMA3
        if self.groq_client:
            res = self._groq_generate(prompt, system, temperature)
            if res is not None:
                return res

        # 3. Try Local Ollama LLaMA3
        res = self._ollama_generate(prompt, system, temperature)
        if res is not None:
            return res

        raise LLMUnavailableError(
            "All LLM backends (Gemini, Groq LLaMA3, Ollama LLaMA3) are unavailable."
        )

    def generate_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> BaseModel:
        """
        Generate structured Pydantic model: Gemini -> Groq LLaMA3 -> Ollama LLaMA3.
        """
        # 1. Try Gemini
        if self.gemini_client:
            res = self._gemini_generate_structured(prompt, schema, system, temperature)
            if res is not None:
                return res

        # 2. Try Groq LLaMA3
        if self.groq_client:
            res = self._groq_generate_structured(prompt, schema, system, temperature)
            if res is not None:
                return res

        # 3. Try Ollama LLaMA3
        res = self._ollama_generate_structured(prompt, schema, system, temperature)
        if res is not None:
            return res

        raise LLMUnavailableError(
            "All LLM backends (Gemini, Groq LLaMA3, Ollama LLaMA3) failed structured generation."
        )

    def active_backend(self) -> str:
        """Probe which backend is reachable."""
        if self.gemini_client:
            try:
                if self._gemini_generate("ping", None, 0.0) is not None:
                    return "gemini"
            except Exception:
                pass
        if self.groq_client:
            try:
                if self._groq_generate("ping", None, 0.0) is not None:
                    return "groq-llama3"
            except Exception:
                pass
        if self._check_ollama():
            return "ollama-llama3"
        return "none"

    # ── Gemini Implementations ───────────────────────────────────────────────

    def _is_retryable(self, err: str) -> bool:
        return any(sig in err for sig in _RETRY_SIGNALS)

    def _gemini_generate(
        self, prompt: str, system: str | None, temperature: float
    ) -> str | None:
        from google.genai import types

        config_kwargs: dict[str, Any] = {"temperature": temperature}
        if system:
            config_kwargs["system_instruction"] = system

        for attempt in range(_MAX_RETRIES):
            try:
                response = self.gemini_client.models.generate_content(
                    model=self._gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                return response.text or ""
            except Exception as e:
                err_str = str(e)
                if self._is_retryable(err_str) and attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_BASE * (attempt + 1)
                    logger.warning(
                        f"Gemini {self._gemini_model} temporary spike (attempt {attempt+1}/{_MAX_RETRIES}), waiting {wait}s: {e}"
                    )
                    time.sleep(wait)
                else:
                    logger.warning(f"Gemini {self._gemini_model} failed, triggering LLaMA3 fallback: {e}")
                    break
        return None

    def _gemini_generate_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system: str | None,
        temperature: float,
    ) -> BaseModel | None:
        from google.genai import types

        config_kwargs: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": schema,
            "temperature": temperature,
        }
        if system:
            config_kwargs["system_instruction"] = system

        for attempt in range(_MAX_RETRIES):
            try:
                response = self.gemini_client.models.generate_content(
                    model=self._gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                raw = response.text or "{}"
                parsed = json.loads(raw)
                return schema(**parsed)
            except Exception as e:
                err_str = str(e)
                if self._is_retryable(err_str) and attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_BASE * (attempt + 1)
                    logger.warning(
                        f"Gemini {self._gemini_model} structured rate limit (attempt {attempt+1}/{_MAX_RETRIES}), waiting {wait}s: {e}"
                    )
                    time.sleep(wait)
                else:
                    logger.warning(f"Gemini {self._gemini_model} structured failed, triggering LLaMA3 fallback: {e}")
                    break
        return None

    # ── Groq / LLaMA3 Implementations ────────────────────────────────────────

    def _groq_generate(
        self, prompt: str, system: str | None, temperature: float
    ) -> str | None:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Try designated Groq model (LLaMA3 or active fallback)
        models_to_try = [self._groq_model, "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "groq/compound-mini", "openai/gpt-oss-20b"]
        models_to_try = list(dict.fromkeys(m for m in models_to_try if m))

        for model in models_to_try:
            try:
                response = self.groq_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.warning(f"Groq fallback ({model}) failed: {e}")
                continue
        return None

    def _groq_generate_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system: str | None,
        temperature: float,
    ) -> BaseModel | None:
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        json_system = (
            (system + "\n\n" if system else "")
            + "IMPORTANT: You MUST respond with ONLY valid JSON matching this schema. "
            "Do NOT include Markdown fences (```), commentary, or extra text.\n\n"
            f"Schema:\n{schema_json}"
        )

        text = self._groq_generate(prompt, json_system, temperature)
        if not text:
            return None

        clean_json = text.strip()
        if clean_json.startswith("```"):
            clean_json = clean_json.split("```", 2)[-1] if clean_json.count("```") >= 2 else clean_json
            clean_json = clean_json.lstrip("json").strip().rstrip("```").strip()

        try:
            parsed = json.loads(clean_json)
            return schema(**parsed)
        except Exception as e:
            logger.warning(f"Groq JSON parse error: {e}")
            return None

    # ── Ollama Local LLaMA3 Implementations ──────────────────────────────────

    def _check_ollama(self) -> bool:
        try:
            res = httpx.get(f"{self._ollama_base_url}/api/tags", timeout=1.5)
            return res.status_code == 200
        except Exception:
            return False

    def _ollama_generate(
        self, prompt: str, system: str | None, temperature: float
    ) -> str | None:
        try:
            payload = {
                "model": self._ollama_model,
                "prompt": f"{system}\n\n{prompt}" if system else prompt,
                "stream": False,
                "options": {"temperature": temperature},
            }
            res = httpx.post(f"{self._ollama_base_url}/api/generate", json=payload, timeout=45.0)
            if res.status_code == 200:
                return res.json().get("response", "")
        except Exception as e:
            logger.debug(f"Local Ollama call skipped or failed: {e}")
        return None

    def _ollama_generate_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system: str | None,
        temperature: float,
    ) -> BaseModel | None:
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        json_system = (
            (system + "\n\n" if system else "")
            + f"Output strictly valid JSON matching this schema:\n{schema_json}"
        )
        try:
            payload = {
                "model": self._ollama_model,
                "prompt": f"{json_system}\n\n{prompt}",
                "format": "json",
                "stream": False,
                "options": {"temperature": temperature},
            }
            res = httpx.post(f"{self._ollama_base_url}/api/generate", json=payload, timeout=60.0)
            if res.status_code == 200:
                clean_json = res.json().get("response", "").strip()
                parsed = json.loads(clean_json)
                return schema(**parsed)
        except Exception as e:
            logger.debug(f"Local Ollama structured generation failed: {e}")
        return None

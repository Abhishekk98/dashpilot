"""Gemini provider (official google-genai SDK)."""

from __future__ import annotations

from pydantic import BaseModel

from .base import LLMNotConfiguredError, LLMProvider, LLMRateLimitError, LLMResponseError

GEMINI_KEY_HELP = "GEMINI_API_KEY is not set in backend/.env. Create a free key at https://aistudio.google.com/apikey"


def inline_refs(schema: dict) -> dict:
    """Replace $ref/$defs from Pydantic schemas with inline copies (safest for Gemini's schema support)."""
    defs = schema.get("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, client=None, timeout_s: float = 120, **kwargs):
        super().__init__(model, **kwargs)
        self.timeout_s = timeout_s
        if not api_key and client is None:
            raise LLMNotConfiguredError(GEMINI_KEY_HELP)
        self._api_key = api_key
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google import genai  # imported lazily so tests don't need network setup
            from google.genai import types

            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=int(self.timeout_s * 1000)),  # milliseconds
            )
        return self._client

    def _config(self, system: str | None, json_schema: type[BaseModel] | None):
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json" if json_schema else None,
            response_json_schema=inline_refs(json_schema.model_json_schema()) if json_schema else None,
        )

    def _call(self, contents, system: str | None, json_schema: type[BaseModel] | None) -> str:
        import httpx
        from google.genai import errors

        try:
            response = self.client.models.generate_content(
                model=self.model, contents=contents, config=self._config(system, json_schema)
            )
        except errors.APIError as exc:
            if exc.code == 429:
                raise LLMRateLimitError(f"Gemini rate limit / free-tier quota reached ({exc.message})") from exc
            if exc.code in (400, 401, 403) and "API key" in str(exc):
                raise LLMNotConfiguredError(f"Gemini rejected the API key: {exc.message}") from exc
            raise LLMResponseError(f"Gemini error {exc.code}: {exc.message}") from exc
        except httpx.TimeoutException as exc:
            raise LLMResponseError(f"Gemini did not answer within {self.timeout_s:.0f}s") from exc

        text = response.text
        if not text:
            reason = getattr(response.candidates[0], "finish_reason", None) if response.candidates else None
            raise LLMResponseError(f"Gemini returned no text (finish reason: {reason})")
        return text

    def _generate(self, prompt, system, json_schema):
        return self._call(prompt, system, json_schema)

    def _analyze_image(self, image, prompt, mime_type, json_schema):
        from google.genai import types

        return self._call([types.Part.from_bytes(data=image, mime_type=mime_type), prompt], None, json_schema)

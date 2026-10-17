"""Claude provider (anthropic SDK). Ready for when LLM_PROVIDER=claude."""

from __future__ import annotations

import base64

import anthropic

from .base import LLMNotConfiguredError, LLMProvider, LLMRateLimitError, LLMResponseError

# Server-side refusal fallback: if the model declines, the API retries on a fallback model.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(
        self,
        api_key: str,
        model: str,
        sdk_client: anthropic.Anthropic | None = None,
        timeout_s: float = 120,
        **kwargs,
    ):
        super().__init__(model, **kwargs)
        if not api_key and sdk_client is None:
            raise LLMNotConfiguredError("ANTHROPIC_API_KEY is not set in backend/.env")
        # Retries are handled by our backoff loop, not the SDK.
        self.sdk = sdk_client or anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=timeout_s)
        self.timeout_s = timeout_s

    def _create(self, content, system: str | None, json_schema) -> str:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": 16000,
            "betas": [_FALLBACK_BETA],
            "fallbacks": "default",
            "output_config": {"effort": "low"},
            "messages": [{"role": "user", "content": content}],
        }
        if system:
            kwargs["system"] = system
        if json_schema:
            kwargs["output_config"]["format"] = {
                "type": "json_schema",
                # Adds additionalProperties=false etc. as structured outputs require.
                "schema": anthropic.transform_schema(json_schema),
            }
        try:
            response = self.sdk.beta.messages.create(**kwargs)
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError("Claude rate limit reached") from exc
        except anthropic.AuthenticationError as exc:
            raise LLMNotConfiguredError("Claude rejected ANTHROPIC_API_KEY") from exc
        except anthropic.APITimeoutError as exc:
            raise LLMResponseError(f"Claude did not answer within {self.timeout_s:.0f}s") from exc
        except anthropic.APIStatusError as exc:
            raise LLMResponseError(f"Claude error {exc.status_code}: {exc.message}") from exc

        if response.stop_reason == "refusal":
            raise LLMResponseError("Claude declined this request")
        text = "".join(b.text for b in response.content if b.type == "text")
        if not text:
            raise LLMResponseError("Claude returned no text")
        return text

    def _generate(self, prompt, system, json_schema):
        return self._create(prompt, system, json_schema)

    def _analyze_image(self, image, prompt, mime_type, json_schema):
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": base64.b64encode(image).decode()}},
            {"type": "text", "text": prompt},
        ]
        return self._create(content, None, json_schema)

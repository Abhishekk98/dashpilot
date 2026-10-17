"""Provider-agnostic LLM interface. Every module calls this, never an SDK directly."""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TypeVar, overload

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")


class LLMError(RuntimeError):
    """Base class for all LLM layer errors."""


class LLMNotConfiguredError(LLMError):
    """The active provider has no API key."""


class LLMRateLimitError(LLMError):
    """Provider returned 429 / quota exhausted (after all retries)."""


class LLMResponseError(LLMError):
    """The provider answered, but not with usable output (refusal, empty, invalid JSON)."""


class LLMProvider(ABC):
    """Common interface implemented by GeminiProvider and ClaudeProvider."""

    name: str
    model: str

    def __init__(self, model: str, max_retries: int = 4, sleep: Callable[[float], None] = time.sleep):
        self.model = model
        self.max_retries = max_retries
        self._sleep = sleep  # injectable so tests do not wait

    # -- public API ---------------------------------------------------------
    @overload
    def generate_text(self, prompt: str, system: str | None = None, json_schema: None = None) -> str: ...
    @overload
    def generate_text(self, prompt: str, system: str | None = None, json_schema: type[T] = ...) -> T: ...

    def generate_text(self, prompt: str, system: str | None = None, json_schema: type[T] | None = None):
        """Text in, text out. With `json_schema` (a Pydantic model) the reply is JSON validated into it."""
        raw = self._with_retry(lambda: self._generate(prompt, system, json_schema))
        return self._validate(raw, json_schema) if json_schema else raw

    @overload
    def analyze_image(self, image: bytes, prompt: str, mime_type: str = "image/png", json_schema: None = None) -> str: ...
    @overload
    def analyze_image(self, image: bytes, prompt: str, mime_type: str = "image/png", json_schema: type[T] = ...) -> T: ...

    def analyze_image(self, image: bytes, prompt: str, mime_type: str = "image/png", json_schema: type[T] | None = None):
        """Vision: describe / extract from an image (used later for Stitch image imports)."""
        raw = self._with_retry(lambda: self._analyze_image(image, prompt, mime_type, json_schema))
        return self._validate(raw, json_schema) if json_schema else raw

    # -- provider hooks -----------------------------------------------------
    @abstractmethod
    def _generate(self, prompt: str, system: str | None, json_schema: type[BaseModel] | None) -> str:
        """Return raw text (JSON text when json_schema is given). Raise LLMRateLimitError on 429."""

    @abstractmethod
    def _analyze_image(self, image: bytes, prompt: str, mime_type: str, json_schema: type[BaseModel] | None) -> str:
        ...

    # -- shared helpers -----------------------------------------------------
    def _with_retry(self, call: Callable[[], R]) -> R:
        """Retry rate-limited calls with exponential backoff + jitter (1s, 2s, 4s, 8s...)."""
        for attempt in range(self.max_retries + 1):
            try:
                return call()
            except LLMRateLimitError:
                if attempt == self.max_retries:
                    raise
                delay = 2**attempt + random.uniform(0, 0.5)
                logger.warning("%s rate limited; retrying in %.1fs (attempt %d)", self.name, delay, attempt + 1)
                self._sleep(delay)
        raise AssertionError("unreachable")

    @staticmethod
    def _validate(raw: str, schema: type[T]) -> T:
        text = raw.strip()
        # Some models wrap JSON in ```json fences even when asked not to.
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        try:
            return schema.model_validate_json(text)
        except ValidationError as exc:
            raise LLMResponseError(f"Model reply did not match {schema.__name__}: {exc.errors()[:3]}") from exc

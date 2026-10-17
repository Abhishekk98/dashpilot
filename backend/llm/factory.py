"""Pick the active provider from settings (LLM_PROVIDER in backend/.env)."""

from __future__ import annotations

from fastapi import Depends

from app.config import Settings, get_settings

from .base import LLMProvider


def build_provider(settings: Settings) -> LLMProvider:
    """Create the configured provider. Raises LLMNotConfiguredError if its key is missing."""
    if settings.llm_provider == "claude":
        from .claude import ClaudeProvider

        return ClaudeProvider(
            settings.anthropic_api_key,
            settings.claude_model,
            max_retries=settings.llm_max_retries,
            timeout_s=settings.llm_timeout_seconds,
        )

    from .gemini import GeminiProvider

    return GeminiProvider(
        settings.gemini_api_key,
        settings.gemini_model,
        max_retries=settings.llm_max_retries,
        timeout_s=settings.llm_timeout_seconds,
    )


def get_llm(settings: Settings = Depends(get_settings)) -> LLMProvider | None:
    """FastAPI dependency: the active provider, or None when no key is configured (AI features degrade)."""
    if not settings.llm_configured:
        return None
    return build_provider(settings)

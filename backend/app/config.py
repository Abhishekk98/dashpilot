"""Application settings loaded from environment variables / backend/.env."""

from functools import lru_cache
from pathlib import Path

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DashPilot API"
    version: str = "0.1.0"

    # Active AI provider; every AI call goes through backend/llm/.
    llm_provider: Literal["gemini", "claude"] = "gemini"
    llm_max_retries: int = 4
    # Per-request timeout so a slow free-tier call can never hang profiling.
    llm_timeout_seconds: int = 120

    gemini_api_key: str = Field(default="", repr=False)
    gemini_model: str = "gemini-3.6-flash"

    anthropic_api_key: str = Field(default="", repr=False)
    claude_model: str = "claude-opus-5-5"

    # Where uploaded files and per-project JSON are kept (V1: local disk).
    storage_dir: Path = Path(__file__).resolve().parent.parent / "storage"
    max_upload_mb: int = 100

    # Stored as a comma-separated string so it can be set from a plain env var.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("gemini_model", "claude_model", mode="before")
    @classmethod
    def _blank_means_default(cls, value, info):
        # `GEMINI_MODEL=` (empty) in .env should fall back to the default model.
        return value or cls.model_fields[info.field_name].default

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalise_provider(cls, value):
        return (value or "gemini").strip().lower()

    @property
    def llm_model(self) -> str:
        return self.gemini_model if self.llm_provider == "gemini" else self.claude_model

    @property
    def llm_configured(self) -> bool:
        key = self.gemini_api_key if self.llm_provider == "gemini" else self.anthropic_api_key
        return bool(key)


@lru_cache
def get_settings() -> Settings:
    return Settings()

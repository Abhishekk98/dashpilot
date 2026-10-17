import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors
from pydantic import BaseModel

from app.config import Settings
from llm import LLMNotConfiguredError, LLMRateLimitError, LLMResponseError, build_provider
from llm.claude import ClaudeProvider
from llm.gemini import GeminiProvider
from tests.fakes import FakeProvider

BACKEND = Path(__file__).resolve().parent.parent

class Answer(BaseModel):
    status: str
    score: int

# --- shared behaviour (base class) ---------------------------------------------

def test_retry_with_exponential_backoff_then_success():
    llm = FakeProvider(replies=["OK"], errors=[LLMRateLimitError("429"), LLMRateLimitError("429")], max_retries=3)
    assert llm.generate_text("hi") == "OK"
    assert len(llm.calls) == 3
    assert 1 <= llm.sleeps[0] < 1.6 and 2 <= llm.sleeps[1] < 2.6  # 1s, 2s (+ jitter)

def test_retry_gives_up_after_max_retries():
    llm = FakeProvider(errors=[LLMRateLimitError("429")] * 5, max_retries=2)
    with pytest.raises(LLMRateLimitError):
        llm.generate_text("hi")
    assert len(llm.calls) == 3

def test_json_output_is_validated():
    llm = FakeProvider(replies=['```json\n{"status": "ok", "score": 3}\n```', '{"status": "ok"}'])
    assert llm.generate_text("x", json_schema=Answer) == Answer(status="ok", score=3)
    with pytest.raises(LLMResponseError):
        llm.generate_text("x", json_schema=Answer)

def test_analyze_image_passes_bytes():
    llm = FakeProvider(replies=["a chart"])
    assert llm.analyze_image(b"png", "describe", mime_type="image/png") == "a chart"
    assert llm.calls[0]["image"] == b"png"

# --- factory -------------------------------------------------------------------

def test_factory_picks_provider_and_reports_missing_key():
    assert isinstance(build_provider(Settings(llm_provider="gemini", gemini_api_key="k")), GeminiProvider)
    claude = build_provider(Settings(llm_provider="claude", anthropic_api_key="k", claude_model=""))
    assert isinstance(claude, ClaudeProvider) and claude.model == "claude-opus-5-5"

    with pytest.raises(LLMNotConfiguredError, match="aistudio.google.com"):
        build_provider(Settings(llm_provider="gemini", gemini_api_key=""))
    with pytest.raises(LLMNotConfiguredError, match="ANTHROPIC_API_KEY"):
        build_provider(Settings(llm_provider="claude", anthropic_api_key=""))

def test_blank_model_in_env_uses_default():
    assert Settings(gemini_model="").gemini_model == "gemini-3.6-flash"

# --- Gemini provider (fake google-genai client) -------------------------------------

class FakeGeminiModels:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome, candidates=[])

def _gemini(outcomes):
    models = FakeGeminiModels(outcomes)
    provider = GeminiProvider("", "gemini-test", client=SimpleNamespace(models=models), sleep=lambda s: None)
    return provider, models

def test_gemini_json_and_system_prompt():
    provider, models = _gemini(['{"status": "ok", "score": 1}'])
    assert provider.generate_text("q", system="be brief", json_schema=Answer).score == 1
    config = models.calls[0]["config"]
    assert models.calls[0]["model"] == "gemini-test"
    assert config.system_instruction == "be brief"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema["required"] == ["status", "score"]

def test_gemini_schema_has_no_refs():
    from core.semantic_roles import RoleAnswer
    from llm.gemini import inline_refs

    schema = inline_refs(RoleAnswer.model_json_schema())
    assert "$ref" not in str(schema) and "$defs" not in schema
    assert "role" in schema["properties"]["columns"]["items"]["properties"]


def test_gemini_429_is_retried():
    rate_limited = genai_errors.ClientError(429, {"error": {"message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}})
    provider, models = _gemini([rate_limited, "OK"])
    assert provider.generate_text("Reply with OK") == "OK"
    assert len(models.calls) == 2

def test_gemini_empty_reply_is_an_error():
    provider, _ = _gemini([None])
    with pytest.raises(LLMResponseError):
        provider.generate_text("x")

# --- Claude provider (fake anthropic client) -------------------------------------------

class FakeClaudeMessages:
    def __init__(self, response):
        self.response, self.calls = response, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

def test_claude_provider_text_and_json_schema():
    response = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text='{"status":"ok","score":2}')])
    messages = FakeClaudeMessages(response)
    provider = ClaudeProvider("", "claude-opus-5-5", sdk_client=SimpleNamespace(beta=SimpleNamespace(messages=messages)))
    assert provider.generate_text("q", json_schema=Answer).status == "ok"
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"]["schema"]["additionalProperties"] is False

def test_claude_refusal_is_an_error():
    response = SimpleNamespace(stop_reason="refusal", content=[])
    sdk = SimpleNamespace(beta=SimpleNamespace(messages=FakeClaudeMessages(response)))
    with pytest.raises(LLMResponseError):
        ClaudeProvider("", "m", sdk_client=sdk).generate_text("q")

# --- architecture rule -------------------------------------------------------------------

def test_only_llm_package_imports_provider_sdks():
    """All modules must go through backend/llm/, never google-genai or anthropic directly."""
    offenders = []
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND)
        if rel.parts[0] in ("llm", "tests", ".venv"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            )
            if any(n.startswith(("anthropic", "google.genai", "google")) for n in names):
                offenders.append(str(rel))
    assert offenders == []


def test_gemini_timeout_is_a_clear_error():
    import httpx

    provider, _ = _gemini([httpx.ReadTimeout("slow")])
    provider.timeout_s = 30
    with pytest.raises(LLMResponseError, match="within 30s"):
        provider.generate_text("x")

from fastapi.testclient import TestClient

from app.api.routes import llm as llm_route
from app.config import Settings, get_settings
from app.main import app
from llm import LLMRateLimitError
from tests.fakes import FakeProvider


def _client(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_llm_test_reports_missing_key():
    try:
        res = _client(Settings(llm_provider="gemini", gemini_api_key="")).get("/api/llm/test")
        assert res.status_code == 503
        assert "GEMINI_API_KEY" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_llm_test_returns_reply(monkeypatch):
    monkeypatch.setattr(llm_route, "build_provider", lambda s: FakeProvider(replies=[" OK\n"]))
    try:
        body = _client(Settings(gemini_api_key="k")).get("/api/llm/test").json()
        assert body["response"] == "OK" and body["provider"] == "fake" and body["model"] == "fake-model"
    finally:
        app.dependency_overrides.clear()


def test_llm_test_rate_limited(monkeypatch):
    monkeypatch.setattr(llm_route, "build_provider", lambda s: FakeProvider(errors=[LLMRateLimitError("quota")] * 5))
    try:
        assert _client(Settings(gemini_api_key="k")).get("/api/llm/test").status_code == 429
    finally:
        app.dependency_overrides.clear()

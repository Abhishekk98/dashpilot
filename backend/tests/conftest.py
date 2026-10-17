from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from llm import get_llm

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "sales"


@pytest.fixture
def sample_bytes():
    return {name: (SAMPLES / name).read_bytes() for name in ("orders.csv", "customers.xlsx", "products.csv")}


@pytest.fixture
def api(tmp_path):
    """TestClient with isolated storage and no AI key (rule-based roles only)."""
    settings = Settings(storage_dir=tmp_path, gemini_api_key="", anthropic_api_key="", max_upload_mb=1)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_llm] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()

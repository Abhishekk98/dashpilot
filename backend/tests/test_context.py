"""Business context: storage, logo upload, and the three AI helpers with and without a provider."""

import json

import pytest
from pydantic import ValidationError

from app.main import app
from core.context import BrandPalette, BusinessContext, harmonic_palette, svg_accent
from llm import LLMRateLimitError, get_llm
from tests.fakes import FakeProvider

SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="#E4572E"/><circle fill="#e4572e"/><path fill="#111111"/></svg>'


def _project(api, sample_bytes):
    pid = api.post("/api/projects", json={"name": "Sales Q1"}).json()["id"]
    api.post(f"/api/projects/{pid}/files", files=[("files", ("orders.csv", sample_bytes["orders.csv"], "text/csv"))])
    return pid


def _use_llm(provider):
    app.dependency_overrides[get_llm] = lambda: provider


# --- pure functions -------------------------------------------------------------------

def test_palette_validation_and_rules():
    assert BrandPalette(accent="f8c").accent == "#FF88CC"
    with pytest.raises(ValidationError):
        BrandPalette(accent="yellow")
    p = harmonic_palette("#F8CF4B")
    assert p.accent == "#F8CF4B" and p.growth == "#4CAF7A"
    assert all(len(c) == 7 for c in p.model_dump().values())
    assert harmonic_palette("#22AA44").growth == "#2E9C9C"  # green accent -> teal growth


def test_svg_accent_ignores_neutrals():
    assert svg_accent(SVG) == "#E4572E"
    assert svg_accent(b'<svg><rect fill="#000000"/></svg>') is None


def test_context_rejects_unknown_choices():
    with pytest.raises(ValidationError):
        BusinessContext(industries=["Space Mining"])
    assert BusinessContext(industries=["Retail", "Retail"]).industries == ["Retail"]


# --- API --------------------------------------------------------------------------------

def test_context_defaults_save_and_reload(api, sample_bytes):
    pid = _project(api, sample_bytes)
    ctx = api.get(f"/api/projects/{pid}/context").json()
    assert ctx["company_name"] == "Sales Q1" and ctx["updated_at"] is None
    assert ctx["archetype"] == "light_elegant" and ctx["palette"]["accent"] == "#F8CF4B"

    ctx.update(company_name="Acme", industries=["E-commerce"], audiences=["Sales Teams"], mode="dark", archetype="neon_tech")
    saved = api.put(f"/api/projects/{pid}/context", json=ctx).json()
    assert saved["updated_at"] and saved["mode"] == "dark"
    assert api.get(f"/api/projects/{pid}/context").json()["company_name"] == "Acme"

    bad = {**ctx, "industries": ["Space Mining"]}
    assert api.put(f"/api/projects/{pid}/context", json=bad).status_code == 422


def test_logo_upload_serve_and_delete(api, sample_bytes):
    pid = _project(api, sample_bytes)
    res = api.post(f"/api/projects/{pid}/context/logo", files={"file": ("brand.svg", SVG, "image/svg+xml")})
    assert res.status_code == 200 and res.json()["logo"]["content_type"] == "image/svg+xml"

    logo = api.get(f"/api/projects/{pid}/context/logo")
    assert logo.content == SVG and "default-src 'none'" in logo.headers["content-security-policy"]

    # Saving the form keeps the logo; the palette helper reads the SVG's brand color.
    ctx = api.get(f"/api/projects/{pid}/context").json()
    assert api.put(f"/api/projects/{pid}/context", json={**ctx, "logo": None}).json()["logo"]
    pal = api.post(f"/api/projects/{pid}/context/palette", json={"accent": "#F8CF4B"}).json()
    assert pal["palette"]["accent"] == "#E4572E" and pal["source"] == "rules"

    assert api.post(f"/api/projects/{pid}/context/logo", files={"file": ("x.gif", b"GIF", "image/gif")}).status_code == 422
    big = b"0" * (2 * 1024 * 1024 + 1)
    assert api.post(f"/api/projects/{pid}/context/logo", files={"file": ("x.png", big, "image/png")}).status_code == 422

    assert api.delete(f"/api/projects/{pid}/context/logo").json()["logo"] is None
    assert api.get(f"/api/projects/{pid}/context/logo").status_code == 404


def test_rule_based_helpers_without_key(api, sample_bytes):
    pid = _project(api, sample_bytes)
    s = api.post(f"/api/projects/{pid}/context/suggest").json()
    assert s["source"] == "rules" and "E-commerce" in s["industries"]
    assert "Executive Leadership" in s["audiences"] and "gross_revenue" in s["goals"]

    polished = api.post(f"/api/projects/{pid}/context/polish", json={"goals": "track sales"}).json()
    assert polished == {"goals": "track sales", "source": "rules", "note": polished["note"]} and polished["note"]

    empty = api.post("/api/projects", json={}).json()["id"]
    assert api.post(f"/api/projects/{empty}/context/suggest").status_code == 422
    assert api.post(f"/api/projects/{pid}/context/palette", json={"accent": "nope"}).status_code == 422


def test_ai_helpers_use_provider_and_filter_answers(api, sample_bytes):
    replies = [
        json.dumps({"industries": ["E-commerce", "Space Mining"], "audiences": ["Sales Teams"], "goals": "Grow GMV.", "domain_score": 91}),
        json.dumps({"accent": "#0057B8", "base": "#111111", "muted": "#6B7280", "canvas": "#F7F7F5", "growth": "#2E9C5A", "rationale": "Blue brand."}),
        json.dumps({"goals": "Track gross_revenue by destination_city month over month."}),
    ]
    llm = FakeProvider(replies=replies)
    _use_llm(llm)
    pid = _project(api, sample_bytes)

    s = api.post(f"/api/projects/{pid}/context/suggest").json()
    assert s["source"] == "ai" and s["industries"] == ["E-commerce"] and s["domain_score"] == 91
    pal = api.post(f"/api/projects/{pid}/context/palette", json={"accent": "#0057B8"}).json()
    assert pal["source"] == "ai" and pal["palette"]["canvas"] == "#F7F7F5"
    pol = api.post(f"/api/projects/{pid}/context/polish", json={"goals": "sales by city"}).json()
    assert pol["source"] == "ai" and "gross_revenue" in pol["goals"]
    assert len(llm.calls) == 3 and "orders" in llm.calls[0]["prompt"]


def test_ai_failures_fall_back_to_rules(api, sample_bytes):
    llm = FakeProvider(errors=[LLMRateLimitError("quota")] * 3, max_retries=0)
    _use_llm(llm)
    pid = _project(api, sample_bytes)
    s = api.post(f"/api/projects/{pid}/context/suggest").json()
    assert s["source"] == "rules" and s["note"] == "quota"
    pal = api.post(f"/api/projects/{pid}/context/palette", json={"accent": "#F8CF4B"}).json()
    assert pal["source"] == "rules" and pal["note"]
    pol = api.post(f"/api/projects/{pid}/context/polish", json={"goals": "sales"}).json()
    assert pol["goals"] == "sales" and pol["note"] == "quota"

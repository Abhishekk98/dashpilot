"""Design method C: image validation, style profile (Pillow + vision), themed variants, API flow.
Reference images are generated here (Pillow drawings and rendered templates) — never client data."""

import io
import json

import pytest
from PIL import Image, ImageDraw

from core.context import BrandPalette, BusinessContext
from core.design_ai import template_html
from core.design_contract import check, render_page
from core.design_option_c import generate_variants, theme, variant_template
from core.planner import page_plan
from core.style_profile import StyleError, build_profile, open_image, pillow_profile, sniff
from llm.base import LLMRateLimitError
from tests.fakes import FakeProvider
from tests.test_design_import import _browser
from tests.test_insights import _project
from tests.test_planner import SAMPLES, _ctx, _plan

BLUE = BusinessContext(company_name="Acme", palette=BrandPalette(accent="#3B82F6", base="#0F172A", muted="#64748B", canvas="#EEF2F7", growth="#10B981"))


def _png(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def neon_dashboard() -> Image.Image:
    """Dark gradient canvas, outlined purple panels with pink bars."""
    img = Image.new("RGB", (1280, 720))
    d = ImageDraw.Draw(img)
    for y in range(720):
        t = y / 719
        d.line([(0, y), (1279, y)], fill=(int(20 + 22 * t), int(11 + 4 * t), int(46 + 33 * t)))
    for i in range(8):
        x, y = 24 + (i % 4) * 312, 90 + (i // 4) * 300
        d.rounded_rectangle([x, y, x + 296, y + 270], radius=8, outline=(168, 85, 247), width=3)
        d.rectangle([x + 20, y + 200, x + 200, y + 222], fill=(236, 72, 153))
    return img


def light_dashboard() -> Image.Image:
    """Grey canvas, white cards, blue KPI bars and charts."""
    img = Image.new("RGB", (1280, 720), (238, 242, 247))
    d = ImageDraw.Draw(img)
    for i in range(6):
        x, y = 24 + (i % 3) * 416, 72 + (i // 3) * 320
        d.rounded_rectangle([x, y, x + 400, y + 300], radius=20, fill=(255, 255, 255))
        d.rectangle([x + 24, y + 200, x + 24 + 60 * (i + 1) % 340, y + 230], fill=(59, 130, 246))
        d.text((x + 24, y + 20), "Revenue", fill=(15, 23, 42))
    return img


@pytest.fixture(scope="module")
def plan():
    whole = _plan(_ctx({n: (SAMPLES / n).read_bytes() for n in ("orders.csv", "customers.xlsx", "products.csv")}))[0]
    return page_plan(whole, 1)  # templates are made per page


# --- image validation ------------------------------------------------------------------------------

def test_image_type_is_checked_by_content():
    img = light_dashboard()
    for fmt, kind, mime in (("PNG", "PNG", "image/png"), ("JPEG", "JPEG", "image/jpeg"), ("WEBP", "WEBP", "image/webp")):
        data = _png(img, fmt)
        assert sniff(data) == kind and open_image(data)[1] == mime
    with pytest.raises(StyleError, match="PNG, JPG or WebP"):
        open_image(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")  # an SVG renamed to .png is still not an image we read
    with pytest.raises(StyleError, match="10 MB"):
        open_image(b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024 + 1))
    with pytest.raises(StyleError, match="too small"):
        open_image(_png(Image.new("RGB", (100, 80))))
    with pytest.raises(StyleError, match="could not be read"):
        open_image(b"\x89PNG\r\n\x1a\n" + b"garbage" * 20)


# --- deterministic profile --------------------------------------------------------------------------

def test_pillow_profile_dark_neon():
    p = pillow_profile(neon_dashboard())
    assert p.mode == "dark" and p.background.type == "gradient" and p.source == "pillow"
    assert {p.palette.primary, *p.palette.accents} >= {"#A855F7", "#EC4899"}
    assert p.card_style == "outlined"  # panels have no fill of their own


def test_pillow_profile_light_cards():
    p = pillow_profile(light_dashboard())
    assert p.mode == "light" and p.card_color == "#FFFFFF" and p.background.colors == ["#EEF2F7"]
    assert p.palette.primary == "#3B82F6" and p.card_style == "elevated"


@pytest.mark.skipif(not _browser(), reason="needs Playwright with Edge/Chrome")
def test_profile_round_trip_from_rendered_design(plan):
    png = render_page(template_html(plan, BLUE, "dark_futuristic"), lambda pg: pg.screenshot(clip={"x": 0, "y": 0, "width": 1280, "height": 720}))
    p = pillow_profile(open_image(png)[0])
    assert p.mode == "dark" and p.palette.primary == "#3B82F6" and p.palette.text == "#F2F0F0"


# --- vision layer ---------------------------------------------------------------------------------

def test_vision_refines_style_and_falls_back():
    data = _png(light_dashboard())
    reply = {"card_style": "glass", "radius_px": 64, "shadow": "deep", "font_character": "serif", "spacing": "airy",
             "layout_pattern": "kpi-row-top + 2x3 charts"}
    llm = FakeProvider(replies=[json.dumps(reply)])
    p, mime, _, note = build_profile(data, llm)
    assert note is None and p.source == "ai" and (p.card_style, p.radius_px, p.shadow, p.font_character, p.spacing) == ("glass", 40, "deep", "serif", "airy")
    assert p.palette.primary == "#3B82F6"  # colors stay deterministic
    assert "image" in llm.calls[0] and "never" not in reply["layout_pattern"]

    bad = FakeProvider(replies=[json.dumps({**reply, "card_style": "holographic"})] * 3)
    p, _, _, note = build_profile(data, bad)
    assert p.source == "pillow" and "unavailable" in note
    p, _, _, note = build_profile(data, FakeProvider(errors=[LLMRateLimitError("quota exhausted")], max_retries=0))
    assert p.source == "pillow" and "quota exhausted" in note
    p, _, _, note = build_profile(data, None)
    assert p.source == "pillow" and "No AI key" in note


# --- variants -----------------------------------------------------------------------------------

PROFILES = [
    pillow_profile(neon_dashboard()).model_copy(update={"card_style": "glass", "shadow": "glow", "font_character": "mono"}),
    pillow_profile(light_dashboard()).model_copy(update={"card_style": "outlined", "radius_px": 0, "font_character": "serif"}),
    pillow_profile(light_dashboard()),
]


@pytest.mark.parametrize("profile", PROFILES)
def test_profile_templates_pass_the_contract(plan, profile):
    for vid in ("reference_close", "reference_brand"):
        html = variant_template(plan, BLUE, profile, vid)
        assert check(html, plan, prefer_browser=False)[0] == []
    t = theme(profile, "#3B82F6")
    assert t["radius"] == f"{profile.radius_px}px" and (t["blur"] != "none") == (profile.card_style == "glass")


def test_brand_variant_uses_brand_accent(plan):
    profile = PROFILES[0]
    close, brand = (variant_template(plan, BLUE, profile, v) for v in ("reference_close", "reference_brand"))
    assert profile.palette.primary in close and "#3B82F6" in brand


def test_variants_ai_retry_and_template_fallback(plan):
    profile = PROFILES[2]
    good = variant_template(plan, BLUE, profile, "reference_close").replace("<title>", "<title>AI ")
    llm = FakeProvider(replies=[json.dumps({"html": good})] + [json.dumps({"html": "<p>x</p>"})] * 3)
    close, brand = generate_variants(plan, BLUE, profile, llm, prefer_browser=False)
    assert close.source == "ai" and close.valid and close.id == "reference_close"
    assert brand.source == "template" and brand.attempts == 3 and "profile-themed template" in brand.note
    assert "Reference style" in llm.calls[0]["prompt"] and "never a layout" in llm.calls[0]["prompt"]

    quota = FakeProvider(errors=[LLMRateLimitError("quota exhausted")], max_retries=0)
    variants = generate_variants(plan, BLUE, profile, quota, prefer_browser=False)
    assert [v.source for v in variants] == ["template", "template"] and len(quota.calls) == 1
    assert "skipped" in variants[1].note


# --- API ------------------------------------------------------------------------------------------

def test_option_c_api_flow(api, sample_bytes):
    pid = _project(api, sample_bytes)
    assert api.get(f"/api/projects/{pid}/plan").json()["plan"]["valid"]
    assert api.post(f"/api/projects/{pid}/design/reference/variants").status_code == 422  # no image yet
    bad = api.post(f"/api/projects/{pid}/design/reference", files={"file": ("ref.png", b"not an image at all", "image/png")})
    assert bad.status_code == 422

    res = api.post(f"/api/projects/{pid}/design/reference", files={"file": ("ref.webp", _png(neon_dashboard(), "WEBP"), "image/webp")})
    assert res.status_code == 200, res.text
    state = res.json()["state"]
    assert state["image"]["mime"] == "image/webp" and state["profile"]["mode"] == "dark" and res.json()["notes"]
    assert api.get(f"/api/projects/{pid}/design/reference/image").headers["content-type"] == "image/webp"

    profile = {**state["profile"], "radius_px": 24, "card_style": "glass"}
    state = api.put(f"/api/projects/{pid}/design/reference/profile", json=profile).json()["state"]
    assert state["edited"] and state["profile"]["radius_px"] == 24
    assert api.put(f"/api/projects/{pid}/design/reference/profile", json={**profile, "card_color": "blue"}).status_code == 422

    state = api.post(f"/api/projects/{pid}/design/reference/variants").json()["state"]
    assert [v["id"] for v in state["variants"]] == ["reference_close", "reference_brand"]
    assert all(v["valid"] and v["source"] == "template" for v in state["variants"]) and not state["stale"]

    sel = api.post(f"/api/projects/{pid}/design/select", json={"id": "reference_brand"}).json()["design"]
    assert sel["selected"] == "reference_brand" and sel["selected_method"] == "C"
    assert sel["selected_label"] == "Option C · Reference + Brand Colors" and not sel["selected_stale"]

    # New Option B variants do not drop the Option C selection.
    design = api.post(f"/api/projects/{pid}/design/variants").json()["design"]
    assert design["selected"] == "reference_brand" and design["selected_method"] == "C"

    # Editing the profile makes the C designs (and the selection) stale.
    api.put(f"/api/projects/{pid}/design/reference/profile", json={**profile, "radius_px": 8})
    assert api.get(f"/api/projects/{pid}/design/reference").json()["state"]["stale"]
    assert api.get(f"/api/projects/{pid}/plan").json()["design"]["selected_stale"]


@pytest.mark.skipif(not _browser(), reason="needs Playwright with Edge/Chrome")
def test_option_c_feeds_design_import(api, sample_bytes):
    pid = _project(api, sample_bytes)
    api.get(f"/api/projects/{pid}/plan")
    api.post(f"/api/projects/{pid}/design/reference", files={"file": ("ref.png", _png(light_dashboard()), "image/png")})
    api.post(f"/api/projects/{pid}/design/reference/variants")
    api.post(f"/api/projects/{pid}/design/select", json={"id": "reference_close"})
    d = api.get(f"/api/projects/{pid}/design/import").json()["design"]
    assert d["source"] == "option_c" and d["source_name"] == "Option C · Close to Reference" and d["valid"]
    assert {m["method"] for m in d["mapping"]} == {"id"}

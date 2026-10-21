"""Design method A (Google Stitch): export reading, prompt, exact import (Tailwind/fonts/icons, scaling,
geometric hiding, Stitch theme), fidelity report + build gate, API flow, fuzz on Stitch-like pages.
Stitch exports here are written by tests.stitch_like (Tailwind CDN + Material Symbols, fake charts)."""

import io
import json
import zipfile

import numpy as np
import pytest
from PIL import Image, ImageDraw

from core.context import BusinessContext
from core.design_fidelity import score
from core.design_import import build_theme, extract, match, render_design, validate_mapping
from core.planner import DashboardPlan, page_plan
from core.stitch_import import StitchError, read_export
from core.stitch_prompt import build as build_prompt
from tests.stitch_like import stitch_export
from tests.test_cleaning_fuzz import dataset
from tests.test_design_import import _browser
from tests.test_insights import _project
from tests.test_planner import CTX, SAMPLES, _ctx, _plan

needs_browser = pytest.mark.skipif(not _browser(), reason="needs Playwright with Edge/Chrome (and network for the Tailwind CDN)")


@pytest.fixture(scope="module")
def plan():
    return page_plan(_plan(_ctx({n: (SAMPLES / n).read_bytes() for n in ("orders.csv", "customers.xlsx", "products.csv")}))[0], 1)


def _zip(files: dict[str, bytes], symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, "/etc/passwd")
    return buf.getvalue()


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# --- export reading ---------------------------------------------------------------------------

def test_read_html_and_zip_exports():
    page = b"<!doctype html><html><body><div>Dashboard</div></body></html>"
    assert read_export("code.html", page).html.startswith("<!doctype")
    shot = _png(Image.new("RGB", (1280, 720), (240, 240, 240)))
    exp = read_export("stitch_export.zip", _zip({"my_design/code.html": page, "my_design/screen.png": shot, "my_design/notes.txt": b"x"}))
    assert exp.screen == shot and "my_design/code.html" in exp.files and exp.name == "stitch_export.zip"
    assert read_export("x.zip", _zip({"code.html": page, "screen.png": b"not a png"})).screen is None  # broken screenshot ignored


@pytest.mark.parametrize("files, symlink, message", [
    ({"../evil.html": b"<div>x</div>"}, None, "unsafe path"),
    ({"/abs/code.html": b"<div>x</div>"}, None, "unsafe path"),
    ({"C:/win/code.html": b"<div>x</div>"}, None, "unsafe path"),
    ({"code.html": b"<div>x</div>"}, "link.html", "symbolic link"),
    ({"a.html": b"<div>a</div>", "b.html": b"<div>b</div>"}, None, "several HTML"),
    ({"readme.txt": b"hi"}, None, "no HTML"),
    ({"code.html": b"<div>" + b"0" * (30 * 1024 * 1024) + b"</div>"}, None, "zip bomb|5 MB"),
])
def test_unsafe_or_wrong_zips_are_rejected(files, symlink, message):
    with pytest.raises(StitchError, match=message):
        read_export("export.zip", _zip(files, symlink))


def test_other_files_are_rejected():
    with pytest.raises(StitchError, match="code.html or its export .zip"):
        read_export("design.png", _png(Image.new("RGB", (300, 200))))
    with pytest.raises(StitchError, match="does not look like an HTML page"):
        read_export("code.html", b"just text")


# --- prompt -----------------------------------------------------------------------------------

def test_prompt_has_exact_layout_and_rules(plan):
    ctx = BusinessContext(company_name="Shop Co", industries=["E-commerce"], audiences=["Executive Leadership"])
    p = build_prompt(plan, ctx, "dark_futuristic", ["Which city drives revenue?"])
    text = p.prompt
    for v in plan.visuals:
        assert f'"{v.title}"' in text and f"x {v.box.x}, y {v.box.y}, {v.box.w}×{v.box.h}px" in text
    assert "1280px wide and 720px tall" in text and "EXACTLY as written" in text and "Segoe UI" in text
    assert "Dark Futuristic" in text and "Which city drives revenue?" in text and ctx.palette.accent in text
    assert {s["id"] for s in p.styles} >= {"dark_futuristic", "light_elegant", "glassmorphism", "minimal_corporate", "neon_tech"}


# --- exact import -------------------------------------------------------------------------------

def _import(plan, html, screen=None):
    found = extract(html, True)
    mapping, _ = match(plan, found.boxes)
    original, background = render_design(html, [m.box_id for m in mapping if m.box_id], True)
    titles = {v.id: v.title for v in plan.visuals}
    return found, mapping, original, background, score(original, background, found.boxes, mapping, titles, screen,
                                                      found.source_w, found.source_h, found.scale)


def _red(png: bytes) -> int:
    a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(int)
    return int(((a[..., 0] > 200) & (a[..., 1] < 70) & (a[..., 2] < 70)).sum())


@needs_browser
def test_stitch_export_imports_exactly(plan):
    html = stitch_export(plan, accent="#E11D2E")
    found, mapping, original, background, report = _import(plan, html)
    assert {m.method for m in mapping} == {"title"} and validate_mapping(plan, mapping, found.boxes) == []
    assert found.scale == 1.0 and not any("expand_more" in b.title or "trending_up" in b.title for b in found.boxes)  # icon ligatures ignored
    # Fake bars, deltas and area charts (red accent) are gone from every chart and KPI card; the red
    # logo tile and the Key Insights accent border are static design and stay.
    bg = np.asarray(Image.open(io.BytesIO(background)).convert("RGB")).astype(int)
    red = (bg[..., 0] > 200) & (bg[..., 1] < 70) & (bg[..., 2] < 70)
    for v in plan.visuals:
        if v.role in ("chart", "kpi"):
            assert red[v.box.y:v.box.y + v.box.h, v.box.x:v.box.x + v.box.w].sum() == 0, v.title
    assert _red(original) > 5000 and red[:62, :80].sum() > 1000
    assert report.passed and report.overall >= 0.999 and report.reference == "render"
    # Static labels beside titles ("Last 12 months") and the header stay pixel-identical.
    o, b = (np.asarray(Image.open(io.BytesIO(p)).convert("RGB")).astype(int) for p in (original, background))
    chart = next(v for v in plan.visuals if v.role == "chart")
    row = (slice(chart.box.y, chart.box.y + 40), slice(chart.box.x, chart.box.x + chart.box.w))
    assert np.abs(o[row] - b[row]).max() == 0 and np.abs(o[:62, :600] - b[:62, :600]).max() == 0
    theme = build_theme("Shop", found.palette, CTX.palette, found)
    assert theme["dataColors"][0] == "#E11D2E" and theme["textClasses"]["callout"]["color"] == "#1B1C1C"


@needs_browser
def test_larger_stitch_page_is_scaled_and_noted(plan):
    found, mapping, _, _, report = _import(plan, stitch_export(plan, dark=True, accent="#3B82F6", size=(1440, 900)))
    assert found.scale == 0.8 and (found.source_w, found.source_h) == (1440, 900)
    assert validate_mapping(plan, mapping, found.boxes) == [] and report.passed
    assert any("scaled to 80%" in n for n in report.notes)
    assert found.value_color == "#F2F0F0" and "#3B82F6" in found.chart_colors


@needs_browser
def test_fidelity_against_stitch_screenshot(plan):
    html = stitch_export(plan)
    _, _, original, _, _ = _import(plan, html)
    found, mapping, original, background, report = _import(plan, html, screen=original)
    assert report.reference == "screenshot" and report.render_match >= 0.999 and report.passed

    # Stitch's screenshot differs (a different header and one card title): the report must catch it.
    shot = Image.open(io.BytesIO(original)).convert("RGB")
    d = ImageDraw.Draw(shot)
    d.rectangle([20, 10, 700, 60], fill=(200, 30, 30))
    kpi = next(v for v in plan.visuals if v.role == "kpi")
    d.rectangle([kpi.box.x, kpi.box.y, kpi.box.x + kpi.box.w, kpi.box.y + 30], fill=(30, 30, 200))
    bad = score(original, background, found.boxes, mapping, {v.id: v.title for v in plan.visuals}, _png(shot))
    assert not bad.passed and bad.overall < 0.99
    failing = [c.title for c in bad.cards if not c.passed]
    assert kpi.title in failing and bad.render_match < 0.99


# --- API ----------------------------------------------------------------------------------------------

@needs_browser
def test_option_a_flow_and_fidelity_gate(api, sample_bytes):
    pid = _project(api, sample_bytes)
    whole = DashboardPlan.model_validate(api.get(f"/api/projects/{pid}/plan").json()["plan"])
    assert whole.pages == ["Overview", "Details"]
    plan = page_plan(whole, 1).model_dump(mode="json")
    prompt = api.get(f"/api/projects/{pid}/design/stitch/prompt?style=neon_tech").json()
    assert prompt["style"] == "neon_tech" and all(v["title"] in prompt["prompt"] for v in plan["visuals"])

    html = stitch_export(page_plan(whole, 1))
    res = api.post(f"/api/projects/{pid}/design/stitch", files={"file": ("stitch_shop.zip", _zip({"stitch_shop/code.html": html.encode()}), "application/zip")})
    assert res.status_code == 200, res.text
    state = res.json()
    assert state["upload"]["label"] == "Option A · Google Stitch (stitch_shop.zip)" and not state["upload"]["has_screen"]
    d = state["design"]
    assert d["source"] == "option_a" and d["valid"] and d["fidelity"]["passed"] and {m["method"] for m in d["mapping"]} == {"title"}

    sel = api.post(f"/api/projects/{pid}/design/select", json={"id": "stitch"}).json()["design"]
    assert sel["selected_method"] == "A" and sel["selected_label"].startswith("Option A")
    assert "page 2" in api.get(f"/api/projects/{pid}/build").json()["blockers"][0]  # one export per page
    p2 = api.post(f"/api/projects/{pid}/design/stitch?page=2",
                  files={"file": ("details.zip", _zip({"d/code.html": stitch_export(page_plan(whole, 2)).encode()}), "application/zip")}).json()
    assert p2["page"] == 2 and p2["uploads"] == [True, True] and p2["design"]["valid"] and p2["upload"]["label"] == state["upload"]["label"]
    imp = api.get(f"/api/projects/{pid}/design/import").json()
    assert imp["design"]["source"] == "option_a" and imp["design"]["source_hash"] == d["source_hash"]  # reused, not re-imported
    assert api.get(f"/api/projects/{pid}/design/original.png").status_code == 200
    assert api.post(f"/api/projects/{pid}/build", json={}).json()["build"]["valid"]

    # KPI values the design draws left-aligned stay left-aligned in Power BI: a multi-row card that starts
    # where the design's number starts, in its size/weight/color, bound to a hidden compact display measure.
    z = zipfile.ZipFile(io.BytesIO(api.get(f"/api/projects/{pid}/build/download").content))
    visuals = [json.loads(z.read(n)) for n in z.namelist() if n.endswith("/visual.json")]
    kpis = [v for v in visuals if v["visual"]["visualType"] == "multiRowCard"]
    assert len(kpis) == sum(1 for v in plan["visuals"] if v["role"] == "kpi")
    kpi_plan = next(v for v in plan["visuals"] if v["role"] == "kpi")
    first = next(v for v in kpis if v["position"]["y"] < kpi_plan["box"]["y"] + kpi_plan["box"]["h"] and abs(v["position"]["x"] - kpi_plan["box"]["x"]) < 40)
    assert first["position"]["x"] == kpi_plan["box"]["x"] + 16  # the stitch_like card has p-4 (16px) padding
    labels = first["visual"]["objects"]["cardTitle"][0]["properties"]
    assert labels["fontSize"]["expr"]["Literal"]["Value"] == "18.0D" and labels["fontFamily"]["expr"]["Literal"]["Value"] == "'Segoe UI Semibold'"
    measure = first["visual"]["query"]["queryState"]["Values"]["projections"][0]["field"]["Measure"]["Property"]
    assert measure.endswith(" (KPI)")
    model = next(z.read(n).decode() for n in z.namelist() if n.endswith("_Measures.tmdl"))
    assert f"measure '{measure}' =" in model and "isHidden" in model and "zz KPI display" in model

    # A Stitch screenshot that does not match blocks the build until the user accepts it.
    shot = Image.new("RGB", (1280, 720), (10, 200, 10))
    api.post(f"/api/projects/{pid}/design/stitch", files={"file": ("s.zip", _zip({"code.html": html.encode(), "screen.png": _png(shot)}), "application/zip")})
    api.post(f"/api/projects/{pid}/design/select", json={"id": "stitch"})
    status = api.get(f"/api/projects/{pid}/build").json()
    assert not status["ready"] and "matches the design" in status["blockers"][0]
    assert api.post(f"/api/projects/{pid}/build", json={}).status_code == 422
    over = api.put(f"/api/projects/{pid}/design/import/fidelity-override", json={"override": True}).json()
    assert over["design"]["fidelity_override"] and not over["design"]["fidelity"]["passed"]
    assert api.post(f"/api/projects/{pid}/build", json={}).json()["build"]["valid"]


# --- fuzz -------------------------------------------------------------------------------------------

@needs_browser
@pytest.mark.parametrize("batch", range(2))
def test_stitch_like_pages_on_random_datasets(batch):
    ran = 0
    for seed in range(500 + batch * 5, 500 + batch * 5 + 5):
        ctx = _ctx(dataset(seed), seed)
        if ctx is None:
            continue
        try:
            plan = page_plan(_plan(ctx, with_insights=seed % 2 == 0)[0], 1)
        except Exception:
            continue
        size = [(1280, 720), (1440, 900), (1366, 768)][seed % 3]
        html = stitch_export(plan, dark=bool(seed % 2), accent=["#E11D2E", "#3B82F6", "#10B981"][seed % 3], size=size, wrapper_padding=24 if seed % 4 == 0 else 0)
        found, mapping, _, _, report = _import(plan, html)
        assert validate_mapping(plan, mapping, found.boxes) == [], f"seed {seed}"
        assert {m.method for m in mapping} == {"title"} and report.passed, f"seed {seed}: {report}"
        ran += 1
    assert ran

"""Design import: rendering/extraction, matching (id, title, AI), mapping validation, background PNG,
theme JSON, the API flow and a random-dataset fuzz run. Uses the installed Edge/Chrome via Playwright."""

import html as htmllib
import io
import json

import pytest
from PIL import Image

from app.main import app
from core.design_ai import template_html
from core.planner import DashboardPlan, page_plan
from core.design_contract import playwright_available, render_page
from core.design_import import (
    DetectedBox, MappingItem, background_png, build_theme, contrast, css_hex, extract, match, title_score,
    validate_mapping,
)
from core.dax import StoredMeasures
from core.dax import build_plan as build_measures
from llm import get_llm
from llm.base import LLMRateLimitError
from tests.fakes import FakeProvider
from tests.test_cleaning_fuzz import dataset
from tests.test_insights import _project
from tests.test_planner import CTX, SAMPLES, _ctx, _plan


def _browser() -> bool:
    if not playwright_available():
        return False
    try:
        render_page("<p>x</p>", lambda page: True)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _browser(), reason="needs Playwright with Edge/Chrome")

VALUE_RED = "#FF0000"  # fake KPI values / chart marks: must not survive in the background PNG


def stitch_page(plan, rename: dict[str, str] | None = None, offset: int = 0) -> str:
    """A Stitch-like export: no data-* attributes, plain CSS classes, fake values and charts,
    reworded titles allowed, the canvas starting `offset` px down the page."""
    rename = rename or {}
    cards = []
    for v in plan.visuals:
        b = v.box
        title = htmllib.escape(rename.get(v.id, v.title))
        style = f"position:absolute;left:{b.x}px;top:{b.y + offset}px;width:{b.w}px;height:{b.h}px"
        if v.role == "slicer":
            body = f'<span class="lbl">{title}</span><span class="val">All</span>'
        elif v.role == "kpi":
            body = f'<p class="t">{title}</p><p class="big">$1.48M</p><p class="delta">+14.2% YoY</p>'
        elif v.role == "insights":
            body = f'<p class="t">{title}</p><ul><li>Revenue grew 12%.</li></ul>'
        else:
            body = (f'<p class="t">{title}</p><svg width="90%" height="60%"><polyline points="0,90 60,40 120,70 180,10" '
                    f'stroke="{VALUE_RED}" stroke-width="6" fill="none"/></svg><span class="axis">Jan Feb Mar</span>')
        cards.append(f'<div class="card {v.role}" style="{style}">{body}</div>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
      body {{ margin:0; background:#F4F1EA; font-family:'Segoe UI',sans-serif; }}
      .page {{ position:relative; width:1280px; height:{720 + offset}px; }}
      .card {{ background:#FFFFFF; border-radius:18px; box-shadow:0 6px 20px rgba(0,0,0,.08); padding:12px 16px; box-sizing:border-box; overflow:hidden; }}
      .slicer {{ border-radius:999px; display:flex; gap:8px; align-items:center; padding:6px 14px; }}
      .t {{ margin:0 0 6px; font:600 13px 'Segoe UI'; color:#1B1C1C; }}
      .big, .val, .delta, .axis {{ color:{VALUE_RED}; font:700 22px 'Segoe UI'; margin:0; }}
      .lbl {{ font:500 11px 'Segoe UI'; color:#4F5665; }}
      .brand {{ position:absolute; left:24px; top:{14 + offset}px; font:600 22px 'Segoe UI'; color:#1B1C1C; }}
    </style></head><body><div class="page"><div class="brand">{htmllib.escape(plan.title)}</div>{''.join(cards)}</div></body></html>"""


def _red_pixels(png: bytes) -> int:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    assert img.size == (1280, 720)
    return sum(1 for r, g, b in img.getdata() if r > 200 and g < 60 and b < 60)


@pytest.fixture(scope="module")
def shop():
    """Page 1 of the sample plan (designs and imports work per page)."""
    plan, measures, dims = _plan(_ctx({n: (SAMPLES / n).read_bytes() for n in ("orders.csv", "customers.xlsx", "products.csv")}))
    return page_plan(plan, 1), measures, dims


# --- extraction + matching -----------------------------------------------------------------------

@pytest.mark.parametrize("style", ["dark_futuristic", "glassmorphism"])
def test_contract_design_maps_by_id(shop, style):
    plan, _, _ = shop
    found = extract(template_html(plan, CTX, style))
    mapping, notes = match(plan, found.boxes)
    assert {m.method for m in mapping} == {"id"} and notes == []
    assert validate_mapping(plan, mapping, found.boxes) == []
    for m, v in zip(mapping, plan.visuals):
        assert (m.x, m.y, m.w, m.h) == (v.box.x, v.box.y, v.box.w, v.box.h)  # exact planned layout
    assert found.heading_font == "Outfit" and {c.role for c in found.palette} >= {"canvas", "card", "text", "accent"}


def test_stitch_like_design_maps_by_title_and_hides_values(shop):
    plan, _, _ = shop
    chart = next(v for v in plan.visuals if v.role == "chart")
    page = stitch_page(plan, rename={chart.id: chart.title.upper() + " (monthly)"}, offset=0)
    found = extract(page)
    mapping, _ = match(plan, found.boxes)
    by = {m.visual_id: m for m in mapping}
    assert all(m.method == "title" for m in mapping), [(m.visual_id, m.method) for m in mapping]
    assert by[chart.id].score >= 0.72
    assert validate_mapping(plan, mapping, found.boxes) == []
    assert all(abs(by[v.id].x - v.box.x) <= 1 and abs(by[v.id].w - v.box.w) <= 1 for v in plan.visuals)
    assert next(c for c in found.palette if c.role == "card").hex == "#FFFFFF"
    assert next(c for c in found.palette if c.role == "canvas").hex == "#F4F1EA"

    before = background_png(page, [])
    after = background_png(page, [m.box_id for m in mapping])
    assert _red_pixels(before) > 2000 and _red_pixels(after) == 0  # values and fake charts gone
    # titles stay: dark title pixels are still there; hiding titles too removes most of them
    dark = lambda png: sum(1 for p in Image.open(io.BytesIO(png)).convert("L").getdata() if p < 60)  # noqa: E731
    no_titles = background_png(page, [m.box_id for m in mapping], hide_titles=[m.box_id for m in mapping])
    assert dark(after) > 500 and dark(no_titles) < dark(after) / 2


def test_page_taller_than_canvas_is_scaled_into_it(shop):
    plan, _, _ = shop
    page = stitch_page(plan, offset=0).replace("</div></body>", '<div class="card" style="position:absolute;left:24px;top:900px;width:300px;height:200px"><p class="t">Footer card</p></div></div></body>')
    page = page.replace("height:720px", "height:1200px")
    found = extract(page)
    # The whole 1280x1200 page is fitted into 1280x720 (scale 0.6, centered); nothing is cut off.
    assert (found.source_w, found.source_h, found.scale) == (1280, 1200, 0.6) and found.skipped == 0
    assert any(b.title == "Footer card" for b in found.boxes)
    assert all(0 <= b.x and b.x + b.w <= 1280 and 0 <= b.y and b.y + b.h <= 720 for b in found.boxes)


def test_stitch_page_with_padding_around_a_1280x720_dashboard_is_not_scaled(shop):
    plan, _, _ = shop
    inner = stitch_page(plan).replace('<div class="page">', '<div class="page" style="margin:40px auto">')
    found = extract(inner.replace("body {", "body { padding: 32px; background:#999;"))
    assert found.scale == 1.0 and len(found.boxes) >= len(plan.visuals)
    assert next(c for c in found.palette if c.role == "canvas").hex == "#F4F1EA"


def test_ai_fallback_maps_reworded_titles(shop):
    plan, _, _ = shop
    kpi = next(v for v in plan.visuals if v.role == "kpi")
    page = stitch_page(plan, rename={kpi.id: "Headline Q"})
    found = extract(page)
    mapping, _ = match(plan, found.boxes)  # no AI: stays unplaced
    assert not next(m for m in mapping if m.visual_id == kpi.id).placed
    box = next(b for b in found.boxes if b.title == "Headline Q")
    other = next(m for m in mapping if m.placed)
    reply = {"pairs": [{"visual_id": kpi.id, "box_id": box.id},
                       {"visual_id": other.visual_id, "box_id": box.id},  # box already taken: ignored
                       {"visual_id": "visual_99", "box_id": "box_99"}]}
    llm = FakeProvider(replies=[json.dumps(reply)])
    mapping, notes = match(plan, found.boxes, llm)
    item = next(m for m in mapping if m.visual_id == kpi.id)
    assert item.method == "ai" and item.box_id == box.id and "AI matched 1 visual" in notes[0]
    assert validate_mapping(plan, mapping, found.boxes) == []
    assert "Headline Q" in llm.calls[0]["prompt"]

    mapping, notes = match(plan, found.boxes, FakeProvider(errors=[LLMRateLimitError("quota")], max_retries=0))
    assert not next(m for m in mapping if m.visual_id == kpi.id).placed and "map the remaining" in notes[0]


def test_title_score():
    box = DetectedBox(id="b", x=0, y=0, w=10, h=10, title="Revenue & Margin Trend", text="Revenue & Margin Trend $1.2M")
    assert title_score("Revenue and Margin Trend", box) == 1.0
    assert title_score("Margin Trend", box) >= 0.72
    assert title_score("Units Sold", box) < 0.5


# --- validation ------------------------------------------------------------------------------

def test_mapping_validator_rules(shop):
    plan, _, _ = shop
    ids = [v.id for v in plan.visuals]
    boxes = [DetectedBox(id=f"box_{i}", x=v.box.x, y=v.box.y, w=v.box.w, h=v.box.h, title=v.title) for i, v in enumerate(plan.visuals)]
    good = [MappingItem(visual_id=v.id, box_id=f"box_{i}", x=v.box.x, y=v.box.y, w=v.box.w, h=v.box.h, method="id") for i, v in enumerate(plan.visuals)]
    assert validate_mapping(plan, good, boxes) == []
    bad = [m.model_copy() for m in good]
    bad[0] = MappingItem(visual_id=ids[0])  # unplaced
    bad[1] = bad[1].model_copy(update={"box_id": bad[2].box_id})  # box reused
    bad[3] = bad[3].model_copy(update={"x": 1200})  # outside
    bad[4] = bad[4].model_copy(update={"x": bad[5].x, "y": bad[5].y})  # overlap
    bad[6] = bad[6].model_copy(update={"w": 20})  # too small
    text = " ".join(validate_mapping(plan, bad + [MappingItem(visual_id="ghost", w=1, h=1)], boxes))
    for part in ("has no box yet", "is used by both", "outside the 1280x720", "overlaps", "too small", "unknown visual ghost"):
        assert part in text, part


# --- theme -----------------------------------------------------------------------------------

def test_theme_colors_are_readable(shop):
    plan, _, _ = shop
    for style in ("dark_futuristic", "light_elegant"):
        found = extract(template_html(plan, CTX, style))
        theme = build_theme("Shop", found.palette, CTX.palette)
        assert len(theme["dataColors"]) == 8 and len(set(theme["dataColors"])) == 8
        assert all(contrast(c, theme["background"]) >= 1.6 for c in theme["dataColors"])
        assert contrast(theme["foreground"], theme["background"]) >= 3
        assert theme["textClasses"]["callout"]["fontFace"] == "Segoe UI"
        assert theme["visualStyles"]["*"]["*"]["background"][0]["show"] is False
    assert css_hex("rgba(10, 20, 30, 0.1)") is None and css_hex("rgb(255 0 0 / 80%)") == "#FF0000" and css_hex("#abc") == "#AABBCC"


# --- API ---------------------------------------------------------------------------------------

def _designed(api, sample_bytes) -> str:
    pid = _project(api, sample_bytes)
    assert api.get(f"/api/projects/{pid}/plan").status_code == 200
    api.post(f"/api/projects/{pid}/design/variants")
    assert api.post(f"/api/projects/{pid}/design/select", json={"id": "light_elegant"}).status_code == 200
    return pid


def test_import_api_flow(api, sample_bytes):
    pid = api.post("/api/projects", json={"name": "Empty"}).json()["id"]
    assert api.get(f"/api/projects/{pid}/design/import").status_code == 422  # no plan yet

    pid = _designed(api, sample_bytes)
    res = api.get(f"/api/projects/{pid}/design/import")
    assert res.status_code == 200, res.text
    body = res.json()
    d = body["design"]
    assert d["valid"] and d["source"] == "option_b" and "Light Elegant" in d["source_name"]
    assert {m["method"] for m in d["mapping"]} == {"id"} and len(d["mapping"]) == len(body["visuals"])
    png = api.get(f"/api/projects/{pid}/design/background.png")
    assert png.status_code == 200 and Image.open(io.BytesIO(png.content)).size == (1280, 720)
    theme = api.get(f"/api/projects/{pid}/design/theme.json").json()
    assert theme["dataColors"] and theme["name"].startswith("DashPilot")

    # Edit: move a chart onto its neighbour -> invalid; then swap two charts' boxes -> valid again.
    charts = [m for m, v in zip(d["mapping"], body["visuals"]) if v["role"] == "chart"]
    a, b = charts[0], charts[1]
    moved = {**a, "x": b["x"], "y": b["y"]}
    res = api.put(f"/api/projects/{pid}/design/import/mapping", json={"mapping": [moved]}).json()
    assert not res["design"]["valid"] and any("overlaps" in i for i in res["design"]["issues"])
    swap = [{"visual_id": a["visual_id"], "box_id": b["box_id"]}, {"visual_id": b["visual_id"], "box_id": a["box_id"]}]
    res = api.put(f"/api/projects/{pid}/design/import/mapping", json={"mapping": swap}).json()
    by = {m["visual_id"]: m for m in res["design"]["mapping"]}
    assert res["design"]["valid"] and by[a["visual_id"]]["box_id"] == b["box_id"] and by[a["visual_id"]]["method"] == "manual"
    # Swapped cards show the other visual's title in the design: Power BI titles them instead.
    assert {vid for vid, m in by.items() if m["pbi_title"]} == {a["visual_id"], b["visual_id"]}
    assert api.get(f"/api/projects/{pid}/design/import").json()["design"]["mapping"] == res["design"]["mapping"]  # saved
    bad = api.put(f"/api/projects/{pid}/design/import/mapping", json={"mapping": [{"visual_id": a["visual_id"], "box_id": "box_99"}]})
    assert bad.status_code == 422

    # Page 2 (Details) is its own import: only its visuals (plus the shared slicers), its own background.
    p2 = api.get(f"/api/projects/{pid}/design/import?page=2").json()
    assert p2["page"] == 2 and p2["pages"] == ["Overview", "Details"] and p2["design"]["valid"]
    assert {v["role"] for v in p2["visuals"]} == {"slicer", "chart"}
    assert api.get(f"/api/projects/{pid}/design/background.png?page=2").status_code == 200
    assert api.get(f"/api/projects/{pid}/design/import?page=3").status_code == 422


def test_upload_and_staleness(api, sample_bytes):
    pid = _designed(api, sample_bytes)
    plan = api.get(f"/api/projects/{pid}/plan").json()["plan"]
    page = stitch_page(page_plan(DashboardPlan.model_validate(plan), 1))
    res = api.post(f"/api/projects/{pid}/design/import/upload", files={"file": ("stitch.html", page.encode(), "text/html")})
    assert res.status_code == 200, res.text
    d = res.json()["design"]
    assert d["source"] == "upload" and d["source_name"] == "stitch.html" and d["valid"]
    assert {m["method"] for m in d["mapping"]} == {"title"}
    assert api.post(f"/api/projects/{pid}/design/import/upload", files={"file": ("x.png", b"\x89PNG", "image/png")}).status_code == 422

    # The plan changes (a chart removed) -> the uploaded design is matched again on the next read.
    visuals = [{k: v[k] for k in ("role", "type", "title", "measures", "dimension", "sort", "purpose", "question_id", "text", "page")} for v in plan["visuals"]]
    visuals.pop(next(i for i, v in enumerate(visuals) if v["role"] == "chart"))
    api.put(f"/api/projects/{pid}/plan", json={"visuals": visuals})
    res = api.get(f"/api/projects/{pid}/design/import").json()
    assert res["design"]["source"] == "upload" and "matched again" in res["notes"][0]
    assert len(res["design"]["mapping"]) == len([v for v in visuals if v["page"] == 1 or v["role"] == "slicer"])

    # Back to the Step 7 design.
    res = api.post(f"/api/projects/{pid}/design/import/selected").json()
    assert res["design"]["source"] == "option_b"


def test_ai_mapping_through_api(api, sample_bytes):
    pid = _designed(api, sample_bytes)
    plan = page_plan(DashboardPlan.model_validate(api.get(f"/api/projects/{pid}/plan").json()["plan"]), 1)
    kpi = next(v for v in plan.visuals if v.role == "kpi")
    page = stitch_page(plan, rename={kpi.id: "Headline Q"})
    box_id = next(b.id for b in extract(page).boxes if b.title == "Headline Q")
    app.dependency_overrides[get_llm] = lambda: FakeProvider(replies=[json.dumps({"pairs": [{"visual_id": kpi.id, "box_id": box_id}]})])
    d = api.post(f"/api/projects/{pid}/design/import/upload", files={"file": ("s.html", page.encode(), "text/html")}).json()["design"]
    assert d["valid"] and next(m for m in d["mapping"] if m["visual_id"] == kpi.id)["method"] == "ai"


# --- fuzz ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("batch", range(2))
def test_import_on_random_datasets(batch):
    ran = 0
    for seed in range(300 + batch * 6, 300 + batch * 6 + 6):
        ctx = _ctx(dataset(seed), seed)
        if ctx is None or not any(m.status == "passed" for m in build_measures(ctx, StoredMeasures(), False)[1]):
            continue
        whole, _, _ = _plan(ctx, with_insights=seed % 2 == 0)
        assert whole.valid
        for n in range(1, len(whole.pages) + 1):
            plan = page_plan(whole, n)
            # Alternate between contract HTML (id match) and a Stitch-like page (title match).
            page = template_html(plan, CTX, "light_elegant") if seed % 2 else stitch_page(plan)
            found = extract(page)
            mapping, _ = match(plan, found.boxes)
            assert validate_mapping(plan, mapping, found.boxes) == [], f"seed {seed}"
            assert {m.method for m in mapping} == ({"id"} if seed % 2 else {"title"}), f"seed {seed}"
        ran += 1
    assert ran

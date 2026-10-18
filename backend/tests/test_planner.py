"""Dashboard planner, design contract, design method B (AI retries + template fallback) and the API."""

import html as htmllib
import json
import random

import pandas as pd
import pytest

from app.main import app
from core.cleaning import SourceTable
from core.cleaning_rules import build_plan as clean_plan
from core.cleaning_rules import table_pipelines
from core.context import BusinessContext
from core.dax import GenContext, StoredMeasures
from core.dax import build_plan as build_measures
from core.dax_eval import date_frame
from core.design_ai import generate_variant, generate_variants, template_html
from core.design_contract import check, measure_static
from core.insights import Engine, InsightPlan, compute_insights, link_questions, template_questions
from core.modelling import DATE_TABLE, ModelSettings, build_model
from core.planner import (
    CHART_TYPES, MAX_CHARTS, MAX_KPIS, VisualInput, apply_edit, build_plan, dimension_options, layout, validate,
)
from core.profiling import build_report
from core.upload import UploadError, csv_delimiter, read_tables
from llm import get_llm
from llm.base import LLMRateLimitError
from tests.conftest import SAMPLES
from tests.fakes import FakeProvider
from tests.test_cleaning_fuzz import dataset
from tests.test_insights import _project


def _ctx(files: dict[str, bytes], seed: int = 0) -> GenContext | None:
    sources = []
    for filename, content in files.items():
        try:
            tables = read_tables(filename, content)
        except UploadError:
            continue
        delimiter = csv_delimiter(content) if filename.endswith(".csv") else ","
        sources += [SourceTable(name=n, filename=filename, sheet=s, delimiter=delimiter, df=df) for n, (s, df) in tables.items()]
    if not sources:
        return None
    report = build_report([(s.name, "f", s.sheet, s.df) for s in sources])
    decisions = {s.id: {"status": "accepted"} for s in clean_plan(report, sources, {}).steps}
    pipelines, _ = table_pipelines(report, sources, decisions)
    cleaned = {n: (p.src, [s for s in p.accepted if not s.error], p.result) for n, p in pipelines.items()}
    model = build_model(report, cleaned, ModelSettings())
    frames = {t.name: pipelines[t.name].result.df.reset_index(drop=True) for t in model.tables if t.included}
    for t in model.tables:
        for c in t.columns:
            if t.included and c.derived:
                frames[t.name][c.name] = pd.to_datetime(frames[t.name][c.name.removesuffix("_date")], errors="coerce").dt.normalize()
    if model.date_table.enabled:
        frames[DATE_TABLE] = date_frame(model.date_table.start, model.date_table.end, 1)
    industries = random.Random(seed).sample(["Retail", "Finance & FinTech", "E-commerce"], 1)
    return GenContext(model=model, report=report, frames=frames, industries=industries)


def _plan(ctx: GenContext, with_insights: bool = True):
    mplan, measures = build_measures(ctx, StoredMeasures(), False)
    insights = None
    if with_insights:
        engine = Engine(ctx, measures)
        found, north, dims = compute_insights(engine)
        questions = template_questions(engine, found, dims, ["Executive Leadership"])
        link_questions(questions, found)
        insights = InsightPlan(insights=found, questions=questions, north_star=north, rows_scanned=0, dimensions=[], confidence=1)
    plan = build_plan("Shop Performance Dashboard", ctx.model, ctx.report, measures, [c.name for c in mplan.cards], insights)
    return plan, measures, dimension_options(ctx.model, ctx.report)


@pytest.fixture(scope="module")
def shop():
    files = {n: (SAMPLES / n).read_bytes() for n in ("orders.csv", "customers.xlsx", "products.csv")}
    return _plan(_ctx(files))


# --- planner rules ------------------------------------------------------------------------

def test_plan_shape_and_rules(shop):
    plan, measures, dims = shop
    assert plan.valid, plan.issues
    roles = [v.role for v in plan.visuals]
    assert roles.count("slicer") >= 1 and 4 <= roles.count("kpi") <= MAX_KPIS
    charts = [v for v in plan.visuals if v.role == "chart"]
    assert 4 <= len(charts) <= MAX_CHARTS and roles.count("insights") == 1
    passed = {m.name for m in measures if m.status == "passed"}
    fields = {d.field for d in dims}
    for v in charts:
        assert v.type in CHART_TYPES and v.purpose and set(v.measures) <= passed and v.dimension in fields
    trend = next(v for v in charts if v.type in ("line", "area"))
    assert trend.dimension.endswith("[Year Month]") and trend.sort == "date"
    assert next(v for v in plan.visuals if v.role == "slicer").title == "Date Range"
    assert len({v.title for v in plan.visuals}) == len(plan.visuals)
    assert len({v.purpose for v in charts}) == len(charts)  # each chart answers its own question
    # every box on the 1280x720 canvas, nothing overlapping
    assert all(0 <= v.box.x and v.box.x + v.box.w <= 1280 and 0 <= v.box.y and v.box.y + v.box.h <= 720 for v in plan.visuals)


def test_validator_catches_bad_edits(shop):
    plan, measures, dims = shop
    items = [VisualInput(**v.model_dump(include=set(VisualInput.model_fields))) for v in plan.visuals]
    chart = next(i for i in items if i.role == "chart")
    bad = list(items)
    bad[items.index(chart)] = chart.model_copy(update={"measures": ["Not A Measure"]})
    bad.append(chart.model_copy())  # duplicate
    bad.append(VisualInput(role="chart", type="donut", title="Wide Donut", measures=chart.measures,
                           dimension=next(d.field for d in dims if d.cardinality > 8)))
    edited = apply_edit(plan, bad, measures, dims)
    text = " ".join(edited.issues)
    assert not edited.valid and edited.edited
    assert "Not A Measure" in text and "must be unique" in text and "donuts need few categories" in text

    with pytest.raises(ValueError):
        VisualInput(role="chart", type="pie_3d", title="X", measures=chart.measures)  # only Power BI native types


def test_edit_reorders_adds_and_removes(shop):
    plan, measures, dims = shop
    items = [VisualInput(**v.model_dump(include=set(VisualInput.model_fields))) for v in plan.visuals]
    charts = [i for i in items if i.role == "chart"]
    rest = [i for i in items if i.role != "chart"]
    first, *others = charts
    new_order = rest[:-1] + [*others[:-1], first.model_copy(update={"type": "clustered_column"}), rest[-1]]
    edited = apply_edit(plan, new_order, measures, dims, title="My Board")
    assert edited.valid, edited.issues
    assert edited.title == "My Board"
    out_charts = [v for v in edited.visuals if v.role == "chart"]
    assert len(out_charts) == len(charts) - 1 and out_charts[-1].type == "clustered_column"
    assert [v.id for v in edited.visuals] == [f"{v.role if v.role != 'chart' else 'visual'}_{n}" for n, v in enumerate(edited.visuals, 1)]


def test_layout_handles_minimum_and_maximum(shop):
    plan, measures, dims = shop
    for keep in (1, MAX_CHARTS):
        charts = [v for v in plan.visuals if v.role == "chart"]
        charts = (charts * 3)[:keep]
        visuals = [v.model_copy() for v in plan.visuals if v.role != "chart"] + [c.model_copy(update={"title": f"Chart {chr(65 + n)}", "type": CHART_TYPES[n]}) for n, c in enumerate(charts)]
        laid = layout(visuals)
        issues = [i for i in validate(plan.model_copy(update={"visuals": laid}), measures, dims) if "overlap" in i or "outside" in i]
        assert not issues


# --- design contract ----------------------------------------------------------------------

CTX = BusinessContext(company_name="Shop", industries=["E-commerce"])


@pytest.mark.parametrize("archetype", ["dark_futuristic", "light_elegant", "glassmorphism"])
def test_templates_pass_the_contract(shop, archetype):
    plan = shop[0]
    html = template_html(plan, CTX, archetype)
    errors, m = check(html, plan, prefer_browser=False)
    assert errors == [] and m.engine == "static" and len(m.boxes) == len(plan.visuals)


def test_contract_reports_every_broken_rule(shop):
    plan = shop[0]
    html = template_html(plan, CTX, "light_elegant")
    kpi = next(v for v in plan.visuals if v.role == "kpi")
    charts = [v for v in plan.visuals if v.role == "chart"]
    broken = (html.replace('style="width:1280px;height:720px"', 'style="width:1200px;height:720px"')
              .replace(f'data-visual-id="{charts[0].id}"', 'data-visual-id="visual_99"')
              .replace(f'data-title="{kpi.title}"', 'data-title="Wrong"', 1)
              .replace("</body>", '<script>alert(1)</script><img src="https://evil.example/x.png"></body>'))
    # move one chart onto its neighbour and write fake numbers into another chart area
    a, b = charts[1], charts[2]
    broken = broken.replace(f"left:{a.box.x}px;top:{a.box.y}px", f"left:{b.box.x}px;top:{b.box.y}px", 1)
    broken = broken.replace(f'data-visual-id="{b.id}"', f'data-visual-id="{b.id}" data-x', 1)
    idx = broken.index(f'data-visual-id="{charts[3].id}"')
    area = broken.index("data-chart-area></div>", idx)
    broken = broken[:area] + "data-chart-area>$1.2M</div>" + broken[area + len("data-chart-area></div>"):]
    errors, _ = check(broken, plan, prefer_browser=False)
    text = "\n".join(errors)
    for part in ("1280x720", f"Missing container for {charts[0].id}", "visual_99", "data-title", "<script>",
                 "evil.example", f"{a.id} overlaps {b.id}", "$1.2M"):
        assert part in text, part


def test_contract_requires_exact_visible_titles_and_insights(shop):
    plan = shop[0]
    insights = next(v for v in plan.visuals if v.role == "insights")
    chart = next(v for v in plan.visuals if v.role == "chart")
    html = template_html(plan, CTX, "light_elegant")
    restyled = html.replace(f'<p class="dp-title">{chart.title}</p>', f'<p class="dp-title" style="text-transform:uppercase">{chart.title}</p>')
    assert check(restyled, plan, prefer_browser=False)[0] == []  # CSS casing is fine
    retitled = html.replace(f'<p class="dp-title">{chart.title}</p>', f'<p class="dp-title">{chart.title.upper()}</p>')
    line = htmllib.escape(insights.text[0])
    reworded = html.replace(f"<li>{line}</li>", f"<li>{line.replace(' for ', ' in ', 1)}</li>")
    errors = check(retitled, plan, prefer_browser=False)[0] + check(reworded, plan, prefer_browser=False)[0]
    assert any(f"{chart.id} must show its title" in e for e in errors)
    assert any("word for word" in e for e in errors)


def test_static_measure_ignores_padding_properties():
    html = '<div data-canvas style="width:1280px;height:720px"><div data-visual-id="a" style="padding-left:9px;left:10px;top:20px;width:300px;max-width:5px;height:200px"></div></div>'
    box = measure_static(html).boxes[0]
    assert (box.x, box.y, box.w, box.h) == (10, 20, 300, 200)


# --- design method B ----------------------------------------------------------------------

def test_ai_retry_then_success(shop):
    plan = shop[0]
    good = template_html(plan, CTX, "dark_futuristic").replace("<title>", "<title>AI ")
    llm = FakeProvider(replies=[json.dumps({"html": "<div>not a dashboard</div>"}), json.dumps({"html": good})])
    variant, usable = generate_variant(plan, CTX, "dark_futuristic", llm, prefer_browser=False)
    assert usable and variant.source == "ai" and variant.attempts == 2 and variant.valid
    assert "FAILED THESE CHECKS" in llm.calls[1]["prompt"] and "Missing container" in llm.calls[1]["prompt"]


def test_ai_always_invalid_falls_back_to_template(shop):
    plan = shop[0]
    llm = FakeProvider(replies=[json.dumps({"html": "<p>x</p>"})] * 3)
    variant, usable = generate_variant(plan, CTX, "glassmorphism", llm, prefer_browser=False)
    assert usable and variant.source == "template" and variant.attempts == 3 and variant.valid and variant.errors
    assert len(llm.calls) == 3 and "after 3 attempts" in variant.note


def test_quota_error_stops_ai_for_all_variants(shop):
    plan = shop[0]
    llm = FakeProvider(errors=[LLMRateLimitError("quota exhausted")], max_retries=0)
    variants = generate_variants(plan, CTX, llm, prefer_browser=False)
    assert [v.source for v in variants] == ["template"] * 3 and all(v.valid for v in variants)
    assert len(llm.calls) == 1 and "AI unavailable" in variants[0].note and "skipped" in variants[2].note


# --- API ------------------------------------------------------------------------------------

def test_plan_design_select_api(api, sample_bytes):
    pid = _project(api, sample_bytes)
    res = api.get(f"/api/projects/{pid}/plan")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["plan"]["valid"] and body["design"]["variants"] == []

    visuals = [{k: v[k] for k in ("role", "type", "title", "measures", "dimension", "sort", "purpose", "question_id", "text")} for v in body["plan"]["visuals"]]
    chart = next(v for v in visuals if v["role"] == "chart")
    chart["type"] = "clustered_column"
    saved = api.put(f"/api/projects/{pid}/plan", json={"title": "Shop Board", "visuals": visuals}).json()
    assert saved["plan"]["edited"] and saved["plan"]["title"] == "Shop Board"
    assert api.get(f"/api/projects/{pid}/plan").json()["plan"]["title"] == "Shop Board"  # persisted

    design = api.post(f"/api/projects/{pid}/design/variants").json()
    assert [v["id"] for v in design["design"]["variants"]] == ["dark_futuristic", "light_elegant", "glassmorphism"]
    assert all(v["valid"] and v["source"] == "template" for v in design["design"]["variants"]) and design["notes"]

    assert api.post(f"/api/projects/{pid}/design/select", json={"id": "nope"}).status_code == 422
    sel = api.post(f"/api/projects/{pid}/design/select", json={"id": "light_elegant"}).json()
    assert sel["design"]["selected"] == "light_elegant"

    # editing the plan marks the generated variants stale
    visuals.pop(next(n for n, v in enumerate(visuals) if v["role"] == "chart"))
    assert api.put(f"/api/projects/{pid}/plan", json={"visuals": visuals}).json()["design"]["stale"]

    bad = [*visuals, {**chart, "measures": ["Ghost"]}]
    res = api.put(f"/api/projects/{pid}/plan", json={"visuals": bad}).json()
    assert not res["plan"]["valid"]
    assert api.post(f"/api/projects/{pid}/design/variants").status_code == 422  # invalid plan cannot be designed


def test_ai_title_polish_and_fallback(api, sample_bytes):
    pid = _project(api, sample_bytes)
    plan = api.get(f"/api/projects/{pid}/plan").json()["plan"]
    chart = next(v for v in plan["visuals"] if v["role"] == "chart")
    kpi = next(v for v in plan["visuals"] if v["role"] == "kpi")
    reply = {"dashboard_title": "Revenue Command Center", "visuals": [
        {"id": chart["id"], "title": "Where Revenue Comes From", "purpose": "Shows the revenue drivers."},
        {"id": kpi["id"], "title": "Renamed Card", "purpose": "x"},  # KPI titles stay the measure name
        {"id": "visual_99", "title": "Ghost", "purpose": "x"},
    ]}
    app.dependency_overrides[get_llm] = lambda: FakeProvider(replies=[json.dumps(reply)])
    out = api.post(f"/api/projects/{pid}/plan/generate?ai=true").json()
    titles = {v["id"]: v["title"] for v in out["plan"]["visuals"]}
    assert out["plan"]["title"] == "Revenue Command Center" and out["plan"]["source"] == "ai"
    assert titles[chart["id"]] == "Where Revenue Comes From" and titles[kpi["id"]] == kpi["title"] and out["plan"]["valid"]

    app.dependency_overrides[get_llm] = lambda: FakeProvider(errors=[LLMRateLimitError("quota exhausted")], max_retries=0)
    out = api.post(f"/api/projects/{pid}/plan/generate?ai=true").json()
    assert out["plan"]["source"] == "rules" and out["plan"]["valid"] and "skipped" in out["notes"][0]


def test_plan_needs_data(api):
    pid = api.post("/api/projects", json={"name": "Empty"}).json()["id"]
    assert api.get(f"/api/projects/{pid}/plan").status_code == 422


# --- fuzz -----------------------------------------------------------------------------------

@pytest.mark.parametrize("batch", range(4))
def test_plans_and_templates_on_random_datasets(batch):
    for seed in range(200 + batch * 10, 200 + batch * 10 + 10):
        ctx = _ctx(dataset(seed), seed)
        if ctx is None:
            continue
        mplan, measures = build_measures(ctx, StoredMeasures(), False)
        if not any(m.status == "passed" for m in measures):
            continue
        plan, measures, dims = _plan(ctx, with_insights=seed % 2 == 0)
        assert plan.valid, f"seed {seed}: {plan.issues}"
        html = template_html(plan, CTX, ["dark_futuristic", "light_elegant", "glassmorphism"][seed % 3])
        errors, _ = check(html, plan, prefer_browser=False)
        assert errors == [], f"seed {seed}: {errors}"

"""Insights: grounding validator, computed insights, AI narratives (grounded or rejected), custom
questions via validated query specs, pins, and fuzz on random datasets."""

import json
import random

import pandas as pd
import pytest

from app.main import app
from core.cleaning import SourceTable
from core.cleaning_rules import build_plan as clean_plan
from core.cleaning_rules import table_pipelines
from core.dax import GenContext, StoredMeasures, build_plan
from core.dax_eval import date_frame
from core.insights import Engine, Insight, QuerySpec, _years, compute_insights, grounded, insight_names, validate_spec
from core.modelling import DATE_TABLE, ModelSettings, build_model
from core.profiling import build_report
from core.upload import UploadError, csv_delimiter, read_tables
from llm import get_llm
from tests.fakes import FakeProvider
from tests.test_cleaning_fuzz import dataset


# --- grounding --------------------------------------------------------------------------

def test_grounding_accepts_only_computed_numbers():
    facts = {"current": 2_481_234.5, "previous": 2_126_000.0, "change": 0.1671, "share": 0.312, "members": 30}
    ok, bad = grounded("Volume reached 2.48M, +16.7% vs 2,126,000 last month; 31.2% from 30 merchants.", facts)
    assert ok and bad == []
    ok, bad = grounded("Volume grew 18.6% to 2.48M and 4 new cities joined.", facts)
    assert not ok and set(bad) == {"18.6%", "4"}
    assert grounded("No numbers at all here.", facts)[0]
    assert grounded("Compared with 2023, growth was 16.7%.", facts, extra=(2023.0,))[0]
    assert not grounded("Compared with 2024, growth was 16.7%.", facts, extra=(2023.0,))[0]
    assert grounded("Share is 0.31 of the total.", facts)[0]  # rounding of a fact


# --- API ---------------------------------------------------------------------------------

def _project(api, sample_bytes):
    pid = api.post("/api/projects", json={"name": "Shop"}).json()["id"]
    files = [("files", (n, sample_bytes[n], "application/octet-stream")) for n in ("orders.csv", "customers.xlsx", "products.csv")]
    api.post(f"/api/projects/{pid}/files", files=files)
    steps = api.get(f"/api/projects/{pid}/cleaning").json()["steps"]
    api.post(f"/api/projects/{pid}/cleaning/decisions", json={"decisions": [{"step_id": s["id"], "status": "accepted"} for s in steps]})
    ctx = api.get(f"/api/projects/{pid}/context").json()
    api.put(f"/api/projects/{pid}/context", json={**ctx, "industries": ["E-commerce"], "audiences": ["Sales Teams"]})
    return pid


def test_insights_are_computed_and_grounded(api, sample_bytes):
    pid = _project(api, sample_bytes)
    plan = api.get(f"/api/projects/{pid}/insights").json()
    types = {i["type"] for i in plan["insights"]}
    assert {"trend", "comparison", "top_performer", "contribution"} <= types
    assert plan["ai_status"] == "off" and plan["north_star"] in {i["id"] for i in plan["insights"]}
    assert plan["rows_scanned"] == 600 and 0 < plan["confidence"] <= 1
    for raw in plan["insights"]:
        # The template text itself must only use computed numbers.
        i = Insight.model_validate(raw)
        assert grounded(f"{i.headline} {i.body}", i.facts, _years(i.headline + i.body), insight_names(i))[0], i.headline
    top = next(i for i in plan["insights"] if i["type"] == "top_performer")
    revenue = pd.read_csv(__import__("io").BytesIO(sample_bytes["orders.csv"]))
    assert top["series"]["values"][0] == pytest.approx(top["facts"]["top"])
    assert 0 < top["facts"]["share"] < 1 and top["facts"]["total"] > 0 and len(revenue) == 600
    assert len(plan["questions"]) >= 5 and all(q["answer"] for q in plan["questions"])


def test_ai_narratives_are_grounded_or_rejected(api, sample_bytes):
    pid = _project(api, sample_bytes)
    plan = api.get(f"/api/projects/{pid}/insights").json()
    trend = next(i for i in plan["insights"] if i["type"] == "trend")
    top = next(i for i in plan["insights"] if i["type"] == "top_performer")
    good = f"Momentum: {trend['value_text']} in the latest month."
    reply = {
        "questions": [{"text": "Which products drive revenue?", "theme": "Performance", "audience": "Sales Teams"},
                      {"text": "Will revenue grow 25% next year?", "theme": "Growth", "audience": "Sales Teams"}],
        "narratives": [
            {"id": trend["id"], "headline": good, "body": "Steady month to month.", "action": "Keep pushing."},
            {"id": top["id"], "headline": "Top member made 99.9% of revenue.", "body": "x", "action": "y"},
        ],
    }
    llm = FakeProvider(replies=[json.dumps(reply)])
    app.dependency_overrides[get_llm] = lambda: llm
    plan = api.get(f"/api/projects/{pid}/insights?ai=true").json()
    by_id = {i["id"]: i for i in plan["insights"]}
    assert by_id[trend["id"]]["narrative_source"] == "ai" and by_id[trend["id"]]["headline"] == good
    assert by_id[top["id"]]["narrative_source"] == "template" and by_id[top["id"]]["headline"] == top["headline"]
    assert plan["ai_status"] == "done" and "1 AI narrative rejected" in plan["ai_note"]
    assert [q["text"] for q in plan["questions"]] == ["Which products drive revenue?"]  # numbered question dropped
    assert api.get(f"/api/projects/{pid}/insights?ai=true").json()["ai_status"] == "done" and len(llm.calls) == 1


def test_custom_questions_use_validated_specs(api, sample_bytes):
    pid = _project(api, sample_bytes)
    res = api.post(f"/api/projects/{pid}/insights/ask", json={"question": "total revenue by destination city"}).json()
    asked = res["asked"]
    assert asked["source"] == "rules" and asked["spec"]["measure"] == "Total Revenue"
    assert asked["spec"]["dimension_column"] == "destination_city" and asked["insight"]["series"]["labels"]
    assert any(i["id"] == asked["insight"]["id"] and i["type"] == "answer" for i in res["plan"]["insights"])

    spec = {"measure": "Total Orders", "filter_table": "orders", "filter_column": "fulfillment_status", "filter_value": "Returned", "period": "all"}
    llm = FakeProvider(replies=[json.dumps(spec), json.dumps({"measure": "Profit Margin X", "period": "all"})])
    app.dependency_overrides[get_llm] = lambda: llm
    res = api.post(f"/api/projects/{pid}/insights/ask", json={"question": "How many orders were returned?"}).json()
    assert res["asked"]["source"] == "ai" and "Returned" in res["asked"]["insight"]["headline"]
    returned = res["asked"]["insight"]["facts"]["value"]
    orders = pd.read_csv(__import__("io").BytesIO(sample_bytes["orders.csv"]))
    assert returned == (orders["fulfillment_status"] == "Returned").sum()

    res = api.post(f"/api/projects/{pid}/insights/ask", json={"question": "what is the profit margin?"}).json()
    assert res["asked"]["source"] == "rules" and res["plan"]["notes"]  # unknown measure -> keyword fallback
    assert api.post(f"/api/projects/{pid}/insights/ask", json={"question": " "}).status_code == 422


def test_pin_and_remove(api, sample_bytes):
    pid = _project(api, sample_bytes)
    first = api.get(f"/api/projects/{pid}/insights").json()["insights"][0]["id"]
    plan = api.post(f"/api/projects/{pid}/insights/pin", json={"id": first, "pinned": True}).json()
    assert plan["pinned"] == [first] and next(i for i in plan["insights"] if i["id"] == first)["pinned"]
    assert api.post(f"/api/projects/{pid}/insights/pin", json={"id": first, "pinned": False}).json()["pinned"] == []
    asked = api.post(f"/api/projects/{pid}/insights/ask", json={"question": "total orders"}).json()["asked"]["insight"]["id"]
    plan = api.post(f"/api/projects/{pid}/insights/asked/delete", json={"id": asked}).json()
    assert asked not in {i["id"] for i in plan["insights"]}


def test_spec_validation_rejects_unknown_names():
    class FakeEngine:
        by_name = {"total": type("M", (), {"name": "Total"})()}
        ctx = type("C", (), {"included": [], "frames": {}})()

        def has_time(self):
            return False

    with pytest.raises(ValueError):
        validate_spec(QuerySpec(measure="nope"), FakeEngine())
    with pytest.raises(ValueError):
        validate_spec(QuerySpec(measure="total", dimension_table="x", dimension_column="y"), FakeEngine())


# --- fuzz -----------------------------------------------------------------------------------

@pytest.mark.parametrize("batch", range(4))
def test_insights_on_random_datasets(batch):
    for seed in range(100 + batch * 10, 100 + batch * 10 + 10):
        sources = []
        for filename, content in dataset(seed).items():
            try:
                tables = read_tables(filename, content)
            except UploadError:
                continue
            delimiter = csv_delimiter(content) if filename.endswith(".csv") else ","
            sources += [SourceTable(name=n, filename=filename, sheet=s, delimiter=delimiter, df=df) for n, (s, df) in tables.items()]
        if not sources:
            continue
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
        ctx = GenContext(model=model, report=report, frames=frames, industries=random.Random(seed).sample(["Retail", "Finance & FinTech", "E-commerce"], 1))
        _, measures = build_plan(ctx, StoredMeasures(), False)
        insights, _, _ = compute_insights(Engine(ctx, measures))
        for i in insights:
            ok, bad = grounded(f"{i.headline} {i.body}", i.facts, _years(i.headline + i.body), insight_names(i))
            assert ok, f"seed {seed}: {i.headline} | {i.body} {bad}"
            if i.type == "top_performer" and "share" in i.facts:
                assert 0 <= i.facts["share"] <= 1.0001, f"seed {seed}: share {i.facts['share']}"

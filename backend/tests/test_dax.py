"""KPIs & DAX: validator, evaluator, generated measures, API (edit/reset/custom/AI) and random models."""

import json
import random

import pandas as pd
import pytest

from app.main import app
from core.cleaning import SourceTable
from core.cleaning_rules import build_plan as clean_plan
from core.cleaning_rules import table_pipelines
from core.context import BusinessContext
from core.dax import GenContext, StoredMeasures, build_plan
from core.dax_eval import Ctx, Data, EvalError, Evaluator, Link, date_frame, parse
from core.dax_validate import Schema, check, find_cycles
from core.modelling import DATE_TABLE, ModelSettings, build_model
from core.profiling import build_report
from core.upload import UploadError, csv_delimiter, read_tables
from llm import get_llm
from tests.fakes import FakeProvider
from tests.test_cleaning_fuzz import dataset


# --- validator ----------------------------------------------------------------------

def _schema():
    s = Schema()
    s.add("orders", ["order_id", "amount", "city"])
    s.add("Dim Date", ["Date", "Year"])
    return s


def test_validator_catches_common_mistakes():
    s, measures = _schema(), {"total": "Total"}
    assert check("SUM(orders[amount])", s, measures).issues == []
    assert check("DIVIDE([Total], COUNTROWS(orders))", s, measures).deps == ["Total"]
    ok = check("VAR __x = [Total]\nRETURN DIVIDE(__x, 2) // note", s, measures)
    assert ok.issues == [] and ok.deps == ["Total"]
    assert check("CALCULATE([Total], SAMEPERIODLASTYEAR('Dim Date'[Date]))", s, measures).time_intelligence

    def issues(expr):
        return " | ".join(check(expr, s, measures).issues)

    assert "unclosed '('" in issues("SUM(orders[amount]")
    assert "Unmatched ')'" in issues("SUM(orders[amount]))")
    assert "Unknown table 'sales'" in issues("SUM(sales[amount])")
    assert "Column [price] does not exist" in issues("SUM(orders[price])")
    assert "Unknown measure [Profit]" in issues("[Profit] * 2")
    assert "Unknown function SUMM()" in issues("SUMM(orders[amount])")
    assert "Unknown name 'foo'" in issues("foo + 1")
    assert check("", s, measures).issues == ["The formula is empty"]
    # ADDCOLUMNS aliases are valid bare references.
    assert check('SUMX(ADDCOLUMNS(VALUES(orders[city]), "@v", [Total]), [@v])', s, measures).issues == []


def test_cycles_are_found():
    cycles = find_cycles({"A": ["B"], "B": ["C"], "C": ["A"], "D": ["A"], "E": []})
    assert set(cycles) == {"A", "B", "C"} and cycles["A"][0] == cycles["A"][-1]


# --- evaluator ----------------------------------------------------------------------

def _data(measures: dict[str, str]) -> Data:
    orders = pd.DataFrame({
        "order_id": ["O1", "O2", "O3", "O4", "O5"],
        "customer_id": ["C1", "C1", "C2", "C3", "C2"],
        "amount": [100.0, 50.0, 30.0, 20.0, 0.0],
        "day": pd.to_datetime(["2023-03-01", "2024-01-15", "2024-02-10", "2024-03-01", "2024-03-05"]),
    })
    customers = pd.DataFrame({"customer_id": ["C1", "C2", "C3"], "segment": ["Gold", "Silver", "Gold"]})
    return Data(
        frames={"orders": orders, "customers": customers, DATE_TABLE: date_frame("2023-01-01", "2024-12-31", 1)},
        links=[Link("orders", "customer_id", "customers", "customer_id"), Link("orders", "day", DATE_TABLE, "Date")],
        date_table=DATE_TABLE,
        measures={k.lower(): v for k, v in measures.items()},
    )


def test_evaluator_matches_pandas():
    m = {
        "Total": "SUM(orders[amount])",
        "Orders": "COUNTROWS(orders)",
        "AOV": "DIVIDE([Total], [Orders])",
        "Gold Total": 'CALCULATE([Total], customers[segment] = "Gold")',
        "Gold Share": "DIVIDE([Gold Total], CALCULATE([Total], ALL(customers)))",
        "Big Orders": "CALCULATE([Orders], orders[amount] >= 50)",
        "Customers": "DISTINCTCOUNT(orders[customer_id])",
        "YTD": "TOTALYTD([Total], 'Dim_Date'[Date])",
        "PY": "CALCULATE([Total], SAMEPERIODLASTYEAR('Dim_Date'[Date]))",
        "YoY": "VAR __c = [Total]\nVAR __p = [PY]\nRETURN DIVIDE(__c - __p, __p)",
        "Weighted": "SUMX(orders, orders[amount] * 2)",
        "Label": 'IF([Total] > 100, "big", "small")',
        "Bad": "[Total] / 0",
    }
    ev = Evaluator(_data(m))
    assert ev.measure("Total", Ctx()) == 200
    assert ev.measure("AOV", Ctx()) == 40
    assert ev.measure("Gold Total", Ctx()) == 170  # filter flows from customers to orders
    assert ev.measure("Gold Share", Ctx()) == pytest.approx(0.85)
    assert ev.measure("Big Orders", Ctx()) == 2
    assert ev.measure("Customers", Ctx()) == 3
    assert ev.measure("Weighted", Ctx()) == 400 and ev.measure("Label", Ctx()) == "big"

    year = Ctx(window=(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-03-05")))
    assert ev.measure("Total", year) == 100 and ev.measure("YTD", year) == 100
    assert ev.measure("PY", year) == 100  # 2023-01-01 .. 2023-03-05 holds the 100 order
    assert ev.measure("YoY", year) == 0
    with pytest.raises(EvalError):
        ev.measure("Bad", Ctx())


def test_parser_accepts_skipped_arguments():
    assert parse("RANKX(ALLSELECTED(t[c]), [m], , DESC, DENSE)").args[2] is None


# --- API ------------------------------------------------------------------------------

def _project(api, sample_bytes, industries=("E-commerce",)):
    pid = api.post("/api/projects", json={"name": "Shop"}).json()["id"]
    files = [("files", (n, sample_bytes[n], "application/octet-stream")) for n in ("orders.csv", "customers.xlsx", "products.csv")]
    api.post(f"/api/projects/{pid}/files", files=files)
    steps = api.get(f"/api/projects/{pid}/cleaning").json()["steps"]
    api.post(f"/api/projects/{pid}/cleaning/decisions", json={"decisions": [{"step_id": s["id"], "status": "accepted"} for s in steps]})
    ctx = api.get(f"/api/projects/{pid}/context").json()
    api.put(f"/api/projects/{pid}/context", json={**ctx, "industries": list(industries), "goals": "Grow revenue"})
    return pid


def _by_name(plan):
    return {m["name"]: m for m in plan["measures"]}


def test_measures_from_library_and_model(api, sample_bytes):
    pid = _project(api, sample_bytes)
    plan = api.get(f"/api/projects/{pid}/measures").json()
    m = _by_name(plan)
    assert plan["errors"] == 0 and plan["primary_fact"] == "orders"
    assert m["Total Revenue"]["source"] == "library" and m["Total Revenue"]["expression"] == "SUM('orders'[gross_revenue])"
    assert m["Total Revenue"]["value"] > 0 and m["Total Revenue"]["status"] == "passed"
    assert m["Average Order Value"]["folder"] == "02 Ratios & Margins"
    assert m["Average Order Value"]["value"] == pytest.approx(m["Total Revenue"]["value"] / m["Total Orders"]["value"])
    assert any(n.endswith("YoY %") for n in m) and any(x["folder"] == "04 Rankings & Pareto" for x in plan["measures"])
    assert len(plan["cards"]) == 5 and all(c["value_text"] for c in plan["cards"])
    assert plan["test_context"].startswith("Latest year: 2026")


def test_edit_reset_custom_and_export(api, sample_bytes):
    pid = _project(api, sample_bytes)
    url = f"/api/projects/{pid}/measures"
    bad = {"name": "Total Revenue", "expression": "SUM('orders'[nope])", "format": "currency", "folder": "01 Base Measures"}
    plan = api.post(url, json={"measure": bad, "original_name": "Total Revenue"}).json()
    tr = _by_name(plan)["Total Revenue"]
    assert tr["status"] == "error" and tr["edited"] and "does not exist" in tr["issues"][0]
    assert _by_name(plan)["Average Order Value"]["status"] == "error"  # depends on the broken measure

    plan = api.post(f"{url}/reset", json={"name": "Total Revenue"}).json()
    assert _by_name(plan)["Total Revenue"]["status"] == "passed" and not _by_name(plan)["Total Revenue"]["edited"]

    custom = {"name": "Big Order Share", "expression": "Big Order Share = DIVIDE(CALCULATE([Total Orders], 'orders'[quantity] >= 4), [Total Orders])", "format": "percent"}
    plan = api.post(url, json={"measure": custom}).json()
    big = _by_name(plan)["Big Order Share"]
    assert big["status"] == "passed" and big["source"] == "user" and big["expression"].startswith("DIVIDE(") and 0 < big["value"] < 1

    clash = {"name": "Total Revenue", "expression": "1", "format": "whole"}
    assert api.post(url, json={"measure": clash}).status_code == 422

    tmdl = api.get(f"{url}/export.tmdl").text
    assert "table _Measures" in tmdl and "measure 'Big Order Share' = DIVIDE(" in tmdl and "displayFolder: 05 Custom" in tmdl
    files = {f["path"] for f in api.get(f"/api/projects/{pid}/model/tmdl").json()}
    assert any(p.endswith("tables/_Measures.tmdl") for p in files)

    plan = api.post(f"{url}/delete", json={"name": "Big Order Share"}).json()
    assert "Big Order Share" not in _by_name(plan)
    plan = api.post(f"{url}/delete", json={"name": "Total Revenue"}).json()
    assert "Total Revenue" not in _by_name(plan)
    assert "Total Revenue" in _by_name(api.post(f"{url}/reset", json={"name": "Total Revenue"}).json())


def test_ai_suggestions_are_validated(api, sample_bytes):
    replies = [
        json.dumps({"measures": [
            {"name": "Prime Revenue", "expression": "CALCULATE([Total Revenue], 'orders'[is_prime] = TRUE())", "format": "currency", "folder": "02 Ratios & Margins", "description": "Revenue from Prime orders."},
            {"name": "Broken", "expression": "SUM('orders'[does_not_exist])", "format": "decimal"},
        ]}),
        json.dumps({"expression": "DIVIDE([Total Revenue], [Total Orders], 0)", "description": "Average revenue per order."}),
        json.dumps({"expression": "SUM(nope[x])", "description": "bad"}),
    ]
    llm = FakeProvider(replies=replies)
    app.dependency_overrides[get_llm] = lambda: llm
    pid = _project(api, sample_bytes)
    url = f"/api/projects/{pid}/measures"

    plan = api.post(f"{url}/suggest").json()
    m = _by_name(plan)
    assert m["Prime Revenue"]["source"] == "ai" and m["Prime Revenue"]["status"] == "passed" and "Broken" not in m
    assert any("Rejected" in n and "does_not_exist" in n for n in plan["notes"])

    plan = api.post(f"{url}/polish", json={"name": "Average Order Value"}).json()
    aov = _by_name(plan)["Average Order Value"]
    assert aov["expression"] == "DIVIDE([Total Revenue], [Total Orders], 0)" and aov["description"] == "Average revenue per order."

    plan = api.post(f"{url}/polish", json={"name": "Total Orders"}).json()
    assert any("rejected" in n for n in plan["notes"]) and _by_name(plan)["Total Orders"]["status"] == "passed"


def test_ai_needs_a_key_and_data(api, sample_bytes):
    pid = _project(api, sample_bytes)
    assert api.post(f"/api/projects/{pid}/measures/suggest").status_code == 422
    empty = api.post("/api/projects", json={}).json()["id"]
    assert api.get(f"/api/projects/{empty}/measures").status_code == 422


# --- random models ------------------------------------------------------------------------

@pytest.mark.parametrize("batch", range(6))
def test_generated_measures_on_random_models(batch):
    for seed in range(batch * 10, batch * 10 + 10):
        rng = random.Random(seed)
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
        plan = clean_plan(report, sources, {})
        decisions = {s.id: {"status": "accepted"} for s in plan.steps}
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
        industries = rng.sample(["Retail", "E-commerce", "Finance & FinTech", "Food Delivery", "HR & People", "Marketing Ops"], 2)
        ctx = GenContext(model=model, report=report, frames=frames, industries=industries)
        measure_plan, measures = build_plan(ctx, StoredMeasures(), False)
        errors = [(m.name, m.expression, m.issues) for m in measures if m.status == "error"]
        assert not errors, f"seed {seed}: {errors}"
        assert measure_plan.passed + measure_plan.edge == len(measures)

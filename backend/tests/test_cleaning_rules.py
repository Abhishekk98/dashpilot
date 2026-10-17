"""Hardened cleaning: robust reading, every new suggestion type, step isolation and AI synonyms."""

import io
import json

import openpyxl
import pandas as pd

import core.cleaning as cleaning
from app.main import app
from core.cleaning import SourceTable, run_pipeline
from core.cleaning_rules import build_plan, suggest_steps, table_pipelines
from core.profiling import build_report
from core.upload import read_tables
from llm import get_llm
from tests.fakes import FakeProvider


def _tables(files: dict[str, bytes]):
    """{filename: bytes} -> (report, sources) the way the app reads uploads."""
    sources = []
    for filename, content in files.items():
        for name, (sheet, df) in read_tables(filename, content).items():
            sources.append(SourceTable(name=name, filename=filename, sheet=sheet, delimiter=",", df=df))
    report = build_report([(s.name, "f", s.sheet, s.df) for s in sources])
    return report, sources


def _accept_all(report, sources, strategies=None):
    plan = build_plan(report, sources, {})
    decisions = {s.id: {"status": "accepted", **({"strategy": strategies[s.kind]} if strategies and s.kind in strategies else {})} for s in plan.steps}
    pipelines, warnings = table_pipelines(report, sources, decisions)
    return pipelines, warnings, plan


def _steps(report, sources, table):
    plan = build_plan(report, sources, {})
    return {s.id: s for s in plan.steps if s.table == table}


# --- reading ------------------------------------------------------------------------

def test_reader_repairs_structure_and_m_repeats_it():
    csv = (
        "Monthly Sales Report,,,\n"
        ",,,\n"
        "Order ID,Amount,,Amount,Empty\n"
        "1,10,x,11,\n"
        "2,NA,y,12\n"
        "3,N/A,z,13,,extra\n"
    ).encode("cp1252")
    (name, (sheet, df)), = read_tables("sales.csv", csv).items()
    # Blank header -> column_3, repeated -> Amount_2, ragged extra cell -> column_6, all-empty "Empty" dropped.
    assert list(df.columns) == ["Order ID", "Amount", "column_3", "Amount_2", "column_6"]
    assert df["Amount"].isna().sum() == 2  # "NA" and "N/A" are blanks
    s = df.attrs["structure"]
    assert s["header_row"] == 2 and "Empty" in s["dropped_columns"] and s["duplicate_names"] == 1

    m = run_pipeline(SourceTable(name=name, filename="sales.csv", sheet=None, delimiter=",", df=df), []).m_script
    assert '#"Skipped Title Rows" = Table.Skip(' in m and "Columns=6" in m
    assert '"Amount_2"' in m and "Table.RemoveColumns" in m and '"N/A"' in m


def test_reader_handles_excel_title_rows():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Quarterly export"])
    ws.append(["id", "city", "amount"])
    ws.append(["A1", "Pune", 5])
    ws.append(["A2", "Delhi", 7])
    buf = io.BytesIO()
    wb.save(buf)
    (name, (sheet, df)), = read_tables("q.xlsx", buf.getvalue()).items()
    assert list(df.columns) == ["id", "city", "amount"] and len(df) == 2 and df.attrs["structure"]["header_row"] == 1


# --- suggestions ----------------------------------------------------------------------

def _csv(rows: list[list]) -> bytes:
    return "\n".join(",".join('"' + str(v).replace('"', '""') + '"' if v is not None else "" for v in r) for r in rows).encode("utf-8")


def test_key_dedupe_strategies():
    rows = [["customer_id", "name", "city", "updated"]]
    rows += [[f"C{i:03d}", f"Name {i}", "Pune", "2024-01-01"] for i in range(1, 21)]
    rows += [["C001", "Name 1 (new)", "Mumbai", "2024-06-01"], ["C002", None, None, "2023-01-01"]]
    report, sources = _tables({"customers.csv": _csv(rows)})
    step = _steps(report, sources, "customers")["customers::customer_id::dedupe_key"]
    assert step.rows_affected == 2 and set(step.strategies) == {"most_complete", "first", "latest"}

    for strategy, expected_name in (("latest", "Name 1 (new)"), ("first", "Name 1"), ("most_complete", "Name 1")):
        pipelines, warnings, _ = _accept_all(report, sources, {"dedupe_key": strategy})
        df = pipelines["customers"].result.df
        assert df["customer_id"].is_unique and not warnings
        assert df.loc[df["customer_id"] == "C001", "name"].iloc[0] == expected_name
    m = pipelines["customers"].result.m_script
    assert '#"One Row Per customer_id"' in m and "Table.Buffer(Table.Sort(" in m


def test_orphans_get_unknown_member_in_dimension():
    customers = _csv([["customer_id", "name"]] + [[f"C{i}", f"N{i}"] for i in range(1, 11)])
    orders = _csv([["order_id", "customer_id", "amount"]] + [[f"O{i}", f"C{(i % 10) + 1}", "5"] for i in range(40)] + [["O99", "C77", "5"]])
    report, sources = _tables({"customers.csv": customers, "orders.csv": orders})
    step = _steps(report, sources, "orders")["orders::customer_id::orphans"]
    assert step.rows_affected == 1 and step.params == {"target_table": "customers", "target_column": "customer_id"}

    pipelines, warnings, _ = _accept_all(report, sources)
    assert not warnings
    assert "Unknown" in set(pipelines["orders"].result.df["customer_id"])
    assert "Unknown" in set(pipelines["customers"].result.df["customer_id"])
    assert 'Table.Column(#"customers", "customer_id")' in pipelines["orders"].result.m_script
    assert '#"Added Unknown Member"' in pipelines["customers"].result.m_script


def test_format_and_value_suggestions():
    rows = [["id", "gender", "active", "price_eur", "visit", "signup_serial_date", "amount", "label"]]
    data = [
        ["1", "M", "Yes", "1.234,50", "25/12/2023", "45000", "120", "A B"],
        ["2", "Male", "y", "12,00", "03/01/2024", "45001", "130", "A B"],
        ["3", "F", "No", "3.000,00", "14/02/2024", "45002", "9999999", "C"],
        ["4", "female", "n", "7,25", "01/03/2024", "45003", "110", "D"],
        ["5", "Female", "TRUE", "1,00", "05/04/2024", "45004", "150", "E"],
        ["6", "M", "0", "2,50", "07/05/2024", "45005", "140", "F"],
        ["7", "F", "1", "9,99", "08/06/2024", "45006", "125", "G"],
    ]
    report, sources = _tables({"visits.csv": _csv(rows + data + [["Total", None, None, None, None, None, "9999", None]])})
    steps = _steps(report, sources, "visits")
    kinds = {s.kind for s in steps.values()}
    assert {"remove_total_rows", "clean_whitespace", "merge_synonyms", "normalise_booleans", "cast_european",
            "date_format", "excel_serial_dates", "sentinel_values"} <= kinds
    assert steps["visits::visit::date_format"].strategy == "day_first"
    assert steps["visits::gender::synonyms"].params["mapping"]["m"] == "Male"

    pipelines, warnings, _ = _accept_all(report, sources)
    df = pipelines["visits"].result.df
    assert len(df) == 7  # the Total row is gone
    assert set(df["gender"]) == {"Male", "Female"}
    assert df["active"].tolist() == [True, True, False, False, True, False, True]
    assert df["price_eur"].iloc[0] == 1234.5
    assert df["visit"].iloc[1] == pd.Timestamp("2024-01-03")
    assert df["signup_serial_date"].iloc[0] == pd.Timestamp("2023-03-15")
    assert pd.isna(df["amount"].iloc[2])
    assert df["label"].iloc[0] == "A B"
    assert not [w for w in warnings if "Failed" in w]


def test_impossible_dates():
    rows = [["event_id", "event_date"]] + [[f"E{i}", f"2023-0{(i % 9) + 1}-01"] for i in range(20)] + [["E98", "1850-01-01"], ["E99", "2091-01-01"]]
    report, sources = _tables({"events.csv": _csv(rows)})
    step = _steps(report, sources, "events")["events::event_date::date_outliers"]
    assert step.rows_affected == 2 and step.strategy == "blank"
    pipelines, _, _ = _accept_all(report, sources)
    assert pipelines["events"].result.df["event_date"].isna().sum() == 2


def test_a_failing_step_is_isolated(monkeypatch):
    report, sources = _tables({"o.csv": _csv([["id", "city"], ["1", "Pune"], ["2", "pune"], ["2", "pune"]])})

    def boom(ctx, step):
        ctx.df["city"] = "broken"
        raise RuntimeError("bad data")

    monkeypatch.setitem(cleaning._OPS, "standardise_categories", boom)
    pipelines, warnings, _ = _accept_all(report, sources)
    result = pipelines["o"].result
    failed = [s for s in pipelines["o"].accepted if s.error]
    assert len(failed) == 1 and failed[0].error.startswith("Failed: RuntimeError")
    assert "broken" not in set(result.df["city"]) and len(result.df) == 2  # rolled back; dedupe still applied
    assert "Standardised" not in result.m_script and any("bad data" in w for w in warnings)


def test_detector_failure_is_isolated(monkeypatch):
    report, sources = _tables({"o.csv": _csv([["id", "city"], ["1", "Pune"], ["1", "Pune"]])})
    import core.cleaning_rules as rules

    def broken(t, df, ctx):
        raise ValueError("odd column")

    monkeypatch.setattr(rules, "DETECTORS", [broken, *rules.DETECTORS[1:]])
    plan = build_plan(report, sources, {})
    assert any(s.kind == "remove_duplicates" for s in plan.steps) and any("skipped" in w for w in plan.warnings)


# --- AI synonyms through the API ----------------------------------------------------------

def test_ai_synonym_scan(api):
    content = _csv([["store", "region"]] + [[f"S{i}", r] for i, r in enumerate(["North", "N. Region", "South", "Sth", "North"] * 4)])
    answer = {"groups": [
        {"table": "stores", "column": "region", "canonical": "North", "variants": ["N. Region"]},
        {"table": "stores", "column": "region", "canonical": "South", "variants": ["Sth", "Nowhere"]},
    ]}
    llm = FakeProvider(replies=[json.dumps(answer)])
    app.dependency_overrides[get_llm] = lambda: llm
    pid = api.post("/api/projects", json={}).json()["id"]
    api.post(f"/api/projects/{pid}/files", files=[("files", ("stores.csv", content, "text/csv"))])

    assert api.get(f"/api/projects/{pid}/cleaning").json()["ai_synonyms"] == "available"
    plan = api.post(f"/api/projects/{pid}/cleaning/synonyms").json()
    step = next(s for s in plan["steps"] if s["kind"] == "merge_synonyms")
    assert plan["ai_synonyms"] == "done" and step["source"] == "ai"
    assert step["params"]["mapping"] == {"n. region": "North", "sth": "South"}
    assert api.get(f"/api/projects/{pid}/cleaning").json()["ai_synonyms"] == "done" and len(llm.calls) == 1

    failing = FakeProvider(replies=["not json"])
    app.dependency_overrides[get_llm] = lambda: failing
    pid2 = api.post("/api/projects", json={}).json()["id"]
    api.post(f"/api/projects/{pid2}/files", files=[("files", ("stores.csv", content, "text/csv"))])
    plan = api.post(f"/api/projects/{pid2}/cleaning/synonyms").json()
    assert plan["ai_synonyms"] == "failed" and plan["ai_note"]
    assert not any(s["kind"] == "merge_synonyms" for s in plan["steps"])

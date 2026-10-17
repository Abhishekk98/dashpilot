"""Cleaning suggestions, the pandas pipeline, the generated M script and the cleaning API."""

import pandas as pd

from core.cleaning import SourceTable, m_text, run_pipeline
from core.cleaning_rules import suggest_steps
from core.profiling import profile_table


def _frame(data: dict) -> pd.DataFrame:
    return pd.DataFrame(data, dtype="string")


def _messy():
    df = _frame(
        {
            "order_id": ["O1", "O2", "O3", "O3", "O5", "O6"],
            "city": ["Delhi", "delhi", "Delhi", "Delhi", "Pune", None],
            "revenue": ["$1,200.50", "$80.00", "$15.25", "$15.25", None, "$40.00"],
            "discount": ["5%", "10%", "0%", "0%", None, "5%"],
            "is_prime": ["Yes", "No", "Yes", "Yes", "No", "No"],
        }
    )
    profile = profile_table("orders", "f1", None, df)
    return SourceTable(name="orders", filename="orders.csv", sheet=None, delimiter=",", df=df), profile


def test_suggestions_cover_the_spec_cases():
    src, profile = _messy()
    steps = {s.id: s for s in suggest_steps(profile, src.df)}
    assert steps["orders::dedupe"].rows_affected == 1
    assert steps["orders::city::standardise"].merges[0].canonical == "Delhi"
    assert steps["orders::city::standardise"].merges[0].variants == {"delhi": 1}
    assert steps["orders::revenue::cast"].types == {"revenue": "currency"}
    assert steps["orders::discount::cast"].types == {"discount": "percentage"}
    assert steps["orders::types"].types == {"is_prime": "boolean"}
    # Money is never filled with an invented median by default; categories get an explicit member.
    assert steps["orders::revenue::nulls"].strategy == "flag"
    assert steps["orders::discount::nulls"].strategy == "fill_median"
    assert steps["orders::city::nulls"].strategy == "fill_unknown"
    assert all(s.status == "pending" for s in steps.values())


def test_pipeline_applies_steps_and_mirrors_them_in_m():
    src, profile = _messy()
    steps = suggest_steps(profile, src.df)
    result = run_pipeline(src, steps)
    df = result.df

    assert len(df) == 5 and result.dropped == {3: "duplicate"}
    assert list(df["city"]) == ["Delhi", "Delhi", "Delhi", "Pune", "Unknown"]
    assert df["revenue"].iloc[0] == 1200.5 and pd.isna(df["revenue"].iloc[3])
    assert "revenue_is_missing" in df.columns and bool(df["revenue_is_missing"].iloc[3])
    assert df["discount"].iloc[0] == 0.05
    assert df["discount"].iloc[3] == 0.05  # median 5% after de-duplication, stored as a fraction
    assert list(df["is_prime"]) == [True, False, True, False, False]

    assert not result.warnings and not any(s.error for s in steps)

    m = result.m_script
    assert 'Csv.Document(File.Contents(DataFolder & "orders.csv"), [Delimiter=","' in m
    for name in ("Removed Duplicates", "Standardised city", "Cast revenue", "Cast discount",
                 "Typed is_prime", "Filled city", "Flagged Missing revenue", "Filled discount"):
        assert f'#"{name}" = ' in m
    assert '#"delhi" = "Delhi"' in m and "Currency.Type" in m and "Percentage.Type" in m
    # Value conversions never raise refresh errors: they go through try ... otherwise null helpers.
    assert '#"fnNumber" = (v) =>' in m and "otherwise null" in m and "TransformColumnTypes" not in m
    assert 'Table.ReplaceValue(#"Flagged Missing revenue", null, 0.05, ' in m
    assert m.rstrip().endswith('#"Filled discount"')


def test_no_steps_keeps_data_and_source_query():
    src, _ = _messy()
    result = run_pipeline(src, [])
    assert len(result.df) == 6 and not result.dropped
    assert result.m_script.rstrip().endswith('#"Removed Empty Rows"')


def test_m_text_escaping():
    assert m_text('say "hi"\n') == '"say ""hi""#(lf)"'


# --- API ------------------------------------------------------------------------------

def _project(api, sample_bytes):
    pid = api.post("/api/projects", json={"name": "p"}).json()["id"]
    api.post(f"/api/projects/{pid}/files", files=[("files", ("orders.csv", sample_bytes["orders.csv"], "text/csv"))])
    return pid


def test_cleaning_api_flow(api, sample_bytes):
    pid = _project(api, sample_bytes)
    plan = api.get(f"/api/projects/{pid}/cleaning").json()
    kinds = {s["kind"] for s in plan["steps"]}
    assert {"standardise_categories", "cast_numeric", "handle_nulls"} <= kinds
    assert plan["accepted"] == 0 and plan["score_after"] == plan["score_before"]
    assert plan["tables"][0]["m_script"].rstrip().endswith('#"Removed Empty Rows"')

    preview = api.get(f"/api/projects/{pid}/cleaning/preview", params={"table": "orders"}).json()
    assert preview["accepted_steps"] == 0 and preview["transformed_rows"] == 0

    decisions = [{"step_id": s["id"], "status": "accepted"} for s in plan["steps"]]
    plan = api.post(f"/api/projects/{pid}/cleaning/decisions", json={"decisions": decisions}).json()
    assert plan["accepted"] == plan["total"]
    assert plan["score_after"] >= plan["score_before"]
    assert '#"Standardised destination_city"' in plan["tables"][0]["m_script"]

    preview = api.get(f"/api/projects/{pid}/cleaning/preview", params={"table": "orders"}).json()
    assert preview["columns"][0] == "order_id" and preview["transformed_rows"] > 0
    assert any(r["status"] == "transformed" for r in preview["rows"])

    # Decisions survive a reload; a strategy change re-titles the step.
    nulls = next(s for s in plan["steps"] if s["kind"] == "handle_nulls")
    body = {"decisions": [{"step_id": nulls["id"], "strategy": "remove_rows"}]}
    plan = api.post(f"/api/projects/{pid}/cleaning/decisions", json=body).json()
    step = next(s for s in plan["steps"] if s["id"] == nulls["id"])
    assert step["strategy"] == "remove_rows" and step["title"].startswith("Remove") and step["status"] == "accepted"


def test_cleaning_api_errors(api, sample_bytes):
    pid = _project(api, sample_bytes)
    bad = {"decisions": [{"step_id": "orders::nope", "status": "accepted"}]}
    assert api.post(f"/api/projects/{pid}/cleaning/decisions", json=bad).status_code == 422
    dedupe_less = next(s for s in api.get(f"/api/projects/{pid}/cleaning").json()["steps"] if s["kind"] == "cast_numeric")
    bad = {"decisions": [{"step_id": dedupe_less["id"], "strategy": "fill_median"}]}
    assert api.post(f"/api/projects/{pid}/cleaning/decisions", json=bad).status_code == 422
    assert api.get(f"/api/projects/{pid}/cleaning/preview", params={"table": "nope"}).status_code == 404
    assert api.get("/api/projects/missing/cleaning").status_code == 404

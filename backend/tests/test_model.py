"""Data model: fact/dimension rules, relationships on cleaned data, date table, settings, AI, TMDL."""

import io
import json
import zipfile

from app.main import app
from llm import LLMRateLimitError, get_llm
from tests.fakes import FakeProvider

README = b"section,text\nAbout,This workbook holds orders\nOwner,Sales team\n"


def _project(api, sample_bytes, extra=()):
    pid = api.post("/api/projects", json={"name": "Sales Model"}).json()["id"]
    files = [
        ("files", ("orders.csv", sample_bytes["orders.csv"], "text/csv")),
        ("files", ("customers.xlsx", sample_bytes["customers.xlsx"], "application/octet-stream")),
        ("files", ("products.csv", sample_bytes["products.csv"], "text/csv")),
        *extra,
    ]
    api.post(f"/api/projects/{pid}/files", files=files)
    return pid


def _accept_all_cleaning(api, pid):
    steps = api.get(f"/api/projects/{pid}/cleaning").json()["steps"]
    api.post(f"/api/projects/{pid}/cleaning/decisions", json={"decisions": [{"step_id": s["id"], "status": "accepted"} for s in steps]})


def _tables(plan):
    return {t["name"]: t for t in plan["tables"]}


def _rels(plan):
    return {r["id"]: r for r in plan["relationships"]}


ORDERS_CUSTOMERS = "orders.customer_id->customers_Customers.customer_id"
ORDERS_PRODUCTS = "orders.product_id->products.product_id"


def test_star_schema_from_raw_and_cleaned_data(api, sample_bytes):
    pid = _project(api, sample_bytes, extra=[("files", ("README.csv", README, "text/csv"))])
    plan = api.get(f"/api/projects/{pid}/model").json()
    tables = _tables(plan)
    assert tables["orders"]["kind"] == "fact" and tables["orders"]["grain"] == "1 row per order_id"
    assert tables["products"]["kind"] == "dimension" and tables["customers_Customers"]["kind"] == "dimension"
    assert not tables["README"]["included"] and tables["README"]["exclusion_reason"]

    # Raw customers contain exact duplicate rows -> cannot be the 1 side yet; nothing is typed yet.
    rels = _rels(plan)
    assert not rels[ORDERS_CUSTOMERS]["valid"] and "duplicate" in rels[ORDERS_CUSTOMERS]["note"]
    assert rels[ORDERS_PRODUCTS]["valid"] and rels[ORDERS_PRODUCTS]["cardinality"] == "many_to_one"
    assert not plan["date_table"]["enabled"] and any(n["title"] == "Date columns still text" for n in plan["notes"])

    _accept_all_cleaning(api, pid)
    plan = api.get(f"/api/projects/{pid}/model").json()
    rels = _rels(plan)
    assert rels[ORDERS_CUSTOMERS]["valid"] and rels[ORDERS_CUSTOMERS]["active"]
    date_rel = rels["orders.order_timestamp_date->Dim_Date.Date"]
    assert date_rel["origin"] == "date" and date_rel["active"]
    assert plan["date_table"]["enabled"] and plan["date_table"]["start"] == "2026-01-01"
    orders_cols = {c["name"]: c for c in _tables(plan)["orders"]["columns"]}
    assert orders_cols["order_timestamp_date"]["derived"] and orders_cols["customer_id"]["hidden"]
    assert orders_cols["gross_revenue"]["data_type"] == "decimal" and orders_cols["gross_revenue"]["measure_candidate"]
    assert plan["ambiguities"] == 0 and plan["tmdl_valid"] and plan["health_score"] >= 85


def test_settings_override_rules(api, sample_bytes):
    pid = _project(api, sample_bytes)
    _accept_all_cleaning(api, pid)
    settings = {
        "table_overrides": {"products": {"included": False}, "customers_Segments": {"kind": "fact"}},
        "removed_relationships": [ORDERS_CUSTOMERS],
        "added_relationships": [],
        "fiscal_year_start_month": 4,
        "hide_keys": False,
        "date_table": True,
    }
    plan = api.put(f"/api/projects/{pid}/model", json=settings).json()
    tables = _tables(plan)
    assert not tables["products"]["included"]
    assert tables["customers_Segments"]["kind"] == "fact" and tables["customers_Segments"]["kind_source"] == "user"
    assert ORDERS_CUSTOMERS not in _rels(plan) and ORDERS_PRODUCTS not in _rels(plan)
    assert plan["hidden_columns"] == 0 and plan["date_table"]["fiscal_year_start_month"] == 4
    assert api.get(f"/api/projects/{pid}/model").json()["settings"]["fiscal_year_start_month"] == 4

    files = {f["path"]: f["content"] for f in api.get(f"/api/projects/{pid}/model/tmdl").json()}
    date_tmdl = next(c for p, c in files.items() if p.endswith("tables/Dim_Date.tmdl"))
    assert "dataCategory: Time" in date_tmdl and "isKey" in date_tmdl and ">= 4" in date_tmdl
    assert not any(p.endswith("tables/products.tmdl") for p in files)


def test_user_relationship_and_ambiguity(api, sample_bytes):
    pid = _project(api, sample_bytes)
    _accept_all_cleaning(api, pid)
    # A user copy of an auto relationship is ignored; a second path between two tables is made inactive.
    extra = {"from_table": "orders", "from_column": "customer_id", "to_table": "customers_Customers", "to_column": "customer_id"}
    dup = {"from_table": "customers_Customers", "from_column": "customer_id", "to_table": "orders", "to_column": "order_id"}
    settings = {"added_relationships": [extra, dup]}
    plan = api.put(f"/api/projects/{pid}/model", json=settings).json()
    rels = _rels(plan)
    assert rels[ORDERS_CUSTOMERS]["origin"] == "auto"  # the user's copy of an auto relationship is not duplicated
    cycle = rels["customers_Customers.customer_id->orders.order_id"]
    assert cycle["origin"] == "user" and not cycle["active"] and plan["ambiguities"] == 1


def test_tmdl_files_and_zip(api, sample_bytes):
    pid = _project(api, sample_bytes)
    _accept_all_cleaning(api, pid)
    files = {f["path"]: f["content"] for f in api.get(f"/api/projects/{pid}/model/tmdl").json()}
    root = "Sales_Model.SemanticModel"
    assert f"{root}/definition.pbism" in files
    model = files[f"{root}/definition/model.tmdl"]
    assert "ref table orders" in model and "ref table Dim_Date" in model
    rels = files[f"{root}/definition/relationships.tmdl"]
    assert "fromColumn: orders.customer_id" in rels and "toColumn: customers_Customers.customer_id" in rels
    orders = files[f"{root}/definition/tables/orders.tmdl"]
    assert "partition orders = m" in orders and 'DataFolder & "orders.csv"' in orders
    assert '#"Added order_timestamp_date"' in orders and "isHidden" in orders
    assert "expression DataFolder" in files[f"{root}/definition/expressions.tmdl"]

    res = api.get(f"/api/projects/{pid}/model/tmdl.zip")
    assert res.status_code == 200 and res.headers["content-type"] == "application/zip"
    assert set(zipfile.ZipFile(io.BytesIO(res.content)).namelist()) == set(files)


def test_ai_classification_is_cached_and_failures_fall_back(api, sample_bytes):
    answer = {
        "tables": [{"table": "customers_Segments", "kind": "dimension", "include": False, "reason": "Lookup notes only"}],
        "notes": [{"title": "Role-playing dates", "text": "Only one date column is used."}],
    }
    llm = FakeProvider(replies=[json.dumps(answer)])
    app.dependency_overrides[get_llm] = lambda: llm
    pid = _project(api, sample_bytes)

    assert api.get(f"/api/projects/{pid}/model").json()["ai_status"] == "pending" and llm.calls == []
    plan = api.get(f"/api/projects/{pid}/model?ai=true").json()
    seg = _tables(plan)["customers_Segments"]
    assert plan["ai_status"] == "done" and not seg["included"] and seg["exclusion_reason"] == "Lookup notes only"
    assert any(n["title"] == "Role-playing dates" for n in plan["notes"])
    assert api.get(f"/api/projects/{pid}/model?ai=true").json()["ai_status"] == "done" and len(llm.calls) == 1

    # The user's choice beats the AI.
    plan = api.put(f"/api/projects/{pid}/model", json={"table_overrides": {"customers_Segments": {"included": True}}}).json()
    assert _tables(plan)["customers_Segments"]["included"]

    failing = FakeProvider(errors=[LLMRateLimitError("quota")], max_retries=0)
    app.dependency_overrides[get_llm] = lambda: failing
    pid2 = _project(api, sample_bytes)
    plan = api.get(f"/api/projects/{pid2}/model?ai=true").json()
    assert plan["ai_status"] == "failed" and plan["ai_note"] == "quota" and _tables(plan)["orders"]["kind"] == "fact"


def test_model_needs_data(api):
    pid = api.post("/api/projects", json={}).json()["id"]
    assert api.get(f"/api/projects/{pid}/model").status_code == 422
    assert api.get("/api/projects/missing/model").status_code == 404

"""Two-phase profiling: fast rule-based report first, AI refinement on a second request."""

import json

from app.main import app
from llm import get_llm
from tests.fakes import FakeProvider


def _project_with_orders(api, sample_bytes):
    pid = api.post("/api/projects", json={"name": "p"}).json()["id"]
    api.post(f"/api/projects/{pid}/files", files=[("files", ("orders.csv", sample_bytes["orders.csv"], "text/csv"))])
    return pid


def _use_llm(provider):
    app.dependency_overrides[get_llm] = lambda: provider


def test_rule_based_first_then_ai(api, sample_bytes):
    answer = {"columns": [{"table": "orders", "column": "quantity", "role": "measure", "confidence": 0.97}]}
    llm = FakeProvider(replies=[json.dumps(answer)])
    _use_llm(llm)
    pid = _project_with_orders(api, sample_bytes)

    fast = api.get(f"/api/projects/{pid}/profile?ai=false").json()
    assert fast["ai_status"] == "pending" and not fast["ai_refined"]
    assert llm.calls == []  # the fast phase never touches the LLM

    refined = api.get(f"/api/projects/{pid}/profile").json()
    assert refined["ai_status"] == "done" and refined["ai_refined"]

    # Cached: neither phase calls the LLM again.
    assert api.get(f"/api/projects/{pid}/profile").json()["ai_status"] == "done"
    assert api.get(f"/api/projects/{pid}/profile?ai=false").json()["ai_status"] == "done"
    assert len(llm.calls) == 1


def test_ai_failure_is_reported_not_raised(api, sample_bytes):
    _use_llm(FakeProvider(replies=["not json"]))
    pid = _project_with_orders(api, sample_bytes)
    report = api.get(f"/api/projects/{pid}/profile").json()
    assert report["ai_status"] == "failed" and report["ai_note"]
    assert report["tables"]  # rule-based results are still there


def test_no_key_means_ai_off(api, sample_bytes):
    pid = _project_with_orders(api, sample_bytes)
    assert api.get(f"/api/projects/{pid}/profile?ai=false").json()["ai_status"] == "off"
    assert api.get(f"/api/projects/{pid}/profile").json()["ai_status"] == "off"

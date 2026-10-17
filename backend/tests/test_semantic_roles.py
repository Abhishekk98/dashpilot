from core.profiling import build_report
from core.semantic_roles import ColumnRole, RoleAnswer, refine_roles
from core.upload import read_tables
from llm import LLMRateLimitError
from tests.fakes import FakeProvider


def _report(sample_bytes):
    name, (sheet, df) = next(iter(read_tables("orders.csv", sample_bytes["orders.csv"]).items()))
    return build_report([(name, "f", sheet, df)])


def test_ai_roles_are_merged(sample_bytes):
    answer = RoleAnswer(
        columns=[
            ColumnRole(table="orders", column="quantity", role="measure", confidence=0.97),
            ColumnRole(table="orders", column="is_prime", role="categorical_slicer", confidence=0.8),
            # Points to a table that does not exist -> ignored.
            ColumnRole(table="orders", column="customer_id", role="foreign_key", target_table="nope", confidence=0.9),
        ]
    )
    llm = FakeProvider(replies=[answer.model_dump_json()])
    report = refine_roles(_report(sample_bytes), llm)

    cols = {c.name: c for c in report.tables[0].column_profiles}
    assert report.ai_refined
    assert cols["quantity"].confidence == 0.97 and cols["quantity"].role_source == "ai"
    assert cols["is_prime"].role == "categorical_slicer"
    assert cols["customer_id"].role == "identifier" and cols["customer_id"].role_source == "rules"
    assert "orders" in llm.calls[0]["prompt"] and llm.calls[0]["json_schema"] is RoleAnswer


def test_ai_failure_keeps_rule_roles(sample_bytes):
    llm = FakeProvider(errors=[LLMRateLimitError("quota")] * 10)
    report = refine_roles(_report(sample_bytes), llm)
    assert not report.ai_refined
    assert all(c.role_source == "rules" for c in report.tables[0].column_profiles)


def test_invalid_json_keeps_rule_roles(sample_bytes):
    report = refine_roles(_report(sample_bytes), FakeProvider(replies=["not json"]))
    assert not report.ai_refined


def test_no_provider_skips_ai(sample_bytes):
    assert not refine_roles(_report(sample_bytes), None).ai_refined

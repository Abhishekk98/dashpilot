"""AI refinement of the rule-based semantic roles (Spec Module 2, "semantic role detection with AI")."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from core.profiling import QualityReport, SemanticRole, summarise
from llm import LLMError, LLMProvider

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "profiling_roles.md"


class ColumnRole(BaseModel):
    table: str
    column: str
    role: SemanticRole
    target_table: str | None = None
    confidence: float = Field(ge=0, le=1)
    # No free-text "reason": it roughly doubled the output tokens (and wait time) on wide workbooks.


class RoleAnswer(BaseModel):
    columns: list[ColumnRole]


def _profile_digest(report: QualityReport) -> str:
    """Compact, token-cheap description of every column for the prompt."""
    tables = []
    for t in report.tables:
        tables.append(
            {
                "table": t.name,
                "rows": t.rows,
                "columns": [
                    {
                        "column": c.name,
                        "type": c.detected_type,
                        "distinct": c.distinct_count,
                        "null_pct": c.null_pct,
                        "samples": c.sample_values,
                        "rule_role": c.role,
                        "rule_target": c.role_target,
                    }
                    for c in t.column_profiles
                ],
            }
        )
    return json.dumps(tables, separators=(",", ":"))  # compact = fewer input tokens


def refine_roles(report: QualityReport, llm: LLMProvider | None) -> QualityReport:
    """Return the report with AI roles merged in; on any AI failure keep the rule-based roles.

    The returned report's ai_status is "done", "failed" (ai_note explains) or "off" (no provider).
    """
    if llm is None or not report.tables:
        report.ai_status = "off"
        return report

    prompt = PROMPT_PATH.read_text(encoding="utf-8").replace("{profile}", _profile_digest(report))
    try:
        answer = llm.generate_text(prompt, json_schema=RoleAnswer)
    except LLMError as exc:
        logger.warning("Semantic role refinement skipped: %s", exc)
        return _failed(report, str(exc))
    except Exception as exc:  # network/API errors must never break profiling
        logger.exception("Semantic role refinement failed")
        return _failed(report, f"AI request failed ({type(exc).__name__})")

    table_names = {t.name for t in report.tables}
    by_key = {(r.table, r.column): r for r in answer.columns}
    for table in report.tables:
        for col in table.column_profiles:
            ai = by_key.get((table.name, col.name))
            # Ignore missing answers and foreign keys pointing at tables that do not exist.
            if ai is None or (ai.role == "foreign_key" and ai.target_table not in table_names):
                continue
            col.role = ai.role
            col.role_target = ai.target_table if ai.role == "foreign_key" else None
            col.confidence = round(ai.confidence, 2)
            col.role_source = "ai"
    # Rebuild headline/signal text so it reflects the refined roles.
    refined = summarise(report.tables)
    refined.ai_refined = True
    refined.ai_status = "done"
    return refined


def _failed(report: QualityReport, note: str) -> QualityReport:
    report.ai_status = "failed"
    report.ai_note = note
    return report

"""Glue between stored projects and the cleaning modules (keeps route handlers thin)."""

from __future__ import annotations

import logging

from core.cleaning import CleaningPlan, CleaningStep, Decision, DiffPreview, PipelineResult, SourceTable, preview
from core.cleaning_rules import ai_error_note, ai_synonyms, build_plan, table_pipelines
from core.profiling import QualityReport
from core.profiling_service import get_report
from core.projects import Project, ProjectStore
from core.upload import csv_delimiter, read_tables
from llm import LLMProvider

logger = logging.getLogger(__name__)

# Parsed tables of the last few file sets, so toggling a step does not re-read Excel files.
_SOURCES: dict[tuple[str, tuple[str, ...]], list[SourceTable]] = {}
_MAX_CACHED = 4
AI_FILE = "cleaning_ai.json"


class CleaningError(LookupError):
    """Unknown step, table or strategy (user-facing message)."""


def load_sources(store: ProjectStore, project: Project) -> list[SourceTable]:
    key = (project.id, tuple(f.id for f in project.files))
    if key not in _SOURCES:
        sources = []
        for stored in project.files:
            content = store.file_path(project.id, stored).read_bytes()
            delimiter = csv_delimiter(content) if stored.extension == ".csv" else ","
            for name, (sheet, df) in read_tables(stored.filename, content).items():
                sources.append(SourceTable(name=name, filename=stored.filename, sheet=sheet, delimiter=delimiter, df=df))
        while len(_SOURCES) >= _MAX_CACHED:
            _SOURCES.pop(next(iter(_SOURCES)))
        _SOURCES[key] = sources
    return _SOURCES[key]


def _signature(report: QualityReport) -> list[str]:
    return [f"{t.name}:{t.rows}:{t.columns}" for t in report.tables]


def _ai_state(store: ProjectStore, project: Project, report: QualityReport) -> dict:
    data = store.read_json(project.id, AI_FILE)
    return data if data.get("signature") == _signature(report) else {}


def get_plan(store: ProjectStore, project: Project, llm: LLMProvider | None) -> CleaningPlan:
    # ai=False: the cleaning screen never waits on the LLM; it uses whatever roles are cached.
    report = get_report(store, project, llm, ai=False)
    ai = _ai_state(store, project, report)
    plan = build_plan(report, load_sources(store, project), store.read_cleaning(project.id), ai.get("mappings"))
    plan.ai_synonyms = ai.get("status") or ("available" if llm is not None else "off")
    plan.ai_note = ai.get("note")
    return plan


def run_ai_synonyms(store: ProjectStore, project: Project, llm: LLMProvider | None) -> CleaningPlan:
    """Ask the LLM for synonym groups once per file set; failures are reported, never raised."""
    report = get_report(store, project, llm, ai=False)
    if llm is not None:
        try:
            state = {"status": "done", "note": None, "mappings": ai_synonyms(report, load_sources(store, project), llm)}
        except Exception as exc:
            logger.warning("AI synonym scan failed: %s", exc)
            state = {"status": "failed", "note": ai_error_note(exc), "mappings": {}}
        store.write_json(project.id, AI_FILE, {"signature": _signature(report), **state})
    return get_plan(store, project, llm)


def save_decisions(
    store: ProjectStore, project: Project, llm: LLMProvider | None, decisions: list[Decision]
) -> CleaningPlan:
    steps = {s.id: s for s in get_plan(store, project, llm).steps}
    data = store.read_cleaning(project.id)
    for d in decisions:
        step = steps.get(d.step_id)
        if step is None:
            raise CleaningError(f"Unknown cleaning step: {d.step_id}")
        if d.strategy is not None and d.strategy not in step.strategies:
            raise CleaningError(f"{d.strategy} is not available for {d.step_id}")
        entry = data.setdefault(d.step_id, {})
        if d.status is not None:
            entry["status"] = d.status
        if d.strategy is not None:
            entry["strategy"] = d.strategy
    store.write_cleaning(project.id, data)
    return get_plan(store, project, llm)


def cleaned_tables(
    store: ProjectStore, project: Project, report: QualityReport
) -> dict[str, tuple[SourceTable, list[CleaningStep], PipelineResult]]:
    """Every profiled table after its accepted cleaning steps (what Power BI will load)."""
    ai = _ai_state(store, project, report)
    pipelines, _ = table_pipelines(report, load_sources(store, project), store.read_cleaning(project.id), ai.get("mappings"))
    return {name: (p.src, [s for s in p.accepted if not s.error], p.result) for name, p in pipelines.items()}


def get_preview(store: ProjectStore, project: Project, llm: LLMProvider | None, table: str) -> DiffPreview:
    report = get_report(store, project, llm, ai=False)
    profiles = {t.name: t for t in report.tables}
    if table not in profiles:
        raise CleaningError(f"Unknown table: {table}")
    ai = _ai_state(store, project, report)
    pipelines, _ = table_pipelines(report, load_sources(store, project), store.read_cleaning(project.id), ai.get("mappings"))
    p = pipelines.get(table)
    if p is None:
        raise CleaningError(f"Unknown table: {table}")
    key = next((c.name for c in profiles[table].column_profiles if c.role == "primary_key"), None)
    return preview(p.src, p.result, [s for s in p.accepted if not s.error], key)

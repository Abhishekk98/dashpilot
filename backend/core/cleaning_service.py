"""Glue between stored projects and the cleaning module (keeps route handlers thin)."""

from __future__ import annotations

from core.cleaning import (
    CleaningPlan,
    CleaningStep,
    Decision,
    DiffPreview,
    PipelineResult,
    SourceTable,
    apply_decisions,
    build_plan,
    preview,
    run_pipeline,
    suggest_steps,
)
from core.profiling import QualityReport
from core.profiling_service import get_report
from core.projects import Project, ProjectStore
from core.upload import csv_delimiter, read_tables
from llm import LLMProvider

# Parsed tables of the last few file sets, so toggling a step does not re-read Excel files.
_SOURCES: dict[tuple[str, tuple[str, ...]], list[SourceTable]] = {}
_MAX_CACHED = 4


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


def get_plan(store: ProjectStore, project: Project, llm: LLMProvider | None) -> CleaningPlan:
    # ai=False: the cleaning screen never waits on the LLM; it uses whatever roles are cached.
    report = get_report(store, project, llm, ai=False)
    return build_plan(report, load_sources(store, project), store.read_cleaning(project.id))


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
    profiles = {t.name: t for t in report.tables}
    decisions = store.read_cleaning(project.id)
    out = {}
    for src in load_sources(store, project):
        if src.name not in profiles:
            continue
        steps = suggest_steps(profiles[src.name], src.df)
        apply_decisions(steps, decisions, profiles)
        accepted = [s for s in steps if s.status == "accepted"]
        out[src.name] = (src, accepted, run_pipeline(src, accepted))
    return out


def get_preview(store: ProjectStore, project: Project, llm: LLMProvider | None, table: str) -> DiffPreview:
    report = get_report(store, project, llm, ai=False)
    profiles = {t.name: t for t in report.tables}
    src = next((s for s in load_sources(store, project) if s.name == table), None)
    if src is None or table not in profiles:
        raise CleaningError(f"Unknown table: {table}")
    steps = suggest_steps(profiles[table], src.df)
    apply_decisions(steps, store.read_cleaning(project.id), profiles)
    key = next((c.name for c in profiles[table].column_profiles if c.role == "primary_key"), None)
    return preview(src, steps, key)

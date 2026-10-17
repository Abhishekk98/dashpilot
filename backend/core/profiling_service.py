"""Glue between stored project files and the profiler (keeps route handlers thin)."""

from __future__ import annotations

import csv
import io

from core.profiling import READER_VERSION, QualityReport, build_report
from core.projects import Project, ProjectStore
from core.semantic_roles import refine_roles
from core.upload import read_tables
from llm import LLMProvider


def load_frames(store: ProjectStore, project: Project):
    """Yield (table_name, file_id, sheet, DataFrame) for every table in the project."""
    for stored in project.files:
        content = store.file_path(project.id, stored).read_bytes()
        for name, (sheet, df) in read_tables(stored.filename, content).items():
            yield name, stored.id, sheet, df


def get_report(
    store: ProjectStore,
    project: Project,
    llm: LLMProvider | None,
    refresh: bool = False,
    ai: bool = True,
) -> QualityReport:
    """Return the project's quality report, profiling the files when nothing is cached.

    Profiling runs in two phases so the UI never waits on the LLM for the basics:
    ai=False returns the fast rule-based report (ai_status "pending" when a provider is set);
    ai=True additionally runs the AI role refinement once and caches the refined report.
    """
    cached = None if refresh else store.read_profile(project.id)
    if cached is not None and cached.get("reader_version", 1) != READER_VERSION:
        cached = None  # files are read differently now; column names / nulls may differ
    if cached is not None:
        report = QualityReport.model_validate(cached)
        if report.ai_refined:
            report.ai_status = "done"  # reports cached before ai_status existed
    else:
        report = build_report(list(load_frames(store, project)))
        report.ai_status = "pending" if llm else "off"
        _write_if_current(store, project, report)

    # A key added (or removed) after the report was cached.
    if report.ai_status == "off" and llm is not None:
        report.ai_status = "pending"
    elif report.ai_status == "pending" and llm is None:
        report.ai_status = "off"

    if ai and report.ai_status == "pending":
        report = refine_roles(report, llm)
        _write_if_current(store, project, report)
    return report


def _write_if_current(store: ProjectStore, project: Project, report: QualityReport) -> None:
    """Cache the report unless files changed while we were profiling (the AI call can be slow)."""
    latest = store.get(project.id)
    if [f.id for f in latest.files] == [f.id for f in project.files]:
        store.write_profile(project.id, report.model_dump(mode="json"))


def columns_csv(report: QualityReport) -> str:
    """Flat CSV of every profiled column ("Export Profiler CSV")."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["table", "column", "detected_type", "null_pct", "distinct_count", "role", "role_target",
         "confidence", "needs_casting", "inconsistent_values", "min", "max", "mean", "median",
         "outliers", "date_min", "date_max", "sample_values"]
    )
    for t in report.tables:
        for c in t.column_profiles:
            n, d = c.numeric, c.dates
            writer.writerow(
                [t.name, c.name, c.detected_type, c.null_pct, c.distinct_count, c.role, c.role_target or "",
                 c.confidence, c.needs_casting, c.inconsistent_values,
                 n.min if n else "", n.max if n else "", n.mean if n else "", n.median if n else "",
                 n.outliers if n else "", d.min if d else "", d.max if d else "", " | ".join(c.sample_values)]
            )
    return out.getvalue()

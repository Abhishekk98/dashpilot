"""Glue between stored projects and the KPI/DAX module (keeps route handlers thin)."""

from __future__ import annotations

import logging

import pandas as pd

from core import tmdl
from core.context_service import get_context
from core.dax import (
    GenContext,
    MeasureInput,
    MeasurePlan,
    StoredMeasures,
    ai_note,
    ai_polish,
    ai_suggest,
    assemble,
    build_plan,
    schema_for,
)
from core.dax_eval import date_frame
from core.dax_validate import check
from core.modelling import DATE_TABLE
from core.modelling_service import build_with_results
from core.projects import Project, ProjectStore
from llm import LLMProvider

logger = logging.getLogger(__name__)
FILE = "measures.json"


class MeasureError(ValueError):
    """User-facing problem (unknown measure, name clash, no AI key)."""


def _stored(store: ProjectStore, project: Project) -> StoredMeasures:
    return StoredMeasures.model_validate(store.read_json(project.id, FILE))


def _save(store: ProjectStore, project: Project, stored: StoredMeasures) -> None:
    store.write_json(project.id, FILE, stored.model_dump())


def gen_context(store: ProjectStore, project: Project, llm: LLMProvider | None) -> GenContext:
    from core.profiling_service import get_report

    report = get_report(store, project, llm, ai=False)
    model, results = build_with_results(store, project, llm)
    frames: dict[str, pd.DataFrame] = {}
    for t in model.tables:
        if not t.included or t.name not in results:
            continue
        df = results[t.name].df.reset_index(drop=True).copy()
        for c in t.columns:
            if c.derived and c.name not in df.columns:  # date-only keys added for the date table
                df[c.name] = pd.to_datetime(df[c.name.removesuffix("_date")], errors="coerce").dt.normalize()
        frames[t.name] = df
    if model.date_table.enabled and model.date_table.start and model.date_table.end:
        frames[DATE_TABLE] = date_frame(model.date_table.start, model.date_table.end, model.date_table.fiscal_year_start_month)
    return GenContext(model=model, report=report, frames=frames, industries=get_context(store, project).industries)


def get_plan(store: ProjectStore, project: Project, llm: LLMProvider | None, notes: list[str] | None = None) -> MeasurePlan:
    plan, _ = build_plan(gen_context(store, project, llm), _stored(store, project), llm is not None, notes)
    return plan


def save_measure(
    store: ProjectStore, project: Project, llm: LLMProvider | None, data: MeasureInput, original: str | None = None
) -> MeasurePlan:
    """Create a measure, or update one (generated measures keep their name; custom ones may be renamed)."""
    ctx = gen_context(store, project, llm)
    stored = _stored(store, project)
    measures, generated = assemble(ctx, stored)
    names = {m.name.lower(): m for m in measures}
    target = (original or data.name).lower()

    if original and original.lower() in generated:
        stored.overrides[names[original.lower()].name if original.lower() in names else original] = data.model_dump(exclude={"name"})
        stored.removed = [n for n in stored.removed if n.lower() != original.lower()]
    else:
        clash = names.get(data.name.lower())
        if clash is not None and clash.name.lower() != target:
            raise MeasureError(f"A measure named [{data.name}] already exists")
        if data.name.lower() in generated and not original:
            raise MeasureError(f"[{data.name}] is a generated measure; edit it instead of adding a new one")
        source = next((c.get("source", "user") for c in stored.custom if c["name"].lower() == target), "user")
        stored.custom = [c for c in stored.custom if c["name"].lower() != target]
        stored.custom.append({**data.model_dump(), "source": source})
    _save(store, project, stored)
    return get_plan(store, project, llm)


def delete_measure(store: ProjectStore, project: Project, llm: LLMProvider | None, name: str) -> MeasurePlan:
    ctx = gen_context(store, project, llm)
    stored = _stored(store, project)
    _, generated = assemble(ctx, stored)
    if name.lower() in generated:
        stored.removed.append(name)
        stored.overrides.pop(name, None)
    else:
        before = len(stored.custom)
        stored.custom = [c for c in stored.custom if c["name"].lower() != name.lower()]
        if len(stored.custom) == before:
            raise MeasureError(f"Unknown measure [{name}]")
    _save(store, project, stored)
    return get_plan(store, project, llm)


def reset_measure(store: ProjectStore, project: Project, llm: LLMProvider | None, name: str) -> MeasurePlan:
    """'Regenerate': drop the user's edits to a generated measure (and restore it if removed)."""
    stored = _stored(store, project)
    stored.overrides = {k: v for k, v in stored.overrides.items() if k.lower() != name.lower()}
    stored.removed = [n for n in stored.removed if n.lower() != name.lower()]
    _save(store, project, stored)
    return get_plan(store, project, llm)


def suggest(store: ProjectStore, project: Project, llm: LLMProvider | None) -> MeasurePlan:
    """Ask the AI for extra measures; only those that pass the validator are added."""
    if llm is None:
        raise MeasureError("No AI key configured. Add GEMINI_API_KEY to backend/.env to get AI suggestions.")
    ctx = gen_context(store, project, llm)
    stored = _stored(store, project)
    measures, _ = assemble(ctx, stored)
    context = get_context(store, project)
    try:
        proposals = ai_suggest(ctx, measures, context.goals, context.audiences, llm)
    except Exception as exc:
        logger.warning("AI measure suggestions failed: %s", exc)
        return get_plan(store, project, llm, [f"AI suggestions did not finish ({ai_note(exc)})."])

    schema = schema_for(ctx.model)
    names = {m.name.lower(): m.name for m in measures}
    added, rejected = [], []
    for p in proposals:
        if p.name.lower() in names:
            rejected.append(f"[{p.name}] already exists")
            continue
        result = check(p.expression, schema, names)
        if result.issues:
            rejected.append(f"[{p.name}]: {result.issues[0]}")
            continue
        names[p.name.lower()] = p.name
        stored.custom.append({**p.model_dump(), "source": "ai"})
        added.append(p.name)
    _save(store, project, stored)
    notes = [f"AI added {len(added)} measure{'s' if len(added) != 1 else ''}: {', '.join(added)}." if added else "AI did not add any new measures."]
    if rejected:
        notes.append("Rejected by the DAX validator: " + "; ".join(rejected[:5]))
    return get_plan(store, project, llm, notes)


def polish(store: ProjectStore, project: Project, llm: LLMProvider | None, name: str) -> MeasurePlan:
    """AI rewrite + plain-language explanation; applied only when the new DAX passes validation."""
    if llm is None:
        raise MeasureError("No AI key configured. Add GEMINI_API_KEY to backend/.env to polish measures with AI.")
    ctx = gen_context(store, project, llm)
    stored = _stored(store, project)
    measures, _ = assemble(ctx, stored)
    target = next((m for m in measures if m.name.lower() == name.lower()), None)
    if target is None:
        raise MeasureError(f"Unknown measure [{name}]")
    try:
        answer = ai_polish(ctx, measures, target, llm)
    except Exception as exc:
        logger.warning("AI polish failed: %s", exc)
        return get_plan(store, project, llm, [f"Polish did not finish ({ai_note(exc)})."])
    names = {m.name.lower(): m.name for m in measures if m.name.lower() != name.lower()}
    result = check(answer.expression, schema_for(ctx.model), names)
    if result.issues:
        return get_plan(store, project, llm, [f"AI rewrite rejected by the validator ({result.issues[0]}); [{target.name}] was not changed."])
    data = MeasureInput(name=target.name, expression=answer.expression, format=target.format, folder=target.folder,
                        description=answer.description.strip()[:600] or target.description)
    return save_measure(store, project, llm, data, original=target.name)


def measures_tmdl(store: ProjectStore, project: Project, llm: LLMProvider | None) -> str:
    """The _Measures table as a TMDL file ("Export DAX Script")."""
    _, measures = build_plan(gen_context(store, project, llm), _stored(store, project), llm is not None)
    return tmdl.measures_table(measures)


def valid_measures(store: ProjectStore, project: Project, llm: LLMProvider | None):
    """Measures without errors, for the semantic model export."""
    if not store.read_json(project.id, FILE) and not project.files:
        return []
    _, measures = build_plan(gen_context(store, project, llm), _stored(store, project), llm is not None)
    return [m for m in measures if m.status != "error"]

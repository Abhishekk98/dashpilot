"""Glue between stored projects, the dashboard planner and design method B (keeps routes thin)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from typing import Literal

from pydantic import BaseModel

from core import design_option_c as option_c

from core.context_service import get_context
from core.dax import StoredMeasures, build_plan as build_measures
from core.dax_service import FILE as MEASURES_FILE
from core.dax_service import gen_context
from core.design_ai import DesignVariant, generate_variants, plan_signature
from core.insights_service import get_insights
from core.planner import DashboardPlan, VisualInput, ai_note, ai_refine, apply_edit, build_plan, dimension_options, finish
from core.projects import Project, ProjectStore
from llm import LLMProvider

logger = logging.getLogger(__name__)
PLAN_FILE = "plan.json"
DESIGN_FILE = "design.json"


class PlanError(ValueError):
    """User-facing problem (no measures yet, unknown variant)."""


class DesignState(BaseModel):
    variants: list[DesignVariant] = []  # Option B variants (Option C keeps its own in design/option_c.json)
    selected: str | None = None
    selected_method: Literal["A", "B", "C"] | None = None
    selected_label: str | None = None  # e.g. "Option C · Close to Reference" (Design Import shows it)
    plan_signature: str | None = None
    stale: bool = False  # the plan changed after these variants were generated
    selected_stale: bool = False  # the selected design (B or C) no longer matches the plan
    generated_at: datetime | None = None


class PlanResponse(BaseModel):
    plan: DashboardPlan
    design: DesignState
    notes: list[str] = []


def _inputs(store: ProjectStore, project: Project, llm: LLMProvider | None):
    ctx = gen_context(store, project, llm)
    stored = StoredMeasures.model_validate(store.read_json(project.id, MEASURES_FILE))
    mplan, measures = build_measures(ctx, stored, llm is not None)
    if not any(m.status == "passed" for m in measures):
        raise PlanError("No validated measures yet. Finish KPIs & DAX first.")
    return ctx, mplan, measures


def _design(store: ProjectStore, project: Project, plan: DashboardPlan) -> DesignState:
    state = DesignState.model_validate(store.read_json(project.id, DESIGN_FILE))
    state.stale = bool(state.variants) and state.plan_signature != plan_signature(plan)
    if state.selected and state.selected_method == "C":
        state.selected_stale = option_c.get_state(store, project).stale
    elif state.selected and state.selected_method == "A":
        state.selected_stale = False  # a Stitch design is re-matched to the plan by Design Import
    elif state.selected:
        state.selected_stale = state.stale
    return state


def get_plan(store: ProjectStore, project: Project, llm: LLMProvider | None, regenerate: bool = False, ai: bool = False) -> PlanResponse:
    ctx, mplan, measures = _inputs(store, project, llm)
    dims = dimension_options(ctx.model, ctx.report)
    stored = store.read_json(project.id, PLAN_FILE)
    notes: list[str] = []
    if stored.get("plan") and not regenerate:
        plan = finish(DashboardPlan.model_validate(stored["plan"]), measures, dims)  # re-validate against today's measures
    else:
        context = get_context(store, project)
        insights = get_insights(store, project, llm)
        title = f"{context.company_name or project.name} Performance Dashboard"[:80]
        plan = build_plan(title, ctx.model, ctx.report, measures, [c.name for c in mplan.cards], insights)
        if ai and llm is not None:
            try:
                plan, changed = ai_refine(plan, context.industries, context.audiences, context.goals, llm)
                plan = finish(plan, measures, dims)
                notes.append(f"AI refined {changed} title{'s' if changed != 1 else ''} and purposes.")
            except Exception as exc:  # titles are optional polish; rules stay
                logger.warning("Planner AI refinement skipped: %s", exc)
                notes.append(f"AI title polish skipped ({ai_note(exc)}); rule-based titles kept.")
        store.write_json(project.id, PLAN_FILE, {"plan": plan.model_dump(mode="json")})
    return PlanResponse(plan=plan, design=_design(store, project, plan), notes=notes)


def save_plan(store: ProjectStore, project: Project, llm: LLMProvider | None, items: list[VisualInput], title: str | None) -> PlanResponse:
    stored = store.read_json(project.id, PLAN_FILE)
    if not stored.get("plan"):
        get_plan(store, project, llm)  # first save before any plan existed: build one for its title/subtitle
        stored = store.read_json(project.id, PLAN_FILE)
    ctx, _, measures = _inputs(store, project, llm)
    dims = dimension_options(ctx.model, ctx.report)
    plan = apply_edit(DashboardPlan.model_validate(stored["plan"]), items, measures, dims, title)
    store.write_json(project.id, PLAN_FILE, {"plan": plan.model_dump(mode="json")})
    return PlanResponse(plan=plan, design=_design(store, project, plan))


def generate_design(store: ProjectStore, project: Project, llm: LLMProvider | None) -> PlanResponse:
    response = get_plan(store, project, llm)
    plan = response.plan
    if not plan.valid:
        raise PlanError("Fix the dashboard plan first: " + "; ".join(plan.issues[:3]))
    context = get_context(store, project)
    variants = generate_variants(plan, context, llm)
    previous = DesignState.model_validate(store.read_json(project.id, DESIGN_FILE))
    keep = previous.selected_method == "C"  # an Option C selection is not affected by new B variants
    state = DesignState(variants=variants, plan_signature=plan_signature(plan), generated_at=datetime.now(timezone.utc),
                        **({"selected": previous.selected, "selected_method": "C", "selected_label": previous.selected_label} if keep else {}))
    store.write_json(project.id, DESIGN_FILE, state.model_dump(mode="json", exclude={"stale", "selected_stale"}))
    state = _design(store, project, plan)
    ai = sum(v.source == "ai" for v in variants)
    notes = [f"{ai} of {len(variants)} variants designed by AI; {len(variants) - ai} from built-in templates."]
    notes += [f"{v.label}: {v.note}" for v in variants if v.note]
    return PlanResponse(plan=plan, design=state, notes=notes)


def select_variant(store: ProjectStore, project: Project, llm: LLMProvider | None, variant_id: str) -> PlanResponse:
    from core import stitch_import  # noqa: PLC0415 — stitch_import builds on design_import_service, which imports this module

    response = get_plan(store, project, llm)
    state = response.design
    if variant_id == stitch_import.VARIANT_ID:  # Option A: the uploaded Google Stitch export
        upload, html = stitch_import.get_upload(store, project), stitch_import.stitch_html(store, project)
        if upload is None or html is None:
            raise PlanError("Upload the Stitch export first.")
        chosen = DesignVariant(id=variant_id, label=upload.label, html=html, source="template")
        state.selected, state.selected_method, state.selected_label = variant_id, "A", upload.label
    else:
        method = "C" if variant_id.startswith("reference_") else "B"
        pool = option_c.get_state(store, project).variants if method == "C" else state.variants
        chosen = next((v for v in pool if v.id == variant_id), None)
        if chosen is None:
            raise PlanError(f"Unknown design variant {variant_id}; generate the variants first.")
        state.selected, state.selected_method, state.selected_label = variant_id, method, f"Option {method} · {chosen.label}"
    store.write_json(project.id, DESIGN_FILE, state.model_dump(mode="json", exclude={"stale", "selected_stale"}))
    state = _design(store, project, response.plan)
    # The chosen pages are what Design Import (Step 8) reads: selected.html, selected_p2.html, ...
    folder = store.project_dir(project.id) / "design"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("selected_p*.html"):
        old.unlink()
    pages = stitch_import.stitch_pages(store, project) if variant_id == stitch_import.VARIANT_ID else (chosen.pages or [chosen.html])
    for page, html in enumerate(pages, 1):
        (folder / ("selected.html" if page == 1 else f"selected_p{page}.html")).write_text(html, encoding="utf-8")
    return PlanResponse(plan=response.plan, design=state)

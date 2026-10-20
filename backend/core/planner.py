"""Dashboard plan: one 1280x720 page with slicers, KPI cards, charts and a Key Insights box. (Spec Module 8)

Chart choice and layout are rule-based and deterministic; the LLM may only polish titles and
purposes (never numbers, types or fields). A validator keeps the plan to Power BI native visuals,
Passed measures, real model fields and a non-overlapping layout.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from core.dax import RATIOS, Measure
from core.insights import Insight, InsightPlan
from core.modelling import DATE_TABLE, ModelPlan
from core.profiling import QualityReport
from llm import LLMError, LLMProvider

logger = logging.getLogger(__name__)
PROMPTS = Path(__file__).resolve().parent.parent / "llm" / "prompts"

CANVAS_W, CANVAS_H = 1280, 720
MARGIN, GAP = 24, 16

VisualType = Literal[
    "card", "line", "area", "clustered_bar", "clustered_column", "stacked_bar", "stacked_column", "donut",
    "map", "filled_map", "table", "matrix", "slicer", "gauge", "scatter", "waterfall", "funnel", "text_box",
]
CHART_TYPES = ["line", "area", "clustered_bar", "clustered_column", "stacked_bar", "stacked_column", "donut", "map",
               "filled_map", "table", "matrix", "gauge", "scatter", "waterfall", "funnel"]
Role = Literal["slicer", "kpi", "chart", "insights"]
MAX_KPIS, MAX_CHARTS, MIN_CHARTS = 5, 6, 1


# --- models -------------------------------------------------------------------------

class Box(BaseModel):
    x: int
    y: int
    w: int
    h: int


class PlanVisual(BaseModel):
    id: str
    role: Role
    type: VisualType
    title: str = Field(max_length=80)
    measures: list[str] = []
    dimension: str | None = None  # "table[column]"
    sort: Literal["desc", "asc", "date"] | None = None
    purpose: str = Field(default="", max_length=300)
    question_id: str | None = None
    text: list[str] = []  # Key Insights lines (text_box only)
    box: Box = Box(x=0, y=0, w=0, h=0)


class DimensionOption(BaseModel):
    field: str  # "table[column]"
    label: str
    kind: Literal["date", "category", "geo"]
    cardinality: int


class DashboardPlan(BaseModel):
    title: str
    subtitle: str = ""
    width: int = CANVAS_W
    height: int = CANVAS_H
    visuals: list[PlanVisual]
    source: Literal["rules", "ai"] = "rules"
    edited: bool = False
    issues: list[str] = []
    valid: bool = True
    # What the editor may choose from.
    measures: list[str] = []
    dimensions: list[DimensionOption] = []
    chart_types: list[str] = CHART_TYPES


class VisualInput(BaseModel):
    """What the user may change per visual in the editor (layout is always recomputed)."""

    id: str | None = None
    role: Role
    type: VisualType
    title: str = Field(max_length=80)
    measures: list[str] = []
    dimension: str | None = None
    sort: Literal["desc", "asc", "date"] | None = None
    purpose: str = Field(default="", max_length=300)
    question_id: str | None = None
    text: list[str] = []


# --- inputs ---------------------------------------------------------------------------

def dimension_options(model: ModelPlan, report: QualityReport) -> list[DimensionOption]:
    """Slicer/axis candidates: date table, categories and places on the fact or related dims."""
    profiles = {(t.name, c.name): c for t in report.tables for c in t.column_profiles}
    facts = [t for t in model.tables if t.included and t.kind == "fact"]
    fact = max(facts, key=lambda t: t.rows) if facts else None
    related = {r.to_table for r in model.relationships if fact and r.valid and r.active and r.from_table == fact.name}
    out = []
    if model.date_table.enabled and fact and DATE_TABLE in related:
        out += [DimensionOption(field=f"{DATE_TABLE}[{c}]", label=c, kind="date", cardinality=n)
                for c, n in (("Date", 365), ("Year Month", 24), ("Year", 5), ("Quarter", 4), ("Month Name", 12), ("Day of Week", 7))]
    for t in model.tables:
        if not t.included or (fact and t.name != fact.name and t.name not in related):
            continue
        for c in t.columns:
            prof = profiles.get((t.name, c.name))
            if prof and prof.role in ("categorical_slicer", "geo_dimension") and c.data_type == "string":
                out.append(DimensionOption(
                    field=f"{t.name}[{c.name}]", label=c.name.replace("_", " "),
                    kind="geo" if prof.role == "geo_dimension" else "category", cardinality=prof.distinct_count,
                ))
    return out


def _passed(measures: list[Measure]) -> list[Measure]:
    return [m for m in measures if m.status == "passed"]


# --- rules ----------------------------------------------------------------------------

_PURPOSE = {
    "trend": "How is {m} changing over time?",
    "top": "Which {d} contributes the most {m}?",
    "share": "How is {m} split across {d}?",
    "rate": "Where is {m} unusually high or low?",
    "detail": "What are the exact figures for each {d}?",
    "weekday": "Which days of the week carry the most {m}?",
}


def _question_for(kind: str, field: str | None, insights: InsightPlan | None, used: set[str]) -> tuple[str | None, str]:
    """Unused business question about this visual's dimension -> (question id, purpose text); ("", "") if none fits."""
    if insights is None:
        return None, ""
    wanted = {"trend": ("trend", "comparison"), "top": ("top_performer", "contribution"), "share": ("contribution", "top_performer"),
              "rate": ("rate_alert",), "detail": ("top_performer",), "weekday": ("top_performer",)}[kind]
    # Trends are about time, so any trend insight fits; everything else must be about the same column.
    ids = {i.id for i in insights.insights if i.type in wanted and (kind == "trend" or i.dimension == field)}
    for q in insights.questions:
        if q.id not in used and q.insight_ids and q.insight_ids[0] in ids:  # judged by the question's main insight
            used.add(q.id)
            return q.id, q.text
    return None, ""


def _pick_charts(measures: list[Measure], dims: list[DimensionOption], insights: InsightPlan | None) -> list[PlanVisual]:
    passed = _passed(measures)
    amount = next((m.name for m in passed if m.folder.startswith("01") and m.format == "currency" and m.expression.startswith("SUM(")), None)
    amount = amount or next((m.name for m in passed if m.folder.startswith("01") and m.expression.startswith("SUM(")), None)
    count = next((m.name for m in passed if m.folder.startswith("01") and m.format == "whole"), None)
    primary = amount or count or (passed[0].name if passed else None)
    if primary is None:
        return []
    rates = [m.name for m in passed if m.folder == RATIOS and m.format == "percent" and "% of Total" not in m.name]
    dates = {d.label: d for d in dims if d.kind == "date"}
    cats = sorted([d for d in dims if d.kind == "category"], key=lambda d: d.cardinality)
    geos = [d for d in dims if d.kind == "geo"]
    # Dimensions the insights found interesting come first.
    hot = [i.dimension for i in (insights.insights if insights else []) if i.dimension]
    ranked = sorted(cats + geos, key=lambda d: (d.field not in hot, hot.index(d.field) if d.field in hot else 0))

    charts: list[PlanVisual] = []
    used: set[str] = set()

    def add(kind: str, vtype: str, title: str, ms: list[str], dim: DimensionOption | None, sort: str | None) -> None:
        if len(charts) >= MAX_CHARTS or any(c.title == title or (c.type == vtype and c.measures == ms and c.dimension == (dim.field if dim else None)) for c in charts):
            return
        qid, purpose = _question_for(kind, dim.field if dim else None, insights, used)
        fallback = _PURPOSE[kind].format(m=ms[0], d=dim.label if dim else "category")
        charts.append(PlanVisual(
            id="", role="chart", type=vtype, title=title, measures=ms, dimension=dim.field if dim else None, sort=sort,
            purpose=purpose or fallback, question_id=qid,
        ))

    if "Year Month" in dates:
        add("trend", "area" if count and primary == amount else "line", f"{primary} Trend", [primary], dates["Year Month"], "date")
    if ranked:
        top = next((d for d in ranked if d.kind == "category"), ranked[0])  # geo columns get a map below
        add("top", "clustered_bar", f"{primary} by {top.label.title()}", [primary], top, "desc")
    small = next((d for d in cats if 2 <= d.cardinality <= 6 and (not ranked or d.field != ranked[0].field)), None)
    if small:
        add("share", "donut", f"{primary} Share by {small.label.title()}", [primary], small, "desc")
    geo = next((d for d in geos if re.search(r"city|state|country|region|district|province", d.label, re.I)), None)
    if geo:
        # A bar, not a map: Power BI's map visuals (Azure Maps) need a tenant switch many users cannot turn on.
        # Maps stay available in the plan editor.
        add("top", "clustered_bar", f"{primary} by {geo.label.title()}", [primary], geo, "desc")
    if rates:
        target = next((d for d in ranked if not re.search(re.escape(d.label.split()[0]), rates[0], re.I)), ranked[0] if ranked else None)
        if target:
            add("rate", "clustered_column", f"{rates[0]} by {target.label.title()}", [rates[0]], target, "desc")
    if ranked:
        detail = ranked[1] if len(ranked) > 1 else ranked[0]
        extra = [m for m in (count, rates[0] if rates else None) if m and m != primary][:2]
        add("detail", "table", f"{detail.label.title()} Details", [primary, *extra], detail, "desc")
    if "Day of Week" in dates and len(charts) < 4:
        add("weekday", "clustered_column", f"{primary} by Day of Week", [primary], dates["Day of Week"], None)
    if len(charts) < 4 and count and count != primary and ranked:
        add("top", "clustered_bar", f"{count} by {ranked[0].label.title()}", [count], ranked[0], "desc")
    if not charts:  # no date or category to slice by: a gauge is the one chart that needs no axis
        charts.append(PlanVisual(id="", role="chart", type="gauge", title=f"{primary} Gauge", measures=[primary],
                                 purpose="No date or category column links to the data yet; add one in Data Model to unlock comparisons."))
    return charts


def _kpis(measures: list[Measure], cards: list[str]) -> list[PlanVisual]:
    names = [n for n in cards if any(m.name == n for m in _passed(measures))]
    for m in _passed(measures):
        if len(names) >= MAX_KPIS:
            break
        if m.name not in names and m.folder.startswith(("01", "02")):
            names.append(m.name)
    return [PlanVisual(id="", role="kpi", type="card", title=n, measures=[n], purpose=f"Headline value of {n}.") for n in names[:MAX_KPIS]]


def _slicers(dims: list[DimensionOption]) -> list[PlanVisual]:
    out = []
    date = next((d for d in dims if d.kind == "date" and d.label == "Date"), None)
    if date:
        out.append(PlanVisual(id="", role="slicer", type="slicer", title="Date Range", dimension=date.field, purpose="Filter every visual to a date range."))
    for d in sorted([d for d in dims if d.kind in ("category", "geo") and d.cardinality <= 60], key=lambda d: d.cardinality)[:2]:
        out.append(PlanVisual(id="", role="slicer", type="slicer", title=d.label.title(), dimension=d.field, purpose=f"Filter by {d.label}."))
    return out


def _insights_box(insights: InsightPlan | None) -> PlanVisual:
    chosen: list[Insight] = []
    if insights:
        chosen = [i for i in insights.insights if i.pinned][:3] or insights.insights[:3]
    return PlanVisual(id="", role="insights", type="text_box", title="Key Insights", text=[i.headline for i in chosen],
                      purpose="Plain-language findings pinned in AI Insights.")


# --- layout ---------------------------------------------------------------------------

def layout(visuals: list[PlanVisual]) -> list[PlanVisual]:
    """Deterministic 1280x720 grid: top bar with slicers, KPI row, two rows of charts + insights."""
    slicers = [v for v in visuals if v.role == "slicer"]
    kpis = [v for v in visuals if v.role == "kpi"]
    charts = [v for v in visuals if v.role == "chart"]
    boxes = [v for v in visuals if v.role == "insights"]
    inner = CANVAS_W - 2 * MARGIN

    # Top bar: title on the left (drawn by the design), slicers right-aligned.
    sw, sh = 176, 40
    for i, v in enumerate(reversed(slicers)):
        v.box = Box(x=CANVAS_W - MARGIN - (i + 1) * sw - i * GAP // 2, y=16, w=sw, h=sh)

    top = 72
    if kpis:
        kw = (inner - GAP * (len(kpis) - 1)) // len(kpis)
        for i, v in enumerate(kpis):
            v.box = Box(x=MARGIN + i * (kw + GAP), y=top, w=kw, h=104)
        top += 104 + GAP

    tiles = charts + boxes
    if tiles:
        rows = 1 if len(tiles) <= 3 else 2
        per_row = [len(tiles) - len(tiles) // 2, len(tiles) // 2] if rows == 2 else [len(tiles)]
        height = CANVAS_H - MARGIN - top
        rh = (height - GAP * (rows - 1)) // rows
        k = 0
        for r, n in enumerate(per_row):
            tw = (inner - GAP * (n - 1)) // n
            for c in range(n):
                tiles[k].box = Box(x=MARGIN + c * (tw + GAP), y=top + r * (rh + GAP), w=tw, h=rh)
                k += 1
    order = slicers + kpis + charts + boxes
    for i, v in enumerate(order):
        prefix = {"slicer": "slicer", "kpi": "kpi", "chart": "visual", "insights": "insights"}[v.role]
        v.id = v.id or f"{prefix}_{i + 1}"
    return order


# --- validation -------------------------------------------------------------------------

def _overlap(a: Box, b: Box) -> bool:
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


def validate(plan: DashboardPlan, measures: list[Measure], dims: list[DimensionOption]) -> list[str]:
    passed = {m.name for m in _passed(measures)}
    fields = {d.field for d in dims}
    issues = []
    roles = [v.role for v in plan.visuals]
    if roles.count("kpi") > MAX_KPIS:
        issues.append(f"At most {MAX_KPIS} KPI cards fit the top row.")
    if roles.count("chart") > MAX_CHARTS:
        issues.append(f"At most {MAX_CHARTS} charts fit one page.")
    if roles.count("chart") < MIN_CHARTS:
        issues.append("Add at least one chart.")
    seen_ids, seen_titles, seen_shapes = set(), set(), set()
    for v in plan.visuals:
        label = f"'{v.title}'"
        if v.id in seen_ids:
            issues.append(f"Duplicate visual id {v.id}.")
        seen_ids.add(v.id)
        if v.title.strip().lower() in seen_titles:
            issues.append(f"Two visuals are titled {label}; titles must be unique (they are matched in Design Import).")
        seen_titles.add(v.title.strip().lower())
        if not v.title.strip():
            issues.append("Every visual needs a title.")
        shape = (v.type, tuple(v.measures), v.dimension)
        if v.role == "chart" and shape in seen_shapes:
            issues.append(f"{label} repeats another chart (same type, measures and field).")
        seen_shapes.add(shape)
        if v.role == "kpi" and (v.type != "card" or len(v.measures) != 1):
            issues.append(f"KPI {label} must be a card with exactly one measure.")
        if v.role == "slicer" and (v.type != "slicer" or v.dimension is None):
            issues.append(f"Slicer {label} needs a field.")
        if v.role == "chart" and v.type not in CHART_TYPES:
            issues.append(f"{label}: '{v.type}' is not a Power BI chart type here.")
        if v.role == "chart" and not v.measures:
            issues.append(f"{label} needs at least one measure.")
        if v.role == "chart" and v.type not in ("card", "gauge") and v.dimension is None and v.type != "scatter":
            issues.append(f"{label} needs a field for its axis or category.")
        for m in v.measures:
            if m not in passed:
                issues.append(f"{label} uses [{m}], which is missing or did not pass validation in KPIs & DAX.")
        if v.dimension and v.dimension not in fields:
            issues.append(f"{label} uses {v.dimension}, which is not a slicer/axis field in the model.")
        if v.type == "donut" and v.dimension:
            card = next((d.cardinality for d in dims if d.field == v.dimension), 0)
            if card > 8:
                issues.append(f"{label}: donuts need few categories ({card} here); use a bar chart.")
        b = v.box
        if b.x < 0 or b.y < 0 or b.x + b.w > plan.width or b.y + b.h > plan.height or b.w <= 0 or b.h <= 0:
            issues.append(f"{label} is outside the 1280x720 canvas.")
    for i, a in enumerate(plan.visuals):
        for b in plan.visuals[i + 1:]:
            if _overlap(a.box, b.box):
                issues.append(f"'{a.title}' overlaps '{b.title}'.")
    return list(dict.fromkeys(issues))


# --- build ----------------------------------------------------------------------------

def build_plan(title: str, model: ModelPlan, report: QualityReport, measures: list[Measure], cards: list[str],
               insights: InsightPlan | None) -> DashboardPlan:
    dims = dimension_options(model, report)
    visuals = layout(_slicers(dims) + _kpis(measures, cards) + _pick_charts(measures, dims, insights) + [_insights_box(insights)])
    plan = DashboardPlan(title=title, subtitle="Executive overview", visuals=visuals)
    return finish(plan, measures, dims)


def finish(plan: DashboardPlan, measures: list[Measure], dims: list[DimensionOption]) -> DashboardPlan:
    plan.measures = [m.name for m in _passed(measures)]
    plan.dimensions = dims
    plan.issues = validate(plan, measures, dims)
    plan.valid = not plan.issues
    return plan


def apply_edit(plan: DashboardPlan, items: list[VisualInput], measures: list[Measure], dims: list[DimensionOption],
               title: str | None = None) -> DashboardPlan:
    """User edits (types, fields, order, add/remove) -> re-laid-out, re-validated plan."""
    visuals = [PlanVisual(**i.model_dump(exclude={"id"}), id="") for i in items]
    new = DashboardPlan(title=(title or plan.title)[:80], subtitle=plan.subtitle, visuals=layout(visuals), source=plan.source, edited=True)
    return finish(new, measures, dims)


# --- AI polish ------------------------------------------------------------------------

class _AITitle(BaseModel):
    id: str
    title: str
    purpose: str


class _AITitles(BaseModel):
    dashboard_title: str
    visuals: list[_AITitle]


_DIGITS = re.compile(r"\d")


def ai_refine(plan: DashboardPlan, industries: list[str], audiences: list[str], goals: str, llm: LLMProvider) -> tuple[DashboardPlan, int]:
    """Let the LLM rewrite titles/purposes only. Numbers, duplicate or over-long titles are rejected."""
    payload = [{"id": v.id, "role": v.role, "type": v.type, "title": v.title, "measures": v.measures, "field": v.dimension,
                "purpose": v.purpose} for v in plan.visuals if v.role in ("chart", "kpi")]
    prompt = (
        (PROMPTS / "planner_titles.md").read_text(encoding="utf-8")
        .replace("{industries}", ", ".join(industries) or "not set")
        .replace("{audiences}", ", ".join(audiences) or "Executive Leadership")
        .replace("{goals}", goals or "not given")
        .replace("{title}", plan.title)
        .replace("{visuals}", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    )
    answer = llm.generate_text(prompt, json_schema=_AITitles)
    by_id = {v.id: v for v in plan.visuals}
    taken = {v.title.lower() for v in plan.visuals if v.role in ("slicer", "insights")}
    changed = 0
    for t in answer.visuals:
        v = by_id.get(t.id)
        title = t.title.strip()
        if v is None or v.role not in ("chart", "kpi") or not title or len(title) > 60 or _DIGITS.search(title) or title.lower() in taken:
            continue
        if v.role == "kpi" and title != v.title:
            continue  # card titles must stay the measure names so values are recognisable
        v.title = title
        if t.purpose.strip() and not _DIGITS.search(t.purpose):
            v.purpose = t.purpose.strip()[:300]
        taken.add(title.lower())
        changed += 1
    dash = answer.dashboard_title.strip()
    if dash and len(dash) <= 80 and not _DIGITS.search(dash):
        plan.title = dash
    plan.source = "ai"
    return plan, changed


def ai_note(exc: Exception) -> str:
    text = str(exc) if isinstance(exc, LLMError) else f"AI request failed ({type(exc).__name__})"
    return text.split(" (", 1)[0][:140]

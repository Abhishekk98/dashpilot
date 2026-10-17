"""Business questions + insights + narratives. (Spec Module 7)

Core rule: every number is computed from the cleaned data with the model and the validated
measures (core/dax_eval.py). The LLM only *phrases* text from those facts; a grounding validator
rejects any AI sentence containing a number that is not one of the computed facts, and the
template text is used instead. Custom questions are mapped by the LLM (or by keyword rules) to a
structured query spec that is validated against the model and executed here; no generated code
ever runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from core.dax import RATIOS, TIME, GenContext, Measure, format_value
from core.dax_eval import Ctx, Data, Evaluator, Filter, Link
from core.modelling import DATE_TABLE
from llm import LLMError, LLMProvider

logger = logging.getLogger(__name__)
PROMPTS = Path(__file__).resolve().parent.parent / "llm" / "prompts"

InsightType = Literal["trend", "comparison", "anomaly", "top_performer", "contribution", "rate_alert", "answer"]
Theme = Literal["Growth", "Performance", "Concentration", "Risk", "Efficiency"]
THEMES: list[str] = ["Growth", "Performance", "Concentration", "Risk", "Efficiency"]
TYPE_THEME: dict[str, str] = {
    "trend": "Growth", "comparison": "Growth", "anomaly": "Risk", "rate_alert": "Risk",
    "top_performer": "Performance", "contribution": "Concentration", "answer": "Efficiency",
}
Period = Literal["all", "latest_month", "latest_quarter", "latest_year", "previous_year"]
MAX_MEMBERS = 30
# Members created by cleaning (blank -> 'Unknown') are not business segments to rank or alert on.
PLACEHOLDER_MEMBERS = {"unknown", "(blank)", "blank", "n/a", "other", "others"}
GENERIC_WORDS = {"name", "type", "code", "key", "value", "the", "and", "for"}


# --- models -------------------------------------------------------------------------

class Series(BaseModel):
    kind: Literal["line", "bar", "share"] = "line"
    labels: list[str] = []
    values: list[float] = []
    texts: list[str] = []  # each value formatted like its measure (for chart labels)
    highlight: int | None = None  # index of the point/bar the insight is about


class Insight(BaseModel):
    id: str
    type: InsightType
    theme: str
    title: str  # short label, e.g. "Top merchant_name"
    headline: str
    body: str
    action: str
    value_text: str
    delta_text: str | None = None
    delta: float | None = None
    series: Series = Series()
    confidence: float = Field(ge=0, le=1)
    measure: str
    dimension: str | None = None
    sources: list[str] = []
    facts: dict[str, float] = {}  # every number the narrative may mention
    names: list[str] = []  # member / period names the text mentions (may contain digits)
    narrative_source: Literal["template", "ai"] = "template"
    pinned: bool = False
    question_ids: list[str] = []


class Question(BaseModel):
    id: str
    text: str
    theme: str
    audience: str
    insight_ids: list[str] = []
    answer: str = ""
    source: Literal["template", "ai"] = "template"


class QuerySpec(BaseModel):
    measure: str
    dimension_table: str | None = None
    dimension_column: str | None = None
    filter_table: str | None = None
    filter_column: str | None = None
    filter_value: str | None = None
    period: Period = "all"
    top_n: int = Field(default=5, ge=1, le=20)


class InsightPlan(BaseModel):
    insights: list[Insight]
    questions: list[Question]
    north_star: str | None
    rows_scanned: int
    dimensions: list[str]
    confidence: float
    ai_status: Literal["off", "available", "done", "failed"] = "off"
    ai_note: str | None = None
    pinned: list[str] = []
    notes: list[str] = []


class AskResult(BaseModel):
    question: str
    spec: QuerySpec
    insight: Insight
    source: Literal["rules", "ai"]


# --- context ------------------------------------------------------------------------

@dataclass
class Dim:
    table: str
    column: str

    @property
    def label(self) -> str:
        return self.column.replace("_", " ")


@dataclass
class Engine:
    ctx: GenContext
    measures: list[Measure]
    ev: Evaluator = field(init=False)
    by_name: dict[str, Measure] = field(init=False)

    def __post_init__(self) -> None:
        ok = [m for m in self.measures if m.status != "error"]
        links = [Link(r.from_table, r.from_column, r.to_table, r.to_column) for r in self.ctx.model.relationships if r.valid and r.active]
        self.ev = Evaluator(Data(
            frames=self.ctx.frames, links=links,
            date_table=DATE_TABLE if self.ctx.model.date_table.enabled and DATE_TABLE in self.ctx.frames else None,
            measures={m.name.lower(): m.expression for m in ok},
        ))
        self.by_name = {m.name.lower(): m for m in ok}

    # -- measure values ---------------------------------------------------------------
    def value(self, measure: str, filters: tuple[Filter, ...] = (), window=None) -> float | None:
        try:
            v = self.ev.measure(measure, Ctx(filters=filters, window=window))
        except Exception:
            return None
        if v is None or isinstance(v, (str, pd.Timestamp, bool)):
            return None
        v = float(v)
        return v if math.isfinite(v) else None

    def fmt(self, measure: str, value: float | None) -> str:
        m = self.by_name.get(measure.lower())
        symbol = m.format_string.split('"')[1] if m and m.format_string.startswith('"') else None
        return format_value(value, m.format if m else "decimal", symbol) or "(Blank)"

    def is_percent(self, measure: str) -> bool:
        m = self.by_name.get(measure.lower())
        return bool(m and m.format == "percent")

    # -- model facts ------------------------------------------------------------------
    def has_time(self) -> bool:
        return self.ev.d.date_table is not None and self.ctx.has_time()

    def max_date(self) -> pd.Timestamp | None:
        try:
            return self.ev.max_date(Ctx()) if self.has_time() else None
        except Exception:
            return None

    def dimensions(self) -> list[Dim]:
        fact = self.ctx.fact
        if fact is None:
            return []
        related = {r.to_table for r in self.ctx.model.relationships if r.valid and r.active and r.from_table == fact.name}
        dims = []
        for t in self.ctx.included:
            if t.name != fact.name and t.name not in related:
                continue
            for c in t.columns:
                prof = self.ctx.profiles.get((t.name, c.name))
                if prof and prof.role in ("categorical_slicer", "geo_dimension") and c.data_type == "string" and 2 <= prof.distinct_count <= 200:
                    dims.append(Dim(t.name, c.name))
        if self.has_time():
            dims.append(Dim(DATE_TABLE, "Day of Week"))
        return dims[:5]

    def members(self, dim: Dim) -> list[str]:
        if dim.table == DATE_TABLE:
            return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        values = self.ctx.frames[dim.table][dim.column].dropna().astype(str)
        return list(values.value_counts().head(MAX_MEMBERS).index)

    def slices_itself(self, measure: str, dim: Dim) -> bool:
        """True when the measure already filters this column (e.g. a status rate sliced by status):
        CALCULATE would override the slice, so per-member values are meaningless."""
        m = self.by_name.get(measure.lower())
        return bool(m and f"[{dim.column}]".lower() in m.expression.lower() and "CALCULATE" in m.expression.upper())

    def by_member(self, measure: str, dim: Dim, window=None, real_only: bool = False) -> list[tuple[str, float]]:
        out = []
        for member in self.members(dim):
            if real_only and member.strip().lower() in PLACEHOLDER_MEMBERS:
                continue
            v = self.value(measure, (Filter(dim.table, dim.column, "=", (member,)),), window)
            if v is not None:
                out.append((member, v))
        return out

    def support(self, dim: Dim, member: str) -> int:
        fact = self.ctx.fact
        if fact is None:
            return 0
        try:
            return len(self.ev.rows(fact.name, Ctx(filters=(Filter(dim.table, dim.column, "=", (member,)),))))
        except Exception:
            return 0

    def monthly(self, measure: str, months: int = 12) -> tuple[list[pd.Timestamp], list[float]]:
        end = self.max_date()
        if end is None:
            return [], []
        starts, values = [], []
        for i in range(months - 1, -1, -1):
            month_end = (end - pd.DateOffset(months=i)) + pd.offsets.MonthEnd(0)
            month_start = month_end.replace(day=1)
            v = self.value(measure, window=(month_start, min(month_end, end)))
            starts.append(month_start)
            values.append(v if v is not None else 0.0)
        # Drop leading empty months (data that starts recently).
        while len(values) > 1 and values[0] == 0.0:
            starts.pop(0)
            values.pop(0)
        return starts, values


# --- helpers -------------------------------------------------------------------------

def _id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.1%}"


def share_text(x: float) -> str:
    return f"{x:.1%}"


def _round_facts(facts: dict[str, float | None]) -> dict[str, float]:
    return {k: float(v) for k, v in facts.items() if v is not None and math.isfinite(float(v))}


def _primary(engine: Engine) -> tuple[str | None, str | None, list[str]]:
    """(amount measure, count measure, rate measures) from the validated measure list."""
    ok = [m for m in engine.measures if m.status == "passed" and m.value is not None]
    amount = next((m.name for m in ok if m.folder.startswith("01") and m.format == "currency" and m.expression.startswith("SUM(")), None)
    amount = amount or next((m.name for m in ok if m.folder.startswith("01") and m.expression.startswith("SUM(")), None)
    count = next((m.name for m in ok if m.folder.startswith("01") and m.format == "whole" and ("COUNTROWS" in m.expression or "DISTINCTCOUNT" in m.expression)), None)
    rates = [m.name for m in ok if m.folder == RATIOS and m.format == "percent" and "% of Total" not in m.name][:4]
    return amount or count, count, rates


# --- insight builders ------------------------------------------------------------------

def _trend(engine: Engine, measure: str) -> list[Insight]:
    starts, values = engine.monthly(measure)
    if len(values) < 3:
        return []
    labels = [f"{s:%b %Y}" for s in starts]
    last, prev = values[-1], values[-2]
    delta = (last - prev) / abs(prev) if prev else None
    k = min(3, len(values) // 2)
    recent, earlier = sum(values[-k:]), sum(values[-2 * k:-k])
    momentum = (recent - earlier) / abs(earlier) if earlier else None
    direction = "up" if (momentum or 0) > 0.02 else "down" if (momentum or 0) < -0.02 else "flat"
    facts = _round_facts({"latest": last, "previous": prev, "change": delta, "momentum": momentum, "months": len(values), "window": k})
    headline = (
        f"{measure} was {engine.fmt(measure, last)} in {labels[-1]}, {pct(delta)} versus {labels[-2]}."
        if delta is not None else f"{measure} was {engine.fmt(measure, last)} in {labels[-1]}."
    )
    if momentum is None:
        body = f"The monthly series covers {len(values)} months."
    elif direction == "flat":
        body = f"Over the last {k} months {measure.lower()} is flat ({pct(momentum)}) compared with the {k} months before."
    else:
        body = f"Over the last {k} months {measure.lower()} is {direction} {abs(momentum):.1%} compared with the {k} months before."
    action = (
        "Find what changed in the latest month (mix, price, volume) before it shows up in the quarter."
        if direction != "flat" else "Momentum is stable; focus on the segments in the performer insights."
    )
    return [Insight(
        id=_id("trend", measure), type="trend", theme="Growth", title=f"{measure} trend", headline=headline, body=body, action=action,
        value_text=engine.fmt(measure, last), delta=delta, delta_text=pct(delta) if delta is not None else None,
        series=Series(kind="line", labels=labels, values=values, highlight=len(values) - 1),
        confidence=round(min(0.97, 0.6 + 0.03 * len(values)), 2), measure=measure, sources=[engine.ctx.fact.name, DATE_TABLE],
        facts=facts,
    )]


def _comparisons(engine: Engine, measure: str) -> list[Insight]:
    end = engine.max_date()
    if end is None:
        return []
    periods = []
    # Latest full month vs the month before (a partial latest month would compare unfairly).
    month_end = end.replace(day=1) - pd.Timedelta(days=1) if end != end + pd.offsets.MonthEnd(0) else end
    m_start = month_end.replace(day=1)
    p_end = m_start - pd.Timedelta(days=1)
    periods.append(("month", f"{m_start:%b %Y}", f"{p_end:%b %Y}", (m_start, month_end), (p_end.replace(day=1), p_end)))
    q_start = pd.Timestamp(end.year, 3 * ((end.month - 1) // 3) + 1, 1)
    pq_start = q_start - pd.DateOffset(months=3)
    periods.append(("quarter", f"Q{(q_start.month - 1) // 3 + 1} {q_start.year} to date", f"same days of Q{(pq_start.month - 1) // 3 + 1} {pq_start.year}",
                    (q_start, end), (pq_start, pq_start + (end - q_start))))
    y_start = pd.Timestamp(end.year, 1, 1)
    periods.append(("year", f"{end.year} to date", f"same period {end.year - 1}", (y_start, end), (y_start - pd.DateOffset(years=1), end - pd.DateOffset(years=1))))
    out = []
    for kind, cur_label, prev_label, cur, prev in periods:
        a, b = engine.value(measure, window=cur), engine.value(measure, window=prev)
        if a is None or not b:
            continue
        delta = (a - b) / abs(b)
        facts = _round_facts({"current": a, "previous": b, "change": delta, "year": end.year, "previous_year": end.year - 1})
        out.append(Insight(
            id=_id("comparison", measure, kind), type="comparison", theme="Growth", title=f"{kind.capitalize()} over {kind}",
            headline=f"{measure} for {cur_label} is {engine.fmt(measure, a)}, {pct(delta)} versus {prev_label}.",
            body=f"The comparison uses the marked date table: {engine.fmt(measure, a)} now against {engine.fmt(measure, b)} before.",
            action="Double down on what drove the increase." if delta > 0 else "Investigate the drop by checking the top and bottom performers below.",
            value_text=engine.fmt(measure, a), delta=delta, delta_text=pct(delta),
            series=Series(kind="bar", labels=[prev_label, cur_label], values=[b, a], highlight=1),
            confidence=0.9, measure=measure, sources=[engine.ctx.fact.name, DATE_TABLE], facts=facts,
        ))
    return out


def _anomalies(engine: Engine, measure: str) -> list[Insight]:
    starts, values = engine.monthly(measure, 18)
    if len(values) < 6:
        return []
    arr = np.array(values, dtype=float)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median))) or float(np.std(arr)) or 1.0
    z = (arr - median) / (1.4826 * mad)
    i = int(np.argmax(np.abs(z)))
    if abs(z[i]) < 2.5:
        return []
    kind = "spike" if z[i] > 0 else "drop"
    deviation = (arr[i] - median) / abs(median) if median else None
    label = f"{starts[i]:%b %Y}"
    facts = _round_facts({"value": arr[i], "typical": median, "deviation": deviation, "z": float(abs(z[i]))})
    return [Insight(
        id=_id("anomaly", measure, label), type="anomaly", theme="Risk", title=f"Unusual {kind}",
        headline=f"{measure} had an unusual {kind} in {label}: {engine.fmt(measure, arr[i])} against a typical month of {engine.fmt(measure, median)}.",
        body=f"That is {pct(deviation)} away from the median month, far outside normal month-to-month variation.",
        action=f"Check {label} for one-off events, data loads or promotions before using it as a baseline.",
        value_text=engine.fmt(measure, arr[i]), delta=deviation, delta_text=pct(deviation),
        series=Series(kind="line", labels=[f"{s:%b %Y}" for s in starts], values=values, highlight=i),
        confidence=round(min(0.98, 0.7 + 0.05 * abs(z[i])), 2), measure=measure, sources=[engine.ctx.fact.name, DATE_TABLE], facts=facts,
    )]


def _performers(engine: Engine, measure: str, dim: Dim, total: float | None) -> list[Insight]:
    if engine.slices_itself(measure, dim):
        return []
    values = sorted(engine.by_member(measure, dim, real_only=True), key=lambda x: -x[1])
    if len(values) < 2 or total in (None, 0):
        return []
    top, bottom = values[0], values[-1]
    # A share only makes sense for additive, non-negative measures whose members sum to the total.
    additive = (not engine.is_percent(measure) and total > 0 and all(v >= 0 for _, v in values)
                and sum(v for _, v in values) <= total * 1.02)
    share = top[1] / total if additive else None
    n = engine.support(dim, top[0])
    facts = _round_facts({"top": top[1], "bottom": bottom[1], "share": share, "total": total, "members": len(values), "rows": n})
    labels = [m for m, _ in values[:8]]
    headline = (
        f"{top[0]} is the top {dim.label} with {engine.fmt(measure, top[1])} of {measure}, {share_text(share)} of the total."
        if share is not None else f"{top[0]} is the top {dim.label} by {measure} at {engine.fmt(measure, top[1])}."
    )
    return [Insight(
        id=_id("top", measure, dim.table, dim.column), type="top_performer", theme="Performance", title=f"Top {dim.label}",
        headline=headline,
        body=f"Across {len(values)} {dim.label} values, the lowest is {bottom[0]} at {engine.fmt(measure, bottom[1])}.",
        action=f"Use {top[0]} as the benchmark and review what {bottom[0]} does differently.",
        value_text=engine.fmt(measure, top[1]), delta=share, delta_text=f"{share_text(share)} share" if share is not None else None,
        series=Series(kind="bar", labels=labels, values=[v for _, v in values[:8]], highlight=0),
        confidence=round(min(0.97, 0.6 + 0.4 * min(1.0, n / 200)), 2), measure=measure, dimension=f"{dim.table}[{dim.column}]",
        sources=[engine.ctx.fact.name, dim.table], facts=facts, names=[top[0], bottom[0]],
    )]


def _contribution(engine: Engine, measure: str, dim: Dim, total: float | None) -> list[Insight]:
    if engine.is_percent(measure) or not total:
        return []
    values = sorted((v for _, v in engine.by_member(measure, dim) if v > 0), reverse=True)
    if len(values) < 5:
        return []
    k = max(1, math.ceil(len(values) * 0.2))
    share = sum(values[:k]) / sum(values)
    cumulative = list(np.cumsum(values) / sum(values))
    facts = _round_facts({"share": share, "top_count": k, "members": len(values), "top_percent": 0.2})
    concentrated = share >= 0.6
    return [Insight(
        id=_id("pareto", measure, dim.table, dim.column), type="contribution", theme="Concentration", title=f"{dim.label} concentration",
        headline=f"The top {k} of {len(values)} {dim.label} values (20%) bring in {share_text(share)} of {measure}.",
        body="Results are highly concentrated, so a few members carry the business." if concentrated else "Results are spread fairly evenly across members.",
        action=f"Protect the top {k} {dim.label} values and set up alerts on them." if concentrated else f"Growth will need broad efforts across {dim.label} values.",
        value_text=share_text(share), delta=share, delta_text="Pareto",
        series=Series(kind="line", labels=[str(i + 1) for i in range(len(cumulative))], values=[float(c) for c in cumulative], highlight=k - 1),
        confidence=0.9, measure=measure, dimension=f"{dim.table}[{dim.column}]", sources=[engine.ctx.fact.name, dim.table], facts=facts,
    )]


def _rate_alerts(engine: Engine, rate: str, dims: list[Dim]) -> list[Insight]:
    overall = engine.value(rate)
    if not overall:
        return []
    best = None
    for dim in dims:
        if engine.slices_itself(rate, dim):
            continue
        for member, v in engine.by_member(rate, dim, real_only=True):
            n = engine.support(dim, member)
            if n >= 30 and v >= overall * 1.5 and (best is None or v / overall > best[3] / overall):
                best = (dim, member, n, v)
    if best is None:
        return []
    dim, member, n, v = best
    ratio = v / overall
    facts = _round_facts({"rate": v, "overall": overall, "ratio": ratio, "rows": n})
    return [Insight(
        id=_id("alert", rate, dim.table, dim.column, member), type="rate_alert", theme="Risk", title=f"{rate} alert",
        headline=f"{rate} for {dim.label} {member} is {engine.fmt(rate, v)}, {ratio:.1f}x the overall {engine.fmt(rate, overall)}.",
        body=f"The gap is based on {n:,} rows, enough to rule out noise from a handful of records.",
        action=f"Review {dim.label} {member} first; it is the biggest contributor to {rate.lower()}.",
        value_text=engine.fmt(rate, v), delta=ratio - 1, delta_text=f"{ratio:.1f}x overall",
        series=Series(kind="bar", labels=["Overall", member], values=[overall, v], highlight=1),
        confidence=round(min(0.97, 0.6 + 0.4 * min(1.0, n / 300)), 2), measure=rate, dimension=f"{dim.table}[{dim.column}]",
        sources=[engine.ctx.fact.name, dim.table], facts=facts, names=[member],
    )]


def add_texts(engine: Engine, i: Insight) -> None:
    if i.type == "contribution":
        i.series.texts = [f"{v:.0%}" for v in i.series.values]
    else:
        i.series.texts = [engine.fmt(i.measure, v) for v in i.series.values]


def compute_insights(engine: Engine) -> tuple[list[Insight], str | None, list[Dim]]:
    amount, count, rates = _primary(engine)
    if amount is None:
        return [], None, []
    dims = engine.dimensions()
    total = engine.value(amount)
    out: list[Insight] = []
    builders = [
        lambda: _comparisons(engine, amount),
        lambda: _trend(engine, amount),
        lambda: _anomalies(engine, amount),
        *[(lambda d=d: _performers(engine, amount, d, total)) for d in dims if d.table != DATE_TABLE][:3],
        *[(lambda d=d: _contribution(engine, amount, d, total)) for d in dims if d.table != DATE_TABLE][:1],
        *[(lambda r=r: _rate_alerts(engine, r, dims)) for r in rates[:2]],
        *[(lambda d=d: _performers(engine, amount, d, total)) for d in dims if d.table == DATE_TABLE],
        lambda: _anomalies(engine, count) if count and count != amount else [],
    ]
    for build in builders:
        try:
            out.extend(build())
        except Exception as exc:  # one odd series must never break the screen
            logger.warning("Insight builder failed: %s", exc)
    seen, unique = set(), []
    for i in out:
        if i.id not in seen:
            seen.add(i.id)
            unique.append(i)
            add_texts(engine, i)
    north = next((i for i in unique if i.type == "comparison" and "year" in i.title.lower()), None) or (unique[0] if unique else None)
    return unique, north.id if north else None, dims


# --- questions ---------------------------------------------------------------------

QUESTION_TEMPLATES: list[tuple[str, str]] = [
    ("Growth", "How is {amount} trending month over month?"),
    ("Growth", "Is {amount} growing versus the previous period?"),
    ("Performance", "Which {dim} drives the most {amount}?"),
    ("Performance", "Which {dim} is underperforming?"),
    ("Concentration", "Do a few {dim} values bring in most of the {amount}?"),
    ("Risk", "Where is {rate} unusually high?"),
    ("Risk", "Were there unusual spikes or drops in {amount}?"),
    ("Efficiency", "Which day of the week performs best?"),
]
# Question wording -> the insight types that answer it best (checked before the theme).
_QUESTION_TYPES: list[tuple[str, tuple[str, ...]]] = [
    ("trend", ("trend",)), ("spike", ("anomaly",)), ("drop", ("anomaly",)), ("unusual", ("anomaly", "rate_alert")),
    ("previous", ("comparison",)), ("versus", ("comparison",)), ("last year", ("comparison",)),
    ("most of", ("contribution",)), ("few", ("contribution",)), ("concentrat", ("contribution",)),
    ("drives", ("top_performer",)), ("top", ("top_performer",)), ("underperform", ("top_performer",)),
    ("day of the week", ("top_performer",)), ("high", ("rate_alert",)),
]


def template_questions(engine: Engine, insights: list[Insight], dims: list[Dim], audiences: list[str]) -> list[Question]:
    amount, _, rates = _primary(engine)
    dim = next((d.label for d in dims if d.table != DATE_TABLE), "segment")
    audience = audiences[0] if audiences else "Executive Leadership"
    out = []
    for theme, text in QUESTION_TEMPLATES:
        if "{rate}" in text and not rates:
            continue
        if "day of the week" in text and not any(d.table == DATE_TABLE for d in dims):
            continue
        q = text.format(amount=(amount or "the main measure").lower(), dim=dim, rate=(rates[0] if rates else "").lower())
        out.append(Question(id=_id("q", q), text=q, theme=theme, audience=audience))
    return out


def link_questions(questions: list[Question], insights: list[Insight]) -> None:
    for q in questions:
        text = q.text.lower()
        wanted = next((types for word, types in _QUESTION_TYPES if word in text), ())
        linked = [i for i in insights if i.type in wanted]
        if "day of the week" in text:
            linked = [i for i in insights if i.dimension and "Day of Week" in i.dimension]
        if not linked and not wanted:
            linked = [i for i in insights if i.theme == q.theme]
        q.insight_ids = [i.id for i in linked[:3]]
        if not linked:
            q.answer = "Nothing unusual found in the data for this question." if wanted else "Not enough data to answer this yet."
        elif "underperform" in text and linked[0].type == "top_performer":
            q.answer = linked[0].body
        else:
            q.answer = linked[0].headline
        for i in linked[:3]:
            if q.id not in i.question_ids:
                i.question_ids.append(q.id)


# --- grounding ---------------------------------------------------------------------

_NUMBER = re.compile(r"(?<![A-Za-z_])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:%|[KkMmBb](?![a-z]))?")


def _parse_number(token: str) -> tuple[float, bool, float] | None:
    """(value, is_percent, rounding tolerance implied by the digits written)."""
    t = token.strip().replace(",", "").replace(" ", "")
    is_pct = t.endswith("%")
    mult = 1.0
    if t and t[-1] in "KkMmBb":
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}[t[-1].lower()]
        t = t[:-1]
    t = t.rstrip("%").lstrip("+")
    try:
        v = float(t) * mult
    except ValueError:
        return None
    decimals = len(t.split(".")[1]) if "." in t else 0
    half_unit = 0.5 * 10 ** -decimals * mult
    if is_pct:
        return v / 100, True, half_unit / 100
    return v, False, half_unit


def grounded(text: str, facts: dict[str, float], extra: tuple[float, ...] = (), names: tuple[str, ...] = ()) -> tuple[bool, list[str]]:
    """Every number in the text must match a computed fact, allowing only the rounding implied by the
    digits written (2.48M ~ 2,481,234; 16.7% ~ 0.1671). Known names (members, measures) are ignored."""
    numeric_names: list[float] = []
    for name in sorted({n for n in names if n and any(ch.isdigit() for ch in n)}, key=len, reverse=True):
        try:
            numeric_names.append(float(name.replace(",", "")))  # e.g. a member called "2023"
        except ValueError:
            text = re.sub(rf"(?<![\w.]){re.escape(name)}(?![\w.])", " ", text)
    candidates = [abs(v) for v in facts.values()] + [abs(v) for v in extra] + [abs(v) for v in numeric_names]
    bad = []
    for m in _NUMBER.finditer(text):
        parsed = _parse_number(m.group())
        if parsed is None:
            continue
        value, is_pct, tolerance = abs(parsed[0]), parsed[1], parsed[2] + 1e-9
        forms = [c for c in candidates] + ([] if is_pct else [c * 100 for c in candidates])
        if not any(abs(value - c) <= tolerance for c in forms):
            bad.append(m.group().strip())
    return not bad, bad


def insight_names(i: Insight) -> tuple[str, ...]:
    """Names an insight may mention that can contain digits (members, labels, measure, column)."""
    dims = []
    if i.dimension:
        column = i.dimension.split("[", 1)[-1].rstrip("]")
        dims = [i.dimension, column, column.replace("_", " ")]
    return tuple(i.names) + tuple(i.series.labels) + (i.measure, i.title, *dims)


# --- AI narratives & questions -----------------------------------------------------------

class _AINarrative(BaseModel):
    id: str
    headline: str
    body: str
    action: str


class _AIQuestion(BaseModel):
    text: str
    theme: str
    audience: str


class _AIAnswer(BaseModel):
    questions: list[_AIQuestion] = []
    narratives: list[_AINarrative] = []


def _fact_sheet(insights: list[Insight]) -> list[dict]:
    return [
        {"id": i.id, "type": i.type, "measure": i.measure, "dimension": i.dimension, "template_headline": i.headline,
         "template_body": i.body, "facts": {k: round(v, 6) for k, v in i.facts.items()}}
        for i in insights
    ]


def _years(text: str) -> tuple[float, ...]:
    return tuple(float(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", text))


def ai_enrich(insights: list[Insight], questions: list[Question], industries: list[str], audiences: list[str], goals: str,
              llm: LLMProvider) -> tuple[list[Question], int, int]:
    """One LLM call for questions + narratives. Ungrounded narratives are rejected (template kept).
    Returns (ai questions, accepted narratives, rejected narratives)."""
    prompt = (
        (PROMPTS / "insights_narrate.md").read_text(encoding="utf-8")
        .replace("{industries}", ", ".join(industries) or "not set")
        .replace("{audiences}", ", ".join(audiences) or "Executive Leadership")
        .replace("{goals}", goals or "not given")
        .replace("{themes}", ", ".join(THEMES))
        .replace("{insights}", json.dumps(_fact_sheet(insights), ensure_ascii=False, separators=(",", ":")))
    )
    answer = llm.generate_text(prompt, json_schema=_AIAnswer)
    by_id = {i.id: i for i in insights}
    accepted = rejected = 0
    for n in answer.narratives:
        insight = by_id.get(n.id)
        if insight is None:
            continue
        # Labels in the template (years, member names with digits) are allowed numbers too.
        text = f"{n.headline} {n.body} {n.action}"
        ok, _ = grounded(text, insight.facts, _years(insight.headline + insight.body), insight_names(insight))
        if ok and n.headline.strip():
            insight.headline, insight.body, insight.action = n.headline.strip()[:300], n.body.strip()[:600], n.action.strip()[:300]
            insight.narrative_source = "ai"
            accepted += 1
        else:
            rejected += 1
    ai_questions = []
    for q in answer.questions[:10]:
        theme = q.theme if q.theme in THEMES else "Performance"
        if q.text.strip() and not _NUMBER.search(q.text):  # questions never carry made-up numbers
            ai_questions.append(Question(id=_id("q", q.text), text=q.text.strip()[:200], theme=theme, audience=q.audience[:60] or (audiences[0] if audiences else ""), source="ai"))
    return ai_questions, accepted, rejected


# --- custom questions ---------------------------------------------------------------------

def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) > 2}


def rule_spec(question: str, engine: Engine) -> QuerySpec | None:
    """Keyword matching: dimension and period by name, then the measure that best matches the rest."""
    words = _words(question)

    def mentioned(d: Dim) -> bool:
        specific = _words(d.column) - GENERIC_WORDS
        return bool(specific) and specific <= {w.rstrip("s") for w in words} | words

    dim = next((d for d in engine.dimensions() if mentioned(d)), None)
    measure_words = words - (_words(dim.column) if dim else set())
    scored = []
    for m in engine.measures:
        if m.status == "error":
            continue
        name_words = _words(m.name)
        overlap = len(measure_words & name_words)
        if overlap:
            # Extra words in the measure name ("Top", "Rank", "by City") count against it.
            scored.append((overlap - 0.5 * len(name_words - measure_words), -len(m.name), m.name))
    if not scored:
        amount, _, _ = _primary(engine)
        if amount is None:
            return None
        measure = amount
    else:
        measure = max(scored)[2]
    q = question.lower()
    period: Period = (
        "latest_month" if "last month" in q or "this month" in q else
        "latest_quarter" if "quarter" in q else
        "previous_year" if "last year" in q or "previous year" in q else
        "latest_year" if "this year" in q or "ytd" in q else "all"
    )
    return QuerySpec(measure=measure, dimension_table=dim.table if dim else None, dimension_column=dim.column if dim else None, period=period)


class _AISpec(BaseModel):
    measure: str
    dimension_table: str | None = None
    dimension_column: str | None = None
    filter_table: str | None = None
    filter_column: str | None = None
    filter_value: str | None = None
    period: Period = "all"
    top_n: int = 5


def ai_spec(question: str, engine: Engine, llm: LLMProvider) -> QuerySpec:
    schema = {
        "measures": [m.name for m in engine.measures if m.status != "error"],
        "dimensions": [{"table": d.table, "column": d.column} for d in engine.dimensions()],
        "filterable_columns": [{"table": t.name, "column": c.name} for t in engine.ctx.included for c in t.columns if c.data_type == "string" and c.key is None][:40],
        "periods": list(Period.__args__),  # type: ignore[attr-defined]
    }
    prompt = (PROMPTS / "insights_query.md").read_text(encoding="utf-8").replace("{question}", question).replace("{schema}", json.dumps(schema, separators=(",", ":")))
    answer = llm.generate_text(prompt, json_schema=_AISpec)
    return QuerySpec(**{**answer.model_dump(), "top_n": max(1, min(20, answer.top_n))})


def validate_spec(spec: QuerySpec, engine: Engine) -> QuerySpec:
    """Reject anything not in the model; returns the spec with canonical names."""
    measure = engine.by_name.get(spec.measure.lower())
    if measure is None:
        raise ValueError(f"Unknown measure [{spec.measure}]")
    out = spec.model_copy(update={"measure": measure.name})
    tables = {t.name.lower(): t for t in engine.ctx.included}
    if engine.has_time():
        tables[DATE_TABLE.lower()] = None

    def column(table: str | None, col: str | None) -> tuple[str, str] | None:
        if not table or not col:
            return None
        if table.lower() == DATE_TABLE.lower() and DATE_TABLE.lower() in tables:
            frame = engine.ctx.frames.get(DATE_TABLE)
            match = next((c for c in frame.columns if c.lower() == col.lower()), None) if frame is not None else None
            if match is None:
                raise ValueError(f"Unknown column {table}[{col}]")
            return DATE_TABLE, match
        t = tables.get(table.lower())
        if t is None:
            raise ValueError(f"Unknown table {table}")
        match = next((c.name for c in t.columns if c.name.lower() == col.lower()), None)
        if match is None:
            raise ValueError(f"Unknown column {table}[{col}]")
        return t.name, match

    dim = column(spec.dimension_table, spec.dimension_column)
    flt = column(spec.filter_table, spec.filter_column)
    out = out.model_copy(update={
        "dimension_table": dim[0] if dim else None, "dimension_column": dim[1] if dim else None,
        "filter_table": flt[0] if flt else None, "filter_column": flt[1] if flt else None,
        "filter_value": spec.filter_value if flt else None,
    })
    if out.period != "all" and not engine.has_time():
        out = out.model_copy(update={"period": "all"})
    return out


def _window(engine: Engine, period: str):
    end = engine.max_date()
    if period == "all" or end is None:
        return None, "all data"
    if period == "latest_month":
        return (end.replace(day=1), end), f"{end:%B %Y}"
    if period == "latest_quarter":
        start = pd.Timestamp(end.year, 3 * ((end.month - 1) // 3) + 1, 1)
        return (start, end), f"Q{(start.month - 1) // 3 + 1} {end.year}"
    if period == "previous_year":
        return (pd.Timestamp(end.year - 1, 1, 1), pd.Timestamp(end.year - 1, 12, 31)), f"{end.year - 1}"
    return (pd.Timestamp(end.year, 1, 1), end), f"{end.year} to date"


def execute(spec: QuerySpec, engine: Engine, question: str) -> Insight:
    window, period_label = _window(engine, spec.period)
    filters: tuple[Filter, ...] = ()
    scope = ""
    if spec.filter_table and spec.filter_column and spec.filter_value is not None:
        filters = (Filter(spec.filter_table, spec.filter_column, "=", (spec.filter_value,)),)
        scope = f" where {spec.filter_column} is {spec.filter_value}"
    total = engine.value(spec.measure, filters, window)
    facts: dict[str, float | None] = {"value": total}
    series = Series()
    if spec.dimension_table and spec.dimension_column:
        dim = Dim(spec.dimension_table, spec.dimension_column)
        rows = []
        for member in engine.members(dim):
            v = engine.value(spec.measure, filters + (Filter(dim.table, dim.column, "=", (member,)),), window)
            if v is not None:
                rows.append((member, v))
        rows.sort(key=lambda x: -x[1])
        rows = rows[: spec.top_n]
        series = Series(kind="bar", labels=[m for m, _ in rows], values=[v for _, v in rows], highlight=0 if rows else None)
        for i, (_, v) in enumerate(rows):
            facts[f"rank_{i + 1}"] = v
        facts["top_n"] = len(rows)
        if rows:
            headline = f"{rows[0][0]} leads {spec.measure} by {dim.label} ({period_label}{scope}) with {engine.fmt(spec.measure, rows[0][1])}."
            body = "Top values: " + "; ".join(f"{m}: {engine.fmt(spec.measure, v)}" for m, v in rows) + "."
        else:
            headline, body = f"No {dim.label} values have {spec.measure} for {period_label}{scope}.", ""
    else:
        headline = f"{spec.measure} for {period_label}{scope} is {engine.fmt(spec.measure, total)}."
        body = "Computed with the validated measure on the cleaned data."
    return Insight(
        id=_id("ask", question), type="answer", theme="Efficiency", title=question[:80], headline=headline, body=body,
        action="Pin this answer to show it in the dashboard's Key Insights card.", value_text=engine.fmt(spec.measure, total),
        series=series, confidence=0.95, measure=spec.measure,
        dimension=f"{spec.dimension_table}[{spec.dimension_column}]" if spec.dimension_column else None,
        sources=[engine.ctx.fact.name] if engine.ctx.fact else [], facts=_round_facts(facts),
        names=[n for n in (spec.filter_value, period_label, question) if n],
    )


def ai_error(exc: Exception) -> str:
    """Short, user-facing reason (provider messages can be paragraphs long)."""
    text = str(exc) if isinstance(exc, LLMError) else f"AI request failed ({type(exc).__name__})"
    first = text.split(" (", 1)[0] if isinstance(exc, LLMError) else text
    return first[:140]

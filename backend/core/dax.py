"""KPIs and DAX measures: industry library + model rules, validation, calculated values. (Spec Module 6)

Measures come from three places, in this order of precedence for names:
1. the industry KPI library (backend/kpi_library/*.json) for the Business Context industries,
2. rules over the data model (base sums/counts, ratios, time intelligence, rankings),
3. the user and the AI (stored per project; AI DAX must pass the validator to be accepted).

Every measure is statically checked (core/dax_validate.py) and, where the pattern is supported,
computed on the cleaned data (core/dax_eval.py) so the user sees a real value.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, field_validator

from core.dax_eval import Ctx, Data, EvalError, Evaluator, Link, Unsupported, parse
from core.dax_validate import Schema, check, find_cycles
from core.modelling import DATE_TABLE, ModelPlan, ModelTable
from core.profiling import ColumnProfile, QualityReport
from llm import LLMError, LLMProvider

logger = logging.getLogger(__name__)

LIBRARY_DIR = Path(__file__).resolve().parent.parent / "kpi_library"
PROMPTS = Path(__file__).resolve().parent.parent / "llm" / "prompts"

Format = Literal["currency", "whole", "decimal", "percent"]
Source = Literal["library", "rules", "ai", "user"]
Status = Literal["passed", "edge", "error"]

BASE, RATIOS, TIME, RANKS, CUSTOM = "01 Base Measures", "02 Ratios & Margins", "03 Time Intelligence", "04 Rankings & Pareto", "05 Custom"
FOLDERS = [BASE, RATIOS, TIME, RANKS, CUSTOM]
# Flag columns added by Clean Data describe data quality, not the business.
_CLEANING_FLAG = re.compile(r"_(is_missing|orphan|placeholder|suspect_date)(_\d+)?$")
_BAD_OUTCOME = re.compile(r"cancel|return|refund|fail|declin|reject|revers|fraud|churn|late|lost|void|chargeback", re.I)


# --- models -------------------------------------------------------------------------

class MeasureInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expression: str = Field(min_length=1, max_length=4000)
    format: Format = "decimal"
    folder: str = Field(default=CUSTOM, max_length=60)
    description: str = Field(default="", max_length=600)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = value.strip().strip("[]").strip()
        if not value or any(c in value for c in "[]\n\t"):
            raise ValueError("measure names cannot be empty or contain [ ] or line breaks")
        return value

    @field_validator("expression")
    @classmethod
    def _strip_assignment(cls, value: str) -> str:
        # Accept "Name = <expr>" pasted from Power BI (but not "VAR x = ..." or "F(...) = ...").
        m = re.match(r"^\s*\[?[^\[\]=\n(]+\]?\s*=(?!=)\s*(.+)$", value, re.S)
        if m and not re.match(r"^\s*VAR\b", value, re.I):
            return m.group(1).strip()
        return value.strip()


class Measure(MeasureInput):
    format_string: str
    source: Source
    edited: bool = False  # a generated measure the user changed
    status: Status = "passed"
    issues: list[str] = []
    deps: list[str] = []
    time_intelligence: bool = False
    value: float | None = None
    value_text: str | None = None
    test_context: str | None = None
    industry: str | None = None


class KpiCard(BaseModel):
    name: str
    value_text: str
    badge: str
    accent: bool = False
    spark: list[float] = []


class MeasurePlan(BaseModel):
    measures: list[Measure]
    folders: dict[str, int]
    cards: list[KpiCard]
    passed: int
    edge: int
    errors: int
    primary_fact: str | None
    test_context: str | None
    industries: list[str]
    notes: list[str] = []
    ai_status: Literal["off", "available"] = "off"


class StoredMeasures(BaseModel):
    """What the user (and the AI) changed; generated measures are rebuilt from the model."""

    custom: list[dict] = []  # MeasureInput + {"source": "user" | "ai"}
    overrides: dict[str, dict] = {}  # generated name -> MeasureInput fields
    removed: list[str] = []


# --- DAX text helpers -------------------------------------------------------------------

def tref(table: str) -> str:
    return "'" + table.replace("'", "''") + "'"


def cref(table: str, column: str) -> str:
    return tref(table) + "[" + column.replace("]", "]]") + "]"


def mref(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def dax_text(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def title(name: str) -> str:
    words = [w for w in re.split(r"[_\s]+", name) if w]
    return " ".join(w if w.isupper() and len(w) <= 4 else w.capitalize() for w in words) or name


def fact_title(table: str) -> str:
    """'credit_card_messy_data_transactions' -> 'Transactions'."""
    words = [w for w in re.split(r"[_\s]+", table) if w]
    return title(words[-1]) if len(words) > 2 else title(table)


def singular(word: str) -> str:
    return word[:-3] + "y" if word.endswith("ies") else word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def format_string(fmt: str, symbol: str | None = None) -> str:
    if fmt == "currency":
        return f'"{symbol}"#,##0.00' if symbol else "#,##0.00"
    return {"whole": "#,##0", "percent": "0.0%", "decimal": "#,##0.00"}.get(fmt, "#,##0.00")


def format_value(value, fmt: str, symbol: str | None = None) -> str | None:
    if value is None:
        return "(Blank)"
    if isinstance(value, pd.Timestamp):
        return f"{value:%Y-%m-%d}"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        return value
    v = float(value)
    if not np.isfinite(v):
        return "∞" if v > 0 else "-∞"
    if fmt == "percent":
        return f"{v:.2%}" if abs(v) < 0.1 else f"{v:.1%}"
    sign, sym = "-" if v < 0 else "", symbol if fmt == "currency" and symbol else ""
    if abs(v) >= 1e6 or (fmt == "currency" and abs(v) >= 1e5):  # compact, like the design's $1.48M
        div, suffix = next((d, s) for d, s in ((1e9, "B"), (1e6, "M"), (1e3, "K")) if abs(v) >= d)
        return f"{sign}{sym}{abs(v) / div:.2f}{suffix}"
    if fmt == "currency":
        return f"{sign}{sym}{abs(v):,.2f}"
    if fmt == "whole":
        return f"{v:,.0f}"
    return f"{v:,.2f}"


# --- model helpers --------------------------------------------------------------------

@dataclass
class GenContext:
    model: ModelPlan
    report: QualityReport
    frames: dict[str, pd.DataFrame]
    industries: list[str]
    profiles: dict[tuple[str, str], ColumnProfile] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.profiles = {(t.name, c.name): c for t in self.report.tables for c in t.column_profiles}

    @property
    def included(self) -> list[ModelTable]:
        return [t for t in self.model.tables if t.included]

    @property
    def fact(self) -> ModelTable | None:
        facts = [t for t in self.included if t.kind == "fact"]
        return max(facts, key=lambda t: t.rows) if facts else None

    def ordered_columns(self):
        """(table, column) pairs, primary fact first."""
        tables = sorted(self.included, key=lambda t: (t is not self.fact, t.kind != "fact"))
        for t in tables:
            for c in t.columns:
                if not c.derived and not _CLEANING_FLAG.search(c.name):
                    yield t, c

    def symbol(self, table: str, column: str) -> str | None:
        prof = self.profiles.get((table, column))
        return prof.currency_symbol if prof else None

    def values(self, table: str, column: str) -> pd.Series:
        return self.frames[table][column] if table in self.frames and column in self.frames[table] else pd.Series(dtype="object")

    def has_time(self) -> bool:
        fact = self.fact
        return bool(fact and self.model.date_table.enabled and any(
            r.active and r.valid and r.from_table == fact.name and r.to_table == DATE_TABLE for r in self.model.relationships
        ))


def _numeric(c) -> bool:
    return c.data_type in ("int64", "double", "decimal")


def _is_flag(ctx: GenContext, table: str, c) -> bool:
    if _CLEANING_FLAG.search(c.name) or c.derived:
        return False
    if c.data_type == "boolean":
        return True
    prof = ctx.profiles.get((table, c.name))
    if prof is not None and prof.role == "flag":
        return True
    values = ctx.values(table, c.name).dropna()
    return _numeric(c) and len(values) > 0 and set(pd.to_numeric(values, errors="coerce").dropna().unique()) <= {0, 1}


def _true_literal(ctx: GenContext, table: str, c) -> str:
    if c.data_type == "boolean":
        return "TRUE()"
    if _numeric(c):
        return "1"
    values = ctx.values(table, c.name).dropna().astype(str)
    truthy = [v for v in values.unique() if v.strip().lower() in ("true", "yes", "y", "t", "1")]
    return dax_text(truthy[0]) if truthy else "TRUE()"


def _find(ctx: GenContext, pattern: str, want: str):
    """First (table, column) whose name matches the pattern and the wanted kind."""
    rx = re.compile(pattern, re.I)
    for t, c in ctx.ordered_columns():
        if not rx.search(c.name):
            continue
        if want == "numeric" and _numeric(c) and c.key is None:
            return t, c
        if want == "id" and (c.key is not None or c.detected_type in ("id", "uuid")):
            return t, c
        if want == "text" and c.data_type == "string" and c.key is None:
            return t, c
        if want == "flag" and _is_flag(ctx, t.name, c):
            return t, c
    return None


# --- generation -------------------------------------------------------------------------

@dataclass
class _Builder:
    ctx: GenContext
    measures: dict[str, Measure] = field(default_factory=dict)  # lower name -> measure
    expressions: set[str] = field(default_factory=set)

    def has(self, name: str) -> bool:
        return name.lower() in self.measures

    def add(self, name: str, expression: str, fmt: str, folder: str, description: str, source: Source = "rules",
            symbol: str | None = None, industry: str | None = None) -> str | None:
        key = re.sub(r"\s+", "", expression.lower())
        if self.has(name) or key in self.expressions:
            return None
        self.expressions.add(key)
        self.measures[name.lower()] = Measure(
            name=name, expression=expression, format=fmt, folder=folder, description=description,
            format_string=format_string(fmt, symbol), source=source, industry=industry,
        )
        return name


def _library(industries: list[str]) -> list[tuple[str, dict]]:
    out = []
    files = {json.loads(p.read_text(encoding="utf-8"))["industry"]: p for p in LIBRARY_DIR.glob("*.json")}
    for industry in industries:
        path = files.get(industry)
        if path:
            out += [(industry, k) for k in json.loads(path.read_text(encoding="utf-8"))["kpis"]]
    return out


def _add_library(b: _Builder, industries: list[str]) -> None:
    ctx, fact = b.ctx, b.ctx.fact
    if fact is None:
        return
    for industry, k in _library(industries):
        kind, name, fmt, desc = k["kind"], k["name"], k.get("format", "decimal"), k.get("description", "")
        if b.has(name):
            continue
        expr, symbol, folder = None, None, BASE
        if kind in ("sum", "average"):
            found = _find(ctx, k["columns"], "numeric")
            if found:
                t, c = found
                expr = f"{'SUM' if kind == 'sum' else 'AVERAGE'}({cref(t.name, c.name)})"
                symbol = ctx.symbol(t.name, c.name)
        elif kind == "distinct":
            found = _find(ctx, k["columns"], "id")
            if found and found[0].name == fact.name:
                expr = f"DISTINCTCOUNT({cref(found[0].name, found[1].name)})"
            elif found:
                expr = f"DISTINCTCOUNT({cref(found[0].name, found[1].name)})"
            elif k.get("fallback") == "count_rows":
                expr = f"COUNTROWS({tref(fact.name)})"
        elif kind == "count_rows":
            expr = f"COUNTROWS({tref(fact.name)})"
        elif kind == "ratio" and b.has(k["numerator"]) and b.has(k["denominator"]):
            expr, folder = f"DIVIDE({mref(k['numerator'])}, {mref(k['denominator'])})", RATIOS
            symbol = _symbol_of(b, k["numerator"]) if fmt == "currency" else None
        elif kind == "difference" and b.has(k["a"]) and b.has(k["b"]):
            expr, folder = f"{mref(k['a'])} - {mref(k['b'])}", RATIOS
            symbol = _symbol_of(b, k["a"])
        elif kind in ("value_rate", "flag_rate", "flag_sum"):
            expr = _conditional(b, k, fact)
            folder = RATIOS
            if kind == "flag_sum" and expr:
                symbol = _symbol_of(b, k["measure"])
        if expr:
            b.add(name, expr, fmt, folder, desc, "library", symbol, industry)


def _symbol_of(b: _Builder, name: str) -> str | None:
    m = b.measures.get(name.lower())
    if m is None or not m.format_string.startswith('"'):
        return None
    return m.format_string.split('"')[1]


def _conditional(b: _Builder, k: dict, fact: ModelTable) -> str | None:
    ctx = b.ctx
    rows = f"COUNTROWS({tref(fact.name)})"
    if k["kind"] == "value_rate":
        rx_col, rx_val = re.compile(k["columns"], re.I), re.compile(k["values"], re.I)
        for c in fact.columns:
            if c.data_type != "string" or c.key is not None or not rx_col.search(c.name):
                continue
            values = sorted({str(v) for v in ctx.values(fact.name, c.name).dropna().unique() if rx_val.search(str(v))})
            if values:
                cond = f"{cref(fact.name, c.name)} = {dax_text(values[0])}" if len(values) == 1 else f"{cref(fact.name, c.name)} IN {{{', '.join(dax_text(v) for v in values[:10])}}}"
                return f"DIVIDE(CALCULATE({rows}, {cond}), {rows})"
        return None
    found = _find(ctx, k["columns"], "flag")
    if not found or found[0].name != fact.name:
        return None
    t, c = found
    cond = f"{cref(t.name, c.name)} = {_true_literal(ctx, t.name, c)}"
    if k["kind"] == "flag_rate":
        return f"DIVIDE(CALCULATE({rows}, {cond}), {rows})"
    if b.has(k["measure"]):
        return f"CALCULATE({mref(b.measures[k['measure'].lower()].name)}, {cond})"
    return None


def _add_rules(b: _Builder) -> tuple[str | None, str | None]:
    """Generic measures from the model. Returns the primary amount and count measure names."""
    ctx, fact = b.ctx, b.ctx.fact
    if fact is None:
        return None, None
    ft = fact_title(fact.name)
    count_expr = f"COUNTROWS({tref(fact.name)})"
    count = next((m.name for m in b.measures.values() if m.folder == BASE and m.format == "whole" and ("COUNTROWS" in m.expression or "DISTINCTCOUNT" in m.expression) and tref(fact.name) in m.expression), None)
    count = count or b.add(f"Total {ft}", count_expr, "whole", BASE, f"Number of rows in {fact.name}, i.e. {ft.lower()} in the current filter context.")

    amounts = [c for c in fact.columns if c.measure_candidate and not c.derived and not _is_flag(ctx, fact.name, c)][:6]
    primary = next((m.name for m in b.measures.values() if m.folder == BASE and m.format == "currency" and m.expression.startswith("SUM(")), None)
    for i, c in enumerate(amounts):
        symbol = ctx.symbol(fact.name, c.name)
        prof = ctx.profiles.get((fact.name, c.name))
        if prof and prof.detected_type == "percentage":  # summing rates is meaningless; average them
            b.add(f"Average {title(c.name)}", f"AVERAGE({cref(fact.name, c.name)})", "percent", BASE, f"Average {c.name} across {ft.lower()}.")
            continue
        fmt = "currency" if prof and prof.detected_type == "currency" else "whole" if c.data_type == "int64" else "decimal"
        name = b.add(f"Total {title(c.name)}", f"SUM({cref(fact.name, c.name)})", fmt, BASE, f"Sum of {c.name} across {ft.lower()}.", symbol=symbol)
        primary = primary or name or next((m.name for m in b.measures.values() if m.expression == f"SUM({cref(fact.name, c.name)})"), None)
        if i < 2:
            b.add(f"Average {title(c.name)}", f"AVERAGE({cref(fact.name, c.name)})", "currency" if fmt == "currency" else "decimal", BASE,
                  f"Average {c.name} per row of {fact.name}.", symbol=symbol)

    links = [r for r in ctx.model.relationships if r.valid and r.from_table == fact.name and r.to_table != DATE_TABLE]
    for r in links[:3]:
        b.add(f"Unique {fact_title(r.to_table)}", f"DISTINCTCOUNT({cref(fact.name, r.from_column)})", "whole", BASE,
              f"Distinct {r.from_column} values in {ft.lower()}: how many {fact_title(r.to_table).lower()} took part.")

    if primary and count:
        pm = b.measures[primary.lower()]
        b.add(f"{primary} per {singular(ft)}", f"DIVIDE({mref(primary)}, {mref(count)})", pm.format if pm.format != "whole" else "decimal",
              RATIOS, f"{primary} divided by {count}; returns blank instead of an error when there are no rows.", symbol=_symbol_of(b, primary))
        b.add(f"{primary} % of Total", f"DIVIDE({mref(primary)}, CALCULATE({mref(primary)}, ALL({tref(fact.name)})))", "percent", RATIOS,
              f"Share of all-time {primary.lower()} in the current selection (100% when nothing is filtered).")

    rows = f"COUNTROWS({tref(fact.name)})"
    for c in fact.columns:
        if _is_flag(ctx, fact.name, c):
            cond = f"{cref(fact.name, c.name)} = {_true_literal(ctx, fact.name, c)}"
            b.add(f"{title(c.name).removeprefix('Is ')} Rate", f"DIVIDE(CALCULATE({rows}, {cond}), {rows})", "percent", RATIOS,
                  f"Share of {ft.lower()} where {c.name} is true.")
            if primary:
                b.add(f"{title(c.name).removeprefix('Is ')} {primary}", f"CALCULATE({mref(primary)}, {cond})", b.measures[primary.lower()].format, RATIOS,
                      f"{primary} for {ft.lower()} where {c.name} is true.", symbol=_symbol_of(b, primary))
    status_cols = [c for c in fact.columns if c.data_type == "string" and c.key is None and re.search(r"status|state|outcome|result|type", c.name, re.I)]
    added = 0
    for c in status_cols:
        for v in ctx.values(fact.name, c.name).dropna().astype(str).value_counts().index:
            if added >= 3 or not _BAD_OUTCOME.search(v):
                continue
            if b.add(f"{title(v)} Rate", f"DIVIDE(CALCULATE({rows}, {cref(fact.name, c.name)} = {dax_text(v)}), {rows})", "percent", RATIOS,
                     f"Share of {ft.lower()} whose {c.name} is '{v}'."):
                added += 1
    return primary, count


def _add_time(b: _Builder, primary: str | None, count: str | None) -> None:
    if not b.ctx.has_time():
        return
    date = cref(DATE_TABLE, "Date")
    for base in [m for m in (primary, count) if m]:
        bm = b.measures[base.lower()]
        sym = _symbol_of(b, base)
        b.add(f"{base} YTD", f"TOTALYTD({mref(base)}, {date})", bm.format, TIME, f"{base} from 1 January to the latest date in context.", symbol=sym)
        b.add(f"{base} MTD", f"TOTALMTD({mref(base)}, {date})", bm.format, TIME, f"{base} from the 1st of the month to the latest date in context.", symbol=sym)
        py = b.add(f"{base} PY", f"CALCULATE({mref(base)}, SAMEPERIODLASTYEAR({date}))", bm.format, TIME,
                   f"{base} for the same period one year earlier, using the marked {DATE_TABLE} table.", symbol=sym)
        if py:
            b.add(f"{base} YoY %",
                  f"VAR __Current = {mref(base)}\nVAR __Prior = {mref(py)}\nRETURN\n    DIVIDE(__Current - __Prior, __Prior)",
                  "percent", TIME,
                  f"Change of {base.lower()} versus the same period last year. DIVIDE returns blank instead of an error when last year is empty.")
        b.add(f"{base} Rolling 30D", f"CALCULATE({mref(base)}, DATESINPERIOD({date}, MAX({date}), -30, DAY))", bm.format, TIME,
              f"{base} over the 30 days up to the latest date in context.", symbol=sym)


def _add_rankings(b: _Builder, primary: str | None) -> None:
    ctx, fact = b.ctx, b.ctx.fact
    if not primary or fact is None:
        return
    related = {r.to_table for r in ctx.model.relationships if r.valid and r.active and r.from_table == fact.name and r.to_table != DATE_TABLE}
    candidates = []
    for t in ctx.included:
        if t.name != fact.name and t.name not in related:
            continue
        for c in t.columns:
            prof = ctx.profiles.get((t.name, c.name))
            if prof and prof.role in ("categorical_slicer", "geo_dimension") and c.data_type == "string" and 2 <= prof.distinct_count <= 500:
                candidates.append((t, c))
    for t, c in candidates[:2]:
        col = cref(t.name, c.name)
        b.add(f"{primary} Rank by {title(c.name)}", f"RANKX(ALLSELECTED({col}), {mref(primary)}, , DESC, DENSE)", "whole", RANKS,
              f"Rank of each {c.name} by {primary.lower()} among the visible {c.name} values (1 = highest).")
        b.add(f"Top {title(c.name)} by {primary}",
              f"VAR __Top = TOPN(1, VALUES({col}), {mref(primary)}, DESC)\nRETURN\n    MAXX(__Top, {col})",
              "decimal", RANKS, f"The {c.name} with the highest {primary.lower()} in the current selection.")
    if candidates:
        t, c = candidates[0]
        col = cref(t.name, c.name)
        b.add(f"{primary} Pareto % by {title(c.name)}",
              f"VAR __Current = {mref(primary)}\nVAR __All = ADDCOLUMNS(ALLSELECTED({col}), \"@Value\", {mref(primary)})\n"
              f"RETURN\n    DIVIDE(SUMX(FILTER(__All, [@Value] >= __Current), [@Value]), SUMX(__All, [@Value]))",
              "percent", RANKS, f"Cumulative share of {primary.lower()} up to this {c.name} when sorted from largest to smallest (80/20 analysis).")


def generate(ctx: GenContext) -> list[Measure]:
    b = _Builder(ctx)
    _add_library(b, ctx.industries)
    primary, count = _add_rules(b)
    _add_time(b, primary, count)
    _add_rankings(b, primary)
    return list(b.measures.values())


# --- validation + values ----------------------------------------------------------------

def schema_for(model: ModelPlan) -> Schema:
    from core.tmdl import DATE_COLUMNS

    s = Schema()
    for t in model.tables:
        if t.included:
            s.add(t.name, [c.name for c in t.columns])
    if model.date_table.enabled:
        s.add(DATE_TABLE, [c for c, _, _ in DATE_COLUMNS])
    return s


def eval_data(ctx: GenContext, measures: list[Measure]) -> Data:
    links = [Link(r.from_table, r.from_column, r.to_table, r.to_column) for r in ctx.model.relationships if r.valid and r.active]
    return Data(
        frames=ctx.frames,
        links=links,
        date_table=DATE_TABLE if ctx.model.date_table.enabled and DATE_TABLE in ctx.frames else None,
        measures={m.name.lower(): m.expression for m in measures if m.status != "error"},
    )


def test_window(ev: Evaluator) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """The latest calendar year in the data, up to its last date (context for time measures)."""
    try:
        end = ev.max_date(Ctx())
    except (Unsupported, EvalError):
        return None
    return pd.Timestamp(end.year, 1, 1), end


def validate(ctx: GenContext, measures: list[Measure]) -> str | None:
    """Static checks + cycles + calculated values (mutates the measures). Returns the test-context label."""
    schema = schema_for(ctx.model)
    names = {m.name.lower(): m.name for m in measures}
    for m in measures:
        result = check(m.expression, schema, names)
        m.issues, m.deps, m.time_intelligence = list(result.issues), result.deps, result.time_intelligence
        m.status = "error" if result.issues else "passed"
        m.value = m.value_text = m.test_context = None
    cycles = find_cycles({m.name: m.deps for m in measures})
    for m in measures:
        if m.name in cycles:
            m.status = "error"
            m.issues.append("Circular reference: " + " → ".join(cycles[m.name]))
    by_name = {m.name.lower(): m for m in measures}

    def uses_time(m: Measure, seen: frozenset = frozenset()) -> bool:
        if m.time_intelligence:
            return True
        return any(d.lower() not in seen and d.lower() in by_name and uses_time(by_name[d.lower()], seen | {m.name.lower()}) for d in m.deps)

    for m in measures:
        if m.status != "error" and any(by_name.get(d.lower()) and by_name[d.lower()].status == "error" for d in m.deps):
            m.status = "error"
            m.issues.append("Depends on a measure with errors: " + ", ".join(d for d in m.deps if by_name.get(d.lower()) and by_name[d.lower()].status == "error"))

    ev = Evaluator(eval_data(ctx, measures))
    window = test_window(ev) if ctx.model.date_table.enabled else None
    label = f"Latest year: {window[0]:%Y} (1 Jan – {window[1]:%d %b})" if window else None
    for m in measures:
        if m.status == "error":
            continue
        timed = uses_time(m)
        if timed and window is None:
            m.status = "edge"
            m.issues.append("Needs the auto date table (enable it in Data Model) to evaluate.")
            continue
        context = Ctx(window=window) if timed else Ctx()
        try:
            m.value = _number(ev.measure(m.name, context))
            m.value_text = format_value(ev.measure(m.name, context), m.format, _symbol(m))
            m.test_context = label if timed else "All data"
            if m.value is None and not isinstance(ev.measure(m.name, context), (str, pd.Timestamp)):
                m.status = "edge"
                m.issues.append(
                    f"Blank in the test context ({label}): there is no data for the compared period. The formula is valid."
                    if timed else "Returns blank on the full data; check the filters it uses."
                )
        except Unsupported as exc:
            m.status = "edge"
            m.issues.append(f"Not evaluated here ({exc}); the value depends on the visual, check it in Power BI.")
        except (EvalError, RecursionError) as exc:
            m.status = "edge"
            m.issues.append(f"Could not evaluate: {exc}")
        except Exception as exc:  # evaluator gaps must never block the screen
            m.status = "edge"
            m.issues.append(f"Could not evaluate ({type(exc).__name__}).")
    return label


def _number(value) -> float | None:
    if value is None or isinstance(value, (str, pd.Timestamp, bool)):
        return None
    v = float(value)
    return v if np.isfinite(v) else None


def _symbol(m: Measure) -> str | None:
    return m.format_string.split('"')[1] if m.format_string.startswith('"') else None


# --- cards ----------------------------------------------------------------------------

def kpi_cards(ctx: GenContext, measures: list[Measure], label: str | None) -> list[KpiCard]:
    ok = [m for m in measures if m.status == "passed" and m.value is not None]
    by_name = {m.name: m for m in ok}
    picks: list[Measure] = []

    def pick(cond):
        m = next((m for m in ok if cond(m) and m not in picks), None)
        if m:
            picks.append(m)

    pick(lambda m: m.folder == BASE and m.format == "currency" and m.expression.startswith("SUM("))
    pick(lambda m: m.folder == BASE and m.format == "whole" and ("COUNTROWS" in m.expression or "DISTINCTCOUNT" in m.expression))
    pick(lambda m: m.folder == RATIOS and m.format != "percent" and m.expression.startswith("DIVIDE("))
    pick(lambda m: m.folder == RATIOS and m.format == "percent" and "% of Total" not in m.name)
    pick(lambda m: m.folder == TIME and m.name.endswith("YoY %"))
    for m in ok:
        if len(picks) >= 5:
            break
        if m not in picks and m.folder in (BASE, RATIOS):
            picks.append(m)

    ev = Evaluator(eval_data(ctx, measures))
    yoy = {m.name.removesuffix(" YoY %"): m for m in ok if m.name.endswith(" YoY %")}
    fact = ctx.fact
    cards = []
    for m in picks[:5]:
        if m.name in yoy and yoy[m.name].value is not None:
            badge = f"{yoy[m.name].value:+.1%} YoY"
        elif m.folder == TIME:
            badge = "SAMEPERIOD"
        elif m.folder == RATIOS and fact is not None:
            badge = f"per {singular(fact_title(fact.name)).lower()}" if m.format != "percent" else f"of {fact_title(fact.name).lower()}"
        else:
            badge = m.industry or (fact_title(fact.name) if fact else "")
        cards.append(KpiCard(name=m.name, value_text=m.value_text or "", badge=badge, accent=m.folder == TIME, spark=_spark(ev, m, ctx)))
    return cards


def _spark(ev: Evaluator, m: Measure, ctx: GenContext) -> list[float]:
    """Monthly values for the last 12 months of data (empty when there is no date table)."""
    if not ctx.has_time() or m.folder == RANKS:
        return []
    try:
        end = ev.max_date(Ctx())
    except Exception:
        return []
    points = []
    for i in range(11, -1, -1):
        month_end = (end - pd.DateOffset(months=i)) + pd.offsets.MonthEnd(0)
        month_start = month_end.replace(day=1)
        try:
            v = _number(ev.measure(m.name, Ctx(window=(month_start, min(month_end, end)))))
        except Exception:
            return []
        points.append(round(v, 6) if v is not None else 0.0)
    return points


# --- AI -----------------------------------------------------------------------------

class _AIMeasure(BaseModel):
    name: str
    expression: str
    format: Format = "decimal"
    folder: str = CUSTOM
    description: str = ""


class _AISuggestions(BaseModel):
    measures: list[_AIMeasure]


class _AIPolish(BaseModel):
    expression: str
    description: str


def model_digest(ctx: GenContext, measures: list[Measure]) -> str:
    tables = []
    for t in ctx.included:
        tables.append({
            "table": t.name, "kind": t.kind,
            "columns": [{"name": c.name, "type": c.data_type, "key": c.key} for c in t.columns if not c.derived],
        })
    if ctx.model.date_table.enabled:
        tables.append({"table": DATE_TABLE, "kind": "date", "columns": [{"name": "Date", "type": "dateTime"}, {"name": "Year"}, {"name": "Month Name"}, {"name": "Quarter"}]})
    rels = [f"{r.from_table}[{r.from_column}] -> {r.to_table}[{r.to_column}]" for r in ctx.model.relationships if r.valid and r.active]
    return json.dumps({"tables": tables, "relationships": rels, "existing_measures": [m.name for m in measures]}, separators=(",", ":"))


def ai_suggest(ctx: GenContext, measures: list[Measure], goals: str, audiences: list[str], llm: LLMProvider) -> list[MeasureInput]:
    prompt = (
        (PROMPTS / "dax_suggest.md").read_text(encoding="utf-8")
        .replace("{goals}", goals or "not given")
        .replace("{industries}", ", ".join(ctx.industries) or "not set")
        .replace("{audiences}", ", ".join(audiences) or "not set")
        .replace("{model}", model_digest(ctx, measures))
    )
    answer = llm.generate_text(prompt, json_schema=_AISuggestions)
    out = []
    for m in answer.measures[:8]:
        try:
            out.append(MeasureInput(name=m.name, expression=m.expression, format=m.format,
                                    folder=m.folder if m.folder in FOLDERS else CUSTOM, description=m.description))
        except ValueError:
            continue
    return out


def ai_polish(ctx: GenContext, measures: list[Measure], target: Measure, llm: LLMProvider) -> _AIPolish:
    prompt = (
        (PROMPTS / "dax_polish.md").read_text(encoding="utf-8")
        .replace("{name}", target.name)
        .replace("{expression}", target.expression)
        .replace("{description}", target.description or "none")
        .replace("{issues}", "; ".join(target.issues) or "none")
        .replace("{model}", model_digest(ctx, measures))
    )
    return llm.generate_text(prompt, json_schema=_AIPolish)


def ai_note(exc: Exception) -> str:
    return str(exc) if isinstance(exc, LLMError) else f"AI request failed ({type(exc).__name__})"


def assemble(ctx: GenContext, stored: StoredMeasures) -> tuple[list[Measure], set[str]]:
    """Generated measures with the user's overrides/removals, plus custom measures. Returns
    (measures, generated names)."""
    generated = generate(ctx)
    gen_names = {m.name.lower() for m in generated}
    removed = {n.lower() for n in stored.removed}
    out: list[Measure] = []
    for m in generated:
        if m.name.lower() in removed:
            continue
        override = stored.overrides.get(m.name)
        if override:
            data = MeasureInput.model_validate({**m.model_dump(include=set(MeasureInput.model_fields)), **override, "name": m.name})
            m = m.model_copy(update={**data.model_dump(), "edited": True, "format_string": format_string(data.format, _symbol(m))})
        out.append(m)
    taken = {m.name.lower() for m in out}
    for raw in stored.custom:
        data = MeasureInput.model_validate(raw)
        if data.name.lower() in taken:
            continue
        taken.add(data.name.lower())
        out.append(Measure(**data.model_dump(), format_string=format_string(data.format), source=raw.get("source", "user")))
    return out, gen_names


def build_plan(ctx: GenContext, stored: StoredMeasures, llm_available: bool, notes: list[str] | None = None) -> tuple[MeasurePlan, list[Measure]]:
    measures, _ = assemble(ctx, stored)
    label = validate(ctx, measures)
    order = {f: i for i, f in enumerate(FOLDERS)}
    measures.sort(key=lambda m: (order.get(m.folder, len(FOLDERS)), m.folder))
    folders: dict[str, int] = {}
    for m in measures:
        folders[m.folder] = folders.get(m.folder, 0) + 1
    plan = MeasurePlan(
        measures=measures, folders=folders, cards=kpi_cards(ctx, measures, label),
        passed=sum(m.status == "passed" for m in measures), edge=sum(m.status == "edge" for m in measures),
        errors=sum(m.status == "error" for m in measures), primary_fact=ctx.fact.name if ctx.fact else None,
        test_context=label, industries=ctx.industries, notes=notes or [],
        ai_status="available" if llm_available else "off",
    )
    return plan, measures

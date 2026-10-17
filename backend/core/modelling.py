"""Star schema, relationships and auto date table. (Spec Module 5)

The model is built from the *cleaned* tables (accepted Clean steps), so data types, keys
and cardinalities match what Power BI will load. Rules decide everything first; the LLM
can refine fact/dimension classification and table inclusion, and the user's choices
(ModelSettings) always win over both.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from core.cleaning import KIND_ORDER, CleaningStep, PipelineResult, SourceTable
from core.profiling import QualityReport, TableProfile
from llm import LLMError, LLMProvider

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "model_tables.md"
DATE_TABLE = "Dim_Date"

TableKind = Literal["fact", "dimension", "date"]
DataType = Literal["string", "int64", "double", "decimal", "dateTime", "boolean"]
Source = Literal["rules", "ai", "user"]

# Detected type -> TMDL data type, used only when the Clean step typed the column.
TMDL_TYPES: dict[str, DataType] = {
    "integer": "int64", "decimal": "double", "percentage": "double", "currency": "decimal",
    "date": "dateTime", "datetime": "dateTime", "boolean": "boolean",
}
NUMERIC: tuple[DataType, ...] = ("int64", "double", "decimal")

# Sheets that document or summarise the data rather than hold it.
_NON_DATA_NAME = re.compile(
    r"(readme|read_me|dictionary|data_dict|glossary|cleaning_log|change_?log|_log$|pivot|summary|notes?$|instructions|metadata|about)",
    re.I,
)
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


# --- models -------------------------------------------------------------------------

class ModelColumn(BaseModel):
    name: str
    data_type: DataType
    detected_type: str
    key: Literal["pk", "fk"] | None = None
    hidden: bool = False
    measure_candidate: bool = False
    derived: bool = False  # added by the model, e.g. a date-only copy of a datetime column


class ModelTable(BaseModel):
    name: str
    kind: TableKind
    kind_source: Source
    included: bool
    exclusion_reason: str | None = None
    rows: int
    source: str
    grain: str | None = None
    columns: list[ModelColumn]


class RelationshipInput(BaseModel):
    from_table: str  # many side
    from_column: str
    to_table: str  # one side
    to_column: str


class Relationship(RelationshipInput):
    id: str
    cardinality: Literal["many_to_one", "one_to_one"] = "many_to_one"
    cross_filter: Literal["single", "both"] = "single"
    active: bool = True
    origin: Literal["auto", "user", "date"]
    valid: bool = True
    missing_keys: int = 0  # many-side values with no match on the one side
    note: str | None = None


class TableOverride(BaseModel):
    included: bool | None = None
    kind: Literal["fact", "dimension"] | None = None


class ModelSettings(BaseModel):
    table_overrides: dict[str, TableOverride] = {}
    removed_relationships: list[str] = []
    added_relationships: list[RelationshipInput] = []
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)
    hide_keys: bool = True
    date_table: bool = True


class DateTableSpec(BaseModel):
    enabled: bool
    name: str = DATE_TABLE
    start: str | None = None  # first day of the first year in the data
    end: str | None = None  # last day of the last year
    fiscal_year_start_month: int = 1
    sources: list[str] = []  # "table.column" date columns related to the date table


class ModelNote(BaseModel):
    tone: Literal["success", "info", "warning"]
    title: str
    text: str


class ModelPlan(BaseModel):
    tables: list[ModelTable]
    relationships: list[Relationship]
    date_table: DateTableSpec
    settings: ModelSettings
    facts: int
    dimensions: int
    ambiguities: int
    hidden_columns: int
    health_score: int
    notes: list[ModelNote]
    ai_status: Literal["off", "pending", "done", "failed"] = "off"
    ai_note: str | None = None
    tmdl_valid: bool = True
    tmdl_errors: list[str] = []


# AI answer (validated, then filtered against the real tables).
class _AITable(BaseModel):
    table: str
    kind: Literal["fact", "dimension"]
    include: bool
    reason: str = ""


class _AINote(BaseModel):
    title: str
    text: str


class AIModelAnswer(BaseModel):
    tables: list[_AITable]
    notes: list[_AINote] = []


# --- helpers ------------------------------------------------------------------------

def rel_id(r: RelationshipInput) -> str:
    return f"{r.from_table}.{r.from_column}->{r.to_table}.{r.to_column}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _source_label(src: SourceTable) -> str:
    return src.filename + (f" › {src.sheet}" if src.sheet else "")


_CONVERTING = ("normalise_booleans", "cast_numeric", "cast_european", "date_format", "set_types", "excel_serial_dates")


def _typed_columns(accepted: list[CleaningStep]) -> dict[str, str]:
    """Columns the Clean step converts away from text, with their final type (later steps win)."""
    typed: dict[str, str] = {}
    for s in sorted(accepted, key=lambda s: KIND_ORDER.index(s.kind)):
        if s.kind in _CONVERTING and not s.error:
            typed.update(s.types)
    return typed


def exclusion_reason(profile: TableProfile) -> str | None:
    if _NON_DATA_NAME.search(profile.name):
        return "Looks like a documentation or summary sheet"
    if profile.columns <= 2:
        return "Too few columns to be a data table"
    if profile.rows < 2:
        return "Too few rows"
    return None


def signature(report: QualityReport) -> list[str]:
    """Identifies the table set an AI answer was made for (re-ask when files change)."""
    return [f"{t.name}:{t.rows}:{t.columns}" for t in report.tables]


# --- AI refinement --------------------------------------------------------------------

def ai_classify(report: QualityReport, llm: LLMProvider) -> AIModelAnswer:
    digest = [
        {
            "table": t.name,
            "rows": t.rows,
            "columns": [{"name": c.name, "role": c.role, "target": c.role_target} for c in t.column_profiles],
        }
        for t in report.tables
    ]
    prompt = PROMPT_PATH.read_text(encoding="utf-8").replace("{tables}", json.dumps(digest, separators=(",", ":")))
    return llm.generate_text(prompt, json_schema=AIModelAnswer)


def ai_note_for(exc: Exception) -> str:
    return str(exc) if isinstance(exc, LLMError) else f"AI request failed ({type(exc).__name__})"


# --- build --------------------------------------------------------------------------

def _columns(profile: TableProfile, result: PipelineResult, accepted: list[CleaningStep]) -> list[ModelColumn]:
    typed = _typed_columns(accepted)
    by_name = {c.name: c for c in profile.column_profiles}
    cols = []
    for name in result.df.columns:
        prof = by_name.get(str(name))
        if prof is None:  # e.g. "<col>_is_missing" flags added by the Clean step
            cols.append(ModelColumn(name=str(name), data_type="boolean", detected_type="boolean"))
            continue
        data_type: DataType = TMDL_TYPES.get(typed.get(prof.name, ""), "string")
        key = "pk" if prof.role == "primary_key" else "fk" if prof.role == "foreign_key" else None
        cols.append(ModelColumn(
            name=prof.name, data_type=data_type, detected_type=typed.get(prof.name, prof.detected_type), key=key,
            measure_candidate=prof.role == "measure" and data_type in NUMERIC,
        ))
    return cols


def _cleaned_links(included: list[ModelTable], frames: dict[str, pd.DataFrame], profiles: dict[str, TableProfile]) -> list[RelationshipInput]:
    """Same-named ID columns where one side is unique after cleaning and holds most of the other
    side's values. Catches keys that only became unique in Clean Data (e.g. one row per customer)."""
    links = []
    for t in included:
        for prof in profiles[t.name].column_profiles:
            if prof.detected_type not in ("id", "uuid") or prof.name not in frames[t.name]:
                continue
            many = frames[t.name][prof.name].dropna().astype(str)
            if many.empty or many.is_unique:
                continue
            for other in included:
                if other.name == t.name or prof.name not in frames[other.name]:
                    continue
                one = frames[other.name][prof.name].dropna().astype(str)
                if len(one) and one.is_unique and many.isin(set(one)).mean() >= 0.8:
                    links.append(RelationshipInput(from_table=t.name, from_column=prof.name, to_table=other.name, to_column=prof.name))
    return links


def _rule_kinds(tables: list[ModelTable], report: QualityReport, links: list[RelationshipInput]) -> dict[str, TableKind]:
    """Referenced tables are dimensions, tables with outgoing keys are facts, else the biggest measure table."""
    included = {t.name for t in tables if t.included}
    profiles = {t.name: t for t in report.tables}
    targets = {c.role_target for t in report.tables if t.name in included for c in t.column_profiles if c.role == "foreign_key"}
    targets |= {link.to_table for link in links}
    sources = {link.from_table for link in links}
    kinds: dict[str, TableKind] = {}
    for t in tables:
        outgoing = t.name in sources or any(c.role == "foreign_key" and c.role_target in included for c in profiles[t.name].column_profiles)
        kinds[t.name] = "dimension" if t.name in targets and not outgoing else "fact" if outgoing else "dimension"
    if included and not any(kinds[n] == "fact" for n in included):
        def weight(name: str) -> tuple[int, int]:
            measures = sum(1 for c in profiles[name].column_profiles if c.role == "measure")
            return measures, profiles[name].rows
        kinds[max(included, key=weight)] = "fact"
    return kinds


def _verify(rel: Relationship, frames: dict[str, pd.DataFrame], types: dict[tuple[str, str], DataType]) -> None:
    """Cardinality and integrity against the cleaned rows."""
    many, one = frames[rel.from_table][rel.from_column], frames[rel.to_table][rel.to_column]
    many_vals, one_vals = many.dropna().astype(str), one.dropna().astype(str)
    if types[(rel.from_table, rel.from_column)] != types[(rel.to_table, rel.to_column)]:
        rel.valid = False
        rel.note = "Column data types differ; accept the same type step for both in Clean Data."
        return
    if not one_vals.is_unique:
        rel.valid = False
        rel.note = f"{rel.to_table}.{rel.to_column} has {one_vals.duplicated().sum():,} duplicate values; it cannot be the 1 side. Remove duplicates in Clean Data."
        return
    rel.cardinality = "one_to_one" if many_vals.is_unique else "many_to_one"
    rel.missing_keys = int((~many_vals.isin(set(one_vals))).sum())
    if rel.missing_keys:
        rel.note = f"{rel.missing_keys:,} rows point to {rel.to_column} values missing from {rel.to_table}; they will show as (Blank)."


def build_model(
    report: QualityReport,
    cleaned: dict[str, tuple[SourceTable, list[CleaningStep], PipelineResult]],
    settings: ModelSettings,
    ai: AIModelAnswer | None = None,
) -> ModelPlan:
    notes: list[ModelNote] = []
    profiles = {t.name: t for t in report.tables}
    ai_tables = {a.table: a for a in (ai.tables if ai else []) if a.table in cleaned}

    # 1. tables: rules -> AI -> user
    tables: list[ModelTable] = []
    for name, (src, accepted, result) in cleaned.items():
        profile = profiles[name]
        reason = exclusion_reason(profile)
        included, kind_source = reason is None, "rules"
        if name in ai_tables:
            included = ai_tables[name].include
            reason = None if included else (ai_tables[name].reason or reason or "Excluded by AI")
        override = settings.table_overrides.get(name)
        if override and override.included is not None:
            included = override.included
            reason = None if included else (reason or "Excluded by you")
        tables.append(ModelTable(
            name=name, kind="dimension", kind_source=kind_source, included=included,
            exclusion_reason=None if included else reason, rows=len(result.df), source=_source_label(src),
            columns=_columns(profile, result, accepted),
        ))
    frames = {n: cleaned[n][2].df for n in cleaned}
    links = _cleaned_links([t for t in tables if t.included], frames, profiles)
    for link in links:  # mark the key columns so they are hidden and drawn as keys
        for t in tables:
            for c in t.columns:
                if (t.name, c.name) == (link.to_table, link.to_column):
                    c.key = "pk"
                elif (t.name, c.name) == (link.from_table, link.from_column) and c.key is None:
                    c.key = "fk"
    kinds = _rule_kinds(tables, report, links)
    for t in tables:
        t.kind = kinds[t.name]
        if t.name in ai_tables:
            t.kind, t.kind_source = ai_tables[t.name].kind, "ai"
        override = settings.table_overrides.get(t.name)
        if override and override.kind:
            t.kind, t.kind_source = override.kind, "user"
        pk = next((c.name for c in t.columns if c.key == "pk"), None)
        if t.kind == "fact":
            t.grain = f"1 row per {pk}" if pk else "no unique key"
    by_name = {t.name: t for t in tables}
    included = [t for t in tables if t.included]
    types ={(t.name, c.name): c.data_type for t in tables for c in t.columns}

    # 2. relationships from detected foreign keys and key links in the cleaned data, then the user's additions
    candidates: list[tuple[RelationshipInput, Literal["auto", "user"]]] = []
    for t in included:
        for c in profiles[t.name].column_profiles:
            target = by_name.get(c.role_target or "")
            if c.role != "foreign_key" or target is None or not target.included:
                continue
            pk = next((x.name for x in target.columns if x.key == "pk"), None) or (c.name if c.name in frames[target.name] else None)
            if pk:
                candidates.append((RelationshipInput(from_table=t.name, from_column=c.name, to_table=target.name, to_column=pk), "auto"))
    candidates += [(link, "auto") for link in links]
    candidates += [(r, "user") for r in settings.added_relationships]

    relationships: list[Relationship] = []
    seen: set[str] = set()
    for inp, origin in candidates:
        rid = rel_id(inp)
        if rid in seen or rid in settings.removed_relationships:
            continue
        if inp.from_table not in by_name or inp.to_table not in by_name or not (by_name[inp.from_table].included and by_name[inp.to_table].included):
            continue
        if inp.from_column not in frames[inp.from_table] or inp.to_column not in frames[inp.to_table]:
            continue
        seen.add(rid)
        rel = Relationship(id=rid, origin=origin, **inp.model_dump())
        _verify(rel, frames, types)
        relationships.append(rel)

    # 3. auto date table, related to the date columns of the fact tables
    date_spec = DateTableSpec(enabled=False, fiscal_year_start_month=settings.fiscal_year_start_month)
    if settings.date_table:
        date_cols: list[tuple[ModelTable, ModelColumn]] = []
        untyped: list[str] = []
        for t in included:
            if t.kind != "fact":
                continue
            for c in t.columns:
                prof = next((p for p in profiles[t.name].column_profiles if p.name == c.name), None)
                if prof is None or c.derived:
                    continue
                if c.data_type == "dateTime":  # includes Excel serials / text dates converted in Clean Data
                    date_cols.append((t, c))
                elif prof.role == "time_dimension":
                    untyped.append(f"{t.name}.{c.name}")
        if untyped:
            notes.append(ModelNote(
                tone="warning", title="Date columns still text",
                text=f"{', '.join(untyped)} cannot join the date table until 'Apply detected data types' is accepted in Clean Data.",
            ))
        values = pd.concat([pd.to_datetime(frames[t.name][c.name], errors="coerce") for t, c in date_cols]) if date_cols else pd.Series(dtype="datetime64[ns]")
        values = values.dropna()
        if not values.empty:
            date_spec = DateTableSpec(
                enabled=True, start=f"{values.min().year}-01-01", end=f"{values.max().year}-12-31",
                fiscal_year_start_month=settings.fiscal_year_start_month,
            )
            years = values.max().year - values.min().year + 1
            if years > 15:
                notes.append(ModelNote(
                    tone="warning", title="Wide date range",
                    text=f"Dates run from {values.min():%Y-%m-%d} to {values.max():%Y-%m-%d} ({years} years); check for placeholder or typo dates.",
                ))
            per_fact: dict[str, int] = {}
            for t, c in date_cols:
                key_col = c.name
                if c.detected_type == "datetime":  # relationships need a date-only column
                    key_col = f"{c.name}_date"
                    if key_col not in {x.name for x in t.columns}:
                        t.columns.append(ModelColumn(name=key_col, data_type="dateTime", detected_type="date", key="fk", derived=True))
                else:
                    c.key = c.key or "fk"
                first = per_fact.get(t.name, 0) == 0
                per_fact[t.name] = per_fact.get(t.name, 0) + 1
                rel = Relationship(
                    id=f"{t.name}.{key_col}->{DATE_TABLE}.Date", from_table=t.name, from_column=key_col,
                    to_table=DATE_TABLE, to_column="Date", origin="date", active=first,
                    note=None if first else "Role-playing date: inactive, use USERELATIONSHIP in DAX.",
                )
                if rel.id not in settings.removed_relationships:
                    relationships.append(rel)
                    date_spec.sources.append(f"{t.name}.{c.name}")
        elif not untyped:
            notes.append(ModelNote(tone="info", title="No date table", text="No date column found in the fact tables, so no date table was added."))

    # 4. ambiguous filter paths: an active relationship that joins two already-connected tables
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    ambiguities = 0
    for rel in relationships:
        if not rel.active or not rel.valid:
            continue
        a, b = find(rel.from_table), find(rel.to_table)
        if a == b:
            rel.active = False
            rel.note = "Set inactive: a second filter path between these tables would be ambiguous."
            ambiguities += 1
        else:
            parent[a] = b

    # 5. hide keys and technical columns from report view
    hidden = 0
    for t in included:
        for c in t.columns:
            c.hidden = settings.hide_keys and (c.key is not None or c.derived or c.detected_type in ("id", "uuid"))
            hidden += c.hidden

    # 6. notes
    facts = [t for t in included if t.kind == "fact"]
    dims = [t for t in included if t.kind == "dimension"]
    excluded = [t.name for t in tables if not t.included]
    if facts:
        notes.insert(0, ModelNote(
            tone="success", title="Star schema",
            text=f"{_plural(len(facts), 'fact table')} ({', '.join(t.name for t in facts)}) with {_plural(len(dims) + date_spec.enabled, 'dimension')}.",
        ))
    if date_spec.enabled:
        fy = "" if settings.fiscal_year_start_month == 1 else f" Fiscal year starts in {MONTHS[settings.fiscal_year_start_month - 1]}."
        notes.append(ModelNote(
            tone="success", title="Auto date table",
            text=f"{DATE_TABLE} covers {date_spec.start} to {date_spec.end} and is marked as the date table, so DAX time intelligence (TOTALYTD, SAMEPERIODLASTYEAR) works.{fy}",
        ))
    if excluded:
        notes.append(ModelNote(tone="info", title="Excluded sheets", text=f"Not loaded into the model: {', '.join(excluded)}. Include any of them from the diagram."))
    if len(facts) == 1 and not dims and len(included) == 1:
        slicers = [c.name for c in profiles[facts[0].name].column_profiles if c.role in ("categorical_slicer", "geo_dimension")][:4]
        if slicers:
            notes.append(ModelNote(
                tone="info", title="Split suggestion",
                text=f"Single flat table. Splitting {', '.join(slicers)} into dimension tables would give a cleaner star schema (not applied automatically).",
            ))
    for rel in relationships:
        if not rel.valid or rel.missing_keys:
            notes.append(ModelNote(tone="warning", title=f"{rel.from_table} → {rel.to_table}", text=rel.note or ""))
    if hidden:
        notes.append(ModelNote(tone="success", title="Keys hidden", text=f"{_plural(hidden, 'key column')} hidden from report view; relationships still use them."))
    for n in ai.notes[:3] if ai else []:
        notes.append(ModelNote(tone="info", title=n.title[:80], text=n.text[:400]))

    invalid = sum(1 for r in relationships if not r.valid)
    with_missing = sum(1 for r in relationships if r.valid and r.missing_keys)
    score = 100 - 15 * invalid - 10 * ambiguities - 5 * min(with_missing, 3) - (0 if date_spec.enabled else 10) - (0 if facts else 30)
    return ModelPlan(
        tables=tables, relationships=relationships, date_table=date_spec, settings=settings,
        facts=len(facts), dimensions=len(dims) + int(date_spec.enabled), ambiguities=ambiguities,
        hidden_columns=hidden, health_score=max(0, score), notes=notes,
    )

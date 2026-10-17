"""Cleaning suggestions, a pandas preview and matching Power Query M code. (Spec Module 3)

Suggestions are derived deterministically from the Data Quality Report, so this step works
without an AI key. Each accepted step is applied twice from one pass over the table
(`run_pipeline`): in pandas for the before/after preview, and as Power Query M so that the
cleaning happens inside Power BI and keeps working on refresh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel

from core.profiling import ColumnProfile, QualityReport, TableProfile, _to_datetime, _to_number

StepKind = Literal["remove_duplicates", "standardise_categories", "cast_numeric", "set_types", "handle_nulls"]
StepStatus = Literal["pending", "accepted", "skipped"]
NullStrategy = Literal["fill_median", "fill_unknown", "remove_rows", "flag"]
Impact = Literal["High", "Medium", "Low"]

# Steps always run in this order, in pandas and in M alike.
KIND_ORDER: list[StepKind] = ["remove_duplicates", "standardise_categories", "cast_numeric", "set_types", "handle_nulls"]
NUMERIC_TYPES = ("currency", "percentage", "integer", "decimal")
UNKNOWN = "Unknown"
_TRUE_VALUES = ("true", "yes", "y", "t", "1")


# --- models -------------------------------------------------------------------------

class ValueMerge(BaseModel):
    canonical: str
    variants: dict[str, int]  # raw spelling -> rows (excluding the canonical spelling)
    total: int  # rows carrying this value after the merge


class CleaningStep(BaseModel):
    id: str
    table: str
    kind: StepKind
    impact: Impact
    category: str
    title: str
    description: str
    columns: list[str]
    rows_affected: int
    affected_pct: float
    status: StepStatus = "pending"
    strategy: NullStrategy | None = None
    strategies: list[NullStrategy] = []
    merges: list[ValueMerge] = []
    types: dict[str, str] = {}  # column -> detected type (cast_numeric / set_types)
    # Median for fill_median, in the column's text scale (5 for "5%"), computed after de-duplication.
    fill_value: float | None = None


class TableCleaning(BaseModel):
    name: str
    source: str
    rows_before: int
    rows_after: int
    accepted: int
    m_script: str


class CleaningPlan(BaseModel):
    steps: list[CleaningStep]
    tables: list[TableCleaning]
    accepted: int
    total: int
    score_before: int
    score_after: int
    rows_before: int
    rows_after: int


class DiffCell(BaseModel):
    before: str | None
    after: str | None
    changed: bool


class DiffRow(BaseModel):
    row: int  # 1-based data row in the source file
    status: Literal["transformed", "unchanged", "duplicate", "removed"]
    cells: list[DiffCell]


class DiffPreview(BaseModel):
    table: str
    columns: list[str]
    changed_columns: list[str]
    rows: list[DiffRow]
    transformed_rows: int
    dropped_rows: int
    accepted_steps: int


class Decision(BaseModel):
    step_id: str
    status: StepStatus | None = None
    strategy: NullStrategy | None = None


@dataclass
class SourceTable:
    """One uploaded table plus what the M source step needs to read it again."""

    name: str
    filename: str
    sheet: str | None
    delimiter: str
    df: pd.DataFrame


# --- suggestions --------------------------------------------------------------------

def _pct(n: int, rows: int) -> float:
    return round(n / rows * 100, 2) if rows else 0.0


def _rows(n: int) -> str:
    return f"{n:,} {'row' if n == 1 else 'rows'}"


def _merges(values: pd.Series) -> list[ValueMerge]:
    """Group spellings that only differ by case/spacing; the most frequent spelling wins."""
    counts = values.dropna().astype(str).value_counts()
    keys = counts.index.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    merges = []
    for _, group in counts.groupby(keys, sort=False):
        if len(group) < 2:
            continue
        canonical = str(group.idxmax())
        variants = {str(k): int(v) for k, v in group.items() if k != canonical}
        merges.append(ValueMerge(canonical=canonical, variants=variants, total=int(group.sum())))
    return sorted(merges, key=lambda m: -sum(m.variants.values()))


def _median(col: ColumnProfile, df: pd.DataFrame) -> float | None:
    numbers = _to_number(df.drop_duplicates()[col.name].dropna().astype(str)).dropna()
    if numbers.empty:
        return None
    median = float(numbers.median())
    return float(round(median)) if col.detected_type == "integer" else round(median, 2)


def _number_text(value: float) -> str:
    return np.format_float_positional(value, trim="-")


def _null_options(col: ColumnProfile) -> tuple[NullStrategy, list[NullStrategy]]:
    if col.role in ("primary_key", "identifier"):
        return "remove_rows", ["remove_rows", "flag"]
    if col.detected_type in NUMERIC_TYPES:
        # Filling money with a median would invent revenue, so amounts default to blanks.
        default = "flag" if col.detected_type == "currency" else "fill_median"
        return default, ["fill_median", "remove_rows", "flag"]
    if col.detected_type in ("date", "datetime", "boolean"):
        return "flag", ["remove_rows", "flag"]
    return "fill_unknown", ["fill_unknown", "remove_rows", "flag"]


def _null_text(col: ColumnProfile, strategy: NullStrategy, rows: int, median: float | None) -> tuple[str, str]:
    n = col.null_count
    share = f"{_pct(n, rows):g}%"
    if strategy == "fill_median":
        shown = _number_text(median or 0.0) + ("%" if col.detected_type == "percentage" else "")
        return (
            f"Fill {share} missing {col.name} with median ({shown})",
            f"{n:,} blank values in {col.name}. The median keeps averages stable without being pulled by outliers.",
        )
    if strategy == "fill_unknown":
        return (
            f"Label {share} missing {col.name} as '{UNKNOWN}'",
            f"{n:,} blank values in {col.name}. An explicit '{UNKNOWN}' member keeps these rows visible in slicers and visuals.",
        )
    if strategy == "remove_rows":
        return (
            f"Remove {_rows(n)} with missing {col.name}",
            f"{n:,} rows have no {col.name}. Rows without this value cannot be identified or related reliably.",
        )
    return (
        f"Flag {share} missing {col.name}",
        f"{n:,} blank values in {col.name} are kept as blanks, and a {col.name}_is_missing column marks them for filtering.",
    )


def suggest_steps(table: TableProfile, df: pd.DataFrame) -> list[CleaningStep]:
    """Rule-based cleaning suggestions for one profiled table (status defaults to pending)."""
    rows = table.rows
    steps: list[CleaningStep] = []
    cols = table.column_profiles

    if table.duplicate_rows:
        has_key = any(c.role == "primary_key" for c in cols)
        measure = next((c.name for c in cols if c.role == "measure"), None)
        effect = f"prevents double-counting {measure} in DAX sums" if measure else "keeps counts and relationships accurate"
        steps.append(CleaningStep(
            id=f"{table.name}::dedupe", table=table.name, kind="remove_duplicates", impact="High",
            category="Star Schema Key" if has_key else "Duplicate Rows",
            title=f"Remove {table.duplicate_rows:,} duplicate {'record' if table.duplicate_rows == 1 else 'records'}",
            description=f"{_rows(table.duplicate_rows)} are exact copies of an earlier row. Removing them {effect}.",
            columns=[c.name for c in cols], rows_affected=table.duplicate_rows,
            affected_pct=_pct(table.duplicate_rows, rows),
        ))

    for col in cols:
        if not col.inconsistent_values:
            continue
        merges = _merges(df[col.name])
        if not merges:
            continue
        changed = sum(sum(m.variants.values()) for m in merges)
        first = merges[0]
        variants = ", ".join(f"'{v}'" for v in first.variants)
        title = (
            f"Standardise {col.name}: {variants} → '{first.canonical}'"
            if len(merges) == 1
            else f"Standardise {len(merges)} spelling groups in {col.name}"
        )
        steps.append(CleaningStep(
            id=f"{table.name}::{col.name}::standardise", table=table.name, kind="standardise_categories",
            impact="Medium", category="Categorical Normalization", title=title,
            description=(
                f"{sum(len(m.variants) for m in merges) + len(merges)} spellings differ only by case or spacing. "
                "Each group is merged into its most frequent spelling so slicers show one member."
            ),
            columns=[col.name], rows_affected=changed, affected_pct=_pct(changed, rows), merges=merges,
        ))

    for col in cols:
        if not col.needs_casting:
            continue
        target = {"currency": "Currency", "percentage": "Percentage"}.get(col.detected_type, "Number")
        non_null = rows - col.null_count
        steps.append(CleaningStep(
            id=f"{table.name}::{col.name}::cast", table=table.name, kind="cast_numeric", impact="High",
            category="Type Casting", title=f"Cast {col.name} from text to {target}",
            description=(
                "Removes currency symbols, % signs and thousands separators, then converts to a number "
                "so DAX can aggregate it."
                + (" Percentages are stored as fractions (5% → 0.05)." if col.detected_type == "percentage" else "")
            ),
            columns=[col.name], rows_affected=non_null, affected_pct=_pct(non_null, rows),
            types={col.name: col.detected_type},
        ))

    typed = {
        c.name: c.detected_type
        for c in cols
        if not c.needs_casting and c.detected_type in ("integer", "decimal", "date", "datetime", "boolean")
    }
    if typed:
        names = ", ".join(typed)
        steps.append(CleaningStep(
            id=f"{table.name}::types", table=table.name, kind="set_types", impact="Medium",
            category="Data Types", title=f"Apply detected data types to {len(typed)} {'column' if len(typed) == 1 else 'columns'}",
            description=f"Sets number, date and true/false types on {names} instead of loading everything as text.",
            columns=list(typed), rows_affected=rows, affected_pct=100.0 if rows else 0.0, types=typed,
        ))

    for col in cols:
        if not col.null_count:
            continue
        default, options = _null_options(col)
        median = _median(col, df) if "fill_median" in options else None
        if median is None and "fill_median" in options:
            options = [o for o in options if o != "fill_median"]
            default = "flag" if default == "fill_median" else default
        title, description = _null_text(col, default, rows, median)
        key = col.role in ("primary_key", "foreign_key", "identifier")
        impact: Impact = "High" if key or col.null_pct >= 10 else "Medium" if col.null_pct >= 1 else "Low"
        steps.append(CleaningStep(
            id=f"{table.name}::{col.name}::nulls", table=table.name, kind="handle_nulls", impact=impact,
            category="Null Handling", title=title, description=description, columns=[col.name],
            rows_affected=col.null_count, affected_pct=col.null_pct, strategy=default, strategies=options,
            fill_value=median, types={col.name: col.detected_type},
        ))
    return steps


def apply_decisions(steps: list[CleaningStep], decisions: dict, tables: dict[str, TableProfile]) -> None:
    """Merge stored accept/skip/strategy choices into freshly generated steps."""
    for step in steps:
        choice = decisions.get(step.id) or {}
        if choice.get("status") in ("pending", "accepted", "skipped"):
            step.status = choice["status"]
        strategy = choice.get("strategy")
        if step.kind == "handle_nulls" and strategy in step.strategies and strategy != step.strategy:
            step.strategy = strategy
            table = tables[step.table]
            col = next(c for c in table.column_profiles if c.name == step.columns[0])
            step.title, step.description = _null_text(col, strategy, table.rows, step.fill_value)


# --- pipeline (pandas + M in one pass) ------------------------------------------------

def m_text(value: str) -> str:
    """M text literal."""
    escaped = value.replace('"', '""').replace("\r", "#(cr)").replace("\n", "#(lf)").replace("\t", "#(tab)")
    return f'"{escaped}"'


def m_name(value: str) -> str:
    """Quoted M identifier, e.g. #"Removed Duplicates"."""
    return "#" + m_text(value)


_M_SYMBOLS = '{"$", "€", "£", "₹", "¥", ",", "%", " ", "(", ")"}'
_M_TYPES = {
    "currency": "Currency.Type",
    "percentage": "Percentage.Type",
    "integer": "Int64.Type",
    "decimal": "type number",
    "date": "type date",
    "datetime": "type datetime",
    "boolean": "type logical",
}


@dataclass
class PipelineResult:
    df: pd.DataFrame  # cleaned rows (index = original row index)
    dropped: dict[int, str] = field(default_factory=dict)  # original index -> "duplicate" | "removed"
    m_script: str = ""


class _M:
    """Accumulates `name = expression` steps of a Power Query let-expression."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    @property
    def last(self) -> str:
        return self.lines[-1][0]

    def add(self, name: str, expression: str) -> None:
        self.lines.append((m_name(name), expression))

    def render(self, header: str) -> str:
        body = ",\n".join(f"    {n} = {e}" for n, e in self.lines)
        return f"{header}\nlet\n{body}\nin\n    {self.last}"


def _source_steps(m: _M, src: SourceTable) -> None:
    path = f"DataFolder & {m_text(src.filename)}"
    if src.filename.lower().endswith(".csv"):
        m.add("Source", f"Csv.Document(File.Contents({path}), [Delimiter={m_text(src.delimiter)}, Encoding=65001, QuoteStyle=QuoteStyle.Csv])")
        m.add("Promoted Headers", f"Table.PromoteHeaders({m.last}, [PromoteAllScalars=true])")
    else:
        m.add("Source", f"Excel.Workbook(File.Contents({path}), null, true)")
        m.add("Sheet", f"{m.last}{{[Item={m_text(src.sheet or '')}, Kind=\"Sheet\"]}}[Data]")
        m.add("Promoted Headers", f"Table.PromoteHeaders({m.last}, [PromoteAllScalars=true])")
    # Mirrors core/upload.py: trimmed text, blanks as nulls, empty rows dropped.
    prev = m.last
    m.add("Trimmed Text", f"Table.TransformColumns({prev}, List.Transform(Table.ColumnNames({prev}), (c) => {{c, each if _ is text then Text.Trim(_) else _}}))")
    prev = m.last
    m.add("Blanks As Null", f'Table.ReplaceValue({prev}, "", null, Replacer.ReplaceValue, Table.ColumnNames({prev}))')
    m.add("Removed Empty Rows", f"Table.SelectRows({m.last}, each List.NonNullCount(Record.FieldValues(_)) > 0)")


def _number_m(kind: str) -> str:
    parsed = f'(if Text.StartsWith(_, "(") then -1 else 1) * Number.From(Text.Remove(_, {_M_SYMBOLS}), "en-US")'
    return f"{parsed} / 100" if kind == "percentage" else parsed


def _to_numeric(values: pd.Series, kind: str) -> pd.Series:
    numbers = _to_number(values.astype("string").fillna("").astype(str))
    numbers[values.isna()] = np.nan
    return numbers / 100 if kind == "percentage" else numbers


def run_pipeline(src: SourceTable, steps: list[CleaningStep]) -> PipelineResult:
    """Apply the given steps (in KIND_ORDER) to a copy of the table, building the M script alongside."""
    df = src.df.copy()
    dropped: dict[int, str] = {}
    numeric_cols: set[str] = set()
    m = _M()
    _source_steps(m, src)

    def drop(mask: pd.Series, reason: str) -> pd.DataFrame:
        for idx in df.index[mask]:
            dropped[int(idx)] = reason
        return df[~mask]

    for step in sorted(steps, key=lambda s: KIND_ORDER.index(s.kind)):
        if step.kind == "remove_duplicates":
            df = drop(df.duplicated(), "duplicate")
            m.add("Removed Duplicates", f"Table.Distinct({m.last})")

        elif step.kind == "standardise_categories":
            col = step.columns[0]
            mapping = {v: merge.canonical for merge in step.merges for v in merge.variants}
            df[col] = df[col].replace(mapping)
            record = ", ".join(f"{m_name(k)} = {m_text(v)}" for k, v in mapping.items())
            m.add(f"Standardised {col}", (
                f"Table.TransformColumns({m.last}, {{{{{m_text(col)}, "
                f"each if _ is text then Record.FieldOrDefault([{record}], _, _) else _, type text}}}})"
            ))

        elif step.kind == "cast_numeric":
            col, kind = next(iter(step.types.items()))
            df[col] = _to_numeric(df[col], kind)
            numeric_cols.add(col)
            m.add(f"Cast {col}", (
                f"Table.TransformColumns({m.last}, {{{{{m_text(col)}, "
                f"each if _ is text then {_number_m(kind)} else _, {_M_TYPES[kind]}}}}})"
            ))

        elif step.kind == "set_types":
            plain = {c: t for c, t in step.types.items() if t != "boolean"}
            bools = [c for c, t in step.types.items() if t == "boolean"]
            for col, kind in plain.items():
                if kind in ("integer", "decimal"):
                    df[col] = _to_numeric(df[col], kind)
                    numeric_cols.add(col)
                else:
                    parsed = _to_datetime(df[col].astype("string").fillna("").astype(str))
                    df[col] = parsed.dt.normalize() if kind == "date" else parsed
            if plain:
                pairs = ", ".join(f"{{{m_text(c)}, {_M_TYPES[t]}}}" for c, t in plain.items())
                m.add("Changed Types", f'Table.TransformColumnTypes({m.last}, {{{pairs}}}, "en-US")')
            for col in bools:
                df[col] = df[col].map(lambda v: pd.NA if pd.isna(v) else str(v).lower() in _TRUE_VALUES).astype("boolean")
            if bools:
                truthy = ", ".join(m_text(v) for v in _TRUE_VALUES)
                pairs = ", ".join(
                    f"{{{m_text(c)}, each if _ is text then List.Contains({{{truthy}}}, Text.Lower(_)) else _, type logical}}"
                    for c in bools
                )
                m.add("Parsed Booleans", f"Table.TransformColumns({m.last}, {{{pairs}}})")

        elif step.kind == "handle_nulls":
            col = step.columns[0]
            missing = df[col].isna()
            field_ref = f"Record.Field(_, {m_text(col)})"
            if step.strategy == "remove_rows":
                df = drop(missing, "removed")
                m.add(f"Removed Missing {col}", f"Table.SelectRows({m.last}, each {field_ref} <> null)")
            elif step.strategy == "flag":
                df[f"{col}_is_missing"] = missing
                m.add(f"Flagged Missing {col}", f"Table.AddColumn({m.last}, {m_text(col + '_is_missing')}, each {field_ref} = null, type logical)")
            elif step.strategy == "fill_unknown":
                df[col] = df[col].astype("object").where(~missing, UNKNOWN)
                m.add(f"Filled {col}", f"Table.ReplaceValue({m.last}, null, {m_text(UNKNOWN)}, Replacer.ReplaceValue, {{{m_text(col)}}})")
            else:  # fill_median: a number once the column is cast/typed, else text like the raw values
                kind = step.types.get(col)
                median = step.fill_value or 0.0
                if col in numeric_cols:
                    value = median / 100 if kind == "percentage" else median
                    df[col] = df[col].where(~missing, value)
                    literal = _number_text(value)
                else:
                    text = _number_text(median) + ("%" if kind == "percentage" else "")
                    df[col] = df[col].where(~missing, text)
                    literal = m_text(text)
                m.add(f"Filled {col}", f"Table.ReplaceValue({m.last}, null, {literal}, Replacer.ReplaceValue, {{{m_text(col)}}})")

    header = (
        f"// {src.name} - generated by DashPilot. DataFolder is a text parameter with the folder\n"
        "// that holds the source files (ending in a backslash)."
    )
    return PipelineResult(df=df, dropped=dropped, m_script=m.render(header))


# --- plan -----------------------------------------------------------------------------

def _score_after(table: TableProfile, result: PipelineResult, accepted: list[CleaningStep]) -> int:
    """Same formula as profiling._table_score, applied to the cleaned table."""
    df = result.df
    cells = df.size or 1
    completeness = 1 - df.isna().sum().sum() / cells
    uniqueness = 1 - df.astype("string").duplicated().sum() / max(len(df), 1)
    fixed = {(s.kind, c) for s in accepted for c in s.columns}
    clean = sum(
        1 for c in table.column_profiles
        if (not c.needs_casting or ("cast_numeric", c.name) in fixed)
        and (not c.inconsistent_values or ("standardise_categories", c.name) in fixed)
    )
    validity = clean / max(len(table.column_profiles), 1)
    return round(100 * (0.5 * completeness + 0.3 * uniqueness + 0.2 * validity))


def build_plan(report: QualityReport, sources: list[SourceTable], decisions: dict) -> CleaningPlan:
    profiles = {t.name: t for t in report.tables}
    steps: list[CleaningStep] = []
    tables: list[TableCleaning] = []
    weighted_after = 0.0
    for src in sources:
        profile = profiles.get(src.name)
        if profile is None:
            continue
        table_steps = suggest_steps(profile, src.df)
        apply_decisions(table_steps, decisions, profiles)
        accepted = [s for s in table_steps if s.status == "accepted"]
        result = run_pipeline(src, accepted)
        weighted_after += _score_after(profile, result, accepted) * max(profile.rows, 1)
        steps.extend(table_steps)
        tables.append(TableCleaning(
            name=src.name, source=src.filename + (f" › {src.sheet}" if src.sheet else ""),
            rows_before=profile.rows, rows_after=len(result.df), accepted=len(accepted), m_script=result.m_script,
        ))

    weight = sum(max(profiles[t.name].rows, 1) for t in tables)
    return CleaningPlan(
        steps=steps,
        tables=tables,
        accepted=sum(1 for s in steps if s.status == "accepted"),
        total=len(steps),
        score_before=report.score,
        score_after=round(weighted_after / weight) if weight else report.score,
        rows_before=sum(t.rows_before for t in tables),
        rows_after=sum(t.rows_after for t in tables),
    )


# --- before/after preview -------------------------------------------------------------

def _display(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (bool, np.bool_)):
        return "TRUE" if value else "FALSE"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d") if value == value.normalize() else value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, (float, np.floating)):
        return np.format_float_positional(float(value), trim="-")
    return str(value)


def preview(src: SourceTable, steps: list[CleaningStep], key_column: str | None, limit: int = 8) -> DiffPreview:
    """Before/after sample rows for the accepted steps of one table."""
    accepted = [s for s in steps if s.status == "accepted"]
    result = run_pipeline(src, accepted)
    before = src.df
    after = result.df.reindex(before.index)
    kept = ~before.index.isin(list(result.dropped))

    shared = [c for c in before.columns if c in after.columns]
    # astype(object) + where: DataFrame.map turns None into NaN in all-empty columns.
    before_text = before[shared].map(_display).astype(object)
    before_text = before_text.where(before_text.notna(), None)
    after_text = after[shared].map(_display).astype(object)
    after_text = after_text.where(after_text.notna(), None)
    # A pure type change ("13:29" -> "13:29:00", "Yes" -> TRUE) is not a value fix; showing it
    # would mark every row as transformed and hide the spelling/casting/blank fixes.
    value_fixed = {
        c
        for s in accepted
        if s.kind in ("standardise_categories", "cast_numeric") or (s.kind == "handle_nulls" and s.strategy != "flag")
        for c in s.columns
    }
    type_only = {c for s in accepted if s.kind == "set_types" for c in s.columns} - value_fixed
    for col in type_only:
        after_text[col] = before_text[col]
    diff = (before_text != after_text) & ~(before_text.isna() & after_text.isna())
    diff = diff[kept]
    counts = diff.sum()
    changed_columns = [str(c) for c, n in counts.sort_values(ascending=False).items() if n > 0]

    key = key_column if key_column in shared else str(shared[0])
    shown = [key] + [c for c in changed_columns if c != key][:4]
    if len(shown) < 3:
        shown += [c for c in shared if c not in shown][: 3 - len(shown)]

    transformed_idx = list(diff.index[diff.any(axis=1)])
    transformed_set = set(transformed_idx)
    dropped_idx = list(result.dropped)
    unchanged_idx = [i for i in before.index[kept] if i not in transformed_set]
    # Prefer rows that show different changed columns, then dropped rows, then a little context.
    picked: list[int] = []
    seen_cols: set[str] = set()
    for idx in transformed_idx:
        cols = {c for c in shown if diff.at[idx, c]}
        if cols - seen_cols:
            picked.append(idx)
            seen_cols |= cols
        if len(picked) >= 3:
            break
    for idx in transformed_idx:
        if len(picked) >= 4:
            break
        if idx not in picked:
            picked.append(idx)
    by_reason = {"duplicate": [i for i in dropped_idx if result.dropped[i] == "duplicate"],
                 "removed": [i for i in dropped_idx if result.dropped[i] == "removed"]}
    picked += by_reason["duplicate"][:2] + by_reason["removed"][:1]
    picked += unchanged_idx[: max(1, limit - len(picked))]
    # Tables where every row changes have no unchanged rows to fill the sample with.
    picked += [i for i in transformed_idx[:limit] if i not in picked][: max(0, limit - len(picked))]
    picked = sorted(set(picked[:limit]))

    rows = []
    for idx in picked:
        reason = result.dropped.get(int(idx))
        cells = []
        for c in shown:
            b = before_text.at[idx, c]
            a = None if reason else after_text.at[idx, c]
            cells.append(DiffCell(before=b, after=a, changed=bool(reason) or b != a))
        status = reason or ("transformed" if idx in transformed_set else "unchanged")
        rows.append(DiffRow(row=int(before.index.get_loc(idx)) + 1, status=status, cells=cells))

    return DiffPreview(
        table=src.name, columns=shown, changed_columns=changed_columns, rows=rows,
        transformed_rows=len(transformed_idx), dropped_rows=len(dropped_idx), accepted_steps=len(accepted),
    )

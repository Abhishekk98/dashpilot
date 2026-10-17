"""Cleaning pipeline: applies accepted steps in pandas (preview) and as Power Query M. (Spec Module 3)

Each accepted step is applied twice from one pass over the table (`run_pipeline`): in pandas for
the before/after preview, and as Power Query M so the cleaning happens inside Power BI and keeps
working on refresh. Suggestions themselves come from core/cleaning_rules.py.

Robustness rules:
- every M value transform is error-proof (`try ... otherwise null`), so a bad cell becomes a blank
  instead of a refresh error;
- every step runs isolated: if one fails, its changes are rolled back, the step gets an `error`
  and the rest of the pipeline continues.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel

from core.profiling import _to_datetime, _to_number
from core.upload import NULL_TOKENS

StepKind = Literal[
    "remove_total_rows", "clean_whitespace", "remove_duplicates", "standardise_categories", "merge_synonyms",
    "normalise_booleans", "cast_numeric", "cast_european", "date_format", "set_types", "excel_serial_dates",
    "date_outliers", "sentinel_values", "dedupe_key", "orphan_keys", "handle_nulls", "unknown_member",
]
StepStatus = Literal["pending", "accepted", "skipped"]
Impact = Literal["High", "Medium", "Low"]

# Steps always run in this order, in pandas and in M alike.
KIND_ORDER: list[str] = list(StepKind.__args__)  # type: ignore[attr-defined]
NUMERIC_TYPES = ("currency", "percentage", "integer", "decimal")
UNKNOWN = "Unknown"
TRUE_VALUES = ("true", "yes", "y", "t", "1", "on")
FALSE_VALUES = ("false", "no", "n", "f", "0", "off")
TOTAL_WORDS = ("total", "totals", "grand total", "subtotal", "sub total", "sub-total", "overall total")
ZERO_WIDTH = ("\u200b", "\u200c", "\u200d", "\ufeff")


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
    strategy: str | None = None
    strategies: list[str] = []
    # Title + description per strategy, so switching strategy re-labels the card.
    strategy_text: dict[str, list[str]] = {}
    merges: list[ValueMerge] = []
    types: dict[str, str] = {}  # column -> resulting detected type (steps that convert columns)
    params: dict[str, Any] = {}
    # Median for fill_median, in the column's text scale (5 for "5%"), computed after de-duplication.
    fill_value: float | None = None
    source: Literal["rules", "ai"] = "rules"
    error: str | None = None  # set when the step could not be applied (it was skipped)


class TableCleaning(BaseModel):
    name: str
    source: str
    rows_before: int
    rows_after: int
    accepted: int
    m_script: str
    structure_notes: list[str] = []


class CleaningPlan(BaseModel):
    steps: list[CleaningStep]
    tables: list[TableCleaning]
    accepted: int
    total: int
    score_before: int
    score_after: int
    rows_before: int
    rows_after: int
    warnings: list[str] = []
    ai_synonyms: Literal["off", "available", "done", "failed"] = "off"
    ai_note: str | None = None


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
    strategy: str | None = None


@dataclass
class SourceTable:
    """One uploaded table plus what the M source step needs to read it again."""

    name: str
    filename: str
    sheet: str | None
    delimiter: str
    df: pd.DataFrame

    @property
    def structure(self) -> dict:
        return self.df.attrs.get("structure") or {}


@dataclass
class PipelineResult:
    df: pd.DataFrame  # cleaned rows (index = original row index; appended rows get new indices)
    dropped: dict[int, str] = field(default_factory=dict)  # original index -> "duplicate" | "removed"
    m_script: str = ""
    warnings: list[str] = field(default_factory=list)


class SkipStep(Exception):
    """A step that does not apply in the current state (e.g. filling text into a number column)."""


# --- M helpers ----------------------------------------------------------------------

def m_text(value: str) -> str:
    """M text literal."""
    escaped = str(value).replace('"', '""').replace("\r", "#(cr)").replace("\n", "#(lf)").replace("\t", "#(tab)")
    return f'"{escaped}"'


def m_name(value: str) -> str:
    """Quoted M identifier, e.g. #"Removed Duplicates"."""
    return "#" + m_text(value)


def m_list(values) -> str:
    return "{" + ", ".join(m_text(v) for v in values) + "}"


def m_number(value: float) -> str:
    return np.format_float_positional(float(value), trim="-")


def m_datetime(iso: str) -> str:
    t = pd.Timestamp(iso)
    return f"#datetime({t.year}, {t.month}, {t.day}, {t.hour}, {t.minute}, {t.second})"


_M_TYPES = {
    "currency": "Currency.Type", "percentage": "Percentage.Type", "integer": "Int64.Type", "decimal": "type number",
    "date": "type date", "datetime": "type datetime", "boolean": "type logical",
}

# Shared M functions, added to a query once, only when a step needs them.
_M_FUNCTIONS = {
    "fnNumber": (
        '(v) => if v = null then null else if v is number then v else let t0 = Text.Trim(Text.From(v)), '
        'neg = Text.StartsWith(t0, "(") and Text.EndsWith(t0, ")"), '
        't = Text.Remove(t0, {"$", "€", "£", "₹", "¥", ",", " ", "(", ")", "%"}), '
        'n = try Number.From(t, "en-US") otherwise null in if n = null then null else if neg then -n else n'
    ),
    "fnDateTime": (
        "(v, culture as text) => if v = null then null else if v is datetime then v "
        "else if v is date then DateTime.From(v) else if v is number then null "
        "else try DateTime.From(Text.From(v), culture) otherwise null"
    ),
    "fnBool": (
        f"(v) => if v = null then null else if v is logical then v else let t = Text.Lower(Text.Trim(Text.From(v))) in "
        f"if List.Contains({m_list(TRUE_VALUES)}, t) then true else if List.Contains({m_list(FALSE_VALUES)}, t) then false else null"
    ),
}


class _M:
    """Accumulates `name = expression` steps of a Power Query let-expression."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []
        self.last = ""  # last *table* step (helpers do not change it)
        self.functions: set[str] = set()

    def add(self, name: str, expression: str) -> None:
        ident = m_name(name)
        n = 2
        while any(ident == existing for existing, _ in self.lines):
            ident = m_name(f"{name} ({n})")
            n += 1
        self.lines.append((ident, expression))
        self.last = ident

    def helper(self, name: str, expression: str) -> str:
        ident = m_name(name)
        if not any(ident == existing for existing, _ in self.lines):
            self.lines.append((ident, expression))
        return ident

    def fn(self, name: str) -> str:
        return self.helper(name, _M_FUNCTIONS[name])

    def snapshot(self) -> tuple[int, str, set[str]]:
        return len(self.lines), self.last, set(self.functions)

    def restore(self, snap: tuple[int, str, set[str]]) -> None:
        del self.lines[snap[0]:]
        self.last, self.functions = snap[1], snap[2]

    def render(self, header: str) -> str:
        body = ",\n".join(f"    {n} = {e}" for n, e in self.lines)
        return f"{header}\nlet\n{body}\nin\n    {self.last}"


def _source_steps(m: _M, src: SourceTable) -> None:
    s = src.structure
    path = f"DataFolder & {m_text(src.filename)}"
    if src.filename.lower().endswith(".csv"):
        code_page = {"utf-8-sig": 65001, "cp1252": 1252, "latin-1": 28591}.get(s.get("encoding") or "utf-8-sig", 65001)
        columns = f"Columns={s['columns']}, " if s.get("columns") else ""
        m.add("Source", f"Csv.Document(File.Contents({path}), [Delimiter={m_text(src.delimiter)}, {columns}Encoding={code_page}, QuoteStyle=QuoteStyle.Csv])")
    else:
        m.add("Source", f"Excel.Workbook(File.Contents({path}), null, true)")
        m.add("Sheet", f"{m.last}{{[Item={m_text(src.sheet or '')}, Kind=\"Sheet\"]}}[Data]")
    if s.get("header_row"):
        m.add("Skipped Title Rows", f"Table.Skip({m.last}, {s['header_row']})")
    m.add("Promoted Headers", f"Table.PromoteHeaders({m.last}, [PromoteAllScalars=true])")
    if s.get("names"):
        # Positional rename to the names DashPilot profiled (blank / repeated headers fixed).
        prev = m.last
        m.add("Renamed Columns", (
            f"if Table.ColumnCount({prev}) = {len(s['names'])} then "
            f"Table.RenameColumns({prev}, List.Zip({{Table.ColumnNames({prev}), {m_list(s['names'])}}})) else {prev}"
        ))
    if s.get("dropped_columns"):
        m.add("Removed Empty Columns", f"Table.RemoveColumns({m.last}, {m_list(s['dropped_columns'])}, MissingField.Ignore)")
    # Mirrors core/upload.py: trimmed text, blanks and null tokens as nulls, empty rows dropped.
    prev = m.last
    m.add("Trimmed Text", f"Table.TransformColumns({prev}, List.Transform(Table.ColumnNames({prev}), (c) => {{c, each if _ is text then Text.Trim(_) else _}}))")
    prev = m.last
    m.add("Blanks As Null", (
        f"Table.TransformColumns({prev}, List.Transform(Table.ColumnNames({prev}), (c) => {{c, each if _ is text and "
        f'(_ = "" or List.Contains({m_list(NULL_TOKENS)}, Text.Upper(_))) then null else _}}))'
    ))
    m.add("Removed Empty Rows", f"Table.SelectRows({m.last}, each List.NonNullCount(Record.FieldValues(_)) > 0)")


# --- pandas helpers -------------------------------------------------------------------

def _text(values: pd.Series) -> pd.Series:
    return values.astype("string")


def to_numbers(values: pd.Series) -> pd.Series:
    """Numbers from text like "$1,234.50" / "(5)" or from numeric values; NaN when not numeric."""
    if pd.api.types.is_bool_dtype(values) or pd.api.types.is_datetime64_any_dtype(values):
        return pd.Series(np.nan, index=values.index, dtype="float64")
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_numeric(values, errors="coerce").astype("float64")
    numbers = _to_number(_text(values).fillna("").astype(str))
    numbers[values.isna().to_numpy()] = np.nan
    return numbers.astype("float64")


def to_datetimes(values: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(values):
        return values
    out = _to_datetime(_text(values).fillna("").astype(str))
    out[values.isna().to_numpy()] = pd.NaT
    return out


def to_bools(values: pd.Series) -> pd.Series:
    def one(v):
        if v is None or v is pd.NA or (isinstance(v, float) and np.isnan(v)):
            return pd.NA
        if isinstance(v, (bool, np.bool_)):
            return bool(v)
        t = str(v).strip().lower()
        return True if t in TRUE_VALUES else False if t in FALSE_VALUES else pd.NA
    return values.map(one).astype("boolean")


_DMY = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})(.*)$")


def parse_day_month(values: pd.Series, day_first: bool) -> pd.Series:
    """Parse a/b/yyyy dates with an explicit day/month order; other strings use the default parser."""
    def iso(v):
        if v is None or v is pd.NA:
            return v
        m = _DMY.match(str(v).strip())
        if not m:
            return v
        a, b, y, rest = m.groups()
        day, month = (a, b) if day_first else (b, a)
        year = int(y) if len(y) == 4 else (2000 + int(y) if int(y) < 50 else 1900 + int(y))
        return f"{year:04d}-{int(month):02d}-{int(day):02d}{rest}"
    return to_datetimes(_text(values).map(iso))


def new_column(df: pd.DataFrame, base: str) -> str:
    """Unique column name for an added flag column (case-insensitive, like Power BI)."""
    existing = {str(c).lower() for c in df.columns}
    name, n = base, 2
    while name.lower() in existing:
        name, n = f"{base}_{n}", n + 1
    return name


# --- pipeline -------------------------------------------------------------------------

@dataclass
class _Ctx:
    src: SourceTable
    df: pd.DataFrame
    m: _M
    dropped: dict[int, str]
    converted: dict[str, str]  # column -> "number" | "date" | "datetime" | "bool"
    cultures: dict[str, str]  # column -> culture used to parse its dates
    lookups: dict[tuple[str, str], set[str]]  # (table, column) -> key values, for orphan checks

    def drop(self, mask: pd.Series, reason: str) -> None:
        flags = mask.fillna(False).astype(bool).to_numpy()
        for idx in self.df.index[flags]:
            self.dropped[int(idx)] = reason
        self.df = self.df[~flags]

    def m_type(self, col: str) -> str:
        return {"number": "type number", "date": "type date", "datetime": "type datetime", "bool": "type logical"}.get(
            self.converted.get(col, ""), "type any"
        )


def _transform(ctx: _Ctx, step_name: str, col: str, body: str, m_type: str | None = None) -> None:
    ctx.m.add(step_name, f"Table.TransformColumns({ctx.m.last}, {{{{{m_text(col)}, each {body}, {m_type or ctx.m_type(col)}}}}})")


def _op_remove_total_rows(ctx: _Ctx, step: CleaningStep) -> None:
    col = step.params["column"]
    norm = _text(ctx.df[col]).str.strip().str.lower().str.rstrip(":")
    ctx.drop(norm.isin(TOTAL_WORDS).fillna(False), "removed")
    ctx.m.add(f"Removed Total Rows", (
        f"Table.SelectRows({ctx.m.last}, each let v = Record.Field(_, {m_text(col)}) in not (v is text and "
        f'List.Contains({m_list(TOTAL_WORDS)}, Text.TrimEnd(Text.Lower(Text.Trim(v)), ":"))))'
    ))


def _clean_ws(v):
    if v is None or v is pd.NA:
        return v
    t = str(v).replace("\u00a0", " ")
    for z in ZERO_WIDTH:
        t = t.replace(z, "")
    t = " ".join(p for p in t.split(" ") if p)
    return t or pd.NA


def _op_clean_whitespace(ctx: _Ctx, step: CleaningStep) -> None:
    zero = m_list(ZERO_WIDTH)
    for col in step.columns:
        ctx.df[col] = _text(ctx.df[col]).map(_clean_ws).astype("string")
        _transform(ctx, f"Cleaned Spaces {col}", col, (
            f'if _ is text then let t = Text.Combine(List.Select(Text.Split(Text.Remove(Text.Replace(_, "#(00A0)", " "), {zero}), " "), '
            f'each _ <> ""), " ") in if t = "" then null else t else _'
        ))


def _op_remove_duplicates(ctx: _Ctx, step: CleaningStep) -> None:
    ctx.drop(ctx.df.duplicated(), "duplicate")
    ctx.m.add("Removed Duplicates", f"Table.Distinct({ctx.m.last})")


def _op_standardise(ctx: _Ctx, step: CleaningStep) -> None:
    col = step.columns[0]
    mapping = {v: merge.canonical for merge in step.merges for v in merge.variants}
    ctx.df[col] = ctx.df[col].replace(mapping)
    record = ", ".join(f"{m_name(k)} = {m_text(v)}" for k, v in mapping.items())
    _transform(ctx, f"Standardised {col}", col, f"if _ is text then Record.FieldOrDefault([{record}], _, _) else _")


def _op_merge_synonyms(ctx: _Ctx, step: CleaningStep) -> None:
    col = step.columns[0]
    mapping: dict[str, str] = step.params["mapping"]  # lower-cased spelling -> canonical
    ctx.df[col] = _text(ctx.df[col]).map(lambda v: v if v is pd.NA else mapping.get(str(v).strip().lower(), v)).astype("string")
    record = ", ".join(f"{m_name(k)} = {m_text(v)}" for k, v in mapping.items())
    _transform(ctx, f"Merged Synonyms {col}", col, f"if _ is text then Record.FieldOrDefault([{record}], Text.Lower(Text.Trim(_)), _) else _")


def _op_normalise_booleans(ctx: _Ctx, step: CleaningStep) -> None:
    fn = ctx.m.fn("fnBool")
    for col in step.columns:
        ctx.df[col] = to_bools(ctx.df[col])
        ctx.converted[col] = "bool"
        _transform(ctx, f"True False {col}", col, f"{fn}(_)")


def _op_cast_numeric(ctx: _Ctx, step: CleaningStep) -> None:
    col, kind = next(iter(step.types.items()))
    numbers = to_numbers(ctx.df[col])
    ctx.df[col] = numbers / 100 if kind == "percentage" else numbers
    ctx.converted[col] = "number"
    fn = ctx.m.fn("fnNumber")
    body = f"let n = {fn}(_) in if n = null then null else n / 100" if kind == "percentage" else f"{fn}(_)"
    _transform(ctx, f"Cast {col}", col, body, _M_TYPES[kind])


def _op_cast_european(ctx: _Ctx, step: CleaningStep) -> None:
    col = step.columns[0]
    text = _text(ctx.df[col]).str.replace(".", "", regex=False).str.replace(" ", "", regex=False).str.replace(",", ".", regex=False)
    ctx.df[col] = pd.to_numeric(text, errors="coerce").astype("float64")
    ctx.converted[col] = "number"
    _transform(ctx, f"Cast European {col}", col, 'if _ is number then _ else try Number.From(Text.From(_), "de-DE") otherwise null', "type number")


def _date_body(ctx: _Ctx, col: str, kind: str, parse: str) -> tuple[str, str]:
    if kind == "date":
        return f"let d = {parse} in if d = null then null else DateTime.Date(d)", "type date"
    return parse, "type datetime"


def _op_date_format(ctx: _Ctx, step: CleaningStep) -> None:
    col, kind = next(iter(step.types.items()))
    day_first = step.strategy == "day_first"
    parsed = parse_day_month(ctx.df[col], day_first)
    ctx.df[col] = parsed.dt.normalize() if kind == "date" else parsed
    culture = "en-GB" if day_first else "en-US"
    ctx.converted[col], ctx.cultures[col] = kind, culture
    body, m_type = _date_body(ctx, col, kind, f"{ctx.m.fn('fnDateTime')}(_, {m_text(culture)})")
    _transform(ctx, f"Parsed Dates {col}", col, body, m_type)


def _op_set_types(ctx: _Ctx, step: CleaningStep) -> None:
    for col, kind in step.types.items():
        if col not in ctx.df.columns:
            continue
        if kind in ("integer", "decimal"):
            ctx.df[col] = to_numbers(ctx.df[col])
            ctx.converted[col] = "number"
            _transform(ctx, f"Typed {col}", col, f"{ctx.m.fn('fnNumber')}(_)", _M_TYPES[kind])
        elif kind in ("date", "datetime"):
            parsed = to_datetimes(ctx.df[col])
            ctx.df[col] = parsed.dt.normalize() if kind == "date" else parsed
            ctx.converted[col] = kind
            culture = ctx.cultures.get(col, "en-US")
            body, m_type = _date_body(ctx, col, kind, f"{ctx.m.fn('fnDateTime')}(_, {m_text(culture)})")
            _transform(ctx, f"Typed {col}", col, body, m_type)
        elif kind == "boolean":
            ctx.df[col] = to_bools(ctx.df[col])
            ctx.converted[col] = "bool"
            _transform(ctx, f"Typed {col}", col, f"{ctx.m.fn('fnBool')}(_)", "type logical")


def _op_excel_serial_dates(ctx: _Ctx, step: CleaningStep) -> None:
    col, kind = next(iter(step.types.items()))
    numbers = to_numbers(ctx.df[col])
    numbers = numbers.where((numbers > 0) & (numbers < 2958466))  # Excel's valid serial range
    parsed = pd.to_datetime(numbers, unit="D", origin="1899-12-30", errors="coerce")
    ctx.df[col] = parsed.dt.normalize() if kind == "date" else parsed
    ctx.converted[col] = kind
    parse = f"let n = {ctx.m.fn('fnNumber')}(_) in if n = null or n <= 0 then null else try DateTime.From(n) otherwise null"
    body, m_type = _date_body(ctx, col, kind, parse)
    _transform(ctx, f"Excel Dates {col}", col, body, m_type)


def _op_date_outliers(ctx: _Ctx, step: CleaningStep) -> None:
    col = step.columns[0]
    low, high = pd.Timestamp(step.params["min"]), pd.Timestamp(step.params["max"])
    dates = to_datetimes(ctx.df[col])
    mask = (dates.notna() & ((dates < low) | (dates > high))).fillna(False)
    parse = f"{ctx.m.fn('fnDateTime')}(_, {m_text(ctx.cultures.get(col, 'en-US'))})"
    test = f"d <> null and (d < {m_datetime(step.params['min'])} or d > {m_datetime(step.params['max'])})"
    if step.strategy == "flag":
        flag = new_column(ctx.df, f"{col}_suspect_date")
        ctx.df[flag] = mask.astype(bool)
        row_parse = parse.replace("(_,", f"(Record.Field(_, {m_text(col)}),")
        ctx.m.add(f"Flagged Dates {col}", f"Table.AddColumn({ctx.m.last}, {m_text(flag)}, each let d = {row_parse} in {test}, type logical)")
    else:
        ctx.df.loc[mask.to_numpy(), col] = pd.NA if not pd.api.types.is_datetime64_any_dtype(ctx.df[col]) else pd.NaT
        _transform(ctx, f"Blanked Dates {col}", col, f"let d = {parse} in if {test} then null else _")


def _op_sentinel_values(ctx: _Ctx, step: CleaningStep) -> None:
    col = step.columns[0]
    values = [float(v) for v in step.params["values"]]
    mask = to_numbers(ctx.df[col]).isin(values).fillna(False)
    listed = "{" + ", ".join(m_number(v) for v in values) + "}"
    fn = ctx.m.fn("fnNumber")
    if step.strategy == "flag":
        flag = new_column(ctx.df, f"{col}_placeholder")
        ctx.df[flag] = mask.astype(bool)
        ctx.m.add(f"Flagged Placeholders {col}", (
            f"Table.AddColumn({ctx.m.last}, {m_text(flag)}, each let n = {fn}(Record.Field(_, {m_text(col)})) in "
            f"n <> null and List.Contains({listed}, n), type logical)"
        ))
    else:
        ctx.df.loc[mask.to_numpy(), col] = np.nan if pd.api.types.is_float_dtype(ctx.df[col]) else pd.NA
        _transform(ctx, f"Blanked Placeholders {col}", col, f"let n = {fn}(_) in if n <> null and List.Contains({listed}, n) then null else _")


def _op_dedupe_key(ctx: _Ctx, step: CleaningStep) -> None:
    key = step.params["key"]
    df = ctx.df
    keyed = df[key].notna()
    order = pd.RangeIndex(len(df))
    if step.strategy == "latest" and step.params.get("date_column") in df.columns:
        dates = to_datetimes(df[step.params["date_column"]])
        rank = (dates - pd.Timestamp(0)).dt.total_seconds().fillna(-np.inf)  # blank dates rank last
    elif step.strategy == "most_complete":
        rank = df.notna().sum(axis=1)
    else:
        rank = pd.Series(0, index=df.index)
    ranked = pd.DataFrame({"rank": rank.to_numpy(), "pos": order, "key": df[key].to_numpy()}, index=df.index)[keyed.to_numpy()]
    ranked = ranked.sort_values(["rank", "pos"], ascending=[False, True], kind="mergesort")
    losers = ranked.index[ranked.duplicated(subset=["key"], keep="first").to_numpy()]
    ctx.drop(pd.Series(df.index.isin(losers), index=df.index), "duplicate")

    k = m_text(key)
    prev = ctx.m.last
    if step.strategy in ("latest", "most_complete"):
        rank_expr = (
            f"{ctx.m.fn('fnDateTime')}(Record.Field(_, {m_text(step.params['date_column'])}), {m_text(ctx.cultures.get(step.params['date_column'], 'en-US'))})"
            if step.strategy == "latest" else "List.NonNullCount(Record.FieldValues(_))"
        )
        kept = (
            f"Table.RemoveColumns(Table.Distinct(Table.Buffer(Table.Sort(Table.AddColumn(Table.AddIndexColumn(keyed, \"__pos\", 0, 1), \"__rank\", each {rank_expr}), "
            f'{{{{"__rank", Order.Descending}}, {{"__pos", Order.Ascending}}}})), {{{k}}}), {{"__pos", "__rank"}})'
        )
    else:
        kept = f"Table.Distinct(keyed, {{{k}}})"
    ctx.m.add(f"One Row Per {key}", (
        f"let keyed = Table.SelectRows({prev}, each Record.Field(_, {k}) <> null), "
        f"blanks = Table.SelectRows({prev}, each Record.Field(_, {k}) = null) in Table.Combine({{{kept}, blanks}})"
    ))


def _op_orphan_keys(ctx: _Ctx, step: CleaningStep) -> None:
    col = step.columns[0]
    target, target_col = step.params["target_table"], step.params["target_column"]
    keys = ctx.lookups.get((target, target_col), set())
    values = ctx.df[col]
    orphan = (values.notna() & ~_text(values).isin(keys)).fillna(False)
    keys_step = ctx.m.helper(
        f"Keys {target} {target_col}",
        f"List.Buffer(List.Transform(Table.Column({m_name(target)}, {m_text(target_col)}), each if _ = null then null else Text.From(_)))",
    )
    if step.strategy == "flag":
        flag = new_column(ctx.df, f"{col}_orphan")
        ctx.df[flag] = orphan.astype(bool)
        ctx.m.add(f"Flagged Orphans {col}", (
            f"Table.AddColumn({ctx.m.last}, {m_text(flag)}, each let v = Record.Field(_, {m_text(col)}) in "
            f"v <> null and not List.Contains({keys_step}, Text.From(v)), type logical)"
        ))
    else:
        ctx.df[col] = values.astype("object").where(~orphan.to_numpy(), UNKNOWN).astype("string")
        _transform(ctx, f"Unknown Member {col}", col, f'if _ = null or List.Contains({keys_step}, Text.From(_)) then _ else {m_text(UNKNOWN)}')


def _op_unknown_member(ctx: _Ctx, step: CleaningStep) -> None:
    key = step.params["key"]
    if UNKNOWN in set(_text(ctx.df[key]).dropna()):
        return
    row = pd.DataFrame({key: [UNKNOWN]}, index=[int(ctx.df.index.max()) + 1 if len(ctx.df) else 0]).astype("string")
    ctx.df = pd.concat([ctx.df, row])
    prev = ctx.m.last
    ctx.m.add("Added Unknown Member", (
        f"if List.Contains(Table.Column({prev}, {m_text(key)}), {m_text(UNKNOWN)}) then {prev} "
        f"else Table.Combine({{{prev}, #table({{{m_text(key)}}}, {{{{{m_text(UNKNOWN)}}}}})}})"
    ))


def _op_handle_nulls(ctx: _Ctx, step: CleaningStep) -> None:
    col = step.columns[0]
    missing = ctx.df[col].isna()
    field_ref = f"Record.Field(_, {m_text(col)})"
    converted = ctx.converted.get(col)
    if step.strategy == "remove_rows":
        ctx.drop(missing.fillna(True), "removed")
        ctx.m.add(f"Removed Missing {col}", f"Table.SelectRows({ctx.m.last}, each {field_ref} <> null)")
    elif step.strategy == "flag":
        flag = new_column(ctx.df, f"{col}_is_missing")
        ctx.df[flag] = missing.astype(bool)
        ctx.m.add(f"Flagged Missing {col}", f"Table.AddColumn({ctx.m.last}, {m_text(flag)}, each {field_ref} = null, type logical)")
    elif step.strategy == "fill_unknown":
        if converted:
            raise SkipStep(f"{col} is no longer text after an earlier step, so '{UNKNOWN}' cannot be filled in")
        ctx.df[col] = ctx.df[col].astype("object").where(~missing.to_numpy(), UNKNOWN).astype("string")
        ctx.m.add(f"Filled {col}", f"Table.ReplaceValue({ctx.m.last}, null, {m_text(UNKNOWN)}, Replacer.ReplaceValue, {{{m_text(col)}}})")
    else:  # fill_median: a number once the column is numeric, else text like the raw values
        if converted in ("date", "datetime", "bool"):
            raise SkipStep(f"{col} is no longer numeric text, so a median cannot be filled in")
        kind = step.types.get(col)
        median = step.fill_value or 0.0
        if converted == "number":
            value = median / 100 if kind == "percentage" else median
            ctx.df[col] = ctx.df[col].where(~missing.to_numpy(), value)
            literal = m_number(value)
        else:
            text = m_number(median) + ("%" if kind == "percentage" else "")
            ctx.df[col] = ctx.df[col].astype("object").where(~missing.to_numpy(), text).astype("string")
            literal = m_text(text)
        ctx.m.add(f"Filled {col}", f"Table.ReplaceValue({ctx.m.last}, null, {literal}, Replacer.ReplaceValue, {{{m_text(col)}}})")


_OPS = {
    "remove_total_rows": _op_remove_total_rows,
    "clean_whitespace": _op_clean_whitespace,
    "remove_duplicates": _op_remove_duplicates,
    "standardise_categories": _op_standardise,
    "merge_synonyms": _op_merge_synonyms,
    "normalise_booleans": _op_normalise_booleans,
    "cast_numeric": _op_cast_numeric,
    "cast_european": _op_cast_european,
    "date_format": _op_date_format,
    "set_types": _op_set_types,
    "excel_serial_dates": _op_excel_serial_dates,
    "date_outliers": _op_date_outliers,
    "sentinel_values": _op_sentinel_values,
    "dedupe_key": _op_dedupe_key,
    "orphan_keys": _op_orphan_keys,
    "handle_nulls": _op_handle_nulls,
    "unknown_member": _op_unknown_member,
}


def run_pipeline(
    src: SourceTable,
    steps: list[CleaningStep],
    lookups: dict[tuple[str, str], set[str]] | None = None,
) -> PipelineResult:
    """Apply the given steps (in KIND_ORDER) to a copy of the table, building the M script alongside.

    A step that fails is rolled back in both pandas and M, gets `step.error`, and is reported in
    `warnings`; the remaining steps still run.
    """
    m = _M()
    _source_steps(m, src)
    ctx = _Ctx(src=src, df=src.df.copy(), m=m, dropped={}, converted={}, cultures={}, lookups=lookups or {})
    warnings: list[str] = []
    for step in sorted(steps, key=lambda s: KIND_ORDER.index(s.kind)):
        missing = [c for c in step.columns if c not in ctx.df.columns]
        snapshot = (ctx.df.copy(), dict(ctx.dropped), dict(ctx.converted), dict(ctx.cultures), m.snapshot())
        try:
            if missing and step.kind not in ("remove_duplicates", "unknown_member"):
                raise SkipStep(f"column {missing[0]} is not in the table")
            _OPS[step.kind](ctx, step)
            step.error = None
        except Exception as exc:  # isolation: one bad step never breaks the rest
            ctx.df, ctx.dropped, ctx.converted, ctx.cultures = snapshot[0], snapshot[1], snapshot[2], snapshot[3]
            m.restore(snapshot[4])
            if isinstance(exc, SkipStep):  # the step does not apply in this state
                step.error = f"Skipped: {exc}"
            else:  # unexpected failure on unusual data
                step.error = f"Failed: {type(exc).__name__}: {exc}"[:240]
            warnings.append(f"{src.name}: '{step.title}' was not applied ({step.error}).")
    header = (
        f"// {src.name} - generated by DashPilot. DataFolder is a text parameter with the folder\n"
        "// that holds the source files (ending in a backslash)."
    )
    return PipelineResult(df=ctx.df, dropped=ctx.dropped, m_script=m.render(header), warnings=warnings)


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


def preview(src: SourceTable, result: PipelineResult, accepted: list[CleaningStep], key_column: str | None, limit: int = 8) -> DiffPreview:
    """Before/after sample rows for the accepted steps of one table."""
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
    # would mark every row as transformed and hide the real fixes.
    value_fixed = {
        c for s in accepted
        if s.kind not in ("set_types", "remove_duplicates", "unknown_member") and not (s.kind == "handle_nulls" and s.strategy == "flag")
        for c in s.columns
    }
    type_only = {c for s in accepted if s.kind == "set_types" for c in s.columns} - value_fixed
    for col in type_only:
        after_text[col] = before_text[col]
    diff = (before_text != after_text) & ~(before_text.isna() & after_text.isna())
    diff = diff[kept]
    counts = diff.sum()
    changed_columns = [str(c) for c, n in counts.sort_values(ascending=False).items() if n > 0]

    key = key_column if key_column in shared else (str(shared[0]) if shared else "")
    shown = ([key] if key else []) + [c for c in changed_columns if c != key][:4]
    if len(shown) < 3:
        shown += [c for c in shared if c not in shown][: 3 - len(shown)]

    transformed_idx = list(diff.index[diff.any(axis=1)])
    transformed_set = set(transformed_idx)
    dropped_idx = [i for i in result.dropped if i in before.index]
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
    by_reason = {
        "duplicate": [i for i in dropped_idx if result.dropped[i] == "duplicate"],
        "removed": [i for i in dropped_idx if result.dropped[i] == "removed"],
    }
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

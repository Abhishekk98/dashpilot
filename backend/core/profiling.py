"""Data Quality Report: types, stats, semantic roles and a quality score. (Spec Module 2)

All functions work on DataFrames whose cells are strings (see core/upload.py).
Roles are first assigned by deterministic rules so the report works without an
API key; `llm_roles.refine_roles` can then upgrade them with Claude.
"""

from __future__ import annotations

import re
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

# --- report models ------------------------------------------------------------

READER_VERSION = 2  # bump when core/upload.py reads files differently

DetectedType = Literal[
    "id", "uuid", "currency", "percentage", "integer", "decimal",
    "date", "datetime", "boolean", "email", "location", "category", "text",
]
SemanticRole = Literal[
    "primary_key", "foreign_key", "measure", "time_dimension", "geo_dimension",
    "categorical_slicer", "flag", "attribute", "identifier",
]


class NumericStats(BaseModel):
    min: float
    max: float
    mean: float
    median: float
    outliers: int


class DateStats(BaseModel):
    min: str
    max: str
    span_days: int


class ColumnProfile(BaseModel):
    name: str
    detected_type: DetectedType
    currency_symbol: str | None = None
    null_count: int
    null_pct: float
    distinct_count: int
    unique_pct: float
    numeric: NumericStats | None = None
    dates: DateStats | None = None
    sample_values: list[str]
    role: SemanticRole
    role_target: str | None = None  # referenced table for foreign keys
    confidence: float = Field(ge=0, le=1)
    role_source: Literal["rules", "ai"] = "rules"
    # Values stored as text that must be cast before DAX (e.g. "$1,234.50").
    needs_casting: bool = False
    # Category values that differ only by case/spacing (e.g. "Delhi" vs "delhi").
    inconsistent_values: int = 0


class TableProfile(BaseModel):
    name: str
    file_id: str
    sheet: str | None = None
    rows: int
    columns: int
    null_pct: float
    duplicate_rows: int
    quality_score: int
    column_profiles: list[ColumnProfile]


class QualityReport(BaseModel):
    score: int
    label: Literal["Good Quality", "Fair Quality", "Needs Attention"]
    confidence: float
    headline: str
    detail: str
    signal: str
    tables: list[TableProfile]
    total_rows: int
    total_columns: int
    ai_refined: bool = False
    # off = no AI key, pending = rule-based result shown while AI refinement runs,
    # done = roles refined by AI, failed = AI call failed (ai_note says why).
    ai_status: Literal["off", "pending", "done", "failed"] = "off"
    ai_note: str | None = None
    # Bumped when core/upload.py reads files differently, so cached reports are rebuilt.
    reader_version: int = READER_VERSION


# --- type detection -------------------------------------------------------------

_CURRENCY_RE = re.compile(r"^\(?-?\s*([$€£₹¥])\s*-?[\d,]*\.?\d+\)?$|^-?[\d,]*\.?\d+\s*([$€£₹¥])$")
_PERCENT_RE = re.compile(r"^-?[\d,]*\.?\d+\s*%$")
_NUMBER_RE = re.compile(r"^-?(\d{1,3}(,\d{3})+|\d+)?(\.\d+)?$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$", re.I)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_CODE_RE = re.compile(r"^[A-Za-z]{0,5}[-_]?\d{2,}$")  # ORD-10001, C0057, P024
_BOOL_VALUES = {"true", "false", "yes", "no", "y", "n", "t", "f", "1", "0"}

_ID_NAME_RE = re.compile(r"(^id$|_id$|^id_|id$|_key$|^key$|_code$|_no$|_number$|guid|uuid)", re.I)
_GEO_NAME_RE = re.compile(
    r"(city|state|country|region|province|district|zip|postal|pincode|address|location|latitude|longitude|^lat$|^lon$|^lng$)",
    re.I,
)

MATCH_THRESHOLD = 0.95
SAMPLE_LIMIT = 20_000


def _share(values: pd.Series, pattern: re.Pattern) -> float:
    return float(values.str.match(pattern).mean()) if len(values) else 0.0


def _to_number(values: pd.Series) -> pd.Series:
    """Parse currency / percent / thousands-separated text to floats (NaN when not numeric)."""
    cleaned = values.str.replace(r"[,$€£₹¥%\s]", "", regex=True).str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def _to_datetime(values: pd.Series) -> pd.Series:
    """Parse text to naive datetimes (NaT when not a date). Mixed time zones are converted to UTC."""
    try:
        out = pd.to_datetime(values, errors="coerce", format="mixed")
    except (ValueError, TypeError, OverflowError):
        out = None
    if out is None or not pd.api.types.is_datetime64_any_dtype(out):
        try:
            out = pd.to_datetime(values, errors="coerce", format="mixed", utc=True)
        except (ValueError, TypeError, OverflowError):
            return pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    if getattr(out.dt, "tz", None) is not None:
        out = out.dt.tz_convert(None)
    return out


def detect_type(name: str, values: pd.Series) -> tuple[DetectedType, str | None, float]:
    """Return (type, currency_symbol, match_share) for the non-null text values of a column."""
    v = values.dropna().astype(str)
    if v.empty:
        return "text", None, 1.0
    v = v.head(SAMPLE_LIMIT)
    lower = v.str.lower()

    if lower.isin(_BOOL_VALUES).mean() >= MATCH_THRESHOLD and lower.nunique() <= 2 and not _ID_NAME_RE.search(name):
        return "boolean", None, float(lower.isin(_BOOL_VALUES).mean())

    share = _share(v, _UUID_RE)
    if share >= MATCH_THRESHOLD:
        return "uuid", None, share

    share = _share(v, _EMAIL_RE)
    if share >= MATCH_THRESHOLD:
        return "email", None, share

    share = _share(v, _CURRENCY_RE)
    if share >= MATCH_THRESHOLD:
        symbols = v.str.extract(r"([$€£₹¥])")[0].dropna()
        return "currency", (symbols.mode().iat[0] if not symbols.empty else None), share

    share = _share(v, _PERCENT_RE)
    if share >= MATCH_THRESHOLD:
        return "percentage", None, share

    share = _share(v, _NUMBER_RE)
    if share >= MATCH_THRESHOLD:
        numbers = _to_number(v)
        is_int = bool((numbers.dropna() % 1 == 0).all())
        # Integer columns named like keys (store_no, zip) are IDs, not measures.
        if is_int and _ID_NAME_RE.search(name):
            return ("location" if _GEO_NAME_RE.search(name) else "id"), None, share
        if is_int and _GEO_NAME_RE.search(name):
            return "location", None, share
        return ("integer" if is_int else "decimal"), None, share

    # Pure digit strings are handled above, so anything date-like here is a real date.
    parsed = _to_datetime(v)
    share = float(parsed.notna().mean())
    if share >= MATCH_THRESHOLD:
        has_time = bool((parsed.dropna().dt.normalize() != parsed.dropna()).any())
        return ("datetime" if has_time else "date"), None, share

    if _GEO_NAME_RE.search(name):
        return "location", None, 1.0

    distinct_ratio = v.nunique() / len(v)
    code_share = _share(v, _CODE_RE)
    if _ID_NAME_RE.search(name) or (code_share >= MATCH_THRESHOLD and distinct_ratio > 0.5):
        return "id", None, max(code_share, 0.9)

    # Low-cardinality text is a slicer candidate; mostly-unique text (names, notes) is not.
    if (v.nunique() <= 50 and (distinct_ratio < 0.5 or len(v) < 20)) or distinct_ratio <= 0.1:
        return "category", None, 1.0
    return "text", None, 1.0


# --- statistics -------------------------------------------------------------------

def _numeric_stats(numbers: pd.Series) -> NumericStats | None:
    n = numbers.dropna()
    if n.empty:
        return None
    q1, q3 = np.percentile(n, [25, 75])
    iqr = q3 - q1
    outliers = int(((n < q1 - 1.5 * iqr) | (n > q3 + 1.5 * iqr)).sum()) if iqr > 0 else 0
    return NumericStats(
        min=float(n.min()), max=float(n.max()), mean=round(float(n.mean()), 4),
        median=float(n.median()), outliers=outliers,
    )


def _date_stats(values: pd.Series) -> DateStats | None:
    d = _to_datetime(values.dropna().astype(str)).dropna()
    if d.empty:
        return None
    return DateStats(min=d.min().isoformat(), max=d.max().isoformat(), span_days=int((d.max() - d.min()).days) + 1)


def _inconsistent_values(values: pd.Series) -> int:
    """Count raw values that collapse into another value after trimming + lower-casing."""
    v = values.dropna().astype(str)
    raw = v.nunique()
    normalised = v.str.strip().str.lower().str.replace(r"\s+", " ", regex=True).nunique()
    return int(raw - normalised)


def _samples(values: pd.Series, k: int = 3) -> list[str]:
    return [str(x) for x in values.dropna().astype(str).unique()[:k]]


# --- roles --------------------------------------------------------------------------

_TYPE_ROLE: dict[str, tuple[SemanticRole, float]] = {
    "currency": ("measure", 0.98),
    "percentage": ("measure", 0.9),
    "decimal": ("measure", 0.92),
    "integer": ("measure", 0.85),
    "date": ("time_dimension", 0.96),
    "datetime": ("time_dimension", 0.96),
    "location": ("geo_dimension", 0.94),
    "boolean": ("flag", 0.95),
    "category": ("categorical_slicer", 0.9),
    "email": ("attribute", 0.9),
    "text": ("attribute", 0.75),
}


def _singular(word: str) -> str:
    word = word.lower()
    return word[:-1] if word.endswith("s") else word


def _base_role(col: ColumnProfile, table: str, rows: int, unique_rows: int) -> tuple[SemanticRole, float]:
    if col.detected_type in ("id", "uuid"):
        # Unique per row, or unique once exact duplicate rows are removed (cleaning step).
        unique = col.null_count == 0 and col.distinct_count in (rows, unique_rows)
        if unique:
            # A unique key whose name echoes the table (orders -> order_id) is the PK.
            prefix = col.name.lower().split("_")[0]
            echoes_table = bool(prefix) and _singular(prefix) in _singular(table)
            confidence = 0.99 if echoes_table else 0.9
            return "primary_key", confidence if col.distinct_count == rows else confidence - 0.05
        return "identifier", 0.8
    return _TYPE_ROLE[col.detected_type]


def profile_column(name: str, values: pd.Series, table: str, rows: int, unique_rows: int | None = None) -> ColumnProfile:
    detected, symbol, match_share = detect_type(name, values)
    non_null = values.dropna()
    null_count = int(values.isna().sum())
    distinct = int(non_null.nunique())

    numeric = dates = None
    if detected in ("currency", "percentage", "integer", "decimal"):
        numeric = _numeric_stats(_to_number(non_null.astype(str)))
    elif detected in ("date", "datetime"):
        dates = _date_stats(non_null)

    raw = non_null.astype(str)
    needs_casting = detected in ("currency", "percentage") or (
        detected in ("integer", "decimal") and bool(raw.str.contains(",", regex=False).any())
    )

    col = ColumnProfile(
        name=name,
        detected_type=detected,
        currency_symbol=symbol,
        null_count=null_count,
        null_pct=round(null_count / rows * 100, 2) if rows else 0.0,
        distinct_count=distinct,
        unique_pct=round(distinct / len(non_null) * 100, 2) if len(non_null) else 0.0,
        numeric=numeric,
        dates=dates,
        sample_values=_samples(values),
        role="attribute",
        confidence=0.5,
        needs_casting=needs_casting,
        inconsistent_values=_inconsistent_values(values) if detected in ("category", "location") else 0,
    )
    role, confidence = _base_role(col, table, rows, rows if unique_rows is None else unique_rows)
    col.role = role
    # Columns where some values did not fit the detected type lower the confidence.
    col.confidence = round(confidence * min(1.0, match_share + 0.02), 2)
    return col


def link_foreign_keys(tables: list[TableProfile], frames: dict[str, pd.DataFrame]) -> None:
    """Mark key-like columns whose values are mostly found in another table's primary key."""
    primary_keys = [
        (t.name, c.name) for t in tables for c in t.column_profiles if c.role == "primary_key"
    ]
    for table in tables:
        for col in table.column_profiles:
            if col.role not in ("identifier", "primary_key") or col.detected_type not in ("id", "uuid"):
                continue
            values = set(frames[table.name][col.name].dropna().astype(str))
            if not values:
                continue
            for pk_table, pk_col in primary_keys:
                if pk_table == table.name:
                    continue
                pk_values = set(frames[pk_table][pk_col].dropna().astype(str))
                overlap = len(values & pk_values) / len(values)
                if overlap >= 0.9 and col.role != "primary_key":
                    col.role, col.role_target = "foreign_key", pk_table
                    col.confidence = round(min(0.99, 0.8 + overlap * 0.19), 2)
                    break


# --- scoring ----------------------------------------------------------------------

def _table_score(df: pd.DataFrame, cols: list[ColumnProfile], duplicate_rows: int) -> int:
    cells = df.size or 1
    completeness = 1 - df.isna().sum().sum() / cells
    uniqueness = 1 - duplicate_rows / max(len(df), 1)
    # Validity: share of columns that are clean (no casting, no inconsistent categories).
    clean_cols = sum(1 for c in cols if not c.needs_casting and c.inconsistent_values == 0)
    validity = clean_cols / max(len(cols), 1)
    return round(100 * (0.5 * completeness + 0.3 * uniqueness + 0.2 * validity))


def profile_table(name: str, file_id: str, sheet: str | None, df: pd.DataFrame) -> TableProfile:
    rows = len(df)
    duplicate_rows = int(df.duplicated().sum())
    cols = [profile_column(str(c), df[c], name, rows, rows - duplicate_rows) for c in df.columns]
    return TableProfile(
        name=name,
        file_id=file_id,
        sheet=sheet,
        rows=rows,
        columns=len(df.columns),
        null_pct=round(float(df.isna().sum().sum()) / max(df.size, 1) * 100, 2),
        duplicate_rows=duplicate_rows,
        quality_score=_table_score(df, cols, duplicate_rows),
        column_profiles=cols,
    )


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def summarise(tables: list[TableProfile]) -> QualityReport:
    """Combine table profiles into the overall Data Quality Report."""
    total_rows = sum(t.rows for t in tables)
    if not tables:
        return QualityReport(
            score=0, label="Needs Attention", confidence=0, headline="No data uploaded yet.",
            detail="Upload CSV or Excel files to see the Data Quality Report.", signal="",
            tables=[], total_rows=0, total_columns=0,
        )

    # Row-weighted so a tiny lookup sheet does not dominate the score.
    score = round(sum(t.quality_score * max(t.rows, 1) for t in tables) / sum(max(t.rows, 1) for t in tables))
    columns = [c for t in tables for c in t.column_profiles]
    confidence = round(sum(c.confidence for c in columns) / len(columns) * 100, 1)
    label = "Good Quality" if score >= 85 else "Fair Quality" if score >= 70 else "Needs Attention"

    fks = sum(1 for c in columns if c.role == "foreign_key")
    casts = sum(1 for c in columns if c.needs_casting)
    inconsistent = sum(1 for c in columns if c.inconsistent_values)
    dups = sum(t.duplicate_rows for t in tables)
    has_time = any(c.role == "time_dimension" for c in columns)
    has_measure = any(c.role == "measure" for c in columns)

    if has_measure and (fks or len(tables) == 1):
        headline = "Ready for star schema modelling." if score >= 85 else "Usable for modelling after cleaning."
    else:
        headline = "No clear measures or relationships found yet."

    fixes = []
    if inconsistent:
        fixes.append("categorical normalisation")
    if dups:
        fixes.append("duplicate removal")
    if any(c.null_pct > 0 for c in columns):
        fixes.append("missing-value handling")
    detail = (f"Recommended before DAX: {', '.join(fixes)}." if fixes else "No cleaning issues detected.")
    if not has_time:
        detail += " No date column found; a date table will need a source date."

    signal_parts = []
    if fks:
        signal_parts.append(f"{_plural(fks, 'foreign key relationship candidate')} identified.")
    if casts:
        signal_parts.append(f"{_plural(casts, 'column')} require{'s' if casts == 1 else ''} numeric casting before DAX aggregation.")
    if inconsistent:
        signal_parts.append(f"{_plural(inconsistent, 'column')} with inconsistent category spelling.")
    signal = " ".join(signal_parts) or "No relationship or casting issues detected."

    return QualityReport(
        score=score, label=label, confidence=confidence, headline=headline, detail=detail, signal=signal,
        tables=tables, total_rows=total_rows, total_columns=len(columns),
    )


def build_report(tables: list[tuple[str, str, str | None, pd.DataFrame]]) -> QualityReport:
    """Profile (name, file_id, sheet, frame) tuples and link relationships across them."""
    profiles = [profile_table(name, file_id, sheet, df) for name, file_id, sheet, df in tables]
    link_foreign_keys(profiles, {name: df for name, _, _, df in tables})
    return summarise(profiles)

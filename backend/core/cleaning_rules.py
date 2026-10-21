"""Cleaning suggestions (rules + optional AI synonyms), user decisions and the cleaning plan.

Every detector runs isolated: if one fails on unusual data it is skipped with a warning and the
other suggestions still appear. The steps themselves are applied by core/cleaning.py.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel

from core.cleaning import (
    _DMY,
    FALSE_VALUES,
    NUMERIC_TYPES,
    TOTAL_WORDS,
    TRUE_VALUES,
    UNKNOWN,
    CleaningPlan,
    CleaningStep,
    Impact,
    PipelineResult,
    SourceTable,
    TableCleaning,
    ValueMerge,
    _clean_ws,
    _text,
    run_pipeline,
    to_datetimes,
    to_numbers,
)
from core.profiling import ColumnProfile, QualityReport, TableProfile
from core.upload import structure_notes
from llm import LLMError, LLMProvider

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "cleaning_synonyms.md"
TEXT_TYPES = ("category", "text", "location", "id", "email")
_EURO = re.compile(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$|^-?\d+,\d+$")
_SERIAL_NAME = re.compile(r"date|_dt$|^dt_|day|time|_on$|_at$|created|updated|modified|dob|birth|joined|signup|start|end", re.I)
_ZERO_IMPLAUSIBLE = re.compile(r"(^|_)(age|price|unit_price|mrp|cost|salary|weight|height)($|_)", re.I)
_RECENCY_NAME = re.compile(r"updated|modified|last|latest|date|time", re.I)

# Synonym dictionary: canonical -> aliases (lower case). `columns` limits a group to matching column names.
SYNONYM_GROUPS: list[tuple[str, set[str], re.Pattern | None]] = [
    ("Male", {"m", "male", "man", "boy"}, re.compile(r"gender|sex", re.I)),
    ("Female", {"f", "female", "woman", "girl"}, re.compile(r"gender|sex", re.I)),
    ("United States", {"us", "usa", "u.s.", "u.s.a.", "united states", "united states of america", "america"}, re.compile(r"country|nation|region|market", re.I)),
    ("United Kingdom", {"uk", "u.k.", "united kingdom", "great britain", "gb"}, re.compile(r"country|nation|region|market", re.I)),
    ("United Arab Emirates", {"uae", "u.a.e.", "united arab emirates"}, None),
    ("Mumbai", {"bombay", "mumbai"}, None),
    ("Bengaluru", {"bangalore", "bengaluru", "banglore"}, None),
    ("Kolkata", {"calcutta", "kolkata"}, None),
    ("Chennai", {"madras", "chennai"}, None),
    ("Gurugram", {"gurgaon", "gurugram"}, None),
    ("Pune", {"poona", "pune"}, None),
    ("Delhi", {"delhi", "new delhi", "ncr delhi"}, None),
    ("Thiruvananthapuram", {"trivandrum", "thiruvananthapuram"}, None),
    ("Vadodara", {"baroda", "vadodara"}, None),
]


@dataclass
class RuleContext:
    profiles: dict[str, TableProfile]
    sources: dict[str, SourceTable]
    ai_synonyms: dict[str, dict[str, str]] = field(default_factory=dict)  # "table::column" -> {lower: canonical}
    today: pd.Timestamp = field(default_factory=lambda: pd.Timestamp.today().normalize())
    warnings: list[str] = field(default_factory=list)


# --- helpers ------------------------------------------------------------------------

def _pct(n: int, rows: int) -> float:
    return round(n / rows * 100, 2) if rows else 0.0


def _rows(n: int) -> str:
    return f"{n:,} {'row' if n == 1 else 'rows'}"


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _number_text(value: float) -> str:
    return np.format_float_positional(value, trim="-")


def _step(table: TableProfile, key: str, **kw) -> CleaningStep:
    rows = kw.pop("rows_affected")
    return CleaningStep(id=f"{table.name}::{key}", table=table.name, rows_affected=int(rows), affected_pct=_pct(int(rows), table.rows), **kw)


def _with_strategies(step: CleaningStep, texts: dict[str, tuple[str, str]], default: str) -> CleaningStep:
    step.strategies = list(texts)
    step.strategy_text = {k: list(v) for k, v in texts.items()}
    step.strategy = default
    step.title, step.description = texts[default]
    return step


def _merges(values: pd.Series) -> list[ValueMerge]:
    """Group spellings that only differ by case/spacing; the most frequent spelling wins."""
    counts = values.dropna().astype(str).value_counts()
    keys = counts.index.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    merges = []
    for _, group in counts.groupby(keys, sort=False):
        if len(group) < 2:
            continue
        # Prefer a properly cased spelling ("Pune" over "PUNE"/"pune"), then the most frequent;
        # hidden spaces are cleaned so it agrees with the whitespace step.
        cased = group[[not (str(k).isupper() or str(k).islower()) for k in group.index]]
        canonical = str(_clean_ws(str((cased if len(cased) else group).idxmax())))
        variants = {str(k): int(v) for k, v in group.items() if k != canonical}
        merges.append(ValueMerge(canonical=canonical, variants=variants, total=int(group.sum())))
    return sorted(merges, key=lambda m: -sum(m.variants.values()))


def _median(col: ColumnProfile, df: pd.DataFrame) -> float | None:
    numbers = to_numbers(df.drop_duplicates()[col.name]).dropna()
    if numbers.empty:
        return None
    median = float(numbers.median())
    return float(round(median)) if col.detected_type == "integer" else round(median, 2)


# --- detectors ----------------------------------------------------------------------

def _detect_total_rows(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    for col in [c for c in t.column_profiles if c.detected_type in TEXT_TYPES][:3]:
        norm = _text(df[col.name]).str.strip().str.lower().str.rstrip(":")
        n = int(norm.isin(TOTAL_WORDS).fillna(False).sum())
        if 0 < n <= max(3, len(df) * 0.05):
            return [_step(
                t, f"{col.name}::totals", kind="remove_total_rows", impact="High", category="Structure",
                title=f"Remove {_plural(n, 'total row')}",
                description=f"Rows labelled 'Total' or 'Grand Total' in {col.name} repeat the sum of other rows; keeping them would double-count every measure.",
                columns=[col.name], rows_affected=n, params={"column": col.name},
            )]
    return []


def _detect_whitespace(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    cols, rows = [], pd.Series(False, index=df.index)
    for col in t.column_profiles:
        if col.detected_type not in TEXT_TYPES:
            continue
        s = _text(df[col.name])
        changed = (s.notna() & (s.map(_clean_ws).astype("string") != s)).fillna(False).astype(bool)
        if changed.any():
            cols.append(col.name)
            rows |= changed
    if not cols:
        return []
    return [_step(
        t, "whitespace", kind="clean_whitespace", impact="Medium", category="Text Formats",
        title=f"Clean hidden spaces in {_plural(len(cols), 'column')}",
        description=f"Non-breaking spaces, zero-width characters or double spaces in {', '.join(cols[:4])} make identical values look different to Power BI.",
        columns=cols, rows_affected=int(rows.sum()),
    )]


def _detect_duplicates(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    if not t.duplicate_rows:
        return []
    cols = t.column_profiles
    measure = next((c.name for c in cols if c.role == "measure"), None)
    effect = f"prevents double-counting {measure} in DAX sums" if measure else "keeps counts and relationships accurate"
    return [_step(
        t, "dedupe", kind="remove_duplicates", impact="High",
        category="Star Schema Key" if any(c.role == "primary_key" for c in cols) else "Duplicate Rows",
        title=f"Remove {t.duplicate_rows:,} duplicate {'record' if t.duplicate_rows == 1 else 'records'}",
        description=f"{_rows(t.duplicate_rows)} are exact copies of an earlier row. Removing them {effect}.",
        columns=[c.name for c in cols], rows_affected=t.duplicate_rows,
    )]


def _detect_case_variants(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    for col in t.column_profiles:
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
        steps.append(_step(
            t, f"{col.name}::standardise", kind="standardise_categories", impact="Medium",
            category="Categorical Normalization", title=title,
            description=(
                f"{sum(len(m.variants) for m in merges) + len(merges)} spellings differ only by case or spacing. "
                "Each group is merged into its most frequent spelling so slicers show one member."
            ),
            columns=[col.name], rows_affected=changed, merges=merges,
        ))
    return steps


def _detect_synonyms(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    for col in t.column_profiles:
        if col.detected_type not in ("category", "location", "text") or col.distinct_count > 300:
            continue
        values = _text(df[col.name]).dropna().str.strip()
        counts = values.value_counts()
        lower_counts = values.str.lower().value_counts()
        mapping: dict[str, str] = {}
        for canonical, aliases, only in SYNONYM_GROUPS:
            if only is not None and not only.search(col.name):
                continue
            present = [v for v in lower_counts.index if v in aliases or v == canonical.lower()]
            if len(present) >= 2:
                mapping.update({v: canonical for v in present})
        ai = ctx.ai_synonyms.get(f"{t.name}::{col.name}", {})
        mapping.update(ai)
        # One spelling per target, preferring proper case ("Female" over "female"/"FEMALE").
        spellings: dict[str, str] = {}
        for target in mapping.values():
            best = spellings.get(target.lower())
            if best is None or (best.islower() or best.isupper()) and not (target.islower() or target.isupper()):
                spellings[target.lower()] = target
        mapping = {k: spellings[v.lower()] for k, v in mapping.items()}
        # Only keep spellings that actually change.
        mapping = {k: v for k, v in mapping.items() if any(raw.lower() == k and raw != v for raw in counts.index)}
        if not mapping:
            continue
        groups: dict[str, dict[str, int]] = defaultdict(dict)
        for raw, n in counts.items():
            target = mapping.get(raw.lower())
            if target is not None and raw != target:
                groups[target][raw] = int(n)
        merges = [ValueMerge(canonical=c, variants=v, total=int(sum(v.values()) + counts.get(c, 0))) for c, v in groups.items()]
        changed = sum(sum(m.variants.values()) for m in merges)
        first = merges[0]
        steps.append(_step(
            t, f"{col.name}::synonyms", kind="merge_synonyms", impact="Medium", category="Synonym Merge",
            title=f"Merge synonyms in {col.name}: {', '.join(repr(v) for v in list(first.variants)[:3])} → '{first.canonical}'"
            if len(merges) == 1 else f"Merge {len(merges)} synonym groups in {col.name}",
            description=(
                "Different words for the same thing are merged so totals are not split across members. "
                + ("Suggested by the AI Co-Analyst; review before accepting." if ai else "From DashPilot's synonym dictionary.")
            ),
            columns=[col.name], rows_affected=changed, merges=merges, params={"mapping": mapping},
            source="ai" if ai else "rules",
        ))
    return steps


def _detect_booleans(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    for col in t.column_profiles:
        if col.detected_type not in ("category", "text"):
            continue
        raw = _text(df[col.name]).dropna().str.strip()
        lower = set(raw.str.lower())
        if len(raw) == 0 or not lower <= set(TRUE_VALUES) | set(FALSE_VALUES):
            continue
        if not (lower & set(TRUE_VALUES)) or not (lower & set(FALSE_VALUES)):
            continue
        spellings = sorted(set(raw))[:6]
        steps.append(_step(
            t, f"{col.name}::booleans", kind="normalise_booleans", impact="Medium", category="Text Formats",
            title=f"Convert {col.name} to true/false",
            description=f"{len(set(raw))} spellings ({', '.join(spellings)}) mean yes or no. One true/false column filters and counts correctly.",
            columns=[col.name], rows_affected=len(raw), types={col.name: "boolean"},
        ))
    return steps


def _detect_casts(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    for col in t.column_profiles:
        if not col.needs_casting:
            continue
        target = {"currency": "Currency", "percentage": "Percentage"}.get(col.detected_type, "Number")
        non_null = t.rows - col.null_count
        steps.append(_step(
            t, f"{col.name}::cast", kind="cast_numeric", impact="High", category="Type Casting",
            title=f"Cast {col.name} from text to {target}",
            description=(
                "Removes currency symbols, % signs and thousands separators, then converts to a number "
                "so DAX can aggregate it. Values that are not numbers become blank instead of errors."
                + (" Percentages are stored as fractions (5% → 0.05)." if col.detected_type == "percentage" else "")
            ),
            columns=[col.name], rows_affected=non_null, types={col.name: col.detected_type},
        ))
    return steps


def _detect_european(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    for col in t.column_profiles:
        if col.detected_type not in ("category", "text") or col.role in ("primary_key", "identifier", "foreign_key"):
            continue
        s = _text(df[col.name]).dropna().str.strip()
        if len(s) < 3:
            continue
        share = s.str.match(_EURO).mean()
        if share >= 0.95 and s.str.contains(",", regex=False).any():
            steps.append(_step(
                t, f"{col.name}::european", kind="cast_european", impact="High", category="Number Formats",
                title=f"Read {col.name} as European numbers (1.234,56)",
                description="Dots are thousands separators and commas are decimals here. Converted to real numbers so they can be summed.",
                columns=[col.name], rows_affected=len(s), types={col.name: "decimal"},
            ))
    return steps


def _detect_date_format(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    for col in t.column_profiles:
        if col.detected_type not in ("date", "datetime", "text", "category"):
            continue
        s = _text(df[col.name]).dropna().str.strip()
        if len(s) < 3:
            continue
        parts = s.str.extract(_DMY.pattern)
        matched = parts[0].notna()
        if matched.mean() < 0.8:
            continue
        a, b = pd.to_numeric(parts[0], errors="coerce"), pd.to_numeric(parts[1], errors="coerce")
        if (a > 31).any() or (b > 31).any():
            continue
        day_first_evidence, month_first_evidence = bool((a > 12).any()), bool((b > 12).any())
        if month_first_evidence or (day_first_evidence and month_first_evidence):
            continue  # default month/day reading is already right, or the column mixes both
        kind = "datetime" if parts[3].fillna("").str.strip().ne("").any() else "date"
        texts = {
            "day_first": (f"Read {col.name} as day/month/year", f"Dates like {s[matched].iloc[0]} are read as day first (dd/mm/yyyy)."),
            "month_first": (f"Read {col.name} as month/day/year", f"Dates like {s[matched].iloc[0]} are read as month first (mm/dd/yyyy)."),
        }
        if not day_first_evidence:
            texts = {k: (f"Confirm the date order of {col.name}", v[1] + " Every value has day and month ≤ 12, so pick the order your source uses.") for k, v in texts.items()}
        step = _step(
            t, f"{col.name}::date_format", kind="date_format", impact="High" if day_first_evidence else "Medium",
            category="Date Formats", title="", description="", columns=[col.name], rows_affected=int(matched.sum()),
            types={col.name: kind},
        )
        steps.append(_with_strategies(step, texts, "day_first" if day_first_evidence else "month_first"))
    return steps


def _detect_types(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    typed = {
        c.name: c.detected_type
        for c in t.column_profiles
        if not c.needs_casting and c.detected_type in ("integer", "decimal", "date", "datetime", "boolean")
    }
    if not typed:
        return []
    return [_step(
        t, "types", kind="set_types", impact="Medium", category="Data Types",
        title=f"Apply detected data types to {_plural(len(typed), 'column')}",
        description=f"Sets number, date and true/false types on {', '.join(typed)} instead of loading everything as text. Unreadable values become blank, never errors.",
        columns=list(typed), rows_affected=t.rows, types=typed,
    )]


def _detect_excel_serial(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    for col in t.column_profiles:
        if col.detected_type not in ("integer", "decimal") or not _SERIAL_NAME.search(col.name):
            continue
        n = to_numbers(df[col.name]).dropna()
        if len(n) < 3 or ((n >= 20000) & (n <= 60000)).mean() < 0.95:
            continue
        kind = "date" if bool((n % 1 == 0).all()) else "datetime"
        sample = pd.to_datetime(n.iloc[0], unit="D", origin="1899-12-30")
        steps.append(_step(
            t, f"{col.name}::excel_dates", kind="excel_serial_dates", impact="High", category="Date Formats",
            title=f"Convert {col.name} from Excel serial numbers to dates",
            description=f"Values like {_number_text(float(n.iloc[0]))} are Excel date serials ({sample:%Y-%m-%d}). Converted so the date table and time intelligence work.",
            columns=[col.name], rows_affected=len(n), types={col.name: kind},
        ))
    return steps


def _detect_date_outliers(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    base_low, high = pd.Timestamp("1900-01-01"), ctx.today + pd.Timedelta(days=1)
    for col in t.column_profiles:
        if col.detected_type not in ("date", "datetime"):
            continue
        d = to_datetimes(df[col.name])
        valid = d.dropna()
        low = base_low
        if len(valid) >= 10:
            q05 = valid.quantile(0.05)
            is_dob = bool(re.search(r"dob|birth|born", col.name, re.I))
            if not is_dob and q05.year >= 2015:
                low = pd.Timestamp(f"{min(q05.year - 5, 2010)}-01-01")
        bad = (d.notna() & ((d < low) | (d > high))).fillna(False)
        n = int(bad.sum())
        if not n:
            continue
        example = d[bad].iloc[0]
        texts = {
            "blank": (f"Blank {_plural(n, 'impossible date')} in {col.name}", f"Dates before {low:%Y} or in the future (e.g. {example:%Y-%m-%d}) are usually typos or placeholders; they are set to blank so the date table stays compact."),
            "flag": (f"Flag {_plural(n, 'suspicious date')} in {col.name}", f"Dates before {low:%Y} or in the future (e.g. {example:%Y-%m-%d}) are kept, and a {col.name}_suspect_date column marks them."),
        }
        step = _step(
            t, f"{col.name}::date_outliers", kind="date_outliers", impact="Medium", category="Date Quality",
            title="", description="", columns=[col.name], rows_affected=n,
            params={"min": low.isoformat(), "max": high.isoformat()},
        )
        steps.append(_with_strategies(step, texts, "blank"))
    return steps


def _detect_sentinels(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    for col in t.column_profiles:
        if col.detected_type not in ("integer", "decimal", "currency") or col.role in ("primary_key", "identifier", "foreign_key"):
            continue
        n = to_numbers(df[col.name]).dropna()
        if len(n) < 5:
            continue
        typical = float(n.abs().median()) or 1.0
        found: list[float] = []
        for v in (9999, 99999, 999999, 9999999, 99999999, 999999999):
            if (n == v).any() and v >= 10 * typical:
                found.append(float(v))
        rest = n[~n.isin(found)]
        for v in (-1, -99, -999, -9999):
            others = rest[rest != v]
            if (n == v).any() and len(others) and (others >= 0).mean() >= 0.95:
                found.append(float(v))
        if _ZERO_IMPLAUSIBLE.search(col.name) and (n == 0).any() and (n == 0).mean() < 0.05 and (rest[rest != 0] > 0).all():
            found.append(0.0)
        if not found:
            continue
        count = int(n.isin(found).sum())
        shown = ", ".join(f"{v:,.0f}" for v in found)
        texts = {
            "blank": (f"Treat {shown} in {col.name} as blank", f"{_plural(count, 'value')} look like placeholder codes, not real amounts; they would distort sums and averages."),
            "flag": (f"Flag {shown} in {col.name} as placeholders", f"{_plural(count, 'value')} are kept and a {col.name}_placeholder column marks them for filtering."),
        }
        step = _step(
            t, f"{col.name}::sentinels", kind="sentinel_values", impact="High", category="Placeholder Values",
            title="", description="", columns=[col.name], rows_affected=count, params={"values": found},
        )
        steps.append(_with_strategies(step, texts, "blank"))
    return steps


def _detect_key_duplicates(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    unique_rows = df.drop_duplicates()
    date_cols = [c.name for c in t.column_profiles if c.detected_type in ("date", "datetime")]
    date_col = next((c for c in date_cols if _RECENCY_NAME.search(c)), date_cols[0] if date_cols else None)
    for col in t.column_profiles:
        if col.detected_type not in ("id", "uuid") and col.role != "primary_key":
            continue
        s = unique_rows[col.name].dropna()
        if len(s) < 2 or s.nunique() / len(s) < 0.8:
            continue
        dup = int(s.duplicated().sum())
        if not dup:
            continue
        texts = {
            "most_complete": (f"Keep one row per {col.name} (most complete)", f"{_plural(dup, 'extra row')} repeat an existing {col.name} with different details. Keeping the row with the most filled-in values makes {col.name} a valid key for relationships."),
            "first": (f"Keep one row per {col.name} (first)", f"{_plural(dup, 'extra row')} repeat an existing {col.name}. The first row of each is kept so {col.name} can be the 1 side of a relationship."),
        }
        if date_col:
            texts["latest"] = (f"Keep one row per {col.name} (latest {date_col})", f"{_plural(dup, 'extra row')} repeat an existing {col.name}. The row with the latest {date_col} is kept as the current version.")
        step = _step(
            t, f"{col.name}::dedupe_key", kind="dedupe_key", impact="High", category="Star Schema Key",
            title="", description="", columns=[col.name], rows_affected=dup,
            params={"key": col.name, "date_column": date_col},
        )
        steps.append(_with_strategies(step, texts, "most_complete"))
    return steps


def fk_target(t: TableProfile, col: ColumnProfile, df: pd.DataFrame, sources: dict[str, SourceTable], profiles: dict[str, TableProfile]) -> tuple[str, str] | None:
    """(table, key column) this column points to: the profiled foreign key, or a same-named,
    mostly-unique ID column in another table that holds most of its values (keys with a few
    duplicates are still recognised, so dedupe-by-key can fix them)."""
    target = sources.get(col.role_target or "")
    if col.role == "foreign_key" and target is not None:
        tprof = profiles[target.name]
        pk = next((c.name for c in tprof.column_profiles if c.role == "primary_key"), col.name if col.name in target.df.columns else None)
        return (target.name, pk) if pk else None
    if col.detected_type not in ("id", "uuid"):
        return None
    values = _text(df[col.name]).dropna()
    if values.empty:
        return None
    for name, src in sources.items():
        if name == t.name or col.name not in src.df.columns:
            continue
        keys = _text(src.df[col.name]).dropna()
        key_uniqueness = keys.nunique() / len(keys) if len(keys) >= 2 else 0.0
        # The other side must be the (mostly) unique one, and more unique than this column.
        if key_uniqueness < 0.8 or values.nunique() / len(values) >= key_uniqueness:
            continue
        if values.isin(set(keys)).mean() >= 0.8:
            return name, col.name
    return None


def _detect_orphans(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    for col in t.column_profiles:
        found = fk_target(t, col, df, ctx.sources, ctx.profiles)
        if found is None:
            continue
        target, pk = ctx.sources[found[0]], found[1]
        keys = set(_text(target.df[pk]).dropna())
        s = _text(df[col.name]).dropna()
        orphans = s[~s.isin(keys)]
        if orphans.empty:
            continue
        n, distinct = len(orphans), orphans.nunique()
        texts = {
            "unknown_member": (f"Map {_plural(n, 'orphan')} in {col.name} to '{UNKNOWN}'", f"{distinct:,} {col.name} values (e.g. {orphans.iloc[0]}) do not exist in {target.name}. They become '{UNKNOWN}' and {target.name} gets an '{UNKNOWN}' row, so totals stay complete."),
            "flag": (f"Flag {_plural(n, 'orphan row')} in {col.name}", f"{distinct:,} {col.name} values do not exist in {target.name}. Rows are kept and a {col.name}_orphan column marks them."),
        }
        step = _step(
            t, f"{col.name}::orphans", kind="orphan_keys", impact="High", category="Relationships",
            title="", description="", columns=[col.name], rows_affected=n,
            params={"target_table": target.name, "target_column": pk},
        )
        steps.append(_with_strategies(step, texts, "unknown_member"))
    return steps


def _null_texts(col: ColumnProfile, rows: int, median: float | None) -> dict[str, tuple[str, str]]:
    n = col.null_count
    share = f"{_pct(n, rows):g}%"
    shown = _number_text(median or 0.0) + ("%" if col.detected_type == "percentage" else "")
    return {
        "fill_median": (f"Fill {share} missing {col.name} with median ({shown})", f"{n:,} blank values in {col.name}. The median keeps averages stable without being pulled by outliers."),
        "fill_unknown": (f"Label {share} missing {col.name} as '{UNKNOWN}'", f"{n:,} blank values in {col.name}. An explicit '{UNKNOWN}' member keeps these rows visible in slicers and visuals."),
        "remove_rows": (f"Remove {_rows(n)} with missing {col.name}", f"{n:,} rows have no {col.name}. Rows without this value cannot be identified or related reliably."),
        "flag": (f"Flag {share} missing {col.name}", f"{n:,} blank values in {col.name} are kept as blanks, and a {col.name}_is_missing column marks them for filtering."),
    }


def _null_options(col: ColumnProfile) -> tuple[str, list[str]]:
    if col.role == "primary_key":
        return "remove_rows", ["remove_rows", "flag"]
    if col.role in ("foreign_key", "identifier"):
        # Removing fact rows would lose their amounts; an 'Unknown' key keeps them in the totals.
        return "fill_unknown", ["fill_unknown", "remove_rows", "flag"]
    if col.detected_type in NUMERIC_TYPES:
        # Filling money with a median would invent revenue, so amounts default to blanks.
        default = "flag" if col.detected_type == "currency" else "fill_median"
        return default, ["fill_median", "remove_rows", "flag"]
    if col.detected_type in ("date", "datetime", "boolean"):
        return "flag", ["remove_rows", "flag"]
    return "fill_unknown", ["fill_unknown", "remove_rows", "flag"]


def _detect_nulls(t: TableProfile, df: pd.DataFrame, ctx: RuleContext) -> list[CleaningStep]:
    steps = []
    for col in t.column_profiles:
        if not col.null_count:
            continue
        default, options = _null_options(col)
        median = _median(col, df) if "fill_median" in options else None
        if median is None and "fill_median" in options:
            options = [o for o in options if o != "fill_median"]
            default = "flag" if default == "fill_median" else default
        texts = {k: v for k, v in _null_texts(col, t.rows, median).items() if k in options}
        key = col.role in ("primary_key", "foreign_key", "identifier")
        impact: Impact = "High" if key or col.null_pct >= 10 else "Medium" if col.null_pct >= 1 else "Low"
        step = _step(
            t, f"{col.name}::nulls", kind="handle_nulls", impact=impact, category="Null Handling",
            title="", description="", columns=[col.name], rows_affected=col.null_count,
            fill_value=median, types={col.name: col.detected_type},
        )
        steps.append(_with_strategies(step, texts, default))
    return steps


DETECTORS = [
    _detect_total_rows, _detect_whitespace, _detect_duplicates, _detect_case_variants, _detect_synonyms,
    _detect_booleans, _detect_casts, _detect_european, _detect_date_format, _detect_types, _detect_excel_serial,
    _detect_date_outliers, _detect_sentinels, _detect_key_duplicates, _detect_orphans, _detect_nulls,
]


def suggest_steps(table: TableProfile, df: pd.DataFrame, ctx: RuleContext | None = None) -> list[CleaningStep]:
    """Rule-based cleaning suggestions for one profiled table (status defaults to pending)."""
    ctx = ctx or RuleContext(profiles={table.name: table}, sources={})
    steps: list[CleaningStep] = []
    for detect in DETECTORS:
        try:
            steps.extend(detect(table, df, ctx))
        except Exception as exc:  # one unusual column must never hide the other suggestions
            logger.warning("Cleaning detector %s failed on %s: %s", detect.__name__, table.name, exc)
            ctx.warnings.append(f"{table.name}: the {detect.__name__.removeprefix('_detect_').replace('_', ' ')} check was skipped ({type(exc).__name__}).")
    _fit_null_options(steps)
    return steps


def _fit_null_options(steps: list[CleaningStep]) -> None:
    """Columns another suggestion converts (to dates, booleans, or numbers from European text)
    cannot be filled with 'Unknown' or a median computed on the raw text; offer remove/flag only."""
    converted = {c for s in steps if s.kind in ("normalise_booleans", "cast_european", "date_format", "excel_serial_dates") for c in s.columns}
    for s in steps:
        if s.kind == "handle_nulls" and s.columns[0] in converted and {"fill_unknown", "fill_median"} & set(s.strategies):
            texts = {k: tuple(v) for k, v in s.strategy_text.items() if k in ("remove_rows", "flag")}
            _with_strategies(s, texts, "flag")


def apply_decisions(steps: list[CleaningStep], decisions: dict) -> None:
    """Merge stored accept/skip/strategy choices into freshly generated steps."""
    for step in steps:
        choice = decisions.get(step.id) or {}
        if choice.get("status") in ("pending", "accepted", "skipped"):
            step.status = choice["status"]
        strategy = choice.get("strategy")
        if strategy in step.strategies and strategy != step.strategy:
            step.strategy = strategy
            step.title, step.description = step.strategy_text[strategy]


# --- AI synonyms ----------------------------------------------------------------------

class _AIGroup(BaseModel):
    table: str
    column: str
    canonical: str
    variants: list[str]


class _AIAnswer(BaseModel):
    groups: list[_AIGroup]


MAX_AI_COLUMNS = 25
MAX_AI_VALUES = 60


def synonym_candidates(report: QualityReport, sources: list[SourceTable]) -> list[dict]:
    """Columns worth asking the AI about: categories/places with 2-150 distinct values.

    Kept small (top values of at most 25 columns) so a free-tier model answers within its deadline.
    """
    frames = {s.name: s.df for s in sources}
    out = []
    for t in report.tables:
        if t.name not in frames:
            continue
        for c in t.column_profiles:
            if c.detected_type in ("category", "location") and 2 <= c.distinct_count <= 150:
                values = _text(frames[t.name][c.name]).dropna().str.strip()
                counts = values[values.str.len() <= 60].value_counts().head(MAX_AI_VALUES)
                if counts.index.str.lower().nunique() >= 2:
                    out.append({"table": t.name, "column": c.name, "values": {str(k): int(v) for k, v in counts.items()}})
    return out[:MAX_AI_COLUMNS]


def ai_synonyms(report: QualityReport, sources: list[SourceTable], llm: LLMProvider) -> dict[str, dict[str, str]]:
    """Ask the LLM which spellings mean the same thing. Raises LLMError on AI failures."""
    candidates = synonym_candidates(report, sources)
    if not candidates:
        return {}
    prompt = PROMPT_PATH.read_text(encoding="utf-8").replace("{columns}", json.dumps(candidates, ensure_ascii=False, separators=(",", ":")))
    answer = llm.generate_text(prompt, json_schema=_AIAnswer)
    known = {(c["table"], c["column"]): {v.lower(): v for v in c["values"]} for c in candidates}
    mappings: dict[str, dict[str, str]] = defaultdict(dict)
    for g in answer.groups:
        values = known.get((g.table, g.column))
        canonical = g.canonical.strip()
        if values is None or not canonical or len(canonical) > 80:
            continue
        if canonical.islower() or canonical.isupper():
            canonical = values.get(canonical.lower(), canonical)  # prefer an existing spelling
        for v in g.variants:
            if v.strip().lower() in values and v.strip().lower() != canonical.lower():
                mappings[f"{g.table}::{g.column}"][v.strip().lower()] = canonical
    return dict(mappings)


def ai_error_note(exc: Exception) -> str:
    return str(exc) if isinstance(exc, LLMError) else f"AI request failed ({type(exc).__name__})"


# --- plan -----------------------------------------------------------------------------

@dataclass
class TablePipeline:
    src: SourceTable
    steps: list[CleaningStep]  # suggestions shown to the user
    accepted: list[CleaningStep]  # accepted suggestions + derived steps (e.g. unknown members)
    result: PipelineResult


def table_pipelines(
    report: QualityReport,
    sources: list[SourceTable],
    decisions: dict,
    ai_map: dict[str, dict[str, str]] | None = None,
) -> tuple[dict[str, TablePipeline], list[str]]:
    """Suggestions + decisions + cleaned result for every profiled table."""
    profiles = {t.name: t for t in report.tables}
    srcmap = {s.name: s for s in sources if s.name in profiles}
    ctx = RuleContext(profiles=profiles, sources=srcmap, ai_synonyms=ai_map or {})

    steps_by_table: dict[str, list[CleaningStep]] = {}
    for name, src in srcmap.items():
        steps = suggest_steps(profiles[name], src.df, ctx)
        apply_decisions(steps, decisions)
        steps_by_table[name] = steps

    # Cross-table effects: accepted orphan mappings add an "Unknown" row to the referenced table.
    derived: dict[str, dict[str, CleaningStep]] = defaultdict(dict)
    lookups: dict[tuple[str, str], set[str]] = {}
    for steps in steps_by_table.values():
        for s in steps:
            if s.kind != "orphan_keys" or s.status != "accepted":
                continue
            target, key = s.params["target_table"], s.params["target_column"]
            lookups[(target, key)] = set(_text(srcmap[target].df[key]).dropna())
            if s.strategy == "unknown_member":
                derived[target][key] = CleaningStep(
                    id=f"{target}::{key}::unknown_member", table=target, kind="unknown_member", impact="Low",
                    category="Relationships", title=f"Add an '{UNKNOWN}' member to {target}",
                    description=f"Lets rows with unmatched {key} values relate to the '{UNKNOWN}' member.",
                    columns=[key], rows_affected=1, affected_pct=0.0, status="accepted", params={"key": key},
                )

    pipelines: dict[str, TablePipeline] = {}
    warnings = list(ctx.warnings)
    for name, src in srcmap.items():
        accepted = [s for s in steps_by_table[name] if s.status == "accepted"] + list(derived[name].values())
        result = run_pipeline(src, accepted, lookups)
        warnings += result.warnings
        pipelines[name] = TablePipeline(src=src, steps=steps_by_table[name], accepted=accepted, result=result)
    return pipelines, warnings


def _score_after(table: TableProfile, result: PipelineResult, accepted: list[CleaningStep]) -> int:
    """Same formula as profiling._table_score, applied to the cleaned table."""
    df = result.df
    cells = df.size or 1
    completeness = 1 - df.isna().sum().sum() / cells
    uniqueness = 1 - df.astype("string").duplicated().sum() / max(len(df), 1)
    fixed = {(s.kind, c) for s in accepted if not s.error for c in s.columns}
    clean = sum(
        1 for c in table.column_profiles
        if (not c.needs_casting or ("cast_numeric", c.name) in fixed)
        and (not c.inconsistent_values or ("standardise_categories", c.name) in fixed)
    )
    validity = clean / max(len(table.column_profiles), 1)
    return round(100 * (0.5 * completeness + 0.3 * uniqueness + 0.2 * validity))


def build_plan(
    report: QualityReport,
    sources: list[SourceTable],
    decisions: dict,
    ai_map: dict[str, dict[str, str]] | None = None,
) -> CleaningPlan:
    profiles = {t.name: t for t in report.tables}
    pipelines, warnings = table_pipelines(report, sources, decisions, ai_map)
    steps: list[CleaningStep] = []
    tables: list[TableCleaning] = []
    weighted_after = 0.0
    for name, p in pipelines.items():
        profile = profiles[name]
        weighted_after += _score_after(profile, p.result, p.accepted) * max(profile.rows, 1)
        steps.extend(p.steps)
        tables.append(TableCleaning(
            name=name, source=p.src.filename + (f" › {p.src.sheet}" if p.src.sheet else ""),
            rows_before=profile.rows, rows_after=len(p.result.df),
            accepted=sum(1 for s in p.steps if s.status == "accepted"), m_script=p.result.m_script,
            structure_notes=structure_notes(p.src.df),
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
        warnings=warnings,
    )

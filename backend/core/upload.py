"""Read uploaded CSV / Excel files into DataFrames. (Spec Module 1)

Every cell is read as text so that profiling can detect types itself
(e.g. "$1,234.50" is currency, "00123" is an ID, not the number 123).

Structure is repaired here, before profiling, because every later step depends on it:
title rows above the real header, blank or duplicate column names, ragged CSV rows,
fully empty rows/columns and null tokens ("NA", "N/A", "null", "-"). What was done is
recorded in `df.attrs["structure"]` so the Power Query source steps can repeat it exactly.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pandas as pd

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
# Text that means "no value" in exports; treated as null both here and in the generated M.
NULL_TOKENS = ("NA", "N/A", "#N/A", "NULL", "NONE", "NAN", "-", "--", "?", "(BLANK)", "#VALUE!", "#REF!", "#DIV/0!")
# Power Query code pages for the encodings we accept.
CODE_PAGES = {"utf-8-sig": 65001, "cp1252": 1252, "latin-1": 28591}
HEADER_SCAN_ROWS = 10


class UploadError(ValueError):
    """User-facing problem with an uploaded file."""


def validate_upload(filename: str, size_bytes: int, max_mb: int) -> str:
    """Return the normalised extension, or raise UploadError."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadError(f"{filename}: only .csv, .xlsx and .xls files are supported")
    if size_bytes == 0:
        raise UploadError(f"{filename}: file is empty")
    if size_bytes > max_mb * 1024 * 1024:
        raise UploadError(f"{filename}: file is larger than {max_mb} MB")
    return ext


def table_name(filename: str, sheet: str | None = None, multi_sheet: bool = False) -> str:
    """Power BI-friendly table name: letters, digits and underscores."""
    stem = Path(filename).stem
    raw = f"{stem}_{sheet}" if multi_sheet and sheet else stem
    name = re.sub(r"[^0-9A-Za-z_]+", "_", raw).strip("_")
    return name or "Table"


def _decode(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UploadError("could not decode file text")


def _sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def csv_delimiter(content: bytes) -> str:
    """Delimiter used by a CSV upload (the Power Query source step needs it)."""
    return _sniff_delimiter(_decode(content)[0])


def _csv_rows(content: bytes) -> tuple[list[list[str | None]], str]:
    text, encoding = _decode(content)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_sniff_delimiter(text))
    return [list(r) for r in reader], encoding


def _excel_sheets(content: bytes, ext: str) -> dict[str, list[list[str | None]]]:
    engine = "openpyxl" if ext == ".xlsx" else None
    sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None, dtype=str, engine=engine, keep_default_na=False)
    return {str(name): df.where(df.notna(), None).values.tolist() for name, df in sheets.items()}


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _looks_like_header(row: list) -> bool:
    cells = [str(v).strip() for v in row if not _is_blank(v)]
    if len(cells) < max(2, len(row) * 0.6):
        return False
    texty = sum(1 for c in cells if not re.fullmatch(r"[-+$€£₹¥%.,\d\s/:]+", c))
    # Repeated header names happen (they get a suffix later), so "mostly unique" is enough.
    return texty >= len(cells) * 0.8 and len(set(cells)) >= len(cells) * 0.7


def _header_row(rows: list[list]) -> int:
    """Index of the real header row: row 0 unless it is a sparse title row above a proper header."""
    if not rows or _looks_like_header(rows[0]):
        return 0
    filled0 = sum(1 for v in rows[0] if not _is_blank(v))
    width = max(len(r) for r in rows[:HEADER_SCAN_ROWS])
    if filled0 >= width * 0.5:
        return 0
    for k in range(1, min(HEADER_SCAN_ROWS, len(rows) - 1)):
        if _looks_like_header(rows[k]):
            return k
    return 0


def column_names(raw: list) -> list[str]:
    """Header cells -> unique, non-blank names (blank -> column_3, repeated -> name_2)."""
    names: list[str] = []
    used: set[str] = set()
    for i, value in enumerate(raw):
        base = "" if _is_blank(value) else re.sub(r"\s+", " ", str(value)).strip()
        base = base or f"column_{i + 1}"
        name, n = base, 1
        while name.lower() in used:  # Power BI column names are case-insensitive
            n += 1
            name = f"{base}_{n}"
        used.add(name.lower())
        names.append(name)
    return names


def _frame(rows: list[list], encoding: str | None) -> pd.DataFrame:
    """Rows of cells -> cleaned text DataFrame with structure notes in df.attrs."""
    width = max((len(r) for r in rows), default=0)
    rows = [list(r) + [None] * (width - len(r)) for r in rows]
    header = _header_row(rows)
    names = column_names(rows[header] if rows else [])
    body = rows[header + 1 :]
    df = pd.DataFrame(body, columns=names, dtype="object") if names else pd.DataFrame()

    # Trim, blank -> NA, null tokens -> NA (the M "Blanks As Null" step does the same).
    def clean(v):
        if _is_blank(v):
            return pd.NA
        text = str(v).strip()
        return pd.NA if text.upper() in NULL_TOKENS else text

    df = df.map(clean) if not df.empty else df
    raw = rows[header] if rows else []
    empty_cols = [c for c in df.columns if df[c].isna().all()] if len(df) else []
    raw_blank = [n for n, v in zip(names, raw) if _is_blank(v)]
    renamed = sum(1 for n, v in zip(names, raw) if not _is_blank(v) and n != re.sub(r"\s+", " ", str(v)).strip())
    df = df.drop(columns=empty_cols).dropna(how="all")
    df = df.astype("string") if len(df.columns) else df
    df.attrs["structure"] = {
        "header_row": header,
        "names": names,
        "columns": width,
        "dropped_columns": empty_cols,
        "blank_names": raw_blank,
        "duplicate_names": renamed,
        "encoding": encoding,
    }
    return df


def read_tables(filename: str, content: bytes) -> dict[str, tuple[str | None, pd.DataFrame]]:
    """Parse a file into {table_name: (sheet_name, DataFrame)}."""
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".csv":
            rows, encoding = _csv_rows(content)
            df = _frame(rows, encoding)
            if df.empty or not len(df.columns):
                raise UploadError(f"{filename}: no data found")
            return {table_name(filename): (None, df)}
        sheets = _excel_sheets(content, ext)
    except UploadError:
        raise
    except Exception as exc:  # parsers raise many format-specific errors
        raise UploadError(f"{filename}: could not be read ({exc.__class__.__name__})") from exc

    frames = {name: _frame(rows, None) for name, rows in sheets.items()}
    # Skip blank sheets (common in hand-made workbooks).
    frames = {name: df for name, df in frames.items() if len(df.columns) and len(df)}
    if not frames:
        raise UploadError(f"{filename}: no data found")
    multi = len(frames) > 1
    tables: dict[str, tuple[str | None, pd.DataFrame]] = {}
    for sheet, df in frames.items():
        name = table_name(filename, sheet, multi)
        while name in tables:  # sheets whose names differ only by punctuation
            name += "_2"
        tables[name] = (sheet, df)
    return tables


def structure_notes(df: pd.DataFrame) -> list[str]:
    """Human-readable list of the structure fixes applied while reading."""
    s = df.attrs.get("structure") or {}
    notes = []
    if s.get("header_row"):
        notes.append(f"Header found on row {s['header_row'] + 1}; {s['header_row']} title row(s) above it skipped.")
    if s.get("blank_names"):
        notes.append(f"{len(s['blank_names'])} blank column name(s) named {', '.join(s['blank_names'][:3])}.")
    if s.get("duplicate_names"):
        notes.append(f"{s['duplicate_names']} repeated column name(s) given a numeric suffix.")
    if s.get("dropped_columns"):
        notes.append(f"{len(s['dropped_columns'])} completely empty column(s) removed.")
    if s.get("encoding") and s["encoding"] != "utf-8-sig":
        notes.append(f"File encoding detected as {s['encoding']} (not UTF-8).")
    return notes

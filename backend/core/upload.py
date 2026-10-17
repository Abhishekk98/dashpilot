"""Read uploaded CSV / Excel files into DataFrames. (Spec Module 1)

Every cell is read as text so that profiling can detect types itself
(e.g. "$1,234.50" is currency, "00123" is an ID, not the number 123).
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pandas as pd

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


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


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
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
    return _sniff_delimiter(_decode(content))


def _read_csv(content: bytes) -> pd.DataFrame:
    text = _decode(content)
    return pd.read_csv(io.StringIO(text), sep=_sniff_delimiter(text), dtype=str, keep_default_na=True, skipinitialspace=True)


def _read_excel(content: bytes, ext: str) -> dict[str, pd.DataFrame]:
    engine = "openpyxl" if ext == ".xlsx" else None
    sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, dtype=str, engine=engine)
    # Skip blank sheets (common in hand-made workbooks).
    return {name: df for name, df in sheets.items() if not df.dropna(how="all").empty}


def read_tables(filename: str, content: bytes) -> dict[str, tuple[str | None, pd.DataFrame]]:
    """Parse a file into {table_name: (sheet_name, DataFrame)}."""
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".csv":
            return {table_name(filename): (None, _clean_frame(_read_csv(content)))}
        sheets = _read_excel(content, ext)
    except UploadError:
        raise
    except Exception as exc:  # pandas raises many parser-specific errors
        raise UploadError(f"{filename}: could not be read ({exc.__class__.__name__})") from exc

    if not sheets:
        raise UploadError(f"{filename}: no data found")
    multi = len(sheets) > 1
    return {table_name(filename, sheet, multi): (sheet, _clean_frame(df)) for sheet, df in sheets.items()}


def _clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Drop fully empty rows/columns and normalise header text."""
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() or f"column_{i + 1}" for i, c in enumerate(df.columns)]
    # Treat whitespace-only strings as missing.
    return df.apply(lambda s: s.astype("string").str.strip()).replace("", pd.NA)

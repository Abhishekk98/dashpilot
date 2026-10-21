"""Opening a built PBIP where it actually lives.

The model reads its files through the DataFolder parameter (an absolute path, as Power Query needs).
Two ways keep it right wherever the project ends up:
- `Open Dashboard.cmd` in the package: sets DataFolder to the Data folder next to itself, then opens
  the .pbip (works after unzipping anywhere; paths with spaces/unicode; safe to run again).
- "Save & Open in Power BI" (the backend runs on the user's machine): copies the build to a local
  folder, points DataFolder there and launches Power BI Desktop.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

from core import tmdl

OPEN_CMD_NAME = "Open Dashboard.cmd"

# The batch part only hands its own location to PowerShell, which runs the script after the marker
# (read from this file, so no quoting rules of cmd apply to it). Env vars carry unicode paths intact.
_OPEN_CMD = r"""@echo off
rem Opens this Power BI project with DataFolder set to the Data folder next to this file.
setlocal
set "DP_ROOT=%~dp0"
set "DP_SELF=%~f0"
powershell -NoProfile -Command "$s = [IO.File]::ReadAllText($env:DP_SELF); Invoke-Expression $s.Substring($s.LastIndexOf('#PS-' + 'SCRIPT'))"
if errorlevel 1 (
  echo.
  echo Could not open the dashboard. See the message above, or open the .pbip and set DataFolder by hand ^(README.md^).
  pause
)
exit /b

#PS-SCRIPT
$ErrorActionPreference = 'Stop'
try {
  $root = $env:DP_ROOT
  $data = Join-Path $root 'Data\'
  if (-not (Test-Path -LiteralPath $data)) { throw "The Data folder is missing next to this file: $data" }
  $model = Get-ChildItem -LiteralPath $root -Directory | Where-Object { $_.Name -like '*.SemanticModel' } | Select-Object -First 1
  if (-not $model) { throw 'No .SemanticModel folder next to this file.' }
  $tmdl = Join-Path $model.FullName 'definition\expressions.tmdl'
  $text = [IO.File]::ReadAllText($tmdl)
  $value = '"' + $data.Replace('"', '""') + '"'
  $new = [regex]::Replace($text, '(?m)^(expression DataFolder = )"(?:[^"]|"")*"', { param($m) $m.Groups[1].Value + $value })
  if ($new -ne $text) { [IO.File]::WriteAllText($tmdl, $new, (New-Object System.Text.UTF8Encoding $false)) }
  Write-Host "DataFolder = $data"
  $pbip = Get-ChildItem -LiteralPath $root -File | Where-Object { $_.Extension -eq '.pbip' } | Select-Object -First 1
  if (-not $pbip) { throw 'No .pbip file next to this file.' }
  if ($env:DP_NO_LAUNCH) { exit 0 }
  try { Invoke-Item -LiteralPath $pbip.FullName }
  catch {
    $exe = Join-Path $env:ProgramFiles 'Microsoft Power BI Desktop\bin\PBIDesktop.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Power BI Desktop is not installed (get it from the Microsoft Store or microsoft.com/power-bi).' }
    Start-Process -FilePath $exe -ArgumentList ('"' + $pbip.FullName + '"')
  }
  Write-Host 'Opening in Power BI Desktop... click Refresh if the visuals are empty.'
} catch {
  Write-Host $_.Exception.Message -ForegroundColor Red
  exit 1
}
"""

OPEN_CMD = _OPEN_CMD.replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii")

_DATA_FOLDER = re.compile(r'(?m)^(expression DataFolder = )"(?:[^"]|"")*"')


class OpenError(ValueError):
    """User-facing problem saving/opening the project locally."""


class TargetExists(OpenError):
    """The folder already holds a saved copy; overwrite only when the user confirms."""


def set_data_folder(expressions: str, folder: str) -> str:
    """expressions.tmdl with DataFolder pointing at `folder` (the same edit Open Dashboard.cmd makes)."""
    folder = folder if folder.endswith(("\\", "/")) else folder + "\\"
    if not _DATA_FOLDER.search(expressions):
        raise OpenError("The model has no DataFolder parameter.")
    return _DATA_FOLDER.sub(lambda m: m.group(1) + tmdl.m_text(folder), expressions, count=1)


def documents_dir() -> Path:
    """The user's Documents folder (also when Windows redirects it, e.g. to OneDrive)."""
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415
            from ctypes import wintypes  # noqa: PLC0415

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

            docs = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(docs), 0, None, ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                if path:
                    return Path(path)
        except (OSError, AttributeError):
            pass
    return Path.home() / "Documents"


def default_target(folder: str) -> str:
    return str(documents_dir() / "DashPilot" / folder)


def clean_target(value: str | None, folder: str) -> Path:
    raw = (value or "").strip() or default_target(folder)
    path = Path(raw)
    if len(raw) > 200 or re.search(r'["<>|?*\n\r]', raw) or not path.is_absolute() or ".." in path.parts:
        raise OpenError("Choose a full folder path, for example C:\\Users\\you\\Documents\\DashPilot\\Sales.")
    if len(path.parts) < 2:
        raise OpenError("Choose a folder, not the root of a drive.")
    return path


def launch(path: Path) -> None:
    """Open the .pbip with its registered app (Power BI Desktop)."""
    if sys.platform != "win32":
        raise OSError("Power BI Desktop runs on Windows only.")
    os.startfile(str(path))  # noqa: S606 - local file the backend just wrote


def save_copy(tree: Path, folder: str, target: Path, overwrite: bool) -> Path:
    """Copy the built PBIP tree into `target` with DataFolder = target\\Data\\. Returns the .pbip path."""
    pbip = target / f"{folder}.pbip"
    if target.exists() and any(target.iterdir()):
        if not pbip.exists():
            raise OpenError(f"{target} already has other files. Choose an empty or new folder.")
        if not overwrite:
            raise TargetExists(f"{target} already has a saved copy of this dashboard. Replace it?")
    try:
        if pbip.exists():
            # Only what DashPilot wrote there; anything else the user added stays.
            for name in (f"{folder}.Report", f"{folder}.SemanticModel", "Data"):
                if (target / name).exists():
                    shutil.rmtree(target / name)
        shutil.copytree(tree, target, dirs_exist_ok=True)
        expressions = target / f"{folder}.SemanticModel" / "definition" / "expressions.tmdl"
        text = expressions.read_text(encoding="utf-8")
        expressions.write_text(set_data_folder(text, str(target / "Data")), encoding="utf-8", newline="")
    except PermissionError:
        raise OpenError(f"Windows blocked writing to {target}. Close the dashboard in Power BI Desktop and try again.") from None
    except OSError as exc:
        raise OpenError(f"Could not save to {target}: {exc.strerror or exc}") from None
    return pbip

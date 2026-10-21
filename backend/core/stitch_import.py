"""Design method A: Google Stitch exports.

`read_export` accepts Stitch's `code.html` or its export zip (HTML + `screen.png`). Zips are read in
memory only (never extracted to disk) with limits on entries, sizes and compression ratio, and any
absolute, parent-relative or symlink entry is rejected.

`upload` stores the export under storage/{id}/design/stitch/ and runs the shared Design Import on it
(core.design_import_service.run_import): title matching (exact, fuzzy, AI), clean background from
Stitch's own render, theme from Stitch's colors, and the fidelity report against screen.png.
Selecting it (planner_service.select_variant("stitch")) writes selected.html like the other methods.
"""

from __future__ import annotations

import io
import json
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

from pydantic import BaseModel

from core.projects import Project, ProjectStore
from core.style_profile import StyleError, open_image
from llm import LLMProvider

MAX_UPLOAD = 25 * 1024 * 1024
MAX_HTML = 5 * 1024 * 1024
MAX_ENTRIES = 300
MAX_UNCOMPRESSED = 60 * 1024 * 1024
MAX_RATIO = 100
STITCH_DIR = "design/stitch"
VARIANT_ID = "stitch"


class StitchError(ValueError):
    """User-facing problem with the uploaded export."""


@dataclass
class StitchExport:
    name: str
    html: str
    screen: bytes | None
    files: list[str]


def _html(data: bytes, name: str) -> str:
    if len(data) > MAX_HTML:
        raise StitchError(f"{name} is larger than 5 MB.")
    html = data.decode("utf-8-sig", errors="replace")
    low = html.lower()
    if "<" not in html or not any(t in low for t in ("<div", "<body", "<section", "<main")):
        raise StitchError(f"{name} does not look like an HTML page.")
    return html


def _safe_name(info: zipfile.ZipInfo) -> PurePosixPath:
    raw = info.filename.replace("\\", "/")
    path = PurePosixPath(raw)
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":") or ".." in path.parts:
        raise StitchError(f"The zip contains an unsafe path ({info.filename[:80]}).")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise StitchError(f"The zip contains a symbolic link ({info.filename[:80]}).")
    return path


def read_export(filename: str, data: bytes) -> StitchExport:
    name = (filename or "design").replace("\\", "/").split("/")[-1][:120]
    if not data:
        raise StitchError("The file is empty.")
    if len(data) > MAX_UPLOAD:
        raise StitchError("Exports must be 25 MB or smaller.")
    if not data.startswith(b"PK\x03\x04"):
        if not name.lower().endswith((".html", ".htm")):
            raise StitchError("Upload Stitch's code.html or its export .zip (HTML + screen.png).")
        return StitchExport(name=name, html=_html(data, name), screen=None, files=[name])
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise StitchError("The zip file is damaged.") from None
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_ENTRIES:
        raise StitchError(f"The zip has more than {MAX_ENTRIES} files.")
    total = 0
    paths = {}
    for info in infos:
        paths[info.filename] = _safe_name(info)
        total += info.file_size
        if info.file_size > MAX_UNCOMPRESSED or total > MAX_UNCOMPRESSED:
            raise StitchError("The zip unpacks to more than 60 MB.")
        if info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
            raise StitchError("The zip is suspiciously compressed (zip bomb protection).")
    htmls = [i for i in infos if paths[i.filename].suffix.lower() in (".html", ".htm")]
    if not htmls:
        raise StitchError("The zip has no HTML page. Export the design from Stitch as code (code.html).")
    page = next((i for i in htmls if paths[i.filename].name.lower() == "code.html"), None)
    if page is None:
        if len(htmls) > 1:
            raise StitchError("The zip has several HTML pages; upload the one dashboard's code.html.")
        page = htmls[0]
    images = [i for i in infos if paths[i.filename].suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
    shot_info = next((i for i in images if paths[i.filename].stem.lower() == "screen"), images[0] if len(images) == 1 else None)
    screen = None
    if shot_info is not None:
        raw = zf.read(shot_info)
        try:
            open_image(raw)
            screen = raw
        except StyleError:
            screen = None  # a broken screenshot only means we compare against our own render
    return StitchExport(name=name, html=_html(zf.read(page), paths[page.filename].name), screen=screen,
                        files=[str(paths[i.filename]) for i in infos][:50])


# --- Option A service ------------------------------------------------------------------------------

class StitchUpload(BaseModel):
    filename: str
    has_screen: bool
    files: list[str] = []
    uploaded_at: datetime
    label: str


def _dir(store: ProjectStore, project: Project):
    path = store.project_dir(project.id) / STITCH_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_upload(store: ProjectStore, project: Project) -> StitchUpload | None:
    meta = store.project_dir(project.id) / STITCH_DIR / "meta.json"
    return StitchUpload.model_validate_json(meta.read_text(encoding="utf-8")) if meta.exists() else None


def stitch_html(store: ProjectStore, project: Project) -> str | None:
    path = store.project_dir(project.id) / STITCH_DIR / "code.html"
    return path.read_text(encoding="utf-8") if path.exists() else None


def upload(store: ProjectStore, project: Project, llm: LLMProvider | None, filename: str, data: bytes):
    """Store a Stitch export and import it (mapping, background, theme, fidelity)."""
    from core.design_import_service import ImportError_, run_import  # noqa: PLC0415

    try:
        export = read_export(filename, data)
    except StitchError as exc:
        raise ImportError_(str(exc)) from None
    folder = _dir(store, project)
    (folder / "code.html").write_text(export.html, encoding="utf-8")
    shot = folder / "screen.png"
    if export.screen:
        shot.write_bytes(export.screen)
    else:
        shot.unlink(missing_ok=True)
    meta = StitchUpload(filename=export.name, has_screen=export.screen is not None, files=export.files,
                        uploaded_at=datetime.now(timezone.utc), label=f"Option A · Google Stitch ({export.name})")
    (folder / "meta.json").write_text(json.dumps(meta.model_dump(mode="json"), indent=2), encoding="utf-8")
    return run_import(store, project, llm, "option_a", meta.label, export.html, screen=export.screen)

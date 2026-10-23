"""Glue between stored projects and the design import (keeps routes thin).

One import per plan page: page 1 lives in storage/{id}/design/, page n in design/p{n}/.
Files per page (read by the PBIP builder in Step 9):
  source.html      the imported design (Option B's selected.html, or the uploaded file)
  import.json      detected boxes, mapping, palette, fonts, theme, issues
  background.png   1280x720 canvas with the mapped cards' contents hidden
  theme.json       Power BI report theme
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from core.context_service import get_context
from core.design_ai import plan_signature
from core.design_fidelity import FidelityReport, score
from core.design_import import (
    DetectedBox, MappingItem, ThemeColor, autofix_mapping, build_theme, extract, match, named_by_label, render_design, title_kept, validate_mapping,
)
from core.planner import DashboardPlan, PlanVisual, page_plan
from core.planner_service import DESIGN_FILE, PLAN_FILE
from core.projects import Project, ProjectStore
from llm import LLMProvider

logger = logging.getLogger(__name__)
IMPORT_FILE = "design/import.json"  # page 1; page n: design/p{n}/import.json


class ImportError_(ValueError):
    """User-facing problem (no plan, no design, bad upload)."""


class DesignImport(BaseModel):
    source: Literal["option_a", "option_b", "upload"]
    source_name: str
    source_hash: str
    plan_signature: str
    scripts: bool = False  # uploaded Stitch exports need their Tailwind script to render
    source_w: int = 1280
    source_h: int = 720
    scale: float = 1.0  # < 1 when the design was larger than 1280x720 and scaled into the canvas
    fidelity: FidelityReport | None = None
    fidelity_override: bool = False  # the user accepted a fidelity below the threshold
    boxes: list[DetectedBox]
    mapping: list[MappingItem]
    palette: list[ThemeColor]
    heading_font: str
    body_font: str
    theme: dict
    issues: list[str] = []
    valid: bool = False
    notes: list[str] = []
    skipped: int = 0
    background_version: str = ""
    imported_at: datetime | None = None


class ImportResponse(BaseModel):
    design: DesignImport
    visuals: list[PlanVisual]
    html: str
    notes: list[str] = []
    page: int = 1
    pages: list[str] = ["Overview"]


def import_file(page: int) -> str:
    return IMPORT_FILE if page == 1 else f"design/p{page}/import.json"


def page_dir(store: ProjectStore, project: Project, page: int = 1):
    path = store.project_dir(project.id) / "design" / ("" if page == 1 else f"p{page}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _dir(store: ProjectStore, project: Project):
    return page_dir(store, project, 1)


def _page(store: ProjectStore, project: Project, page: int) -> tuple[DashboardPlan, DashboardPlan]:
    """(whole plan, the page as a single-page plan)."""
    plan = _plan(store, project)
    if not 1 <= page <= len(plan.pages):
        raise ImportError_(f"The plan has {len(plan.pages)} page(s); there is no page {page}.")
    return plan, page_plan(plan, page)


def _plan(store: ProjectStore, project: Project) -> DashboardPlan:
    stored = store.read_json(project.id, PLAN_FILE).get("plan")
    if not stored:
        raise ImportError_("No dashboard plan yet. Finish Step 7 (Design Method) first.")
    plan = DashboardPlan.model_validate(stored)
    if not plan.valid:
        raise ImportError_("The dashboard plan has issues. Fix them in Step 7 first.")
    return plan


def _hash(html: str) -> str:
    return hashlib.sha1(html.encode("utf-8")).hexdigest()[:16]


def selected_name(page: int) -> str:
    return "selected.html" if page == 1 else f"selected_p{page}.html"


def _selected(store: ProjectStore, project: Project, page: int = 1) -> tuple[str, str] | None:
    path = _dir(store, project) / selected_name(page)
    if not path.exists():
        return None
    design = store.read_json(project.id, DESIGN_FILE)
    if design.get("selected_label"):
        return path.read_text(encoding="utf-8"), design["selected_label"]
    chosen = next((v for v in design.get("variants", []) if v.get("id") == design.get("selected")), None)
    return path.read_text(encoding="utf-8"), f"Option B · {chosen['label']}" if chosen else "Selected design"


def _method(label: str) -> str:
    return "option_a" if label.startswith("Option A") else "option_b"


STITCH_SCREEN = "stitch/screen.png"  # Option A: Stitch's own screenshot from the export zip (page n: stitch/p{n}/screen.png)
SOURCE_SCREEN = "source_screen.png"  # the screenshot belonging to the imported design (fidelity reference)


def _stitch_screen(store: ProjectStore, project: Project, page: int = 1) -> bytes | None:
    path = _dir(store, project) / (STITCH_SCREEN if page == 1 else f"stitch/p{page}/screen.png")
    return path.read_bytes() if path.exists() else None


def _finish(store: ProjectStore, project: Project, plan: DashboardPlan, imp: DesignImport, html: str, page: int = 1,
            pages: list[str] | None = None) -> ImportResponse:
    if imp.source == "option_a":
        fix_notes = autofix_mapping(plan, imp.mapping, imp.boxes)
        if fix_notes:
            imp.notes.extend(fix_notes)
    imp.issues = validate_mapping(plan, imp.mapping, imp.boxes)
    imp.valid = not imp.issues

    folder = page_dir(store, project, page)
    boxes = {b.id: b for b in imp.boxes}
    titles = {v.id: v.title for v in plan.visuals}
    for m in imp.mapping:
        m.pbi_title = m.placed and not title_kept(titles.get(m.visual_id, ""), boxes.get(m.box_id or ""))
    hide = [m.box_id for m in imp.mapping if m.box_id and m.placed]
    hide_titles = [m.box_id for m in imp.mapping if m.box_id and (m.pbi_title or named_by_label(titles.get(m.visual_id, ""), boxes.get(m.box_id)))]
    original, background = render_design(html, hide, imp.scripts, hide_titles)

    # The background is always our render of the design with the mapped cards' dummy contents hidden.
    # Stitch's screen.png still has its fake charts and numbers (they would show under the Power BI
    # visuals), so it is only the fidelity reference.
    screen_path = folder / SOURCE_SCREEN
    (folder / "background.png").write_bytes(background)
    (folder / "original.png").write_bytes(original)

    imp.fidelity = score(original, background, imp.boxes, imp.mapping, titles,
                         screen_path.read_bytes() if screen_path.exists() else None, imp.source_w, imp.source_h, imp.scale)
    imp.background_version = str(int(time.time() * 1000))
    (folder / "theme.json").write_text(json.dumps(imp.theme, indent=2), encoding="utf-8")
    store.write_json(project.id, import_file(page), imp.model_dump(mode="json"))
    return ImportResponse(design=imp, visuals=plan.visuals, html=html, notes=imp.notes, page=page, pages=pages or plan.pages)


def run_import(store: ProjectStore, project: Project, llm: LLMProvider | None, source: str, name: str, html: str,
               scripts: bool = False, screen: bytes | None = None, page: int = 1) -> ImportResponse:
    whole, plan = _page(store, project, page)
    folder = page_dir(store, project, page)
    (folder / "source.html").write_text(html, encoding="utf-8")
    if screen:
        (folder / SOURCE_SCREEN).write_bytes(screen)
    else:
        (folder / SOURCE_SCREEN).unlink(missing_ok=True)
    # Stitch exports style themselves with the Tailwind CDN script; it runs with all other network blocked.
    scripts = scripts or "cdn.tailwindcss.com" in html
    fallback_note: str | None = None
    try:
        found = extract(html, scripts)
        if not found.boxes:
            raise ValueError("No containers found in design.")
    except Exception as exc:
        if source == "option_a":
            logger.warning("Stitch import failed, falling back to built-in template: %s", exc)
            fallback_note = f"⚠️ Warning: Stitch design could not be parsed ({str(exc).splitlines()[0][:100]}). Fell back to built-in template layout."
            from core.design_ai import template_html  # noqa: PLC0415
            context = get_context(store, project)
            html = template_html(plan, context, archetype="dark_neon")
            found = extract(html, False)
            (folder / "source.html").write_text(html, encoding="utf-8")
        else:
            logger.warning("Design render failed: %s", exc)
            raise ImportError_(f"Could not render the design ({str(exc).splitlines()[0][:160] or type(exc).__name__}).") from exc

    mapping, notes = match(plan, found.boxes, llm)
    if fallback_note:
        notes.insert(0, fallback_note)
    context = get_context(store, project)
    if found.skipped:
        notes.append(f"{found.skipped} container{'s' if found.skipped != 1 else ''} outside the 1280x720 canvas were ignored.")
    if found.scale < 0.999:
        notes.append(f"The design is {found.source_w}x{found.source_h}px, not 1280x720; it was scaled to {found.scale:.0%} "
                     "to fit the Power BI page. Ask Stitch for an exact 1280x720 canvas for a 1:1 result.")
    imp = DesignImport(
        source=source, source_name=name, source_hash=_hash(html), plan_signature=plan_signature(plan), scripts=scripts,
        source_w=found.source_w, source_h=found.source_h, scale=found.scale,
        boxes=found.boxes, mapping=mapping, palette=found.palette, heading_font=found.heading_font, body_font=found.body_font,
        theme=build_theme(f"DashPilot {context.company_name or project.name}", found.palette, context.palette, found),
        notes=notes, skipped=found.skipped, imported_at=datetime.now(timezone.utc),
    )
    return _finish(store, project, plan, imp, html, page, whole.pages)


def get_import(store: ProjectStore, project: Project, llm: LLMProvider | None, page: int = 1) -> ImportResponse:
    """The saved import of one page; re-imported automatically when the plan or the Step 7 design changed."""
    whole, plan = _page(store, project, page)
    stored = store.read_json(project.id, import_file(page))
    selected = _selected(store, project, page)
    if stored:
        imp = DesignImport.model_validate(stored)
        html = (page_dir(store, project, page) / "source.html").read_text(encoding="utf-8")
        changed_design = imp.source != "upload" and selected is not None and _hash(selected[0]) != imp.source_hash
        if imp.plan_signature == plan_signature(plan) and not changed_design:
            return ImportResponse(design=imp, visuals=plan.visuals, html=html, notes=[], page=page, pages=whole.pages)
        if imp.source == "upload":
            screen = (page_dir(store, project, page) / SOURCE_SCREEN)
            res = run_import(store, project, llm, "upload", imp.source_name, html, imp.scripts, screen.read_bytes() if screen.exists() else None, page)
            res.notes.insert(0, "The dashboard plan changed, so the uploaded design was matched again.")
            return res
    if selected is None:
        where = f" for page {page} ({whole.pages[page - 1]})" if len(whole.pages) > 1 else ""
        raise ImportError_(f"Select a design in Step 7 (Design Method) or upload an HTML design{where}.")
    res = use_selected(store, project, llm, page)
    if stored:
        res.notes.insert(0, "The plan or the selected design changed, so the design was imported again.")
    return res


def get_imports(store: ProjectStore, project: Project, llm: LLMProvider | None) -> list[ImportResponse]:
    """Every page's import (the PBIP build needs all of them)."""
    plan = _plan(store, project)
    return [get_import(store, project, llm, page) for page in range(1, len(plan.pages) + 1)]


def use_selected(store: ProjectStore, project: Project, llm: LLMProvider | None, page: int = 1) -> ImportResponse:
    selected = _selected(store, project, page)
    if selected is None:
        raise ImportError_("No design selected in Step 7 yet." if page == 1 else f"The selected design has no page {page}; upload one for it.")
    method = _method(selected[1])
    return run_import(store, project, llm, method, selected[1], selected[0],
                      screen=_stitch_screen(store, project, page) if method == "option_a" else None, page=page)


def import_upload(store: ProjectStore, project: Project, llm: LLMProvider | None, filename: str, data: bytes, page: int = 1) -> ImportResponse:
    """Step 8 upload: a design's HTML, or a Google Stitch export zip (HTML + screen.png)."""
    from core.stitch_import import StitchError, read_export  # noqa: PLC0415

    try:
        export = read_export(filename, data)
    except StitchError as exc:
        raise ImportError_(str(exc)) from None
    return run_import(store, project, llm, "upload", export.name, export.html, screen=export.screen, page=page)


def set_override(store: ProjectStore, project: Project, llm: LLMProvider | None, override: bool, page: int = 1) -> ImportResponse:
    """Accept (or stop accepting) a fidelity below the threshold for the build."""
    current = get_import(store, project, llm, page)
    current.design.fidelity_override = override
    store.write_json(project.id, import_file(page), current.design.model_dump(mode="json"))
    return current


class MappingEdit(BaseModel):
    visual_id: str
    box_id: str | None = None
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0


def save_mapping(store: ProjectStore, project: Project, llm: LLMProvider | None, items: list[MappingEdit], page: int = 1) -> ImportResponse:
    current = get_import(store, project, llm, page)
    imp, plan_visuals = current.design, current.visuals
    whole, plan = _page(store, project, page)
    boxes = {b.id: b for b in imp.boxes}
    before = {m.visual_id: m for m in imp.mapping}
    planned = [v.id for v in plan_visuals]
    edits = {e.visual_id: e for e in items if e.visual_id in planned}
    mapping = []
    for vid in planned:
        e = edits.get(vid)
        old = before.get(vid, MappingItem(visual_id=vid))
        if e is None:
            mapping.append(old)
            continue
        if e.box_id is not None and e.box_id not in boxes:
            raise ImportError_(f"Box {e.box_id} does not exist in this design.")
        if e.box_id is not None and (e.w <= 0 or e.h <= 0):  # picked a box: take its position
            b = boxes[e.box_id]
            e = MappingEdit(visual_id=vid, box_id=b.id, x=b.x, y=b.y, w=b.w, h=b.h)
        same = (e.box_id, e.x, e.y, e.w, e.h) == (old.box_id, old.x, old.y, old.w, old.h)
        mapping.append(old if same else MappingItem(visual_id=vid, box_id=e.box_id, x=e.x, y=e.y, w=e.w, h=e.h,
                                                    method="manual" if e.w > 0 else "none", score=1.0 if e.w > 0 else 0.0))
    imp.mapping = mapping
    imp.notes = []
    return _finish(store, project, plan, imp, current.html, page, whole.pages)

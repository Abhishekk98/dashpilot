"""Glue between stored projects and the design import (keeps routes thin).

Files under storage/{id}/design/ (read by the PBIP builder in Step 9):
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
from core.design_import import (
    DetectedBox, MappingItem, ThemeColor, background_png, build_theme, extract, match, title_kept, validate_mapping,
)
from core.planner import DashboardPlan, PlanVisual
from core.planner_service import DESIGN_FILE, PLAN_FILE
from core.projects import Project, ProjectStore
from llm import LLMProvider

logger = logging.getLogger(__name__)
IMPORT_FILE = "design/import.json"
MAX_UPLOAD = 3 * 1024 * 1024


class ImportError_(ValueError):
    """User-facing problem (no plan, no design, bad upload)."""


class DesignImport(BaseModel):
    source: Literal["option_b", "option_c", "upload"]
    source_name: str
    source_hash: str
    plan_signature: str
    scripts: bool = False  # uploaded Stitch exports need their Tailwind script to render
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


def _dir(store: ProjectStore, project: Project):
    path = store.project_dir(project.id) / "design"
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def _selected(store: ProjectStore, project: Project) -> tuple[str, str] | None:
    path = _dir(store, project) / "selected.html"
    if not path.exists():
        return None
    design = store.read_json(project.id, DESIGN_FILE)
    if design.get("selected_label"):
        return path.read_text(encoding="utf-8"), design["selected_label"]
    chosen = next((v for v in design.get("variants", []) if v.get("id") == design.get("selected")), None)
    return path.read_text(encoding="utf-8"), f"Option B · {chosen['label']}" if chosen else "Selected design"


def _method(label: str) -> str:
    return "option_c" if label.startswith("Option C") else "option_b"


def _finish(store: ProjectStore, project: Project, plan: DashboardPlan, imp: DesignImport, html: str) -> ImportResponse:
    imp.issues = validate_mapping(plan, imp.mapping, imp.boxes)
    imp.valid = not imp.issues
    folder = _dir(store, project)
    boxes = {b.id: b for b in imp.boxes}
    titles = {v.id: v.title for v in plan.visuals}
    for m in imp.mapping:
        m.pbi_title = m.placed and not title_kept(titles.get(m.visual_id, ""), boxes.get(m.box_id or ""))
    hide = [m.box_id for m in imp.mapping if m.box_id and m.placed]
    hide_titles = [m.box_id for m in imp.mapping if m.box_id and m.pbi_title]
    (folder / "background.png").write_bytes(background_png(html, hide, imp.scripts, hide_titles))
    imp.background_version = str(int(time.time() * 1000))
    (folder / "theme.json").write_text(json.dumps(imp.theme, indent=2), encoding="utf-8")
    store.write_json(project.id, IMPORT_FILE, imp.model_dump(mode="json"))
    return ImportResponse(design=imp, visuals=plan.visuals, html=html, notes=imp.notes)


def run_import(store: ProjectStore, project: Project, llm: LLMProvider | None, source: str, name: str, html: str,
               scripts: bool = False) -> ImportResponse:
    plan = _plan(store, project)
    folder = _dir(store, project)
    (folder / "source.html").write_text(html, encoding="utf-8")
    try:
        found = extract(html, scripts)
    except Exception as exc:
        logger.warning("Design render failed: %s", exc)
        raise ImportError_(f"Could not render the design ({str(exc).splitlines()[0][:160] or type(exc).__name__}).") from exc
    if not found.boxes:
        raise ImportError_("No cards or containers were found in this design. Is it a 1280x720 dashboard page?")
    mapping, notes = match(plan, found.boxes, llm)
    context = get_context(store, project)
    if found.skipped:
        notes.append(f"{found.skipped} container{'s' if found.skipped != 1 else ''} outside the 1280x720 canvas were ignored.")
    if abs(found.canvas_w - 1280) > 1 or abs(found.canvas_h - 720) > 1:
        notes.append(f"The design's canvas is {found.canvas_w:.0f}x{found.canvas_h:.0f}px; only the top-left 1280x720 is used.")
    imp = DesignImport(
        source=source, source_name=name, source_hash=_hash(html), plan_signature=plan_signature(plan), scripts=scripts,
        boxes=found.boxes, mapping=mapping, palette=found.palette, heading_font=found.heading_font, body_font=found.body_font,
        theme=build_theme(f"DashPilot {context.company_name or project.name}", found.palette, context.palette),
        notes=notes, skipped=found.skipped, imported_at=datetime.now(timezone.utc),
    )
    return _finish(store, project, plan, imp, html)


def get_import(store: ProjectStore, project: Project, llm: LLMProvider | None) -> ImportResponse:
    """The saved import; re-imported automatically when the plan or the Step 7 design changed."""
    plan = _plan(store, project)
    stored = store.read_json(project.id, IMPORT_FILE)
    selected = _selected(store, project)
    if stored:
        imp = DesignImport.model_validate(stored)
        html = (_dir(store, project) / "source.html").read_text(encoding="utf-8")
        changed_design = imp.source != "upload" and selected is not None and _hash(selected[0]) != imp.source_hash
        if imp.plan_signature == plan_signature(plan) and not changed_design:
            return ImportResponse(design=imp, visuals=plan.visuals, html=html, notes=[])
        if imp.source == "upload":
            res = run_import(store, project, llm, "upload", imp.source_name, html, imp.scripts)
            res.notes.insert(0, "The dashboard plan changed, so the uploaded design was matched again.")
            return res
    if selected is None:
        raise ImportError_("Select a design in Step 7 (Design Method) or upload an HTML design.")
    res = run_import(store, project, llm, _method(selected[1]), selected[1], selected[0])
    if stored:
        res.notes.insert(0, "The plan or the selected design changed, so the design was imported again.")
    return res


def use_selected(store: ProjectStore, project: Project, llm: LLMProvider | None) -> ImportResponse:
    selected = _selected(store, project)
    if selected is None:
        raise ImportError_("No design selected in Step 7 yet.")
    return run_import(store, project, llm, _method(selected[1]), selected[1], selected[0])


def import_upload(store: ProjectStore, project: Project, llm: LLMProvider | None, filename: str, data: bytes) -> ImportResponse:
    if not filename.lower().endswith((".html", ".htm")):
        raise ImportError_("Upload the HTML export (.html). Image imports come with Option C.")
    if len(data) > MAX_UPLOAD:
        raise ImportError_("The HTML file is larger than 3 MB.")
    html = data.decode("utf-8", errors="replace")
    if "<" not in html or not any(t in html.lower() for t in ("<div", "<body", "<section", "<main")):
        raise ImportError_("This file does not look like an HTML page.")
    # Stitch exports style themselves with the Tailwind CDN script; it runs with all other network blocked.
    scripts = "cdn.tailwindcss.com" in html
    return run_import(store, project, llm, "upload", filename[:120], html, scripts)


class MappingEdit(BaseModel):
    visual_id: str
    box_id: str | None = None
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0


def save_mapping(store: ProjectStore, project: Project, llm: LLMProvider | None, items: list[MappingEdit]) -> ImportResponse:
    current = get_import(store, project, llm)
    imp, plan_visuals = current.design, current.visuals
    plan = _plan(store, project)
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
    return _finish(store, project, plan, imp, current.html)

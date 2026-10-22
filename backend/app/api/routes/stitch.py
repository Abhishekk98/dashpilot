from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.api.deps import get_store
from app.api.routes.projects import _load
from core import stitch_import
from core.context_service import get_context
from core.design_import_service import DesignImport, ImportError_, import_file
from core.insights_service import get_insights
from core.planner_service import PLAN_FILE
from core.planner import MAX_PAGES, DashboardPlan, page_plan
from core.projects import ProjectStore
from core.stitch_prompt import StitchPrompt, StitchStyle, build
from llm import LLMProvider, get_llm

router = APIRouter(prefix="/projects", tags=["design-option-a"])
Page = Query(1, ge=1, le=MAX_PAGES, description="Plan page (one Stitch export per page)")


class StitchState(BaseModel):
    page: int = 1
    pages: list[str] = ["Overview"]
    uploads: list[bool] = []  # an export is uploaded for page n
    upload: stitch_import.StitchUpload | None = None
    design: DesignImport | None = None  # the import of the uploaded export (mapping, fidelity)
    notes: list[str] = []


def _state(store: ProjectStore, project, notes: list[str] | None = None, page: int = 1) -> StitchState:
    upload = stitch_import.get_upload(store, project, page)
    stored = store.read_json(project.id, import_file(page))
    design = DesignImport.model_validate(stored) if stored and stored.get("source") == "option_a" else None
    plan = store.read_json(project.id, PLAN_FILE).get("plan")
    pages = DashboardPlan.model_validate(plan).pages if plan else ["Overview"]
    uploads = [stitch_import.get_upload(store, project, n) is not None for n in range(1, len(pages) + 1)]
    return StitchState(page=page, pages=pages, uploads=uploads, upload=upload, design=design, notes=notes or [])


@router.get("/{project_id}/design/stitch/prompt", response_model=StitchPrompt)
def stitch_prompt(project_id: str, style: StitchStyle = "light_elegant", page: int = Page, store: ProjectStore = Depends(get_store)) -> StitchPrompt:
    """The Google Stitch prompt for the current dashboard plan (exact layout + import rules)."""
    project = _load(store, project_id)
    stored = store.read_json(project.id, PLAN_FILE).get("plan")
    if not stored:
        raise HTTPException(status_code=422, detail="Build the dashboard plan first.")
    plan = DashboardPlan.model_validate(stored)
    if page > len(plan.pages):
        raise HTTPException(status_code=422, detail=f"The plan has {len(plan.pages)} page(s).")
    pages = plan.pages
    plan = page_plan(plan, page)
    try:
        questions = [q.text for q in get_insights(store, project, None).questions]
    except Exception:  # questions only enrich the prompt
        questions = []
    return build(plan, get_context(store, project), style, questions, all_pages=pages)


@router.get("/{project_id}/design/stitch", response_model=StitchState)
def stitch_state(project_id: str, page: int = Page, store: ProjectStore = Depends(get_store)) -> StitchState:
    return _state(store, _load(store, project_id), page=page)


@router.post("/{project_id}/design/stitch", response_model=StitchState)
def stitch_upload(project_id: str, file: UploadFile = File(...), page: int = Page, store: ProjectStore = Depends(get_store),
                  llm: LLMProvider | None = Depends(get_llm)) -> StitchState:
    """Upload Stitch's code.html or export zip; it is imported right away (mapping + fidelity report).
    Sync on purpose: Playwright's sync API cannot run on the event loop."""
    project = _load(store, project_id)
    data = file.file.read(stitch_import.MAX_UPLOAD + 1)
    try:
        res = stitch_import.upload(store, project, llm, file.filename or "code.html", data, page)
    except ImportError_ as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return _state(store, project, res.notes, page)

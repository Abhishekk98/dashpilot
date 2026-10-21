from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import get_store
from app.api.routes.projects import _load
from core import stitch_import
from core.context_service import get_context
from core.design_import_service import IMPORT_FILE, DesignImport, ImportError_
from core.insights_service import get_insights
from core.planner_service import PLAN_FILE
from core.planner import DashboardPlan
from core.projects import ProjectStore
from core.stitch_prompt import StitchPrompt, StitchStyle, build
from llm import LLMProvider, get_llm

router = APIRouter(prefix="/projects", tags=["design-option-a"])


class StitchState(BaseModel):
    upload: stitch_import.StitchUpload | None = None
    design: DesignImport | None = None  # the import of the uploaded export (mapping, fidelity)
    notes: list[str] = []


def _state(store: ProjectStore, project, notes: list[str] | None = None) -> StitchState:
    upload = stitch_import.get_upload(store, project)
    stored = store.read_json(project.id, IMPORT_FILE)
    design = DesignImport.model_validate(stored) if stored and stored.get("source") == "option_a" else None
    return StitchState(upload=upload, design=design, notes=notes or [])


@router.get("/{project_id}/design/stitch/prompt", response_model=StitchPrompt)
def stitch_prompt(project_id: str, style: StitchStyle = "light_elegant", store: ProjectStore = Depends(get_store)) -> StitchPrompt:
    """The Google Stitch prompt for the current dashboard plan (exact layout + import rules)."""
    project = _load(store, project_id)
    stored = store.read_json(project.id, PLAN_FILE).get("plan")
    if not stored:
        raise HTTPException(status_code=422, detail="Build the dashboard plan first.")
    plan = DashboardPlan.model_validate(stored)
    try:
        questions = [q.text for q in get_insights(store, project, None).questions]
    except Exception:  # questions only enrich the prompt
        questions = []
    return build(plan, get_context(store, project), style, questions)


@router.get("/{project_id}/design/stitch", response_model=StitchState)
def stitch_state(project_id: str, store: ProjectStore = Depends(get_store)) -> StitchState:
    return _state(store, _load(store, project_id))


@router.post("/{project_id}/design/stitch", response_model=StitchState)
def stitch_upload(project_id: str, file: UploadFile = File(...), store: ProjectStore = Depends(get_store),
                  llm: LLMProvider | None = Depends(get_llm)) -> StitchState:
    """Upload Stitch's code.html or export zip; it is imported right away (mapping + fidelity report).
    Sync on purpose: Playwright's sync API cannot run on the event loop."""
    project = _load(store, project_id)
    data = file.file.read(stitch_import.MAX_UPLOAD + 1)
    try:
        res = stitch_import.upload(store, project, llm, file.filename or "code.html", data)
    except ImportError_ as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return _state(store, project, res.notes)

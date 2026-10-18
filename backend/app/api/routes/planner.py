from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_store
from app.api.routes.projects import _load
from core.planner import VisualInput
from core.planner_service import PlanError, PlanResponse, generate_design, get_plan, save_plan, select_variant
from core.projects import ProjectStore
from llm import LLMProvider, get_llm

router = APIRouter(prefix="/projects", tags=["planner"])


class PlanEdit(BaseModel):
    title: str | None = Field(default=None, max_length=80)
    visuals: list[VisualInput]


class Select(BaseModel):
    id: str


def _run(fn, store: ProjectStore, project_id: str, llm, *args):
    project = _load(store, project_id)
    if not project.files:
        raise HTTPException(status_code=422, detail="Upload data first; the dashboard plan is built from your measures.")
    try:
        return fn(store, project, llm, *args)
    except PlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/{project_id}/plan", response_model=PlanResponse)
def read_plan(project_id: str, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> PlanResponse:
    """The saved dashboard plan (re-validated), or a new rule-based plan."""
    return _run(get_plan, store, project_id, llm)


@router.post("/{project_id}/plan/generate", response_model=PlanResponse)
def regenerate_plan(project_id: str, ai: bool = False, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> PlanResponse:
    """Rebuild the plan from the current measures and insights; ai=true lets the LLM polish titles."""
    return _run(get_plan, store, project_id, llm, True, ai)


@router.put("/{project_id}/plan", response_model=PlanResponse)
def update_plan(project_id: str, body: PlanEdit, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> PlanResponse:
    """Save the user's edits (types, fields, order, add/remove); layout is recomputed and validated."""
    return _run(save_plan, store, project_id, llm, body.visuals, body.title)


@router.post("/{project_id}/design/variants", response_model=PlanResponse)
def design_variants(project_id: str, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> PlanResponse:
    """Design method B: three 1280x720 HTML variants, each checked against the design contract."""
    return _run(generate_design, store, project_id, llm)


@router.post("/{project_id}/design/select", response_model=PlanResponse)
def choose_variant(project_id: str, body: Select, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> PlanResponse:
    """Keep one variant for Design Import (Step 8)."""
    return _run(select_variant, store, project_id, llm, body.id)

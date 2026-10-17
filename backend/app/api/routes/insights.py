from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_store
from app.api.routes.projects import _load
from core.insights import InsightPlan
from core.insights_service import AskResponse, InsightError, ask, get_insights, remove_asked, set_pinned
from core.projects import ProjectStore
from llm import LLMProvider, get_llm

router = APIRouter(prefix="/projects", tags=["insights"])


class AskBody(BaseModel):
    question: str = Field(max_length=300)


class PinBody(BaseModel):
    id: str
    pinned: bool = True


class IdBody(BaseModel):
    id: str


def _project(store: ProjectStore, project_id: str):
    project = _load(store, project_id)
    if not project.files:
        raise HTTPException(status_code=422, detail="Upload data first; insights are computed from the cleaned data and measures.")
    return project


@router.get("/{project_id}/insights", response_model=InsightPlan)
def read_insights(project_id: str, ai: bool = False, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> InsightPlan:
    """Computed insights + business questions. ai=true also asks the LLM (once) to phrase them."""
    return get_insights(store, _project(store, project_id), llm, run_ai=ai)


@router.post("/{project_id}/insights/ask", response_model=AskResponse)
def ask_question(project_id: str, body: AskBody, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> AskResponse:
    """Question -> validated query spec -> computed answer (no generated code is executed)."""
    try:
        return ask(store, _project(store, project_id), llm, body.question)
    except InsightError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/{project_id}/insights/pin", response_model=InsightPlan)
def pin_insight(project_id: str, body: PinBody, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> InsightPlan:
    """Pin an insight for the dashboard's Key Insights card (read by the planner step)."""
    return set_pinned(store, _project(store, project_id), llm, body.id, body.pinned)


@router.post("/{project_id}/insights/asked/delete", response_model=InsightPlan)
def delete_asked(project_id: str, body: IdBody, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> InsightPlan:
    return remove_asked(store, _project(store, project_id), llm, body.id)

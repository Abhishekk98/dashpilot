from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.api.deps import get_store
from app.api.routes.projects import _load
from core.dax import MeasureInput, MeasurePlan
from core.dax_service import MeasureError, delete_measure, get_plan, measures_tmdl, polish, reset_measure, save_measure, suggest
from core.projects import ProjectStore
from llm import LLMProvider, get_llm

router = APIRouter(prefix="/projects", tags=["measures"])


class SaveMeasure(BaseModel):
    measure: MeasureInput
    original_name: str | None = None  # set when editing an existing measure


class NamedMeasure(BaseModel):
    name: str


def _project_with_data(store: ProjectStore, project_id: str):
    project = _load(store, project_id)
    if not project.files:
        raise HTTPException(status_code=422, detail="Upload data first; measures are built from the data model.")
    return project


def _run(fn, *args):
    try:
        return fn(*args)
    except MeasureError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/{project_id}/measures", response_model=MeasurePlan)
def list_measures(project_id: str, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> MeasurePlan:
    """Generated + custom measures, each validated and (where possible) calculated on the cleaned data."""
    return get_plan(store, _project_with_data(store, project_id), llm)


@router.post("/{project_id}/measures", response_model=MeasurePlan)
def upsert_measure(project_id: str, body: SaveMeasure, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> MeasurePlan:
    return _run(save_measure, store, _project_with_data(store, project_id), llm, body.measure, body.original_name)


@router.post("/{project_id}/measures/delete", response_model=MeasurePlan)
def remove_measure(project_id: str, body: NamedMeasure, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> MeasurePlan:
    return _run(delete_measure, store, _project_with_data(store, project_id), llm, body.name)


@router.post("/{project_id}/measures/reset", response_model=MeasurePlan)
def regenerate_measure(project_id: str, body: NamedMeasure, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> MeasurePlan:
    """Drop the user's edits to a generated measure."""
    return _run(reset_measure, store, _project_with_data(store, project_id), llm, body.name)


@router.post("/{project_id}/measures/validate", response_model=MeasurePlan)
def validate_measures(project_id: str, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> MeasurePlan:
    """Re-run validation and calculated values for all measures (every response is already validated)."""
    return get_plan(store, _project_with_data(store, project_id), llm)


@router.post("/{project_id}/measures/suggest", response_model=MeasurePlan)
def suggest_measures(project_id: str, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> MeasurePlan:
    """AI measures from the business goals; only those passing the DAX validator are added."""
    return _run(suggest, store, _project_with_data(store, project_id), llm)


@router.post("/{project_id}/measures/polish", response_model=MeasurePlan)
def polish_measure(project_id: str, body: NamedMeasure, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> MeasurePlan:
    """AI rewrite + plain-language explanation, applied only if the new DAX validates."""
    return _run(polish, store, _project_with_data(store, project_id), llm, body.name)


@router.get("/{project_id}/measures/export.tmdl", response_class=PlainTextResponse)
def export_measures(project_id: str, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> PlainTextResponse:
    content = measures_tmdl(store, _project_with_data(store, project_id), llm)
    return PlainTextResponse(content, media_type="text/plain", headers={"Content-Disposition": 'attachment; filename="_Measures.tmdl"'})

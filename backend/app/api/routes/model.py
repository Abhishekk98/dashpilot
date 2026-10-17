from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import get_store
from app.api.routes.projects import _load
from core import tmdl
from core.modelling import ModelPlan, ModelSettings
from core.modelling_service import get_model, save_settings, tmdl_files
from core.projects import ProjectStore
from llm import LLMProvider, get_llm

router = APIRouter(prefix="/projects", tags=["model"])


class TmdlFile(BaseModel):
    path: str
    content: str


@router.get("/{project_id}/model", response_model=ModelPlan)
def read_model(
    project_id: str,
    ai: bool = False,
    store: ProjectStore = Depends(get_store),
    llm: LLMProvider | None = Depends(get_llm),
) -> ModelPlan:
    """Star schema from the cleaned tables. ai=false answers fast (ai_status "pending" until ai=true ran once)."""
    project = _load(store, project_id)
    if not project.files:
        raise HTTPException(status_code=422, detail="Upload data first; the model is built from the profiled tables.")
    return get_model(store, project, llm, run_ai=ai)


@router.put("/{project_id}/model", response_model=ModelPlan)
def write_model(
    project_id: str,
    body: ModelSettings,
    store: ProjectStore = Depends(get_store),
    llm: LLMProvider | None = Depends(get_llm),
) -> ModelPlan:
    """Save the user's choices (included tables, fact/dimension, relationships, date table, hidden keys)."""
    return save_settings(store, _load(store, project_id), llm, body)


@router.get("/{project_id}/model/tmdl", response_model=list[TmdlFile])
def preview_tmdl(
    project_id: str, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)
) -> list[TmdlFile]:
    files = tmdl_files(store, _load(store, project_id), llm)
    return [TmdlFile(path=p, content=c) for p, c in files.items()]


@router.get("/{project_id}/model/tmdl.zip")
def export_tmdl(
    project_id: str, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)
) -> Response:
    project = _load(store, project_id)
    data = tmdl.zip_files(tmdl_files(store, project, llm))
    filename = tmdl.model_folder(project.name) + ".zip"
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

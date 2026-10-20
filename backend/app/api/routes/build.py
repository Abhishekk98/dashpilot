from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import get_store
from app.api.routes.projects import _load
from core.pbip_service import BuildError, BuildStatus, build_project, get_status, zip_path
from core.projects import ProjectStore
from llm import LLMProvider, get_llm

router = APIRouter(prefix="/projects", tags=["build"])


class BuildBody(BaseModel):
    data_folder: str | None = Field(default=None, max_length=200)


def _run(fn, store: ProjectStore, project_id: str, llm, *args):
    project = _load(store, project_id)
    try:
        return fn(store, project, llm, *args)
    except BuildError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/{project_id}/build", response_model=BuildStatus)
def read_build(project_id: str, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> BuildStatus:
    """Whether the project can be built, and the last build with its validation checklist."""
    return _run(get_status, store, project_id, llm)


@router.post("/{project_id}/build", response_model=BuildStatus)
def run_build(project_id: str, body: BuildBody, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> BuildStatus:
    """Build the PBIP (semantic model + report + data), validate it and zip it."""
    return _run(build_project, store, project_id, llm, body.data_folder)


@router.get("/{project_id}/build/download")
def download(project_id: str, store: ProjectStore = Depends(get_store)) -> FileResponse:
    try:
        path, name = zip_path(store, _load(store, project_id))
    except BuildError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return FileResponse(path, media_type="application/zip", filename=name)

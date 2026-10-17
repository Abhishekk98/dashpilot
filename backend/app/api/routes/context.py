from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import get_store
from app.api.routes.projects import _load
from core.context import BusinessContext, BrandPalette, ContextSuggestion, PaletteSuggestion, PolishedGoals
from core.context_service import (
    ContextError,
    get_context,
    logo_file,
    palette,
    polish,
    remove_logo,
    save_context,
    suggest,
    upload_logo,
)
from core.projects import ProjectStore
from llm import LLMProvider, get_llm

router = APIRouter(prefix="/projects", tags=["context"])


class PaletteRequest(BaseModel):
    accent: str = BrandPalette().accent
    use_logo: bool = True


class PolishRequest(BaseModel):
    goals: str = Field(max_length=2000)


@router.get("/{project_id}/context", response_model=BusinessContext)
def read_context(project_id: str, store: ProjectStore = Depends(get_store)) -> BusinessContext:
    """Saved business context, or defaults (updated_at null) when the step was never saved."""
    return get_context(store, _load(store, project_id))


@router.put("/{project_id}/context", response_model=BusinessContext)
def write_context(project_id: str, body: BusinessContext, store: ProjectStore = Depends(get_store)) -> BusinessContext:
    return save_context(store, _load(store, project_id), body)


@router.post("/{project_id}/context/logo", response_model=BusinessContext)
async def post_logo(project_id: str, file: UploadFile = File(...), store: ProjectStore = Depends(get_store)) -> BusinessContext:
    project = _load(store, project_id)
    try:
        return upload_logo(store, project, file.filename or "logo", await file.read())
    except ContextError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.delete("/{project_id}/context/logo", response_model=BusinessContext)
def delete_logo(project_id: str, store: ProjectStore = Depends(get_store)) -> BusinessContext:
    return remove_logo(store, _load(store, project_id))


@router.get("/{project_id}/context/logo")
def get_logo(project_id: str, store: ProjectStore = Depends(get_store)) -> FileResponse:
    found = logo_file(store, _load(store, project_id))
    if found is None:
        raise HTTPException(status_code=404, detail="No logo uploaded")
    path, content_type = found
    # SVGs can carry scripts: never let them run if the URL is opened directly.
    headers = {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff"}
    return FileResponse(path, media_type=content_type, headers=headers)


@router.post("/{project_id}/context/suggest", response_model=ContextSuggestion)
def post_suggest(
    project_id: str, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)
) -> ContextSuggestion:
    """Industry, audience, goals and a domain score inferred from the profiled columns."""
    try:
        return suggest(store, _load(store, project_id), llm)
    except ContextError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/{project_id}/context/palette", response_model=PaletteSuggestion)
def post_palette(
    project_id: str,
    body: PaletteRequest,
    store: ProjectStore = Depends(get_store),
    llm: LLMProvider | None = Depends(get_llm),
) -> PaletteSuggestion:
    try:
        return palette(store, _load(store, project_id), llm, BrandPalette(accent=body.accent).accent, body.use_logo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/{project_id}/context/polish", response_model=PolishedGoals)
def post_polish(
    project_id: str,
    body: PolishRequest,
    store: ProjectStore = Depends(get_store),
    llm: LLMProvider | None = Depends(get_llm),
) -> PolishedGoals:
    return polish(store, _load(store, project_id), llm, body.goals)

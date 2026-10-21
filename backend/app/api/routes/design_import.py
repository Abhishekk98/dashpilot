from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import get_store
from app.api.routes.projects import _load
from core.design_import_service import (
    ImportError_, ImportResponse, MappingEdit, get_import, import_upload, page_dir, save_mapping, set_override, use_selected,
)
from core.planner import MAX_PAGES
from core.projects import ProjectStore
from llm import LLMProvider, get_llm

router = APIRouter(prefix="/projects", tags=["design-import"])
Page = Query(1, ge=1, le=MAX_PAGES, description="Plan page (1 = Overview)")


class MappingBody(BaseModel):
    mapping: list[MappingEdit]


class OverrideBody(BaseModel):
    override: bool


def _run(fn, store: ProjectStore, project_id: str, llm, *args):
    project = _load(store, project_id)
    try:
        return fn(store, project, llm, *args)
    except ImportError_ as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/{project_id}/design/import", response_model=ImportResponse)
def read_import(project_id: str, page: int = Page, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> ImportResponse:
    """The saved import, or a fresh import of the design selected in Step 7."""
    return _run(get_import, store, project_id, llm, page)


@router.post("/{project_id}/design/import/selected", response_model=ImportResponse)
def import_selected(project_id: str, page: int = Page, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> ImportResponse:
    """Import (again) the Option B design selected in Step 7; drops manual mapping edits."""
    return _run(use_selected, store, project_id, llm, page)


@router.post("/{project_id}/design/import/upload", response_model=ImportResponse)
def upload_design(project_id: str, file: UploadFile = File(...), page: int = Page, store: ProjectStore = Depends(get_store),
                  llm: LLMProvider | None = Depends(get_llm)) -> ImportResponse:
    """Import an uploaded HTML design (e.g. a Google Stitch export); visuals are matched by title.
    Sync on purpose: Playwright's sync API cannot run on the event loop."""
    data = file.file.read()
    return _run(import_upload, store, project_id, llm, file.filename or "design.html", data, page)


@router.put("/{project_id}/design/import/mapping", response_model=ImportResponse)
def update_mapping(project_id: str, body: MappingBody, page: int = Page, store: ProjectStore = Depends(get_store),
                   llm: LLMProvider | None = Depends(get_llm)) -> ImportResponse:
    """Reassign boxes or move/resize them; re-validates and re-renders the background."""
    return _run(save_mapping, store, project_id, llm, body.mapping, page)


@router.put("/{project_id}/design/import/fidelity-override", response_model=ImportResponse)
def fidelity_override(project_id: str, body: OverrideBody, page: int = Page, store: ProjectStore = Depends(get_store),
                      llm: LLMProvider | None = Depends(get_llm)) -> ImportResponse:
    """Accept a design fidelity below the threshold so the PBIP can be built anyway (shown as a warning)."""
    return _run(set_override, store, project_id, llm, body.override, page)


@router.get("/{project_id}/design/original.png")
def original(project_id: str, page: int = Page, store: ProjectStore = Depends(get_store)) -> FileResponse:
    """The design rendered as it is (before dummy contents are hidden), 1280x720."""
    return _file(store, project_id, "original.png", "image/png", page=page)


def _file(store: ProjectStore, project_id: str, name: str, media: str, download: str | None = None, page: int = 1) -> FileResponse:
    path = page_dir(store, _load(store, project_id), page) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Import the design first.")
    headers = {"Cache-Control": "no-cache"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{download}"'
    return FileResponse(path, media_type=media, headers=headers)


@router.get("/{project_id}/design/background.png")
def background(project_id: str, page: int = Page, store: ProjectStore = Depends(get_store)) -> FileResponse:
    return _file(store, project_id, "background.png", "image/png", page=page)


@router.get("/{project_id}/design/theme.json")
def theme(project_id: str, store: ProjectStore = Depends(get_store)) -> FileResponse:
    return _file(store, project_id, "theme.json", "application/json", "dashpilot-theme.json")

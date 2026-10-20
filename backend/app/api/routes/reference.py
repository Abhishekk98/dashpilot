from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import get_store
from app.api.routes.projects import _load
from core import design_option_c as option_c
from core.planner_service import PlanError
from core.projects import ProjectStore
from core.style_profile import StyleProfile
from llm import LLMProvider, get_llm

router = APIRouter(prefix="/projects", tags=["design-option-c"])


class ReferenceResponse(BaseModel):
    state: option_c.OptionCState
    notes: list[str] = []


def _run(fn, *args) -> ReferenceResponse:
    try:
        out = fn(*args)
    except PlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    state, notes = out if isinstance(out, tuple) else (out, [])
    return ReferenceResponse(state=state, notes=notes + ([state.profile_note] if state.profile_note and fn is option_c.upload_reference else []))


@router.get("/{project_id}/design/reference", response_model=ReferenceResponse)
def read_reference(project_id: str, store: ProjectStore = Depends(get_store)) -> ReferenceResponse:
    """Option C state: reference image info, style profile and generated variants."""
    return _run(option_c.get_state, store, _load(store, project_id))


@router.post("/{project_id}/design/reference", response_model=ReferenceResponse)
def upload_reference(project_id: str, file: UploadFile = File(...), store: ProjectStore = Depends(get_store),
                     llm: LLMProvider | None = Depends(get_llm)) -> ReferenceResponse:
    """Upload a reference dashboard image (PNG/JPG/WebP, max 10 MB) and read its style profile.
    Sync on purpose: the vision call and image work should not block the event loop."""
    data = file.file.read(option_c.style_profile_limit() + 1)
    return _run(option_c.upload_reference, store, _load(store, project_id), llm, file.filename or "reference", data)


@router.put("/{project_id}/design/reference/profile", response_model=ReferenceResponse)
def update_profile(project_id: str, profile: StyleProfile, store: ProjectStore = Depends(get_store)) -> ReferenceResponse:
    """Save the user's edits to the style profile."""
    return _run(option_c.save_profile, store, _load(store, project_id), profile)


@router.post("/{project_id}/design/reference/variants", response_model=ReferenceResponse)
def reference_variants(project_id: str, store: ProjectStore = Depends(get_store), llm: LLMProvider | None = Depends(get_llm)) -> ReferenceResponse:
    """Two designs in the reference style (close to reference, reference + brand colors)."""
    return _run(option_c.generate, store, _load(store, project_id), llm)


@router.get("/{project_id}/design/reference/image")
def reference_image(project_id: str, store: ProjectStore = Depends(get_store)) -> FileResponse:
    path, mime = option_c.image_path(store, _load(store, project_id))
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="No reference image uploaded")
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})

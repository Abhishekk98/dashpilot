from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.api.deps import get_store
from app.config import Settings, get_settings
from core.cleaning import CleaningPlan, Decision, DiffPreview
from core.cleaning_service import CleaningError, get_plan, get_preview, save_decisions
from core.profiling import QualityReport
from core.profiling_service import columns_csv, get_report
from core.projects import Project, ProjectNotFoundError, ProjectStore, StoredFile, TableRef, new_file_id
from core.upload import UploadError, read_tables, validate_upload
from llm import LLMProvider, get_llm

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProject(BaseModel):
    name: str = "Untitled Project"


class UploadResult(BaseModel):
    project: Project
    errors: list[str]


def _load(store: ProjectStore, project_id: str) -> Project:
    try:
        return store.get(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("", response_model=Project, status_code=201)
def create_project(body: CreateProject, store: ProjectStore = Depends(get_store)) -> Project:
    return store.create(body.name)


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str, store: ProjectStore = Depends(get_store)) -> Project:
    return _load(store, project_id)


@router.post("/{project_id}/files", response_model=UploadResult)
async def upload_files(
    project_id: str,
    files: list[UploadFile] = File(...),
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> UploadResult:
    """Accept one or more CSV/Excel files; bad files are reported without failing the rest."""
    project = _load(store, project_id)
    errors: list[str] = []
    for upload in files:
        filename = Path(upload.filename or "upload").name
        try:
            if upload.size is not None:
                validate_upload(filename, upload.size, settings.max_upload_mb)
            content = await upload.read()
            ext = validate_upload(filename, len(content), settings.max_upload_mb)
            tables = read_tables(filename, content)
        except UploadError as exc:
            errors.append(str(exc))
            continue
        stored = StoredFile(
            id=new_file_id(),
            filename=filename,
            extension=ext,
            size_bytes=len(content),
            uploaded_at=datetime.now(timezone.utc),
            tables=[TableRef(name=n, sheet=s, rows=len(df), columns=len(df.columns)) for n, (s, df) in tables.items()],
        )
        project = store.add_file(project, stored, content)
    return UploadResult(project=project, errors=errors)


@router.delete("/{project_id}/files/{file_id}", response_model=Project)
def delete_file(project_id: str, file_id: str, store: ProjectStore = Depends(get_store)) -> Project:
    project = _load(store, project_id)
    try:
        return store.remove_file(project, file_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="File not found") from None


@router.get("/{project_id}/profile", response_model=QualityReport)
def get_profile(
    project_id: str,
    refresh: bool = False,
    ai: bool = True,
    store: ProjectStore = Depends(get_store),
    llm: LLMProvider | None = Depends(get_llm),
) -> QualityReport:
    """Quality report. ai=false answers fast with rule-based roles; ai=true also waits for AI refinement."""
    return get_report(store, _load(store, project_id), llm, refresh, ai)


class DecisionBatch(BaseModel):
    decisions: list[Decision]


@router.get("/{project_id}/cleaning", response_model=CleaningPlan)
def get_cleaning(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    llm: LLMProvider | None = Depends(get_llm),
) -> CleaningPlan:
    """Cleaning suggestions with their accept/skip state and the per-table Power Query M scripts."""
    return get_plan(store, _load(store, project_id), llm)


@router.post("/{project_id}/cleaning/decisions", response_model=CleaningPlan)
def post_cleaning_decisions(
    project_id: str,
    body: DecisionBatch,
    store: ProjectStore = Depends(get_store),
    llm: LLMProvider | None = Depends(get_llm),
) -> CleaningPlan:
    try:
        return save_decisions(store, _load(store, project_id), llm, body.decisions)
    except CleaningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/{project_id}/cleaning/preview", response_model=DiffPreview)
def get_cleaning_preview(
    project_id: str,
    table: str,
    store: ProjectStore = Depends(get_store),
    llm: LLMProvider | None = Depends(get_llm),
) -> DiffPreview:
    """Before/after sample rows for the accepted steps of one table."""
    try:
        return get_preview(store, _load(store, project_id), llm, table)
    except CleaningError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/{project_id}/profile/columns.csv", response_class=PlainTextResponse)
def export_profile_csv(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    llm: LLMProvider | None = Depends(get_llm),
) -> PlainTextResponse:
    report = get_report(store, _load(store, project_id), llm, ai=False)  # export what is shown; never wait on AI
    return PlainTextResponse(
        columns_csv(report),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="profiler.csv"'},
    )

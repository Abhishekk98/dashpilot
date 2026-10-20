"""Glue between stored projects and the PBIP builder/validator (keeps routes thin).

Output: storage/{id}/build/{Folder}/ (the PBIP tree) and storage/{id}/build/{Folder}.zip.
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import zipfile
from datetime import datetime, timezone

from pydantic import BaseModel

from core import tmdl
from core.dax_service import valid_measures
from core.design_ai import plan_signature
from core.design_import_service import ImportError_, _plan, get_import
from core.modelling_service import build_with_results
from core.pbip_builder import BuildInputs, build, folder_name
from core.pbip_validator import Check, validate
from core.projects import Project, ProjectStore
from llm import LLMProvider

BUILD_FILE = "build/build.json"


class BuildError(ValueError):
    """User-facing problem (earlier steps not finished, bad data folder)."""


class BuildResult(BaseModel):
    folder: str
    zip_name: str
    size_bytes: int
    file_count: int
    digest: str  # sha256 of the zip
    built_at: datetime
    data_folder: str
    checks: list[Check]
    valid: bool
    tables: int
    measures: int
    visuals: int
    bindings: int
    partitions: int
    signature: str  # plan + mapping + design version the build was made from


class BuildStatus(BaseModel):
    ready: bool
    blockers: list[str] = []
    default_data_folder: str
    project_folder: str
    build: BuildResult | None = None
    stale: bool = False  # plan, mapping or design changed after this build


def _signature(store: ProjectStore, project: Project, llm: LLMProvider | None) -> tuple[str, object]:
    imp = get_import(store, project, llm).design
    raw = plan_signature(_plan(store, project)) + imp.background_version + "".join(
        f"{m.visual_id}{m.box_id}{m.x},{m.y},{m.w},{m.h}{m.pbi_title}" for m in imp.mapping)
    return hashlib.sha1(raw.encode()).hexdigest()[:16], imp


def default_data_folder(project: Project) -> str:
    return f"C:\\DashPilot\\{folder_name(project.name)}\\Data\\"


def clean_data_folder(value: str | None, project: Project) -> str:
    value = (value or "").strip() or default_data_folder(project)
    if len(value) > 200 or re.search(r'["\n\r<>|?*]', value):
        raise BuildError("The data folder must be a plain Windows path, for example C:\\DashPilot\\Data\\")
    return value if value.endswith(("\\", "/")) else value + "\\"


def get_status(store: ProjectStore, project: Project, llm: LLMProvider | None) -> BuildStatus:
    blockers: list[str] = []
    sig = None
    try:
        sig, imp = _signature(store, project, llm)
        if not imp.valid:
            blockers.append("Finish the visual mapping in Step 8 (every visual needs one box, no overlaps).")
    except ImportError_ as exc:
        blockers.append(str(exc))
    stored = store.read_json(project.id, BUILD_FILE)
    last = BuildResult.model_validate(stored) if stored else None
    return BuildStatus(ready=not blockers, blockers=blockers, default_data_folder=default_data_folder(project),
                       project_folder=folder_name(project.name), build=last, stale=bool(last and sig and last.signature != sig))


def build_project(store: ProjectStore, project: Project, llm: LLMProvider | None, data_folder: str | None) -> BuildStatus:
    folder_value = clean_data_folder(data_folder, project)
    try:
        sig, imp = _signature(store, project, llm)
    except ImportError_ as exc:
        raise BuildError(str(exc)) from None
    if not imp.valid:
        raise BuildError("Finish the visual mapping in Step 8 first: " + "; ".join(imp.issues[:2]))
    plan = _plan(store, project)
    model, results = build_with_results(store, project, llm)
    problems = tmdl.check(model)
    if problems:
        raise BuildError("The data model has problems: " + "; ".join(problems[:3]))
    design_dir = store.project_dir(project.id) / "design"
    inputs = BuildInputs(
        project_name=project.name, model=model, cleaned=results, measures=valid_measures(store, project, llm),
        plan=plan, boxes=imp.boxes, mapping=imp.mapping, theme=imp.theme,
        background=(design_dir / "background.png").read_bytes(),
        sources=[(f.filename, store.file_path(project.id, f).read_bytes()) for f in project.files],
        data_folder=folder_value,
    )
    files = build(inputs)
    checks = validate(files, plan.width, plan.height)

    out = store.project_dir(project.id) / "build"
    shutil.rmtree(out, ignore_errors=True)
    folder = folder_name(project.name)
    tree = out / folder
    for path, content in files.items():
        target = tree / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in sorted(files.items()):
            zf.writestr(f"{folder}/{path}", content)
    data = buf.getvalue()
    (out / f"{folder}.zip").write_bytes(data)

    count = lambda pattern: sum(1 for p in files if re.search(pattern, p))  # noqa: E731
    result = BuildResult(
        folder=folder, zip_name=f"{folder}.zip", size_bytes=len(data), file_count=len(files),
        digest=hashlib.sha256(data).hexdigest(), built_at=datetime.now(timezone.utc), data_folder=folder_value,
        checks=checks, valid=all(c.status != "fail" for c in checks),
        tables=count(r"\.SemanticModel/definition/tables/"), measures=len(inputs.measures),
        visuals=count(r"/visuals/.+/visual\.json$"), bindings=next((c.count or 0 for c in checks if c.id == "fields"), 0),
        partitions=sum(content.count(b"\tpartition ") for p, content in files.items() if p.endswith(".tmdl")),
        signature=sig,
    )
    store.write_json(project.id, BUILD_FILE, result.model_dump(mode="json"))
    return BuildStatus(ready=True, default_data_folder=default_data_folder(project), project_folder=folder, build=result)


def zip_path(store: ProjectStore, project: Project):
    stored = store.read_json(project.id, BUILD_FILE)
    if not stored:
        raise BuildError("Build the project first.")
    result = BuildResult.model_validate(stored)
    if not result.valid:
        raise BuildError("The last build did not pass validation; fix the issues and build again.")
    path = store.project_dir(project.id) / "build" / result.zip_name
    if not path.exists():
        raise BuildError("Build the project first.")
    return path, result.zip_name

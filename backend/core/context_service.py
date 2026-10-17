"""Glue between stored projects and the business context module (keeps route handlers thin)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.context import (
    LOGO_TYPES,
    MAX_LOGO_BYTES,
    BusinessContext,
    ContextSuggestion,
    LogoRef,
    PaletteSuggestion,
    PolishedGoals,
    polish_goals,
    suggest_context,
    suggest_palette,
)
from core.profiling_service import get_report
from core.projects import Project, ProjectStore
from llm import LLMProvider


class ContextError(ValueError):
    """User-facing problem (bad logo file, nothing to suggest from)."""


def get_context(store: ProjectStore, project: Project) -> BusinessContext:
    data = store.read_context(project.id)
    return BusinessContext.model_validate(data) if data else BusinessContext(company_name=project.name)


def save_context(store: ProjectStore, project: Project, context: BusinessContext) -> BusinessContext:
    # The logo is managed by its own endpoints; the form never overwrites it.
    current = get_context(store, project)
    saved = context.model_copy(update={"logo": current.logo, "updated_at": datetime.now(timezone.utc)})
    store.write_context(project.id, saved.model_dump(mode="json"))
    return saved


def upload_logo(store: ProjectStore, project: Project, filename: str, content: bytes) -> BusinessContext:
    ext = Path(filename).suffix.lower()
    if ext not in LOGO_TYPES:
        raise ContextError(f"{filename}: logos must be .png, .jpg or .svg")
    if not content:
        raise ContextError(f"{filename}: file is empty")
    if len(content) > MAX_LOGO_BYTES:
        raise ContextError(f"{filename}: logos must be 2 MB or smaller")
    ext = ".jpg" if ext == ".jpeg" else ext
    store.save_logo(project.id, ext, content)
    context = get_context(store, project)
    context.logo = LogoRef(
        filename=Path(filename).name, extension=ext, content_type=LOGO_TYPES[ext],
        size_bytes=len(content), uploaded_at=datetime.now(timezone.utc),
    )
    store.write_context(project.id, context.model_dump(mode="json"))
    return context


def remove_logo(store: ProjectStore, project: Project) -> BusinessContext:
    store.remove_logo(project.id)
    context = get_context(store, project)
    context.logo = None
    store.write_context(project.id, context.model_dump(mode="json"))
    return context


def logo_file(store: ProjectStore, project: Project) -> tuple[Path, str] | None:
    logo = get_context(store, project).logo
    if logo is None:
        return None
    path = store.logo_path(project.id, logo.extension)
    return (path, logo.content_type) if path.exists() else None


def suggest(store: ProjectStore, project: Project, llm: LLMProvider | None) -> ContextSuggestion:
    if not project.files:
        raise ContextError("Upload data first; suggestions are based on the profiled columns.")
    return suggest_context(get_report(store, project, llm, ai=False), llm)


def palette(
    store: ProjectStore, project: Project, llm: LLMProvider | None, accent: str, use_logo: bool
) -> PaletteSuggestion:
    found = logo_file(store, project) if use_logo else None
    logo = (found[0].read_bytes(), found[1]) if found else None
    return suggest_palette(accent, get_context(store, project), llm, logo)


def polish(store: ProjectStore, project: Project, llm: LLMProvider | None, goals: str) -> PolishedGoals:
    report = get_report(store, project, llm, ai=False)
    return polish_goals(goals, get_context(store, project), report, llm)

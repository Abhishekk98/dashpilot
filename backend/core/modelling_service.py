"""Glue between stored projects and the data model (keeps route handlers thin)."""

from __future__ import annotations

import logging

from core import tmdl
from core.cleaning_service import cleaned_tables
from core.modelling import AIModelAnswer, ModelPlan, ModelSettings, ai_classify, ai_note_for, build_model, signature
from core.profiling_service import get_report
from core.projects import Project, ProjectStore
from llm import LLMProvider

logger = logging.getLogger(__name__)


def _settings(store: ProjectStore, project: Project) -> ModelSettings:
    return ModelSettings.model_validate(store.read_model(project.id).get("settings", {}))


def _build(store: ProjectStore, project: Project, llm: LLMProvider | None, run_ai: bool):
    report = get_report(store, project, llm, ai=False)
    cleaned = cleaned_tables(store, project, report)
    data = store.read_model(project.id)
    sig = signature(report)

    # The AI classification is cached per table set; run_ai=False never waits on the LLM.
    cache = data.get("ai") if (data.get("ai") or {}).get("signature") == sig else None
    answer, status, note = None, "off", None
    if cache:
        status, note = cache["status"], cache.get("note")
        answer = AIModelAnswer.model_validate(cache["answer"]) if cache.get("answer") else None
    elif llm is not None and report.tables:
        status = "pending"
        if run_ai:
            try:
                answer, status = ai_classify(report, llm), "done"
            except Exception as exc:  # AI problems must never break the model step
                logger.warning("Model AI refinement skipped: %s", exc)
                status, note = "failed", ai_note_for(exc)
            data["ai"] = {"signature": sig, "status": status, "note": note,
                          "answer": answer.model_dump() if answer else None}
            store.write_model(project.id, data)

    plan = build_model(report, cleaned, _settings(store, project), answer)
    plan.ai_status, plan.ai_note = status, note
    plan.tmdl_errors = tmdl.check(plan)
    plan.tmdl_valid = not plan.tmdl_errors
    return plan, {name: result for name, (_, _, result) in cleaned.items()}


def get_model(store: ProjectStore, project: Project, llm: LLMProvider | None, run_ai: bool = False) -> ModelPlan:
    return _build(store, project, llm, run_ai)[0]


def save_settings(store: ProjectStore, project: Project, llm: LLMProvider | None, settings: ModelSettings) -> ModelPlan:
    data = store.read_model(project.id)
    data["settings"] = settings.model_dump(mode="json")
    store.write_model(project.id, data)
    return get_model(store, project, llm)


def tmdl_files(store: ProjectStore, project: Project, llm: LLMProvider | None) -> dict[str, str]:
    plan, results = _build(store, project, llm, run_ai=False)
    return tmdl.build_files(plan, results, project.name)

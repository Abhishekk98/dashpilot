"""Glue between stored projects and the insights engine (keeps route handlers thin)."""

from __future__ import annotations

import hashlib
import json
import logging
import time

from pydantic import BaseModel

from core.context_service import get_context
from core.dax import StoredMeasures, build_plan
from core.dax_service import FILE as MEASURES_FILE
from core.dax_service import gen_context
from core.insights import (
    AskResult,
    Engine,
    Insight,
    InsightPlan,
    Question,
    ai_enrich,
    ai_error,
    add_texts,
    ai_spec,
    compute_insights,
    execute,
    link_questions,
    rule_spec,
    template_questions,
    validate_spec,
)
from core.projects import Project, ProjectStore
from llm import LLMProvider

logger = logging.getLogger(__name__)
FILE = "insights.json"
MAX_ASKED = 10
RETRY_AFTER_S = 30 * 60


class InsightError(ValueError):
    """User-facing problem (empty question, nothing to analyse)."""


class AskResponse(BaseModel):
    plan: InsightPlan
    asked: AskResult


def _engine(store: ProjectStore, project: Project, llm: LLMProvider | None) -> Engine:
    ctx = gen_context(store, project, llm)
    stored = StoredMeasures.model_validate(store.read_json(project.id, MEASURES_FILE))
    _, measures = build_plan(ctx, stored, llm is not None)
    return Engine(ctx, measures)


def _signature(insights: list[Insight]) -> str:
    payload = json.dumps([(i.id, sorted((k, round(v, 6)) for k, v in i.facts.items())) for i in insights])
    return hashlib.sha1(payload.encode()).hexdigest()


def get_insights(store: ProjectStore, project: Project, llm: LLMProvider | None, run_ai: bool = False, notes: list[str] | None = None) -> InsightPlan:
    engine = _engine(store, project, llm)
    insights, north, dims = compute_insights(engine)
    context = get_context(store, project)
    questions = template_questions(engine, insights, dims, context.audiences)
    data = store.read_json(project.id, FILE)
    sig = _signature(insights)
    ai = data.get("ai") if (data.get("ai") or {}).get("signature") == sig else None
    if ai and ai["status"] == "failed" and run_ai and time.time() - ai.get("at", 0) > RETRY_AFTER_S:
        ai = None  # quota resets / transient errors: try again, at most every 30 minutes
    status, note = ("off" if llm is None else "available"), None

    if ai is None and llm is not None and run_ai and insights:
        try:
            ai_questions, accepted, rejected = ai_enrich(insights, questions, context.industries, context.audiences, context.goals, llm)
            ai = {
                "signature": sig, "status": "done",
                "note": f"{rejected} AI narrative{'s' if rejected != 1 else ''} rejected by the grounding check; template text kept." if rejected else None,
                "questions": [q.model_dump() for q in ai_questions],
                "narratives": {i.id: {"headline": i.headline, "body": i.body, "action": i.action} for i in insights if i.narrative_source == "ai"},
            }
        except Exception as exc:  # AI problems never block computed insights
            logger.warning("Insight narration failed: %s", exc)
            ai = {"signature": sig, "status": "failed", "note": ai_error(exc), "questions": [], "narratives": {}, "at": time.time()}
        data["ai"] = ai
        store.write_json(project.id, FILE, data)
    if ai is not None:
        status, note = ai["status"], ai.get("note")
        for i in insights:
            n = ai["narratives"].get(i.id)
            if n:
                i.headline, i.body, i.action, i.narrative_source = n["headline"], n["body"], n["action"], "ai"
        if ai["questions"]:
            questions = [Question.model_validate(q) for q in ai["questions"]]

    asked = [Insight.model_validate(x) for x in data.get("asked", [])]
    all_insights = insights + [a for a in asked if a.id not in {i.id for i in insights}]
    link_questions(questions, insights)
    pinned = set(data.get("pinned", []))
    for i in all_insights:
        i.pinned = i.id in pinned
    return InsightPlan(
        insights=all_insights, questions=questions, north_star=north,
        rows_scanned=engine.ctx.fact.rows if engine.ctx.fact else 0,
        dimensions=[d.column for d in dims],
        confidence=round(sum(i.confidence for i in insights) / len(insights), 3) if insights else 0.0,
        ai_status=status, ai_note=note, pinned=[i.id for i in all_insights if i.pinned], notes=notes or [],
    )


def ask(store: ProjectStore, project: Project, llm: LLMProvider | None, question: str) -> AskResponse:
    question = question.strip()
    if len(question) < 3:
        raise InsightError("Type a question first, e.g. 'Which city has the highest revenue this year?'")
    engine = _engine(store, project, llm)
    spec, source, note = None, "rules", None
    if llm is not None:
        try:
            spec, source = validate_spec(ai_spec(question, engine, llm), engine), "ai"
        except Exception as exc:  # unknown names, bad JSON, quota: fall back to keyword rules
            logger.info("AI query mapping fell back to rules: %s", exc)
            note = f"AI could not map the question ({ai_error(exc) if not isinstance(exc, ValueError) else exc}); used keyword matching."
    if spec is None:
        raw = rule_spec(question, engine)
        if raw is None:
            raise InsightError("No measures are available to answer questions yet.")
        spec = validate_spec(raw, engine)
    insight = execute(spec, engine, question)
    add_texts(engine, insight)
    data = store.read_json(project.id, FILE)
    asked = [a for a in data.get("asked", []) if a.get("id") != insight.id]
    data["asked"] = ([insight.model_dump(mode="json")] + asked)[:MAX_ASKED]
    store.write_json(project.id, FILE, data)
    plan = get_insights(store, project, llm, notes=[note] if note else None)
    return AskResponse(plan=plan, asked=AskResult(question=question, spec=spec, insight=insight, source=source))


def set_pinned(store: ProjectStore, project: Project, llm: LLMProvider | None, insight_id: str, pinned: bool) -> InsightPlan:
    data = store.read_json(project.id, FILE)
    current = [p for p in data.get("pinned", []) if p != insight_id]
    data["pinned"] = current + ([insight_id] if pinned else [])
    store.write_json(project.id, FILE, data)
    return get_insights(store, project, llm)


def remove_asked(store: ProjectStore, project: Project, llm: LLMProvider | None, insight_id: str) -> InsightPlan:
    data = store.read_json(project.id, FILE)
    data["asked"] = [a for a in data.get("asked", []) if a.get("id") != insight_id]
    data["pinned"] = [p for p in data.get("pinned", []) if p != insight_id]
    store.write_json(project.id, FILE, data)
    return get_insights(store, project, llm)

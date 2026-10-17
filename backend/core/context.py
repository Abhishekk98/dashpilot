"""Business context and brand kit: company, industry, audience, goals, palette. (Spec Module 4)

Everything has a rule-based answer so the step works without an API key; the AI helpers
(suggest context from the data, harmonic palette, polish goals) upgrade those answers when a
provider is configured and fall back to the rules on any AI failure.
"""

from __future__ import annotations

import colorsys
import json
import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from core.profiling import QualityReport
from llm import LLMError, LLMProvider

logger = logging.getLogger(__name__)

PROMPTS = Path(__file__).resolve().parent.parent / "llm" / "prompts"

INDUSTRIES = [
    "Retail", "Food Delivery", "E-commerce", "Finance & FinTech", "HR & People", "Healthcare",
    "SaaS & Subscription", "Manufacturing", "Logistics & Fleet", "Education", "Marketing Ops",
]
AUDIENCES = [
    "Executive Leadership", "Sales Teams", "Growth Marketing", "Operations & Dispatch",
    "Financial Controllers", "Product Managers",
]
FONT_STACKS = ["Outfit + Inter", "Segoe UI", "Inter", "Georgia + Segoe UI"]
Archetype = Literal["dark_futuristic", "light_elegant", "glassmorphism", "minimal_corporate", "neon_tech"]
Source = Literal["ai", "rules"]

LOGO_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}
MAX_LOGO_BYTES = 2 * 1024 * 1024
_HEX = re.compile(r"^#[0-9A-F]{6}$")


# --- models -------------------------------------------------------------------------

class BrandPalette(BaseModel):
    accent: str = "#F8CF4B"
    base: str = "#232323"
    muted: str = "#4F5665"
    canvas: str = "#EEEEEC"
    growth: str = "#4CAF7A"

    @field_validator("*", mode="before")
    @classmethod
    def _hex(cls, value: str) -> str:
        value = str(value).strip().upper()
        if re.fullmatch(r"#?[0-9A-F]{3}", value):  # #ABC -> #AABBCC
            value = "#" + "".join(c * 2 for c in value.lstrip("#"))
        value = value if value.startswith("#") else f"#{value}"
        if not _HEX.match(value):
            raise ValueError("colors must be hex like #F8CF4B")
        return value


class LogoRef(BaseModel):
    filename: str
    extension: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime


class BusinessContext(BaseModel):
    company_name: str = Field(default="", max_length=120)
    industries: list[str] = []
    audiences: list[str] = []
    goals: str = Field(default="", max_length=2000)
    palette: BrandPalette = BrandPalette()
    mode: Literal["light", "dark"] = "light"
    font_stack: str = FONT_STACKS[0]
    archetype: Archetype = "light_elegant"
    domain_score: int | None = Field(default=None, ge=0, le=100)
    logo: LogoRef | None = None
    updated_at: datetime | None = None  # None = never saved (screen pre-fills suggestions)

    @field_validator("industries")
    @classmethod
    def _known_industries(cls, value: list[str]) -> list[str]:
        return _known(value, INDUSTRIES, "industry")

    @field_validator("audiences")
    @classmethod
    def _known_audiences(cls, value: list[str]) -> list[str]:
        return _known(value, AUDIENCES, "audience")

    @field_validator("font_stack")
    @classmethod
    def _known_font(cls, value: str) -> str:
        if value not in FONT_STACKS:
            raise ValueError(f"font_stack must be one of {FONT_STACKS}")
        return value


def _known(values: list[str], allowed: list[str], what: str) -> list[str]:
    unknown = [v for v in values if v not in allowed]
    if unknown:
        raise ValueError(f"unknown {what}: {', '.join(unknown)}")
    return list(dict.fromkeys(values))  # de-duplicate, keep order


class ContextSuggestion(BaseModel):
    industries: list[str]
    audiences: list[str]
    goals: str
    domain_score: int = Field(ge=0, le=100)
    source: Source
    note: str | None = None


class PaletteSuggestion(BaseModel):
    palette: BrandPalette
    rationale: str
    source: Source
    note: str | None = None


class PolishedGoals(BaseModel):
    goals: str
    source: Source
    note: str | None = None


# AI answer shapes (validated, then filtered against the allowed lists).
class _AIContext(BaseModel):
    industries: list[str]
    audiences: list[str]
    goals: str
    domain_score: int


class _AIPalette(BaseModel):
    accent: str
    base: str
    muted: str
    canvas: str
    growth: str
    rationale: str


class _AIGoals(BaseModel):
    goals: str


# --- suggest context from the data ----------------------------------------------------------

# Column / table name hints per industry. Each distinct matching word counts once.
_INDUSTRY_HINTS: dict[str, str] = {
    "Food Delivery": r"restaurant|delivery|courier|rider|menu|cuisine|dish|tip",
    "Logistics & Fleet": r"shipment|shipping|fleet|vehicle|route|warehouse|dispatch|freight|carrier|driver|tracking",
    "Finance & FinTech": r"txn|transaction|fraud|credit|loan|account|balance|card|payment|interest|bank|merchant",
    "Healthcare": r"patient|diagnosis|hospital|doctor|clinic|admission|treatment|ward",
    "HR & People": r"employee|salary|hire|attrition|department|payroll|leave|tenure|headcount",
    "SaaS & Subscription": r"subscription|mrr|arr|churn|plan|seat|trial|renewal|tenant",
    "E-commerce": r"order|cart|sku|checkout|shipping|return|product|prime|discount",
    "Retail": r"store|sku|product|pos|basket|inventory|category|brand|revenue",
    "Education": r"student|course|grade|enrol|teacher|exam|semester|school",
    "Marketing Ops": r"campaign|click|impression|lead|ctr|cpc|conversion|channel|utm|ad",
    "Manufacturing": r"machine|production|defect|plant|batch|downtime|yield|shift",
}
_INDUSTRY_AUDIENCE = {
    "Finance & FinTech": "Financial Controllers",
    "Marketing Ops": "Growth Marketing",
    "Logistics & Fleet": "Operations & Dispatch",
    "Food Delivery": "Operations & Dispatch",
    "Manufacturing": "Operations & Dispatch",
    "Retail": "Sales Teams",
    "E-commerce": "Sales Teams",
    "SaaS & Subscription": "Product Managers",
}


def _words(report: QualityReport) -> set[str]:
    names = [t.name for t in report.tables] + [c.name for t in report.tables for c in t.column_profiles]
    return {w for n in names for w in re.split(r"[^a-z0-9]+", n.lower()) if w}


def rule_suggestion(report: QualityReport) -> ContextSuggestion:
    words = _words(report)
    scores = Counter(
        {ind: sum(1 for w in words if re.fullmatch(f"(?:{pattern})s?", w)) for ind, pattern in _INDUSTRY_HINTS.items()}
    )
    ranked = [ind for ind, n in scores.most_common() if n > 0]
    top = ranked[:1] + [i for i in ranked[1:2] if scores[i] >= max(2, scores[ranked[0]] - 1)]
    audiences = ["Executive Leadership"] + [_INDUSTRY_AUDIENCE[i] for i in top if i in _INDUSTRY_AUDIENCE]
    best = scores[top[0]] if top else 0
    return ContextSuggestion(
        industries=top,
        audiences=list(dict.fromkeys(audiences)),
        goals=_goal_template(report),
        domain_score=min(90, 40 + best * 10) if top else 30,
        source="rules",
    )


def _goal_template(report: QualityReport) -> str:
    cols = [c for t in report.tables for c in t.column_profiles]
    measures = [c.name for c in cols if c.role == "measure"][:3]
    dims = [c.name for c in cols if c.role in ("categorical_slicer", "geo_dimension")][:3]
    has_time = any(c.role == "time_dimension" for c in cols)
    if not measures:
        return ""
    parts = [f"Track {', '.join(measures)}"]
    if has_time:
        parts.append("over time (month-over-month and year-over-year)")
    if dims:
        parts.append(f"broken down by {', '.join(dims)}")
    return " ".join(parts) + ", and highlight the main drivers of change."


def _digest(report: QualityReport) -> str:
    return json.dumps(
        [
            {
                "table": t.name,
                "rows": t.rows,
                "columns": [{"name": c.name, "role": c.role, "samples": c.sample_values[:3]} for c in t.column_profiles],
            }
            for t in report.tables
        ],
        separators=(",", ":"),
    )


def _ai_note(exc: Exception) -> str:
    return str(exc) if isinstance(exc, LLMError) else f"AI request failed ({type(exc).__name__})"


def suggest_context(report: QualityReport, llm: LLMProvider | None) -> ContextSuggestion:
    rules = rule_suggestion(report)
    if llm is None or not report.tables:
        return rules
    prompt = (
        (PROMPTS / "context_suggest.md").read_text(encoding="utf-8")
        .replace("{industries}", json.dumps(INDUSTRIES))
        .replace("{audiences}", json.dumps(AUDIENCES))
        .replace("{profile}", _digest(report))
    )
    try:
        answer = llm.generate_text(prompt, json_schema=_AIContext)
    except Exception as exc:  # AI problems must never break the screen
        logger.warning("Context suggestion fell back to rules: %s", exc)
        return rules.model_copy(update={"note": _ai_note(exc)})
    industries = [i for i in answer.industries if i in INDUSTRIES][:3]
    audiences = [a for a in answer.audiences if a in AUDIENCES][:3]
    if not industries:
        return rules.model_copy(update={"note": "AI answer had no known industry"})
    return ContextSuggestion(
        industries=industries,
        audiences=audiences or rules.audiences,
        goals=answer.goals.strip()[:2000] or rules.goals,
        domain_score=max(0, min(100, answer.domain_score)),
        source="ai",
    )


# --- palette ---------------------------------------------------------------------------

def _hls(hex_color: str) -> tuple[float, float, float]:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)


def _hex_from_hls(h: float, lightness: float, saturation: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, lightness, saturation)
    return "#" + "".join(f"{round(v * 255):02X}" for v in (r, g, b))


def harmonic_palette(accent: str) -> BrandPalette:
    """Rule-based palette around an accent: tinted charcoal, slate, warm canvas, a growth green."""
    accent = BrandPalette(accent=accent).accent
    h, _, _ = _hls(accent)
    degrees = h * 360
    # Keep "growth" readable as positive: green, or teal when the accent is already green.
    growth = "#2E9C9C" if 80 <= degrees <= 170 else "#4CAF7A"
    return BrandPalette(
        accent=accent,
        base=_hex_from_hls(h, 0.14, 0.06),
        muted=_hex_from_hls(h + 0.5, 0.35, 0.12),  # complementary slate keeps secondary series calm
        canvas=_hex_from_hls(h, 0.93, 0.08),
        growth=growth,
    )


def svg_accent(svg: bytes) -> str | None:
    """Most frequent saturated, mid-light color in an SVG logo (None when it is monochrome)."""
    text = svg.decode("utf-8", errors="ignore")
    colors = [BrandPalette(accent=m).accent for m in re.findall(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", text)]
    usable = [c for c in colors if _hls(c)[2] >= 0.25 and 0.2 <= _hls(c)[1] <= 0.85]
    return Counter(usable).most_common(1)[0][0] if usable else None


def suggest_palette(
    accent: str,
    context: BusinessContext,
    llm: LLMProvider | None,
    logo: tuple[bytes, str] | None = None,
) -> PaletteSuggestion:
    """Harmonic 5-color palette. The logo (bytes, content type) is used when one is uploaded."""
    if logo and logo[1] == "image/svg+xml":
        accent = svg_accent(logo[0]) or accent
    rules = PaletteSuggestion(
        palette=harmonic_palette(accent),
        rationale="Tinted charcoal and canvas from the accent hue, a complementary slate for secondary series, and a green kept for growth.",
        source="rules",
    )
    if llm is None:
        return rules
    prompt = (
        (PROMPTS / "context_palette.md").read_text(encoding="utf-8")
        .replace("{accent}", accent)
        .replace("{industries}", ", ".join(context.industries) or "not set")
        .replace("{mode}", context.mode)
        .replace("{archetype}", context.archetype)
    )
    try:
        if logo and logo[1] != "image/svg+xml":
            answer = llm.analyze_image(logo[0], prompt, mime_type=logo[1], json_schema=_AIPalette)
        else:
            answer = llm.generate_text(prompt, json_schema=_AIPalette)
        palette = BrandPalette(**answer.model_dump(exclude={"rationale"}))
    except Exception as exc:  # includes invalid hex values in the AI answer
        logger.warning("Palette suggestion fell back to rules: %s", exc)
        return rules.model_copy(update={"note": _ai_note(exc)})
    return PaletteSuggestion(palette=palette, rationale=answer.rationale.strip()[:400], source="ai")


# --- goals --------------------------------------------------------------------------------

def polish_goals(goals: str, context: BusinessContext, report: QualityReport, llm: LLMProvider | None) -> PolishedGoals:
    goals = goals.strip()
    if llm is None:
        return PolishedGoals(goals=goals, source="rules", note="No AI key configured; goals left as written.")
    if not goals:
        return PolishedGoals(goals=goals, source="rules", note="Write a goal first, then polish it.")
    prompt = (
        (PROMPTS / "context_polish.md").read_text(encoding="utf-8")
        .replace("{goals}", goals)
        .replace("{company}", context.company_name or "the company")
        .replace("{industries}", ", ".join(context.industries) or "not set")
        .replace("{audiences}", ", ".join(context.audiences) or "not set")
        .replace("{profile}", _digest(report))
    )
    try:
        answer = llm.generate_text(prompt, json_schema=_AIGoals)
    except Exception as exc:
        logger.warning("Goal polishing failed: %s", exc)
        return PolishedGoals(goals=goals, source="rules", note=_ai_note(exc))
    return PolishedGoals(goals=answer.goals.strip()[:2000] or goals, source="ai")

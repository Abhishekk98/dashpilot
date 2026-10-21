"""Google Stitch prompt for the planned dashboard (spec 9.1).

The prompt follows the spec's template and adds the exact layout (every card's position, size and
title from the Dashboard Plan) plus strict build rules, so the HTML Stitch exports can be imported
1:1: one 1280x720 canvas, one card per visual with its exact title, empty-looking chart areas.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.context import BusinessContext
from core.planner import DashboardPlan, PlanVisual

StitchStyle = Literal["dark_futuristic", "light_elegant", "glassmorphism", "minimal_corporate", "neon_tech"]

STYLES: dict[str, tuple[str, str, str]] = {  # id -> (label, direction, card style)
    "dark_futuristic": ("Dark Futuristic", "premium, futuristic and elegant on a near-black canvas, subtle accent glow", "dark translucent cards with a 1px light border and a soft accent glow"),
    "light_elegant": ("Light Elegant", "premium, airy and elegant on a warm light canvas, refined editorial spacing", "white cards with a very soft shadow"),
    "glassmorphism": ("Glassmorphism", "premium glassmorphism on a soft gradient canvas, layered depth", "frosted translucent white cards with blur and a thin white border"),
    "minimal_corporate": ("Minimal Corporate", "clean, minimal and corporate, flat surfaces, strict grid", "flat white cards with a 1px light-grey border, no shadow"),
    "neon_tech": ("Neon Tech", "bold neon tech on a deep navy canvas, high contrast", "dark cards with a thin neon outline and glow"),
}

DARK = {"dark_futuristic": ("#0E0F12", "#F2F0F0"), "neon_tech": ("#0B1020", "#EAF2FF")}  # (canvas, text)

KIND = {
    "card": "KPI card", "line": "line chart", "area": "area chart", "clustered_bar": "clustered bar chart (horizontal bars)",
    "clustered_column": "clustered column chart (vertical bars)", "stacked_bar": "stacked bar chart", "stacked_column": "stacked column chart",
    "donut": "donut chart", "map": "map", "filled_map": "filled map", "table": "table", "matrix": "matrix",
    "slicer": "slicer (dropdown pill)", "gauge": "gauge", "scatter": "scatter chart", "waterfall": "waterfall chart",
    "funnel": "funnel chart", "text_box": "text box",
}
FONTS = {"Outfit + Inter": "Outfit", "Segoe UI": "Segoe UI", "Inter": "Inter", "Georgia + Segoe UI": "Georgia"}


class StitchPrompt(BaseModel):
    style: StitchStyle
    styles: list[dict[str, str]]
    prompt: str
    visuals: int


def _field(v: PlanVisual) -> str:
    return (v.dimension or "").split("[")[-1].rstrip("]").replace("_", " ")


def _line(v: PlanVisual) -> str:
    b = v.box
    where = f"x {b.x}, y {b.y}, {b.w}×{b.h}px"
    if v.role == "slicer":
        return f'- Slicer "{v.title}" (dropdown pill) at {where}: the label "{v.title}" on the left, a dropdown on the right.'
    if v.role == "kpi":
        return f'- KPI card "{v.title}" at {where}: the title, then one large placeholder value, a % change and a tiny trend line.'
    if v.role == "insights":
        return f'- Text box "{v.title}" at {where}: the title, then up to 3 short bullet lines of placeholder text.'
    what = ", ".join(v.measures) + (f" by {_field(v)}" if v.dimension else "")
    return f'- {KIND.get(v.type, v.type).capitalize()} "{v.title}" at {where}: shows {what}.'


def build(plan: DashboardPlan, context: BusinessContext, style: StitchStyle = "light_elegant", questions: list[str] | None = None) -> StitchPrompt:
    label, direction, cards = STYLES[style]
    p = context.palette
    # Dark styles need a dark canvas and light text; light styles use the brand's own canvas and text.
    canvas, text = DARK.get(style, (p.canvas, p.base))
    heading = FONTS.get(context.font_stack, "Segoe UI")
    company = context.company_name or plan.title.removesuffix(" Performance Dashboard")
    industry = ", ".join(context.industries) or "business"
    audience = ", ".join(context.audiences) or "executives"
    kpis = [v for v in plan.visuals if v.role == "kpi"]
    slicers = [v for v in plan.visuals if v.role == "slicer"]
    rows: dict[int, list[PlanVisual]] = {}
    for v in plan.visuals:
        if v.role in ("chart", "insights"):
            rows.setdefault(v.box.y, []).append(v)
    visual_rows = "\n".join(
        f"- Row {n + 2}: " + "; ".join(f'{KIND.get(v.type, v.type)} "{v.title}"' for v in sorted(rows[y], key=lambda v: v.box.x))
        for n, y in enumerate(sorted(rows))
    )
    layout = "\n".join(_line(v) for v in plan.visuals)
    qs = "\n".join(f"- {q}" for q in (questions or [])[:6]) or "- " + "\n- ".join(v.purpose for v in plan.visuals if v.role == "chart" and v.purpose)
    allowed = "KPI/card, line, area, clustered bar/column, stacked bar/column, donut, map/filled map, table, matrix, slicer, gauge, scatter, waterfall, funnel, text box"
    prompt = f"""Design a premium, futuristic, elegant Power BI dashboard UI on a 1280x720 canvas for {company}, a {industry} company. Audience: {audience}.

BRAND THEME: Primary {p.accent}, background {canvas}, cards: {cards}, 16px rounded corners, accents {p.accent}, {p.growth}, {p.muted}; text {text}. Headings in "{heading}", all chart labels and numbers in "Segoe UI". Style: {label} — {direction}.

LAYOUT:
- Top bar: logo placeholder (left), title "{plan.title}", slicers: {", ".join(f'"{s.title}"' for s in slicers) or "none"} (right)
- Row 1: {len(kpis)} KPI cards: {", ".join(f'"{k.title}"' for k in kpis)} — each with value, % change and small trend
{visual_rows}

EXACT POSITIONS (px on the 1280x720 canvas — keep every card exactly here):
- Header at x 24, y 14, 640×46px: logo placeholder, the title "{plan.title}" and the subtitle "{company} • {plan.subtitle}".
{layout}

BUSINESS QUESTIONS THIS DASHBOARD ANSWERS:
{qs}

RULES (the design is imported into Power BI automatically, so follow them exactly):
1. The whole dashboard is ONE root container exactly 1280px wide and 720px tall. Nothing outside it, no scrolling, no responsive resizing.
2. Every item listed under EXACT POSITIONS is its own separate card container (its own background, border or shadow) at exactly that position and size. Do not add any other cards, sidebars, navigation, tabs, footers or extra sections.
3. Each card shows its title text EXACTLY as written above (same words, same capitalisation) as the first text in the card. Titles are used to match the Power BI visuals.
4. Inside chart cards draw only a simple placeholder of that chart type. No other text in the chart area: no axis labels, legends, numbers or annotations — only the title.
5. Use only chart types available in Power BI: {allowed}.
6. All chart labels and numbers in "Segoe UI". Keep consistent spacing and alignment on the grid above.
7. No photos or illustrations; only the logo placeholder in the header.
Premium, minimal, high contrast, generous spacing, aligned grid, no clutter."""
    return StitchPrompt(style=style, styles=[{"id": k, "label": v[0]} for k, v in STYLES.items()], prompt=prompt, visuals=len(plan.visuals))

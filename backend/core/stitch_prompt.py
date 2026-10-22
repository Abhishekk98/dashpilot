"""Google Stitch prompt for the planned dashboard.

Generates a focused, high-level prompt specifying:
- Dashboard title & pages
- Per-page KPI cards with exact measure names
- Charts with type and dimension/measure fields
- Slicers (filters)
- AI insights panel
- Left sidebar navigation
- Style: premium, futuristic, advanced layout, 1280x720 Power BI canvas, dark/glass theme, sidebar navigation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.context import BusinessContext
from core.planner import DashboardPlan, PlanVisual

StitchStyle = Literal["dark_futuristic", "light_elegant", "glassmorphism", "minimal_corporate", "neon_tech"]

STYLES: dict[str, tuple[str, str, str]] = {  # id -> (label, direction, card style)
    "dark_futuristic": ("Dark Futuristic", "premium, futuristic, advanced layout, 1280x720 Power BI canvas, dark/glass theme, sidebar navigation", "dark translucent cards with a 1px light border and a soft neon glow"),
    "light_elegant": ("Light Elegant", "premium, airy and elegant on a warm light canvas, refined editorial spacing", "white frosted glass cards with a very soft shadow"),
    "glassmorphism": ("Glassmorphism", "premium glassmorphism on a soft gradient canvas, layered depth", "frosted translucent glass cards with blur and a thin white border"),
    "minimal_corporate": ("Minimal Corporate", "clean, minimal and corporate, flat dark surfaces, strict grid", "flat dark cards with a 1px subtle border, no heavy shadow"),
    "neon_tech": ("Neon Tech", "bold neon tech on a deep navy canvas, high contrast", "dark cards with a thin neon outline and cyber glow"),
}

DARK = {"dark_futuristic": ("#0A0E1A", "#F2F5FA"), "neon_tech": ("#080C16", "#EAF2FF"), "minimal_corporate": ("#0D1117", "#E6EDF3")}

KIND = {
    "card": "KPI card", "line": "line chart", "area": "area chart", "clustered_bar": "clustered bar chart (horizontal)",
    "clustered_column": "clustered column chart (vertical)", "stacked_bar": "stacked bar chart", "stacked_column": "stacked column chart",
    "donut": "donut chart", "map": "map", "filled_map": "filled map", "table": "table", "matrix": "matrix with data bars",
    "slicer": "filter dropdown pill", "gauge": "gauge chart", "scatter": "scatter chart", "waterfall": "waterfall chart",
    "funnel": "funnel chart", "text_box": "text box",
}


class StitchPrompt(BaseModel):
    style: StitchStyle
    styles: list[dict[str, str]]
    prompt: str
    visuals: int


def _field(v: PlanVisual) -> str:
    return (v.dimension or "").split("[")[-1].rstrip("]").replace("_", " ")


def build(plan: DashboardPlan, context: BusinessContext, style: StitchStyle = "dark_futuristic", questions: list[str] | None = None) -> StitchPrompt:
    label, direction, cards = STYLES.get(style, STYLES["dark_futuristic"])
    p = context.palette
    canvas, text = DARK.get(style, (p.canvas, p.base))
    company = context.company_name or plan.title.removesuffix(" Performance Dashboard")

    pages_list = plan.pages if plan.pages else ["Overview"]
    curr_page = pages_list[0] if pages_list else "Overview"
    pages_str = ", ".join(f'"{pg}"' for pg in pages_list)

    slicers = [v for v in plan.visuals if v.role == "slicer"]
    slicers_lines = [f'- Slicer: "{s.title}" (Field: {_field(s) or s.title})' for s in slicers]
    slicers_block = "\n".join(slicers_lines) if slicers_lines else "- Date Range slicer and Category filter pills"

    kpis = [v for v in plan.visuals if v.role == "kpi"]
    kpis_lines = []
    for k in kpis:
        m_name = k.measures[0] if k.measures else k.title
        kpis_lines.append(f'- KPI Card: "{k.title}" (Measure: [{m_name}]) — value + "vs PY" delta pill + sparkline')
    kpis_block = "\n".join(kpis_lines) if kpis_lines else "- KPI cards for core business metrics"

    charts = [v for v in plan.visuals if v.role == "chart"]
    charts_lines = []
    for c in charts:
        ctype = KIND.get(c.type, c.type)
        m_str = ", ".join(f"[{m}]" for m in c.measures) or "metric"
        dim_str = f"by {_field(c)}" if c.dimension else ""
        charts_lines.append(f'- {ctype.capitalize()}: "{c.title}" (Measures: {m_str} {dim_str})')
    charts_block = "\n".join(charts_lines) if charts_lines else "- Charts showing trends and category distributions"

    insights = [v for v in plan.visuals if v.role == "insights"]
    insights_title = insights[0].title if insights else "Key Insights"

    prompt = f"""Design a dashboard UI on a 1280x720 Power BI canvas for {company}.

STYLE:
premium, futuristic, advanced layout, 1280x720 Power BI canvas, dark/glass theme, sidebar navigation
- Aesthetic: {label} — {direction}
- Canvas: Exact 1280x720 px, dark canvas {canvas}, primary text {text}, accent {p.accent}
- Cards: {cards}, 14-16px rounded corners, subtle shadows, consistent 16px grid

DASHBOARD TITLE & PAGES:
- Dashboard Title: "{plan.title}"
- Pages: {len(pages_list)} pages ({pages_str})
- Current Page: "{curr_page}"

NAVIGATION:
- Left sidebar navigation panel: logo placeholder at the top, followed by vertical page navigation buttons ({pages_str})
- Active page highlighted: "{curr_page}"

FILTERS (SLICERS):
{slicers_block}

KPI CARDS:
{kpis_block}
(Each card has metric title, large bold value, delta tag, and mini progress/sparkline)

CHARTS & VISUALIZATIONS:
{charts_block}
(Inside each chart card, show visual title and leave chart area clear with a clean subtle placeholder for Power BI interactive visuals)

AI INSIGHTS PANEL:
- "{insights_title}": numbered bullet points [1], [2], [3] summarizing key business takeaways and trends

RULES:
1. Root container must be exactly 1280px wide by 720px tall (overflow: hidden, no scrolling).
2. Each visual card MUST display its title EXACTLY as written above so Power BI can bind data automatically.
3. Clean typography using "Segoe UI" or "DIN", high contrast, aligned grid.
4. Export clean HTML with modern CSS/Tailwind and a full screenshot (screen.png)."""

    return StitchPrompt(style=style, styles=[{"id": k, "label": v[0]} for k, v in STYLES.items()], prompt=prompt, visuals=len(plan.visuals))

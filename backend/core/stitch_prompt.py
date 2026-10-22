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


def build(plan: DashboardPlan, context: BusinessContext, style: StitchStyle = "dark_futuristic", questions: list[str] | None = None,
          all_pages: list[str] | None = None) -> StitchPrompt:
    """Prompt for one page (`plan` is planner.page_plan); `all_pages` names every page for the menu."""
    label, direction, cards = STYLES.get(style, STYLES["dark_futuristic"])
    p = context.palette
    canvas, text = DARK.get(style, (p.canvas, p.base))
    company = context.company_name or plan.title.removesuffix(" Performance Dashboard")

    curr_page = plan.pages[0] if plan.pages else "Overview"
    pages_list = all_pages or plan.pages or ["Overview"]
    pages_str = ", ".join(f'"{pg}"' for pg in pages_list)

    slicers = [v for v in plan.visuals if v.role == "slicer"]
    slicers_lines = [f'- Filter dropdown "{s.title}" (field: {_field(s) or s.title}); write the name "{s.title}" just above or inside the dropdown'
                     for s in slicers]
    slicers_block = "\n".join(slicers_lines) if slicers_lines else "- A date range filter dropdown"

    kpis = [v for v in plan.visuals if v.role == "kpi"]
    kpis_lines = []
    for k in kpis:
        m_name = k.measures[0] if k.measures else k.title
        kpis_lines.append(f'- KPI card "{k.title}" (measure: [{m_name}])')
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

    menu = (f'- Left sidebar with a logo placeholder and one menu item per page, labelled exactly {pages_str}; '
            f'"{curr_page}" is the active item.' if len(pages_list) > 1 else "- Left sidebar with a logo placeholder (single page, no page menu).")
    prompt = f"""Design one page of a Power BI dashboard for {company}: page "{curr_page}" of {len(pages_list)} ({pages_str}).

STYLE:
premium, futuristic, advanced layout, 1280x720 Power BI canvas, dark/glass theme, sidebar navigation
- Look: {label}, {direction}
- Colours: canvas {canvas}, text {text}, accent {p.accent}
- Cards: {cards}, 14-16px rounded corners, consistent 16px grid

TITLE: "{plan.title}"

NAVIGATION:
{menu}

FILTERS:
{slicers_block}

KPI CARDS (title at the top; under it a placeholder value, a small vs PY change and a sparkline, which Power BI replaces with live visuals):
{kpis_block}

CHARTS (title at the top; the rest of the card is the chart area that Power BI fills):
{charts_block}

INSIGHTS PANEL:
- "{insights_title}": 3 numbered points

RULES:
1. The page is exactly 1280px wide and 720px tall (overflow hidden, no scrolling).
2. Every card is its own container and shows its title exactly as written above.
3. Power BI native chart types only. Use "Segoe UI" for chart text.
4. No other text: no status lines, sync times, data source names, canvas sizes or extra badges."""

    return StitchPrompt(style=style, styles=[{"id": k, "label": v[0]} for k, v in STYLES.items()], prompt=prompt, visuals=len(plan.visuals))

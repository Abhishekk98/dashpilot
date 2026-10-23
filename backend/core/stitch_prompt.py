"""Google Stitch prompt for the planned dashboard.

Generates a focused content-first prompt specifying:
- Dashboard title & pages
- Per-page KPI cards with exact measure names
- Charts with type and dimension/measure fields
- Slicers (filters)
- AI insights panel
- Required page navigation
- Creative, premium styling delegated to Stitch with dynamic aesthetic hints.
"""

from __future__ import annotations

import random
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

STYLE_HINTS: list[str] = [
    "STYLE HINT: Cyberpunk Neon HUD — deep obsidian canvas with sharp luminous cyan/electric-amber glowing accents, frosted translucent dark cards, and sleek telemetry rings.",
    "STYLE HINT: Frosted Glassmorphism Luxe — soft gradient dark backdrop, glass cards with blurred backdrop-filter, 1px iridescent white borders, and floating depth.",
    "STYLE HINT: Bento Grid Executive — asymmetric modular cards, bold typography, deep charcoal surfaces, vibrant emerald status indicators, and clean editorial structure.",
    "STYLE HINT: Tokyo Midnight Command Center — pitch-black theme, high-contrast neon violet and acid-lime accents, pill-shaped tags, and futuristic telemetry widgets.",
    "STYLE HINT: Titanium Dark Minimalist — matte dark-steel surfaces, razor-sharp architectural borders, amber telemetry highlights, and high-density metric widgets.",
    "STYLE HINT: Aurora Gradient Dream — layered deep indigo and plum canvas, iridescent aqua/violet border glows, ultra-modern typography, and floating elevation.",
    "STYLE HINT: Neo-Brutalist Cyber Analytics — bold high-contrast outlines, deep navy canvas, electric yellow and hot-pink pill badges, and structured modular blocks.",
    "STYLE HINT: Stealth Aero Glass — stealth matte carbon canvas, smoky translucent panels with subtle inner highlights, electric-blue accents, and modern cockpit layout.",
]

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
    style_hint = random.choice(STYLE_HINTS)
    company = context.company_name or plan.title.removesuffix(" Performance Dashboard")

    curr_page = plan.pages[0] if plan.pages else "Overview"
    pages_list = all_pages or plan.pages or ["Overview"]
    pages_str = ", ".join(f'"{pg}"' for pg in pages_list)

    slicers = [v for v in plan.visuals if v.role == "slicer"]
    slicers_lines = [f'- Filter dropdown "{s.title}" (field: {_field(s) or s.title}); write the name "{s.title}" clearly'
                     for s in slicers]
    slicers_block = "\n".join(slicers_lines) if slicers_lines else "- Date range filter dropdown"

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
        charts_lines.append(f'- {ctype.capitalize()}: "{c.title}" (Type: {c.type}, Measures: {m_str} {dim_str})')
    charts_block = "\n".join(charts_lines) if charts_lines else "- Charts showing trends and category distributions"

    insights = [v for v in plan.visuals if v.role == "insights"]
    insights_lines = [f'- Insights panel: "{v.title}"' for v in insights]
    insights_block = "\n".join(insights_lines) if insights_lines else '- Key Insights panel: "Key Insights"'

    nav_line = (
        f'Page navigation is REQUIRED: provide navigation buttons/menu for all {len(pages_list)} pages ({pages_str}). Current active page is "{curr_page}".'
        if len(pages_list) > 1
        else 'Single-page dashboard: header with title and filter controls required.'
    )

    prompt = f"""Create a premium, futuristic, creative Power BI dashboard (1280x720 per page). Use an advanced, non-generic layout of your choice: e.g. glassmorphism, neon dark, bento grid, sidebar navigation. Every element must fit within the page with no overlap.

{style_hint}

DASHBOARD: {company} — Page "{curr_page}" of {len(pages_list)} ({pages_str})
PAGE TITLE: "{plan.title}"

PAGE NAVIGATION (REQUIRED):
- {nav_line}

FILTERS / SLICERS:
{slicers_block}

KPI CARDS:
{kpis_block}

CHARTS:
{charts_block}

INSIGHTS:
{insights_block}"""

    return StitchPrompt(style=style, styles=[{"id": k, "label": v[0]} for k, v in STYLES.items()], prompt=prompt, visuals=len(plan.visuals))


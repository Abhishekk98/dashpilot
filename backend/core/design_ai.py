"""Design method B: DashPilot (AI) designs the 1280x720 page from the plan. (Spec Module 9.2)

Every variant starts from a deterministic HTML template for its style (which always satisfies the
design contract). With an AI key the LLM restyles that template; the result must pass
core/design_contract.check, with up to 2 repair retries fed with the validator's errors. If it still
fails, or there is no key / quota, the template itself is used, so this step always works.
"""

from __future__ import annotations

import hashlib
import html as htmllib
import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from core.context import BrandPalette, BusinessContext
from core.design_contract import check
from core.design_layouts import LAYOUTS, Arrangement, arrange, nav_slots, suggest
from core.planner import CANVAS_H, CANVAS_W, MARGIN, Box, DashboardPlan, PlanVisual, page_plan
from llm import LLMError, LLMNotConfiguredError, LLMProvider, LLMRateLimitError

logger = logging.getLogger(__name__)
PROMPT = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "design_generate.md"

Archetype = Literal[
    "dark_neon", "glass_light", "gradient_corporate", "command_center",
    "dark_futuristic", "light_elegant", "glassmorphism", "minimal_corporate", "neon_tech",
]
ARCHETYPE_MAP: dict[str, str] = {
    "dark_neon": "dark_neon",
    "glass_light": "glass_light",
    "gradient_corporate": "gradient_corporate",
    "command_center": "command_center",
    "dark_futuristic": "dark_neon",
    "neon_tech": "dark_neon",
    "light_elegant": "glass_light",
    "glassmorphism": "glass_light",
    "minimal_corporate": "gradient_corporate",
}
VARIANTS: list[tuple[str, str, str, str]] = [
    ("dark_neon", "Gradient Sidebar", "Deep navy canvas, a left sidebar with the page menu, vivid gradient KPI cards with icon badges and white values, soft glass chart cards.", "dark_neon"),
    ("glass_light", "Glass Tabs", "Pastel canvas with blurred colour blobs, frosted glass cards, a top bar with page tabs and colour-coded KPI icon chips.", "glass_light"),
    ("gradient_corporate", "Midnight Rings", "Dark banking look: a left rail with filters and page menu, KPI cards with gradient ring badges, deep navy chart cards.", "gradient_corporate"),
    ("command_center", "Command Center", "Near-black command center with a red accent and grid texture, a KPI ticker strip, a dense chart grid and an insights column.", "command_center"),
]
MAX_RETRIES = 2
MAX_HTML = 80_000


class DesignVariant(BaseModel):
    id: str  # Option B: an Archetype; Option C: "reference_close" / "reference_brand"
    label: str
    html: str
    source: Literal["ai", "template"]
    attempts: int = 0  # AI attempts made (0 = template only)
    errors: list[str] = []  # validator errors of the last failed AI attempt
    valid: bool = True
    engine: str = "static"
    note: str | None = None
    pages: list[str] = []  # HTML of every page (pages[0] == html); empty for single-page designs made before pages existed
    layouts: list[str] = []  # core.design_layouts name per page

    def page_html(self, page: int) -> str | None:
        pages = self.pages or [self.html]
        return pages[page - 1] if page <= len(pages) else None


def plan_signature(plan: DashboardPlan) -> str:
    payload = [(v.id, v.type, v.title, v.page, v.box.x, v.box.y, v.box.w, v.box.h) for v in plan.visuals] + [plan.title, plan.pages]
    return hashlib.sha1(json.dumps(payload).encode()).hexdigest()[:16]


# --- template -------------------------------------------------------------------------
# Four built-in looks, modelled on reference dashboards: a gradient-card sidebar dashboard (dark_neon),
# a pastel glassmorphism page with tabs (glass_light), a dark banking page with ring badges
# (gradient_corporate) and a red command center (command_center). Everything here is background art:
# no numbers or status text are drawn, because Power BI draws the real values on top.

def _fonts(font_stack: str) -> tuple[str, str, str]:
    """(heading font, body font, Google Fonts link or '')."""
    if font_stack.startswith("Outfit"):
        return "Outfit", "Inter", "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@400;500;600&display=swap"
    if font_stack == "Inter":
        return "Inter", "Inter", "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    if font_stack.startswith("Georgia"):
        return "Georgia", "Segoe UI", ""
    return "Segoe UI", "Segoe UI", ""


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# KPI card fills: one per card, in order (gradient, solid fallback for the theme detector).
_GRADIENT_KPIS = [
    ("linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)", "#8B5CF6"),
    ("linear-gradient(135deg, #3B82F6 0%, #06B6D4 100%)", "#3B82F6"),
    ("linear-gradient(135deg, #F43F5E 0%, #FB923C 100%)", "#F43F5E"),
    ("linear-gradient(135deg, #059669 0%, #34D399 100%)", "#059669"),
    ("linear-gradient(135deg, #6366F1 0%, #0EA5E9 100%)", "#6366F1"),
    ("linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)", "#F59E0B"),
]
# KPI icon chips (tint, ink) for the pastel glass look. Tints stay translucent so the theme
# detector does not pick a pastel as the accent colour.
_PASTEL_CHIPS = [("rgba(124,58,237,0.12)", "#7C3AED"), ("rgba(219,39,119,0.12)", "#DB2777"), ("rgba(2,132,199,0.12)", "#0284C7"),
                 ("rgba(22,163,74,0.12)", "#16A34A"), ("rgba(217,119,6,0.14)", "#D97706"), ("rgba(225,29,72,0.12)", "#E11D48")]


def _theme(archetype: str, p: BrandPalette) -> dict[str, str]:
    arch = ARCHETYPE_MAP.get(archetype, archetype)
    if arch == "dark_neon":
        return {
            "page": "#070A14",
            "canvas": "radial-gradient(ellipse 60% 55% at 92% 0%, rgba(139,92,246,0.20), transparent 60%), "
                      "radial-gradient(ellipse 50% 45% at 30% 100%, rgba(6,182,212,0.12), transparent 60%), #0B1020",
            "card": "rgba(20, 26, 46, 0.86)", "border": "1px solid rgba(148, 163, 255, 0.14)", "radius": "18px",
            "shadow": "0 12px 32px rgba(2, 6, 23, 0.55)", "blur": "none",
            "title": "#F1F5F9", "muted": "#94A3B8", "area": "rgba(255, 255, 255, 0.025)",
            "accent": "#A78BFA", "secondary": "#22D3EE", "logo": "linear-gradient(135deg, #8B5CF6, #D946EF)", "logo_ink": "#FFFFFF",
            "rail_bg": "linear-gradient(180deg, #121833 0%, #0D1228 100%)", "rail_border": "1px solid rgba(148, 163, 255, 0.12)",
            "kpi_value": "#FFFFFF", "kpi_title": "rgba(255, 255, 255, 0.90)",
            "nav_bg": "rgba(255, 255, 255, 0.04)", "nav_border": "1px solid rgba(255, 255, 255, 0.06)",
            "slicer_bg": "rgba(20, 26, 46, 0.92)",
        }
    if arch == "glass_light":
        return {
            "page": "#EEF0FA",
            "canvas": "linear-gradient(135deg, #FDF2F8 0%, #F5F3FF 45%, #F0F9FF 100%)",
            "card": "rgba(255, 255, 255, 0.62)", "border": "1px solid rgba(255, 255, 255, 0.92)", "radius": "20px",
            "shadow": "0 12px 32px rgba(99, 102, 241, 0.10), 0 2px 6px rgba(15, 23, 42, 0.04)", "blur": "blur(18px)",
            "title": "#1E1B4B", "muted": "#64748B", "area": "rgba(255, 255, 255, 0.35)",
            "accent": "#7C3AED", "secondary": "#DB2777", "logo": "linear-gradient(135deg, #7C3AED, #DB2777)", "logo_ink": "#FFFFFF",
            "rail_bg": "rgba(255, 255, 255, 0.55)", "rail_border": "1px solid rgba(255, 255, 255, 0.9)",
            "kpi_value": "#1E1B4B", "kpi_title": "#475569",
            "nav_bg": "rgba(255, 255, 255, 0.70)", "nav_border": "1px solid rgba(255, 255, 255, 0.95)",
            "slicer_bg": "rgba(255, 255, 255, 0.78)",
        }
    if arch == "gradient_corporate":
        return {
            "page": "#060A16",
            "canvas": "radial-gradient(ellipse 55% 50% at 100% 0%, rgba(56,189,248,0.14), transparent 60%), "
                      "radial-gradient(ellipse 45% 40% at 40% 110%, rgba(129,140,248,0.12), transparent 60%), #0A0F1E",
            "card": "#111A2E", "border": "1px solid rgba(148, 163, 184, 0.12)", "radius": "16px",
            "shadow": "0 10px 28px rgba(0, 0, 0, 0.40)", "blur": "none",
            "title": "#F8FAFC", "muted": "#8EA0BC", "area": "rgba(255, 255, 255, 0.02)",
            "accent": "#38BDF8", "secondary": "#818CF8", "logo": "linear-gradient(135deg, #38BDF8, #818CF8)", "logo_ink": "#06101F",
            "rail_bg": "linear-gradient(180deg, #0E1529 0%, #0B1122 100%)", "rail_border": "1px solid rgba(148, 163, 184, 0.10)",
            "kpi_value": "#F8FAFC", "kpi_title": "#8EA0BC",
            "nav_bg": "rgba(56, 189, 248, 0.05)", "nav_border": "1px solid rgba(56, 189, 248, 0.10)",
            "slicer_bg": "#111A2E",
        }
    return {
        "page": "#050506",
        "canvas": "radial-gradient(ellipse 45% 40% at 0% 0%, rgba(226,55,68,0.16), transparent 60%), "
                  "repeating-linear-gradient(0deg, rgba(255,255,255,0.022) 0 1px, transparent 1px 32px), "
                  "repeating-linear-gradient(90deg, rgba(255,255,255,0.022) 0 1px, transparent 1px 32px), #0A0A0C",
        "card": "#131317", "border": "1px solid rgba(255, 255, 255, 0.07)", "radius": "12px",
        "shadow": "0 8px 24px rgba(0, 0, 0, 0.50)", "blur": "none",
        "title": "#F4F4F5", "muted": "#8B8B94", "area": "rgba(255, 255, 255, 0.015)",
        "accent": "#E23744", "secondary": "#FF7A59", "logo": "linear-gradient(135deg, #E23744, #FF7A59)", "logo_ink": "#FFFFFF",
        "rail_bg": "#0E0E11", "rail_border": "1px solid rgba(226, 55, 68, 0.2)",
        "kpi_value": "#FFFFFF", "kpi_title": "#A1A1AA",
        "nav_bg": "#131317", "nav_border": "1px solid rgba(255, 255, 255, 0.08)",
        "slicer_bg": "#131317",
    }


def _box(v: PlanVisual) -> str:
    b = v.box
    return f"left:{b.x}px;top:{b.y}px;width:{b.w}px;height:{b.h}px"


_ICONS = {
    "money": '<path d="M12 3v18"/><path d="M16.5 7.5c0-1.7-2-3-4.5-3s-4.5 1.2-4.5 3 2 2.6 4.5 3 4.5 1.3 4.5 3.3-2 3.2-4.5 3.2-4.5-1.3-4.5-3"/>',
    "count": '<path d="M5 20V11"/><path d="M11 20V5"/><path d="M17 20v-7"/><path d="M3 20h18"/>',
    "rate": '<circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/><path d="M19 5 5 19"/>',
    "people": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8"/><path d="M18.5 14.4c1.8.8 3 2.7 3 5.6"/>',
    "time": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "trend": '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "spark": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
    "filter": '<path d="M3 5h18l-7 8.2V19l-4 2v-7.8z"/>',
    "date": '<rect x="3" y="5" width="18" height="16" rx="2.5"/><path d="M3 10h18M8 3v4M16 3v4"/>',
}
_ICON_WORDS = [
    ("rate", ("rate", "%", "ratio", "margin", "share", "percent", "conversion", "churn")),
    ("people", ("customer", "user", "client", "member", "employee", "people", "visitor", "patient", "student")),
    ("time", ("time", "days", "duration", "hours", "minutes", "lead")),
    ("money", ("revenue", "sales", "amount", "value", "volume", "profit", "cost", "price", "spend", "income", "aov", "gmv")),
    ("count", ("count", "order", "transaction", "number", "units", "qty", "quantity", "#", "total")),
]


def _icon(name: str, size: int = 18) -> str:
    return (f'<svg class="dp-icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">{_ICONS[name]}</svg>')


def _kpi_icon(title: str) -> str:
    low = title.lower()
    return next((name for name, words in _ICON_WORDS if any(w in low for w in words)), "trend")


def _container(v: PlanVisual, arch: str = "dark_neon", index: int = 0, value_color: str = "#FFFFFF") -> str:
    """One visual's card. `index` counts cards of the same role (KPI colours rotate with it);
    `value_color` is the colour Power BI gives the KPI's number (data-value-color)."""
    e = htmllib.escape
    attrs = f'data-visual-id="{e(v.id)}" data-type="{e(v.type)}" data-title="{e(v.title, quote=True)}"'
    style = _box(v)
    if v.role == "slicer":
        icon = _icon("date" if v.title == "Date Range" else "filter", 14)
        return (f'<div class="dp-card dp-slicer" {attrs} style="{style}"><span class="dp-slicer-icon">{icon}</span>'
                f'<span class="dp-slicer-label">{e(v.title)}</span><div class="dp-chart" data-chart-area></div></div>')
    if v.role == "kpi":
        icon = _icon(_kpi_icon(v.title))
        extra = ""
        if arch == "dark_neon":
            grad, solid = _GRADIENT_KPIS[index % len(_GRADIENT_KPIS)]
            style += f";background-color:{solid};background-image:{grad}"
        elif arch == "glass_light":
            tint, ink = _PASTEL_CHIPS[index % len(_PASTEL_CHIPS)]
            extra = f' style="background:{tint};color:{ink}"'
        badge = (f'<span class="dp-kpi-ring"><span class="dp-kpi-ring-in">{icon}</span></span>' if arch == "gradient_corporate"
                 else f'<span class="dp-kpi-icon"{extra}>{icon}</span>')
        return (f'<div class="dp-card dp-kpi" {attrs} data-value-color="{value_color}" style="{style}">'
                f'{badge}<p class="dp-title">{e(v.title)}</p><div class="dp-chart" data-chart-area></div></div>')
    if v.role == "insights":
        items = "".join(f"<li>{e(t)}</li>" for t in v.text[:4]) or "<li>Pin insights in Step 6 to show them here.</li>"
        return (f'<div class="dp-card dp-insights" {attrs} style="{style}"><div class="dp-visual-header">'
                f'<span class="dp-insights-icon">{_icon("spark", 15)}</span><p class="dp-title">{e(v.title)}</p></div><ul>{items}</ul></div>')
    return (f'<div class="dp-card dp-visual" {attrs} style="{style}"><div class="dp-visual-header"><span class="dp-mark"></span>'
            f'<p class="dp-title">{e(v.title)}</p></div><div class="dp-chart" data-chart-area></div></div>')


def _panel(kind: str, b: Box) -> str:
    return f'<div class="dp-panel dp-panel-{kind}" style="left:{b.x}px;top:{b.y}px;width:{b.w}px;height:{b.h}px"></div>'


def _rail_width(visuals: list[PlanVisual]) -> int:
    """Width of a left rail that holds no cards (the PBIP builder puts the page buttons there)."""
    xs = [v.box.x for v in visuals if v.role in ("kpi", "chart", "insights")]
    return min(xs) - MARGIN if xs and min(xs) >= 200 else 0


def _nav_track(total_pages: int, rail_w: int) -> str:
    """The track the Power BI page buttons sit on (they are drawn by Power BI, so no labels here)."""
    slots = nav_slots(total_pages, rail_w)
    if not slots:
        return ""
    if rail_w:
        return "".join(f'<div class="dp-nav-slot" data-nav-track style="left:{s.x}px;top:{s.y}px;width:{s.w}px;height:{s.h}px"></div>' for s in slots)
    x, y = slots[0].x - 4, slots[0].y - 4
    w, h = slots[-1].x + slots[-1].w + 4 - x, slots[0].h + 8
    return f'<div class="dp-nav-track" data-nav-track style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"></div>'


def _decor(arch: str) -> str:
    """Decorative shapes behind the cards (no text)."""
    if arch == "glass_light":
        return ('<div class="dp-blob" style="left:-120px;top:-140px;width:520px;height:420px;background:radial-gradient(circle, rgba(244,114,182,0.34), transparent 65%)"></div>'
                '<div class="dp-blob" style="left:760px;top:-180px;width:640px;height:520px;background:radial-gradient(circle, rgba(167,139,250,0.34), transparent 65%)"></div>'
                '<div class="dp-blob" style="left:380px;top:380px;width:700px;height:520px;background:radial-gradient(circle, rgba(125,211,252,0.32), transparent 65%)"></div>')
    if arch == "command_center":
        return '<div class="dp-topline"></div>'
    return ""


_ARCH_CSS = {
    "dark_neon": """
  .dp-kpi { border: none; box-shadow: 0 12px 28px rgba(2, 6, 23, 0.45); }
  .dp-kpi::after { content: ''; position: absolute; right: -34px; top: -38px; width: 120px; height: 120px; border-radius: 50%;
    background: rgba(255, 255, 255, 0.14); }
  .dp-kpi::before { content: ''; position: absolute; right: 18px; bottom: -46px; width: 90px; height: 90px; border-radius: 50%;
    background: rgba(255, 255, 255, 0.08); }
  .dp-kpi-icon { background: rgba(255, 255, 255, 0.22); color: #FFFFFF; }
  .dp-mark { background: linear-gradient(180deg, #A78BFA, #22D3EE); }
  .dp-panel-rail::after { content: ''; position: absolute; right: -1px; top: 18%; height: 64%; width: 2px;
    background: linear-gradient(180deg, transparent, rgba(167, 139, 250, 0.6), transparent); }
""",
    "glass_light": """
  .dp-kpi::after { content: ''; position: absolute; left: 16px; bottom: 0; width: 44px; height: 3px; border-radius: 3px 3px 0 0;
    background: linear-gradient(90deg, #7C3AED, #DB2777); }
  .dp-mark { background: linear-gradient(180deg, #7C3AED, #DB2777); }
  .dp-panel-band { background: rgba(255, 255, 255, 0.55); border-bottom: 1px solid rgba(255, 255, 255, 0.9);
    backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px); box-shadow: 0 6px 20px rgba(99, 102, 241, 0.06); }
""",
    "gradient_corporate": """
  .dp-kpi { display: grid; grid-template-columns: 42px 1fr; grid-template-rows: auto 1fr; column-gap: 10px; align-items: start; padding: 12px; }
  .dp-kpi .dp-kpi-ring { grid-row: 1 / span 2; align-self: center; }
  .dp-kpi > .dp-title { grid-column: 2; margin: 0 0 2px; white-space: normal; display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; line-height: 1.25; }
  .dp-kpi .dp-chart { grid-column: 2; height: 100%; }
  .dp-kpi-ring { position: relative; width: 42px; height: 42px; border-radius: 50%;
    background: conic-gradient(from 200deg, #38BDF8, #818CF8, #34D399, #38BDF8); }
  .dp-kpi-ring::before { content: ''; position: absolute; inset: 3.5px; border-radius: 50%; background: #111A2E; }
  .dp-kpi-ring-in { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #7DD3FC; }
  .dp-mark { background: linear-gradient(180deg, #38BDF8, #818CF8); }
  .dp-slicer { display: grid; grid-template-columns: 14px 1fr; grid-template-rows: auto 1fr; column-gap: 6px; row-gap: 3px;
    align-items: center; border-radius: 12px; padding: 7px 10px 6px 12px; }
  .dp-slicer .dp-chart { grid-column: 1 / span 2; height: 100%; }
  .dp-panel-hero_band { background: linear-gradient(135deg, rgba(56, 189, 248, 0.10), rgba(129, 140, 248, 0.07));
    border: 1px solid rgba(56, 189, 248, 0.14); border-radius: 18px; }
""",
    "command_center": """
  .dp-card::before { content: ''; position: absolute; left: 0; right: 0; top: 0; height: 2px;
    background: linear-gradient(90deg, #E23744, rgba(226, 55, 68, 0) 70%); }
  .dp-kpi { border-left: 3px solid #E23744; }
  .dp-kpi::before { display: none; }
  .dp-kpi .dp-title { text-transform: uppercase; letter-spacing: 0.08em; font-size: 10px; }
  .dp-kpi-icon { background: rgba(226, 55, 68, 0.14); color: #FF5A65; }
  .dp-visual .dp-title, .dp-insights .dp-title { text-transform: uppercase; letter-spacing: 0.06em; font-size: 11.5px; }
  .dp-mark { background: #E23744; border-radius: 2px; width: 8px; height: 8px; }
  .dp-panel-band { background: linear-gradient(180deg, rgba(226, 55, 68, 0.06), rgba(226, 55, 68, 0.01));
    border-top: 1px solid rgba(226, 55, 68, 0.22); border-bottom: 1px solid rgba(226, 55, 68, 0.22); }
  .dp-topline { position: absolute; left: 0; top: 0; width: 1280px; height: 3px; background: linear-gradient(90deg, #E23744, #FF7A59 40%, transparent 85%); }
""",
}


def template_html(plan: DashboardPlan, context: BusinessContext, archetype: Archetype | None = None,
                  theme: dict[str, str] | None = None, fonts: tuple[str, str, str] | None = None,
                  arrangement: Arrangement | None = None, page_label: str = "") -> str:
    """Deterministic contract-compliant design (also the baseline the AI restyles). `arrangement` places
    the page's visuals (core.design_layouts; default: the plan's neutral grid)."""
    arch = ARCHETYPE_MAP.get(archetype or "dark_neon", "dark_neon")
    t = {**_theme(arch, context.palette), **(theme or {})}
    heading, body, link = fonts or _fonts(context.font_stack)
    e = htmllib.escape
    font_link = f'<link rel="stylesheet" href="{link}">' if link else ""
    visuals = arrangement.visuals if arrangement else plan.visuals
    hb = arrangement.header if arrangement else Box(x=16, y=14, w=480, h=46)
    panels = "".join(_panel(k, b) for k, b in (arrangement.panels if arrangement else []))
    counts: dict[str, int] = {}
    cards = []
    for v in visuals:
        cards.append(_container(v, arch, counts.get(v.role, 0), t["kpi_value"]))
        counts[v.role] = counts.get(v.role, 0) + 1
    containers = "\n    ".join(cards)
    nav = _nav_track(plan.total_pages, _rail_width(visuals))
    # File-style names ("Credit_Card_Fraud") read and wrap better with spaces in the header.
    title = plan.title.replace("_", " ")
    brand = e((context.company_name or plan.title).replace("_", " "))
    narrow = hb.w < 300
    fit = int((hb.w - 56) / (0.56 * max(len(title), 1)))
    head_size = 16 if narrow else max(15, min(21, fit))
    clamp = 2 if narrow or fit < 15 else 1
    chip = f'<span class="dp-chip">{e(page_label)}</span>' if page_label else ""
    sans = f"'{body}', 'Segoe UI', sans-serif"
    head = f"'{heading}', 'Segoe UI', sans-serif"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{e(plan.title)}</title>{font_link}
<style>
  html, body {{ margin: 0; padding: 0; background: {t['page']}; }}
  .dp-canvas {{ position: relative; width: {CANVAS_W}px; height: {CANVAS_H}px; overflow: hidden; background: {t['canvas']};
    font-family: {sans}; color: {t['title']}; }}
  .dp-blob {{ position: absolute; border-radius: 50%; filter: blur(30px); }}
  .dp-panel {{ position: absolute; box-sizing: border-box; }}
  .dp-panel-rail {{ background: {t['rail_bg']}; border-right: {t['rail_border']}; backdrop-filter: {t['blur']}; -webkit-backdrop-filter: {t['blur']}; }}
  .dp-panel-band {{ background: linear-gradient(90deg, {t['area']}, transparent 85%); border-bottom: {t['border']}; }}
  .dp-panel-hero_band {{ border-radius: 16px; }}
  .dp-nav-track, .dp-nav-slot {{ position: absolute; box-sizing: border-box; background: {t['nav_bg']}; border: {t['nav_border']}; }}
  .dp-nav-track {{ border-radius: 12px; }}
  .dp-nav-slot {{ border-radius: 10px; }}
  .dp-header {{ position: absolute; left: {hb.x}px; top: {hb.y}px; width: {hb.w}px; height: {hb.h}px; display: flex; align-items: center; gap: 12px; }}
  .dp-logo {{ flex: none; width: 36px; height: 36px; border-radius: 11px; background: {t['logo']}; color: {t['logo_ink']}; display: flex;
    align-items: center; justify-content: center; font: 700 16px {head}; box-shadow: 0 6px 16px {_hex_rgba(t['accent'], 0.35)}; }}
  .dp-head-text {{ min-width: 0; flex: 1; }}
  .dp-heading {{ font: 600 {head_size}px/1.12 {head}; letter-spacing: -0.015em; color: {t['title']}; display: -webkit-box;
    -webkit-line-clamp: {clamp}; -webkit-box-orient: vertical; overflow: hidden; word-break: break-word; }}
  .dp-sub {{ display: block; font: 400 11px/1.3 {sans}; color: {t['muted']}; margin-top: 3px; letter-spacing: 0.02em;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .dp-chip {{ display: inline-block; margin-left: 6px; padding: 1px 8px; border-radius: 999px; background: {_hex_rgba(t['accent'], 0.14)};
    color: {t['accent']}; font: 600 9.5px {sans}; letter-spacing: 0.06em; text-transform: uppercase; vertical-align: 1px; }}
  .dp-card {{ position: absolute; box-sizing: border-box; background: {t['card']}; border: {t['border']}; border-radius: {t['radius']};
    box-shadow: {t['shadow']}; backdrop-filter: {t['blur']}; -webkit-backdrop-filter: {t['blur']}; padding: 14px 16px;
    display: flex; flex-direction: column; overflow: hidden; }}
  .dp-title {{ margin: 0; font: 600 13px/1.25 {head}; color: {t['title']}; letter-spacing: -0.005em;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .dp-chart {{ flex: 1; border-radius: 10px; background: {t['area']}; font-family: 'Segoe UI', sans-serif; min-height: 0; }}
  .dp-icon {{ display: block; }}
  .dp-visual-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; min-width: 0; }}
  .dp-mark {{ flex: none; width: 4px; height: 14px; border-radius: 4px; background: {t['accent']}; }}
  .dp-kpi {{ padding: 12px 14px; }}
  .dp-kpi > .dp-title {{ font: 500 12px/1.2 {head}; color: {t['kpi_title']}; position: relative; z-index: 1; }}
  .dp-kpi .dp-chart {{ background: transparent; position: relative; z-index: 1; }}
  .dp-kpi-icon {{ position: absolute; right: 12px; top: 12px; width: 30px; height: 30px; border-radius: 9px; display: flex;
    align-items: center; justify-content: center; z-index: 1; }}
  .dp-kpi > .dp-title {{ margin-right: 40px; margin-bottom: 4px; }}
  .dp-slicer {{ flex-direction: row; align-items: center; gap: 6px; padding: 6px 6px 6px 12px; border-radius: 999px; background: {t['slicer_bg']}; }}
  .dp-slicer-icon {{ flex: none; color: {t['accent']}; display: flex; }}
  .dp-slicer-label {{ font: 500 11px {sans}; color: {t['muted']}; white-space: nowrap; }}
  .dp-slicer .dp-chart {{ height: 24px; flex: 1; background: transparent; }}
  .dp-insights {{ background: linear-gradient(160deg, {_hex_rgba(t['accent'], 0.10)}, transparent 55%), {t['card']}; }}
  .dp-insights-icon {{ flex: none; width: 26px; height: 26px; border-radius: 8px; display: flex; align-items: center; justify-content: center;
    background: {_hex_rgba(t['accent'], 0.16)}; color: {t['accent']}; }}
  .dp-insights ul {{ margin: 2px 0 0; padding-left: 16px; font: 400 12px/1.5 {sans}; color: {t['title']}; }}
  .dp-insights li {{ margin-bottom: 8px; }}
  .dp-insights li::marker {{ color: {t['accent']}; }}
{_ARCH_CSS[arch]}</style></head>
<body><div class="dp-canvas" data-canvas style="width:{CANVAS_W}px;height:{CANVAS_H}px">{_decor(arch)}{panels}{nav}
    <div class="dp-header"><div class="dp-logo" data-role="logo">{e(brand[:1].upper())}</div>
      <div class="dp-head-text"><div class="dp-heading">{e(title)}</div><span class="dp-sub">{brand} &bull; {e(plan.subtitle)}{chip}</span></div></div>
    {containers}
</div></body></html>
"""


# --- AI -----------------------------------------------------------------------------

class _AIHtml(BaseModel):
    html: str


def _prompt(plan: DashboardPlan, style: str, palette: dict, fonts: str, baseline: str, errors: list[str]) -> str:
    visuals = [{"id": v.id, "role": v.role, "type": v.type, "title": v.title,
                "box": {"left": v.box.x, "top": v.box.y, "width": v.box.w, "height": v.box.h}} for v in plan.visuals]
    feedback = ("\n\nYOUR PREVIOUS ATTEMPT FAILED THESE CHECKS; FIX ALL OF THEM:\n- " + "\n- ".join(errors[:20])) if errors else ""
    return (
        PROMPT.read_text(encoding="utf-8")
        .replace("{style}", style)
        .replace("{palette}", json.dumps(palette))
        .replace("{fonts}", fonts)
        .replace("{visuals}", json.dumps(visuals, ensure_ascii=False))
        .replace("{baseline}", baseline)
        + feedback
    )


def generate_styled(plan: DashboardPlan, variant_id: str, label: str, style: str, palette: dict, fonts: str, baseline: str,
                    llm: LLMProvider | None, prefer_browser: bool = True) -> tuple[DesignVariant, bool]:
    """AI restyle of `baseline` checked against the design contract: 2 retries with the validator's
    errors, then the baseline template. Returns (variant, ai_still_usable) — False after quota/key
    errors so callers stop asking. Shared by design methods B (presets) and C (reference style)."""
    if llm is None:
        _, m = check(baseline, plan, prefer_browser)
        return DesignVariant(id=variant_id, label=label, html=baseline, source="template", engine=m.engine,
                             note="No AI key: built-in template."), False
    errors: list[str] = []
    attempts = 0
    for attempt in range(1 + MAX_RETRIES):
        attempts = attempt + 1
        try:
            answer = llm.generate_text(_prompt(plan, style, palette, fonts, baseline, errors), json_schema=_AIHtml)
        except (LLMRateLimitError, LLMNotConfiguredError) as exc:
            note = f"AI unavailable ({str(exc).split(' (', 1)[0][:100]}); built-in template used."
            _, m = check(baseline, plan, prefer_browser)
            return DesignVariant(id=variant_id, label=label, html=baseline, source="template", attempts=attempts, engine=m.engine, note=note), False
        except (LLMError, Exception) as exc:  # bad JSON etc.: counts as a failed attempt
            errors = [f"The answer was not valid JSON with an 'html' field ({type(exc).__name__})."]
            continue
        html = answer.html.strip()
        if len(html) > MAX_HTML:
            errors = [f"HTML is {len(html)} characters; keep it under {MAX_HTML}."]
            continue
        errors, m = check(html, plan, prefer_browser)
        if not errors:
            return DesignVariant(id=variant_id, label=label, html=html, source="ai", attempts=attempts, engine=m.engine), True
        logger.info("AI design %s attempt %d failed %d checks", variant_id, attempts, len(errors))
    _, m = check(baseline, plan, prefer_browser)
    return DesignVariant(id=variant_id, label=label, html=baseline, source="template", attempts=attempts, errors=errors,
                         engine=m.engine, note=f"AI design failed the contract after {attempts} attempts; built-in template used."), True


def page_label(plan: DashboardPlan, page: int) -> str:
    return f"{plan.pages[page - 1]} · {page}/{len(plan.pages)}" if len(plan.pages) > 1 else ""


def combine(variant_id: str, label: str, parts: list[DesignVariant], layouts: list[str]) -> DesignVariant:
    """One variant from its per-page results (page 1 is `html`)."""
    notes = list(dict.fromkeys(p.note for p in parts if p.note))
    return DesignVariant(
        id=variant_id, label=label, html=parts[0].html, pages=[p.html for p in parts], layouts=layouts,
        source="ai" if all(p.source == "ai" for p in parts) else "template", attempts=sum(p.attempts for p in parts),
        errors=[e for p in parts for e in p.errors][:20], valid=all(p.valid for p in parts), engine=parts[0].engine,
        note=" ".join(notes) or None,
    )


def generate_paged(plan: DashboardPlan, variant_id: str, label: str, layouts: list[str], page_html, style: str, palette: dict,
                   fonts: str, llm: LLMProvider | None, prefer_browser: bool = True) -> tuple[DesignVariant, bool]:
    """Every page of one variant: page_html(page_plan, arrangement, page_label) gives each page's baseline,
    which the AI may restyle (generate_styled). Shared by Options B and C."""
    parts, ai = [], llm
    for page, layout in enumerate(layouts, 1):
        sub = page_plan(plan, page)
        arr = arrange(sub, layout)
        placed = arr.plan(sub)
        part, usable = generate_styled(placed, variant_id, label, style, palette, fonts, page_html(placed, arr, page_label(plan, page)),
                                       ai, prefer_browser)
        parts.append(part)
        if not usable:
            ai = None
    return combine(variant_id, label, parts, layouts), ai is not None


def variant_layouts(plan: DashboardPlan, index: int) -> list[str]:
    """Layout per page for the index-th variant: each variant gets its dedicated signature layout."""
    layout_name = VARIANTS[index % len(VARIANTS)][3]
    return [layout_name for _ in range(len(plan.pages))]


def generate_variant(plan: DashboardPlan, context: BusinessContext, archetype: Archetype, llm: LLMProvider | None,
                     prefer_browser: bool = True, layouts: list[str] | None = None) -> tuple[DesignVariant, bool]:
    """One Option B preset variant: the archetype's style in its own layout(s)."""
    arch = ARCHETYPE_MAP.get(archetype, "dark_neon")
    index = next((i for i, v in enumerate(VARIANTS) if v[0] == arch), 0)
    label, description, default_layout = VARIANTS[index][1], VARIANTS[index][2], VARIANTS[index][3]
    layouts = layouts or [default_layout for _ in range(len(plan.pages))]
    full = f"{label} · {LAYOUTS[layouts[0]][0]}"
    style = f"{label}: {description} Layout: {LAYOUTS[layouts[0]][0]} — {LAYOUTS[layouts[0]][1]}"
    return generate_paged(plan, arch, full, layouts,
                          lambda placed, arr, chip: template_html(placed, context, arch, arrangement=arr, page_label=chip),
                          style, context.palette.model_dump(), context.font_stack, llm, prefer_browser)


def generate_variants(plan: DashboardPlan, context: BusinessContext, llm: LLMProvider | None, prefer_browser: bool = True) -> list[DesignVariant]:
    out = []
    ai = llm
    for arch_id, _, _, _ in VARIANTS:
        variant, usable = generate_variant(plan, context, arch_id, ai, prefer_browser)
        if ai is None and llm is not None:
            variant.note = "AI skipped after an earlier quota/key error; built-in template used."
        if not usable:
            ai = None  # quota/key problems: do not burn more requests on the next variants
        out.append(variant)
    return out

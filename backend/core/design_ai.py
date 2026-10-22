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
from core.design_layouts import LAYOUTS, Arrangement, arrange, suggest
from core.planner import CANVAS_H, CANVAS_W, Box, DashboardPlan, PlanVisual, page_plan
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
    ("dark_neon", "Dark Neon", "Deep navy canvas with purple/teal neon glow, left navigation rail, rich KPI cards with vs PY deltas and sparklines.", "dark_neon"),
    ("glass_light", "Glassmorphism Light", "Frosted lavender-blue glass cards, top navigation tabs, CY vs PY indicators, and chart subtitle insights.", "glass_light"),
    ("gradient_corporate", "Gradient Corporate", "Executive layout with left rail slicers, vibrant top gradient hero KPI band, donut breakdown, and ranked tables.", "gradient_corporate"),
    ("command_center", "Command Center Dark", "Obsidian telemetry dashboard, top status page navigator, dense KPI tiles with mini progress bars, and dedicated AI insights column.", "command_center"),
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

def _fonts(font_stack: str) -> tuple[str, str, str]:
    """(heading font, body font, Google Fonts link or '')."""
    if font_stack.startswith("Outfit"):
        return "Outfit", "Inter", "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=Inter:wght@400;500;600&display=swap"
    if font_stack == "Inter":
        return "Inter", "Inter", "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap"
    if font_stack.startswith("Georgia"):
        return "Georgia", "Segoe UI", ""
    return "Segoe UI", "Segoe UI", ""


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _theme(archetype: str, p: BrandPalette) -> dict[str, str]:
    arch = ARCHETYPE_MAP.get(archetype, archetype)
    if arch == "dark_neon":
        return {
            "page": "#070913",
            "canvas": f"radial-gradient(ellipse 70% 60% at 85% 15%, {_hex_rgba(p.accent or '#00F2FE', 0.14)}, transparent 60%), radial-gradient(ellipse 60% 50% at 15% 85%, rgba(157, 78, 221, 0.16), transparent 60%), #0B0F19",
            "card": "rgba(16, 23, 41, 0.82)",
            "border": f"1px solid {_hex_rgba(p.accent or '#00F2FE', 0.28)}",
            "radius": "14px",
            "shadow": f"0 4px 24px rgba(0,0,0,0.55), 0 0 14px {_hex_rgba(p.accent or '#00F2FE', 0.12)}",
            "title": "#F3F4F6", "muted": "#8E9BB0",
            "area": "rgba(0, 242, 254, 0.04)", "accent": p.accent or "#00F2FE", "secondary": "#9D4EDD",
            "kpi_bar": f"linear-gradient(90deg, {p.accent or '#00F2FE'}, #9D4EDD)", "blur": "none",
            "rail_bg": "#0A0E1A", "rail_border": f"1px solid {_hex_rgba(p.accent or '#00F2FE', 0.22)}",
        }
    if arch == "glass_light":
        return {
            "page": "#EAEBF5",
            "canvas": "linear-gradient(135deg, #F0F4FD 0%, #E5EDFF 40%, #EDE9FE 100%)",
            "card": "rgba(255, 255, 255, 0.68)",
            "border": "1px solid rgba(255, 255, 255, 0.85)",
            "radius": "18px",
            "shadow": "0 10px 30px rgba(67, 97, 238, 0.08), 0 2px 6px rgba(0, 0, 0, 0.04)",
            "title": "#1E293B", "muted": "#64748B",
            "area": "rgba(255, 255, 255, 0.40)", "accent": p.accent or "#4361EE", "secondary": "#3B82F6",
            "kpi_bar": p.accent or "#4361EE", "blur": "blur(16px)",
            "rail_bg": "rgba(255,255,255,0.5)", "rail_border": "1px solid rgba(255,255,255,0.7)",
        }
    if arch == "gradient_corporate":
        return {
            "page": "#080D1A",
            "canvas": "linear-gradient(180deg, #0A1020 0%, #0F172A 100%)",
            "card": "rgba(30, 41, 59, 0.70)",
            "border": "1px solid rgba(255, 255, 255, 0.10)",
            "radius": "12px",
            "shadow": "0 8px 24px rgba(0, 0, 0, 0.35)",
            "title": "#F8FAFC", "muted": "#94A3B8",
            "area": "rgba(255, 255, 255, 0.03)", "accent": p.accent or "#38BDF8", "secondary": "#0284C7",
            "kpi_bar": f"linear-gradient(90deg, {p.accent or '#38BDF8'}, #0284C7)", "blur": "none",
            "hero_band": "linear-gradient(135deg, #1E3A8A 0%, #0284C7 60%, #06B6D4 100%)",
            "rail_bg": "#070C18", "rail_border": "1px solid rgba(255, 255, 255, 0.08)",
        }
    return {
        "page": "#05070B",
        "canvas": "#080B10",
        "card": "rgba(14, 18, 26, 0.95)",
        "border": "1px solid rgba(255, 59, 48, 0.25)",
        "radius": "8px",
        "shadow": "0 0 1px 1px rgba(255, 59, 48, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
        "title": "#E1E7EF", "muted": "#6C7A8E",
        "area": "rgba(255, 255, 255, 0.02)", "accent": "#FF3B30", "secondary": "#00E5FF",
        "kpi_bar": "#FF3B30", "blur": "none",
        "rail_bg": "#06080E", "rail_border": "1px solid rgba(255, 59, 48, 0.2)",
    }


def _box(v: PlanVisual) -> str:
    b = v.box
    return f"left:{b.x}px;top:{b.y}px;width:{b.w}px;height:{b.h}px"


def _container(v: PlanVisual, arch: str = "dark_neon") -> str:
    e = htmllib.escape
    attrs = f'data-visual-id="{e(v.id)}" data-type="{e(v.type)}" data-title="{e(v.title, quote=True)}" style="{_box(v)}"'
    if v.role == "slicer":
        return f'<div class="dp-card dp-slicer dp-slicer-{arch}" {attrs}><span class="dp-slicer-label">{e(v.title)}</span><div class="dp-chart" data-chart-area></div></div>'
    if v.role == "kpi":
        meta = ""
        if arch == "dark_neon":
            meta = ('<div class="dp-kpi-meta"><span class="dp-delta dp-pos">&#9650; +12.4% vs PY</span>'
                    '<svg class="dp-sparkline" viewBox="0 0 72 18" preserveAspectRatio="none"><path d="M0 14 Q 18 16, 36 8 T 72 3" fill="none" stroke="#00F2FE" stroke-width="2"/><path d="M0 14 Q 18 16, 36 8 T 72 3 L 72 18 L 0 18 Z" fill="rgba(0,242,254,0.18)"/></svg></div>')
        elif arch == "glass_light":
            meta = ('<div class="dp-kpi-meta"><span class="dp-delta dp-glass-delta">CY vs PY &#9650; 8.4%</span>'
                    '<svg class="dp-sparkline" viewBox="0 0 72 16" preserveAspectRatio="none"><path d="M0 12 Q 24 15, 48 6 T 72 2" fill="none" stroke="#4361EE" stroke-width="1.8"/></svg></div>')
        elif arch == "gradient_corporate":
            meta = '<div class="dp-kpi-meta"><span class="dp-delta dp-corp-pill">Ranked #1 &bull; +9.1%</span></div>'
        elif arch == "command_center":
            meta = ('<div class="dp-kpi-meta"><div class="dp-kpi-progress"><div class="dp-kpi-progress-bar" style="width: 78%;"></div></div>'
                    '<span class="dp-delta dp-telemetry-tag">ACTIVE 98.4%</span></div>')
        return f'<div class="dp-card dp-kpi dp-kpi-{arch}" {attrs}><p class="dp-title">{e(v.title)}</p>{meta}<div class="dp-chart" data-chart-area></div><span class="dp-kpi-bar"></span></div>'
    if v.role == "insights":
        if arch == "command_center":
            items = "".join(f'<li><span class="dp-num-badge">[{i+1}]</span> {e(t)}</li>' for i, t in enumerate(v.text[:4])) or '<li><span class="dp-num-badge">[1]</span> Pin insights in Step 6 to show them here.</li>'
        else:
            items = "".join(f"<li>{e(t)}</li>" for t in v.text[:3]) or "<li>Pin insights in Step 6 to show them here.</li>"
        return f'<div class="dp-card dp-insights dp-insights-{arch}" {attrs}><p class="dp-title">{e(v.title)}</p><ul>{items}</ul></div>'
    sub = ""
    if arch == "glass_light":
        sub = '<span class="dp-subtitle-insight">Insight: Key category trends &amp; distribution</span>'
    elif arch == "command_center":
        sub = '<span class="dp-subtitle-insight">TELEMETRY &bull; LIVE FEED</span>'
    return f'<div class="dp-card dp-visual dp-visual-{arch}" {attrs}><div class="dp-visual-header"><p class="dp-title">{e(v.title)}</p>{sub}</div><div class="dp-chart" data-chart-area></div></div>'


def _panel(kind: str, b: Box) -> str:
    return f'<div class="dp-panel dp-panel-{kind}" style="left:{b.x}px;top:{b.y}px;width:{b.w}px;height:{b.h}px"></div>'


def template_html(plan: DashboardPlan, context: BusinessContext, archetype: Archetype | None = None,
                  theme: dict[str, str] | None = None, fonts: tuple[str, str, str] | None = None,
                  arrangement: Arrangement | None = None, page_label: str = "") -> str:
    """Deterministic contract-compliant design (also the baseline the AI restyles). `arrangement` places
    the page's visuals (core.design_layouts; default: the plan's neutral grid)."""
    arch = ARCHETYPE_MAP.get(archetype or "dark_neon", "dark_neon")
    t = theme or _theme(arch, context.palette)
    heading, body, link = fonts or _fonts(context.font_stack)
    e = htmllib.escape
    font_link = f'<link rel="stylesheet" href="{link}">' if link else ""
    visuals = arrangement.visuals if arrangement else plan.visuals
    hb = arrangement.header if arrangement else Box(x=16, y=14, w=480, h=46)
    panels = "".join(_panel(k, b) for k, b in (arrangement.panels if arrangement else []))
    containers = "\n    ".join(_container(v, arch) for v in visuals)
    brand = e(context.company_name or plan.title)
    head_size = 20 if hb.w >= 400 else 17
    chip = f'<span class="dp-chip">{e(page_label)}</span>' if page_label else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{e(plan.title)}</title>{font_link}
<style>
  html, body {{ margin: 0; padding: 0; background: {t['page']}; }}
  .dp-canvas {{ position: relative; width: {CANVAS_W}px; height: {CANVAS_H}px; overflow: hidden; background: {t['canvas']};
    font-family: '{body}', 'DIN', 'Segoe UI', sans-serif; color: {t['title']}; }}
  .dp-header {{ position: absolute; left: {hb.x}px; top: {hb.y}px; width: {hb.w}px; height: {hb.h}px; display: flex; align-items: center; gap: 12px; }}
  .dp-panel {{ position: absolute; box-sizing: border-box; }}
  .dp-panel-rail {{ background: {t.get('rail_bg', t['card'])}; border-right: {t.get('rail_border', t['border'])}; backdrop-filter: {t['blur']}; -webkit-backdrop-filter: {t['blur']}; }}
  .dp-panel-band {{ background: linear-gradient(90deg, {t['area']}, transparent 85%); border-bottom: {t['border']}; }}
  .dp-panel-hero_band {{ background: {t.get('hero_band', 'linear-gradient(135deg, #1E3A8A 0%, #0284C7 60%, #06B6D4 100%)')}; border-radius: 14px; box-shadow: 0 10px 30px rgba(0,0,0,0.25); }}
  .dp-chip {{ display: inline-block; margin-left: 8px; padding: 2px 9px; border-radius: 999px; background: {t['area']}; border: {t['border']};
    font: 500 10px '{body}', 'DIN', 'Segoe UI', sans-serif; letter-spacing: 0.06em; text-transform: uppercase; color: {t['muted']}; vertical-align: middle; }}
  .dp-logo {{ width: 34px; height: 34px; border-radius: 10px; background: {t['accent']}; color: #111; display: flex; align-items: center;
    justify-content: center; font: 600 15px '{heading}', 'DIN', 'Segoe UI', sans-serif; }}
  .dp-heading {{ font: 500 {head_size}px/1.15 '{heading}', 'DIN', 'Segoe UI', sans-serif; letter-spacing: -0.01em; color: {t['title']}; }}
  .dp-sub {{ display: block; font: 400 11px '{body}', 'DIN', 'Segoe UI', sans-serif; color: {t['muted']}; margin-top: 3px; letter-spacing: 0.02em; }}
  .dp-card {{ position: absolute; box-sizing: border-box; background: {t['card']}; border: {t['border']}; border-radius: {t['radius']};
    box-shadow: {t['shadow']}; backdrop-filter: {t['blur']}; -webkit-backdrop-filter: {t['blur']}; padding: 12px 16px;
    display: flex; flex-direction: column; overflow: hidden; }}
  .dp-title {{ margin: 0 0 6px; font: 600 13px/1.25 '{heading}', 'DIN', 'Segoe UI', sans-serif; color: {t['title']}; letter-spacing: -0.005em; }}
  .dp-chart {{ flex: 1; border-radius: 10px; background: {t['area']}; font-family: 'Segoe UI', sans-serif; }}
  .dp-kpi {{ padding: 8px 12px; }}
  .dp-kpi .dp-title {{ margin: 0 0 2px; font: 600 11px/1.2 '{heading}', 'DIN', 'Segoe UI', sans-serif; color: {t['muted']}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .dp-kpi .dp-chart {{ background: transparent; min-height: 44px; }}
  .dp-kpi-bar {{ position: absolute; left: 12px; right: 12px; bottom: 6px; height: 3px; border-radius: 3px; background: {t['kpi_bar']}; opacity: 0.85; }}
  .dp-kpi-meta {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px; }}
  .dp-delta {{ font: 600 10px/1.2 '{body}', 'DIN', 'Segoe UI', sans-serif; padding: 2px 6px; border-radius: 4px; }}
  .dp-pos {{ color: #10B981; background: rgba(16, 185, 129, 0.12); }}
  .dp-glass-delta {{ color: #4361EE; background: rgba(67, 97, 238, 0.12); }}
  .dp-corp-pill {{ color: #38BDF8; background: rgba(56, 189, 248, 0.12); }}
  .dp-telemetry-tag {{ color: #00E5FF; background: rgba(0, 229, 255, 0.12); font-size: 9px; letter-spacing: 0.05em; }}
  .dp-sparkline {{ width: 72px; height: 18px; }}
  .dp-kpi-progress {{ width: 80px; height: 5px; background: rgba(255,255,255,0.12); border-radius: 3px; overflow: hidden; }}
  .dp-kpi-progress-bar {{ height: 100%; background: #FF3B30; border-radius: 3px; }}
  .dp-slicer {{ flex-direction: row; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px; }}
  .dp-slicer-label {{ font: 500 11px '{body}', 'DIN', 'Segoe UI', sans-serif; color: {t['muted']}; white-space: nowrap; }}
  .dp-slicer .dp-chart {{ height: 22px; flex: 1; }}
  .dp-visual-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }}
  .dp-subtitle-insight {{ font: 400 10px/1.2 '{body}', 'DIN', 'Segoe UI', sans-serif; color: {t['muted']}; letter-spacing: 0.02em; }}
  .dp-insights {{ border-left: 3px solid {t['accent']}; }}
  .dp-insights ul {{ margin: 0; padding-left: 16px; font: 400 12px/1.45 '{body}', 'DIN', 'Segoe UI', sans-serif; color: {t['title']}; }}
  .dp-insights li {{ margin-bottom: 6px; }}
  .dp-insights li::marker {{ color: {t['accent']}; }}
  .dp-num-badge {{ color: {t['accent']}; font-weight: 700; margin-right: 4px; }}
</style></head>
<body><div class="dp-canvas" data-canvas style="width:{CANVAS_W}px;height:{CANVAS_H}px">{panels}
    <div class="dp-header"><div class="dp-logo" data-role="logo">{e(brand[:1].upper())}</div>
      <div><span class="dp-heading">{e(plan.title)}</span><span class="dp-sub">{brand} &bull; {e(plan.subtitle)}{chip}</span></div></div>
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

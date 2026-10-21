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

Archetype = Literal["dark_futuristic", "light_elegant", "glassmorphism"]
VARIANTS: list[tuple[Archetype, str, str]] = [
    ("dark_futuristic", "Dark Futuristic", "Obsidian canvas, luminous accent edges and glows, telemetry feel, high contrast."),
    ("light_elegant", "Light Elegant", "Airy warm canvas, white cards, charcoal headings, refined editorial spacing, soft shadows."),
    ("glassmorphism", "Glassmorphism", "Soft gradient canvas, frosted translucent cards with blur, thin white borders, layered depth."),
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


def _theme(archetype: Archetype, p: BrandPalette) -> dict[str, str]:
    if archetype == "dark_futuristic":
        return {
            "page": "#0B0C0F", "canvas": "radial-gradient(ellipse 70% 60% at 100% 0%, " + _hex_rgba(p.accent, 0.10) + ", transparent 70%), #111215",
            "card": "rgba(255,255,255,0.045)", "border": "1px solid rgba(255,255,255,0.08)", "radius": "16px",
            "shadow": f"0 0 0 1px rgba(0,0,0,0.2), 0 12px 32px -12px {_hex_rgba(p.accent, 0.25)}",
            "title": "#F2F0F0", "muted": "#9A9DA6", "area": "rgba(255,255,255,0.03)", "accent": p.accent,
            "kpi_bar": f"linear-gradient(90deg, {p.accent}, {_hex_rgba(p.accent, 0)})", "blur": "none",
        }
    if archetype == "glassmorphism":
        return {
            "page": p.canvas, "canvas": f"linear-gradient(135deg, {p.canvas} 0%, {_hex_rgba(p.accent, 0.28)} 55%, {_hex_rgba(p.muted, 0.25)} 100%)",
            "card": "rgba(255,255,255,0.55)", "border": "1px solid rgba(255,255,255,0.7)", "radius": "24px",
            "shadow": "0 16px 40px -16px rgba(35,35,35,0.18)", "title": p.base, "muted": p.muted,
            "area": "rgba(255,255,255,0.35)", "accent": p.accent, "kpi_bar": p.accent, "blur": "blur(14px)",
        }
    return {
        "page": p.canvas, "canvas": f"radial-gradient(ellipse 60% 50% at 100% 100%, {_hex_rgba(p.accent, 0.16)}, transparent 75%), {p.canvas}",
        "card": "#FFFFFF", "border": "1px solid rgba(35,35,35,0.04)", "radius": "20px",
        "shadow": "0 12px 36px -8px rgba(35,35,35,0.07), 0 2px 8px -2px rgba(35,35,35,0.03)", "title": p.base,
        "muted": p.muted, "area": _hex_rgba(p.canvas, 0.6), "accent": p.accent, "kpi_bar": p.accent, "blur": "none",
    }


def _box(v: PlanVisual) -> str:
    b = v.box
    return f"left:{b.x}px;top:{b.y}px;width:{b.w}px;height:{b.h}px"


def _container(v: PlanVisual) -> str:
    e = htmllib.escape
    attrs = f'data-visual-id="{e(v.id)}" data-type="{e(v.type)}" data-title="{e(v.title, quote=True)}" style="{_box(v)}"'
    if v.role == "slicer":
        return f'<div class="dp-card dp-slicer" {attrs}><span class="dp-slicer-label">{e(v.title)}</span><div class="dp-chart" data-chart-area></div></div>'
    if v.role == "kpi":
        return f'<div class="dp-card dp-kpi" {attrs}><p class="dp-title">{e(v.title)}</p><div class="dp-chart" data-chart-area></div><span class="dp-kpi-bar"></span></div>'
    if v.role == "insights":
        items = "".join(f"<li>{e(t)}</li>" for t in v.text[:3]) or "<li>Pin insights in Step 6 to show them here.</li>"
        return f'<div class="dp-card dp-insights" {attrs}><p class="dp-title">{e(v.title)}</p><ul>{items}</ul></div>'
    return f'<div class="dp-card dp-visual" {attrs}><p class="dp-title">{e(v.title)}</p><div class="dp-chart" data-chart-area></div></div>'


def _panel(kind: str, b: Box) -> str:
    return f'<div class="dp-panel dp-panel-{kind}" style="left:{b.x}px;top:{b.y}px;width:{b.w}px;height:{b.h}px"></div>'


def template_html(plan: DashboardPlan, context: BusinessContext, archetype: Archetype | None = None,
                  theme: dict[str, str] | None = None, fonts: tuple[str, str, str] | None = None,
                  arrangement: Arrangement | None = None, page_label: str = "") -> str:
    """Deterministic contract-compliant design (also the baseline the AI restyles). `arrangement` places
    the page's visuals (core.design_layouts; default: the plan's neutral grid). Option C passes its own
    `theme` (same keys as _theme) and `fonts` built from a reference image's style profile."""
    t = theme or _theme(archetype or "light_elegant", context.palette)
    heading, body, link = fonts or _fonts(context.font_stack)
    e = htmllib.escape
    font_link = f'<link rel="stylesheet" href="{link}">' if link else ""
    visuals = arrangement.visuals if arrangement else plan.visuals
    hb = arrangement.header if arrangement else Box(x=24, y=14, w=640, h=46)
    panels = "".join(_panel(k, b) for k, b in (arrangement.panels if arrangement else []))
    containers = "\n    ".join(_container(v) for v in visuals)
    brand = e(context.company_name or plan.title)
    head_size = 22 if hb.w >= 420 else 19
    chip = f'<span class="dp-chip">{e(page_label)}</span>' if page_label else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{e(plan.title)}</title>{font_link}
<style>
  html, body {{ margin: 0; padding: 0; background: {t['page']}; }}
  .dp-canvas {{ position: relative; width: {CANVAS_W}px; height: {CANVAS_H}px; overflow: hidden; background: {t['canvas']};
    font-family: '{body}', 'Segoe UI', sans-serif; color: {t['title']}; }}
  .dp-header {{ position: absolute; left: {hb.x}px; top: {hb.y}px; width: {hb.w}px; height: {hb.h}px; display: flex; align-items: center; gap: 12px; }}
  .dp-panel {{ position: absolute; box-sizing: border-box; }}
  .dp-panel-rail {{ background: {t['card']}; border-right: {t['border']}; backdrop-filter: {t['blur']}; -webkit-backdrop-filter: {t['blur']}; }}
  .dp-panel-band {{ background: linear-gradient(90deg, {t['area']}, transparent 85%); border-bottom: {t['border']}; }}
  .dp-chip {{ display: inline-block; margin-left: 8px; padding: 2px 9px; border-radius: 999px; background: {t['area']}; border: {t['border']};
    font: 500 10px '{body}', 'Segoe UI', sans-serif; letter-spacing: 0.06em; text-transform: uppercase; color: {t['muted']}; vertical-align: middle; }}
  .dp-kpi-hero .dp-title {{ font-size: 15px; }}
  .dp-kpi-hero .dp-kpi-bar {{ height: 4px; }}
  .dp-logo {{ width: 34px; height: 34px; border-radius: 10px; background: {t['accent']}; color: #111; display: flex; align-items: center;
    justify-content: center; font: 600 15px '{heading}', 'Segoe UI', sans-serif; }}
  .dp-heading {{ font: 500 {head_size}px/1.15 '{heading}', 'Segoe UI', sans-serif; letter-spacing: -0.01em; color: {t['title']}; }}
  .dp-sub {{ display: block; font: 400 11px '{body}', 'Segoe UI', sans-serif; color: {t['muted']}; margin-top: 3px; letter-spacing: 0.02em; }}
  .dp-card {{ position: absolute; box-sizing: border-box; background: {t['card']}; border: {t['border']}; border-radius: {t['radius']};
    box-shadow: {t['shadow']}; backdrop-filter: {t['blur']}; -webkit-backdrop-filter: {t['blur']}; padding: 12px 16px;
    display: flex; flex-direction: column; overflow: hidden; }}
  .dp-title {{ margin: 0 0 8px; font: 600 13px/1.25 '{heading}', 'Segoe UI', sans-serif; color: {t['title']}; letter-spacing: -0.005em; }}
  .dp-chart {{ flex: 1; border-radius: 10px; background: {t['area']}; font-family: 'Segoe UI', sans-serif; }}
  .dp-kpi {{ padding: 8px 12px; }}
  .dp-kpi .dp-title {{ margin: 0 0 2px; font: 600 11px/1.2 '{heading}', 'Segoe UI', sans-serif; color: {t['muted']}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .dp-kpi .dp-chart {{ background: transparent; min-height: 48px; }}
  .dp-kpi-bar {{ position: absolute; left: 12px; right: 12px; bottom: 6px; height: 3px; border-radius: 3px; background: {t['kpi_bar']}; opacity: 0.85; }}
  .dp-slicer {{ flex-direction: row; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px; }}
  .dp-slicer-label {{ font: 500 11px '{body}', 'Segoe UI', sans-serif; color: {t['muted']}; white-space: nowrap; }}
  .dp-slicer .dp-chart {{ height: 22px; flex: 1; }}
  .dp-insights {{ border-left: 3px solid {t['accent']}; }}
  .dp-insights ul {{ margin: 0; padding-left: 16px; font: 400 12px/1.45 '{body}', 'Segoe UI', sans-serif; color: {t['title']}; }}
  .dp-insights li {{ margin-bottom: 6px; }}
  .dp-insights li::marker {{ color: {t['accent']}; }}
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
    """Layout per page for the index-th variant: each variant gets a different best-fitting layout."""
    return [suggest(page_plan(plan, p))[index % len(LAYOUTS)] for p in range(1, len(plan.pages) + 1)]


def generate_variant(plan: DashboardPlan, context: BusinessContext, archetype: Archetype, llm: LLMProvider | None,
                     prefer_browser: bool = True, layouts: list[str] | None = None) -> tuple[DesignVariant, bool]:
    """One Option B preset variant: the archetype's style in its own layout(s)."""
    index = next(i for i, (a, _, _) in enumerate(VARIANTS) if a == archetype)
    label, description = VARIANTS[index][1], VARIANTS[index][2]
    layouts = layouts or variant_layouts(plan, index)
    full = f"{label} · {LAYOUTS[layouts[0]][0]}"
    style = f"{label}: {description} Layout: {LAYOUTS[layouts[0]][0]} — {LAYOUTS[layouts[0]][1]}"
    return generate_paged(plan, archetype, full, layouts,
                          lambda placed, arr, chip: template_html(placed, context, archetype, arrangement=arr, page_label=chip),
                          style, context.palette.model_dump(), context.font_stack, llm, prefer_browser)


def generate_variants(plan: DashboardPlan, context: BusinessContext, llm: LLMProvider | None, prefer_browser: bool = True) -> list[DesignVariant]:
    out = []
    ai = llm
    for archetype, _, _ in VARIANTS:
        variant, usable = generate_variant(plan, context, archetype, ai, prefer_browser)
        if ai is None and llm is not None:
            variant.note = "AI skipped after an earlier quota/key error; built-in template used."
        if not usable:
            ai = None  # quota/key problems: do not burn more requests on the next variants
        out.append(variant)
    return out

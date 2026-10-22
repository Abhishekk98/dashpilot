"""Design Import (spec Module 10A): one pipeline for every design method.

The 1280x720 HTML (Option B's selected design, or an uploaded Stitch/hand-made export) is rendered in
the installed Edge/Chrome through `design_contract.render_page`:

1. `extract` finds the visual containers (data-visual-id containers in contract HTML; otherwise the
   nearest card-like ancestor of each short text, i.e. a titled card) with position, colors, radius
   and fonts, plus the page palette.
2. `match` maps planned visuals to boxes: exact id, then fuzzy title, then (optionally) the LLM.
3. `validate_mapping` applies the design-validator rules to the mapping (one box per visual, no box
   used twice, inside the canvas, no overlaps).
4. `background_png` re-renders the page with the mapped cards' contents hidden (titles, card shapes,
   header and logo stay) and screenshots the canvas.
5. `build_theme` turns the palette into a Power BI report theme (numbers in Segoe UI).
"""

from __future__ import annotations

import colorsys
import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from core.context import BrandPalette
from core.design_contract import CANVAS_H, CANVAS_W, overlap, render_page
from core.planner import DashboardPlan
from llm import LLMProvider

logger = logging.getLogger(__name__)
PROMPT = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "design_mapping.md"
TITLE_THRESHOLD = 0.72
MIN_W, MIN_H = 40, 30


# --- models ---------------------------------------------------------------------------------

class ValueStyle(BaseModel):
    """Where and how a card shows its main number (offset from the card's top-left, in px)."""

    dx: int
    dy: int
    w: int
    h: int
    size: float  # px
    weight: int = 400
    color: str | None = None
    font: str = "Segoe UI"
    align: Literal["left", "center", "right"] = "center"


class DetectedBox(BaseModel):
    id: str  # box_01... in reading order
    x: int
    y: int
    w: int
    h: int
    title: str
    text: str = ""  # first part of all text in the box (used for matching)
    visual_id: str | None = None  # data-visual-id when the HTML follows the design contract
    type: str | None = None
    background: str | None = None  # hex
    border: str | None = None
    radius: int = 0
    title_font: str = ""
    title_color: str | None = None
    # Content area inside the card as [left, top, right, bottom] insets in px (None = whole card).
    inset: list[int] | None = None
    value: ValueStyle | None = None  # the card's main number (KPI cards), as the design draws it


class MappingItem(BaseModel):
    visual_id: str
    box_id: str | None = None  # None = not placed yet (or placed by hand without a detected box)
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    method: Literal["id", "title", "ai", "manual", "none"] = "none"
    score: float = 0.0
    # True when the card in the design does not show this visual's title (slot reassigned, AI match,
    # or placed by hand): the background then hides the card's title and Power BI draws its own.
    pbi_title: bool = False

    @property
    def placed(self) -> bool:
        return self.w > 0 and self.h > 0


class ThemeColor(BaseModel):
    hex: str
    role: Literal["canvas", "card", "text", "muted", "accent", "other"]
    weight: float = 0.0


class Extraction(BaseModel):
    canvas_w: float
    canvas_h: float
    boxes: list[DetectedBox]
    palette: list[ThemeColor]
    heading_font: str
    body_font: str
    skipped: int = 0  # containers outside the 1280x720 canvas
    # The design's own size; a page that is not 1280x720 is scaled into the canvas (`scale` < 1).
    source_w: int = CANVAS_W
    source_h: int = CANVAS_H
    scale: float = 1.0
    # How the design draws charts and numbers (placeholder charts in Stitch exports) -> Power BI theme.
    chart_colors: list[str] = []
    label_color: str | None = None
    value_color: str | None = None
    value_font: str | None = None


# --- colors -----------------------------------------------------------------------------------

_RGB = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?\s*\)")


def css_hex(value: str | None) -> str | None:
    """'rgb(…)' / 'rgba(…)' / '#abc' -> '#AABBCC' (None for transparent or unknown)."""
    if not value:
        return None
    value = value.strip()
    if value.startswith("#") and len(value) in (4, 7):
        v = value[1:]
        v = "".join(c * 2 for c in v) if len(v) == 3 else v
        return "#" + v.upper()
    m = _RGB.search(value)
    if not m:
        return None
    a = m.group(4)
    alpha = float(a[:-1]) / 100 if a and a.endswith("%") else float(a) if a else 1.0
    if alpha < 0.35:
        return None
    return "#{:02X}{:02X}{:02X}".format(*(min(255, round(float(m.group(i)))) for i in (1, 2, 3)))


def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def luminance(hex_color: str) -> float:
    def ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hex_color)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _saturation(hex_color: str) -> float:
    return colorsys.rgb_to_hls(*_rgb(hex_color))[2]


def _distance(a: str, b: str) -> float:
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b))) ** 0.5


def _mix(a: str, b: str, t: float) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(round((x * (1 - t) + y * t) * 255) for x, y in zip(_rgb(a), _rgb(b))))


def _rotate(hex_color: str, degrees: float, lightness: float | None = None) -> str:
    h, l, s = colorsys.rgb_to_hls(*_rgb(hex_color))
    r, g, b = colorsys.hls_to_rgb((h + degrees / 360) % 1, lightness if lightness is not None else l, max(s, 0.45))
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def _merge(weights: dict[str, float]) -> list[tuple[str, float]]:
    """Merge near-identical colors (anti-aliasing, alpha blends), heaviest first."""
    out: list[list] = []
    for hex_color, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        for item in out:
            if _distance(item[0], hex_color) < 0.06:
                item[1] += w
                break
        else:
            out.append([hex_color, w])
    return [(c, w) for c, w in out]


# --- extraction (browser) -----------------------------------------------------------------------

# Pages without a [data-canvas] (Stitch exports): find the dashboard — an element of about 1280x720,
# else the whole page — and, when it is not 1280x720, scale it into the canvas (centered, letterboxed
# with the page background). The <html> element then is the 1280x720 canvas.
_FIT = r"""
() => {
  if (document.querySelector('[data-canvas]')) return {scaled: false, scale: 1, w: 1280, h: 720};
  const de = document.documentElement, body = document.body;
  window.scrollTo(0, 0);
  const W = Math.max(de.scrollWidth, body.scrollWidth, 1), H = Math.max(de.scrollHeight, body.scrollHeight, 1);
  let target = null;
  for (const el of body.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (Math.abs(r.width - 1280) <= 8 && Math.abs(r.height - 720) <= 8) { target = r; break; }
  }
  const t = target ? {x: target.left, y: target.top, w: target.width, h: target.height} : {x: 0, y: 0, w: W, h: H};
  const s = Math.min(1280 / t.w, 720 / t.h, 1);
  const dx = (1280 - t.w * s) / 2 - t.x * s, dy = (720 - t.h * s) / 2 - t.y * s;
  if (Math.abs(s - 1) > 0.002 || Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
    body.style.transformOrigin = '0 0';
    body.style.transform = `translate(${dx}px, ${dy}px) scale(${s})`;
    body.style.width = W + 'px';
  }
  de.style.width = '1280px'; de.style.height = '720px'; de.style.overflow = 'hidden';
  de.setAttribute('data-canvas', '');
  return {scaled: Math.abs(s - 1) > 0.002, scale: s, w: Math.round(t.w), h: Math.round(t.h)};
}
"""

_DETECT = r"""
(mark) => {
  const canvas = document.querySelector('[data-canvas]') || document.body;
  const o = canvas.getBoundingClientRect();
  const W = 1280, H = 720;
  const alpha = c => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return 0; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(parseFloat); return p.length > 3 ? p[3] : 1; };
  const shown = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.05; };
  // Icon fonts (Material Symbols, Font Awesome…) render ligature words like "check_circle": not text.
  const icon = el => /material|symbols|icons?\b|awesome|glyph/i.test(getComputedStyle(el).fontFamily + ' ' + (el.getAttribute('class') || ''));
  const own = el => {
    const t = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').replace(/\s+/g, ' ').trim();
    return t && /[\p{L}\p{N}]/u.test(t) && !icon(el) ? t : '';
  };
  const rel = el => { const r = el.getBoundingClientRect(); return {x: r.left - o.left, y: r.top - o.top, w: r.width, h: r.height}; };
  const cardLike = el => {
    if (el === canvas || el === document.body || el === document.documentElement) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 60 || r.height < 28) return false;
    if (r.width > W * 0.97 && r.height > H * 0.5) return false;
    const cs = getComputedStyle(el);
    const border = parseFloat(cs.borderTopWidth) > 0 && parseFloat(cs.borderLeftWidth) > 0 && alpha(cs.borderTopColor) > 0.04;
    return alpha(cs.backgroundColor) > 0.04 || cs.backgroundImage !== 'none' || border || cs.boxShadow !== 'none';
  };

  let found = [];
  const contract = [...canvas.querySelectorAll('[data-visual-id]')];
  if (contract.length) {
    for (const el of contract) {
      const want = (el.getAttribute('data-title') || '').trim().toLowerCase();
      const texts = [el, ...el.querySelectorAll('*')].filter(e => !e.closest('[data-chart-area]') && own(e));
      found.push({el, titleEl: texts.find(e => own(e).toLowerCase() === want) || texts[0] || null});
    }
  } else {
    const seen = new Map();
    for (const t of canvas.querySelectorAll('*')) {
      if (t.closest('svg') || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(t.tagName)) continue;
      const txt = own(t);
      if (!txt || txt.length > 90 || !shown(t)) continue;
      let a = t;
      while (a && a !== canvas && !cardLike(a)) a = a.parentElement;
      if (!a || a === canvas || seen.has(a)) continue;
      seen.set(a, t);
    }
    found = [...seen].map(([el, titleEl]) => ({el, titleEl}));
    // A panel filling most of a card (e.g. a fake chart's plot area) belongs to that card.
    const area = e => { const r = e.getBoundingClientRect(); return r.width * r.height; };
    found = found.filter(b => !found.some(a => a !== b && a.el.contains(b.el) && area(b.el) >= 0.25 * area(a.el)));
  }

  // Where the Power BI visual goes inside the card: the chart area when the HTML marks one,
  // otherwise everything the card draws outside its title row (fake charts, KPI values, slicer
  // text), so the visual covers all dummy content and static labels beside the title stay.
  const draws = d => {
    const tag = d.tagName.toLowerCase(), cs = getComputedStyle(d);
    return own(d) || ['svg', 'canvas', 'img'].includes(tag) || alpha(cs.backgroundColor) > 0.04 || cs.backgroundImage !== 'none'
      || (parseFloat(cs.borderTopWidth) > 0 && alpha(cs.borderTopColor) > 0.04) || (d instanceof SVGElement && tag !== 'svg');
  };
  const contentArea = (el, titleEl) => {
    const areaEl = el.querySelector('[data-chart-area]');
    if (areaEl) return rel(areaEl);
    if (!titleEl) return null;
    const b = rel(el), t = rel(titleEl);
    if (b.h <= 64 && t.x + t.w < b.x + b.w * 0.7) {  // pill (slicer): content right of the label
      const a = {x: t.x + t.w + 6, y: b.y + 3, w: b.x + b.w - (t.x + t.w + 6) - 4, h: b.h - 6};
      return a.w >= 20 && a.h >= 16 ? a : null;
    }
    const below = t.y + t.h / 2 < b.y + b.h / 2;  // title in the top half: content under it
    const pad = 6;
    let a = below ? {x1: b.x + pad, y1: t.y + t.h + 4, x2: b.x + b.w - pad, y2: b.y + b.h - pad}
                  : {x1: b.x + pad, y1: b.y + pad, x2: b.x + b.w - pad, y2: t.y - 4};
    for (const d of el.querySelectorAll('*')) {
      if (d === titleEl || d.contains(titleEl) || titleEl.contains(d) || !shown(d) || !draws(d)) continue;
      const r = rel(d);
      if (r.w < 1 || r.h < 1) continue;
      const cy = r.y + r.h / 2;
      if (cy >= t.y - 2 && cy <= t.y + t.h + 2) continue;  // same row as the title: a static label
      if (below ? cy < t.y : cy > t.y + t.h) continue;
      a = {x1: Math.min(a.x1, r.x), y1: below ? a.y1 : Math.min(a.y1, r.y), x2: Math.max(a.x2, r.x + r.w), y2: below ? Math.max(a.y2, r.y + r.h) : a.y2};
    }
    a = {x: Math.max(b.x, a.x1), y: Math.max(b.y, a.y1), w: Math.min(b.x + b.w, a.x2) - Math.max(b.x, a.x1), h: Math.min(b.y + b.h, a.y2) - Math.max(b.y, a.y1)};
    return a.w >= 20 && a.h >= 16 ? a : null;
  };

  // Chart look of the design (Stitch draws placeholder charts): series colors, label and value styles.
  const chart = {colors: {}, labels: {}, values: []};
  const collect = (el, area) => {
    if (!area) return;
    for (const d of el.querySelectorAll('*')) {
      if (!shown(d)) continue;
      const r = rel(d);
      const cx = r.x + r.w / 2, cy = r.y + r.h / 2;
      if (cx < area.x || cx > area.x + area.w || cy < area.y || cy > area.y + area.h) continue;
      const cs = getComputedStyle(d), weight = Math.max(1, Math.min(r.w * r.h, 4000));
      if (d instanceof SVGElement) {
        // Only drawn shapes count (the <svg>/<g> containers report an inherited default fill).
        if (!['path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon'].includes(d.tagName.toLowerCase())) continue;
        const fill = d.getAttribute('fill') === 'none' ? null : cs.fill, stroke = cs.strokeWidth === '0px' ? null : cs.stroke;
        for (const c of [fill, stroke]) if (c && c !== 'none' && alpha(c) > 0.3) add(chart.colors, c, weight);
      } else if (alpha(cs.backgroundColor) > 0.3 && r.w * r.h < area.w * area.h * 0.6) add(chart.colors, cs.backgroundColor, weight);
      const t = own(d);
      if (t) {
        const size = parseFloat(cs.fontSize);
        if (/[0-9]/.test(t)) chart.values.push({size, color: cs.color, font: cs.fontFamily, weight: cs.fontWeight});
        if (size <= 12 && t.length <= 14) add(chart.labels, cs.color, 1);  // axis-style labels (counted, not prose)
      }
    }
  };
  const add = (map, k, w) => { if (k) map[k] = (map[k] || 0) + w; };

  // The card's main number (a KPI's dummy value): where it sits in the content area and how it looks,
  // so the Power BI card can show the real value the same way.
  const valueStyle = (el, area) => {
    if (!area) return null;
    let best = null;
    for (const d of el.querySelectorAll('*')) {
      const t = own(d);
      if (!t || !/[0-9]/.test(t) || !shown(d)) continue;
      const r = rel(d), cs = getComputedStyle(d);
      const cx = r.x + r.w / 2, cy = r.y + r.h / 2;
      if (cx < area.x || cx > area.x + area.w || cy < area.y || cy > area.y + area.h) continue;
      const size = parseFloat(cs.fontSize);
      if (!best || size > best.size) {
        // The text's own width (an inline box may be wider than its glyphs).
        const range = document.createRange(); range.selectNodeContents(d);
        const tr = range.getBoundingClientRect();
        best = {x: tr.left - o.left, y: tr.top - o.top, w: tr.width, h: tr.height, size, weight: parseInt(cs.fontWeight) || 400,
                color: cs.color, font: cs.fontFamily};
      }
    }
    if (!best) return null;
    const left = best.x - area.x, right = area.x + area.w - (best.x + best.w);
    best.align = Math.abs(left - right) <= Math.max(6, area.w * 0.08) ? 'center' : left < right ? 'left' : 'right';
    return best;
  };

  const boxes = found.map(({el, titleEl}) => {
    const cs = getComputedStyle(el);
    const ts = titleEl ? getComputedStyle(titleEl) : cs;
    const area = contentArea(el, titleEl);
    const value = valueStyle(el, area);
    collect(el, area);
    if (mark && area) el.setAttribute('data-dp-area', JSON.stringify({x: area.x + o.left, y: area.y + o.top, w: area.w, h: area.h}));
    return {
      area, value,
      ...rel(el),
      title: el.getAttribute('data-title') || (titleEl ? own(titleEl) : ''),
      text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 300),
      visual_id: el.getAttribute('data-visual-id'), type: el.getAttribute('data-type'),
      background: cs.backgroundColor, border: parseFloat(cs.borderTopWidth) > 0 ? cs.borderTopColor : null,
      radius: parseFloat(cs.borderTopLeftRadius) || 0,
      title_font: ts.fontFamily, title_color: ts.color, _el: el, _title: titleEl,
    };
  });
  boxes.sort((a, b) => (Math.round(a.y / 8) - Math.round(b.y / 8)) || (a.x - b.x));
  boxes.forEach((b, i) => {
    b.id = 'box_' + String(i + 1).padStart(2, '0');
    if (mark) { b._el.setAttribute('data-dp-box', b.id); if (b._title) b._title.setAttribute('data-dp-title', ''); }
    delete b._el; delete b._title;
  });

  // Palette: backgrounds weighted by visible area, text colors by amount of text.
  const bg = {}, fg = {}, fonts = {}, titleFonts = {};
  let n = 0;
  for (const el of [canvas, ...canvas.querySelectorAll('*')]) {
    if (++n > 4000) break;
    if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') continue;
    if (!shown(el)) continue;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const w = Math.max(0, Math.min(r.right, o.right) - Math.max(r.left, o.left));
    const h = Math.max(0, Math.min(r.bottom, o.bottom) - Math.max(r.top, o.top));
    if (alpha(cs.backgroundColor) > 0.04) add(bg, cs.backgroundColor, w * h);
    for (const c of (cs.backgroundImage.match(/rgba?\([^)]+\)|#[0-9a-fA-F]{3,6}\b/g) || [])) add(bg, c, w * h * 0.3);
    if (parseFloat(cs.borderTopWidth) > 0) add(bg, cs.borderTopColor, (w + h) * 2);
    const t = own(el);
    if (t) { add(fg, cs.color, t.length * parseFloat(cs.fontSize)); add(fonts, cs.fontFamily, t.length); }
  }
  for (const b of boxes) add(titleFonts, b.title_font, 1);
  // Canvas color: what is painted at the canvas edges (scaled Stitch pages put the page there).
  const paint = (x, y) => {
    let e = document.elementFromPoint(o.left + x, o.top + y);
    while (e) { const c = getComputedStyle(e).backgroundColor; if (alpha(c) > 0.5) return c; e = e.parentElement; }
    const c = getComputedStyle(document.body).backgroundColor;
    return alpha(c) > 0.5 ? c : null;
  };
  const edges = [[4, 4], [o.width - 4, 4], [4, o.height - 4], [o.width - 4, o.height - 4], [o.width / 2, 4]].map(([x, y]) => paint(x, y)).filter(Boolean);
  const canvasBg = edges.sort((a, b) => edges.filter(c => c === b).length - edges.filter(c => c === a).length)[0];
  return {w: o.width, h: o.height, boxes, bg, fg, fonts, titleFonts, chart, canvasBg: canvasBg || 'rgb(255, 255, 255)'};
}
"""


def _inset(box: dict, area: dict | None) -> list[int] | None:
    if not area:
        return None
    left, top = area["x"] - box["x"], area["y"] - box["y"]
    right, bottom = box["x"] + box["w"] - area["x"] - area["w"], box["y"] + box["h"] - area["y"] - area["h"]
    inset = [max(0, round(v)) for v in (left, top, right, bottom)]
    return inset if inset[0] + inset[2] < box["w"] - 20 and inset[1] + inset[3] < box["h"] - 16 else None


def _value(box: dict, v: dict | None) -> ValueStyle | None:
    if not v or v["w"] < 4 or v["h"] < 4:
        return None
    return ValueStyle(dx=round(v["x"] - box["x"]), dy=round(v["y"] - box["y"]), w=round(v["w"]), h=round(v["h"]),
                      size=round(v["size"], 1), weight=v["weight"], color=css_hex(v["color"]), font=_first_family(v["font"]),
                      align=v["align"])


def _first_family(stack: str) -> str:
    return (stack or "").split(",")[0].strip().strip("'\"") or "Segoe UI"


def _detect(page, mark: bool) -> dict:
    fit = page.evaluate(_FIT)
    data = page.evaluate(_DETECT, mark)
    data["fit"] = fit
    return data


def extract(html: str, allow_scripts: bool = False) -> Extraction:
    data = render_page(html, lambda page: _detect(page, False), allow_scripts)
    boxes, skipped = [], 0
    for b in data["boxes"]:
        x, y, w, h = (round(b[k]) for k in ("x", "y", "w", "h"))
        if x < -1 or y < -1 or x + w > CANVAS_W + 1 or y + h > CANVAS_H + 1:
            skipped += 1  # Stitch pages can be taller than the canvas; only the 1280x720 part counts
            continue
        boxes.append(DetectedBox(
            id=b["id"], x=max(0, x), y=max(0, y), w=min(w, CANVAS_W - max(0, x)), h=min(h, CANVAS_H - max(0, y)),
            title=" ".join((b["title"] or "").split())[:120], text=b["text"], visual_id=b["visual_id"], type=b["type"],
            background=css_hex(b["background"]), border=css_hex(b["border"]), radius=round(b["radius"]),
            title_font=_first_family(b["title_font"]), title_color=css_hex(b["title_color"]),
            inset=_inset(b, b.get("area")),
            value=_value(b, b.get("value")),
        ))
    palette = _palette(data, boxes)
    chart = data.get("chart") or {}
    card = next((c.hex for c in palette if c.role == "card"), "#FFFFFF")
    def hexes(weights: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for c, w in weights.items():
            h = css_hex(c)
            if h:
                out[h] = out.get(h, 0) + w
        return out

    series = [c for c, _ in _merge(hexes(chart.get("colors", {}))) if contrast(c, card) >= 1.15]
    labels = _merge(hexes(chart.get("labels", {})))
    values = sorted(chart.get("values", []), key=lambda v: -v["size"])
    fit = data.get("fit") or {}
    return Extraction(
        canvas_w=data["w"], canvas_h=data["h"], boxes=boxes, skipped=skipped, palette=palette,
        heading_font=_first_family(max(data["titleFonts"], key=data["titleFonts"].get)) if data["titleFonts"] else "Segoe UI",
        body_font=_first_family(max(data["fonts"], key=data["fonts"].get)) if data["fonts"] else "Segoe UI",
        source_w=fit.get("w", CANVAS_W), source_h=fit.get("h", CANVAS_H), scale=round(fit.get("scale", 1.0), 4),
        chart_colors=series[:8], label_color=labels[0][0] if labels else None,
        value_color=css_hex(values[0]["color"]) if values else None,
        value_font=_first_family(values[0]["font"]) if values else None,
    )


def _palette(data: dict, boxes: list[DetectedBox]) -> list[ThemeColor]:
    canvas = css_hex(data["canvasBg"]) or "#FFFFFF"
    bgs = _merge({h: w for c, w in data["bg"].items() if (h := css_hex(c))})
    texts = _merge({h: w for c, w in data["fg"].items() if (h := css_hex(c))})
    cards = _merge({b.background: b.w * b.h for b in boxes if b.background})
    card = next((c for c, _ in cards if _distance(c, canvas) > 0.02), cards[0][0] if cards else canvas)
    text = next((c for c, _ in texts if contrast(c, card) >= 3), "#FFFFFF" if luminance(card) < 0.4 else "#1B1C1C")
    muted = next((c for c, _ in texts if _distance(c, text) > 0.08 and contrast(c, card) >= 2), _mix(text, card, 0.4))
    total = sum(w for _, w in bgs) + sum(w for _, w in texts) or 1
    vivid = [(c, w) for c, w in _merge({**dict(bgs), **{c: w * 50 for c, w in texts}}) if _saturation(c) > 0.35 and 0.03 < luminance(c) < 0.9]
    out = [ThemeColor(hex=canvas, role="canvas"), ThemeColor(hex=card, role="card"),
           ThemeColor(hex=text, role="text"), ThemeColor(hex=muted, role="muted")]
    for i, (c, w) in enumerate(vivid[:4]):
        out.append(ThemeColor(hex=c, role="accent" if i == 0 else "other", weight=round(w / total, 4)))
    seen: list[str] = []
    unique = []
    for c in out:
        if c.role in ("accent", "other") and any(_distance(c.hex, s) < 0.06 for s in seen):
            continue
        seen.append(c.hex)
        unique.append(c)
    return unique


# --- matching --------------------------------------------------------------------------------

def _norm(text: str) -> str:
    text = text.lower().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", text).split())


def title_score(title: str, box: DetectedBox) -> float:
    a, b = _norm(title), _norm(box.title)
    if not a:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio() if b else 0.0
    ta, tb = set(a.split()), set(b.split())
    tokens = len(ta & tb) / max(len(ta), len(tb)) if tb else 0.0
    inside = 0.9 if f" {a} " in f" {_norm(box.text)} " else 0.0  # exact title somewhere in the card
    return round(max(ratio, tokens * 0.95, inside), 3)


class _AIPair(BaseModel):
    visual_id: str
    box_id: str


class _AIPairs(BaseModel):
    pairs: list[_AIPair]


def _item(visual_id: str, box: DetectedBox, method: str, score: float) -> MappingItem:
    return MappingItem(visual_id=visual_id, box_id=box.id, x=box.x, y=box.y, w=box.w, h=box.h, method=method, score=score)


def match(plan: DashboardPlan, boxes: list[DetectedBox], llm: LLMProvider | None = None) -> tuple[list[MappingItem], list[str]]:
    """Planned visual -> detected box (id, then title, then AI). Unmatched visuals stay unplaced."""
    notes: list[str] = []
    by_visual: dict[str, MappingItem] = {}
    used: set[str] = set()
    planned = {v.id: v for v in plan.visuals}

    for b in boxes:  # 1. contract ids (Options B/C)
        if b.visual_id in planned and b.visual_id not in by_visual and b.id not in used:
            by_visual[b.visual_id] = _item(b.visual_id, b, "id", 1.0)
            used.add(b.id)

    pairs = sorted(  # 2. titles (Stitch): best pairs first, each side used once
        ((title_score(v.title, b), v.id, b) for v in plan.visuals if v.id not in by_visual for b in boxes if b.id not in used),
        key=lambda t: -t[0],
    )
    for score, vid, b in pairs:
        if score < TITLE_THRESHOLD:
            break
        if vid in by_visual or b.id in used:
            continue
        by_visual[vid] = _item(vid, b, "title", score)
        used.add(b.id)

    left = [v for v in plan.visuals if v.id not in by_visual]
    free = [b for b in boxes if b.id not in used]
    if left and free and llm is not None:  # 3. AI fallback for renamed / reworded titles
        try:
            answer = llm.generate_text(_ai_prompt(left, free), json_schema=_AIPairs)
            free_ids = {b.id: b for b in free}
            accepted = 0
            for p in answer.pairs:
                if p.visual_id in planned and p.visual_id not in by_visual and p.box_id in free_ids and p.box_id not in used:
                    by_visual[p.visual_id] = _item(p.visual_id, free_ids[p.box_id], "ai", 0.6)
                    used.add(p.box_id)
                    accepted += 1
            if accepted:
                notes.append(f"AI matched {accepted} visual{'s' if accepted != 1 else ''} whose titles differ in the design; please check them.")
        except Exception as exc:  # matching still works without AI; the user maps the rest
            logger.warning("AI mapping skipped: %s", exc)
            notes.append("AI matching unavailable; map the remaining visuals by hand.")

    mapping = [by_visual.get(v.id) or MappingItem(visual_id=v.id) for v in plan.visuals]
    return mapping, notes


def _ai_prompt(visuals, boxes: list[DetectedBox]) -> str:
    vs = [{"visual_id": v.id, "role": v.role, "type": v.type, "title": v.title, "measures": v.measures} for v in visuals]
    bs = [{"box_id": b.id, "title": b.title, "text": b.text[:120], "size": f"{b.w}x{b.h}", "position": f"{b.x},{b.y}"} for b in boxes]
    return (PROMPT.read_text(encoding="utf-8")
            .replace("{visuals}", json.dumps(vs, ensure_ascii=False))
            .replace("{boxes}", json.dumps(bs, ensure_ascii=False)))


# --- validation ------------------------------------------------------------------------------

def validate_mapping(plan: DashboardPlan, mapping: list[MappingItem], boxes: list[DetectedBox]) -> list[str]:
    """Same rules as the design validator, on the final placement Step 9 will use."""
    issues: list[str] = []
    titles = {v.id: v.title for v in plan.visuals}
    box_ids = {b.id for b in boxes}
    seen: dict[str, int] = {}
    for m in mapping:
        seen[m.visual_id] = seen.get(m.visual_id, 0) + 1
    for vid, title in titles.items():
        if seen.get(vid, 0) == 0 or not next(m for m in mapping if m.visual_id == vid).placed:
            issues.append(f"'{title}' has no box yet; pick a box or place it by hand.")
        elif seen[vid] > 1:
            issues.append(f"'{title}' is mapped more than once.")
    for m in mapping:
        if m.visual_id not in titles:
            issues.append(f"Mapping refers to unknown visual {m.visual_id}.")
    used: dict[str, str] = {}
    for m in mapping:
        if m.box_id is None:
            continue
        if m.box_id not in box_ids:
            issues.append(f"Box {m.box_id} does not exist in the design.")
        elif m.box_id in used:
            issues.append(f"Box {m.box_id} is used by both '{titles.get(used[m.box_id], used[m.box_id])}' and '{titles.get(m.visual_id, m.visual_id)}'.")
        used.setdefault(m.box_id, m.visual_id)
    placed = [m for m in mapping if m.placed and m.visual_id in titles]
    for m in placed:
        if m.w < MIN_W or m.h < MIN_H:
            issues.append(f"'{titles[m.visual_id]}' is too small ({m.w}x{m.h}px; at least {MIN_W}x{MIN_H}).")
        if m.x < 0 or m.y < 0 or m.x + m.w > CANVAS_W or m.y + m.h > CANVAS_H:
            issues.append(f"'{titles[m.visual_id]}' is outside the 1280x720 canvas.")
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            if overlap(a, b):
                issues.append(f"'{titles[a.visual_id]}' overlaps '{titles[b.visual_id]}'.")
    return list(dict.fromkeys(issues))


# --- background ------------------------------------------------------------------------------

_HIDE_CSS = """
[data-dp-hide] * { visibility: hidden !important; }
[data-dp-hide] [data-dp-title], [data-dp-hide] [data-dp-title] * { visibility: visible !important; }
[data-dp-hide] [data-chart-area], [data-dp-hide-all] [data-chart-area] { visibility: visible !important; }
[data-dp-hide] [data-chart-area] * { visibility: hidden !important; }
[data-dp-hide] .dp-kpi-bar, [data-dp-hide] .dp-kpi-meta, [data-dp-hide] .dp-kpi-meta * { visibility: visible !important; }
[data-dp-hide] .dp-sparkline, [data-dp-hide] .dp-sparkline * { visibility: visible !important; }
[data-dp-hide] .dp-kpi-progress, [data-dp-hide] .dp-kpi-progress * { visibility: visible !important; }
[data-dp-hide] .dp-subtitle-insight, [data-dp-hide] .dp-subtitle-insight * { visibility: visible !important; }
[data-dp-hide-all] *:not([data-chart-area]) { visibility: hidden !important; }
"""


def title_kept(visual_title: str, box: DetectedBox | None) -> bool:
    """Whether the card's own title can stay in the background for this visual."""
    return box is not None and title_score(visual_title, box) >= TITLE_THRESHOLD


# Contract cards (data-visual-id) hide everything but the title (CSS above). Other cards (Stitch
# exports) hide only what lies in the content area Power BI will cover, so everything else in the
# design — static labels beside a title, decorations, header, logo — stays pixel-identical.
_HIDE_JS = """
([ids, all, css]) => {
  const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);
  for (const id of ids) for (const el of document.querySelectorAll(`[data-dp-box="${id}"]`)) {
    const area = el.getAttribute('data-dp-area');
    if (all.includes(id)) { el.setAttribute('data-dp-hide-all', ''); continue; }
    if (el.hasAttribute('data-visual-id') || !area) { el.setAttribute('data-dp-hide', ''); continue; }
    const a = JSON.parse(area), title = el.querySelector('[data-dp-title]');
    for (const d of el.querySelectorAll('*')) {
      if (title && (d === title || d.contains(title) || title.contains(d))) continue;
      const r = d.getBoundingClientRect();
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      if (cx >= a.x && cx <= a.x + a.w && cy >= a.y && cy <= a.y + a.h) d.style.setProperty('visibility', 'hidden', 'important');
    }
  }
}
"""


def _clip(page) -> bytes:
    r = page.evaluate("() => { const c = document.querySelector('[data-canvas]') || document.body; const r = c.getBoundingClientRect(); return {x: r.left, y: r.top}; }")
    return page.screenshot(clip={"x": max(0, r["x"]), "y": max(0, r["y"]), "width": CANVAS_W, "height": CANVAS_H}, full_page=True)


def render_design(html: str, hide_box_ids: list[str], allow_scripts: bool = False, hide_titles: list[str] | None = None) -> tuple[bytes, bytes]:
    """(original render, clean background) of the 1280x720 canvas in one browser session.
    The background hides the mapped cards' dummy contents (fake charts, KPI values, slicer contents,
    insight text) and keeps card shapes, titles, header and logo; Power BI draws the rest.
    Cards in `hide_titles` lose their title too (another visual sits there; Power BI titles it)."""

    def shoot(page) -> tuple[bytes, bytes]:
        _detect(page, True)
        original = _clip(page)
        page.evaluate(_HIDE_JS, [hide_box_ids, hide_titles or [], _HIDE_CSS])
        return original, _clip(page)

    return render_page(html, shoot, allow_scripts)


def background_png(html: str, hide_box_ids: list[str], allow_scripts: bool = False, hide_titles: list[str] | None = None) -> bytes:
    return render_design(html, hide_box_ids, allow_scripts, hide_titles)[1]


# --- Power BI theme ----------------------------------------------------------------------------

def _role(palette: list[ThemeColor], role: str, default: str) -> str:
    return next((c.hex for c in palette if c.role == role), default)


def data_colors(palette: list[ThemeColor], brand: BrandPalette, background: str, n: int = 8, chart: list[str] | None = None) -> list[str]:
    """Series colors: the colors the design's own charts use (Stitch placeholders), the design's
    accent, brand colors, other vivid design colors, then hue steps; each must stand out from the
    canvas and from the colors before it."""
    accent = _role(palette, "accent", brand.accent)
    candidates = list(chart or []) + [accent, css_hex(brand.accent), css_hex(brand.growth)]
    candidates += [c.hex for c in palette if c.role == "other"]
    candidates += [css_hex(brand.muted), css_hex(brand.base)]
    light_canvas = luminance(background) > 0.4
    for step in (150, 210, 40, 270, 100, 320, 180, 75, 240, 15):
        candidates.append(_rotate(accent, step, 0.42 if light_canvas else 0.62))
    out: list[str] = []
    own = set(chart or [])
    for c in candidates:
        # The design's own chart colors are kept unless nearly invisible (the designer chose them).
        if c and contrast(c, background) >= (1.15 if c in own else 1.6) and all(_distance(c, o) > 0.18 for o in out):
            out.append(c)
        if len(out) == n:
            break
    return out


PBI_FONTS = {"Segoe UI", "Segoe UI Semibold", "Segoe UI Light", "Arial", "Calibri", "Georgia", "Verdana", "Tahoma",
             "Trebuchet MS", "Cambria", "Candara", "Corbel", "Consolas", "Courier New", "Times New Roman", "DIN"}


def build_theme(name: str, palette: list[ThemeColor], brand: BrandPalette, found: Extraction | None = None) -> dict:
    """Power BI theme from the design: canvas/card/text colors, the design's chart colors first in the
    series colors, and its label and KPI value styles (fonts only when Power BI has them)."""
    canvas = _role(palette, "canvas", css_hex(brand.canvas) or "#FFFFFF")
    card = _role(palette, "card", canvas)
    text = _role(palette, "text", "#1B1C1C")
    muted = _role(palette, "muted", _mix(text, card, 0.4))
    if found and found.label_color and contrast(found.label_color, card) >= 2:
        muted = found.label_color
    value = found.value_color if found and found.value_color and contrast(found.value_color, card) >= 3 else text
    value_font = found.value_font if found and found.value_font in PBI_FONTS else "Segoe UI"
    colors = data_colors(palette, brand, card, chart=found.chart_colors if found else None)
    solid = lambda c: {"solid": {"color": c}}  # noqa: E731
    grid = _mix(card, text, 0.12)
    return {
        "name": name[:60],
        "dataColors": colors,
        "background": card,
        "foreground": text,
        "tableAccent": colors[0],
        "good": css_hex(brand.growth) or "#4CAF7A",
        "neutral": muted,
        "bad": "#E5484D",
        "maximum": colors[0], "center": _mix(colors[0], card, 0.5), "minimum": card,
        "textClasses": {
            "callout": {"fontSize": 26, "fontFace": value_font, "color": value},
            "title": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": text},
            "header": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": text},
            "label": {"fontSize": 10, "fontFace": "Segoe UI", "color": muted},
        },
        "visualStyles": {
            "*": {"*": {
                # The designed card (background PNG) shows through; titles are part of the design.
                "background": [{"show": False, "transparency": 100}],
                "border": [{"show": False}],
                "dropShadow": [{"show": False}],
                "visualHeader": [{"show": False}],
                "title": [{"show": False, "fontColor": solid(text), "fontFamily": "Segoe UI"}],
                "categoryAxis": [{"labelColor": solid(muted), "fontFamily": "Segoe UI", "gridlineColor": solid(grid)}],
                "valueAxis": [{"labelColor": solid(muted), "fontFamily": "Segoe UI", "gridlineColor": solid(grid)}],
                "legend": [{"labelColor": solid(muted), "fontFamily": "Segoe UI"}],
                "labels": [{"color": solid(text), "fontFamily": "Segoe UI"}],
            }},
            "card": {"*": {
                "labels": [{"color": solid(value), "fontFamily": value_font, "fontSize": 26}],
                "categoryLabels": [{"show": False}],
            }},
            "slicer": {"*": {
                "header": [{"show": False}],
                "items": [{"fontColor": solid(text), "fontFamily": "Segoe UI", "background": solid(card)}],
            }},
            "tableEx": {"*": {
                "columnHeaders": [{"fontColor": solid(text), "backColor": solid(card), "fontFamily": "Segoe UI Semibold"}],
                "values": [{"fontColorPrimary": solid(text), "backColorPrimary": solid(card),
                            "fontColorSecondary": solid(text), "backColorSecondary": solid(_mix(card, text, 0.04))}],
            }},
            "page": {"*": {"background": [{"transparency": 100}], "outspace": [{"color": solid(canvas)}]}},
        },
    }

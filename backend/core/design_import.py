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
  // otherwise below the title (or right of it for short pill-shaped cards like slicers).
  const contentArea = (el, titleEl) => {
    const areaEl = el.querySelector('[data-chart-area]');
    if (areaEl) return rel(areaEl);
    if (!titleEl) return null;
    const b = rel(el), t = rel(titleEl);
    let a = null;
    if (b.h <= 64 && t.x + t.w < b.x + b.w * 0.7) a = {x: t.x + t.w + 6, y: b.y + 4, w: b.x + b.w - (t.x + t.w + 6) - 6, h: b.h - 8};
    else if (t.y + t.h < b.y + b.h * 0.6) a = {x: b.x + 8, y: t.y + t.h + 6, w: b.w - 16, h: b.y + b.h - (t.y + t.h + 6) - 8};
    return a && a.w >= 20 && a.h >= 16 ? a : null;
  };

  const boxes = found.map(({el, titleEl}) => {
    const cs = getComputedStyle(el);
    const ts = titleEl ? getComputedStyle(titleEl) : cs;
    return {
      area: contentArea(el, titleEl),
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
  const add = (map, k, w) => { if (k) map[k] = (map[k] || 0) + w; };
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
  let page = canvas, canvasBg = null;
  while (page && !canvasBg) { const c = getComputedStyle(page).backgroundColor; if (alpha(c) > 0.5) canvasBg = c; page = page.parentElement; }
  return {w: o.width, h: o.height, boxes, bg, fg, fonts, titleFonts, canvasBg: canvasBg || 'rgb(255, 255, 255)'};
}
"""


def _inset(box: dict, area: dict | None) -> list[int] | None:
    if not area:
        return None
    left, top = area["x"] - box["x"], area["y"] - box["y"]
    right, bottom = box["x"] + box["w"] - area["x"] - area["w"], box["y"] + box["h"] - area["y"] - area["h"]
    inset = [max(0, round(v)) for v in (left, top, right, bottom)]
    return inset if inset[0] + inset[2] < box["w"] - 20 and inset[1] + inset[3] < box["h"] - 16 else None


def _first_family(stack: str) -> str:
    return (stack or "").split(",")[0].strip().strip("'\"") or "Segoe UI"


def extract(html: str, allow_scripts: bool = False) -> Extraction:
    data = render_page(html, lambda page: page.evaluate(_DETECT, False), allow_scripts)
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
        ))
    return Extraction(
        canvas_w=data["w"], canvas_h=data["h"], boxes=boxes, skipped=skipped,
        palette=_palette(data, boxes),
        heading_font=_first_family(max(data["titleFonts"], key=data["titleFonts"].get)) if data["titleFonts"] else "Segoe UI",
        body_font=_first_family(max(data["fonts"], key=data["fonts"].get)) if data["fonts"] else "Segoe UI",
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
[data-dp-hide-all] *:not([data-chart-area]) { visibility: hidden !important; }
"""


def title_kept(visual_title: str, box: DetectedBox | None) -> bool:
    """Whether the card's own title can stay in the background for this visual."""
    return box is not None and title_score(visual_title, box) >= TITLE_THRESHOLD


def background_png(html: str, hide_box_ids: list[str], allow_scripts: bool = False, hide_titles: list[str] | None = None) -> bytes:
    """Canvas screenshot with the mapped cards' contents hidden (fake charts, KPI values, slicer
    contents, insight text); card shapes, titles, header and logo stay. Power BI draws the rest.
    Cards in `hide_titles` lose their title too (another visual sits there; Power BI titles it)."""
    hide_titles = hide_titles or []

    def shoot(page) -> bytes:
        page.evaluate(_DETECT, True)
        page.evaluate(
            """([ids, all, css]) => {
                for (const id of ids) document.querySelectorAll(`[data-dp-box="${id}"]`).forEach(el =>
                    el.setAttribute(all.includes(id) ? 'data-dp-hide-all' : 'data-dp-hide', ''));
                const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
            }""",
            [hide_box_ids, hide_titles, _HIDE_CSS],
        )
        r = page.evaluate("() => { const c = document.querySelector('[data-canvas]') || document.body; const r = c.getBoundingClientRect(); return {x: r.left, y: r.top}; }")
        return page.screenshot(clip={"x": max(0, r["x"]), "y": max(0, r["y"]), "width": CANVAS_W, "height": CANVAS_H}, full_page=True)

    return render_page(html, shoot, allow_scripts)


# --- Power BI theme ----------------------------------------------------------------------------

def _role(palette: list[ThemeColor], role: str, default: str) -> str:
    return next((c.hex for c in palette if c.role == role), default)


def data_colors(palette: list[ThemeColor], brand: BrandPalette, background: str, n: int = 8) -> list[str]:
    """Series colors: the design's accent, brand colors, other vivid design colors, then hue steps;
    each must stand out from the canvas and from the colors before it."""
    accent = _role(palette, "accent", brand.accent)
    candidates = [accent, css_hex(brand.accent), css_hex(brand.growth)]
    candidates += [c.hex for c in palette if c.role == "other"]
    candidates += [css_hex(brand.muted), css_hex(brand.base)]
    light_canvas = luminance(background) > 0.4
    for step in (150, 210, 40, 270, 100, 320, 180, 75, 240, 15):
        candidates.append(_rotate(accent, step, 0.42 if light_canvas else 0.62))
    out: list[str] = []
    for c in candidates:
        if c and contrast(c, background) >= 1.6 and all(_distance(c, o) > 0.18 for o in out):
            out.append(c)
        if len(out) == n:
            break
    return out


def build_theme(name: str, palette: list[ThemeColor], brand: BrandPalette) -> dict:
    canvas = _role(palette, "canvas", css_hex(brand.canvas) or "#FFFFFF")
    card = _role(palette, "card", canvas)
    text = _role(palette, "text", "#1B1C1C")
    muted = _role(palette, "muted", _mix(text, card, 0.4))
    colors = data_colors(palette, brand, card)
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
            "callout": {"fontSize": 26, "fontFace": "Segoe UI", "color": text},
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
                "labels": [{"color": solid(text), "fontFamily": "Segoe UI", "fontSize": 26}],
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

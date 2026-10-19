"""Design contract checks for 1280x720 dashboard HTML (shared by design methods B/C and Design Import).

`measure(html)` renders the page and returns every visual container's box. It uses Playwright with
the installed Edge/Chrome when available ("playwright" engine) and otherwise reads the absolutely
positioned inline styles DashPilot's own templates use ("static" engine). `check(html, plan)` then
enforces the contract: canvas size, one container per planned visual with the right type and
title, nothing outside the canvas, no overlaps, empty chart areas, Segoe UI for chart text, and no
scripts or external resources.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, TypeVar

from core.planner import CANVAS_H, CANVAS_W, DashboardPlan

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")
T = TypeVar("T")


@dataclass
class MeasuredBox:
    id: str
    type: str
    title: str
    x: float
    y: float
    w: float
    h: float
    chart_text: str = ""  # visible text inside the chart area (must be empty)
    text: str = ""  # all text in the container (titles, insight lines)


@dataclass
class Measurement:
    engine: str  # "playwright" | "static"
    canvas_w: float
    canvas_h: float
    boxes: list[MeasuredBox] = field(default_factory=list)


# --- static engine --------------------------------------------------------------------

_PX = re.compile(r"(?:^|;)\s*(left|top|width|height)\s*:\s*(-?\d+(?:\.\d+)?)px", re.I)  # whole properties only (not padding-left)


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canvas: tuple[float, float] | None = None
        self.boxes: list[MeasuredBox] = []
        self.stack: list[tuple[str, MeasuredBox | None, bool]] = []  # (tag, visual, in_chart_area)

    @staticmethod
    def _style(attrs: dict) -> dict[str, float]:
        return {k.lower(): float(v) for k, v in _PX.findall(attrs.get("style") or "")}

    def handle_starttag(self, tag, attrs_list):
        attrs = {k: (v or "") for k, v in attrs_list}
        style = self._style(attrs)
        visual = self.stack[-1][1] if self.stack else None
        in_chart = self.stack[-1][2] if self.stack else False
        if "data-canvas" in attrs and self.canvas is None:
            self.canvas = (style.get("width", 0.0), style.get("height", 0.0))
        if "data-visual-id" in attrs:
            visual = MeasuredBox(
                id=attrs["data-visual-id"], type=attrs.get("data-type", ""), title=attrs.get("data-title", ""),
                x=style.get("left", -1.0), y=style.get("top", -1.0), w=style.get("width", 0.0), h=style.get("height", 0.0),
            )
            self.boxes.append(visual)
        if "data-chart-area" in attrs:
            in_chart = True
        if tag.lower() not in ("br", "img", "hr", "meta", "link", "input"):
            self.stack.append((tag, visual, in_chart))

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()[0] == tag:
                break

    def handle_data(self, data):
        if not self.stack or self.stack[-1][1] is None or not data.strip():
            return
        visual = self.stack[-1][1]
        visual.text += " " + data
        if self.stack[-1][2]:
            visual.chart_text += data.strip()


def measure_static(html: str) -> Measurement:
    c = _Collector()
    c.feed(html)
    w, h = c.canvas or (0.0, 0.0)
    return Measurement(engine="static", canvas_w=w, canvas_h=h, boxes=c.boxes)


# --- playwright engine -------------------------------------------------------------------

_JS = """
() => {
  const canvas = document.querySelector('[data-canvas]') || document.body;
  const origin = canvas.getBoundingClientRect();
  const boxes = [...document.querySelectorAll('[data-visual-id]')].map(el => {
    const r = el.getBoundingClientRect();
    const area = el.querySelector('[data-chart-area]');
    return {
      id: el.getAttribute('data-visual-id'), type: el.getAttribute('data-type') || '', title: el.getAttribute('data-title') || '',
      x: r.left - origin.left, y: r.top - origin.top, w: r.width, h: r.height,
      chart_text: area ? (area.innerText || '').trim() : '',
      text: el.textContent || '',  // source text, before any CSS text-transform
    };
  });
  return {w: origin.width, h: origin.height, boxes};
}
"""


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


SCRIPT_HOSTS = ("cdn.tailwindcss.com",)  # Stitch exports style themselves with the Tailwind CDN


def render_page(html: str, work: Callable[[Any], T], allow_scripts: bool = False) -> T:
    """Open `html` at 1280x720 in a headless installed browser (Edge, then Chrome, then Playwright's
    Chromium) and return `work(page)`. Network is limited to the font hosts (and, with allow_scripts,
    the Tailwind CDN that Stitch exports need); everything else is blocked, so page scripts cannot
    reach anything. Without allow_scripts, scripts are stripped and never run."""
    from playwright.sync_api import sync_playwright

    if not allow_scripts:
        html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
    hosts = ALLOWED_HOSTS + (SCRIPT_HOSTS if allow_scripts else ())
    with sync_playwright() as p:
        browser = None
        for channel in ("msedge", "chrome", None):
            try:
                browser = p.chromium.launch(channel=channel) if channel else p.chromium.launch()
                break
            except Exception:
                continue
        if browser is None:
            raise RuntimeError("No browser available for Playwright")
        try:
            page = browser.new_page(viewport={"width": CANVAS_W, "height": CANVAS_H}, java_script_enabled=True)
            page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(("data:", "about:")) or any(h in route.request.url for h in hosts) else route.abort())
            page.set_content(html, wait_until="load", timeout=20000)
            return work(page)
        finally:
            browser.close()


def measure_playwright(html: str) -> Measurement:
    data = render_page(html, lambda page: page.evaluate(_JS))
    return Measurement(engine="playwright", canvas_w=data["w"], canvas_h=data["h"],
                       boxes=[MeasuredBox(**b) for b in data["boxes"]])


def measure(html: str, prefer_browser: bool = True) -> Measurement:
    if prefer_browser and playwright_available():
        try:
            return measure_playwright(html)
        except Exception as exc:  # no browser / sandbox issues: fall back, never fail the user
            logger.warning("Playwright measurement failed, using static layout: %s", exc)
    return measure_static(html)


# --- contract ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return " ".join(text.split())


def overlap(a, b, tolerance: float = 1.0) -> bool:
    """True when two boxes (anything with x/y/w/h) overlap by more than `tolerance` px."""
    return _overlap(a, b, tolerance)


def _overlap(a: MeasuredBox, b: MeasuredBox, tolerance: float = 1.0) -> bool:
    return a.x + tolerance < b.x + b.w and b.x + tolerance < a.x + a.w and a.y + tolerance < b.y + b.h and b.y + tolerance < a.y + a.h


def check(html: str, plan: DashboardPlan, prefer_browser: bool = True) -> tuple[list[str], Measurement]:
    """Contract errors (empty = valid) plus the measurement they were based on."""
    errors: list[str] = []
    if re.search(r"<script\b", html, re.I):
        errors.append("Remove all <script> tags; the design must be static HTML/CSS.")
    for url in re.findall(r"(?:src|href)\s*=\s*[\"']?(https?://[^\"'\s>]+)", html, re.I) + re.findall(r"url\(\s*[\"']?(https?://[^\"')\s]+)", html, re.I):
        if not any(h in url for h in ALLOWED_HOSTS):
            errors.append(f"External resource not allowed: {url[:80]}")
    if "segoe ui" not in html.lower():
        errors.append("Chart text must use the \"Segoe UI\" font (font-family on the chart areas).")

    m = measure(html, prefer_browser)
    if abs(m.canvas_w - CANVAS_W) > 1 or abs(m.canvas_h - CANVAS_H) > 1:
        errors.append(f"The canvas element with data-canvas must be exactly {CANVAS_W}x{CANVAS_H}px (found {m.canvas_w:.0f}x{m.canvas_h:.0f}).")
    planned = {v.id: v for v in plan.visuals}
    found: dict[str, list[MeasuredBox]] = {}
    for b in m.boxes:
        found.setdefault(b.id, []).append(b)
    for vid, v in planned.items():
        boxes = found.get(vid, [])
        if not boxes:
            errors.append(f"Missing container for {vid} ('{v.title}'): add data-visual-id=\"{vid}\".")
            continue
        if len(boxes) > 1:
            errors.append(f"{vid} appears {len(boxes)} times; each visual needs exactly one container.")
        b = boxes[0]
        if b.type != v.type:
            errors.append(f"{vid} must have data-type=\"{v.type}\" (found \"{b.type}\").")
        if b.title.strip() != v.title.strip():
            errors.append(f"{vid} must have data-title=\"{v.title}\" (found \"{b.title}\").")
        if b.w < 40 or b.h < 30:
            errors.append(f"{vid} is too small ({b.w:.0f}x{b.h:.0f}px).")
        if b.x < -1 or b.y < -1 or b.x + b.w > CANVAS_W + 1 or b.y + b.h > CANVAS_H + 1:
            errors.append(f"{vid} ('{v.title}') is outside the 1280x720 canvas.")
        if v.role in ("chart", "kpi") and b.chart_text:
            errors.append(f"{vid} has text inside its chart area (\"{b.chart_text[:30]}\"); leave chart areas empty.")
        shown = _norm(b.text)
        if _norm(v.title) not in shown:
            errors.append(f"{vid} must show its title exactly as \"{v.title}\" (same words and capitalisation; CSS text-transform is fine).")
        for line in v.text:
            if _norm(line) not in shown:
                errors.append(f"{vid} must show this insight line word for word: \"{line[:80]}\".")
    for vid in found:
        if vid not in planned:
            errors.append(f"Unknown data-visual-id \"{vid}\"; use only the planned ids.")
    boxes = [found[v][0] for v in planned if v in found]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if _overlap(a, b):
                errors.append(f"{a.id} overlaps {b.id}.")
    return list(dict.fromkeys(errors)), m

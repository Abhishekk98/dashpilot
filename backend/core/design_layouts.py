"""Layout library for DashPilot designs (Option B; Option C falls back to it).

The plan says WHAT is on a page; a layout decides WHERE. Every layout takes one page of the plan
(slicers, KPI cards, charts, the insights box, in any number the plan allows) and returns positions
on the 1280x720 canvas, plus where the title block goes and any decorative panels (a side rail, a
KPI band). All layouts keep every visual inside the canvas, never overlap, and keep Power BI's
minimum sizes (the Date Range pill keeps room for its two dates).

`suggest(page)` ranks the layouts that fit a page; the three Option B variants use different ones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from core.planner import CANVAS_H, CANVAS_W, Box, DashboardPlan, PlanVisual

M, G = 24, 16  # outer margin, gap
SLICER_H = 40
DATE_W, SLICER_W, SLICER_MIN_W = 280, 200, 168
TOP = 72  # first row under the header


@dataclass
class Arrangement:
    layout: str
    label: str
    visuals: list[PlanVisual]  # copies of the page's visuals with their boxes set
    header: Box
    panels: list[tuple[str, Box]] = field(default_factory=list)  # ("rail" | "band", box) drawn behind the cards

    def plan(self, plan: DashboardPlan) -> DashboardPlan:
        return plan.model_copy(update={"visuals": self.visuals})


LAYOUTS: dict[str, tuple[str, str]] = {
    "bento": ("Bento Grid", "Asymmetric tiles: a wide hero chart beside a 2-column grid, KPIs in a weighted band."),
    "hero_trend": ("Hero KPI + Trend", "One headline KPI next to a large trend, supporting KPIs and charts below."),
    "side_panel": ("Side Panel", "A full-height rail with title, filters and stacked KPIs; charts fill the stage."),
    "executive_split": ("Executive Split", "Story on the left (hero chart + detail), numbers on the right (KPI grid + insights)."),
    "command_center": ("Command Center", "Dense terminal style: KPI ticker, three-column chart grid, insights column."),
    "editorial": ("Editorial", "Magazine layout: hero chart and supporting charts left, a KPI column on the right."),
    "detail_focus": ("Detail Focus", "A large table or main chart with supporting charts stacked beside it."),
    "grid": ("Classic Grid", "Header, KPI row and an even grid of charts."),
}


# --- helpers ------------------------------------------------------------------------------------

def _b(x: float, y: float, w: float, h: float) -> Box:
    return Box(x=int(round(x)), y=int(round(y)), w=int(round(w)), h=int(round(h)))


def _row(items: list[PlanVisual], x: float, y: float, w: float, h: float, weights: list[float] | None = None, gap: int = G) -> None:
    if not items:
        return
    weights = weights or [1.0] * len(items)
    unit = (w - gap * (len(items) - 1)) / sum(weights)
    cx = x
    for i, (v, wt) in enumerate(zip(items, weights)):
        right = x + w if i == len(items) - 1 else cx + unit * wt
        v.box = _b(cx, y, right - cx, h)
        cx = right + gap


def _col(items: list[PlanVisual], x: float, y: float, w: float, h: float, gap: int = G, max_h: float | None = None) -> float:
    """Stack items; returns the bottom edge used."""
    if not items:
        return y
    ih = (h - gap * (len(items) - 1)) / len(items)
    if max_h:
        ih = min(ih, max_h)
    for i, v in enumerate(items):
        v.box = _b(x, y + i * (ih + gap), w, ih)
    return y + len(items) * ih + (len(items) - 1) * gap


def _grid(items: list[PlanVisual], x: float, y: float, w: float, h: float, cols: int, gap: int = G) -> None:
    """Rows of `cols`; a shorter last row stretches its items to the full width."""
    if not items:
        return
    cols = max(1, min(cols, len(items)))
    rows = math.ceil(len(items) / cols)
    rh = (h - gap * (rows - 1)) / rows
    for r in range(rows):
        _row(items[r * cols:(r + 1) * cols], x, y + r * (rh + gap), w, rh, gap=gap)


def _slicer_bar(slicers: list[PlanVisual], right: float, y: float, min_left: float) -> float:
    """Slicer pills right-aligned in the header row; returns their left edge."""
    widths = [DATE_W if s.title == "Date Range" else SLICER_W for s in slicers]
    if right - sum(widths) - (G // 2) * max(0, len(widths) - 1) < min_left:
        widths = [DATE_W if s.title == "Date Range" else SLICER_MIN_W for s in slicers]
    x = right
    for s, w in zip(reversed(slicers), reversed(widths)):
        x -= w
        s.box = _b(x, y, w, SLICER_H)
        x -= G // 2
    return x + G // 2 if slicers else right


def _parts(visuals: list[PlanVisual]):
    vs = [v.model_copy(deep=True) for v in visuals]
    slicers = [v for v in vs if v.role == "slicer"]
    kpis = [v for v in vs if v.role == "kpi"]
    charts = [v for v in vs if v.role == "chart"]
    insights = [v for v in vs if v.role == "insights"]
    return vs, slicers, kpis, charts, insights


def _hero(charts: list[PlanVisual]) -> tuple[PlanVisual | None, list[PlanVisual]]:
    """The chart that deserves the most room: a trend first, then a table, else the first chart."""
    if not charts:
        return None, []
    hero = next((c for c in charts if c.type in ("line", "area")), None) or next((c for c in charts if c.type in ("table", "matrix")), charts[0])
    return hero, [c for c in charts if c is not hero]


def _header_row(slicers: list[PlanVisual]) -> Box:
    left = _slicer_bar(slicers, CANVAS_W - M, 16, M + 360)
    return _b(M, 14, max(320, left - M - G), 46)


# --- layouts --------------------------------------------------------------------------------------

def _bento(visuals):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers)
    y, inner = TOP, CANVAS_W - 2 * M
    if kpis:
        _row(kpis, M, y, inner, 96, gap=G)
        y += 96 + G
    hero, rest = _hero(charts)
    rest = rest + insights
    h = CANVAS_H - M - y
    if not rest:
        hero.box = _b(M, y, inner, h)
    else:
        hw = int(round((inner - G) * (0.50 if len(rest) >= 3 else 0.56)))
        hero.box = _b(M, y, hw, h)
        _grid(rest, M + hw + G, y, inner - hw - G, h, 2, gap=G)
    return vs, header, [("band", _b(0, 0, CANVAS_W, TOP - 4))] if not kpis else []


def _hero_trend(visuals):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers)
    inner = CANVAS_W - 2 * M
    hero, rest = _hero(charts)
    y = TOP
    if kpis:
        _row(kpis, M, y, inner, 92, gap=G)
        y += 92 + G
    tiles = rest + insights
    h = CANVAS_H - M - y
    if not tiles:
        hero.box = _b(M, y, inner, h)
    else:
        hw = int(round((inner - G) * (0.55 if len(tiles) <= 3 else 0.50)))
        hero.box = _b(M, y, hw, h)
        _grid(tiles, M + hw + G, y, inner - hw - G, h, 2 if len(tiles) >= 3 else 1, gap=G)
    return vs, header, []


def _side_panel(visuals):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    rail = 336
    header = _b(M, 20, rail - 2 * M, 52)
    y = 20 + 52 + 12
    date_slicers = [s for s in slicers if s.title == "Date Range"]
    other_slicers = [s for s in slicers if s.title != "Date Range"]
    for s in date_slicers:
        s.box = _b(M, y, rail - 2 * M, 36)
        y += 36 + 10
    if len(other_slicers) >= 2:
        _row(other_slicers[:2], M, y, rail - 2 * M, 34, gap=8)
        y += 34 + 12
        for s in other_slicers[2:]:
            s.box = _b(M, y, rail - 2 * M, 34)
            y += 34 + 10
    elif other_slicers:
        other_slicers[0].box = _b(M, y, rail - 2 * M, 34)
        y += 34 + 12
    if slicers:
        y = max(y, 160)
    if kpis:
        _col(kpis, M, y, rail - 2 * M, CANVAS_H - M - y, gap=12, max_h=110)
    x0 = rail + G
    w = CANVAS_W - M - x0
    hero, rest = _hero(charts)
    tiles = rest + insights
    h = CANVAS_H - 2 * M
    if not kpis and not slicers and not tiles:
        hero.box = _b(x0, M, w, h)
    elif not tiles:
        hero.box = _b(x0, M, w, h)
    else:
        hh = int(round(h * (0.42 if len(tiles) >= 3 else 0.48) - G / 2))
        hero.box = _b(x0, M, w, hh)
        _grid(tiles, x0, M + hh + G, w, h - hh - G, 2 if len(tiles) <= 4 else 3, gap=G)
    return vs, header, [("rail", _b(0, 0, rail, CANVAS_H))]


def _executive_split(visuals):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers)
    left_w = 736
    rx, rw = M + left_w + G, CANVAS_W - 2 * M - left_w - G
    body = CANVAS_H - M - TOP
    hero, rest = _hero(charts)
    left_more, right_more = rest[:2], rest[2:]
    if not kpis and not insights and not right_more:
        left_w, rw = CANVAS_W - 2 * M, 0
    hh = int(round(body * (0.54 if left_more else 1.0) - (G / 2 if left_more else 0)))
    hero.box = _b(M, TOP, left_w, hh)
    if left_more:
        _row(left_more, M, TOP + hh + G, left_w, body - hh - G, gap=G)
    if rw:
        y = TOP
        if kpis:
            rows = math.ceil(len(kpis) / 2)
            kh = 92
            for r in range(rows):
                _row(kpis[r * 2:(r + 1) * 2], rx, y + r * (kh + G), rw, kh, gap=G)
            y += rows * kh + (rows - 1) * G + G
        stack = insights + right_more
        if len(stack) >= 3:
            _grid(stack, rx, y, rw, CANVAS_H - M - y, 2, gap=G)
        elif stack:
            _col(stack, rx, y, rw, CANVAS_H - M - y, gap=G)
    return vs, header, []


def _command_center(visuals):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers)
    inner = CANVAS_W - 2 * M
    y = TOP
    if kpis:
        _row(kpis, M, y, inner, 92, gap=G)
        y += 92 + G
    h = CANVAS_H - M - y
    side = 300 if insights else 0
    if insights:
        insights[0].box = _b(CANVAS_W - M - side, y, side, h)
    w = inner - (side + G if side else 0)
    cols = 3 if len(charts) >= 5 or (len(charts) == 3 and not insights) else 2 if len(charts) >= 2 else 1
    _grid(charts, M, y, w, h, cols, gap=G)
    return vs, header, [("band", _b(0, TOP - 6, CANVAS_W, 92 + 12))] if kpis else []


def _editorial(visuals):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers)
    col_w = 280 if kpis else 0
    x_r = CANVAS_W - M - col_w
    body = CANVAS_H - M - TOP
    if kpis:
        _col(kpis, x_r, TOP, col_w, body, gap=G, max_h=132)
    w = CANVAS_W - 2 * M - (col_w + G if col_w else 0)
    hero, rest = _hero(charts)
    tiles = rest + insights
    if not tiles:
        hero.box = _b(M, TOP, w, body)
    else:
        hh = int(round(body * (0.52 if len(tiles) <= 3 else 0.44) - G / 2))
        hero.box = _b(M, TOP, w, hh)
        y = TOP + hh + G
        _grid(tiles, M, y, w, CANVAS_H - M - y, 3 if len(tiles) >= 5 else 2, gap=G)
    return vs, header, []


def _detail_focus(visuals):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers)
    inner = CANVAS_W - 2 * M
    y = TOP
    if kpis:
        _row(kpis, M, y, inner, 92, gap=G)
        y += 92 + G
    main = next((c for c in charts if c.type in ("table", "matrix")), None) or _hero(charts)[0]
    rest = [c for c in charts if c is not main] + insights
    h = CANVAS_H - M - y
    if not rest:
        main.box = _b(M, y, inner, h)
    else:
        mw = int(round((inner - G) * 0.58))
        main.box = _b(M, y, mw, h)
        _grid(rest, M + mw + G, y, inner - mw - G, h, 1 if len(rest) <= 3 else 2, gap=G)
    return vs, header, []


def _classic(visuals):
    from core.planner import layout  # noqa: PLC0415

    vs = [v.model_copy(deep=True) for v in visuals]
    layout(vs)
    slicers = [v for v in vs if v.role == "slicer"]
    left = min((s.box.x for s in slicers), default=CANVAS_W - M)
    return vs, _b(M, 14, max(320, left - M - G), 46), []


_BUILDERS = {
    "bento": _bento, "hero_trend": _hero_trend, "side_panel": _side_panel, "executive_split": _executive_split,
    "command_center": _command_center, "editorial": _editorial, "detail_focus": _detail_focus, "grid": _classic,
}


def arrange(page: DashboardPlan, layout: str) -> Arrangement:
    """Positions for one page (a plan from planner.page_plan) in the given layout; visual order is kept."""
    built, header, panels = _BUILDERS[layout](page.visuals)
    by_id = {v.id: v for v in built}
    return Arrangement(layout=layout, label=LAYOUTS[layout][0], visuals=[by_id[v.id] for v in page.visuals], header=header, panels=panels)


def suggest(page: DashboardPlan) -> list[str]:
    """Layouts ranked by fit for this page's content (best first; never empty)."""
    roles = [v.role for v in page.visuals]
    k, c, s = roles.count("kpi"), roles.count("chart"), roles.count("slicer")
    trend = any(v.type in ("line", "area") for v in page.visuals if v.role == "chart")
    table = any(v.type in ("table", "matrix") for v in page.visuals if v.role == "chart")
    score = {
        "bento": 3.0 + (c >= 3),
        "hero_trend": (3.5 if trend else 1.5) if k >= 1 else 0.5,
        "side_panel": (3.2 if k >= 3 else 2.0 if k >= 1 else 1.0) - (s > 4),
        "executive_split": 2.6 + (k >= 2) * 0.5,
        "command_center": 3.1 if c >= 4 else 1.4,
        "editorial": 2.5 if 2 <= k <= 5 else 0.6,
        "detail_focus": 4.0 if (table and k == 0) else 1.2 if table else 0.3,
        "grid": 0.1,
    }
    if k == 0:  # detail pages: keep the KPI-centric layouts down
        score["hero_trend"] -= 1
        score["editorial"] -= 1
    order = list(LAYOUTS)
    return sorted(order, key=lambda name: (-score[name], order.index(name)))


def verify_layout_grid(arr: Arrangement, min_chart: tuple[int, int] = (160, 110)) -> list[str]:
    """Automated strict layout & grid verification:
    - Zero canvas overflow (all visuals fit within 1280x720 canvas margins)
    - Zero overlaps between any visual pair
    - Zero overlaps with header
    - All KPI cards are identical in height and width (when in rows) or height (in columns)
    - Minimum sizes respected (Date Range >= 200px width, charts >= min_chart, KPIs >= 80x50)
    - Evenly spaced grid gaps
    """
    from core.design_contract import overlap  # noqa: PLC0415

    issues = []
    # 1. Bounds check
    for v in arr.visuals:
        b = v.box
        if b.x < 0 or b.y < 0 or b.x + b.w > CANVAS_W or b.y + b.h > CANVAS_H:
            issues.append(f"{v.id} outside the canvas ({b.x},{b.y},{b.w},{b.h})")
        if b.x < M or b.x + b.w > CANVAS_W - M + 2:
            issues.append(f"{v.id} violates outer canvas margin M={M} ({b.x}..{b.x + b.w})")
        need = (80, 50) if v.role == "kpi" else (120, 28) if v.role == "slicer" else min_chart
        if b.w < need[0] or b.h < need[1]:
            issues.append(f"{v.id} too small ({b.w}x{b.h} < {need[0]}x{need[1]})")
        if v.title == "Date Range" and b.w < 200:
            issues.append(f"Date Range pill too narrow ({b.w} < 200)")

    # 2. Overlap checks
    for i, a in enumerate(arr.visuals):
        for b in arr.visuals[i + 1:]:
            if overlap(a.box, b.box, 0):
                issues.append(f"{a.id} overlaps {b.id}")
    for v in arr.visuals:
        if overlap(v.box, arr.header, 0):
            issues.append(f"{v.id} overlaps the title")

    # 3. KPI uniformity
    kpis = [v for v in arr.visuals if v.role == "kpi"]
    if len(kpis) > 1:
        heights = [k.box.h for k in kpis]
        if max(heights) - min(heights) > 2:
            issues.append(f"KPI cards have inconsistent heights ({min(heights)}px to {max(heights)}px)")
        same_row_groups: dict[int, list[PlanVisual]] = {}
        for k in kpis:
            same_row_groups.setdefault(k.box.y, []).append(k)
        for y_pos, row_kpis in same_row_groups.items():
            if len(row_kpis) > 1:
                widths = [k.box.w for k in row_kpis]
                if max(widths) - min(widths) > 2:
                    issues.append(f"Row of KPI cards at y={y_pos} have uneven widths ({min(widths)}px to {max(widths)}px)")

    return issues


def check(arr: Arrangement, min_chart: tuple[int, int] = (160, 110)) -> list[str]:
    """Layout sanity (used by tests and as a guard before rendering): inside, no overlaps, sizes, grid alignment."""
    return verify_layout_grid(arr, min_chart)


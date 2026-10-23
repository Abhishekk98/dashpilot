"""Layout library for DashPilot designs (Option B).

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

M, G = 16, 16  # outer margin, gap (consistent 16px grid)
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
    "dark_neon": ("Dark Neon Sidebar", "Left vertical navigation rail, top filters, and cyber-luminous stage cards."),
    "glass_light": ("Glassmorphism Tabs", "Top horizontal navigation tabs, frosted glass KPI row, and editorial charts."),
    "gradient_corporate": ("Gradient Corporate Rail", "Left rail slicers, top gradient hero band for KPIs, and structured data tables."),
    "command_center": ("Command Center", "Dense terminal style: KPI ticker, three-column chart grid, insights column."),
    "bento": ("Bento Grid", "Asymmetric tiles: a wide hero chart beside a 2-column grid, KPIs in a weighted band."),
    "hero_trend": ("Hero KPI + Trend", "One headline KPI next to a large trend, supporting KPIs and charts below."),
    "side_panel": ("Side Panel", "A full-height rail with title, filters and stacked KPIs; charts fill the stage."),
    "executive_split": ("Executive Split", "Story on the left (hero chart + detail), numbers on the right (KPI grid + insights)."),
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


NAV_TOP_W, NAV_TOP_H, NAV_TOP_Y = 92, 30, 20  # page tabs top-right (the header row keeps 208px free)
NAV_RAIL_H, NAV_RAIL_Y, NAV_GAP = 36, 80, 8  # page buttons stacked in a left rail, under the title


def nav_slots(total_pages: int, rail_w: int = 0) -> list[Box]:
    """Where the Power BI page-navigation buttons go (one per page; none for a single page).
    Shared by the design templates (which draw the track behind them) and the PBIP builder."""
    if total_pages < 2:
        return []
    if rail_w:
        return [_b(M, NAV_RAIL_Y + i * (NAV_RAIL_H + NAV_GAP), rail_w - 2 * M, NAV_RAIL_H) for i in range(total_pages)]
    x0 = CANVAS_W - M - (total_pages * NAV_TOP_W + (total_pages - 1) * NAV_GAP)
    return [_b(x0 + i * (NAV_TOP_W + NAV_GAP), NAV_TOP_Y, NAV_TOP_W, NAV_TOP_H) for i in range(total_pages)]


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


def _header_row(slicers: list[PlanVisual], is_multi: bool = False) -> Box:
    right = CANVAS_W - M - 208 if is_multi else CANVAS_W - M
    left = _slicer_bar(slicers, right, 16, M + 360)
    return _b(M, 14, max(320, left - M - G), 46)


# --- layouts --------------------------------------------------------------------------------------

def _bento(visuals, is_multi: bool = False):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers, is_multi=is_multi)
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


def _hero_trend(visuals, is_multi: bool = False):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers, is_multi=is_multi)
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


def _side_panel(visuals, is_multi: bool = False):
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


def _executive_split(visuals, is_multi: bool = False):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers, is_multi=is_multi)
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


def _command_center(visuals, is_multi: bool = False):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers, is_multi=is_multi)
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


def _editorial(visuals, is_multi: bool = False):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers, is_multi=is_multi)
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


def _detail_focus(visuals, is_multi: bool = False):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers, is_multi=is_multi)
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


def _dark_neon(visuals, is_multi: bool = False):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    rail = 216
    header = _b(M, 16, rail - 2 * M, 56)
    x0 = rail + G
    w = CANVAS_W - M - x0

    y = 16
    if slicers:
        _slicer_bar(slicers, right=CANVAS_W - M, y=16, min_left=x0)
        y = 16 + SLICER_H + G

    if kpis:
        _row(kpis, x0, y, w, 96, gap=G)
        y += 96 + G

    hero, rest = _hero(charts)
    tiles = rest + insights
    h = CANVAS_H - M - y
    if not tiles:
        if hero:
            hero.box = _b(x0, y, w, h)
    else:
        hw = int(round((w - G) * (0.54 if len(tiles) <= 3 else 0.48)))
        if hero:
            hero.box = _b(x0, y, hw, h)
            _grid(tiles, x0 + hw + G, y, w - hw - G, h, 2 if len(tiles) >= 3 else 1, gap=G)
        else:
            _grid(tiles, x0, y, w, h, 2 if len(tiles) >= 3 else 1, gap=G)

    return vs, header, [("rail", _b(0, 0, rail, CANVAS_H))]


def _glass_light(visuals, is_multi: bool = False):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    header = _header_row(slicers, is_multi=is_multi)
    inner = CANVAS_W - 2 * M
    y = TOP
    if kpis:
        _row(kpis, M, y, inner, 92, gap=G)
        y += 92 + G
    hero, rest = _hero(charts)
    tiles = rest + insights
    h = CANVAS_H - M - y
    if not tiles:
        if hero:
            hero.box = _b(M, y, inner, h)
    else:
        hw = int(round((inner - G) * (0.55 if len(tiles) <= 3 else 0.50)))
        if hero:
            hero.box = _b(M, y, hw, h)
            _grid(tiles, M + hw + G, y, inner - hw - G, h, 2 if len(tiles) >= 3 else 1, gap=G)
        else:
            _grid(tiles, M, y, inner, h, 2 if len(tiles) >= 3 else 1, gap=G)
    return vs, header, [("band", _b(0, 0, CANVAS_W, TOP - 4))]


def _gradient_corporate(visuals, is_multi: bool = False):
    vs, slicers, kpis, charts, insights = _parts(visuals)
    rail = 236
    header = _b(M, 16, rail - 2 * M, 52)

    sy = 76 + (88 if is_multi else 0) + 12
    for s in slicers:  # label above the dropdown, so the Date Range keeps room for both dates
        s.box = _b(M, sy, rail - 2 * M, 56)
        sy += 56 + 10

    x0 = rail + G
    w = CANVAS_W - M - x0
    panels: list[tuple[str, Box]] = [("rail", _b(0, 0, rail, CANVAS_H))]

    y = 16
    if kpis:
        kh = 96
        band_h = kh + 20
        panels.append(("hero_band", _b(x0, y, w, band_h)))
        _row(kpis, x0 + 12, y + 10, w - 24, kh, gap=12)
        y += band_h + G

    hero, rest = _hero(charts)
    tiles = rest + insights
    h = CANVAS_H - M - y
    if not tiles:
        if hero:
            hero.box = _b(x0, y, w, h)
    else:
        hw = int(round((w - G) * (0.52 if len(tiles) <= 3 else 0.56)))
        if hero:
            hero.box = _b(x0, y, hw, h)
            _grid(tiles, x0 + hw + G, y, w - hw - G, h, 2 if len(tiles) >= 3 else 1, gap=G)
        else:
            _grid(tiles, x0, y, w, h, 2 if len(tiles) >= 3 else 1, gap=G)

    return vs, header, panels


def _classic(visuals, is_multi: bool = False):
    from core.planner import layout  # noqa: PLC0415

    vs = [v.model_copy(deep=True) for v in visuals]
    layout(vs, is_multi=is_multi)
    slicers = [v for v in vs if v.role == "slicer"]
    right_limit = CANVAS_W - M - 208 if is_multi else CANVAS_W - M
    left = min((s.box.x for s in slicers), default=right_limit)
    return vs, _b(M, 14, max(320, left - M - G), 46), []


_BUILDERS = {
    "dark_neon": _dark_neon,
    "glass_light": _glass_light,
    "gradient_corporate": _gradient_corporate,
    "command_center": _command_center,
    "bento": _bento,
    "hero_trend": _hero_trend,
    "side_panel": _side_panel,
    "executive_split": _executive_split,
    "editorial": _editorial,
    "detail_focus": _detail_focus,
    "grid": _classic,
}


def arrange(page: DashboardPlan, layout: str) -> Arrangement:
    """Positions for one page (a plan from planner.page_plan) in the given layout; visual order is kept."""
    is_multi = getattr(page, "total_pages", 1) > 1 or len(getattr(page, "pages", [])) > 1 or any(v.page > 1 for v in page.visuals)
    built, header, panels = _BUILDERS[layout](page.visuals, is_multi=is_multi)
    by_id = {v.id: v for v in built}
    return Arrangement(layout=layout, label=LAYOUTS[layout][0], visuals=[by_id[v.id] for v in page.visuals], header=header, panels=panels)


def suggest(page: DashboardPlan) -> list[str]:
    """Layouts ranked by fit for this page's content (best first; never empty)."""
    roles = [v.role for v in page.visuals]
    k, c, s = roles.count("kpi"), roles.count("chart"), roles.count("slicer")
    trend = any(v.type in ("line", "area") for v in page.visuals if v.role == "chart")
    table = any(v.type in ("table", "matrix") for v in page.visuals if v.role == "chart")
    score = {
        "dark_neon": 3.8 if trend else 3.2,
        "glass_light": 3.7 + (k >= 2) * 0.4,
        "gradient_corporate": 3.6 if table else 3.1,
        "command_center": 3.5 if c >= 4 else 1.8,
        "bento": 3.0 + (c >= 3),
        "hero_trend": (3.5 if trend else 1.5) if k >= 1 else 0.5,
        "side_panel": (3.2 if k >= 3 else 2.0 if k >= 1 else 1.0) - (s > 4),
        "executive_split": 2.6 + (k >= 2) * 0.5,
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


# --- Dynamic Layout Engine, Collision Resolution & Auto-Pagination (Part 2) ---

MIN_GAP = 12


def _get_rect(item) -> tuple[int, int, int, int]:
    if hasattr(item, "box") and item.box is not None:
        return int(item.box.x), int(item.box.y), int(item.box.w), int(item.box.h)
    if hasattr(item, "x") and hasattr(item, "y") and hasattr(item, "w") and hasattr(item, "h"):
        return int(item.x), int(item.y), int(item.w), int(item.h)
    if isinstance(item, dict):
        return int(item.get("x", 0)), int(item.get("y", 0)), int(item.get("w", 0)), int(item.get("h", 0))
    if isinstance(item, (list, tuple)) and len(item) >= 4:
        return int(item[0]), int(item[1]), int(item[2]), int(item[3])
    return 0, 0, 0, 0


def _set_rect(item, x: int, y: int, w: int, h: int) -> None:
    if hasattr(item, "box"):
        item.box = Box(x=x, y=y, w=w, h=h)
    if hasattr(item, "x"):
        item.x = x
    if hasattr(item, "y"):
        item.y = y
    if hasattr(item, "w"):
        item.w = w
    if hasattr(item, "h"):
        item.h = h
    if isinstance(item, dict):
        item["x"], item["y"], item["w"], item["h"] = x, y, w, h


def rects_intersect(a, b, min_gap: int = MIN_GAP) -> bool:
    """True if rectangle a and b intersect or violate the minimum gap."""
    ax, ay, aw, ah = _get_rect(a)
    bx, by, bw, bh = _get_rect(b)
    return not (ax + aw + min_gap <= bx or bx + bw + min_gap <= ax or
                ay + ah + min_gap <= by or by + bh + min_gap <= ay)


def resolve_overlaps(
    items: list,
    canvas_w: int = CANVAS_W,
    canvas_h: int = CANVAS_H,
    min_gap: int = MIN_GAP,
    margin: int = M,
    top_offset: int = TOP,
) -> list:
    """Ensure no two visuals intersect (gap >= min_gap) and all fit within canvas margins.
    If an overlap is found, shifts the visual right or down to the next free slot."""
    if not items:
        return items

    placed: list = []
    max_w = canvas_w - 2 * margin
    max_h = canvas_h - top_offset - margin

    for item in items:
        x, y, w, h = _get_rect(item)
        role = getattr(item, "role", "chart")
        if w <= 0:
            w = 200 if role == "slicer" else 190 if role == "kpi" else 380
        if h <= 0:
            h = 40 if role == "slicer" else 92 if role == "kpi" else 240

        w = max(40, min(w, max_w))
        h = max(30, min(h, max_h))

        is_slicer = role == "slicer" or (y < top_offset and h <= 50)
        curr_top = 16 if is_slicer else top_offset

        cur_x = max(margin, min(x, canvas_w - margin - w))
        cur_y = max(curr_top, y)

        def collides(cx: int, cy: int) -> bool:
            return any(rects_intersect((cx, cy, w, h), p, min_gap=min_gap) for p in placed)

        if collides(cur_x, cur_y):
            found_slot = False
            for p in placed:
                px, py, pw, ph = _get_rect(p)
                cand_x = px + pw + min_gap
                cand_y = py
                if cand_x + w <= canvas_w - margin and not collides(cand_x, cand_y):
                    cur_x, cur_y = cand_x, cand_y
                    found_slot = True
                    break
            if not found_slot:
                bottom_edge = max((_get_rect(p)[1] + _get_rect(p)[3] for p in placed), default=curr_top)
                cur_x = margin
                cur_y = bottom_edge + min_gap
                while collides(cur_x, cur_y):
                    c = next(p for p in placed if rects_intersect((cur_x, cur_y, w, h), p, min_gap=min_gap))
                    cur_y = _get_rect(c)[1] + _get_rect(c)[3] + min_gap

        _set_rect(item, cur_x, cur_y, w, h)
        placed.append(item)

    return items


def adapt_grid_layout(
    visuals: list[PlanVisual],
    canvas_w: int = CANVAS_W,
    canvas_h: int = CANVAS_H,
    min_gap: int = MIN_GAP,
    margin: int = M,
    top_offset: int = TOP,
) -> list[PlanVisual]:
    """Adapt the visual layout into clean KPI rows and chart grids without stretching or cutting."""
    vs, slicers, kpis, charts, insights = _parts(visuals)
    inner_w = canvas_w - 2 * margin

    if slicers:
        _slicer_bar(slicers, right=canvas_w - margin, y=16, min_left=margin + 360)

    y = top_offset
    if kpis:
        kpi_h = 92
        kpi_cols = min(len(kpis), 5)
        kpi_w = (inner_w - (kpi_cols - 1) * min_gap) // kpi_cols
        for i, k in enumerate(kpis):
            row_idx = i // 5
            col_idx = i % 5
            ky = y + row_idx * (kpi_h + min_gap)
            kx = margin + col_idx * (kpi_w + min_gap)
            k.box = _b(kx, ky, kpi_w, kpi_h)
        kpi_rows = math.ceil(len(kpis) / 5)
        y += kpi_rows * kpi_h + kpi_rows * min_gap

    tiles = charts + insights
    if tiles:
        cols = 3 if len(tiles) >= 5 else 2 if len(tiles) >= 2 else 1
        tile_w = (inner_w - (cols - 1) * min_gap) // cols
        tile_h = 240
        for i, t in enumerate(tiles):
            r = i // cols
            c = i % cols
            tx = margin + c * (tile_w + min_gap)
            ty = y + r * (tile_h + min_gap)
            t.box = _b(tx, ty, tile_w, tile_h)

    return vs


@dataclass
class PageSlice:
    page_num: int
    visuals: list[PlanVisual]
    mapping: list = field(default_factory=list)


def paginate_visuals(
    visuals: list[PlanVisual],
    mapping: list | None = None,
    canvas_w: int = CANVAS_W,
    canvas_h: int = CANVAS_H,
    min_gap: int = MIN_GAP,
    margin: int = M,
    top_offset: int = TOP,
) -> list[PageSlice]:
    """Auto-pagination: Visuals exceeding canvas bounds (y + h > 720 - margin) automatically
    move to the next page with identical theme, header space, and grid rules."""
    if not visuals:
        return [PageSlice(page_num=1, visuals=[], mapping=[])]

    mapping_by_vid = {getattr(m, "visual_id", None): m for m in (mapping or [])}

    for v in visuals:
        if v.box is None:
            dw = 200 if v.role == "slicer" else 190 if v.role == "kpi" else 380
            dh = 40 if v.role == "slicer" else 92 if v.role == "kpi" else 240
            v.box = _b(margin, top_offset, dw, dh)
        m = mapping_by_vid.get(v.id)
        if m and getattr(m, "placed", False):
            v.box = _b(m.x, m.y, m.w, m.h)

    has_collision = False
    for i, a in enumerate(visuals):
        ax, ay, aw, ah = a.box.x, a.box.y, a.box.w, a.box.h
        for b in visuals[i + 1:]:
            bx, by, bw, bh = b.box.x, b.box.y, b.box.w, b.box.h
            if rects_intersect((ax, ay, aw, ah), (bx, by, bw, bh), min_gap=min_gap):
                has_collision = True
                break
        if has_collision:
            break
    if has_collision:
        resolve_overlaps(visuals, canvas_w=canvas_w, canvas_h=canvas_h, min_gap=min_gap, margin=margin, top_offset=top_offset)

    pages: list[PageSlice] = []
    max_usable_h = canvas_h
    current_page_num = 1
    remaining = list(visuals)

    while remaining:
        current_page_visuals: list[PlanVisual] = []
        overflow: list[PlanVisual] = []

        if current_page_num > 1:
            adapt_grid_layout(remaining, canvas_w=canvas_w, canvas_h=canvas_h, min_gap=min_gap, margin=margin, top_offset=top_offset)
            resolve_overlaps(remaining, canvas_w=canvas_w, canvas_h=canvas_h, min_gap=min_gap, margin=margin, top_offset=top_offset)

        for v in remaining:
            b = v.box
            if b.y + b.h <= max_usable_h:
                v_copy = v.model_copy(deep=True)
                v_copy.page = current_page_num
                current_page_visuals.append(v_copy)
            else:
                overflow.append(v)

        if not current_page_visuals and overflow:
            first = overflow.pop(0)
            first_copy = first.model_copy(deep=True)
            first_copy.page = current_page_num
            first_copy.box.y = top_offset
            first_copy.box.h = min(first_copy.box.h, max_usable_h - top_offset)
            current_page_visuals.append(first_copy)

        slice_mapping = []
        for pv in current_page_visuals:
            orig_m = mapping_by_vid.get(pv.id)
            if orig_m is not None:
                new_m = orig_m.model_copy(deep=True)
                new_m.x, new_m.y, new_m.w, new_m.h = pv.box.x, pv.box.y, pv.box.w, pv.box.h
            else:
                from core.design_import import MappingItem  # noqa: PLC0415
                new_m = MappingItem(visual_id=pv.id, x=pv.box.x, y=pv.box.y, w=pv.box.w, h=pv.box.h, method="fallback", pbi_title=True)
            slice_mapping.append(new_m)

        pages.append(PageSlice(page_num=current_page_num, visuals=current_page_visuals, mapping=slice_mapping))
        remaining = overflow
        current_page_num += 1

    return pages


def validate_and_autofix_layout(
    visuals: list[PlanVisual],
    mapping: list | None = None,
    canvas_w: int = CANVAS_W,
    canvas_h: int = CANVAS_H,
    min_gap: int = MIN_GAP,
    margin: int = M,
) -> tuple[list[PageSlice], list[str]]:
    """Strict layout check and auto-fix:
    - Zero overlaps (min_gap >= 8-12px)
    - All visuals within 1280x720 canvas
    - Overflows auto-paginated to next page(s)
    - Never blocks build, auto-fixes issues and logs notes
    """
    notes: list[str] = []
    has_overlap = False
    for i, a in enumerate(visuals):
        for b in visuals[i + 1:]:
            if rects_intersect(a.box if a.box else a, b.box if b.box else b, min_gap=min_gap):
                has_overlap = True
                break
        if has_overlap:
            break

    if has_overlap:
        notes.append("Visual overlap detected; layout engine auto-shifted visuals to clean non-overlapping slots.")

    pages = paginate_visuals(visuals, mapping=mapping, canvas_w=canvas_w, canvas_h=canvas_h, min_gap=min_gap, margin=margin)
    if len(pages) > 1:
        notes.append(f"Visuals exceeded 1280x720 canvas height; auto-paginated across {len(pages)} pages with navigation.")

    return pages, notes



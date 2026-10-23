from core.design_layouts import LAYOUTS, arrange, check, verify_layout_grid
from core.planner import Box, DashboardPlan, PlanVisual


def _make_plan(kpi_count: int = 5, slicer_count: int = 3, chart_count: int = 4) -> DashboardPlan:
    visuals = []
    # Slicers
    visuals.append(PlanVisual(id="slicer_date", role="slicer", type="slicer", title="Date Range", dimension="Dim_Date[Date]"))
    for s in range(1, slicer_count):
        visuals.append(PlanVisual(id=f"slicer_{s}", role="slicer", type="slicer", title=f"Filter {s}", dimension=f"Table[Col{s}]"))

    # KPIs
    for k in range(1, kpi_count + 1):
        visuals.append(PlanVisual(id=f"kpi_{k}", role="kpi", type="card", title=f"KPI Metric {k}", measures=[f"Measure_{k}"]))

    # Charts
    for c in range(1, chart_count + 1):
        vtype = "area" if c == 1 else "clustered_bar"
        visuals.append(PlanVisual(id=f"chart_{c}", role="chart", type=vtype, title=f"Chart Visual {c}", measures=[f"Measure_{c}"], dimension="Dim_Date[Year Month]" if c == 1 else f"Table[Dim_{c}]"))

    # Insights
    visuals.append(PlanVisual(id="insights_box", role="insights", type="text_box", title="Key Insights", text=["Insight line 1", "Insight line 2", "Insight line 3"]))

    return DashboardPlan(
        title="Test Performance Dashboard",
        subtitle="Automated Layout Verification",
        visuals=visuals,
    )


def test_all_layouts_grid_snap_and_uniformity():
    """Verify that all 8 layouts satisfy strict grid alignment, snap, uniform KPIs, and zero overlap."""
    for layout_name in LAYOUTS:
        for kpis in (1, 3, 5):
            for slicers in (1, 2, 3):
                plan = _make_plan(kpi_count=kpis, slicer_count=slicers, chart_count=3)
                arr = arrange(plan, layout_name)
                issues = verify_layout_grid(arr)
                assert not issues, f"Layout '{layout_name}' with {kpis} KPIs and {slicers} slicers had grid issues: {issues}"


def test_kpi_cards_sufficient_height():
    """Verify that KPI cards in all layouts have at least 80px height so values and labels never clip."""
    plan = _make_plan(kpi_count=5, slicer_count=3, chart_count=4)
    for layout_name in LAYOUTS:
        arr = arrange(plan, layout_name)
        kpis = [v for v in arr.visuals if v.role == "kpi"]
        assert kpis, f"No KPIs placed in {layout_name}"
        for k in kpis:
            assert k.box.h >= 80, f"KPI {k.id} in '{layout_name}' height {k.box.h} is < 80px"


def test_verify_layout_grid_catches_overflow_and_overlap():
    """Verify that verify_layout_grid properly catches corrupted/overlapping positions."""
    plan = _make_plan(kpi_count=2, slicer_count=1, chart_count=2)
    arr = arrange(plan, "bento")

    # Clean layout passes
    assert check(arr) == []

    # Corrupt a visual to overflow
    bad_overflow = arrange(plan, "bento")
    bad_overflow.visuals[0].box.x = 1260
    assert any("violates outer canvas margin" in s or "outside the canvas" in s for s in check(bad_overflow))

    # Corrupt visuals to overlap
    bad_overlap = arrange(plan, "bento")
    bad_overlap.visuals[1].box = bad_overlap.visuals[0].box
    assert any("overlaps" in s for s in check(bad_overlap))


def test_nav_slots_fit_the_header_or_the_rail():
    from core.design_layouts import arrange as _arrange, nav_slots  # noqa: PLC0415

    assert nav_slots(1) == []
    top = nav_slots(2)
    assert [(s.y, s.w, s.h) for s in top] == [(20, 92, 30)] * 2 and top[-1].x + top[-1].w == 1280 - 16
    rail = nav_slots(2, rail_w=216)
    assert all(s.x == 16 and s.x + s.w == 216 - 16 for s in rail) and rail[1].y > rail[0].y + rail[0].h
    # Rail layouts keep the nav slots free of cards; top layouts keep them clear of the slicers.
    plan = _make_plan().model_copy(update={"total_pages": 2})
    for name, slots in (("dark_neon", rail), ("gradient_corporate", nav_slots(2, rail_w=236)), ("glass_light", top), ("command_center", top)):
        arr = _arrange(plan, name)
        for v in arr.visuals:
            assert not any(v.box.x < s.x + s.w and s.x < v.box.x + v.box.w and v.box.y < s.y + s.h and s.y < v.box.y + v.box.h for s in slots), (name, v.id)


# --- Tests for Part 2: Collision resolution, No overlap, Auto-pagination (3, 8, 15 visuals) ---

def test_layout_engine_3_visuals_no_overlap_in_bounds():
    """3 visuals case: 0 overlap, gap >= 12px, all within 1280x720 canvas, 1 page."""
    from core.design_layouts import paginate_visuals, rects_intersect

    visuals = [
        PlanVisual(id="kpi_1", role="kpi", type="card", title="Revenue", box=Box(x=16, y=72, w=200, h=92)),
        PlanVisual(id="chart_1", role="chart", type="line", title="Daily Trend", box=Box(x=16, y=176, w=600, h=240)),
        PlanVisual(id="chart_2", role="chart", type="clustered_bar", title="Top Products", box=Box(x=628, y=176, w=600, h=240)),
    ]
    pages = paginate_visuals(visuals)
    assert len(pages) == 1
    p1 = pages[0].visuals
    assert len(p1) == 3

    # Check bounds
    for v in p1:
        b = v.box
        assert b.x >= 0 and b.y >= 0, f"{v.id} negative coords ({b.x}, {b.y})"
        assert b.x + b.w <= 1280, f"{v.id} exceeds canvas width ({b.x + b.w} > 1280)"
        assert b.y + b.h <= 720, f"{v.id} exceeds canvas height ({b.y + b.h} > 720)"

    # Check zero overlap with gap >= 12px
    for i, a in enumerate(p1):
        for b in p1[i + 1:]:
            assert not rects_intersect(a.box, b.box, min_gap=12), f"{a.id} overlaps {b.id}"


def test_layout_engine_8_visuals_no_overlap_in_bounds():
    """8 visuals case: 4 KPIs + 4 charts, all overlapping initially, auto-resolved with zero overlap."""
    from core.design_layouts import paginate_visuals, rects_intersect

    visuals = []
    # Intentionally start with overlapping/identical coordinates
    for k in range(1, 5):
        visuals.append(PlanVisual(id=f"kpi_{k}", role="kpi", type="card", title=f"KPI {k}", box=Box(x=16, y=72, w=220, h=92)))
    for c in range(1, 5):
        visuals.append(PlanVisual(id=f"chart_{c}", role="chart", type="clustered_bar", title=f"Chart {c}", box=Box(x=16, y=176, w=600, h=240)))

    pages = paginate_visuals(visuals)
    assert len(pages) == 1
    p1 = pages[0].visuals
    assert len(p1) == 8

    # Check bounds
    for v in p1:
        b = v.box
        assert b.x >= 0 and b.y >= 0, f"{v.id} negative coords ({b.x}, {b.y})"
        assert b.x + b.w <= 1280, f"{v.id} exceeds canvas width ({b.x + b.w} > 1280)"
        assert b.y + b.h <= 720, f"{v.id} exceeds canvas height ({b.y + b.h} > 720)"

    # Check zero overlap for all pairs
    for i, a in enumerate(p1):
        for b in p1[i + 1:]:
            assert not rects_intersect(a.box, b.box, min_gap=12), f"{a.id} overlaps {b.id}"


def test_layout_engine_15_visuals_auto_pagination_and_no_overlap():
    """15 visuals case: 5 KPIs + 9 charts + 1 insights box. Exceeds 720px, overflows to next page."""
    from core.design_layouts import paginate_visuals, rects_intersect

    visuals = []
    # 5 KPIs
    for k in range(1, 6):
        visuals.append(PlanVisual(id=f"kpi_{k}", role="kpi", type="card", title=f"KPI {k}", box=Box(x=16, y=72, w=220, h=92)))
    # 9 charts
    for c in range(1, 10):
        visuals.append(PlanVisual(id=f"chart_{c}", role="chart", type="clustered_bar", title=f"Chart {c}", box=Box(x=16, y=176, w=600, h=240)))
    # 1 insights box
    visuals.append(PlanVisual(id="insights_1", role="insights", type="text_box", title="Key Insights", box=Box(x=16, y=176, w=600, h=180)))

    assert len(visuals) == 15
    pages = paginate_visuals(visuals)

    # Overflow MUST move to next page(s)
    assert len(pages) >= 2, f"Expected at least 2 pages for 15 visuals, got {len(pages)}"

    # All 15 visuals must be accounted for
    total_preserved = sum(len(p.visuals) for p in pages)
    assert total_preserved == 15, f"Preserved {total_preserved} of 15 visuals"

    # On EVERY page: zero overlaps, all inside 1280x720 canvas
    for pg in pages:
        p_vs = pg.visuals
        for v in p_vs:
            b = v.box
            assert b.x >= 0 and b.y >= 0, f"Page {pg.page_num}: {v.id} negative ({b.x}, {b.y})"
            assert b.x + b.w <= 1280, f"Page {pg.page_num}: {v.id} width overflow ({b.x + b.w} > 1280)"
            assert b.y + b.h <= 720, f"Page {pg.page_num}: {v.id} height overflow ({b.y + b.h} > 720)"
        for i, a in enumerate(p_vs):
            for b in p_vs[i + 1:]:
                assert not rects_intersect(a.box, b.box, min_gap=12), f"Page {pg.page_num}: {a.id} overlaps {b.id}"


def test_validator_autofixes_overlap_and_out_of_bounds():
    """Validator: detects overlaps & out-of-bounds, auto-fixes them without blocking."""
    from core.design_layouts import validate_and_autofix_layout, rects_intersect

    # 4 overlapping visuals with out-of-bounds coords
    visuals = [
        PlanVisual(id="v1", role="kpi", type="card", title="KPI 1", box=Box(x=100, y=100, w=200, h=92)),
        PlanVisual(id="v2", role="kpi", type="card", title="KPI 2", box=Box(x=100, y=100, w=200, h=92)),  # identical = overlap
        PlanVisual(id="v3", role="chart", type="line", title="Chart 1", box=Box(x=1200, y=100, w=500, h=300)),  # width OOB
        PlanVisual(id="v4", role="chart", type="clustered_bar", title="Chart 2", box=Box(x=50, y=650, w=400, h=300)),  # height OOB
    ]
    pages, notes = validate_and_autofix_layout(visuals)
    assert notes  # notes logged
    assert len(pages) >= 1

    for pg in pages:
        for v in pg.visuals:
            b = v.box
            assert b.x >= 0 and b.y >= 0
            assert b.x + b.w <= 1280
            assert b.y + b.h <= 720
        for i, a in enumerate(pg.visuals):
            for b in pg.visuals[i + 1:]:
                assert not rects_intersect(a.box, b.box, min_gap=12)


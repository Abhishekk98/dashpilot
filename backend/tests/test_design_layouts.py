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

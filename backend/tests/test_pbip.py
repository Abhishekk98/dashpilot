"""PBIP builder + validator: structure, PBIR schema validity, placement, validator rules, API, fuzz."""

import io
import json
import zipfile

import pandas as pd
import pytest

from core.cleaning import SourceTable
from core.cleaning_rules import build_plan as clean_plan
from core.cleaning_rules import table_pipelines
from core.dax import GenContext, StoredMeasures
from core.dax import build_plan as build_measures
from core.dax_eval import date_frame
from core.design_import import DetectedBox, MappingItem, ThemeColor, build_theme
from core.insights import Engine, InsightPlan, compute_insights, link_questions, template_questions
from core.modelling import DATE_TABLE, ModelSettings, build_model
from core.pbip_builder import BuildInputs, PageInput, build, folder_name, page_name, visual_rect
from core.pbip_validator import validate
from core.planner import build_plan as build_dashboard
from core.planner import page_plan
from core.profiling import build_report
from core.upload import UploadError, csv_delimiter, read_tables
from tests.conftest import SAMPLES
from tests.test_cleaning_fuzz import dataset
from tests.test_planner import CTX

PALETTE = [ThemeColor(hex="#F4F1EA", role="canvas"), ThemeColor(hex="#FFFFFF", role="card"), ThemeColor(hex="#1B1C1C", role="text"),
           ThemeColor(hex="#6B6B6B", role="muted"), ThemeColor(hex="#F8CF4B", role="accent")]
INSET = [17, 37, 17, 13]


def _inputs(files: dict[str, bytes], name: str = "Shop Co", inset: list[int] | None = INSET) -> BuildInputs | None:
    sources = []
    for filename, content in files.items():
        try:
            tables = read_tables(filename, content)
        except UploadError:
            continue
        delimiter = csv_delimiter(content) if filename.endswith(".csv") else ","
        sources += [SourceTable(name=n, filename=filename, sheet=s, delimiter=delimiter, df=df) for n, (s, df) in tables.items()]
    if not sources:
        return None
    report = build_report([(s.name, "f", s.sheet, s.df) for s in sources])
    decisions = {s.id: {"status": "accepted"} for s in clean_plan(report, sources, {}).steps}
    pipelines, _ = table_pipelines(report, sources, decisions)
    cleaned = {n: (p.src, [s for s in p.accepted if not s.error], p.result) for n, p in pipelines.items()}
    model = build_model(report, cleaned, ModelSettings())
    frames = {t.name: pipelines[t.name].result.df.reset_index(drop=True) for t in model.tables if t.included}
    for t in model.tables:
        for c in t.columns:
            if t.included and c.derived:
                frames[t.name][c.name] = pd.to_datetime(frames[t.name][c.name.removesuffix("_date")], errors="coerce").dt.normalize()
    if model.date_table.enabled:
        frames[DATE_TABLE] = date_frame(model.date_table.start, model.date_table.end, 1)
    ctx = GenContext(model=model, report=report, frames=frames, industries=["Retail"])
    mplan, measures = build_measures(ctx, StoredMeasures(), False)
    if not any(m.status == "passed" for m in measures):
        return None
    engine = Engine(ctx, measures)
    found, north, dims = compute_insights(engine)
    questions = template_questions(engine, found, dims, ["Executive Leadership"])
    link_questions(questions, found)
    insights = InsightPlan(insights=found, questions=questions, north_star=north, rows_scanned=0, dimensions=[], confidence=1)
    whole = build_dashboard(f"{name} Dashboard", model, report, measures, [c.name for c in mplan.cards], insights)
    assert whole.valid, whole.issues
    pages = []
    for n in range(1, len(whole.pages) + 1):
        plan = page_plan(whole, n)
        boxes = [DetectedBox(id=f"box_{i:02d}", x=v.box.x, y=v.box.y, w=v.box.w, h=v.box.h, title=v.title, visual_id=v.id,
                             inset=([60, 4, 6, 4] if v.role == "slicer" else inset) if inset else None)
                 for i, v in enumerate(plan.visuals, 1)]
        mapping = [MappingItem(visual_id=v.id, box_id=b.id, x=b.x, y=b.y, w=b.w, h=b.h, method="id", score=1) for v, b in zip(plan.visuals, boxes)]
        pages.append(PageInput(plan=plan, boxes=boxes, mapping=mapping, background=b"\x89PNG\r\n\x1a\n" + bytes([n]) * 64))
    first = pages[0]
    return BuildInputs(
        project_name=name, model=model, cleaned={n: p.result for n, p in pipelines.items()},
        measures=[m for m in measures if m.status != "error"], plan=first.plan, boxes=first.boxes, mapping=first.mapping,
        theme=build_theme(f"DashPilot {name}", PALETTE, CTX.palette), background=first.background,
        sources=list(files.items()), data_folder="C:\\DashPilot\\Shop_Co\\Data\\", extra_pages=pages[1:],
    )


@pytest.fixture(scope="module")
def shop() -> BuildInputs:
    return _inputs({n: (SAMPLES / n).read_bytes() for n in ("orders.csv", "customers.xlsx", "products.csv")})


def _all_pbi_titles(shop: BuildInputs) -> BuildInputs:
    """Every card on every page gets its title from Power BI."""
    flip = lambda mapping: [m.model_copy(update={"pbi_title": True}) for m in mapping]  # noqa: E731
    extra = [PageInput(pg.plan, pg.boxes, flip(pg.mapping), pg.background) for pg in shop.extra_pages]
    return shop.__class__(**{**shop.__dict__, "mapping": flip(shop.mapping), "extra_pages": extra})


def _is_extra(visual: dict) -> bool:
    """KPI vs PY lines and sparklines (drawn inside a KPI card, not planned visuals)."""
    return visual["position"]["z"] >= 20000


def _visuals(files: dict[str, bytes]) -> list[dict]:
    return [json.loads(c) for p, c in files.items() if p.endswith("/visual.json")]


# --- builder -----------------------------------------------------------------------------------

def test_build_structure_and_validation(shop):
    files = build(shop)
    root = folder_name(shop.project_name)
    assert root == "Shop_Co"
    for path in (f"{root}.pbip", f"{root}.Report/definition.pbir", f"{root}.Report/.platform", f"{root}.Report/definition/report.json",
                 f"{root}.Report/definition/version.json", f"{root}.Report/definition/pages/pages.json",
                 f"{root}.Report/StaticResources/RegisteredResources/DashPilotTheme.json",
                 f"{root}.Report/StaticResources/RegisteredResources/DashPilotBackground.png",
                 f"{root}.SemanticModel/definition.pbism", f"{root}.SemanticModel/definition/model.tmdl",
                 f"{root}.SemanticModel/definition/tables/_Measures.tmdl", f"{root}.SemanticModel/definition/expressions.tmdl",
                 "Data/orders.csv", "Data/customers.xlsx", "README.md"):
        assert path in files, path
    assert any(p.startswith("Data/Cleaned/") and p.endswith(".csv") for p in files)
    checks = validate(files)
    assert all(c.status == "pass" for c in checks), [(c.id, c.issues) for c in checks if c.status != "pass"]
    assert next(c for c in checks if c.id == "schemas").count >= 20
    assert b'DataFolder = "C:\\DashPilot\\Shop_Co\\Data\\"' in files[f"{root}.SemanticModel/definition/expressions.tmdl"]
    assert b"annotation PBI_QueryOrder" in files[f"{root}.SemanticModel/definition/model.tmdl"]
    assert json.loads(files[f"{root}.Report/StaticResources/RegisteredResources/DashPilotTheme.json"]) == shop.theme
    # Two pages: Overview + Details, each with its own background; slicers synced across pages.
    order = json.loads(files[f"{root}.Report/definition/pages/pages.json"])["pageOrder"]
    assert order == [page_name(1), page_name(2)]
    second = json.loads(files[f"{root}.Report/definition/pages/{page_name(2)}/page.json"])
    assert second["displayName"] == "Details" and "DashPilotBackground_p2.png" in json.dumps(second)
    assert files[f"{root}.Report/StaticResources/RegisteredResources/DashPilotBackground_p2.png"] == shop.extra_pages[0].background
    p2 = [json.loads(c) for p, c in files.items() if f"/pages/{page_name(2)}/visuals/" in p]
    plan_p2 = [v for v in p2 if v["visual"]["visualType"] != "actionButton" and not _is_extra(v)]
    assert len(plan_p2) == len(shop.extra_pages[0].plan.visuals)
    nav_p2 = [v for v in p2 if v["visual"]["visualType"] == "actionButton"]
    assert len(nav_p2) == 2
    synced = [v["visual"]["syncGroup"]["groupName"] for v in _visuals(files) if v["visual"]["visualType"] == "slicer"]
    assert len(synced) == 2 * len(set(synced))  # one group per slicer, on both pages


def test_visuals_follow_plan_and_mapping(shop):
    files = build(shop)
    visuals = {v["name"]: v for v in _visuals(files)}
    plan_visuals = {k: v for k, v in visuals.items() if v["visual"]["visualType"] != "actionButton" and not _is_extra(v)}
    assert len(plan_visuals) == sum(len(pg.plan.visuals) for pg in shop.pages)
    nav_visuals = {k: v for k, v in visuals.items() if v["visual"]["visualType"] == "actionButton"}
    assert len(nav_visuals) == len(shop.pages) * len(shop.pages)
    by_plan = {v.id: v for v in shop.plan.visuals}
    for data in visuals.values():
        assert "active" not in json.dumps(data["visual"].get("query", {}))  # collapses tables in Power BI
        bg = data["visual"]["visualContainerObjects"]["background"][0]["properties"]["show"]["expr"]["Literal"]["Value"]
        assert bg == "false"
    table = next(v for v in visuals.values() if v["visual"]["visualType"] == "tableEx")
    plan_table = next(v for pg in shop.pages for v in pg.plan.visuals if v.type == "table")
    assert len(table["visual"]["query"]["queryState"]["Values"]["projections"]) == 1 + len(plan_table.measures)
    text = next(v for v in visuals.values() if v["visual"]["visualType"] == "textbox")
    runs = json.dumps(text["visual"]["objects"]["general"])
    insights = next(v for v in shop.plan.visuals if v.role == "insights")
    assert all(line.split(",")[0] in runs for line in insights.text)
    date_slicer = next(v for v in visuals.values() if v["visual"]["visualType"] == "slicer"
                       and "Dim_Date" in json.dumps(v["visual"]["query"]))
    assert date_slicer["visual"]["objects"]["data"][0]["properties"]["mode"]["expr"]["Literal"]["Value"] == "'Between'"
    trend = next(v for v in visuals.values() if v["visual"]["visualType"] in ("lineChart", "areaChart"))
    assert trend["visual"]["query"]["sortDefinition"]["sort"][0]["direction"] == "Ascending"
    # Visuals sit in the card's content area, under the design title.
    kpi_plan = next(v for v in shop.plan.visuals if v.role == "kpi")
    kpi_item = next(m for m in shop.mapping if m.visual_id == kpi_plan.id)
    kpi_box = next(b for b in shop.boxes if b.id == kpi_item.box_id)
    assert visual_rect(kpi_plan, kpi_item, kpi_box) == (kpi_item.x + 17, kpi_item.y + 37, kpi_item.w - 34, kpi_item.h - 50)
    del by_plan


def test_power_bi_title_when_slot_shows_another_title(shop):
    inputs = _all_pbi_titles(shop)
    visuals = _visuals(build(inputs))
    chart = next(v for v in visuals if v["visual"]["visualType"] == "clusteredBarChart")
    props = chart["visual"]["visualContainerObjects"]["title"][0]["properties"]
    assert props["show"]["expr"]["Literal"]["Value"] == "true" and "text" in props
    card = next(v for v in visuals if v["visual"]["visualType"] == "card")
    assert card["visual"]["objects"]["categoryLabels"][0]["properties"]["show"]["expr"]["Literal"]["Value"] == "true"
    assert all(c.status == "pass" for c in validate(build(inputs)))


def test_m_reads_excel_serial_dates_and_day_first_text():
    from core.cleaning import _M_FUNCTIONS  # noqa: PLC0415
    fn = _M_FUNCTIONS["fnDateTime"]
    assert "v is number then (if v >= 1 and v < 2958466 then DateTime.From(v)" in fn
    assert '"en-GB"' in fn and "otherwise try DateTime.From(t" in fn


# --- validator ------------------------------------------------------------------------------------

def test_validator_catches_broken_files(shop):
    files = dict(build(shop))
    root = folder_name(shop.project_name)
    page = next(p for p in files if p.endswith("/page.json"))
    data = json.loads(files[page])
    del data["displayOption"]
    files[page] = json.dumps(data).encode()

    measures = f"{root}.SemanticModel/definition/tables/_Measures.tmdl"
    text = files[measures].decode()
    text = text.replace("\tmeasure ", "    measure ", 1)  # spaces instead of tabs
    first = next(line for line in text.splitlines() if line.startswith("\tmeasure") and " = " in line)
    text = text.replace(first, first + " + (1", 1)  # unbalanced bracket
    text = text.replace("\tmeasure 'Units Sold' =", "\tmeasure 'Units Sold' = [Ghost Measure] +", 1)
    files[measures] = text.encode()

    visual_paths = [p for p in files if p.endswith("/visual.json")]
    a, b = (json.loads(files[p]) for p in visual_paths[3:5])
    b["position"].update(x=a["position"]["x"], y=a["position"]["y"])
    files[visual_paths[4]] = json.dumps(b).encode()
    c = json.loads(files[visual_paths[6]])
    c["visual"]["query"]["queryState"].setdefault("Y", {"projections": []})["projections"].append(
        {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": "No Such Measure"}},
         "queryRef": "_Measures.No Such Measure", "nativeQueryRef": "No Such Measure"})
    files[visual_paths[6]] = json.dumps(c).encode()
    del files[f"{root}.Report/StaticResources/RegisteredResources/DashPilotBackground.png"]

    checks = {c.id: c for c in validate(files)}
    assert checks["schemas"].status == "fail" and "displayOption" in " ".join(checks["schemas"].issues)
    assert checks["tmdl"].status == "fail"
    assert any("tabs" in i for i in checks["tmdl"].issues) and any("expression has" in i for i in checks["tmdl"].issues)
    assert checks["dax"].status == "fail" and "Ghost Measure" in " ".join(checks["dax"].issues)
    assert checks["fields"].status == "fail" and "No Such Measure" in " ".join(checks["fields"].issues)
    assert checks["layout"].status == "fail" and "overlap" in " ".join(checks["layout"].issues)
    assert checks["resources"].status == "fail" and "DashPilotBackground.png" in " ".join(checks["resources"].issues)


def test_validator_requires_datafolder_paths(shop):
    files = dict(build(shop))
    root = folder_name(shop.project_name)
    table = next(p for p in files if "/tables/" in p and b"DataFolder &" in files[p])
    text = files[table].decode()
    files[table] = text.replace("DataFolder & ", '"C:\\DashPilot\\Shop_Co\\Data\\" & ', 1).encode()
    check = next(c for c in validate(files) if c.id == "data_paths")
    assert check.status == "fail" and any("absolute path" in i for i in check.issues)
    assert any("does not start with DataFolder" in i for i in check.issues)

    files = dict(build(shop))
    del files["Data/orders.csv"]
    check = next(c for c in validate(files) if c.id == "data_paths")
    assert check.status == "fail" and "orders.csv" in " ".join(check.issues)
    good = next(c for c in validate(build(shop)) if c.id == "data_paths")
    assert good.status == "pass" and good.count >= 2
    assert root


def test_slicers_show_friendly_titles(shop):
    inputs = _all_pbi_titles(shop)
    for files, header in ((build(shop), False), (build(inputs), True)):
        plan = {v.title: v for v in shop.plan.visuals if v.role == "slicer"}
        slicers = [v for v in _visuals(files) if v["visual"]["visualType"] == "slicer"]
        assert slicers and len(slicers) == len(plan) * len(shop.pages)  # every page has the slicers
        for s in slicers:
            proj = next(iter(s["visual"]["query"]["queryState"].values()))["projections"][0]
            assert proj["displayName"] in plan  # "Payment Channel", not payment_channel
            props = s["visual"]["objects"]["header"][0]["properties"]
            assert props["show"]["expr"]["Literal"]["Value"] == ("true" if header else "false")
            if header:
                assert props["text"]["expr"]["Literal"]["Value"] == f"'{proj['displayName']}'"


def test_open_dashboard_cmd_sets_datafolder_anywhere(shop, tmp_path):
    import os  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    from core.pbip_open import OPEN_CMD_NAME  # noqa: PLC0415
    files = build(shop)
    root = folder_name(shop.project_name)
    cmd = files[OPEN_CMD_NAME]
    assert cmd.decode("ascii").count("\r\n") == cmd.count(b"\n")  # CRLF for cmd.exe
    assert OPEN_CMD_NAME in files["README.md"].decode() and "Edit parameters → DataFolder" in files["README.md"].decode()
    if sys.platform != "win32":
        pytest.skip("Open Dashboard.cmd runs on Windows")
    folder = tmp_path / "My Reports & Co ü डैश" / root  # spaces, &, unicode
    for path, content in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(content)
    expressions = folder / f"{root}.SemanticModel" / "definition" / "expressions.tmdl"
    env = {**os.environ, "DP_NO_LAUNCH": "1"}
    for _ in range(2):  # idempotent
        run = subprocess.run(f'cmd /c ""{folder / OPEN_CMD_NAME}""', env=env, capture_output=True, timeout=60)  # as Explorer runs it
        assert run.returncode == 0, run.stdout + run.stderr
        text = expressions.read_text(encoding="utf-8")
        assert text.splitlines()[0].startswith(f'expression DataFolder = "{folder}\\Data\\" meta [IsParameterQuery=true')
        assert not expressions.read_bytes().startswith(b"\xef\xbb\xbf")
    assert text.count("expression DataFolder") == 1


def test_save_copy_points_datafolder_at_target(shop, tmp_path):
    from core.pbip_open import OpenError, TargetExists, clean_target, save_copy, set_data_folder  # noqa: PLC0415
    files = build(shop)
    root = folder_name(shop.project_name)
    tree = tmp_path / "build" / root
    for path, content in files.items():
        (tree / path).parent.mkdir(parents=True, exist_ok=True)
        (tree / path).write_bytes(content)
    target = tmp_path / "Docs" / "DashPilot" / root
    pbip = save_copy(tree, root, target, overwrite=False)
    assert pbip.exists() and (target / "Data" / "orders.csv").exists()
    text = (target / f"{root}.SemanticModel" / "definition" / "expressions.tmdl").read_text(encoding="utf-8")
    assert f'DataFolder = "{target}\\Data\\"' in text
    with pytest.raises(TargetExists):
        save_copy(tree, root, target, overwrite=False)
    (target / "notes.txt").write_text("mine")
    save_copy(tree, root, target, overwrite=True)
    assert (target / "notes.txt").exists()  # only DashPilot's own folders are replaced
    other = tmp_path / "Other"
    other.mkdir()
    (other / "x.txt").write_text("x")
    with pytest.raises(OpenError, match="other files"):
        save_copy(tree, root, other, overwrite=True)
    with pytest.raises(OpenError):
        clean_target("relative\\path", root)
    assert 'DataFolder = "D:\\a ""b""\\Data\\"' in set_data_folder('expression DataFolder = "C:\\x\\" meta [IsParameterQuery=true]', 'D:\\a "b"\\Data')


def test_map_visuals_warn(shop):
    plan = shop.plan.model_copy(deep=True)
    chart = next(v for v in plan.visuals if v.type == "clustered_bar")
    chart.type = "map"
    inputs = shop.__class__(**{**shop.__dict__, "plan": plan})
    layout = next(c for c in validate(build(inputs)) if c.id == "layout")
    assert layout.status == "warn" and "Azure Maps" in layout.issues[0]


# --- API --------------------------------------------------------------------------------------------

def test_build_api_flow(api, sample_bytes, monkeypatch, tmp_path):
    from tests.test_design_import import _browser, _designed  # noqa: PLC0415
    if not _browser():
        pytest.skip("needs Playwright with Edge/Chrome for the design import")
    pid = api.post("/api/projects", json={"name": "Empty"}).json()["id"]
    status = api.get(f"/api/projects/{pid}/build").json()
    assert not status["ready"] and status["blockers"]
    assert api.post(f"/api/projects/{pid}/build", json={}).status_code == 422

    pid = _designed(api, sample_bytes)
    assert api.get(f"/api/projects/{pid}/design/import").json()["design"]["valid"]
    status = api.get(f"/api/projects/{pid}/build").json()
    assert status["ready"] and status["build"] is None and status["default_data_folder"].endswith("\\Data\\")
    assert api.post(f"/api/projects/{pid}/build", json={"data_folder": 'C:\\bad"path'}).status_code == 422
    assert api.get(f"/api/projects/{pid}/build/download").status_code == 409  # nothing built yet

    res = api.post(f"/api/projects/{pid}/build", json={"data_folder": "D:\\Reports\\Shop"})
    assert res.status_code == 200, res.text
    b = res.json()["build"]
    whole = api.get(f"/api/projects/{pid}/plan").json()["plan"]
    slicers = sum(v["role"] == "slicer" for v in whole["visuals"])
    p_count = len(whole["pages"])
    nav_buttons = p_count * p_count if p_count > 1 else 0
    kpi_extras = 2 * sum(v["role"] == "kpi" for v in whole["visuals"])  # vs PY line + sparkline per KPI card
    assert b["valid"] and b["data_folder"] == "D:\\Reports\\Shop\\"
    assert b["visuals"] == len(whole["visuals"]) + slicers * (p_count - 1) + nav_buttons + kpi_extras
    assert {c["status"] for c in b["checks"]} == {"pass"}, [(c["id"], c.get("issues")) for c in b["checks"] if c["status"] != "pass"]
    z = api.get(f"/api/projects/{pid}/build/download")
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert f"{b['folder']}/{b['folder']}.pbip" in names and any(n.endswith("/visual.json") for n in names)
    assert f"{b['folder']}/Open Dashboard.cmd" in names

    # Save & Open in Power BI: local copy with DataFolder pointing at it, then the launcher.
    from core import pbip_service  # noqa: PLC0415
    launched = []
    monkeypatch.setattr(pbip_service, "launch", launched.append)
    assert api.get(f"/api/projects/{pid}/build").json()["open_folder"].endswith(f"DashPilot\\{b['folder']}")
    target = tmp_path / "Saved Dash"
    res = api.post(f"/api/projects/{pid}/build/open", json={"folder": str(target)})
    assert res.status_code == 200, res.text
    assert res.json()["launched"] and launched == [target / f"{b['folder']}.pbip"]
    assert f'"{target}\\Data\\"' in (target / f"{b['folder']}.SemanticModel/definition/expressions.tmdl").read_text(encoding="utf-8")
    assert api.post(f"/api/projects/{pid}/build/open", json={"folder": str(target)}).status_code == 409
    assert api.post(f"/api/projects/{pid}/build/open", json={"folder": str(target), "overwrite": True}).status_code == 200
    assert api.post(f"/api/projects/{pid}/build/open", json={"folder": "not\\absolute"}).status_code == 422

    # Editing the plan makes the build stale (the mapping follows on the next import).
    plan = api.get(f"/api/projects/{pid}/plan").json()["plan"]
    visuals = [{k: v[k] for k in ("role", "type", "title", "measures", "dimension", "sort", "purpose", "question_id", "text", "page")} for v in plan["visuals"]]
    visuals.pop(next(i for i, v in enumerate(visuals) if v["role"] == "chart"))
    api.put(f"/api/projects/{pid}/plan", json={"visuals": visuals})
    assert api.get(f"/api/projects/{pid}/build").json()["stale"]


def test_multipage_navigation_buttons(shop):
    # 1. Multi-page dashboard has 2 buttons on each page (4 total)
    files = build(shop)
    visuals = _visuals(files)
    nav_buttons = [v for v in visuals if v["visual"]["visualType"] == "actionButton"]
    assert len(nav_buttons) == 4

    p1_name, p2_name = page_name(1), page_name(2)
    p1_btns = [json.loads(c) for p, c in files.items() if f"/pages/{p1_name}/visuals/" in p and "visual.json" in p and json.loads(c)["visual"]["visualType"] == "actionButton"]
    p2_btns = [json.loads(c) for p, c in files.items() if f"/pages/{p2_name}/visuals/" in p and "visual.json" in p and json.loads(c)["visual"]["visualType"] == "actionButton"]
    assert len(p1_btns) == 2
    assert len(p2_btns) == 2

    # Check button texts
    p1_texts = {b["visual"]["objects"]["text"][0]["properties"]["text"]["expr"]["Literal"]["Value"]: b for b in p1_btns}
    assert "'Overview'" in p1_texts and "'Details'" in p1_texts

    # On page 1: Overview is active (Segoe UI Semibold, accent color), Details is inactive (Segoe UI)
    btn_ov1 = p1_texts["'Overview'"]
    btn_det1 = p1_texts["'Details'"]
    assert btn_ov1["visual"]["objects"]["text"][0]["properties"]["fontFamily"]["expr"]["Literal"]["Value"] == "'Segoe UI Semibold'"
    assert btn_det1["visual"]["objects"]["text"][0]["properties"]["fontFamily"]["expr"]["Literal"]["Value"] == "'Segoe UI'"

    # Check links
    assert btn_ov1["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]["type"]["expr"]["Literal"]["Value"] == "'PageNavigation'"
    assert btn_ov1["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]["navigationSection"]["expr"]["Literal"]["Value"] == f"'{p1_name}'"
    assert btn_det1["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]["navigationSection"]["expr"]["Literal"]["Value"] == f"'{p2_name}'"

    # On page 2: Details is active, Overview is inactive
    p2_texts = {b["visual"]["objects"]["text"][0]["properties"]["text"]["expr"]["Literal"]["Value"]: b for b in p2_btns}
    btn_ov2 = p2_texts["'Overview'"]
    btn_det2 = p2_texts["'Details'"]
    assert btn_ov2["visual"]["objects"]["text"][0]["properties"]["fontFamily"]["expr"]["Literal"]["Value"] == "'Segoe UI'"
    assert btn_det2["visual"]["objects"]["text"][0]["properties"]["fontFamily"]["expr"]["Literal"]["Value"] == "'Segoe UI Semibold'"

    # 2. Single-page dashboard generates zero actionButtons
    shop_single = shop.__class__(**{**shop.__dict__, "extra_pages": []})
    single_files = build(shop_single)
    single_navs = [v for v in _visuals(single_files) if v["visual"]["visualType"] == "actionButton"]
    assert len(single_navs) == 0

    # 3. PBIP validation passes with zero errors (schemas + layout)
    checks = validate(files)
    failures = [(c.id, c.issues) for c in checks if c.status == "fail"]
    assert not failures, f"PBIP validation failed: {failures}"

    # 4. Multi-page dashboard without nav buttons on a page fails validator
    files_no_nav = {p: c for p, c in files.items() if not (f"/pages/{p1_name}/visuals/" in p and "actionButton" in c.decode("utf-8", errors="ignore"))}
    fail_checks = validate(files_no_nav)
    layout_check = next(c for c in fail_checks if c.id == "layout")
    assert layout_check.status == "fail"
    assert any("lacks navigation buttons" in issue for issue in layout_check.issues)


# --- fuzz ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("batch", range(3))
def test_build_on_random_datasets(batch):
    ran = 0
    for seed in range(400 + batch * 8, 400 + batch * 8 + 8):
        inputs = _inputs(dataset(seed), name=f"Fuzz {seed}", inset=INSET if seed % 2 else None)
        if inputs is None:
            continue
        checks = validate(build(inputs))
        bad = [(c.id, c.issues[:3]) for c in checks if c.status == "fail"]
        assert not bad, f"seed {seed}: {bad}"
        ran += 1
    assert ran


def test_kpi_number_takes_the_design_value_color():
    from core.design_import import DetectedBox, MappingItem  # noqa: PLC0415
    from core.pbip_builder import visual_json  # noqa: PLC0415
    from core.planner import Box, PlanVisual  # noqa: PLC0415

    v = PlanVisual(id="kpi_1", role="kpi", type="card", title="Revenue", measures=["Revenue"], box=Box(x=232, y=72, w=190, h=96))
    item = MappingItem(visual_id="kpi_1", box_id="box_01", x=232, y=72, w=190, h=96, method="id")
    tokens = {"text": "#0F172A", "card": "#FFFFFF", "muted": "#64748B", "grid": "#E2E8F0", "band": "#F8FAFC",
              "accent": "#7C3AED", "value": "#0F172A", "value_font": "Segoe UI"}
    plain = DetectedBox(id="box_01", x=232, y=72, w=190, h=96, title="Revenue")
    white = plain.model_copy(update={"value_color": "#FFFFFF"})
    color = lambda box: visual_json(v, item, box, 0, tokens)["visual"]["objects"]["labels"][0]["properties"]["color"]["solid"]["color"]["expr"]["Literal"]["Value"]  # noqa: E731
    assert color(plain) == "'#0F172A'" and color(white) == "'#FFFFFF'"


def test_kpi_extras_data_bars_subtitles_and_indian_units(shop):
    from types import SimpleNamespace  # noqa: PLC0415

    from core.pbip_builder import _indian, _kpi_display_dax, kpi_delta_color_name, kpi_delta_name  # noqa: PLC0415

    files = build(shop)
    root = folder_name(shop.project_name)
    measures = files[f"{root}.SemanticModel/definition/tables/_Measures.tmdl"].decode()
    kpi = next(v for v in shop.plan.visuals if v.role == "kpi")
    assert kpi_delta_name(kpi.measures[0]) in measures and "SAMEPERIODLASTYEAR" in measures and '" MoM"' in measures
    visuals = _visuals(files)
    delta = next(v for v in visuals if _is_extra(v) and v["visual"]["visualType"] == "card")
    colour = delta["visual"]["objects"]["labels"][0]["properties"]["color"]["solid"]["color"]["expr"]
    assert colour["Measure"]["Property"] == kpi_delta_color_name(kpi.measures[0])
    spark = next(v for v in visuals if _is_extra(v) and v["visual"]["visualType"] == "areaChart")
    assert spark["visual"]["objects"]["categoryAxis"][0]["properties"]["show"]["expr"]["Literal"]["Value"] == "false"
    # The KPI value, its vs PY line and the sparkline share the card without overlapping.
    checks = validate(files)
    assert all(c.status == "pass" for c in checks), [(c.id, c.issues) for c in checks if c.status != "pass"]
    table = next(v for v in visuals if v["visual"]["visualType"] == "tableEx")
    assert "dataBars" in table["visual"]["objects"]["columnFormatting"][0]["properties"]
    bar = next(v for v in visuals if v["visual"]["visualType"] == "clusteredBarChart")
    title = bar["visual"]["visualContainerObjects"]["title"][0]["properties"]
    assert title["show"]["expr"]["Literal"]["Value"] == "true" and title["text"]["expr"]["Measure"]["Property"].endswith("(subtitle)")

    rupees = SimpleNamespace(format_string="#,##0", expression="SUM('Orders'[Item_Subtotal_INR])")
    assert _indian(rupees) and not _indian(SimpleNamespace(format_string="#,##0", expression="COUNTROWS('Orders')"))
    dax = _kpi_display_dax("GMV", "#,##0", indian=True)
    assert '"Cr"' in dax and '"L"' in dax and "₹" in dax and '"M"' not in dax

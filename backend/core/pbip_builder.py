"""Power BI Project (PBIP) builder (spec Module 11).

Writes a complete PBIP folder as {relative path: bytes}:

  {P}.pbip
  {P}.SemanticModel/   definition.pbism, .platform, definition/*.tmdl (core.tmdl, same as the Model step)
  {P}.Report/          definition.pbir, .platform, definition/ (PBIR: version, report, pages, visuals),
                       StaticResources/RegisteredResources/ (background PNG + theme JSON from Step 8)
  Data/                the uploaded files (the M partitions read them through the DataFolder parameter)
  Data/Cleaned/        the cleaned tables as CSV (what the M steps produce), for reference
  README.md            how to open

Visual JSON comes from templates/visuals/{type}.json (visualType, query roles, default formatting).
Positions come from the Step 8 mapping; each visual sits in its card's content area so the card
title drawn in the background stays visible. Format reference: Microsoft's PBIR JSON schemas
(cached in templates/pbir_schemas, checked by core.pbip_validator).
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from core.cleaning import PipelineResult
from core.dax import Measure
from core.design_import import DetectedBox, MappingItem
from core.modelling import ModelPlan
from core.planner import DashboardPlan, PlanVisual
from core import tmdl

TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "visuals"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/"
SCHEMAS = {
    "pbip": SCHEMA + "pbip/pbipProperties/1.0.0/schema.json",
    "platform": SCHEMA + "gitIntegration/platformProperties/2.0.0/schema.json",
    "pbir": SCHEMA + "item/report/definitionProperties/2.0.0/schema.json",
    "pbism": SCHEMA + "item/semanticModel/definitionProperties/1.0.0/schema.json",
    "version": SCHEMA + "item/report/definition/versionMetadata/1.0.0/schema.json",
    "report": SCHEMA + "item/report/definition/report/3.3.0/schema.json",
    "pages": SCHEMA + "item/report/definition/pagesMetadata/1.1.0/schema.json",
    "page": SCHEMA + "item/report/definition/page/2.1.0/schema.json",
    "visual": SCHEMA + "item/report/definition/visualContainer/2.13.0/schema.json",
}
THEME_FILE = "DashPilotTheme.json"
BACKGROUND_FILE = "DashPilotBackground.png"
PAGE_NAME = "dashpilot0page0000001"
DATE_SLICER_FIELD = f"{tmdl.DATE_TABLE}[Date]"


@dataclass
class BuildInputs:
    project_name: str
    model: ModelPlan
    cleaned: dict[str, PipelineResult]
    measures: list[Measure]  # every measure without errors (the model); visuals use Passed ones
    plan: DashboardPlan
    boxes: list[DetectedBox]
    mapping: list[MappingItem]
    theme: dict
    background: bytes
    sources: list[tuple[str, bytes]]  # (filename, original bytes)
    data_folder: str


# --- names ------------------------------------------------------------------------------------

def folder_name(project_name: str) -> str:
    return tmdl.model_folder(project_name).removesuffix(".SemanticModel")


def _id(*parts: str) -> str:
    """Stable 20-hex-char object name (the style Power BI Desktop uses)."""
    return hashlib.sha1("/".join(parts).encode()).hexdigest()[:20]


def _uuid(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "dashpilot/pbip/" + "/".join(parts)))


def _json(data: dict) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


# --- PBIR expression helpers ------------------------------------------------------------------

def literal(value) -> dict:
    if isinstance(value, bool):
        v = "true" if value else "false"
    elif isinstance(value, (int, float)):
        v = f"{value}D"
    else:
        v = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": v}}}


def color(hex_color: str) -> dict:
    return {"solid": {"color": literal(hex_color)}}


def _prop(value) -> dict:
    return color(value) if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else literal(value)


def objects(spec: dict[str, dict]) -> dict:
    """{"labels": {"fontSize": 9}} -> PBIR {"labels": [{"properties": {"fontSize": {"expr": …}}}]}"""
    return {name: [{"properties": {k: _prop(v) for k, v in props.items()}}] for name, props in spec.items() if props}


def _fill(value, tokens: dict[str, str]):
    if isinstance(value, dict):
        return {k: _fill(v, tokens) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, tokens) for v in value]
    if isinstance(value, str):
        return re.sub(r"\{\{(\w+)\}\}", lambda m: tokens.get(m.group(1), m.group(0)), value)
    return value


def template(visual_type: str) -> dict:
    data = json.loads((TEMPLATES / f"{visual_type}.json").read_text(encoding="utf-8"))
    data.pop("_comment", None)
    return data


# --- fields -----------------------------------------------------------------------------------

_FIELD = re.compile(r"^(.+)\[(.+)\]$")


def column_ref(field: str) -> tuple[str, str]:
    m = _FIELD.match(field)
    if not m:
        raise ValueError(f"Field {field!r} is not in Table[Column] form")
    return m.group(1), m.group(2)


def _column(field: str) -> tuple[dict, str, str]:
    table, col = column_ref(field)
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": col}}, f"{table}.{col}", col


def _measure(name: str) -> tuple[dict, str, str]:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": tmdl.MEASURES_TABLE}}, "Property": name}}, f"{tmdl.MEASURES_TABLE}.{name}", name


def _projection(ref: tuple[dict, str, str]) -> dict:
    # No "active" flag: it marks the current drill level, and in a table's Values role it collapses
    # the visual to that one field (seen in Power BI Desktop).
    field, query_ref, native = ref
    return {"field": field, "queryRef": query_ref, "nativeQueryRef": native}


def _query(v: PlanVisual, tpl: dict) -> dict | None:
    roles = tpl["roles"]
    if not roles:
        return None
    state: dict[str, dict] = {}
    measures = v.measures[: tpl["max_measures"]] if tpl["max_measures"] else []
    if "category" in roles and v.dimension:
        state.setdefault(roles["category"], {"projections": []})["projections"].append(_projection(_column(v.dimension)))
    target = roles.get("measures")
    for i, m in enumerate(measures):
        role = target[min(i, len(target) - 1)] if isinstance(target, list) else target
        state.setdefault(role, {"projections": []})["projections"].append(_projection(_measure(m)))
    query: dict = {"queryState": state}
    if v.sort and (measures or v.dimension):
        if v.sort == "date" and v.dimension:
            field, direction = _column(v.dimension)[0], "Ascending"
        elif measures:
            field, direction = _measure(measures[0])[0], "Descending" if v.sort == "desc" else "Ascending"
        else:
            field, direction = _column(v.dimension)[0], "Ascending"
        query["sortDefinition"] = {"sort": [{"field": field, "direction": direction}], "isDefaultSort": False}
    return query


# --- layout -----------------------------------------------------------------------------------

def visual_rect(v: PlanVisual, item: MappingItem, box: DetectedBox | None) -> tuple[int, int, int, int]:
    """Where the Power BI visual goes: the card's content area below/right of its design title,
    or the whole card (with a little padding) when Power BI draws the title itself."""
    x, y, w, h = item.x, item.y, item.w, item.h
    if item.pbi_title or box is None:
        l = t = r = b = 6
    elif box.inset:
        l, t, r, b = box.inset
        if v.role == "slicer":  # slicers need the full pill height for the dropdown
            t = b = 0
    else:
        l, t, r, b = (8, 34, 8, 8) if v.role in ("chart", "kpi", "insights") else (6, 0, 6, 0)
    rect = (x + l, y + t, w - l - r, h - t - b)
    return rect if rect[2] >= 20 and rect[3] >= 16 else (x, y, w, h)


# --- visuals ------------------------------------------------------------------------------------

def _tokens(theme: dict, palette_muted: str | None) -> dict[str, str]:
    text, card = theme.get("foreground", "#1B1C1C"), theme.get("background", "#FFFFFF")
    label = theme.get("textClasses", {}).get("label", {}).get("color")
    grid = theme.get("visualStyles", {}).get("*", {}).get("*", {}).get("valueAxis", [{}])[0].get("gridlineColor", {}).get("solid", {}).get("color", "#E3E2E2")
    band = theme.get("visualStyles", {}).get("tableEx", {}).get("*", {}).get("values", [{}])[0].get("backColorSecondary", {}).get("solid", {}).get("color", card)
    callout = theme.get("textClasses", {}).get("callout", {})
    return {"text": text, "card": card, "muted": palette_muted or label or text, "grid": grid, "band": band,
            "accent": (theme.get("dataColors") or ["#F8CF4B"])[0],
            "value": callout.get("color", text), "value_font": callout.get("fontFace", "Segoe UI")}


PBI_SAFE_FONTS = {"Segoe UI", "Arial", "Calibri", "Georgia", "Verdana", "Tahoma", "Trebuchet MS", "Cambria", "Candara",
                  "Corbel", "Consolas", "Courier New", "Times New Roman", "DIN"}
KPI_PAD_X, KPI_PAD_Y = 0, 0  # multi-row card's own inset before its first value (measured in Power BI Desktop)


def _value_font(font: str, weight: int) -> str:
    """Power BI picks weight through the font name (Segoe UI Semibold / Bold)."""
    base = font if font in PBI_SAFE_FONTS else "Segoe UI"
    if base == "Segoe UI" and weight >= 700:
        return "Segoe UI Bold"
    if base == "Segoe UI" and weight >= 550:
        return "Segoe UI Semibold"
    return base


KPI_FOLDER = "zz KPI display"


def kpi_display_name(measure: str) -> str:
    return f"{measure} (KPI)"


def _kpi_display_dax(measure: str, fmt: str) -> str:
    """The value as the design shows it (compact like Power BI's auto units), as text: the multi-row card
    that draws left/right-aligned KPIs has no display-units option of its own. Percentages and values
    under 10,000 keep the measure's own format; larger ones get K/M/B with 2 decimals."""
    ref = "[" + measure.replace("]", "]]") + "]"
    own = fmt.replace('"', '""')
    if "%" in fmt:
        return f'VAR v = {ref} RETURN IF(ISBLANK(v), BLANK(), FORMAT(v, "{own}"))'
    first = fmt.split(";")[0]
    prefix = first[: len(first) - len(first.lstrip("\\$€£₹¥ "))]  # currency symbol in front, if any
    scaled = (prefix + "#,0.00").replace('"', '""')
    return (f'VAR v = {ref} VAR a = ABS(v) RETURN IF(ISBLANK(v), BLANK(), SWITCH(TRUE(), '
            f'a >= 1E9, FORMAT(v / 1E9, "{scaled}") & "B", a >= 1E6, FORMAT(v / 1E6, "{scaled}") & "M", '
            f'a >= 1E4, FORMAT(v / 1E3, "{scaled}") & "K", FORMAT(v, "{own}")))')


def kpi_display_measures(inp: BuildInputs) -> list:
    """Hidden helper measures for the KPI cards drawn left/right-aligned (one per measure used)."""
    from types import SimpleNamespace  # noqa: PLC0415

    boxes = {b.id: b for b in inp.boxes}
    mapping = {m.visual_id: m for m in inp.mapping}
    by_name = {m.name: m for m in inp.measures}
    out, seen = [], set()
    for v in inp.plan.visuals:
        item = mapping.get(v.id)
        val = kpi_value(v, item, boxes.get(item.box_id or "")) if item and item.placed else None
        if val is None or val.align == "center" or not v.measures or v.measures[0] in seen or v.measures[0] not in by_name:
            continue
        m = by_name[v.measures[0]]
        seen.add(m.name)
        out.append(SimpleNamespace(name=kpi_display_name(m.name), expression=_kpi_display_dax(m.name, m.format_string or "#,0.##"), format_string="",
                                   folder=KPI_FOLDER, description=f"{m.name} as the dashboard's KPI card shows it (compact).", hidden=True))
    return out


def kpi_value(v: PlanVisual, item: MappingItem, box: DetectedBox | None):
    """The design's KPI number style when it can be reproduced (a design-drawn title is kept)."""
    if v.role != "kpi" or item.pbi_title or box is None or box.value is None:
        return None
    return box.value


def visual_json(v: PlanVisual, item: MappingItem, box: DetectedBox | None, order: int, tokens: dict[str, str]) -> dict:
    val = kpi_value(v, item, box)
    aligned = val is not None and val.align != "center"
    tpl = template("kpi_left" if aligned else v.type)
    x, y, w, h = visual_rect(v, item, box)
    spec = _fill(tpl["objects"], tokens)
    show_title = item.pbi_title
    if v.role == "kpi":
        if val is not None:
            # The real value in the design's own size, weight, color and place.
            target = "dataLabels" if aligned else "labels"
            spec[target].update({"fontSize": round(val.size * 0.75, 1), "fontFamily": _value_font(val.font, val.weight)})
            if val.color:
                spec[target]["color"] = val.color
            if aligned:
                # The compact display measure is text, which the multi-row card draws as its "card title".
                spec["cardTitle"] = dict(spec[target])
                # The multi-row card draws its value top-left: start the visual where the design's number starts
                # (right-aligned designs keep the left edge of the number; real values may be wider).
                x0, y0 = item.x + val.dx - KPI_PAD_X, item.y + val.dy - KPI_PAD_Y
                right, bottom = x + w, y + h
                x, y = max(item.x, x0), max(item.y, y0)
                w, h = max(40, right - x), max(30, bottom - y)
        if not aligned:
            spec.setdefault("categoryLabels", {})["show"] = show_title  # the card's own label doubles as its title
        show_title = False
    if v.role == "slicer":
        spec.setdefault("header", {})["show"] = show_title
        show_title = False
        if v.dimension == DATE_SLICER_FIELD:
            spec.setdefault("data", {})["mode"] = "Between"
    if len(v.measures) > 1 and "legend" in spec:
        spec["legend"]["show"] = True
    visual: dict = {"visualType": tpl["visualType"]}
    # Aligned KPI cards show the compact display measure (see kpi_display_measures).
    query = _query(v.model_copy(update={"measures": [kpi_display_name(v.measures[0])]}) if aligned and v.measures else v, tpl)
    if query:
        visual["query"] = query
    obj = objects(spec)
    if v.type == "text_box":
        obj["general"] = [{"properties": {"paragraphs": [
            {"textRuns": [{"value": "• " + line, "textStyle": {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": tokens["text"]}}]}
            for line in (v.text or ["Pin insights in DashPilot Step 6 to fill this box."])
        ]}}]
    if obj:
        visual["objects"] = obj
    container = {
        "background": {"show": False},
        "border": {"show": False},
        "dropShadow": {"show": False},
        "visualHeader": {"show": False},
        "title": {"show": show_title, **({"text": v.title, "fontColor": tokens["text"], "fontFamily": "Segoe UI Semibold", "fontSize": 11} if show_title else {})},
    }
    visual["visualContainerObjects"] = objects(container)
    visual["drillFilterOtherVisuals"] = True
    return {
        "$schema": SCHEMAS["visual"],
        "name": _id("visual", v.id),
        "position": {"x": x, "y": y, "z": (order + 1) * 1000, "height": h, "width": w, "tabOrder": (order + 1) * 1000},
        "visual": visual,
    }


# --- report -------------------------------------------------------------------------------------

def _report_files(inp: BuildInputs, root: str) -> dict[str, bytes]:
    d = f"{root}/definition"
    boxes = {b.id: b for b in inp.boxes}
    mapping = {m.visual_id: m for m in inp.mapping}
    palette_muted = inp.theme.get("textClasses", {}).get("label", {}).get("color")
    tokens = _tokens(inp.theme, palette_muted)
    canvas = inp.theme.get("background", "#FFFFFF")
    version = {"visual": "2.13.0", "report": "3.3.0", "page": "2.1.0"}
    files: dict[str, bytes] = {
        f"{root}/definition.pbir": _json({"$schema": SCHEMAS["pbir"], "version": "4.0",
                                          "datasetReference": {"byPath": {"path": f"../{folder_name(inp.project_name)}.SemanticModel"}}}),
        f"{root}/.platform": _json({"$schema": SCHEMAS["platform"], "metadata": {"type": "Report", "displayName": inp.project_name},
                                    "config": {"version": "2.0", "logicalId": _uuid(inp.project_name, "report")}}),
        f"{d}/version.json": _json({"$schema": SCHEMAS["version"], "version": "2.0.0"}),
        f"{d}/report.json": _json({
            "$schema": SCHEMAS["report"],
            "themeCollection": {"customTheme": {"name": THEME_FILE, "reportVersionAtImport": version, "type": "RegisteredResources"}},
            "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources", "items": [
                {"name": THEME_FILE, "path": THEME_FILE, "type": "CustomTheme"},
                {"name": BACKGROUND_FILE, "path": BACKGROUND_FILE, "type": "Image"},
            ]}],
            "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                         "allowChangeFilterTypes": True, "useEnhancedTooltips": True},
        }),
        f"{d}/pages/pages.json": _json({"$schema": SCHEMAS["pages"], "pageOrder": [PAGE_NAME], "activePageName": PAGE_NAME}),
        f"{d}/pages/{PAGE_NAME}/page.json": _json({
            "$schema": SCHEMAS["page"],
            "name": PAGE_NAME,
            "displayName": inp.plan.title[:100] or "Dashboard",
            "displayOption": "FitToPage",
            "height": inp.plan.height,
            "width": inp.plan.width,
            "objects": {
                "background": [{"properties": {
                    "image": {"image": {
                        "name": literal(BACKGROUND_FILE),
                        "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1, "ItemName": BACKGROUND_FILE}}},
                        "scaling": literal("Fit"),
                    }},
                    "transparency": literal(0),
                }}],
                "outspace": [{"properties": {"color": color(canvas)}}],
            },
        }),
        f"{root}/StaticResources/RegisteredResources/{THEME_FILE}": _json(inp.theme),
        f"{root}/StaticResources/RegisteredResources/{BACKGROUND_FILE}": inp.background,
    }
    for order, v in enumerate(inp.plan.visuals):
        item = mapping.get(v.id)
        if item is None or not item.placed:
            continue
        data = visual_json(v, item, boxes.get(item.box_id or ""), order, tokens)
        files[f"{d}/pages/{PAGE_NAME}/visuals/{data['name']}/visual.json"] = _json(data)
    return files


# --- whole project --------------------------------------------------------------------------------

README = """# {name} — Power BI Project (built by DashPilot)

## How to open
1. Unzip this archive. The default data folder is `{data_folder}`;
   unzip so that the `Data` folder ends up there, or change the parameter in step 3.
2. Open **Power BI Desktop** (2024 or newer) and double-click `{folder}.pbip`.
3. If your files are in another place: **Home → Transform data → Edit parameters → DataFolder**
   and enter the full path of the `Data` folder (ending with `\\`), then **Close & Apply**.
4. Click **Refresh** to load the data. The page uses the designed background and theme;
   visuals are already placed and bound to the measures.

## What is inside
- `{folder}.SemanticModel` — tables, relationships, date table and the `_Measures` table (TMDL);
  every table has its Power Query (M) with the cleaning steps from DashPilot.
- `{folder}.Report` — one 1280×720 page (PBIR format), background image and theme in
  `StaticResources/RegisteredResources`.
- `Data` — your uploaded files (read by Power Query); `Data/Cleaned` — the cleaned tables as CSV.

Measures: {measures} • Visuals: {visuals} • Tables: {tables}
"""


def build(inp: BuildInputs) -> dict[str, bytes]:
    folder = folder_name(inp.project_name)
    model_root = f"{folder}.SemanticModel"
    files: dict[str, bytes] = {}
    model = tmdl.build_files(inp.model, inp.cleaned, inp.project_name, inp.measures + kpi_display_measures(inp), inp.data_folder)
    for path, text in model.items():
        files[path] = text.encode("utf-8")
    files[f"{model_root}/definition.pbism"] = _json({"$schema": SCHEMAS["pbism"], "version": "4.2", "settings": {}})
    files[f"{model_root}/.platform"] = _json({"$schema": SCHEMAS["platform"], "metadata": {"type": "SemanticModel", "displayName": inp.project_name},
                                              "config": {"version": "2.0", "logicalId": _uuid(inp.project_name, "model")}})
    files.update(_report_files(inp, f"{folder}.Report"))
    files[f"{folder}.pbip"] = _json({"$schema": SCHEMAS["pbip"], "version": "1.0",
                                     "artifacts": [{"report": {"path": f"{folder}.Report"}}], "settings": {"enableAutoRecovery": True}})
    for filename, content in inp.sources:
        files[f"Data/{filename}"] = content
    for t in inp.model.tables:
        if t.included and t.name in inp.cleaned:
            files[f"Data/Cleaned/{t.name}.csv"] = inp.cleaned[t.name].df.to_csv(index=False).encode("utf-8-sig")
    included = sum(1 for t in inp.model.tables if t.included) + (1 if inp.model.date_table.enabled else 0)
    files["README.md"] = README.format(name=inp.project_name, folder=folder, data_folder=inp.data_folder,
                                       measures=len(inp.measures), visuals=len(inp.plan.visuals), tables=included).encode("utf-8")
    files[".gitignore"] = b"**/.pbi/localSettings.json\n**/.pbi/cache.abf\n"
    return files

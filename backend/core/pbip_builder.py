"""Power BI Project (PBIP) builder (spec Module 11).

Writes a complete PBIP folder as {relative path: bytes}:

  {P}.pbip
  {P}.SemanticModel/   definition.pbism, .platform, definition/*.tmdl (core.tmdl, same as the Model step)
  {P}.Report/          definition.pbir, .platform, definition/ (PBIR: version, report, pages, visuals),
                       StaticResources/RegisteredResources/ (background PNG + theme JSON from Step 8)
  Data/                the uploaded files (the M partitions read them through the DataFolder parameter)
  Data/Cleaned/        the cleaned tables as CSV (what the M steps produce), for reference
  README.md            how to open (and how to change DataFolder by hand)
  Open Dashboard.cmd   sets DataFolder to the Data folder next to it, then opens the .pbip

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
from dataclasses import dataclass, field
from pathlib import Path

from core.cleaning import PipelineResult
from core.dax import Measure
from core.design_import import DetectedBox, MappingItem
from core.modelling import ModelPlan
from core.pbip_open import OPEN_CMD, OPEN_CMD_NAME
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
PAGE_NAME = "dashpilot0page0000001"  # page n: dashpilot0page000000n
DATE_SLICER_FIELD = f"{tmdl.DATE_TABLE}[Date]"


@dataclass
class PageInput:
    """One report page: its part of the plan (planner.page_plan) and its Step 8 import."""
    plan: DashboardPlan
    boxes: list[DetectedBox]
    mapping: list[MappingItem]
    background: bytes


@dataclass
class BuildInputs:
    project_name: str
    model: ModelPlan
    cleaned: dict[str, PipelineResult]
    measures: list[Measure]  # every measure without errors (the model); visuals use Passed ones
    plan: DashboardPlan  # page 1 (planner.page_plan); further pages in extra_pages
    boxes: list[DetectedBox]
    mapping: list[MappingItem]
    theme: dict
    background: bytes
    sources: list[tuple[str, bytes]]  # (filename, original bytes)
    data_folder: str
    extra_pages: list[PageInput] = field(default_factory=list)

    @property
    def pages(self) -> list[PageInput]:
        return [PageInput(self.plan, self.boxes, self.mapping, self.background), *self.extra_pages]


def page_name(page: int) -> str:
    return f"dashpilot0page{page:07d}"


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
    elif v.role == "kpi":
        # KPI cards: give the Power BI visual ample height below the background title
        # so values and labels never get cut off at the bottom.
        l, r = 8, 8
        t = 20
        b = 6
    else:
        l, t, r, b = (8, 34, 8, 8) if v.role in ("chart", "insights") else (6, 0, 6, 0)
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

    by_name = {m.name: m for m in inp.measures}
    out, seen = [], set()
    placed = [(v, {m.visual_id: m for m in pg.mapping}.get(v.id), {b.id: b for b in pg.boxes}) for pg in inp.pages for v in pg.plan.visuals]
    for v, item, boxes in placed:
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


def _filter_no_blank_date(field_str: str) -> dict:
    table, col = column_ref(field_str)
    return {
        "name": _id("flt_blank", field_str),
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": col}},
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "d", "Entity": table, "Type": 0}],
            "Where": [{
                "Condition": {
                    "Not": {
                        "Expression": {
                            "In": {
                                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": col}}],
                                "Values": [[{"Literal": {"Value": "null"}}]]
                            }
                        }
                    }
                }
            }]
        }
    }


def _filter_top_n(v: PlanVisual, card_h: int) -> dict:
    table, col = column_ref(v.dimension or "")
    item_count = 5 if card_h < 160 else (8 if card_h < 260 else 10)
    return {
        "name": _id("flt_topn", v.dimension or ""),
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": col}},
        "type": "VisualTopN",
        "filter": {
            "Version": 2,
            "From": [{"Name": "t", "Entity": table, "Type": 0}],
            "Where": [{
                "Condition": {
                    "VisualTopN": {
                        "ItemCount": item_count
                    }
                }
            }]
        }
    }


def _filter_exclude_unknown(field_str: str) -> dict:
    table, col = column_ref(field_str)
    return {
        "name": _id("flt_unknown", field_str),
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": col}},
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "t", "Entity": table, "Type": 0}],
            "Where": [{
                "Condition": {
                    "Not": {
                        "Expression": {
                            "In": {
                                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": col}}],
                                "Values": [[{"Literal": {"Value": "'Unknown'"}}], [{"Literal": {"Value": "null"}}]]
                            }
                        }
                    }
                }
            }]
        }
    }


def visual_json(v: PlanVisual, item: MappingItem, box: DetectedBox | None, order: int, tokens: dict[str, str], page: int = 1,
                sync: bool = False) -> dict:
    val = kpi_value(v, item, box)
    aligned = val is not None and val.align != "center"
    tpl = template("kpi_left" if aligned else v.type)
    x, y, w, h = visual_rect(v, item, box)
    spec = _fill(tpl["objects"], tokens)
    show_title = item.pbi_title
    if v.role == "kpi":
        # Dynamic auto font size based on card size so values and labels never clip
        if h >= 85 and w >= 150:
            font_size = 20
        elif h >= 65 and w >= 120:
            font_size = 18
        elif h >= 50:
            font_size = 16
        else:
            font_size = 14

        target = "dataLabels" if aligned else "labels"
        if val is not None:
            spec[target].update({"fontSize": round(val.size * 0.75, 1), "fontFamily": _value_font(val.font, val.weight)})
            if val.color:
                spec[target]["color"] = val.color
            if aligned:
                spec["cardTitle"] = dict(spec[target])
                x0, y0 = item.x + val.dx - KPI_PAD_X, item.y + val.dy - KPI_PAD_Y
                right, bottom = x + w, y + h
                x, y = max(item.x, x0), max(item.y, y0)
                w, h = max(40, right - x), max(30, bottom - y)
        else:
            if target in spec:
                spec[target]["fontSize"] = font_size
        if not aligned:
            spec.setdefault("categoryLabels", {})["show"] = show_title
        show_title = False
    if v.role == "slicer":
        spec.setdefault("header", {}).update({"show": show_title, **({"text": v.title, "fontColor": tokens["text"]} if show_title else {})})
        show_title = False
        if v.dimension == DATE_SLICER_FIELD:
            spec.setdefault("data", {})["mode"] = "Between"
            spec["slider"] = {"show": False}
            spec["date"] = {"fontColor": tokens["text"], "background": tokens["card"], "textSize": 8}
    if len(v.measures) > 1 and "legend" in spec:
        spec["legend"]["show"] = True
    visual: dict = {"visualType": tpl["visualType"]}
    query = _query(v.model_copy(update={"measures": [kpi_display_name(v.measures[0])]}) if aligned and v.measures else v, tpl)
    if query:
        if v.role == "slicer":
            for role in query["queryState"].values():
                for p in role["projections"]:
                    p["displayName"] = v.title
        visual["query"] = query
    obj = objects(spec)
    if v.type == "text_box":
        raw_lines = v.text or ["Pin insights in DashPilot Step 6 to fill this box."]
        deduped = []
        seen_words = set()
        seen_nums = set()
        for line in raw_lines:
            hl = line.strip()
            norm = re.sub(r"\b(was|is|for|in|to date|versus)\b", "", hl.lower())
            words = frozenset(re.findall(r"\b[a-z0-9.%+-]+\b", norm))
            nums = tuple(sorted(re.findall(r"\d+[\d.,]*%?[KMBkmb]?", hl)))
            if words not in seen_words and (not nums or nums not in seen_nums):
                seen_words.add(words)
                if nums:
                    seen_nums.add(nums)
                deduped.append(hl)
        obj["general"] = [{"properties": {"paragraphs": [
            {"textRuns": [{"value": "• " + line, "textStyle": {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": tokens["text"]}}]}
            for line in deduped[:3]
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
    if v.role == "slicer" and sync:
        visual["syncGroup"] = {"groupName": _id("sync", v.id), "fieldChanges": True, "filterChanges": True}
    visual["drillFilterOtherVisuals"] = True

    # Visual-level filters (PBIR filterConfig)
    filters = []
    if v.type in ("line", "area") and v.dimension:
        # Filter out (Blank) dates so trend chart has a clean timeline
        filters.append(_filter_no_blank_date(v.dimension))
    elif v.type in ("clustered_bar", "stacked_bar") and v.dimension and v.measures:
        # Show top N categories scaled to card height so no scrollbar appears
        filters.append(_filter_top_n(v, h))
    elif v.type in ("donut", "pie") and v.dimension:
        # If dimension is sparse / has high blanks (e.g. cancellation reasons), filter out "Unknown"
        table, col = column_ref(v.dimension)
        if "cancellation" in col.lower() or "reason" in col.lower():
            filters.append(_filter_exclude_unknown(v.dimension))

    out_visual = {
        "$schema": SCHEMAS["visual"],
        "name": _id("visual", v.id) if page == 1 else _id("visual", f"p{page}", v.id),
        "position": {"x": x, "y": y, "z": (order + 1) * 1000, "height": h, "width": w, "tabOrder": (order + 1) * 1000},
        "visual": visual,
    }
    if filters:
        out_visual["filterConfig"] = {"filters": filters}
    return out_visual


# --- report -------------------------------------------------------------------------------------

def background_file(page: int) -> str:
    return BACKGROUND_FILE if page == 1 else BACKGROUND_FILE.replace(".png", f"_p{page}.png")


def _page_json(name: str, display: str, plan: DashboardPlan, background: str, canvas: str) -> dict:
    return {
        "$schema": SCHEMAS["page"],
        "name": name,
        "displayName": display[:100] or "Dashboard",
        "displayOption": "FitToPage",
        "height": plan.height,
        "width": plan.width,
        "objects": {
            "background": [{"properties": {
                "image": {"image": {
                    "name": literal(background),
                    "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1, "ItemName": background}}},
                    "scaling": literal("Fit"),
                }},
                "transparency": literal(0),
            }}],
            "outspace": [{"properties": {"color": color(canvas)}}],
        },
    }


def _report_files(inp: BuildInputs, root: str) -> dict[str, bytes]:
    d = f"{root}/definition"
    pages = inp.pages
    palette_muted = inp.theme.get("textClasses", {}).get("label", {}).get("color")
    tokens = _tokens(inp.theme, palette_muted)
    canvas = inp.theme.get("background", "#FFFFFF")
    version = {"visual": "2.13.0", "report": "3.3.0", "page": "2.1.0"}
    names = [page_name(n) for n in range(1, len(pages) + 1)]
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
                *({"name": background_file(n), "path": background_file(n), "type": "Image"} for n in range(1, len(pages) + 1)),
            ]}],
            "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                         "allowChangeFilterTypes": True, "useEnhancedTooltips": True},
        }),
        f"{d}/pages/pages.json": _json({"$schema": SCHEMAS["pages"], "pageOrder": names, "activePageName": names[0]}),
        f"{root}/StaticResources/RegisteredResources/{THEME_FILE}": _json(inp.theme),
    }
    for n, pg in enumerate(pages, 1):
        # Page 1 is named after the dashboard; further pages by their plan name ("Details").
        display = inp.plan.title if n == 1 else (pg.plan.pages[0] if pg.plan.pages else f"Page {n}")
        files[f"{d}/pages/{names[n - 1]}/page.json"] = _json(_page_json(names[n - 1], display, pg.plan, background_file(n), canvas))
        files[f"{root}/StaticResources/RegisteredResources/{background_file(n)}"] = pg.background
        boxes = {b.id: b for b in pg.boxes}
        mapping = {m.visual_id: m for m in pg.mapping}
        for order, v in enumerate(pg.plan.visuals):
            item = mapping.get(v.id)
            if item is None or not item.placed:
                continue
            data = visual_json(v, item, boxes.get(item.box_id or ""), order, tokens, n, sync=len(pages) > 1)
            files[f"{d}/pages/{names[n - 1]}/visuals/{data['name']}/visual.json"] = _json(data)
    return files


# --- whole project --------------------------------------------------------------------------------

README = """# {name} — Power BI Project (built by DashPilot)

## How to open
1. Unzip this archive anywhere (any folder name is fine, spaces too).
2. Double-click **`Open Dashboard.cmd`** in the `{folder}` folder. It points the model's `DataFolder`
   parameter at the `Data` folder next to it and opens `{folder}.pbip` in **Power BI Desktop**
   (2024 or newer). Run it again whenever you move the folder.
3. If the visuals are empty, click **Refresh** (Home → Refresh) once to load the data.

Windows may ask before running a downloaded file: choose **More info → Run anyway** (or right-click the
zip → Properties → Unblock before unzipping).

## Changing DataFolder by hand
Every table reads its file as `DataFolder & "<file name>"`; the build set DataFolder to
`{data_folder}`. To change it without the script:
- In Power BI Desktop: **Home → Transform data → Edit parameters → DataFolder**, enter the full path of
  the `Data` folder ending with `\\` (for example `D:\\Reports\\{folder}\\Data\\`), then **Close & Apply** and **Refresh**.
- Or, with Power BI closed, edit the first line of
  `{folder}.SemanticModel/definition/expressions.tmdl`: `expression DataFolder = "D:\\Reports\\{folder}\\Data\\" meta [...]`.

## What is inside
- `{folder}.SemanticModel` — tables, relationships, date table and the `_Measures` table (TMDL);
  every table has its Power Query (M) with the cleaning steps from DashPilot, reading your original files,
  so a refresh with updated files is cleaned the same way.
- `{folder}.Report` — {pages} page(s) of 1280×720 (PBIR format), background images and theme in
  `StaticResources/RegisteredResources`.
- `Data` — your uploaded files (read by Power Query); `Data/Cleaned` — the cleaned tables as CSV, for reference.
- `Open Dashboard.cmd` — sets DataFolder and opens the dashboard.

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
                                       measures=len(inp.measures), visuals=sum(len(pg.plan.visuals) for pg in inp.pages), tables=included,
                                       pages=len(inp.pages)).encode("utf-8")
    files[".gitignore"] = b"**/.pbi/localSettings.json\n**/.pbi/cache.abf\n"
    files[OPEN_CMD_NAME] = OPEN_CMD
    return files

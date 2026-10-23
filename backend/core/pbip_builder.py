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
from core.design_layouts import nav_slots
from core.planner import CANVAS_H, CANVAS_W, MARGIN, DashboardPlan, PlanVisual
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
        if v.role == "slicer" and t <= 12:  # pill slicers need the full pill height for the dropdown
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


def _ref(measure: str) -> str:
    return "[" + measure.replace("]", "]]") + "]"


def _indian(m) -> bool:
    """Rupee amounts get Indian units (K / L / Cr)."""
    text = f"{m.format_string or ''} {getattr(m, 'expression', '')}"
    return "₹" in text or bool(re.search(r"(?i)(\b|_)(inr|rupees?)(\b|_)", text))


def _kpi_display_dax(measure: str, fmt: str, indian: bool = False) -> str:
    """The KPI value as text, compact like Power BI's auto units (K/M/B, or K/L/Cr for rupees).
    Percentages and values under 10,000 keep the measure's own format."""
    ref = _ref(measure)
    own = fmt.replace('"', '""')
    if "%" in fmt:
        return f'VAR v = {ref} RETURN IF(ISBLANK(v), BLANK(), FORMAT(v, "{own}"))'
    first = fmt.split(";")[0]
    prefix = first[: len(first) - len(first.lstrip("\\$€£₹¥ "))]  # currency symbol in front, if any
    if indian and not prefix:
        prefix = "₹"
    scaled = (prefix + "#,0.00").replace('"', '""')
    small = (prefix + first.lstrip("\\$€£₹¥ ")).replace('"', '""') if prefix else own
    units = ([("1E7", "Cr"), ("1E5", "L"), ("1E3", "K")] if indian else [("1E9", "B"), ("1E6", "M"), ("1E3", "K")])
    steps = ", ".join(f'a >= {(n if u != "K" else "1E4")}, FORMAT(v / {n}, "{scaled}") & "{u}"' for n, u in units)
    return f'VAR v = {ref} VAR a = ABS(v) RETURN IF(ISBLANK(v), BLANK(), SWITCH(TRUE(), {steps}, FORMAT(v, "{small}")))'


# Measures where a rise is bad news (the vs PY arrow turns red when they go up).
LOWER_IS_BETTER = ("fraud", "cancel", "churn", "fail", "reversal", "return", "refund", "delay", "time", "cost",
                   "complaint", "defect", "error", "bounce", "late", "discount", "loss", "expense")


def kpi_delta_name(measure: str) -> str:
    return f"{measure} (vs)"


def kpi_delta_color_name(measure: str) -> str:
    return f"{measure} (vs colour)"


def subtitle_name(v: PlanVisual) -> str:
    return f"{v.title} (subtitle)"


def _delta_vars(measure: str) -> str:
    """Change vs the same period last year; when there is no previous year in the data, the latest
    month vs the month before (labelled MoM)."""
    m, d = _ref(measure), f"'{tmdl.DATE_TABLE}'[Date]"
    return (f"VAR cur = {m} VAR py = CALCULATE({m}, SAMEPERIODLASTYEAR({d})) "
            f"VAR usePY = NOT ISBLANK(cur) && NOT ISBLANK(py) "
            f"VAR lastDay = MAXX(FILTER(VALUES({d}), NOT ISBLANK({m})), {d}) "
            f"VAR cm = CALCULATE({m}, DATESBETWEEN({d}, EOMONTH(lastDay, -1) + 1, lastDay)) "
            f"VAR pm = CALCULATE({m}, DATESBETWEEN({d}, EOMONTH(lastDay, -2) + 1, EOMONTH(lastDay, -1))) "
            f"VAR chg = IF(usePY, DIVIDE(cur - py, ABS(py)), IF(ISBLANK(lastDay) || ISBLANK(cm), BLANK(), DIVIDE(cm - pm, ABS(pm)))) ")


def _delta_dax(measure: str) -> tuple[str, str]:
    """(text like '▲ 12.4% vs PY', its colour: green when the change is good news, red when bad)."""
    lower = any(w in measure.lower() for w in LOWER_IS_BETTER)
    text = (_delta_vars(measure) + 'RETURN IF(ISBLANK(chg), "", IF(chg >= 0, "▲ ", "▼ ") & FORMAT(ABS(chg), "0.0%") '
            '& IF(usePY, " vs PY", " MoM"))')
    good = "chg <= 0" if lower else "chg >= 0"
    colour = _delta_vars(measure) + f'RETURN IF(ISBLANK(chg), "#94A3B8", IF({good}, "#22C55E", "#EF4444"))'
    return text, colour


SUBTITLE_TYPES = ("clustered_bar", "clustered_column", "stacked_bar", "stacked_column", "donut", "pie", "line", "area", "funnel")


def has_subtitle(v: PlanVisual, item: MappingItem | None) -> bool:
    """Charts with one category and a measure get a dynamic one-line insight under the design title."""
    return (v.role == "chart" and v.type in SUBTITLE_TYPES and bool(v.dimension) and bool(v.measures)
            and item is not None and item.placed and not item.pbi_title)


def _subtitle_dax(v: PlanVisual) -> str:
    table, col = column_ref(v.dimension or "")
    c, m = f"'{table}'[{col}]", _ref(v.measures[0])
    trend = table == tmdl.DATE_TABLE and col.lower() in ("year month", "month", "date", "month name")
    tail = (" was the peak" if trend else " has the largest share" if v.type in ("donut", "pie")
            else f" has the highest {v.measures[0]}").replace('"', '""')
    return (f"VAR t = TOPN(1, FILTER(VALUES({c}), NOT ISBLANK({m})), {m}, DESC) VAR top = MAXX(t, {c}) "
            f'RETURN IF(ISBLANK(top), "", top & "{tail}")')


def kpi_extras(inp: BuildInputs) -> bool:
    """vs PY deltas and sparklines need the date table."""
    return inp.model.date_table.enabled


def kpi_display_measures(inp: BuildInputs) -> list:
    """Hidden helper measures: every KPI's compact value, its vs PY text and colour (with a date table),
    and the dynamic subtitle of each chart."""
    from types import SimpleNamespace  # noqa: PLC0415

    def helper(name: str, expression: str, description: str):
        return SimpleNamespace(name=name, expression=expression, format_string="", folder=KPI_FOLDER, description=description, hidden=True)

    by_name = {m.name: m for m in inp.measures}
    out, seen = [], set()
    for pg in inp.pages:
        mapping = {m.visual_id: m for m in pg.mapping}
        for v in pg.plan.visuals:
            item = mapping.get(v.id)
            if v.role == "kpi" and item and item.placed and v.measures and v.measures[0] in by_name and v.measures[0] not in seen:
                m = by_name[v.measures[0]]
                seen.add(m.name)
                out.append(helper(kpi_display_name(m.name), _kpi_display_dax(m.name, m.format_string or "#,0.##", _indian(m)),
                                  f"{m.name} as the dashboard's KPI card shows it (compact)."))
                if kpi_extras(inp):
                    text, colour = _delta_dax(m.name)
                    out.append(helper(kpi_delta_name(m.name), text, f"{m.name}: change vs PY (or MoM) for the KPI card."))
                    out.append(helper(kpi_delta_color_name(m.name), colour, f"{m.name}: colour of the KPI card's change."))
            elif has_subtitle(v, item) and v.measures[0] in by_name and subtitle_name(v) not in seen:
                seen.add(subtitle_name(v))
                out.append(helper(subtitle_name(v), _subtitle_dax(v), f"One-line insight under '{v.title}'."))
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
                sync: bool = False, rect: tuple[int, int, int, int] | None = None, subtitle: bool = False, compact: bool = False) -> dict:
    """`rect` overrides the position (a KPI value sharing its card with the vs PY line and sparkline);
    `subtitle` shows the chart's dynamic insight measure as a small Power BI title under the design title;
    `compact` shows a KPI through its "(KPI)" helper measure (K/M/B or K/L/Cr)."""
    val = kpi_value(v, item, box)
    aligned = val is not None and val.align != "center"
    tpl = template("kpi_left" if aligned else v.type)
    x, y, w, h = rect or visual_rect(v, item, box)
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
        if box is not None and box.value_color and not (val is not None and val.color) and target in spec:
            spec[target]["color"] = box.value_color  # e.g. white numbers on gradient KPI cards
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
    # KPI cards show the compact text value (K/M/B or K/L/Cr), named like the KPI.
    compact = v.role == "kpi" and bool(v.measures) and (compact or aligned)
    query = _query(v.model_copy(update={"measures": [kpi_display_name(v.measures[0])]}) if compact else v, tpl)
    if query:
        if v.role == "slicer" or compact:
            for role in query["queryState"].values():
                for p in role["projections"]:
                    p["displayName"] = v.title
        visual["query"] = query
    obj = objects(spec)
    if v.type == "text_box":
        raw_lines = v.text or ["Pin insights in DashPilot Step 6 to fill this box."]
        deduped = []
        seen_words: list[frozenset[str]] = []
        for line in raw_lines:
            hl = line.strip()
            norm = re.sub(r"\b(was|is|for|in|to date|versus|the|a|an)\b", "", hl.lower())
            words = frozenset(re.findall(r"\b[a-z0-9$%+-]+\b", norm))
            if words and any(len(words & prev) / max(len(words | prev), 1) >= 0.75 for prev in seen_words):
                continue
            if words:
                seen_words.append(words)
            deduped.append(hl)
        obj["general"] = [{"properties": {"paragraphs": [
            {"textRuns": [{"value": "• " + line, "textStyle": {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": tokens["text"]}}]}
            for line in (deduped or raw_lines)[:3]
        ]}}]
    if v.type in ("table", "matrix") and v.measures and query:
        # Data bars on every number column (the design's accent colour).
        obj["columnFormatting"] = [
            {"properties": {"dataBars": {"positiveColor": color(tokens["accent"]), "negativeColor": color("#EF4444"),
                                         "axisColor": color(tokens["grid"]), "reverseDirection": literal(False), "hideText": literal(False)}},
             "selector": {"metadata": _measure(m)[1]}}
            for m in v.measures[: tpl["max_measures"]]
        ]
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
    if subtitle and not show_title:
        visual["visualContainerObjects"]["title"] = [{"properties": {
            "show": literal(True), "text": {"expr": _measure(subtitle_name(v))[0]}, "fontColor": color(tokens["muted"]),
            "fontFamily": literal("Segoe UI"), "fontSize": literal(9), "alignment": literal("left"),
        }}]
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


EXTRA_Z = 20000  # KPI vs PY lines and sparklines sit above everything else


def kpi_split(rect: tuple[int, int, int, int], extras: bool) -> tuple[tuple, tuple | None, tuple | None]:
    """(value, vs PY line, sparkline) inside a KPI card's content area; extras only when they fit."""
    x, y, w, h = rect
    if not extras or h < 48 or w < 110:
        return rect, None, None
    line_h = 16
    spark_w = round(w * 0.38) if w >= 150 else 0
    left_w = w - spark_w - (6 if spark_w else 0)
    value = (x, y, left_w, h - line_h - 2)
    delta = (x, y + h - line_h, left_w, line_h)
    spark = (x + w - spark_w, y + 4, spark_w, h - 6) if spark_w else None
    return value, delta, spark


def _bare_container() -> dict:
    return objects({"background": {"show": False}, "border": {"show": False}, "dropShadow": {"show": False},
                    "visualHeader": {"show": False}, "title": {"show": False}})


def kpi_delta_json(v: PlanVisual, rect: tuple, order: int, page: int) -> dict:
    x, y, w, h = rect
    m = v.measures[0]
    colour = {"solid": {"color": {"expr": _measure(kpi_delta_color_name(m))[0]}}}
    return {
        "$schema": SCHEMAS["visual"],
        "name": _id("kpi_delta", f"p{page}", v.id),
        "position": {"x": x, "y": y, "z": EXTRA_Z + order * 10, "height": h, "width": w, "tabOrder": EXTRA_Z + order * 10},
        "visual": {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": [{**_projection(_measure(kpi_delta_name(m))), "displayName": f"{v.title} vs PY"}]}}},
            "objects": {"labels": [{"properties": {"color": colour, "fontSize": literal(8), "fontFamily": literal("Segoe UI Semibold")}}],
                        "categoryLabels": [{"properties": {"show": literal(False)}}]},
            "visualContainerObjects": _bare_container(),
            "drillFilterOtherVisuals": True,
        },
    }


def kpi_spark_json(v: PlanVisual, rect: tuple, order: int, page: int, line_color: str) -> dict:
    x, y, w, h = rect
    month = f"{tmdl.DATE_TABLE}[Year Month]"
    query = {"queryState": {"Category": {"projections": [_projection(_column(month))]},
                            "Y": {"projections": [_projection(_measure(v.measures[0]))]}},
             "sortDefinition": {"sort": [{"field": _column(month)[0], "direction": "Ascending"}], "isDefaultSort": False}}
    return {
        "$schema": SCHEMAS["visual"],
        "name": _id("kpi_spark", f"p{page}", v.id),
        "position": {"x": x, "y": y, "z": EXTRA_Z + order * 10 + 1, "height": h, "width": w, "tabOrder": EXTRA_Z + order * 10 + 1},
        "visual": {
            "visualType": "areaChart",
            "query": query,
            "objects": objects({"categoryAxis": {"show": False}, "valueAxis": {"show": False, "gridlineShow": False},
                                "legend": {"show": False}, "labels": {"show": False}, "dataPoint": {"fill": line_color}}),
            "visualContainerObjects": _bare_container(),
            "drillFilterOtherVisuals": True,
        },
        "filterConfig": {"filters": [_filter_no_blank_date(month)]},
    }


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


def _is_light_color(hex_color: str) -> bool:
    hex_clean = hex_color.lstrip("#")
    if len(hex_clean) == 6:
        try:
            r, g, b = int(hex_clean[0:2], 16), int(hex_clean[2:4], 16), int(hex_clean[4:6], 16)
            return (0.299 * r + 0.587 * g + 0.114 * b) > 160
        except ValueError:
            return True
    return True


def nav_button_json(page_num: int, target_num: int, target_page_name: str, label: str,
                    x: int, y: int, w: int, h: int, is_active: bool, tokens: dict[str, str]) -> dict:
    accent = tokens.get("accent", "#107C41")
    card = tokens.get("card", "#FFFFFF")
    grid = tokens.get("grid", "#E0E0E0")
    muted = tokens.get("muted", "#4F5665")

    if is_active:
        font_color = "#111111" if _is_light_color(accent) else "#FFFFFF"
        font_family = "Segoe UI Semibold"
        fill_color = accent
        outline_color = accent
    else:
        font_color = muted  # card-coloured fill: covers a design's own menu text (Stitch) under the button
        font_family = "Segoe UI"
        fill_color = card
        outline_color = grid

    return {
        "$schema": SCHEMAS["visual"],
        "name": _id("nav", str(page_num), target_page_name),
        "position": {
            "x": x,
            "y": y,
            "z": 9000 + target_num,
            "height": h,
            "width": w,
            "tabOrder": 9000 + target_num,
        },
        "visual": {
            "visualType": "actionButton",
            "objects": {
                "text": [{"properties": {
                    "show": literal(True),
                    "text": literal(label),
                    "fontColor": color(font_color),
                    "fontSize": literal(10),
                    "fontFamily": literal(font_family),
                    "horizontalAlignment": literal("center"),
                    "verticalAlignment": literal("middle"),
                }}],
                "fill": [{"properties": {
                    "show": literal(True),
                    "fillColor": color(fill_color),
                    "transparency": literal(0),
                }}],
                "outline": [{"properties": {
                    "show": literal(True),
                    "lineColor": color(outline_color),
                    "weight": literal(1),
                }}],
            },
            "visualContainerObjects": {
                "background": [{"properties": {"show": literal(False)}}],
                "border": [{"properties": {"show": literal(False)}}],
                "dropShadow": [{"properties": {"show": literal(False)}}],
                "visualHeader": [{"properties": {"show": literal(False)}}],
                "title": [{"properties": {"show": literal(False)}}],
                "visualLink": [{
                    "properties": {
                        "show": literal(True),
                        "type": literal("PageNavigation"),
                        "navigationSection": literal(target_page_name),
                    }
                }],
            },
        },
    }


def report_title_textbox_json(title: str, subtitle: str, x: int, y: int, w: int, h: int, page: int,
                              tokens: dict[str, str], font_family: str = "Segoe UI", font_color: str | None = None) -> dict:
    paragraphs = [
        {"textRuns": [{"value": title, "textStyle": {"fontFamily": font_family, "fontSize": "16pt", "color": font_color or tokens.get("text", "#FFFFFF"), "fontWeight": "bold"}}]}
    ]
    if subtitle:
        paragraphs.append(
            {"textRuns": [{"value": subtitle, "textStyle": {"fontFamily": font_family, "fontSize": "10pt", "color": tokens.get("muted", "#94A3B8")}}]}
        )
    return {
        "$schema": SCHEMAS["visual"],
        "name": _id("title", str(page), title),
        "position": {
            "x": x,
            "y": y,
            "z": 20005,
            "height": h,
            "width": w,
            "tabOrder": 100,
        },
        "visual": {
            "visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]},
            "visualContainerObjects": _bare_container(),
            "drillFilterOtherVisuals": True,
        },
    }


def design_nav_slots(pg: PageInput, labels: list[str]):
    """Button slots on the design's own page menu: an unmapped box titled like one of the pages is
    that page's item; the other pages continue below it (a side menu) or beside it (top tabs).
    If a single tab container box is detected (box_02 / role nav), it is partitioned across labels."""
    from core.planner import Box  # noqa: PLC0415

    used = {m.box_id for m in pg.mapping if m.placed and m.box_id}
    norm = lambda s: " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())  # noqa: E731
    wanted = {norm(lab): i for i, lab in enumerate(labels)}

    # 1. Single tab container box holding the page tabs (e.g. box_02 with Overview and Details)
    nav_box = next(
        (b for b in pg.boxes if (getattr(b, "role", None) == "nav" or b.id == "box_02") and b.id not in used),
        None,
    )
    if nav_box is None:
        nav_box = next(
            (b for b in pg.boxes if b.id not in used and b.h <= 60 and sum(1 for lab in labels if norm(lab) in norm(b.text or b.title)) >= min(2, len(labels))),
            None,
        )
    if nav_box is not None:
        b = nav_box
        n_btn = max(1, len(labels))
        gap = 4
        btn_w = max(40, (b.w - (n_btn - 1) * gap) // n_btn)
        slots = [Box(x=b.x + t * (btn_w + gap), y=b.y, w=btn_w, h=b.h) for t in range(n_btn)]
        return slots

    # 2. Individual anchor box
    anchor = next(((b, wanted[norm(b.title)]) for b in pg.boxes if b.id not in used and norm(b.title) in wanted and b.h <= 60), None)
    if anchor is None:
        return []
    b, i = anchor
    vertical = b.w <= 280 and b.x < 260
    step_x, step_y = (0, b.h + 12) if vertical else (b.w + 8, 0)
    slots = [Box(x=b.x + (t - i) * step_x, y=b.y + (t - i) * step_y, w=b.w, h=b.h) for t in range(len(labels))]
    fits = all(s.x >= 0 and s.y >= 0 and s.x + s.w <= pg.plan.width and s.y + s.h <= pg.plan.height for s in slots)
    return slots if fits else []


def _is_sidebar_page(pg: PageInput) -> tuple[bool, int]:
    """Detect if the page uses a left sidebar layout and return (is_sidebar, sidebar_w)."""
    boxes = {b.id: b for b in pg.boxes}
    mapping = {m.visual_id: m for m in pg.mapping}
    xs = [
        item.x if item.x > 0 else (boxes[item.box_id].x if item.box_id in boxes else 0)
        for v in pg.plan.visuals
        if v.role in ("kpi", "chart", "insights")
        for item in [mapping.get(v.id)]
        if item and item.placed
    ]
    if xs and min(xs) >= 200:
        return True, min(xs) - MARGIN
    return False, 0


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
    helpers = {h.name for h in kpi_display_measures(inp)}
    for n, pg in enumerate(pages, 1):
        # Page 1 is named after the dashboard; further pages by their plan name ("Details").
        display = inp.plan.title if n == 1 else (pg.plan.pages[0] if pg.plan.pages else f"Page {n}")
        files[f"{d}/pages/{names[n - 1]}/page.json"] = _json(_page_json(names[n - 1], display, pg.plan, background_file(n), canvas))
        files[f"{root}/StaticResources/RegisteredResources/{background_file(n)}"] = pg.background
        boxes = {b.id: b for b in pg.boxes}
        mapping = {m.visual_id: m for m in pg.mapping}
        from core.design_layouts import resolve_overlaps
        placed_items = [mapping[v.id] for v in pg.plan.visuals if v.id in mapping and mapping[v.id].placed]
        if placed_items:
            resolve_overlaps(placed_items, min_gap=12)
        for order, v in enumerate(pg.plan.visuals):
            item = mapping.get(v.id)
            if item is None or not item.placed:
                dw = 200 if v.role == "slicer" else 190 if v.role == "kpi" else 380
                dh = 40 if v.role == "slicer" else 92 if v.role == "kpi" else 240
                fx = MARGIN + (order % 3) * (dw + 12)
                fy = 72 + (order // 3) * (dh + 12)
                item = MappingItem(visual_id=v.id, x=fx, y=min(fy, CANVAS_H - dh - MARGIN), w=dw, h=dh, method="fallback", pbi_title=True)
            box = boxes.get(item.box_id or "")
            extra: list[dict] = []
            rect = None
            if v.role == "kpi" and v.measures and not item.pbi_title:
                rect, delta, spark = kpi_split(visual_rect(v, item, box), kpi_delta_name(v.measures[0]) in helpers)
                if delta:
                    extra.append(kpi_delta_json(v, delta, order, n))
                if spark:
                    extra.append(kpi_spark_json(v, spark, order, n, (box.value_color if box and box.value_color else tokens["accent"])))
            data = visual_json(v, item, box, order, tokens, n, sync=len(pages) > 1, rect=rect,
                               subtitle=subtitle_name(v) in helpers and has_subtitle(v, item),
                               compact=bool(v.measures) and kpi_display_name(v.measures[0]) in helpers)
            for out in (data, *extra):
                files[f"{d}/pages/{names[n - 1]}/visuals/{out['name']}/visual.json"] = _json(out)

        # Report title textbox if an unmapped title box is present in the design
        used_boxes = {m.box_id for m in pg.mapping if m.placed and m.box_id}
        title_box = next(
            (b for b in pg.boxes if b.id not in used_boxes and (
                getattr(b, "role", None) == "title"
                or (b.id == "box_01" and (getattr(b, "role", None) == "title" or b.title == "Dashboard" or "dashboard" in (b.title or "").lower() or "report" in (b.title or "").lower()))
                or (b.y < 80 and b.h <= 70 and any(w in (b.title or "").lower() for w in ("dashboard", "overview", "report", "performance")))
            )),
            None,
        )
        if title_box is not None:
            title_x = title_box.x
            title_y = max(MARGIN, title_box.y)
            right_boxes = [b for b in pg.boxes if b.id != title_box.id and b.x > title_x and b.y < title_y + 80 and b.y + b.h > title_y]
            max_right = min((b.x for b in right_boxes), default=title_x + min(title_box.w, 360))
            title_w = max(100, min(title_box.w, max_right - title_x - 12))
            title_h = min(title_box.h, 60)
            title_visual = report_title_textbox_json(
                title=inp.plan.title,
                subtitle=inp.plan.subtitle or "",
                x=title_x,
                y=title_y,
                w=title_w,
                h=title_h,
                page=n,
                tokens=tokens,
                font_family=title_box.title_font or "Segoe UI",
                font_color=title_box.title_color or tokens.get("text", "#FFFFFF"),
            )
            files[f"{d}/pages/{names[n - 1]}/visuals/{title_visual['name']}/visual.json"] = _json(title_visual)

    for n in range(1, len(pages) + 1):
        curr_page_name = names[n - 1]
        pg = pages[n - 1]
        labels = [p.plan.pages[0] if p.plan.pages else ("Overview" if t == 1 else f"Page {t}") for t, p in enumerate(pages, 1)]
        slots = design_nav_slots(pg, labels)
        if not slots and len(pages) > 1:
            is_sidebar, sidebar_w = _is_sidebar_page(pg)
            slots = nav_slots(len(pages), sidebar_w if is_sidebar else 0)
        if slots and (len(pages) > 1 or len(slots) > 1):
            for t, slot in enumerate(slots, 1):
                target_page_name = names[min(t - 1, len(names) - 1)]
                label = labels[t - 1] if t <= len(labels) else f"Page {t}"
                btn_data = nav_button_json(
                    page_num=n, target_num=t, target_page_name=target_page_name,
                    label=label, x=slot.x, y=slot.y, w=slot.w, h=slot.h,
                    is_active=(t == n), tokens=tokens,
                )
                files[f"{d}/pages/{curr_page_name}/visuals/{btn_data['name']}/visual.json"] = _json(btn_data)

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

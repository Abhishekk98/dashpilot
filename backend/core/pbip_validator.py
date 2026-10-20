"""Validation of a built PBIP before delivery (spec Module 12).

Checks the files the builder produced, not its inputs:
- every PBIP/PBIR JSON file against Microsoft's JSON schema named in its "$schema" (cached in
  templates/pbir_schemas, so no network is needed)
- TMDL syntax (indentation, object declarations, balanced DAX/M brackets and quotes)
- the model: relationship columns exist, measure references resolve
- every field and measure a visual uses exists in the generated model
- layout: every visual inside the page, no overlaps (same rule as the design validator)
- resources: background/theme/dataset/report paths referenced by the JSON exist
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from jsonschema.validators import validator_for
from pydantic import BaseModel
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

from core.design_contract import overlap

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "templates" / "pbir_schemas"
SCHEMA_BASE = "https://developer.microsoft.com/json-schemas/"
JSON_SUFFIXES = (".json", ".pbir", ".pbism", ".pbip", ".platform")


class Check(BaseModel):
    id: str
    label: str
    status: Literal["pass", "warn", "fail"]
    detail: str = ""
    count: int | None = None
    issues: list[str] = []


# --- schemas ------------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _registry() -> Registry:
    resources = []
    for path in SCHEMA_DIR.rglob("*.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(contents, default_specification=DRAFT7)
        url = SCHEMA_BASE + path.relative_to(SCHEMA_DIR).as_posix()
        resources.append((url, resource))
        if contents.get("$id") and contents["$id"] != url:
            resources.append((contents["$id"], resource))
    return Registry().with_resources(resources)


def schema_errors(data: dict) -> list[str]:
    url = data.get("$schema")
    if not url:
        return ["missing $schema"]
    registry = _registry()
    try:
        root = registry.contents(url)
    except Exception:
        return [f"schema not cached: {url}"]
    validator = validator_for(root)({"$ref": url}, registry=registry)
    out = []
    for e in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))[:5]:
        where = "/".join(str(p) for p in e.absolute_path) or "(root)"
        out.append(f"{where}: {e.message[:160]}")
    return out


# --- TMDL ---------------------------------------------------------------------------------------

_TOP = ("table", "relationship", "expression", "model", "database", "ref", "role", "perspective", "culture", "annotation", "///", "createOrReplace")
_DECL = re.compile(r"^(column|measure|partition|hierarchy|level|annotation|calculationGroup|calculationItem|variation|changedProperty)\b")
_PROP = re.compile(r"^[A-Za-z][A-Za-z0-9]*(:\s*.*)?$")


def _close(text: str, i: int, quote: str) -> int:
    """Index of the closing `quote` for the one at i, honouring doubled escapes ("" '' ]]); -1 if none."""
    j = text.find(quote, i + 1)
    while j != -1 and j + 1 < len(text) and text[j + 1] == quote:
        j = text.find(quote, j + 2)
    return j


def scan(text: str) -> tuple[list[tuple[str | None, str]], set[str], str | None]:
    """Light DAX/M scanner -> ([(table or None, name) for each [...] reference], string literals, problem).
    Brackets hold names verbatim (quotes inside are not strings; ]] escapes ]), 'names' and "strings"
    use doubled quotes, // and -- start comments. `problem` is None when (), {} and quotes balance."""
    refs: list[tuple[str | None, str]] = []
    strings: set[str] = set()
    stack: list[str] = []
    table: str | None = None
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            j = _close(text, i, '"')
            if j == -1:
                return refs, strings, "unclosed string"
            strings.add(text[i + 1:j].replace('""', '"'))
            i, table = j + 1, None
            continue
        if ch == "'":
            j = _close(text, i, "'")
            if j == -1:
                return refs, strings, "unclosed quoted name"
            table = text[i + 1:j].replace("''", "'")
            i = j + 1
            continue
        if ch == "[":
            j = _close(text, i, "]")
            if j == -1:
                return refs, strings, "unclosed '['"
            refs.append((table, text[i + 1:j].replace("]]", "]")))
            i, table = j + 1, None
            continue
        if text[i:i + 2] in ("//", "--"):
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        m = re.match(r"[A-Za-z_][A-Za-z0-9_.]*", text[i:])
        if m:
            table = m.group(0)
            i += len(table)
            continue
        if ch in "({":
            stack.append(ch)
        elif ch in ")}":
            if not stack or stack[-1] != {")": "(", "}": "{"}[ch]:
                return refs, strings, f"unexpected '{ch}'"
            stack.pop()
        if not ch.isspace():
            table = None
        i += 1
    return refs, strings, (f"unclosed '{stack[-1]}'" if stack else None)


def _balanced(text: str) -> str | None:
    return scan(text)[2]


def tmdl_errors(path: str, text: str) -> list[str]:
    errors: list[str] = []
    lines = text.split("\n")
    expr_indent: int | None = None  # inside a multi-line M/DAX expression
    expr_lines: list[str] = []
    expr_start = 0

    def close_expr():
        nonlocal expr_indent, expr_lines
        if expr_lines:
            problem = _balanced("\n".join(expr_lines))
            if problem:
                errors.append(f"{path}:{expr_start}: expression has {problem}")
        expr_indent, expr_lines = None, []

    for no, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        if raw.startswith(" "):
            errors.append(f"{path}:{no}: indent with tabs, not spaces")
            continue
        depth = len(raw) - len(raw.lstrip("\t"))
        body = raw.strip()
        if expr_indent is not None:
            if depth >= expr_indent:
                expr_lines.append(body)
                continue
            close_expr()
        if body.startswith("///"):
            continue
        if depth == 0:
            if not body.startswith(_TOP):
                errors.append(f"{path}:{no}: unknown top-level object '{body.split()[0]}'")
        elif not (_DECL.match(body) or _PROP.match(body.split(" =")[0])):
            errors.append(f"{path}:{no}: cannot read '{body[:40]}'")
        decl = re.match(r"^(table|column|measure|partition|ref table|hierarchy|level|expression|relationship)\s+(.*)$", body)
        if decl:
            name_part = decl.group(2).split(" =")[0].strip()
            if name_part.startswith("'") and _close(name_part, 0, "'") != len(name_part) - 1:
                errors.append(f"{path}:{no}: badly quoted name {name_part[:40]}")
        if re.search(r"(=|source =|expression =)\s*$", body):  # value continues on deeper lines
            expr_indent, expr_lines, expr_start = depth + 1, [], no
        elif " = " in body and depth >= 1 and body.startswith(("measure", "partition", "expression")):
            value = body.split(" = ", 1)[1]
            problem = _balanced(value)
            if problem and not value.strip().endswith(("meta [", "meta")):
                errors.append(f"{path}:{no}: expression has {problem}")
        elif body.startswith("expression ") and " = " in body:
            problem = _balanced(body.split(" = ", 1)[1])
            if problem:
                errors.append(f"{path}:{no}: expression has {problem}")
    close_expr()
    return errors


_NAME = r"('(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)"


def _unquote(name: str) -> str:
    return name[1:-1].replace("''", "'") if name.startswith("'") else name


def inventory(files: dict[str, bytes]) -> tuple[dict[str, set[str]], dict[str, str]]:
    """({table: {columns}}, {measure: expression}) parsed from the generated TMDL."""
    tables: dict[str, set[str]] = {}
    measures: dict[str, str] = {}
    for path, content in files.items():
        if not path.endswith(".tmdl") or "/tables/" not in path:
            continue
        text = content.decode("utf-8")
        m = re.match(rf"^table {_NAME}", text)
        if not m:
            continue
        table = _unquote(m.group(1))
        tables[table] = {_unquote(c) for c in re.findall(rf"^\tcolumn {_NAME}", text, re.M)}
        for mm in re.finditer(rf"^\tmeasure {_NAME} =(.*(?:\n\t\t\t.*)*)", text, re.M):
            measures[_unquote(mm.group(1))] = mm.group(2)
    return tables, measures


# --- report ------------------------------------------------------------------------------------

def _refs(node, out: list[tuple[str, str, str]]) -> None:
    if isinstance(node, dict):
        for kind in ("Column", "Measure"):
            if kind in node and isinstance(node[kind], dict) and "Property" in node[kind]:
                entity = node[kind].get("Expression", {}).get("SourceRef", {}).get("Entity")
                out.append((kind, entity, node[kind]["Property"]))
        for v in node.values():
            _refs(v, out)
    elif isinstance(node, list):
        for v in node:
            _refs(v, out)


def validate(files: dict[str, bytes], width: int = 1280, height: int = 720) -> list[Check]:
    checks: list[Check] = []

    # 1. JSON schemas
    parsed: dict[str, dict] = {}
    schema_issues: list[str] = []
    for path, content in files.items():
        if not path.endswith(JSON_SUFFIXES) or "/RegisteredResources/" in path:
            continue
        try:
            data = json.loads(content.decode("utf-8-sig"))
        except ValueError as exc:
            schema_issues.append(f"{path}: not valid JSON ({exc})")
            continue
        parsed[path] = data
        schema_issues += [f"{path}: {e}" for e in schema_errors(data)]
    checks.append(Check(id="schemas", label="Report files match Microsoft's PBIR/PBIP schemas", count=len(parsed),
                        status="fail" if schema_issues else "pass", detail=f"{len(parsed)} files validated", issues=schema_issues[:20]))

    # 2. TMDL syntax
    tmdl = {p: c.decode("utf-8") for p, c in files.items() if p.endswith(".tmdl")}
    tmdl_issues = [e for p, t in tmdl.items() for e in tmdl_errors(p, t)]
    tables, measures = inventory(files)
    checks.append(Check(id="tmdl", label="Semantic model (TMDL) syntax", count=len(tables),
                        status="fail" if tmdl_issues else "pass", detail=f"{len(tmdl)} files • {len(tables)} tables", issues=tmdl_issues[:20]))

    # 3. Model consistency: relationships and measure references
    model_issues: list[str] = []
    rel = next((t for p, t in tmdl.items() if p.endswith("relationships.tmdl")), "")
    for side in re.findall(rf"(?:from|to)Column: {_NAME}\.{_NAME}", rel):
        table, col = _unquote(side[0]), _unquote(side[1])
        if col not in tables.get(table, set()):
            model_issues.append(f"Relationship uses {table}[{col}], which is not in the model.")
    all_columns = {c for cols in tables.values() for c in cols}
    for name, expr in measures.items():
        refs, local, _ = scan(expr)  # string literals = columns the expression adds itself (ADDCOLUMNS(…, "@Value", …))
        for table, ref in refs:
            if table in tables:
                if ref not in tables[table]:
                    model_issues.append(f"[{name}] uses {table}[{ref}], which is not in the model.")
            elif ref not in measures and ref not in all_columns and ref not in local:
                model_issues.append(f"[{name}] refers to [{ref}], which is neither a measure nor a column.")
    checks.append(Check(id="dax", label="DAX measures & format strings", count=len(measures),
                        status="fail" if model_issues else "pass", detail=f"{len(measures)} measures in _Measures", issues=model_issues[:20]))

    # 4. Visual fields exist in the model
    visuals = {p: d for p, d in parsed.items() if p.endswith("/visual.json")}
    field_issues: list[str] = []
    bound = 0
    for path, data in visuals.items():
        refs: list[tuple[str, str, str]] = []
        _refs(data.get("visual", {}).get("query", {}), refs)
        bound += len(refs)
        for kind, entity, prop in refs:
            if kind == "Measure" and prop not in measures:
                field_issues.append(f"{data['name']}: measure [{prop}] is not in the model.")
            if kind == "Column" and prop not in tables.get(entity, set()):
                field_issues.append(f"{data['name']}: column {entity}[{prop}] is not in the model.")
    checks.append(Check(id="fields", label="Visual fields bound to the model", count=bound,
                        status="fail" if field_issues else "pass", detail=f"{bound} field bindings in {len(visuals)} visuals", issues=field_issues[:20]))

    # 5. Layout
    layout_issues: list[str] = []
    boxes = []
    for data in visuals.values():
        p = data["position"]
        box = SimpleNamespace(x=p["x"], y=p["y"], w=p["width"], h=p["height"], name=data["name"])
        if box.x < 0 or box.y < 0 or box.x + box.w > width + 0.5 or box.y + box.h > height + 0.5:
            layout_issues.append(f"Visual {box.name} is outside the {width}x{height} page.")
        boxes.append(box)
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if overlap(a, b):
                layout_issues.append(f"Visuals {a.name} and {b.name} overlap.")
    maps = [d["name"] for d in visuals.values() if d.get("visual", {}).get("visualType") == "azureMap"]
    if maps:
        layout_issues_warn = [f"{len(maps)} map visual(s): Power BI shows them only when the Azure Maps tenant setting is on "
                              "(Admin portal → Tenant settings → Azure Maps). Pick a bar chart in Step 7 if you cannot change it."]
    else:
        layout_issues_warn = []
    checks.append(Check(id="layout", label="Report page & visual positions", count=len(visuals),
                        status="fail" if layout_issues else "warn" if maps else "pass",
                        detail=f"{len(visuals)} visuals on a {width}×{height} page", issues=(layout_issues + layout_issues_warn)[:20]))

    # 6. Resources and cross-file references
    res_issues: list[str] = []
    for path, data in parsed.items():
        if path.endswith("/definition/report.json"):
            base = path.removesuffix("definition/report.json") + "StaticResources/"
            for pkg in data.get("resourcePackages", []):
                for item in pkg.get("items", []):
                    if f"{base}{pkg['name']}/{item['path']}" not in files:
                        res_issues.append(f"{item['path']} is listed in report.json but missing.")
        if path.endswith("definition.pbir"):
            target = data.get("datasetReference", {}).get("byPath", {}).get("path", "")
            if not any(f.startswith(target.removeprefix("../") + "/") for f in files):
                res_issues.append(f"definition.pbir points to {target}, which is missing.")
        if path.endswith(".pbip"):
            for art in data.get("artifacts", []):
                rp = art.get("report", {}).get("path", "")
                if not any(f.startswith(rp + "/") for f in files):
                    res_issues.append(f".pbip points to {rp}, which is missing.")
    theme = next((p for p in files if p.endswith(".json") and "/RegisteredResources/" in p), None)
    theme_colors = len(json.loads(files[theme]).get("dataColors", [])) if theme else 0
    checks.append(Check(id="resources", label="Background image & theme JSON", count=theme_colors,
                        status="fail" if res_issues or not theme else "pass",
                        detail=f"1280×720 background • {theme_colors} theme colors", issues=res_issues[:20]))
    return checks

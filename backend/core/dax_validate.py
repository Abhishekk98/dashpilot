"""Static DAX checks: tokenizer, reference validation, function whitelist and circular dependencies.

Every measure (rule-generated, AI-suggested or typed by the user) passes through `check()` before
it is accepted. This is not a full DAX parser; it catches the mistakes that would make Power BI
reject a measure: unbalanced brackets, unknown tables/columns/measures, unknown functions and
measures that depend on themselves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FUNCTIONS = {
    # aggregation
    "SUM", "SUMX", "AVERAGE", "AVERAGEX", "AVERAGEA", "MIN", "MINX", "MINA", "MAX", "MAXX", "MAXA", "COUNT", "COUNTA",
    "COUNTX", "COUNTAX", "COUNTROWS", "COUNTBLANK", "DISTINCTCOUNT", "DISTINCTCOUNTNOBLANK", "PRODUCT", "PRODUCTX",
    "MEDIAN", "MEDIANX", "PERCENTILE.INC", "PERCENTILE.EXC", "PERCENTILEX.INC", "STDEV.S", "STDEV.P", "STDEVX.S",
    "VAR.S", "VAR.P", "APPROXIMATEDISTINCTCOUNT",
    # filter / context
    "CALCULATE", "CALCULATETABLE", "FILTER", "ALL", "ALLEXCEPT", "ALLSELECTED", "ALLNOBLANKROW", "REMOVEFILTERS",
    "KEEPFILTERS", "VALUES", "DISTINCT", "SELECTEDVALUE", "HASONEVALUE", "HASONEFILTER", "ISFILTERED", "ISCROSSFILTERED",
    "USERELATIONSHIP", "CROSSFILTER", "RELATED", "RELATEDTABLE", "LOOKUPVALUE", "TREATAS", "EARLIER", "EARLIEST",
    # tables
    "ADDCOLUMNS", "SELECTCOLUMNS", "SUMMARIZE", "SUMMARIZECOLUMNS", "TOPN", "GENERATE", "GENERATESERIES", "ROW",
    "UNION", "INTERSECT", "EXCEPT", "CROSSJOIN", "DATATABLE", "GROUPBY", "NATURALINNERJOIN", "NATURALLEFTOUTERJOIN",
    "FIRSTNONBLANK", "LASTNONBLANK", "FIRSTNONBLANKVALUE", "LASTNONBLANKVALUE", "SAMPLE", "WINDOW", "OFFSET", "INDEX",
    # ranking
    "RANKX", "RANK", "ROWNUMBER",
    # logical / info
    "IF", "IF.EAGER", "SWITCH", "AND", "OR", "NOT", "TRUE", "FALSE", "BLANK", "ISBLANK", "ISERROR", "IFERROR", "COALESCE",
    "ISNUMBER", "ISTEXT", "ISEMPTY", "CONTAINS", "CONTAINSROW", "CONTAINSSTRING", "CONTAINSSTRINGEXACT", "ISINSCOPE",
    # math
    "DIVIDE", "ABS", "ROUND", "ROUNDUP", "ROUNDDOWN", "INT", "TRUNC", "MOD", "POWER", "SQRT", "EXP", "LN", "LOG", "LOG10",
    "CEILING", "FLOOR", "SIGN", "MROUND", "QUOTIENT", "CURRENCY", "CONVERT", "VALUE", "FIXED",
    # text
    "FORMAT", "CONCATENATE", "CONCATENATEX", "LEFT", "RIGHT", "MID", "LEN", "UPPER", "LOWER", "TRIM", "SUBSTITUTE",
    "REPLACE", "SEARCH", "FIND", "REPT", "UNICHAR", "COMBINEVALUES",
    # dates and time intelligence
    "DATE", "DATEVALUE", "TIME", "YEAR", "MONTH", "DAY", "QUARTER", "WEEKNUM", "WEEKDAY", "HOUR", "MINUTE", "TODAY", "NOW",
    "EOMONTH", "EDATE", "DATEDIFF", "CALENDAR", "CALENDARAUTO", "TOTALYTD", "TOTALQTD", "TOTALMTD", "DATESYTD", "DATESQTD",
    "DATESMTD", "DATESINPERIOD", "DATESBETWEEN", "DATEADD", "SAMEPERIODLASTYEAR", "PARALLELPERIOD", "PREVIOUSYEAR",
    "PREVIOUSQUARTER", "PREVIOUSMONTH", "PREVIOUSDAY", "NEXTYEAR", "NEXTQUARTER", "NEXTMONTH", "NEXTDAY", "STARTOFYEAR",
    "ENDOFYEAR", "STARTOFQUARTER", "ENDOFQUARTER", "STARTOFMONTH", "ENDOFMONTH", "FIRSTDATE", "LASTDATE",
    "OPENINGBALANCEYEAR", "CLOSINGBALANCEYEAR", "OPENINGBALANCEMONTH", "CLOSINGBALANCEMONTH",
}
KEYWORDS = {"VAR", "RETURN", "IN", "NOT", "AND", "OR", "ASC", "DESC", "DAY", "MONTH", "YEAR", "QUARTER", "WEEK", "TRUE", "FALSE", "SKIP", "DENSE", "BOTH", "NONE", "ONEWAY", "ABS", "REL"}
TIME_FUNCTIONS = {f for f in FUNCTIONS if f.startswith(("TOTAL", "DATES", "SAMEPERIOD", "PARALLEL", "PREVIOUS", "NEXT", "DATEADD", "STARTOF", "ENDOF", "OPENING", "CLOSING"))}

_TOKEN = re.compile(
    r"""(?P<ws>\s+)
      |(?P<comment>//[^\n]*|--[^\n]*|/\*.*?\*/)
      |(?P<string>"(?:[^"]|"")*")
      |(?P<qtable>'(?:[^']|'')*')
      |(?P<bracket>\[(?:[^\]]|\]\])*\])
      |(?P<number>\d+(?:\.\d+)?)
      |(?P<ident>[A-Za-z_][A-Za-z0-9_.]*)
      |(?P<op><=|>=|<>|==|&&|\|\||[-+*/=<>&,(){}^])""",
    re.S | re.X,
)


@dataclass
class Token:
    kind: str  # string | table | bracket | number | ident | op
    value: str
    pos: int


def tokenize(expression: str) -> tuple[list[Token], list[str]]:
    tokens, issues, pos = [], [], 0
    while pos < len(expression):
        m = _TOKEN.match(expression, pos)
        if not m:
            issues.append(f"Unexpected character {expression[pos]!r} at position {pos + 1}")
            pos += 1
            continue
        kind = m.lastgroup or ""
        text = m.group()
        if kind == "string":
            tokens.append(Token("string", text[1:-1].replace('""', '"'), pos))
        elif kind == "qtable":
            tokens.append(Token("table", text[1:-1].replace("''", "'"), pos))
        elif kind == "bracket":
            tokens.append(Token("bracket", text[1:-1].replace("]]", "]"), pos))
        elif kind in ("number", "ident", "op"):
            tokens.append(Token(kind, text, pos))
        pos = m.end()
    return tokens, issues


@dataclass
class Schema:
    """Tables and columns a measure may reference (case-insensitive, like Power BI)."""

    tables: dict[str, tuple[str, dict[str, str]]] = field(default_factory=dict)  # lower -> (name, {col lower: col})

    def add(self, table: str, columns: list[str]) -> None:
        self.tables[table.lower()] = (table, {c.lower(): c for c in columns})

    def table(self, name: str) -> str | None:
        found = self.tables.get(name.lower())
        return found[0] if found else None

    def column(self, table: str, column: str) -> str | None:
        found = self.tables.get(table.lower())
        return found[1].get(column.lower()) if found else None

    def any_column(self, column: str) -> bool:
        return any(column.lower() in cols for _, cols in self.tables.values())


@dataclass
class CheckResult:
    issues: list[str]
    deps: list[str]  # measure names referenced (canonical spelling)
    columns: list[tuple[str, str]]
    time_intelligence: bool


def check(expression: str, schema: Schema, measures: dict[str, str]) -> CheckResult:
    """Validate one expression. `measures` maps lower-case measure name -> canonical name."""
    tokens, issues = tokenize(expression)
    if not tokens:
        return CheckResult(["The formula is empty"], [], [], False)

    depth = {"(": 0, "{": 0}
    pairs = {")": "(", "}": "{"}
    for t in tokens:
        if t.kind == "op" and t.value in depth:
            depth[t.value] += 1
        elif t.kind == "op" and t.value in pairs:
            depth[pairs[t.value]] -= 1
            if depth[pairs[t.value]] < 0:
                issues.append(f"Unmatched '{t.value}' at position {t.pos + 1}")
                depth[pairs[t.value]] = 0
    for opener, n in depth.items():
        if n > 0:
            issues.append(f"{n} unclosed '{opener}'")

    strings = {t.value for t in tokens if t.kind == "string"}
    variables = {tokens[i + 1].value.lower() for i, t in enumerate(tokens[:-1]) if t.kind == "ident" and t.value.upper() == "VAR"}
    deps: list[str] = []
    columns: list[tuple[str, str]] = []
    time_intel = False
    for i, t in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        prev = tokens[i - 1] if i else None
        if t.kind in ("ident", "table") and nxt is not None and nxt.kind == "bracket" and (t.kind == "table" or t.value.upper() not in FUNCTIONS):
            table = schema.table(t.value)
            if table is None:
                issues.append(f"Unknown table '{t.value}'")
            elif schema.column(table, nxt.value) is None:
                issues.append(f"Column [{nxt.value}] does not exist in '{table}'")
            else:
                columns.append((table, schema.column(table, nxt.value)))
        elif t.kind == "bracket" and not (prev is not None and prev.kind in ("ident", "table") and (prev.kind == "table" or prev.value.upper() not in FUNCTIONS)):
            name = measures.get(t.value.lower())
            if name is not None:
                deps.append(name)
            elif not (schema.any_column(t.value) or t.value in strings):
                issues.append(f"Unknown measure [{t.value}]")
        elif t.kind == "ident" and nxt is not None and nxt.kind == "op" and nxt.value == "(":
            if t.value.upper() not in FUNCTIONS:
                issues.append(f"Unknown function {t.value}()")
            elif t.value.upper() in TIME_FUNCTIONS:
                time_intel = True
        elif t.kind == "ident":
            upper = t.value.upper()
            if upper in KEYWORDS or t.value.lower() in variables or upper in FUNCTIONS:
                continue
            if schema.table(t.value) is None:
                issues.append(f"Unknown name '{t.value}'")
        elif t.kind == "table" and schema.table(t.value) is None:
            issues.append(f"Unknown table '{t.value}'")
    return CheckResult(list(dict.fromkeys(issues)), list(dict.fromkeys(deps)), columns, time_intel)


def find_cycles(graph: dict[str, list[str]]) -> dict[str, list[str]]:
    """{measure: cycle path} for every measure that is part of (or depends on) a cycle."""
    state: dict[str, int] = {}
    cyclic: dict[str, list[str]] = {}

    def visit(node: str, path: list[str]) -> None:
        if state.get(node) == 1:
            cycle = path[path.index(node):] + [node]
            for n in cycle:
                cyclic.setdefault(n, cycle)
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        for dep in graph.get(node, []):
            visit(dep, path + [node])
        state[node] = 2

    for node in graph:
        visit(node, [])
    return cyclic

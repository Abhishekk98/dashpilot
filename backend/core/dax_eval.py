"""A small DAX interpreter over pandas, used to show a "Calculated Value" for each measure.

It covers the patterns DashPilot generates and the common hand-written ones: aggregations,
DIVIDE / arithmetic, IF, VAR ... RETURN, CALCULATE with column filters and ALL, simple iterators
(SUMX/AVERAGEX/... over a table) and time intelligence (YTD/QTD/MTD, same period last year,
DATESINPERIOD, PREVIOUSYEAR). Anything else raises `Unsupported`, which the UI shows as
"Check Edge Cases" instead of a value. Filters flow from a dimension to the fact through the
model's active relationships, like single-direction filtering in Power BI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
import pandas as pd

from core.dax_validate import Token, tokenize


class Unsupported(Exception):
    """The expression uses a DAX feature this evaluator does not model."""


class EvalError(Exception):
    """The expression cannot be evaluated (e.g. a reference that does not resolve)."""


# --- AST ------------------------------------------------------------------------------

@dataclass
class Num:
    value: float


@dataclass
class Str:
    value: str


@dataclass
class ColRef:
    table: str | None
    column: str


@dataclass
class MeasureRef:
    name: str


@dataclass
class Name:
    name: str  # table or variable


@dataclass
class Call:
    fn: str
    args: list


@dataclass
class BinOp:
    op: str
    left: Any
    right: Any


@dataclass
class Unary:
    op: str
    operand: Any


@dataclass
class ListLit:
    items: list


@dataclass
class VarBlock:
    names: list[tuple[str, Any]]
    body: Any


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.t = tokens
        self.i = 0

    def peek(self, offset: int = 0) -> Token | None:
        j = self.i + offset
        return self.t[j] if j < len(self.t) else None

    def take(self) -> Token:
        tok = self.peek()
        if tok is None:
            raise EvalError("Unexpected end of formula")
        self.i += 1
        return tok

    def accept(self, value: str) -> bool:
        tok = self.peek()
        if tok is not None and tok.kind in ("op", "ident") and tok.value.upper() == value:
            self.i += 1
            return True
        return False

    def expect(self, value: str) -> None:
        if not self.accept(value):
            tok = self.peek()
            raise EvalError(f"Expected '{value}' near {tok.value if tok else 'end'}")

    def parse(self):
        node = self.expr()
        if self.peek() is not None:
            raise EvalError(f"Unexpected '{self.peek().value}'")
        return node

    def expr(self):
        tok = self.peek()
        if tok is not None and tok.kind == "ident" and tok.value.upper() == "VAR":
            names = []
            while self.accept("VAR"):
                name = self.take().value
                self.expect("=")
                names.append((name.lower(), self.expr_no_var()))
            self.expect("RETURN")
            return VarBlock(names, self.expr())
        return self.expr_no_var()

    def expr_no_var(self):
        return self.or_()

    def or_(self):
        node = self.and_()
        while self.accept("||") or self.accept("OR"):
            node = BinOp("||", node, self.and_())
        return node

    def and_(self):
        node = self.cmp()
        while self.accept("&&") or self.accept("AND"):
            node = BinOp("&&", node, self.cmp())
        return node

    def cmp(self):
        node = self.add()
        tok = self.peek()
        if tok is not None and tok.kind == "op" and tok.value in ("=", "==", "<>", "<", ">", "<=", ">="):
            self.i += 1
            return BinOp("=" if tok.value == "==" else tok.value, node, self.add())
        if tok is not None and tok.kind == "ident" and tok.value.upper() == "IN":
            self.i += 1
            return BinOp("IN", node, self.primary())
        return node

    def add(self):
        node = self.mul()
        while True:
            tok = self.peek()
            if tok is not None and tok.kind == "op" and tok.value in ("+", "-", "&"):
                self.i += 1
                node = BinOp(tok.value, node, self.mul())
            else:
                return node

    def mul(self):
        node = self.unary()
        while True:
            tok = self.peek()
            if tok is not None and tok.kind == "op" and tok.value in ("*", "/", "^"):
                self.i += 1
                node = BinOp(tok.value, node, self.unary())
            else:
                return node

    def unary(self):
        if self.accept("-"):
            return Unary("-", self.unary())
        if self.accept("+"):
            return self.unary()
        tok = self.peek()
        if tok is not None and tok.kind == "ident" and tok.value.upper() == "NOT" and not (self.peek(1) and self.peek(1).value == "("):
            self.i += 1
            return Unary("NOT", self.unary())
        return self.primary()

    def arg(self):
        """A function argument; DAX allows skipped ones, e.g. RANKX(t, [m], , DESC)."""
        tok = self.peek()
        if tok is not None and tok.kind == "op" and tok.value in (",", ")"):
            return None
        return self.expr()

    def primary(self):
        tok = self.take()
        if tok.kind == "number":
            return Num(float(tok.value))
        if tok.kind == "string":
            return Str(tok.value)
        if tok.kind == "bracket":
            return MeasureRef(tok.value)
        if tok.kind == "op" and tok.value == "(":
            node = self.expr()
            self.expect(")")
            return node
        if tok.kind == "op" and tok.value == "{":
            items = []
            if not self.accept("}"):
                items.append(self.expr())
                while self.accept(","):
                    items.append(self.expr())
                self.expect("}")
            return ListLit(items)
        if tok.kind in ("ident", "table"):
            nxt = self.peek()
            if nxt is not None and nxt.kind == "bracket":
                self.i += 1
                return ColRef(tok.value, nxt.value)
            if tok.kind == "ident" and nxt is not None and nxt.kind == "op" and nxt.value == "(":
                self.i += 1
                args = []
                if not self.accept(")"):
                    args.append(self.arg())
                    while self.accept(","):
                        args.append(self.arg())
                    self.expect(")")
                return Call(tok.value.upper(), args)
            return Name(tok.value)
        raise EvalError(f"Unexpected '{tok.value}'")


def parse(expression: str):
    tokens, issues = tokenize(expression)
    if issues:
        raise EvalError(issues[0])
    return _Parser(tokens).parse()


# --- data model -----------------------------------------------------------------------

@dataclass
class Link:
    """Active relationship: many_table[many_col] -> one_table[one_col]."""

    many_table: str
    many_col: str
    one_table: str
    one_col: str


@dataclass
class Data:
    frames: dict[str, pd.DataFrame]  # canonical table name -> frame
    links: list[Link]
    date_table: str | None
    measures: dict[str, str]  # lower name -> expression

    def table(self, name: str) -> str:
        for t in self.frames:
            if t.lower() == name.lower():
                return t
        raise EvalError(f"Unknown table {name}")

    def column(self, table: str, column: str) -> str:
        for c in self.frames[table].columns:
            if str(c).lower() == column.lower():
                return str(c)
        raise EvalError(f"Unknown column {table}[{column}]")


@dataclass(frozen=True)
class Filter:
    table: str
    column: str
    op: str
    values: tuple


@dataclass
class Ctx:
    filters: tuple[Filter, ...] = ()
    window: tuple[pd.Timestamp, pd.Timestamp] | None = None  # inclusive date range on the date table
    cleared: frozenset[str] = frozenset()  # tables whose filters ALL()/REMOVEFILTERS removed
    row: tuple[str, pd.Series] | None = None  # (table, row) inside an iterator
    variables: dict[str, Any] = field(default_factory=dict)


def _pred(series: pd.Series, f: Filter) -> pd.Series:
    if f.op == "IN":
        if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
            return series.isin([v for v in f.values])
        return series.astype("string").isin([str(v) for v in f.values]).fillna(False)
    value = f.values[0]
    if isinstance(value, bool) and not pd.api.types.is_bool_dtype(series):
        text = series.astype("string").str.lower()
        truthy = text.isin(["true", "yes", "y", "t", "1"])
        return truthy.fillna(False) if value else (~truthy).fillna(False)
    if isinstance(value, str) and not pd.api.types.is_string_dtype(series) and not pd.api.types.is_object_dtype(series):
        try:
            value = float(value)
        except ValueError:
            return pd.Series(False, index=series.index)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and not pd.api.types.is_numeric_dtype(series):
        series = pd.to_numeric(series, errors="coerce")
    if isinstance(value, str):
        series = series.astype("string")
    ops = {"=": series == value, "<>": series != value, "<": series < value, ">": series > value, "<=": series <= value, ">=": series >= value}
    return ops[f.op].fillna(False).astype(bool)


class Evaluator:
    def __init__(self, data: Data):
        self.d = data
        self.cache: dict[tuple, Any] = {}

    # -- rows of a table in a filter context --------------------------------------------
    def rows(self, table: str, ctx: Ctx) -> pd.DataFrame:
        df = self.d.frames[table]
        mask = pd.Series(True, index=df.index)
        for f in ctx.filters:
            if f.table in ctx.cleared:
                continue
            if f.table == table:
                mask &= _pred(df[f.column], f)
                continue
            for link in self.d.links:
                if link.many_table == table and link.one_table == f.table:
                    one = self.d.frames[f.table]
                    allowed = one.loc[_pred(one[f.column], f), link.one_col].dropna().astype(str)
                    mask &= df[link.many_col].astype(str).isin(set(allowed))
        if ctx.window is not None and self.d.date_table and self.d.date_table not in ctx.cleared:
            start, end = ctx.window
            if table == self.d.date_table:
                dates = df["Date"]
                mask &= (dates >= start) & (dates <= end)
            else:
                for link in self.d.links:
                    if link.many_table == table and link.one_table == self.d.date_table:
                        dates = pd.to_datetime(df[link.many_col], errors="coerce").dt.normalize()
                        mask &= ((dates >= start) & (dates <= end)).fillna(False)
                        break
        return df[mask.to_numpy()]

    def max_date(self, ctx: Ctx) -> pd.Timestamp:
        if not self.d.date_table:
            raise Unsupported("no date table")
        dates = self.rows(self.d.date_table, ctx)["Date"]
        # The visible range is the data's own dates, not the padded calendar.
        data_dates = []
        for link in self.d.links:
            if link.one_table == self.d.date_table:
                data_dates.append(pd.to_datetime(self.rows(link.many_table, ctx)[link.many_col], errors="coerce"))
        if data_dates:
            all_dates = pd.concat(data_dates).dropna()
            if not all_dates.empty:
                return all_dates.max().normalize()
        if dates.empty:
            raise EvalError("no dates in context")
        return dates.max()

    def _window(self, ctx: Ctx) -> tuple[pd.Timestamp, pd.Timestamp]:
        if ctx.window is not None:
            return ctx.window
        dates = self.d.frames[self.d.date_table]["Date"] if self.d.date_table else None
        if dates is None or dates.empty:
            raise Unsupported("time intelligence without a date table")
        return dates.min(), self.max_date(ctx)

    # -- evaluation ------------------------------------------------------------------------
    def measure(self, name: str, ctx: Ctx, stack: tuple = ()):
        key = name.lower()
        if key in stack:
            raise EvalError(f"circular reference [{name}]")
        expr = self.d.measures.get(key)
        if expr is None:
            raise EvalError(f"unknown measure [{name}]")
        if ctx.row is not None:
            raise Unsupported("measure inside an iterator (context transition)")
        cache_key = (key, ctx.filters, ctx.window, ctx.cleared)
        if cache_key not in self.cache:
            self.cache[cache_key] = self.eval(parse(expr), replace(ctx, variables={}), stack + (key,))
        return self.cache[cache_key]

    def eval(self, node, ctx: Ctx, stack: tuple = ()):
        if isinstance(node, Num):
            return node.value
        if isinstance(node, Str):
            return node.value
        if isinstance(node, ListLit):
            return [self.eval(n, ctx, stack) for n in node.items]
        if isinstance(node, VarBlock):
            variables = dict(ctx.variables)
            for name, value_node in node.names:
                variables[name] = self.eval(value_node, replace(ctx, variables=variables), stack)
            return self.eval(node.body, replace(ctx, variables=variables), stack)
        if isinstance(node, Name):
            if node.name.lower() in ctx.variables:
                return ctx.variables[node.name.lower()]
            raise Unsupported(f"table expression {node.name}")
        if isinstance(node, MeasureRef):
            if node.name.lower() in self.d.measures:
                return self.measure(node.name, ctx, stack)
            if ctx.row is not None:
                table, row = ctx.row
                return self._value(row[self.d.column(table, node.name)])
            raise EvalError(f"unknown measure [{node.name}]")
        if isinstance(node, ColRef):
            if ctx.row is None:
                raise Unsupported("column reference outside a row context")
            table, row = ctx.row
            if self.d.table(node.table or table) != table:
                raise Unsupported("RELATED-style column from another table")
            return self._value(row[self.d.column(table, node.column)])
        if isinstance(node, Unary):
            v = self.eval(node.operand, ctx, stack)
            if node.op == "NOT":
                return not bool(v)
            return None if v is None else -v
        if isinstance(node, BinOp):
            return self._binop(node, ctx, stack)
        if isinstance(node, Call):
            return self._call(node, ctx, stack)
        raise Unsupported(type(node).__name__)

    @staticmethod
    def _value(v):
        if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)):
            return None
        if isinstance(v, (np.integer, np.floating)):
            return float(v)
        if isinstance(v, np.bool_):
            return bool(v)
        return v

    def _binop(self, node: BinOp, ctx: Ctx, stack: tuple):
        if node.op == "IN":
            raise Unsupported("IN outside CALCULATE")
        a, b = self.eval(node.left, ctx, stack), self.eval(node.right, ctx, stack)
        if node.op == "&&":
            return bool(a) and bool(b)
        if node.op == "||":
            return bool(a) or bool(b)
        if node.op == "&":
            return f"{'' if a is None else a}{'' if b is None else b}"
        if node.op in ("=", "<>", "<", ">", "<=", ">="):
            if a is None or b is None:
                return node.op == "=" and a == b
            return {"=": a == b, "<>": a != b, "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[node.op]
        # DAX treats blank as 0 in arithmetic
        if a is None and b is None:
            return None
        a, b = a or 0.0, b or 0.0
        if isinstance(a, pd.Timestamp) or isinstance(b, pd.Timestamp):
            raise Unsupported("date arithmetic")
        if node.op == "+":
            return a + b
        if node.op == "-":
            return a - b
        if node.op == "*":
            return a * b
        if node.op == "^":
            return a ** b
        if b == 0:
            raise EvalError("division by zero (use DIVIDE for a safe ratio)")
        return a / b

    # -- functions ---------------------------------------------------------------------
    def _col(self, node) -> tuple[str, str]:
        if not isinstance(node, ColRef) or node.table is None:
            raise Unsupported("aggregate over an expression")
        table = self.d.table(node.table)
        return table, self.d.column(table, node.column)

    def _table_arg(self, node, ctx: Ctx) -> tuple[str, pd.DataFrame]:
        if isinstance(node, Name):
            table = self.d.table(node.name)
            return table, self.rows(table, ctx)
        if isinstance(node, Call) and node.fn == "FILTER" and len(node.args) == 2:
            table, rows = self._table_arg(node.args[0], ctx)
            keep = [bool(self.eval(node.args[1], replace(ctx, row=(table, r)))) for _, r in rows.iterrows()]
            return table, rows[keep]
        if isinstance(node, Call) and node.fn in ("ALL", "REMOVEFILTERS") and node.args and isinstance(node.args[0], Name):
            table = self.d.table(node.args[0].name)
            return table, self.rows(table, replace(ctx, cleared=ctx.cleared | {table}))
        raise Unsupported("table expression")

    def _numbers(self, table: str, column: str, ctx: Ctx) -> pd.Series:
        values = self.rows(table, ctx)[column]
        if pd.api.types.is_bool_dtype(values):
            return values.astype(float)
        if pd.api.types.is_datetime64_any_dtype(values):
            return values
        return pd.to_numeric(values, errors="coerce")

    def _call(self, node: Call, ctx: Ctx, stack: tuple):
        fn, args = node.fn, node.args
        ev = lambda n, c=ctx: self.eval(n, c, stack)  # noqa: E731

        if fn in ("SUM", "AVERAGE", "MIN", "MAX", "MEDIAN") and len(args) == 1:
            if fn == "MAX" and isinstance(args[0], ColRef) and self.d.date_table and self.d.table(args[0].table) == self.d.date_table:
                return self.max_date(ctx)
            table, column = self._col(args[0])
            values = self._numbers(table, column, ctx).dropna()
            if values.empty:
                return None
            result = {"SUM": values.sum, "AVERAGE": values.mean, "MIN": values.min, "MAX": values.max, "MEDIAN": values.median}[fn]()
            return self._value(result)
        if fn in ("MAX", "MIN") and len(args) == 2:
            a, b = ev(args[0]), ev(args[1])
            if a is None or b is None:
                return a if b is None else b
            return max(a, b) if fn == "MAX" else min(a, b)
        if fn in ("COUNT", "COUNTA") and len(args) == 1:
            table, column = self._col(args[0])
            return float(self.rows(table, ctx)[column].notna().sum()) or None
        if fn == "COUNTBLANK" and len(args) == 1:
            table, column = self._col(args[0])
            return float(self.rows(table, ctx)[column].isna().sum())
        if fn in ("DISTINCTCOUNT", "DISTINCTCOUNTNOBLANK", "APPROXIMATEDISTINCTCOUNT") and len(args) == 1:
            table, column = self._col(args[0])
            values = self.rows(table, ctx)[column]
            n = values.dropna().astype(str).nunique() + (1 if fn == "DISTINCTCOUNT" and values.isna().any() else 0)
            return float(n) or None
        if fn == "COUNTROWS" and len(args) == 1:
            _, rows = self._table_arg(args[0], ctx)
            return float(len(rows)) or None
        if fn in ("SUMX", "AVERAGEX", "MINX", "MAXX", "COUNTX") and len(args) == 2:
            table, rows = self._table_arg(args[0], ctx)
            values = [ev(args[1], replace(ctx, row=(table, r))) for _, r in rows.iterrows()]
            values = [v for v in values if v is not None]
            if not values:
                return None
            return {"SUMX": sum, "AVERAGEX": lambda v: sum(v) / len(v), "MINX": min, "MAXX": max, "COUNTX": len}[fn](values)
        if fn == "DIVIDE" and len(args) in (2, 3):
            a, b = ev(args[0]), ev(args[1])
            if b in (None, 0, 0.0):
                return ev(args[2]) if len(args) == 3 else None
            return None if a is None else a / b
        if fn == "IF" and len(args) in (2, 3):
            return ev(args[1]) if ev(args[0]) else (ev(args[2]) if len(args) == 3 else None)
        if fn == "COALESCE" and args:
            for a in args:
                v = ev(a)
                if v is not None:
                    return v
            return None
        if fn in ("BLANK",):
            return None
        if fn == "TRUE":
            return True
        if fn == "FALSE":
            return False
        if fn == "ISBLANK" and len(args) == 1:
            return ev(args[0]) is None
        if fn == "ABS" and len(args) == 1:
            v = ev(args[0])
            return None if v is None else abs(v)
        if fn == "ROUND" and len(args) == 2:
            v = ev(args[0])
            return None if v is None else round(v, int(ev(args[1]) or 0))
        if fn == "CALCULATE" and args:
            return ev(args[0], self._apply_filters(args[1:], ctx, stack))
        if fn in ("TOTALYTD", "TOTALQTD", "TOTALMTD") and len(args) >= 2:
            period = {"TOTALYTD": "DATESYTD", "TOTALQTD": "DATESQTD", "TOTALMTD": "DATESMTD"}[fn]
            return ev(args[0], self._apply_filters([Call(period, [args[1]])], ctx, stack))
        raise Unsupported(f"{fn}()")

    def _apply_filters(self, filters: list, ctx: Ctx, stack: tuple) -> Ctx:
        new = ctx
        for f in filters:
            if isinstance(f, BinOp) and isinstance(f.left, ColRef) and f.op in ("=", "<>", "<", ">", "<=", ">=", "IN"):
                table, column = self._col(f.left)
                right = self.eval(f.right, ctx, stack)
                values = tuple(right) if f.op == "IN" else (right,)
                kept = tuple(x for x in new.filters if not (x.table == table and x.column == column))
                new = replace(new, filters=kept + (Filter(table, column, f.op, values),), cleared=new.cleared - {table})
            elif isinstance(f, Call) and f.fn in ("ALL", "REMOVEFILTERS") and f.args and isinstance(f.args[0], Name):
                table = self.d.table(f.args[0].name)
                new = replace(new, filters=tuple(x for x in new.filters if x.table != table),
                              window=None if table == self.d.date_table else new.window)
            elif isinstance(f, Call) and f.fn in ("ALL", "REMOVEFILTERS") and f.args and isinstance(f.args[0], ColRef):
                table, column = self._col(f.args[0])
                new = replace(new, filters=tuple(x for x in new.filters if not (x.table == table and x.column == column)))
            elif isinstance(f, Call) and f.fn in ("DATESYTD", "DATESQTD", "DATESMTD", "SAMEPERIODLASTYEAR", "PREVIOUSYEAR", "DATESINPERIOD"):
                new = replace(new, window=self._time_window(f, new, stack))
            elif isinstance(f, Call) and f.fn == "USERELATIONSHIP":
                raise Unsupported("USERELATIONSHIP")
            else:
                raise Unsupported("filter expression")
        return new

    def _time_window(self, f: Call, ctx: Ctx, stack: tuple) -> tuple[pd.Timestamp, pd.Timestamp]:
        start, end = self._window(ctx)
        if f.fn == "DATESYTD":
            return pd.Timestamp(end.year, 1, 1), end
        if f.fn == "DATESQTD":
            return pd.Timestamp(end.year, 3 * ((end.month - 1) // 3) + 1, 1), end
        if f.fn == "DATESMTD":
            return pd.Timestamp(end.year, end.month, 1), end
        if f.fn == "SAMEPERIODLASTYEAR":
            return start - pd.DateOffset(years=1), end - pd.DateOffset(years=1)
        if f.fn == "PREVIOUSYEAR":
            return pd.Timestamp(start.year - 1, 1, 1), pd.Timestamp(start.year - 1, 12, 31)
        # DATESINPERIOD(dates, anchor, n, interval)
        if len(f.args) != 4 or not isinstance(f.args[3], Name):
            raise Unsupported("DATESINPERIOD form")
        anchor = self.eval(f.args[1], ctx, stack)
        n = int(self.eval(f.args[2], ctx, stack) or 0)
        unit = f.args[3].name.upper()
        offset = {"DAY": pd.DateOffset(days=abs(n)), "MONTH": pd.DateOffset(months=abs(n)), "QUARTER": pd.DateOffset(months=3 * abs(n)), "YEAR": pd.DateOffset(years=abs(n))}.get(unit)
        if offset is None or not isinstance(anchor, pd.Timestamp):
            raise Unsupported("DATESINPERIOD interval")
        return (anchor - offset + pd.Timedelta(days=1), anchor) if n < 0 else (anchor, anchor + offset - pd.Timedelta(days=1))


def date_frame(start: str, end: str, fiscal_start: int) -> pd.DataFrame:
    """The auto date table (same columns as core/tmdl.py) as a DataFrame."""
    dates = pd.date_range(start, end, freq="D")
    fy = dates.year + (dates.month >= fiscal_start).astype(int) if fiscal_start != 1 else dates.year
    return pd.DataFrame({
        "Date": dates,
        "Year": dates.year,
        "Quarter": "Q" + dates.quarter.astype(str),
        "Month Number": dates.month,
        "Month Name": dates.month_name(),
        "Year Month": dates.strftime("%Y-%m"),
        "Week of Year": dates.isocalendar().week.to_numpy(),
        "Day": dates.day,
        "Day of Week Number": dates.dayofweek + 1,
        "Day of Week": dates.day_name(),
        "Fiscal Year": "FY" + pd.Index(fy).astype(str),
        "Fiscal Quarter": "FQ" + (((dates.month - fiscal_start) % 12) // 3 + 1).astype(str),
    })

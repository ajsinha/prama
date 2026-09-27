"""Column lineage from pandas jobs, read from the syntax tree.

The same discipline as the PySpark reader: the file is parsed with `ast`, never
executed or imported. A DataFrame is followed from where it is read
(`pd.read_sql_table`, `pd.read_sql` with a literal query) through the
operations whose meaning is certain (column selection, `rename`, a column
assigned from other columns, row filters) to where it is written (`to_sql`).
A merge, a groupby, an `apply`, a column built from a variable: each is a
named gap rather than a guess.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import dataclasses
from collections.abc import Iterator

from prama.lineage.graph import Column, Edge, Transform
from prama.lineage.sql import Extraction, Gap, SqlLineage

#: Methods that keep every column as it is and change only which rows exist.
_ROWS = frozenset(
    {"dropna", "drop_duplicates", "copy", "head", "tail", "query", "sort_values", "reset_index"}
)
#: Methods on a column that leave the value essentially itself.
_RENAMES = frozenset({"astype", "fillna", "round", "strip", "upper", "lower", "abs"})
#: The frame SQL is read into, so a query's output columns can be named.
_QUERY = "__pandas_query__"

Columns = dict[str, tuple[set[Column], Transform]]


@dataclasses.dataclass
class _Frame:
    """A DataFrame: each output column's inputs, or a whole table unchanged."""

    #: A table read whole: its columns are not known until one is named.
    table: str | None = None
    columns: Columns | None = None

    def lookup(self, name: str) -> tuple[set[Column], Transform] | None:
        key = name.lower()
        if self.columns is not None:
            found = self.columns.get(key)
            return (set(found[0]), found[1]) if found else None
        if self.table:
            return {Column(dataset=self.table, name=key)}, Transform.IDENTITY
        return None


def _string(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _strings(node: ast.AST) -> list[str] | None:
    if isinstance(node, ast.List | ast.Tuple):
        values = [_string(e) for e in node.elts]
        return [v for v in values if v is not None] if all(values) else None
    return None


def _keyword(node: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in node.keywords if k.arg == name), None)


def _qualified(node: ast.Call, name: str) -> str:
    schema = _string(_keyword(node, "schema"))
    return f"{schema}.{name}" if schema else name


def _statements(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Every statement in source order, into function, `with`, `if` and loop bodies."""
    for statement in body:
        yield statement
        for field in ("body", "orelse", "finalbody"):
            inner = getattr(statement, field, None)
            if isinstance(inner, list) and not isinstance(statement, ast.ClassDef):
                yield from _statements(inner)


class _Reader:
    def __init__(self, job: str) -> None:
        self.job = job
        self.frames: dict[str, _Frame] = {}
        self.edges: list[Edge] = []
        self.gaps: list[Gap] = []

    def gap(self, node: ast.AST, why: str) -> None:
        line = getattr(node, "lineno", "?")
        self.gaps.append(Gap(kind="unread", detail=f"line {line}: {why}", statement=self.job))

    # -- reads --------------------------------------------------------------

    def read(self, node: ast.Call, method: str) -> _Frame | None:
        first = _string(node.args[0]) if node.args else _string(_keyword(node, "sql"))
        if first is None:
            self.gap(node, f"`{method}` of a table or query that is not a literal")
            return None
        if method == "read_sql_table" or " " not in first.strip():
            return _Frame(table=_qualified(node, first))
        extraction = SqlLineage().extract(f"CREATE VIEW {_QUERY} AS {first}", job=self.job)
        columns: Columns = {}
        for edge in extraction.edges:
            if edge.target.dataset != _QUERY or edge.transform in (
                Transform.FILTER,
                Transform.JOIN_KEY,
            ):
                continue
            inputs, how = columns.get(edge.target.name, (set(), edge.transform))
            inputs.add(edge.source)
            columns[edge.target.name] = (inputs, how if len(inputs) == 1 else Transform.DERIVED)
        for gap in extraction.gaps:
            self.gap(node, f"in the query: {gap.detail}")
        return _Frame(columns=columns) if columns else None

    # -- column expressions -------------------------------------------------

    def expression(self, node: ast.AST, frame: _Frame) -> tuple[set[Column], Transform] | None:
        """The input columns of an expression over *frame*, or None if unfollowed."""
        if isinstance(node, ast.Subscript) and (name := _string(node.slice)) is not None:
            if isinstance(node.value, ast.Name) and self.frames.get(node.value.id) is frame:
                return frame.lookup(name)
            return None
        if isinstance(node, ast.Attribute) and node.attr == "str":
            return self.expression(node.value, frame)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _RENAMES:
                inner = self.expression(node.func.value, frame)
                return (inner[0], Transform.RENAME) if inner else None
            return None
        if isinstance(node, ast.BinOp):
            parts = [self.expression(node.left, frame), self.expression(node.right, frame)]
            if any(
                p is None and not isinstance(s, ast.Constant)
                for p, s in zip(parts, (node.left, node.right), strict=True)
            ):
                return None
            inputs: set[Column] = set().union(*(p[0] for p in parts if p))
            return inputs, Transform.DERIVED
        return None

    # -- frames -------------------------------------------------------------

    def frame(self, node: ast.AST) -> _Frame | None:
        """The DataFrame an expression evaluates to, if its meaning is certain."""
        if isinstance(node, ast.Name):
            return self.frames.get(node.id)
        if isinstance(node, ast.Subscript):
            base = self.frame(node.value)
            if base is None:
                return None
            names = _strings(node.slice)
            if names is None:
                return base  # a boolean mask: which rows, not which columns
            columns: Columns = {}
            for name in names:
                found = base.lookup(name)
                if found is None:
                    self.gap(node, f"the column {name!r} could not be traced")
                    continue
                columns[name.lower()] = found
            return _Frame(columns=columns)
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            return None
        method = node.func.attr
        if method in ("read_sql_table", "read_sql", "read_sql_query"):
            return self.read(node, method)
        base = self.frame(node.func.value)
        if base is None:
            if method in ("merge", "join", "groupby", "rename", "assign"):
                self.gap(node, f"`.{method}` on a DataFrame whose source could not be followed")
            return None
        if method in _ROWS:
            return base
        if method == "rename":
            return self.renamed(node, base)
        if method in ("merge", "join", "groupby", "pivot", "pivot_table", "apply", "melt"):
            self.gap(node, f"`.{method}`: its column provenance is not followed yet")
            return None
        self.gap(node, f"`.{method}` is not an operation this reader follows")
        return None

    def renamed(self, node: ast.Call, base: _Frame) -> _Frame | None:
        mapping = _keyword(node, "columns")
        if not isinstance(mapping, ast.Dict):
            self.gap(node, "a rename whose mapping is not a literal")
            return None
        columns: Columns = dict(base.columns or {})
        for key, value in zip(mapping.keys, mapping.values, strict=True):
            old, new = _string(key) if key else None, _string(value)
            found = base.lookup(old) if old else None
            if old is None or new is None or found is None:
                self.gap(node, "a renamed column that could not be traced")
                continue
            columns.pop(old.lower(), None)
            columns[new.lower()] = (found[0], Transform.RENAME)
        if base.columns is None and base.table:
            # The table's other columns are carried but unnamed; only the
            # renamed ones are known, and a write names what it writes.
            return (
                _Frame(table=base.table, columns=None)
                if not columns
                else _Frame(table=base.table, columns=columns)
            )
        return _Frame(columns=columns)

    # -- statements ---------------------------------------------------------

    def assign_column(self, statement: ast.Assign, target: ast.Subscript) -> None:
        """`df["c"] = <expression over df's columns>`."""
        if not isinstance(target.value, ast.Name) or target.value.id not in self.frames:
            return
        name = _string(target.slice)
        frame = self.frames[target.value.id]
        if name is None:
            self.gap(statement, "a column assigned by a name that is not a literal")
            return
        computed = self.expression(statement.value, frame)
        if computed is None:
            self.gap(
                statement, f"the column {name!r} is built in a way this reader does not follow"
            )
            return
        columns = dict(frame.columns or {})
        columns[name.lower()] = computed
        frame.columns = columns if frame.columns is not None or not frame.table else None
        if frame.columns is None:
            self.gap(
                statement,
                f"{name!r} is added to all of {frame.table!r}; its other columns are not named",
            )

    def write(self, node: ast.Call) -> None:
        target = _string(node.args[0]) if node.args else _string(_keyword(node, "name"))
        receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
        frame = self.frame(receiver) if receiver is not None else None
        if target is None or frame is None:
            self.gap(node, "a `to_sql` whose DataFrame or table could not be followed")
            return
        target = _qualified(node, target)
        if frame.columns is None:
            self.gap(node, f"{target!r} is written from {frame.table!r} with unnamed columns")
            return
        for output, (inputs, transform) in frame.columns.items():
            for source in sorted(inputs, key=lambda c: (c.dataset, c.name)):
                self.edges.append(
                    Edge(
                        source=source,
                        target=Column(dataset=target, name=output),
                        transform=transform,
                        produced_by=self.job,
                        expression=f"line {node.lineno}",
                    )
                )

    def visit(self, tree: ast.Module) -> None:
        for statement in _statements(tree.body):
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                target = statement.targets[0]
                if isinstance(target, ast.Name):
                    frame = self.frame(statement.value)
                    if frame is not None:
                        self.frames[target.id] = frame
                    else:
                        self.frames.pop(target.id, None)
                elif isinstance(target, ast.Subscript):
                    self.assign_column(statement, target)
            if isinstance(statement, ast.Expr | ast.Assign):
                for node in ast.walk(statement):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        if node.func.attr == "to_sql":
                            self.write(node)
                        elif _keyword(node, "inplace") is not None:
                            self.gap(node, f"`.{node.func.attr}(inplace=True)` is not followed")


def extract(source: str, *, job: str = "") -> Extraction:
    """Lineage from one pandas file's text. Never executes it."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return Extraction(
            gaps=(Gap(kind="unparsed", detail=f"not valid Python: {exc.msg}", statement=job),),
            statements=1,
        )
    reader = _Reader(job)
    reader.visit(tree)
    return Extraction(edges=tuple(reader.edges), gaps=tuple(reader.gaps), statements=1)

"""Column lineage from PySpark jobs, read from the syntax tree.

The job is parsed with `ast`, never executed or imported. A DataFrame is
followed from where it is read (`spark.table`, `spark.read.table`) through the
transformations whose meaning is certain (`select`, `alias`, `withColumn`,
`withColumnRenamed`, `groupBy(...).agg(...)`, `filter`/`where`) to where it is
written (`saveAsTable`, `insertInto`). Anything else is a named gap: a join,
a UDF, a column built from a variable. A guessed edge would be worse than a
reported gap, because an impact analysis would trust it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import dataclasses

from prama.lineage.graph import Column, Edge, Transform
from prama.lineage.sql import Extraction, Gap

_AGGREGATES = frozenset({"sum", "avg", "mean", "count", "min", "max", "first", "last", "stddev"})
_RENAMES = frozenset({"cast", "trim", "upper", "lower", "coalesce"})


@dataclasses.dataclass
class _Frame:
    """A DataFrame: the dataset it reads, and each output column's inputs."""

    dataset: str
    #: output column -> (input columns, transform). None means "all columns
    #: of the source, unchanged", which is what a bare table read is.
    columns: dict[str, tuple[set[str], Transform]] | None = None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class _Reader:
    def __init__(self, job: str) -> None:
        self.job = job
        self.frames: dict[str, _Frame] = {}
        self.edges: list[Edge] = []
        self.gaps: list[Gap] = []

    def gap(self, node: ast.AST, why: str) -> None:
        self.gaps.append(
            Gap(
                kind="unread",
                detail=f"line {getattr(node, 'lineno', '?')}: {why}",
                statement=self.job,
            )
        )

    # -- column expressions -------------------------------------------------

    def column(self, node: ast.AST, frame: _Frame) -> tuple[str, set[str], Transform] | None:
        """(output name, inputs, transform) for one select argument."""
        name = _string(node)
        if name is not None:
            inputs, how = self._lookup(name, frame)
            return name, inputs, how
        if (
            isinstance(node, ast.Call)
            and _call_name(node) == "alias"
            and isinstance(node.func, ast.Attribute)
        ):
            alias = _string(node.args[0]) if node.args else None
            inner = self.expression(node.func.value, frame)
            if alias is None or inner is None:
                return None
            return alias, inner[0], inner[1]
        inner = self.expression(node, frame)
        if inner is None or len(inner[0]) != 1:
            return None
        (only,) = inner[0]
        return only, inner[0], inner[1]

    def expression(self, node: ast.AST, frame: _Frame) -> tuple[set[str], Transform] | None:
        """The input columns and transform of a column expression, or None."""
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name == "col" and node.args and (column := _string(node.args[0])) is not None:
                return self._lookup(column, frame)
            if name in _AGGREGATES and node.args:
                inner = self.expression(node.args[0], frame)
                return (inner[0], Transform.AGGREGATED) if inner else None
            if name in _RENAMES and isinstance(node.func, ast.Attribute):
                inner = self.expression(node.func.value, frame) or (
                    self.expression(node.args[0], frame) if node.args else None
                )
                return (inner[0], Transform.RENAME) if inner else None
            return None
        if isinstance(node, ast.BinOp):
            left, right = self.expression(node.left, frame), self.expression(node.right, frame)
            parts = [p for p in (left, right) if p]
            if not parts:
                return None
            return set().union(*(p[0] for p in parts)), Transform.DERIVED
        if isinstance(node, ast.Constant):
            return set(), Transform.DERIVED
        return None

    def _lookup(self, column: str, frame: _Frame) -> tuple[set[str], Transform]:
        """A column's inputs, and how it was made: a column carried forward
        keeps its transform (a renamed column selected later is still renamed)."""
        if frame.columns is not None and column.lower() in frame.columns:
            inputs, how = frame.columns[column.lower()]
            return set(inputs), how
        return {column.lower()}, Transform.IDENTITY

    def _inputs(self, column: str, frame: _Frame) -> set[str]:
        if frame.columns is None:
            return {column.lower()}
        known = frame.columns.get(column.lower())
        return set(known[0]) if known else {column.lower()}

    # -- DataFrame chains ---------------------------------------------------

    def frame(self, node: ast.AST) -> _Frame | None:
        """The DataFrame an expression evaluates to, if its meaning is certain."""
        if isinstance(node, ast.Name):
            return self.frames.get(node.id)
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            return None
        method, receiver = node.func.attr, node.func.value
        if method == "table" and node.args and (name := _string(node.args[0])):
            return _Frame(dataset=name)
        base = self.frame(receiver)
        if base is None:
            if method in ("select", "withColumn", "join", "agg"):
                self.gap(node, f"`.{method}` on a DataFrame whose source could not be followed")
            return None
        if method in ("filter", "where", "distinct", "orderBy", "sort", "limit", "cache", "alias"):
            return base
        if method == "select":
            columns: dict[str, tuple[set[str], Transform]] = {}
            for argument in node.args:
                read = self.column(argument, base)
                if read is None:
                    self.gap(
                        argument, "a selected column built in a way this reader does not follow"
                    )
                    continue
                columns[read[0].lower()] = (read[1], read[2])
            return _Frame(base.dataset, columns)
        if method == "withColumn" and len(node.args) == 2 and (name := _string(node.args[0])):
            computed = self.expression(node.args[1], base)
            if computed is None:
                self.gap(node, f"the column {name!r} is built in a way this reader does not follow")
                return base
            return _Frame(base.dataset, {**(base.columns or {}), name.lower(): computed})
        if method == "withColumnRenamed" and len(node.args) == 2:
            old, new = _string(node.args[0]), _string(node.args[1])
            if old and new:
                columns = dict(base.columns or {})
                columns[new.lower()] = (self._inputs(old, base), Transform.RENAME)
                columns.pop(old.lower(), None)
                return _Frame(base.dataset, columns)
        if method == "agg":
            # `groupBy(...)` passes its frame through; `agg` defines the output.
            columns = {}
            for argument in node.args:
                read = self.column(argument, base)
                if read is None:
                    self.gap(argument, "an aggregate this reader does not follow")
                    continue
                columns[read[0].lower()] = (read[1], read[2])
            return _Frame(base.dataset, columns)
        if method == "groupBy":
            return base
        if method == "join":
            self.gap(node, "a join: its column provenance is not followed yet")
            return None
        self.gap(node, f"`.{method}` is not a transformation this reader follows")
        return None

    def write(self, node: ast.Call) -> None:
        """`<frame>.write[.mode(...)].saveAsTable("t")` or `.insertInto("t")`."""
        target = _string(node.args[0]) if node.args else None
        chain = node.func.value if isinstance(node.func, ast.Attribute) else None
        while isinstance(chain, ast.Call) and _call_name(chain) in (
            "mode",
            "format",
            "option",
            "partitionBy",
        ):
            chain = chain.func.value if isinstance(chain.func, ast.Attribute) else None
        if not (isinstance(chain, ast.Attribute) and chain.attr == "write") or target is None:
            self.gap(node, "a write whose DataFrame or target is not a literal")
            return
        frame = self.frame(chain.value)
        if frame is None:
            self.gap(node, f"a write to {target!r} from a DataFrame that could not be followed")
            return
        if frame.columns is None:
            self.gap(
                node,
                f"{target!r} is written from {frame.dataset!r} unchanged; "
                "its columns are not named",
            )
            return
        for output, (inputs, transform) in frame.columns.items():
            for source in sorted(inputs):
                self.edges.append(
                    Edge(
                        source=Column(dataset=frame.dataset, name=source),
                        target=Column(dataset=target, name=output),
                        transform=transform,
                        produced_by=self.job,
                        expression=f"line {node.lineno}",
                    )
                )

    def visit(self, tree: ast.Module) -> None:
        """Statements in source order, so a name is bound before it is written from."""
        for statement in tree.body:
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                target = statement.targets[0]
                if isinstance(target, ast.Name):
                    frame = self.frame(statement.value)
                    if frame is not None:
                        self.frames[target.id] = frame
            for node in ast.walk(statement):
                if isinstance(node, ast.Call) and _call_name(node) in ("saveAsTable", "insertInto"):
                    self.write(node)


def extract(source: str, *, job: str = "") -> Extraction:
    """Lineage from one PySpark file's text. Never executes it."""
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

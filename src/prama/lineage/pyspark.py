"""Column lineage from PySpark jobs, read from the syntax tree.

The job is parsed with `ast`, never executed or imported. A DataFrame is
followed from where it is read (`spark.table`, `spark.read.table`) through the
transformations whose meaning is certain (`select`, `alias`, `withColumn`,
`withColumnRenamed`, `groupBy(...).agg(...)`, `filter`/`where`) to where it is
written (`saveAsTable`, `insertInto`). A join is followed: its key pairs
become join-key edges into the written table's rows, and a column after it is
taken from the side that provably has it. Anything else is a named gap: a UDF, a
column built from a variable, a name either side of a join could hold. A guessed
edge would be worse than a reported gap, because an impact analysis would trust it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import dataclasses

from prama.lineage.graph import Column, Edge, Transform
from prama.lineage.sql import Extraction, Gap

_AGGREGATES = frozenset({"sum", "avg", "mean", "count", "min", "max", "first", "last", "stddev"})
_RENAMES = frozenset({"cast", "trim", "upper", "lower", "coalesce"})
#: Join kinds that decide which rows exist, as `prama.lineage.parsed` names them.
_JOIN_KINDS = {"inner": "inner", "left": "left", "left_outer": "left", "leftouter": "left"}

#: A column input: (dataset, column).
Input = tuple[str, str]


@dataclasses.dataclass
class _Frame:
    """A DataFrame: where its rows come from, and each output column's inputs.

    ``columns`` maps an output column to its inputs and transform; ``None``
    means "all columns of the source, unchanged", which is what a bare table
    read is. A joined frame has ``sides``, the frames it joined, and records
    the join's key pairs in ``joins`` so the write can emit them.
    """

    dataset: str
    columns: dict[str, tuple[set[Input], Transform]] | None = None
    sides: tuple[_Frame, ...] = ()
    #: (kind, driving input, looked-up input), from every join in the chain.
    joins: tuple[tuple[str, Input, Input], ...] = ()


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

    def column(self, node: ast.AST, frame: _Frame) -> tuple[str, set[Input], Transform] | None:
        """(output name, inputs, transform) for one select argument."""
        name = _string(node)
        if name is not None:
            found = self._lookup(name, frame, node)
            return (name, *found) if found else None
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
        ((_, only),) = inner[0]
        return only, inner[0], inner[1]

    def expression(self, node: ast.AST, frame: _Frame) -> tuple[set[Input], Transform] | None:
        """The input columns and transform of a column expression, or None."""
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name == "col" and node.args and (column := _string(node.args[0])) is not None:
                return self._lookup(column, frame, node)
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

    def _lookup(
        self, column: str, frame: _Frame, node: ast.AST | None = None
    ) -> tuple[set[Input], Transform] | None:
        """A column's inputs, and how it was made: a column carried forward
        keeps its transform (a renamed column selected later is still renamed).

        After a join, a column is taken from the side that provably has it. A
        name either side could hold is reported, not guessed: picking one would
        be an edge that is wrong half the time.
        """
        key = column.lower()
        if frame.columns is not None and key in frame.columns:
            inputs, how = frame.columns[key]
            return set(inputs), how
        if not frame.sides:
            return {(frame.dataset, key)}, Transform.IDENTITY
        # A join key named in `on` is the same value on both sides; the driving
        # side's is the one the joined row carries.
        for _, driving, _looked_up in frame.joins:
            if driving[1] == key:
                return {driving}, Transform.IDENTITY
        known = [s for s in frame.sides if s.columns is not None and key in s.columns]
        if len(known) == 1:
            return self._lookup(key, known[0], node)
        bare = [s for s in frame.sides if s.columns is None and not s.sides]
        if not known and len(bare) == 1:
            return self._lookup(key, bare[0], node)
        if node is not None:
            self.gap(
                node,
                f"after a join, {column!r} could come from "
                f"{' or '.join(s.dataset for s in frame.sides)}; nothing says which",
            )
        return None

    def _inputs(self, column: str, frame: _Frame) -> set[Input]:
        found = self._lookup(column, frame)
        return found[0] if found else set()

    # -- joins --------------------------------------------------------------

    def _join(self, node: ast.Call, left: _Frame) -> _Frame | None:
        """`left.join(right, on, how)`: both sides, and the key pairs."""
        if not node.args:
            self.gap(node, "a join with nothing to join")
            return None
        right = self.frame(node.args[0])
        if right is None:
            self.gap(node, "a join to a DataFrame whose source could not be followed")
            return None
        on = node.args[1] if len(node.args) > 1 else None
        how_node = node.args[2] if len(node.args) > 2 else None
        for keyword in node.keywords:
            if keyword.arg == "on":
                on = keyword.value
            elif keyword.arg == "how":
                how_node = keyword.value
        how = (_string(how_node) or "inner").lower() if how_node is not None else "inner"
        kind = _JOIN_KINDS.get(how)
        pairs: list[tuple[Input, Input]] = []
        single = _string(on) if on is not None else None
        names: list[str | None] = [single] if single else []
        if isinstance(on, ast.List | ast.Tuple):
            names = [_string(e) for e in on.elts]
        if names and all(names):
            for name in names:
                driving = self._lookup(str(name), left)
                looked_up = self._lookup(str(name), right)
                if driving and looked_up:
                    pairs.append((next(iter(driving[0])), next(iter(looked_up[0]))))
        elif on is not None:
            for equality in ast.walk(on):
                if isinstance(equality, ast.Compare) and isinstance(equality.ops[0], ast.Eq):
                    sides = [equality.left, equality.comparators[0]]
                    ends = [self._join_side(side, left, right) for side in sides]
                    if all(ends):
                        (a_side, a), (_, b) = ends  # type: ignore[misc]
                        pairs.append((a, b) if a_side == "left" else (b, a))
        if on is None:
            self.gap(node, "a join with no condition: every row meets every row")
        elif not pairs:
            self.gap(node, "a join whose condition this reader does not follow")
        joins = left.joins + right.joins
        if kind is not None:
            joins += tuple((kind, d, lu) for d, lu in pairs if d[0] != lu[0])
        elif pairs:
            self.gap(node, f"a {how} join: which rows survive it is not recorded")
        return _Frame(dataset=left.dataset, sides=(left, right), joins=joins)

    def _join_side(self, node: ast.AST, left: _Frame, right: _Frame) -> tuple[str, Input] | None:
        """`a["k"]`, `a.k` or `a.col` on one side of a join condition."""
        frame_node: ast.AST | None = None
        name: str | None = None
        if isinstance(node, ast.Subscript):
            frame_node, name = node.value, _string(node.slice)
        elif isinstance(node, ast.Attribute):
            frame_node, name = node.value, node.attr
        if frame_node is None or name is None:
            return None
        frame = self.frame(frame_node)
        if frame is None:
            return None
        for side, candidate in (("left", left), ("right", right)):
            if frame.dataset == candidate.dataset and frame.columns == candidate.columns:
                found = self._lookup(name, candidate)
                return (side, next(iter(found[0]))) if found and found[0] else None
        return None

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
            columns: dict[str, tuple[set[Input], Transform]] = {}
            for argument in node.args:
                read = self.column(argument, base)
                if read is None:
                    self.gap(
                        argument, "a selected column built in a way this reader does not follow"
                    )
                    continue
                columns[read[0].lower()] = (read[1], read[2])
            return dataclasses.replace(base, columns=columns)
        if method == "withColumn" and len(node.args) == 2 and (name := _string(node.args[0])):
            computed = self.expression(node.args[1], base)
            if computed is None:
                self.gap(node, f"the column {name!r} is built in a way this reader does not follow")
                return base
            return dataclasses.replace(
                base, columns={**(base.columns or {}), name.lower(): computed}
            )
        if method == "withColumnRenamed" and len(node.args) == 2:
            old, new = _string(node.args[0]), _string(node.args[1])
            if old and new:
                columns = dict(base.columns or {})
                columns[new.lower()] = (self._inputs(old, base), Transform.RENAME)
                columns.pop(old.lower(), None)
                return dataclasses.replace(base, columns=columns)
        if method == "agg":
            # `groupBy(...)` passes its frame through; `agg` defines the output.
            columns = {}
            for argument in node.args:
                read = self.column(argument, base)
                if read is None:
                    self.gap(argument, "an aggregate this reader does not follow")
                    continue
                columns[read[0].lower()] = (read[1], read[2])
            return dataclasses.replace(base, columns=columns)
        if method == "groupBy":
            return base
        if method == "join":
            return self._join(node, base)
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
        # The join keys decide which rows the target holds (see
        # `prama.lineage.parsed._join_edges`, whose pairing text this matches).
        for kind, driving, looked_up in frame.joins:
            pairing = f"{kind} join: {driving[0]}.{driving[1]} = {looked_up[0]}.{looked_up[1]}"
            for side in (driving, looked_up):
                self.edges.append(
                    Edge(
                        source=Column(dataset=side[0], name=side[1]),
                        target=Column(dataset=target, name="*"),
                        transform=Transform.JOIN_KEY,
                        produced_by=self.job,
                        expression=pairing,
                    )
                )
        if frame.columns is None:
            self.gap(
                node,
                f"{target!r} is written from {frame.dataset!r} unchanged; "
                "its columns are not named",
            )
            return
        for output, (inputs, transform) in frame.columns.items():
            for dataset, source in sorted(inputs):
                self.edges.append(
                    Edge(
                        source=Column(dataset=dataset, name=source),
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

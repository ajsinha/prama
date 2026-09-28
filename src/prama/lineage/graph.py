"""Where data came from and where it goes, at column level.

`FR-LIN-001`…`007`. Table-level lineage answers "which tables read this one",
which sounds useful and is nearly worthless for the question people actually
ask. A warehouse fact table feeds four hundred things; telling somebody that
after an incident is telling them nothing. **Column-level lineage answers "this
column feeds that column, which is line 23 of the FINREP return"**, and that is
a sentence somebody can act on at seven in the morning.

**Edges are typed, because not everything downstream is equally affected.** A
column copied verbatim carries the whole defect. A column that is one of forty
inputs to a sum carries a fortieth of it, and a filter that excludes the
affected rows carries none. An impact analysis that treats these alike produces
a list of four hundred "affected" assets, which is the same as producing no
list — and a trust score computed over untyped edges says a report is as
untrustworthy as the worst column anywhere upstream of it, which nobody
believes and nobody should.

**Cycles are normal and must not hang.** A table feeding a table that feeds it
back through a different path is an ordinary warehouse, not a modelling error,
and a traversal that assumes a DAG will find out in production.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

#: Impact below this is not reported. Not a performance cap: a column
#: contributing a thousandth of an aggregate is not "affected" in any sense the
#: reader means, and including it is how an impact list becomes something
#: nobody opens.
IMPACT_FLOOR = 0.01

#: Hops beyond which traversal stops. A warehouse is not usually deeper than
#: this, and a graph that is has a modelling problem the traversal should
#: report rather than absorb.
MAXIMUM_DEPTH = 12


class Transform(enum.Enum):
    """What happens to a value on its way along an edge.

    The attenuation is the number that makes an impact list readable, and each
    one is a claim about how much of an upstream defect survives the hop.
    """

    #: Copied. A defect arrives intact.
    IDENTITY = "identity"
    #: Cast, trimmed, renamed. Still essentially the same value.
    RENAME = "rename"
    #: Computed from this and other columns.
    DERIVED = "derived"
    #: Summed, averaged, counted over many rows. One bad row in ten thousand
    #: barely moves a total, which is why an aggregate is the strongest
    #: attenuator here and also the most dangerous: it hides a defect rather
    #: than removing it.
    AGGREGATED = "aggregated"
    #: Used to filter rather than to produce a value. A wrong filter changes
    #: which rows exist, which is often worse than a wrong value, so it is
    #: barely attenuated (0.9, below).
    FILTER = "filter"
    #: Used only as a join key.
    JOIN_KEY = "join_key"

    @property
    def attenuation(self) -> float:
        """How much of an upstream defect survives this hop."""
        return {
            Transform.IDENTITY: 1.0,
            Transform.RENAME: 1.0,
            Transform.DERIVED: 0.7,
            Transform.AGGREGATED: 0.35,
            # A wrong filter changes the population rather than a value, and a
            # missing population is not a diluted problem.
            Transform.FILTER: 0.9,
            Transform.JOIN_KEY: 0.8,
        }[self]

    @property
    def explains(self) -> str:
        return {
            Transform.IDENTITY: "copied unchanged",
            Transform.RENAME: "renamed or cast",
            Transform.DERIVED: "computed from this and other columns",
            Transform.AGGREGATED: "summed or averaged over many rows",
            Transform.FILTER: "used to decide which rows exist",
            Transform.JOIN_KEY: "used as a join key",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Column:
    """One column, addressed the way a person would write it."""

    dataset: str
    name: str

    @property
    def qualified(self) -> str:
        return f"{self.dataset}.{self.name}"

    def __str__(self) -> str:
        return self.qualified

    @classmethod
    def parse(cls, text: str) -> Column:
        dataset, _, name = text.rpartition(".")
        if not dataset:
            raise ValueError(
                f"{text!r} is not a qualified column. Lineage needs to know which "
                "dataset a column belongs to, or two columns called `amount` in "
                "different tables become one node and the graph is wrong everywhere"
            )
        return cls(dataset=dataset, name=name)


@dataclasses.dataclass(frozen=True, slots=True)
class Edge:
    """One column feeding another, and how."""

    source: Column
    target: Column
    transform: Transform = Transform.IDENTITY
    #: The job, model or query that does it. What somebody opens next.
    produced_by: str = ""
    #: A fragment of the expression, for the reader who wants to check.
    expression: str = ""

    def describe(self) -> str:
        head = f"{self.source} → {self.target} ({self.transform.explains})"
        if self.produced_by:
            head += f", by {self.produced_by}"
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.qualified,
            "target": self.target.qualified,
            "transform": self.transform.value,
            "produced_by": self.produced_by,
            "expression": self.expression,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Reached:
    """A node the blast radius reached, and how badly."""

    column: Column
    #: Product of the attenuations along the strongest path to it.
    impact: float
    depth: int
    #: The path taken, so the answer can be checked rather than trusted.
    path: tuple[Edge, ...] = ()

    @property
    def is_direct(self) -> bool:
        return self.depth == 1

    def describe(self) -> str:
        route = (
            " → ".join(
                [self.path[0].source.qualified, *(edge.target.qualified for edge in self.path)]
            )
            if self.path
            else self.column.qualified
        )
        return (
            f"{self.column} at {self.impact:.0%} of the defect, {self.depth} hop"
            f"{'s' if self.depth != 1 else ''} away: {route}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column.qualified,
            "impact": round(self.impact, 6),
            "depth": self.depth,
            "path": [edge.to_dict() for edge in self.path],
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class BlastRadius:
    """Everything a defect in one column reaches, ranked."""

    origin: Column
    reached: tuple[Reached, ...] = ()
    #: Nodes that exist downstream and fell below the floor. Counted rather
    #: than listed, so "and 380 others at under 1%" is visible without being
    #: the report.
    below_floor: int = 0
    #: True when traversal stopped at the depth limit rather than at the edge
    #: of the graph.
    truncated: bool = False

    def __len__(self) -> int:
        return len(self.reached)

    @property
    def datasets(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for item in self.reached:
            seen.setdefault(item.column.dataset, None)
        return tuple(seen)

    def worst(self, limit: int = 10) -> tuple[Reached, ...]:
        return tuple(
            sorted(self.reached, key=lambda item: (-item.impact, item.column.qualified))[:limit]
        )

    def describe(self) -> str:
        if not self.reached:
            return f"nothing downstream of {self.origin}"
        head = (
            f"{len(self.reached)} columns across {len(self.datasets)} datasets are "
            f"affected by {self.origin}"
        )
        if self.below_floor:
            head += (
                f"; {self.below_floor} more are downstream at under "
                f"{IMPACT_FLOOR:.0%} and are not listed, because a column carrying a "
                f"thousandth of a defect is not affected in any sense the reader means"
            )
        if self.truncated:
            head += (
                f". Traversal stopped at {MAXIMUM_DEPTH} hops; a graph deeper than "
                f"that has a modelling problem worth looking at on its own"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin.qualified,
            "reached": [item.to_dict() for item in self.reached],
            "datasets": list(self.datasets),
            "below_floor": self.below_floor,
            "truncated": self.truncated,
            "summary": self.describe(),
        }


class LineageGraph:
    """Column-level lineage, traversable in both directions."""

    def __init__(self) -> None:
        self._out: dict[Column, list[Edge]] = {}
        self._in: dict[Column, list[Edge]] = {}
        self._datasets: dict[str, set[Column]] = {}

    def add(self, edge: Edge) -> None:
        self._out.setdefault(edge.source, []).append(edge)
        self._in.setdefault(edge.target, []).append(edge)
        self._datasets.setdefault(edge.source.dataset, set()).add(edge.source)
        self._datasets.setdefault(edge.target.dataset, set()).add(edge.target)

    def add_all(self, edges: Iterable[Edge]) -> None:
        for edge in edges:
            self.add(edge)

    @property
    def columns(self) -> tuple[Column, ...]:
        return tuple(sorted(set(self._out) | set(self._in), key=lambda c: c.qualified))

    @property
    def datasets(self) -> tuple[str, ...]:
        return tuple(sorted(self._datasets))

    def columns_of(self, dataset: str) -> tuple[Column, ...]:
        return tuple(sorted(self._datasets.get(dataset, set()), key=lambda c: c.name))

    def edges(self) -> tuple[Edge, ...]:
        """Every edge, once. What a merge and an export both need."""
        return tuple(edge for edges in self._out.values() for edge in edges)

    def downstream(self, column: Column) -> tuple[Edge, ...]:
        return tuple(self._out.get(column, ()))

    def upstream(self, column: Column) -> tuple[Edge, ...]:
        return tuple(self._in.get(column, ()))

    # -- traversal ---------------------------------------------------------

    def blast_radius(
        self,
        origin: Column,
        *,
        floor: float = IMPACT_FLOOR,
        max_depth: int = MAXIMUM_DEPTH,
    ) -> BlastRadius:
        """Everything a defect here reaches, attenuated along the way.

        Breadth-first, keeping the *strongest* path to each node rather than
        the first one found. That matters: a column reachable both directly and
        through an aggregate is affected as much as the direct path says, and
        reporting the attenuated figure because it was discovered first would
        understate it.
        """
        best: dict[Column, Reached] = {}
        below = 0
        truncated = False
        frontier: list[tuple[Column, float, int, tuple[Edge, ...]]] = [(origin, 1.0, 0, ())]

        while frontier:
            column, impact, depth, path = frontier.pop(0)
            if depth >= max_depth:
                truncated = True
                continue
            for edge in self._out.get(column, ()):
                carried = impact * edge.transform.attenuation
                if carried < floor:
                    below += 1
                    continue
                existing = best.get(edge.target)
                if existing is not None and existing.impact >= carried:
                    continue
                reached = Reached(
                    column=edge.target,
                    impact=carried,
                    depth=depth + 1,
                    path=(*path, edge),
                )
                best[edge.target] = reached
                # Cycles terminate because attenuation is at most 1 and a
                # revisit only continues when it is strictly stronger, which
                # cannot happen forever.
                frontier.append((edge.target, carried, depth + 1, reached.path))

        return BlastRadius(
            origin=origin,
            reached=tuple(
                sorted(best.values(), key=lambda item: (-item.impact, item.column.qualified))
            ),
            below_floor=below,
            truncated=truncated,
        )

    def sources_of(self, column: Column, *, max_depth: int = MAXIMUM_DEPTH) -> tuple[Column, ...]:
        """Every column upstream, nearest first.

        The set an incident's root cause is somewhere in. Ordered by distance
        because the nearest cause is the likeliest, and a ranked list beats a
        set when somebody has twenty minutes.
        """
        seen: dict[Column, int] = {}
        frontier = [(column, 0)]
        while frontier:
            current, depth = frontier.pop(0)
            if depth >= max_depth:
                continue
            for edge in self._in.get(current, ()):
                if edge.source in seen and seen[edge.source] <= depth + 1:
                    continue
                seen[edge.source] = depth + 1
                frontier.append((edge.source, depth + 1))
        return tuple(sorted(seen, key=lambda c: (seen[c], c.qualified)))

    def paths(
        self, source: Column, target: Column, *, max_depth: int = MAXIMUM_DEPTH
    ) -> Iterator[tuple[Edge, ...]]:
        """Every route from one column to another.

        Plural on purpose. "Why does this number depend on that one?" often has
        two answers, and showing one of them is how somebody fixes a path and
        finds the number still wrong.
        """
        stack: list[tuple[Column, tuple[Edge, ...], frozenset[Column]]] = [
            (source, (), frozenset({source}))
        ]
        while stack:
            current, path, visited = stack.pop()
            if len(path) >= max_depth:
                continue
            for edge in self._out.get(current, ()):
                if edge.target == target:
                    yield (*path, edge)
                    continue
                if edge.target in visited:
                    continue
                stack.append((edge.target, (*path, edge), visited | {edge.target}))

    def dataset_edges(self) -> tuple[tuple[str, str], ...]:
        """The table-level view, derived rather than stored separately.

        Kept derived because a table graph maintained beside a column graph
        drifts from it, and the drift is invisible until an impact analysis
        names a table nothing actually reads.
        """
        seen: dict[tuple[str, str], None] = {}
        for edges in self._out.values():
            for edge in edges:
                if edge.source.dataset != edge.target.dataset:
                    seen.setdefault((edge.source.dataset, edge.target.dataset), None)
        return tuple(seen)

    def orphans(self) -> tuple[Column, ...]:
        """Columns nothing reads.

        Worth surfacing: an orphan is either dead weight to be retired or a
        gap in the lineage, and both are worth knowing. It is also the number
        that tells you how complete the graph is — a warehouse where eighty
        percent of columns are orphans has not been scanned properly.
        """
        return tuple(
            column for column in self.columns if not self._out.get(column) and self._in.get(column)
        )

    def __len__(self) -> int:
        return sum(len(edges) for edges in self._out.values())


def merge(graphs: Sequence[LineageGraph]) -> LineageGraph:
    """One graph from several scanners.

    Lineage arrives from more than one place — dbt for the models, a SQL parser
    for the legacy views, OpenLineage for the jobs — and the union is the only
    complete picture. Duplicate edges are kept rather than deduplicated,
    because two scanners agreeing is worth knowing and the traversal takes the
    strongest path anyway.
    """
    combined = LineageGraph()
    for graph in graphs:
        combined.add_all(graph.edges())
    return combined

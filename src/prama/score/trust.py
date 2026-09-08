"""Trust that flows along lineage, over a semiring somebody chose.

`FR-SCR-004`, and `RSK-18`: trust propagation is the part of this system most
likely to be dismissed as arbitrary, and the dismissal would be fair against
most implementations. A number that says a report is 0.73 trustworthy, arrived
at by multiplying things nobody can name, is astrology with a schema.

Three commitments make it defensible.

**The combination rule is chosen, not assumed.** A semiring is a pair of
operations — how trust combines *along* a path and *across* several paths — and
different businesses genuinely mean different things by it. A risk team
computing a worst case wants the minimum; a team asking "how much of this is
supported" wants the product. Both are correct and they disagree, so the choice
is a configuration with a name and a rationale rather than a constant buried in
a loop.

**The derivation is always visible.** Every score carries the path it came
down, the operations applied, and the local score at each hop. A number
somebody cannot reconstruct is a number they will not act on, and rightly.

**A defect that has been contained stops propagating.** This is the honest
half. If a downstream dataset has a control that *would* catch the upstream
problem and it passed, the problem did not arrive — and continuing to
discount that dataset punishes it for a fault it demonstrably does not have.
Propagation without containment is what makes trust scores go to zero
everywhere after one bad Tuesday and stay there.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from prama.lineage.graph import Column, Edge, LineageGraph


class Semiring(enum.Enum):
    """How trust combines along a path and across several.

    Named after what they mean rather than after their algebra, because the
    person choosing has an opinion about the meaning and none about the
    algebra.

    **The across-paths choice is the one that gets made wrong**, and it turns
    on a distinction lineage does not record: whether several upstream paths
    are *complementary* or *redundant*. A derived column needs all its inputs —
    a position value needs the amount and the rate — so it is no better than
    the worst of them. Two independent feeds of the same fact are redundant,
    and one good feed is enough.

    Taking the best across complementary inputs is the classic error, and it is
    seductive because it produces reassuring numbers: a report built from a
    corrupt feed and a healthy rate table scores as though the feed were fine.
    So the default treats inputs as complementary, which is what almost all
    lineage is, and redundancy is something a person asserts.
    """

    #: Multiply along a path, take the worst across paths. A derived column is
    #: no better than the weakest thing that feeds it. The default, because
    #: almost all lineage is complementary.
    ALL_INPUTS_MATTER = "all_inputs_matter"
    #: Multiply along, take the best across. Correct **only** where the paths
    #: are genuinely redundant — two feeds of the same fact, where one being
    #: good is enough. Asserted rather than assumed.
    REDUNDANT_SOURCES = "redundant_sources"
    #: Minimum along and across. "A chain is as strong as its weakest link",
    #: taken literally in both directions. What a risk team asks for, and it
    #: ignores how many weak links there are.
    WEAKEST_LINK = "weakest_link"
    #: Multiply along, average across. Right when several sources genuinely
    #: contribute in proportion, and wrong when one is authoritative.
    PRODUCT_MEAN = "product_mean"

    @property
    def along(self) -> Callable[[float, float], float]:
        if self is Semiring.WEAKEST_LINK:
            return min
        return lambda left, right: left * right

    @property
    def across(self) -> Callable[[Sequence[float]], float]:
        if self is Semiring.REDUNDANT_SOURCES:
            return lambda values: max(values) if values else 1.0
        if self is Semiring.PRODUCT_MEAN:
            return lambda values: sum(values) / len(values) if values else 1.0
        return lambda values: min(values) if values else 1.0

    @property
    def explains(self) -> str:
        return {
            Semiring.ALL_INPUTS_MATTER: (
                "trust multiplies along a path and the weakest path governs, because a "
                "derived value needs every one of its inputs"
            ),
            Semiring.REDUNDANT_SOURCES: (
                "trust multiplies along a path and the best path wins, which is right "
                "only where the sources are genuinely redundant"
            ),
            Semiring.WEAKEST_LINK: (
                "the weakest link on the weakest path, which asks what could be wrong "
                "rather than what probably is"
            ),
            Semiring.PRODUCT_MEAN: (
                "trust multiplies along a path and paths are averaged, which asks what "
                "everything feeding this contributes in proportion"
            ),
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Hop:
    """One step of a derivation, so the number can be checked."""

    edge: Edge
    #: Trust arriving at the source of this edge.
    incoming: float
    #: The source column's own score, before anything upstream is considered.
    local: float
    #: Trust leaving, after the edge's attenuation and the semiring.
    outgoing: float
    #: Set when a control downstream demonstrably catches the upstream problem.
    contained_by: str = ""

    def describe(self) -> str:
        if self.contained_by:
            return (
                f"{self.edge.source} → {self.edge.target}: contained by "
                f"{self.contained_by}, which passed, so the upstream problem did not "
                f"arrive here"
            )
        return (
            f"{self.edge.source} ({self.local:.2f}) → {self.edge.target}: "
            f"{self.incoming:.2f} in, {self.outgoing:.2f} out "
            f"({self.edge.transform.explains})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge": self.edge.to_dict(),
            "incoming": round(self.incoming, 6),
            "local": round(self.local, 6),
            "outgoing": round(self.outgoing, 6),
            "contained_by": self.contained_by,
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Trust:
    """One column's trust, and the derivation behind it."""

    column: Column
    score: float
    #: The column's own evidence, before lineage. What its controls say.
    local: float
    semiring: Semiring
    #: The path that produced the score. The whole defence against "arbitrary".
    derivation: tuple[Hop, ...] = ()
    #: Paths considered and not chosen, counted. A score that took the best of
    #: four paths is a different claim from one that had only the path it took.
    alternatives: int = 0

    @property
    def is_inherited(self) -> bool:
        """Whether upstream lowered it below what its own controls say."""
        return self.score < self.local - 1e-9

    def explain(self) -> str:
        if not self.derivation:
            return (
                f"{self.column} scores {self.score:.2f} on its own evidence; nothing "
                f"upstream of it is known"
            )
        head = f"{self.column} scores {self.score:.2f}. Its own controls say {self.local:.2f}"
        if self.is_inherited:
            head += f", and upstream brings it down to {self.score:.2f}"
        head += f". {self.semiring.explains}"
        if self.alternatives:
            head += f", and {self.alternatives} other paths were considered"
        return head + ". " + " ".join(hop.describe() for hop in self.derivation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column.qualified,
            "score": round(self.score, 6),
            "local": round(self.local, 6),
            "inherited": self.is_inherited,
            "semiring": self.semiring.value,
            "alternatives": self.alternatives,
            "derivation": [hop.to_dict() for hop in self.derivation],
            "explanation": self.explain(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Containment:
    """A control that stops an upstream problem propagating further.

    The honest half of trust propagation, and the half most implementations
    leave out. A dataset whose own controls would catch the upstream defect,
    and which passed them, did not receive the defect — and continuing to
    discount it punishes it for a fault it demonstrably does not have.
    Propagation without containment is why trust scores go to zero everywhere
    after one bad Tuesday and stay there.
    """

    column: Column
    control: str
    #: True when the control ran and passed. A control that exists and did not
    #: run contains nothing.
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column.qualified,
            "control": self.control,
            "passed": self.passed,
        }


class TrustPropagator:
    """Computes trust over lineage, showing its working."""

    def __init__(
        self,
        graph: LineageGraph,
        *,
        semiring: Semiring = Semiring.ALL_INPUTS_MATTER,
        containment: Sequence[Containment] = (),
        max_depth: int = 8,
    ) -> None:
        self._graph = graph
        self._semiring = semiring
        self._contained = {item.column: item for item in containment if item.passed}
        self._max_depth = max_depth

    def trust(self, column: Column, local: Mapping[Column, float]) -> Trust:
        """One column's trust, derived from its own evidence and its sources."""
        own = local.get(column, 1.0)
        paths = self._paths_to(column, local, depth=0, seen=frozenset({column}))
        if not paths:
            return Trust(
                column=column,
                score=own,
                local=own,
                semiring=self._semiring,
            )

        scored = [(self._along(own, hops), hops) for hops in paths]
        combined = self._semiring.across([score for score, _ in scored])
        # The derivation shown must be the path that *decided* the score, not
        # the strongest one. Showing the best path under a semiring that takes
        # the worst produces an explanation whose arithmetic does not reach its
        # own conclusion — which is precisely the "arbitrary number" complaint
        # this module exists to answer, arrived at by a different route.
        deciding = min(scored, key=lambda pair: (abs(pair[0] - combined), -len(pair[1])))
        return Trust(
            column=column,
            score=min(own, combined),
            local=own,
            semiring=self._semiring,
            derivation=deciding[1],
            alternatives=max(0, len(scored) - 1),
        )

    def trust_all(self, local: Mapping[Column, float]) -> dict[Column, Trust]:
        return {column: self.trust(column, local) for column in self._graph.columns}

    # -- derivation --------------------------------------------------------

    def _paths_to(
        self,
        column: Column,
        local: Mapping[Column, float],
        *,
        depth: int,
        seen: frozenset[Column],
    ) -> list[tuple[Hop, ...]]:
        """Every upstream path, as hops, bounded by depth and by cycles."""
        if depth >= self._max_depth:
            return []
        paths: list[tuple[Hop, ...]] = []
        for edge in self._graph.upstream(column):
            if edge.source in seen:
                continue
            contained = self._contained.get(edge.target)
            source_local = local.get(edge.source, 1.0)
            if contained is not None:
                # The problem did not arrive. The hop is recorded so the
                # derivation shows *why* nothing was inherited, which is more
                # useful than the hop being absent.
                paths.append(
                    (
                        Hop(
                            edge=edge,
                            incoming=1.0,
                            local=source_local,
                            outgoing=1.0,
                            contained_by=contained.control,
                        ),
                    )
                )
                continue

            upstream = self._paths_to(
                edge.source, local, depth=depth + 1, seen=seen | {edge.source}
            )
            attenuated = self._attenuate(source_local, edge)
            if not upstream:
                paths.append(
                    (
                        Hop(
                            edge=edge,
                            incoming=source_local,
                            local=source_local,
                            outgoing=attenuated,
                        ),
                    )
                )
                continue
            for prefix in upstream:
                arriving = prefix[-1].outgoing
                combined = self._semiring.along(arriving, source_local)
                paths.append(
                    (
                        *prefix,
                        Hop(
                            edge=edge,
                            incoming=arriving,
                            local=source_local,
                            outgoing=self._attenuate(combined, edge),
                        ),
                    )
                )
        return paths

    def _attenuate(self, value: float, edge: Edge) -> float:
        """How much of a defect survives an edge, expressed as trust.

        An aggregate dilutes a bad value, so a column downstream of one is more
        trustworthy than the source — not less. Applying the transform's
        attenuation to the *deficit* rather than to the score is what makes
        that come out right; applying it to the score directly would make every
        aggregate less trustworthy than its inputs, which is backwards.
        """
        deficit = (1.0 - value) * edge.transform.attenuation
        return max(0.0, min(1.0, 1.0 - deficit))

    def _along(self, own: float, hops: Sequence[Hop]) -> float:
        arriving = hops[-1].outgoing if hops else 1.0
        return self._semiring.along(arriving, own)


def ranked_by_trust(trusts: Mapping[Column, Trust], *, limit: int = 10) -> tuple[Trust, ...]:
    """Least trustworthy first — the remediation queue.

    `RQ8` asks whether this ordering differs from ranking by severity, and it
    does whenever a low-severity defect sits upstream of something important:
    severity ranks the finding, trust ranks the *consequence*, and the two
    disagree exactly where the disagreement is worth having.
    """
    return tuple(
        sorted(trusts.values(), key=lambda trust: (trust.score, trust.column.qualified))[:limit]
    )

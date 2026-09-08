"""Ranked causes, each with the thing to go and look at.

`FR-INC-004`. Root-cause analysis in a data platform is usually a graph
traversal presented as insight: "here are the forty things upstream of the
failure". That is a list, not an analysis, and the person holding it is exactly
where they were before.

**A hypothesis is only worth ranking if it can be checked**, and cheaply. "The
06:30 feed did not arrive" is verifiable in thirty seconds; "there may be an
upstream data quality issue" is not verifiable at all. So every hypothesis
carries the check — the specific thing to look at, and what would confirm or
kill it — and the ranking is over hypotheses that can be settled rather than
over plausibility.

Four signals, and they are ranked by how much they narrow the search:

*An upstream control that is itself failing.* The strongest by a distance:
something upstream is known to be broken, and the only question is whether it
explains this. Nothing else comes close, and a system that ranks a speculative
cause above a demonstrated upstream failure is ranking on the wrong axis.

*A change that touched the path.* Strong when it exists, and it usually does —
most incidents are somebody's Tuesday afternoon.

*Proximity in lineage.* The nearest upstream column is likelier than the
furthest, because a defect that travelled six hops would have been caught by
something on the way if anything on the way were watching.

*A learned prior.* What has caused incidents on this path before. Weak
individually and worth having because it is free, and because the answer is
often the same as last time.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping, Sequence
from typing import Any

from prama.incident.correlate import Change, Incident
from prama.lineage.graph import Column, LineageGraph


class Evidence(enum.Enum):
    """Why a cause is being suggested."""

    #: Something upstream is known to be failing right now.
    UPSTREAM_FAILING = "upstream_failing"
    #: A change touched the path shortly before.
    CHANGE = "change"
    #: It sits between the failure and its sources.
    PROXIMITY = "proximity"
    #: It has caused incidents on this path before.
    PRIOR = "prior"

    @property
    def weight(self) -> float:
        return {
            # A demonstrated upstream failure is not in the same category as a
            # speculation, and a ranking that puts them on one scale is ranking
            # on the wrong axis.
            Evidence.UPSTREAM_FAILING: 1.0,
            Evidence.CHANGE: 0.6,
            Evidence.PROXIMITY: 0.25,
            Evidence.PRIOR: 0.15,
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Hypothesis:
    """A possible cause, and the thing to go and look at."""

    cause: str
    #: What to check, specifically. A hypothesis nobody can settle in a few
    #: minutes is not a hypothesis; it is a shrug with a rank.
    check: str
    #: What would confirm it, and what would kill it. Both, because a check
    #: that can only confirm is a check that always confirms.
    confirms: str
    rules_out: str
    evidence: tuple[tuple[Evidence, str], ...] = ()
    column: Column | None = None
    change: Change | None = None

    @property
    def score(self) -> float:
        """Combined as independent evidence, not averaged."""
        remaining = 1.0
        for kind, _ in self.evidence:
            remaining *= 1.0 - kind.weight
        return 1.0 - remaining

    @property
    def is_demonstrated(self) -> bool:
        """Whether something here is known to be broken, rather than suspected."""
        return any(kind is Evidence.UPSTREAM_FAILING for kind, _ in self.evidence)

    def describe(self) -> str:
        reasons = "; ".join(detail for _, detail in self.evidence)
        return f"{self.cause} — {reasons}. Check: {self.check}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "cause": self.cause,
            "check": self.check,
            "confirms": self.confirms,
            "rules_out": self.rules_out,
            "score": round(self.score, 4),
            "demonstrated": self.is_demonstrated,
            "column": self.column.qualified if self.column else None,
            "change": self.change.to_dict() if self.change else None,
            "evidence": [[kind.value, detail] for kind, detail in self.evidence],
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Analysis:
    """What to look at first, and why."""

    incident: str
    hypotheses: tuple[Hypothesis, ...] = ()
    #: Upstream columns examined and not offered. Counted, so the analysis can
    #: say how wide it looked without listing forty things.
    considered: int = 0

    @property
    def best(self) -> Hypothesis | None:
        return self.hypotheses[0] if self.hypotheses else None

    @property
    def is_conclusive(self) -> bool:
        """Whether one hypothesis stands clearly ahead of the rest.

        Reported because "we think it is one of these four" is a useful and
        different answer from "it is this", and presenting the first as the
        second is how an RCA loses its reader the second time it is wrong.
        """
        if len(self.hypotheses) < 2:
            return bool(self.hypotheses)
        return self.hypotheses[0].score >= self.hypotheses[1].score * 1.5

    def describe(self) -> str:
        if not self.hypotheses:
            return (
                f"{self.incident}: nothing upstream explains this. The cause is in "
                f"the dataset itself, or in something not in the lineage graph"
            )
        head = f"{self.incident}: {self.hypotheses[0].describe()}"
        if not self.is_conclusive:
            head += (
                f". {len(self.hypotheses)} hypotheses are close together, so this is "
                f"where to start rather than the answer"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident": self.incident,
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "considered": self.considered,
            "conclusive": self.is_conclusive,
            "summary": self.describe(),
        }


class RootCause:
    """Ranks the causes an incident could have, and says how to settle each."""

    def __init__(
        self,
        graph: LineageGraph,
        *,
        changes: Sequence[Change] = (),
        #: Columns whose own controls are currently failing. The strongest
        #: signal there is, and the one that needs no inference.
        failing: Sequence[Column] = (),
        #: How often each column has been the confirmed cause before.
        priors: Mapping[str, int] | None = None,
        limit: int = 5,
    ) -> None:
        self._graph = graph
        self._changes = sorted(changes, key=lambda change: change.at)
        self._failing = set(failing)
        self._priors = dict(priors or {})
        self._limit = limit

    def analyse(self, incident: Incident) -> Analysis:
        origin = incident.common_ancestor or (
            incident.findings[0].qualified if incident.findings else None
        )
        if origin is None:
            return Analysis(incident=incident.identity)

        sources = self._graph.sources_of(origin)
        candidates = [origin, *sources]
        hypotheses: list[Hypothesis] = []

        for depth, column in enumerate(candidates):
            evidence: list[tuple[Evidence, str]] = []

            if column in self._failing and column != origin:
                evidence.append(
                    (
                        Evidence.UPSTREAM_FAILING,
                        f"{column} is failing its own controls right now",
                    )
                )

            change = self._change_touching(column, incident)
            if change is not None:
                evidence.append(
                    (
                        Evidence.CHANGE,
                        f"{change.what} touched it at {change.at.strftime('%Y-%m-%d %H:%M')}",
                    )
                )

            if column == origin:
                # The origin is where the failures converge, which makes it the
                # single most likely place for the defect to be — and an
                # earlier version gave it no evidence at all, so it was omitted
                # from its own analysis and the nearest *upstream* column
                # ranked first. The most obvious answer has to be on the list
                # even when it is obvious.
                evidence.append(
                    (
                        Evidence.PROXIMITY,
                        "every failure in this incident converges here, so the defect "
                        "is here unless something upstream put it here",
                    )
                )
            elif depth <= 2:
                evidence.append(
                    (
                        Evidence.PROXIMITY,
                        f"it is {depth} hop{'s' if depth != 1 else ''} upstream, and a "
                        f"defect that travelled further would likely have been caught "
                        f"on the way",
                    )
                )

            seen = self._priors.get(column.qualified, 0)
            if seen:
                evidence.append(
                    (
                        Evidence.PRIOR,
                        f"it has been the confirmed cause {seen} time"
                        f"{'s' if seen != 1 else ''} before on this path",
                    )
                )

            if not evidence:
                continue
            hypotheses.append(self._hypothesis(column, evidence, change))

        # Ties break toward the origin, then by name. Without the first the
        # ordering among equally-supported hypotheses is alphabetical, which
        # puts whichever column sorts first at the top of a root cause
        # analysis.
        hypotheses.sort(key=lambda item: (-item.score, item.column != origin, item.cause))
        return Analysis(
            incident=incident.identity,
            hypotheses=tuple(hypotheses[: self._limit]),
            considered=len(candidates),
        )

    def _change_touching(self, column: Column, incident: Incident) -> Change | None:
        if incident.opened_at is None:
            return None
        touching = [
            change
            for change in self._changes
            if change.at <= incident.opened_at
            and {column.qualified, column.dataset} & set(change.touched)
        ]
        return touching[-1] if touching else None

    @staticmethod
    def _hypothesis(
        column: Column,
        evidence: list[tuple[Evidence, str]],
        change: Change | None,
    ) -> Hypothesis:
        """Build the hypothesis with a check that can actually be run.

        The check is specific to what the evidence is: a failing upstream
        control is settled by reading that control's last result, and a change
        is settled by reading the diff. A generic "investigate upstream" would
        rank the same and help nobody.
        """
        kinds = {kind for kind, _ in evidence}
        if Evidence.UPSTREAM_FAILING in kinds:
            return Hypothesis(
                cause=f"{column} is broken and this is downstream of it",
                check=f"read the last result of the controls on {column}",
                confirms="they are failing, and their failure started before this one",
                rules_out=(
                    "they are failing but started afterwards, which makes this a "
                    "common cause rather than a chain"
                ),
                evidence=tuple(evidence),
                column=column,
                change=change,
            )
        if change is not None:
            return Hypothesis(
                cause=f"{change.what} broke {column}",
                check=f"read the change {change.identity} and what it altered",
                confirms=(
                    "it altered how this column is produced, and the failure begins after it"
                ),
                rules_out=(
                    "the failure begins before the change, or the change touched "
                    "nothing on this path"
                ),
                evidence=tuple(evidence),
                column=column,
                change=change,
            )
        return Hypothesis(
            cause=f"the defect originates in {column}",
            check=f"compare {column} against its own source for this period",
            confirms="it disagrees with its source, or arrived late or not at all",
            rules_out="it agrees with its source, which moves the cause downstream",
            evidence=tuple(evidence),
            column=column,
        )


def learn_from(confirmed: Sequence[tuple[str, str]]) -> dict[str, int]:
    """Counts of which column was the confirmed cause, for the prior.

    Deliberately counts rather than a model. There is nothing a model would add
    that a count does not, and a great deal it would take away: this one can be
    printed, argued with, and reset when a system is replaced and its history
    stops applying.
    """
    counts: dict[str, int] = {}
    for _, column in confirmed:
        counts[column] = counts.get(column, 0) + 1
    return counts

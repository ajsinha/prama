"""One upstream defect, one incident.

`FR-INC-001`…`003`, and the acceptance criterion this module exists for: a
feed that fails to arrive must produce **one** incident, not four hundred.

Wave 7's selector already folds a dataset's simultaneous failures into a single
finding, and that is not enough. The failure people actually experience is
wider: a feed does not arrive, twelve downstream datasets go stale, four
hundred controls fail across all of them, and the selector — correctly, since
each dataset genuinely has a problem — reports twelve findings. Twelve is much
better than four hundred and is still eleven more than there are incidents.

**The correlation that closes the gap is the lineage graph.** Findings whose
datasets are all downstream of one column are not twelve problems; they are one
problem seen from twelve places, and the incident is about the column. This is
the payoff for building lineage at column level: table-level lineage would
identify the common ancestor as "the warehouse" and be useless.

Three signals, and none is sufficient alone:

*Lineage* — a common upstream ancestor. Strong, and available only where the
graph reaches.

*Time* — findings inside one window. Necessary and nowhere near sufficient: at
six in the morning everything fails together because everything runs together.

*Change* — a deploy, a schema alteration, a mapping edit. The strongest signal
of all when it exists, because it converts "these twelve things broke" into
"these twelve things broke twenty minutes after somebody changed that", and the
second is a sentence with a next step in it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from prama.lineage.graph import Column, LineageGraph

#: Findings further apart than this are not one incident on time alone. An
#: hour, because a nightly batch runs over about that long and two failures at
#: opposite ends of it are usually the same batch.
DEFAULT_WINDOW = timedelta(hours=1)

#: A change this long before a finding is a plausible cause. Longer than the
#: correlation window on purpose: a deploy at midnight explains a failure at
#: six, and the two are not within an hour of each other.
CHANGE_LOOKBACK = timedelta(hours=12)


class Signal(enum.Enum):
    """Why two findings were judged to be one incident."""

    LINEAGE = "lineage"
    TIME = "time"
    CHANGE = "change"
    #: The same dataset. Wave 7's roll-up already does this; it is here so an
    #: incident can say so rather than appearing to have no reason.
    DATASET = "dataset"

    @property
    def strength(self) -> float:
        return {
            Signal.CHANGE: 0.9,
            Signal.LINEAGE: 0.8,
            Signal.DATASET: 0.6,
            # On its own, almost nothing: at six in the morning everything
            # fails together because everything runs together.
            Signal.TIME: 0.15,
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Finding:
    """One thing a monitor or control found, ready to be correlated."""

    identity: str
    dataset: str
    column: str = ""
    at: datetime | None = None
    severity: str = "major"
    description: str = ""

    @property
    def qualified(self) -> Column | None:
        return Column(dataset=self.dataset, name=self.column) if self.column else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "dataset": self.dataset,
            "column": self.column,
            "at": self.at.isoformat() if self.at else None,
            "severity": self.severity,
            "description": self.description,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Change:
    """Something a person did, which is usually the answer."""

    identity: str
    at: datetime
    what: str
    by: str = ""
    #: Datasets or columns it touched. The link that turns "these twelve things
    #: broke" into "these twelve things broke after somebody changed that".
    touched: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "at": self.at.isoformat(),
            "what": self.what,
            "by": self.by,
            "touched": list(self.touched),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Incident:
    """One problem, however many places it was noticed from."""

    identity: str
    findings: tuple[Finding, ...]
    #: Why these were grouped, with the evidence for each signal.
    signals: tuple[tuple[Signal, str], ...] = ()
    #: The column everything is downstream of, when there is one. What the
    #: incident is actually about.
    common_ancestor: Column | None = None
    change: Change | None = None
    opened_at: datetime | None = None

    @property
    def datasets(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for finding in self.findings:
            seen.setdefault(finding.dataset, None)
        return tuple(seen)

    @property
    def is_single(self) -> bool:
        return len(self.findings) == 1

    @property
    def confidence(self) -> float:
        """How sure the correlation is, from the signals that support it.

        A lone finding is certain, not uncertain: there is no grouping to be
        wrong about. Reporting zero for it — which the signal arithmetic does
        on its own — reads as "we are not sure this is an incident", which is a
        different and much more alarming claim than the one intended.

        Combined as independent evidence rather than averaged, for the same
        reason as Wave 6's relationship discovery: two weak agreeing signals
        beat one strong one, and averaging lets a time coincidence drag a
        well-supported grouping down to its level.
        """
        if self.is_single:
            return 1.0
        remaining = 1.0
        for signal, _ in self.signals:
            remaining *= 1.0 - signal.strength
        return 1.0 - remaining

    @property
    def is_speculative(self) -> bool:
        """Whether this was grouped on timing alone.

        Worth flagging rather than suppressing: grouping on time alone is
        usually right and occasionally merges two unrelated incidents, and the
        person triaging needs to know which kind they are holding.
        """
        return not self.is_single and {signal for signal, _ in self.signals} == {Signal.TIME}

    def describe(self) -> str:
        count, datasets = len(self.findings), len(self.datasets)
        head = (
            f"{count} finding{'' if count == 1 else 's'} across {datasets} "
            f"dataset{'' if datasets == 1 else 's'}, one incident"
        )
        if self.common_ancestor is not None:
            head += f", all downstream of {self.common_ancestor}"
        if self.change is not None:
            head += (
                f". {self.change.what} by {self.change.by or 'somebody'} at "
                f"{self.change.at.strftime('%H:%M')} is the nearest change that "
                f"touches it"
            )
        if self.is_speculative:
            head += (
                ". Grouped on timing alone, which is usually right and occasionally "
                "merges two unrelated problems"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "findings": [finding.to_dict() for finding in self.findings],
            "datasets": list(self.datasets),
            "signals": [[signal.value, detail] for signal, detail in self.signals],
            "confidence": round(self.confidence, 4),
            "speculative": self.is_speculative,
            "common_ancestor": (self.common_ancestor.qualified if self.common_ancestor else None),
            "change": self.change.to_dict() if self.change else None,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "summary": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Correlation:
    """What a batch of findings turned into."""

    incidents: tuple[Incident, ...] = ()
    findings: int = 0

    @property
    def reduction(self) -> float:
        """How much noise the correlation removed. The number to publish."""
        if not self.findings:
            return 0.0
        return 1.0 - len(self.incidents) / self.findings

    def describe(self) -> str:
        count = len(self.incidents)
        return (
            f"{self.findings} findings became {count} "
            f"incident{'' if count == 1 else 's'} "
            f"({self.reduction:.0%} fewer things to look at)"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "incidents": [incident.to_dict() for incident in self.incidents],
            "findings": self.findings,
            "reduction": round(self.reduction, 4),
            "summary": self.describe(),
        }


class Correlator:
    """Groups findings into the incidents they are evidence of."""

    def __init__(
        self,
        graph: LineageGraph | None = None,
        *,
        window: timedelta = DEFAULT_WINDOW,
        changes: Sequence[Change] = (),
    ) -> None:
        self._graph = graph
        self._window = window
        self._changes = sorted(changes, key=lambda change: change.at)

    def correlate(self, findings: Sequence[Finding]) -> Correlation:
        """One pass: group by shared upstream, then by change, then by time."""
        if not findings:
            return Correlation()

        groups = self._merge_by_dataset(self._by_ancestor(findings))
        incidents: list[Incident] = []
        for ancestor, members in groups:
            incidents.append(self._build(members, ancestor))

        incidents.sort(key=lambda incident: (-len(incident.findings), incident.identity))
        return Correlation(incidents=tuple(incidents), findings=len(findings))

    def _merge_by_dataset(
        self, groups: list[tuple[Column | None, list[Finding]]]
    ) -> list[tuple[Column | None, list[Finding]]]:
        """Fold together groups whose upstreams reach a common dataset.

        A sub-ledger that breaks affects its ``amount`` column and its
        ``account`` column. Those are two roots of two subgraphs, so grouping
        by column alone reports two incidents about one sub-ledger — this
        module's own failure, one level up.

        The test is the *upstream closure*, not the ancestor itself. A finding
        that shares no ancestor with any other resolves to itself, so comparing
        ancestors directly misses exactly the lone finding that most needs
        folding in. Its sources still reach the sub-ledger, and that is the
        question.

        Merged only when the findings also fall inside the correlation window:
        two columns of one warehouse table failing a fortnight apart are two
        problems that happen to share a table.
        """
        if self._graph is None:
            return groups
        merged: list[tuple[Column | None, list[Finding], set[str]]] = []
        for ancestor, members in groups:
            if ancestor is None:
                merged.append((ancestor, members, set()))
                continue
            reach = self._upstream_datasets(ancestor)
            for index, (other, existing, other_reach) in enumerate(merged):
                if other is None or not (reach & other_reach):
                    continue
                if not self._overlapping(existing, members):
                    continue
                shared = sorted(reach & other_reach)[0]
                merged[index] = (
                    Column(dataset=shared, name="*"),
                    existing + members,
                    reach | other_reach,
                )
                break
            else:
                merged.append((ancestor, members, reach))
        return [(ancestor, members) for ancestor, members, _ in merged]

    def _upstream_datasets(self, column: Column) -> set[str]:
        """Datasets this column and everything feeding it belong to."""
        assert self._graph is not None
        return {column.dataset} | {source.dataset for source in self._graph.sources_of(column)}

    def _overlapping(self, left: Sequence[Finding], right: Sequence[Finding]) -> bool:
        stamps = [item.at for item in (*left, *right) if item.at]
        return not stamps or (max(stamps) - min(stamps)) <= self._window

    # -- grouping ----------------------------------------------------------

    def _by_ancestor(
        self, findings: Sequence[Finding]
    ) -> list[tuple[Column | None, list[Finding]]]:
        """Group findings that share an upstream column.

        The payoff for column-level lineage. Table-level would identify the
        common ancestor as "the warehouse", which groups everything into one
        incident every night and is worse than not grouping at all.
        """
        if self._graph is None:
            return self._by_dataset_and_time(findings)

        ancestors: dict[str, set[str]] = {}
        for finding in findings:
            column = finding.qualified
            if column is None:
                ancestors[finding.identity] = set()
                continue
            ancestors[finding.identity] = {
                source.qualified for source in self._graph.sources_of(column)
            } | {column.qualified}

        assigned: dict[str, int] = {}
        groups: list[tuple[Column | None, list[Finding]]] = []

        for finding in findings:
            mine = ancestors[finding.identity]
            placed = False
            for index, (ancestor, members) in enumerate(groups):
                if ancestor is None or ancestor.qualified not in mine:
                    continue
                # And the timing has to agree. Sharing an upstream column was
                # the only test, so two unrelated failures three days apart
                # merged into one incident because everything in a warehouse
                # shares a feed eventually (QA finding INC-011).
                #
                # An incident is a claim that these findings have one cause. A
                # cause that acted on Monday and again on Thursday, with
                # nothing between, is two causes — and merging them sends one
                # responder to explain both.
                if not self._within_window(members[0], finding):
                    continue
                members.append(finding)
                assigned[finding.identity] = index
                placed = True
                break
            if placed:
                continue

            shared = self._shared_ancestor(finding, findings, ancestors)
            groups.append((shared, [finding]))
            assigned[finding.identity] = len(groups) - 1

        # Findings with no lineage fall back to dataset and time, so a graph
        # that does not reach everywhere degrades rather than fails.
        without = [f for f in findings if not ancestors[f.identity]]
        if without:
            groups = [
                (ancestor, [f for f in members if ancestors[f.identity]])
                for ancestor, members in groups
            ]
            groups = [(a, m) for a, m in groups if m]
            groups.extend(self._by_dataset_and_time(without))
        return groups

    def _shared_ancestor(
        self,
        finding: Finding,
        findings: Sequence[Finding],
        ancestors: dict[str, set[str]],
    ) -> Column | None:
        """The deepest column this finding shares with the others.

        Deepest rather than any: everything shares "the raw feed" eventually,
        and an incident about the raw feed when the fault is in one derived
        column sends people to the wrong system.
        """
        mine = ancestors[finding.identity]
        if not mine:
            return None
        counts: dict[str, int] = {}
        for other in findings:
            if other.identity == finding.identity:
                continue
            for shared in mine & ancestors[other.identity]:
                counts[shared] = counts.get(shared, 0) + 1
        if not counts:
            return finding.qualified
        best = max(counts, key=lambda key: (counts[key], len(key)))
        return Column.parse(best)

    def _by_dataset_and_time(
        self, findings: Sequence[Finding]
    ) -> list[tuple[Column | None, list[Finding]]]:
        groups: list[tuple[Column | None, list[Finding]]] = []
        for finding in sorted(findings, key=lambda f: (f.dataset, f.at or datetime.min)):
            for _, members in groups:
                if members[0].dataset != finding.dataset:
                    continue
                if self._within_window(members[0], finding):
                    members.append(finding)
                    break
            else:
                groups.append((None, [finding]))
        return groups

    def _within_window(self, left: Finding, right: Finding) -> bool:
        if left.at is None or right.at is None:
            return True
        return abs(left.at - right.at) <= self._window

    # -- building ----------------------------------------------------------

    def _build(self, members: list[Finding], ancestor: Column | None) -> Incident:
        signals: list[tuple[Signal, str]] = []
        if ancestor is not None and len(members) > 1:
            signals.append(
                (
                    Signal.LINEAGE,
                    f"every finding is downstream of {ancestor}",
                )
            )
        if len({finding.dataset for finding in members}) == 1 and len(members) > 1:
            signals.append((Signal.DATASET, f"all in {members[0].dataset}"))
        stamps = [finding.at for finding in members if finding.at]
        if len(stamps) > 1 and max(stamps) - min(stamps) <= self._window:
            signals.append(
                (
                    Signal.TIME,
                    f"all within {int((max(stamps) - min(stamps)).total_seconds() // 60)} "
                    f"minutes of each other",
                )
            )

        change = self._nearest_change(members, ancestor)
        if change is not None:
            signals.append(
                (
                    Signal.CHANGE,
                    f"{change.what} touched {', '.join(change.touched)} beforehand",
                )
            )

        opened = min(stamps) if stamps else None
        return Incident(
            identity=(
                f"incident:{ancestor.qualified}"
                if ancestor is not None
                else f"incident:{members[0].dataset}:{members[0].identity}"
            ),
            findings=tuple(members),
            signals=tuple(signals),
            common_ancestor=ancestor,
            change=change,
            opened_at=opened,
        )

    def _nearest_change(self, members: Sequence[Finding], ancestor: Column | None) -> Change | None:
        """The most recent change that touched something involved.

        Nearest rather than every: a list of eleven changes is a list nobody
        reads, and the most recent one touching the right thing is right often
        enough to be the first place to look.
        """
        stamps = [finding.at for finding in members if finding.at]
        if not stamps or not self._changes:
            return None
        earliest = min(stamps)
        touched = {finding.dataset for finding in members}
        touched |= {finding.qualified.qualified for finding in members if finding.qualified}
        if ancestor is not None:
            touched |= {ancestor.qualified, ancestor.dataset}

        candidates = [
            change
            for change in self._changes
            if change.at <= earliest
            and earliest - change.at <= CHANGE_LOOKBACK
            and touched & set(change.touched)
        ]
        return candidates[-1] if candidates else None

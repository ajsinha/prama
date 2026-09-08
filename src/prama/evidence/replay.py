"""Running a control again, and saying precisely why the answer moved.

"Replay a run from last month and get the same verdict" is the claim. It is
worth very little on its own — a system that always replays identically is
either correct or is not really re-reading anything, and from the outside those
look alike. What makes replay useful is the other case: when the answer *does*
differ, the report has to say why, and "why" has exactly four candidates.

* **The data changed.** The snapshot identifier moved. This is the ordinary,
  legitimate case and it is not a defect: somebody restated a position, a late
  file arrived, a correction was booked. It is also the case an investigation
  most often wants, so it is named first and named plainly.
* **The control changed.** The plan hash moved. The question being asked is not
  the question that was asked, and comparing the two answers is comparing two
  different controls.
* **The engine changed.** The same plan, the same data, a different backend or a
  different version of one. This is the one that should never happen and the
  one worth escalating: it means two engines disagree, which the conformance
  suite exists to prevent.
* **Nothing identifiable changed.** Same plan, same snapshot, same engine,
  different answer. This is the alarming one, and it is reported as alarming
  rather than smoothed into one of the others. It means either the snapshot was
  not exact — in which case the record already said so and the honest verdict is
  that this run was never replayable — or something is wrong that we cannot see
  from here.

The last distinction is why a snapshot's ``exact`` flag is carried into the
record rather than discarded. Without it, an inexact snapshot's divergence looks
identical to an unexplained one, and an estate full of file-digest sources would
generate unexplained divergences every night until nobody read them.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

from prama.evidence.record import EvidenceRecord


class Cause(enum.Enum):
    """Why a replay differs from the record it replays."""

    IDENTICAL = "identical"
    STABLE = "stable"
    DATA_CHANGED = "data_changed"
    CONTROL_CHANGED = "control_changed"
    ENGINE_CHANGED = "engine_changed"
    PARAMETERS_CHANGED = "parameters_changed"
    SNAPSHOT_NOT_EXACT = "snapshot_not_exact"
    COVERAGE_CHANGED = "coverage_changed"
    UNEXPLAINED = "unexplained"

    @property
    def is_divergence(self) -> bool:
        return self not in (Cause.IDENTICAL, Cause.STABLE)

    @property
    def needs_escalation(self) -> bool:
        """Whether somebody should be told rather than merely shown.

        Data changing is normal. Two engines disagreeing about the same plan
        and the same data is a portability failure, and an unexplained
        divergence is worse than either.
        """
        return self in (Cause.ENGINE_CHANGED, Cause.UNEXPLAINED)

    @property
    def explanation(self) -> str:
        return {
            Cause.IDENTICAL: "the replay reproduced the original exactly",
            Cause.STABLE: (
                "the inputs moved and the answer did not — the control reached the "
                "same conclusion about different data, which is a stronger result "
                "than an exact replay rather than a weaker one"
            ),
            Cause.DATA_CHANGED: (
                "the source data moved between the two runs, which is the ordinary "
                "case: a restatement, a late arrival or a correction"
            ),
            Cause.CONTROL_CHANGED: (
                "the control itself was edited, so the two runs asked different "
                "questions and their answers are not comparable"
            ),
            Cause.PARAMETERS_CHANGED: (
                "the run was given different parameters, so it examined a different scope"
            ),
            Cause.ENGINE_CHANGED: (
                "the same control ran on a different engine and disagreed — a "
                "portability failure, and the conformance suite should have caught it"
            ),
            Cause.COVERAGE_CHANGED: (
                "the two runs examined different amounts of the dataset — one was "
                "incremental and one was not — so their answers are about different "
                "sets of rows"
            ),
            Cause.SNAPSHOT_NOT_EXACT: (
                "the source could not identify its own state exactly, so this run was "
                "never replayable and the original record said so"
            ),
            Cause.UNEXPLAINED: (
                "the plan, the data and the engine are all identical and the answer "
                "is not — this should not be possible and needs investigating"
            ),
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Divergence:
    """A replay compared against the record it replays."""

    cause: Cause
    original: EvidenceRecord
    replayed: EvidenceRecord
    #: Field-by-field differences, for the reader who wants the detail.
    differences: tuple[tuple[str, Any, Any], ...] = ()

    @property
    def is_identical(self) -> bool:
        return self.cause is Cause.IDENTICAL

    @property
    def answer_held(self) -> bool:
        """Whether the control reached the same conclusion, however the inputs moved."""
        return not self.cause.is_divergence

    @property
    def verdict_changed(self) -> bool:
        return self.original.verdict != self.replayed.verdict

    def render(self) -> str:
        if self.answer_held:
            reached = (
                "reproduced the original exactly"
                if self.is_identical
                else "reached the same conclusion about changed data"
            )
            return (
                f"Replay of sequence {self.original.sequence} {reached}: {self.original.verdict}."
            )
        headline = (
            f"{self.original.verdict} → {self.replayed.verdict}"
            if self.verdict_changed
            else f"{self.original.verdict}, with different numbers"
        )
        lines = [
            f"Replay of sequence {self.original.sequence} diverged: {headline}.",
            f"Cause: {self.cause.explanation}.",
        ]
        if self.differences:
            lines.append("What differs:")
            lines.extend(
                f"  {field}: {before!r} → {after!r}" for field, before, after in self.differences
            )
        if self.cause.needs_escalation:
            lines.append("This is not an ordinary divergence and should be escalated.")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cause": self.cause.value,
            "identical": self.is_identical,
            "verdict_changed": self.verdict_changed,
            "escalate": self.cause.needs_escalation,
            "sequence": self.original.sequence,
            "plan_id": self.original.plan_id,
            "original_verdict": self.original.verdict,
            "replayed_verdict": self.replayed.verdict,
            "differences": [
                {"field": f, "original": b, "replayed": a} for f, b, a in self.differences
            ],
            "summary": self.render(),
        }


def compare(original: EvidenceRecord, replayed: EvidenceRecord) -> Divergence:
    """Diagnose a replay against its original.

    A divergence is a difference in the *answer*. The inputs moving is the
    explanation for one, not a divergence in itself: a nightly replay against
    fresh data would otherwise report every record as diverged, and the two
    whose verdicts actually changed would be lost among the ones that did not.

    The order of the tests is the order of the questions somebody asks, and it
    matters: if both the control and the data moved, the useful thing to say is
    that the control moved, because the answers were never comparable and no
    amount of looking at the data will explain it.
    """
    answer = tuple(_answer_differences(original, replayed))
    inputs = tuple(_input_differences(original, replayed))
    if not answer:
        # Same conclusion. Whether the inputs held still is worth saying, but
        # neither case is a divergence.
        return Divergence(
            Cause.IDENTICAL if not inputs else Cause.STABLE,
            original,
            replayed,
            differences=inputs,
        )
    differences = inputs + answer
    changed = {field for field, _, _ in inputs}

    if "plan_id" in changed or "control_version" in changed:
        cause = Cause.CONTROL_CHANGED
    elif "parameters" in changed:
        cause = Cause.PARAMETERS_CHANGED
    elif "coverage" in changed:
        # Before the data check: two runs that read different amounts of the
        # table were never comparable, and blaming the data would send somebody
        # looking for a restatement that did not happen.
        cause = Cause.COVERAGE_CHANGED
    elif "snapshot" in changed:
        cause = Cause.DATA_CHANGED
    elif not original.snapshot.exact:
        # Same identifier, different answer, and the source admitted its
        # identifier does not pin the data. That is the record keeping its own
        # promise rather than an anomaly.
        cause = Cause.SNAPSHOT_NOT_EXACT
    elif "engine" in changed:
        cause = Cause.ENGINE_CHANGED
    else:
        cause = Cause.UNEXPLAINED
    return Divergence(cause=cause, original=original, replayed=replayed, differences=differences)


def _answer_differences(
    original: EvidenceRecord, replayed: EvidenceRecord
) -> list[tuple[str, Any, Any]]:
    """What the control concluded. A difference here is the divergence."""
    found: list[tuple[str, Any, Any]] = []
    if original.verdict != replayed.verdict:
        found.append(("verdict", original.verdict, replayed.verdict))
    for name in sorted(set(original.metrics) | set(replayed.metrics)):
        before = original.metrics.get(name)
        after = replayed.metrics.get(name)
        if before != after:
            found.append((f"metrics.{name}", before, after))
    return found


def _input_differences(
    original: EvidenceRecord, replayed: EvidenceRecord
) -> list[tuple[str, Any, Any]]:
    """What the control was given. A difference here explains a divergence.

    Timings, sequence numbers and hashes are excluded on purpose: a replay
    happens later and takes a different length of time, and reporting that
    would bury the differences that matter under two that never do.
    """
    found: list[tuple[str, Any, Any]] = []
    for field in ("plan_id", "control_version", "engine", "coverage"):
        before, after = getattr(original, field), getattr(replayed, field)
        if before != after:
            found.append((field, before, after))
    if original.snapshot.identifier != replayed.snapshot.identifier:
        found.append(("snapshot", original.snapshot.identifier, replayed.snapshot.identifier))
    if original.parameters != replayed.parameters:
        found.append(("parameters", original.parameters, replayed.parameters))
    return found


@dataclasses.dataclass(frozen=True, slots=True)
class ReplayReport:
    """Many replays at once, summarised the way a release gate wants."""

    divergences: tuple[Divergence, ...] = ()

    @property
    def replayed(self) -> int:
        return len(self.divergences)

    @property
    def identical(self) -> int:
        return sum(1 for d in self.divergences if d.is_identical)

    @property
    def held(self) -> int:
        """Replays whose answer did not move, exactly or across changed inputs."""
        return sum(1 for d in self.divergences if d.answer_held)

    @property
    def escalations(self) -> tuple[Divergence, ...]:
        return tuple(d for d in self.divergences if d.cause.needs_escalation)

    @property
    def all_accounted_for(self) -> bool:
        """Every difference has a named cause that is not 'unexplained'.

        The acceptance criterion is not that everything replays identically —
        data legitimately changes — but that nothing diverges without the
        report being able to say why.
        """
        return not any(d.cause is Cause.UNEXPLAINED for d in self.divergences)

    def by_cause(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for divergence in self.divergences:
            counts[divergence.cause.value] = counts.get(divergence.cause.value, 0) + 1
        return dict(sorted(counts.items()))

    def render(self) -> str:
        lines = [
            f"Replayed {self.replayed} record(s): {self.held} reached the same "
            f"conclusion ({self.identical} of them against identical inputs), "
            f"{self.replayed - self.held} diverged."
        ]
        for cause, count in self.by_cause().items():
            if cause != Cause.IDENTICAL.value:
                lines.append(f"  {count} of them: {Cause(cause).explanation}")
        if self.escalations:
            lines.append("")
            lines.append(f"{len(self.escalations)} need escalation:")
            lines.extend(f"  {d.render()}" for d in self.escalations)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "replayed": self.replayed,
            "identical": self.identical,
            "held": self.held,
            "all_accounted_for": self.all_accounted_for,
            "by_cause": self.by_cause(),
            "escalations": [d.to_dict() for d in self.escalations],
            "summary": self.render(),
        }

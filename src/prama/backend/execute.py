"""Turning computed metrics into a verdict, identically on every engine.

Deliberately separate from compilation and from any driver. The engines compute
numbers; this decides what the numbers mean, once, so two backends cannot
disagree about a threshold even if they disagree about everything else. It is
also the piece the conformance suite pins: if the metrics match and this is
shared, the verdicts match by construction.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.ir.model import ControlPlan, Verdict


@dataclasses.dataclass(frozen=True, slots=True)
class ControlResult:
    """What one control found, on one engine, over one scope."""

    plan_id: str
    verdict: Verdict
    metrics: dict[str, float]
    #: Present only for a segmented control: one entry per segment.
    segments: tuple[SegmentResult, ...] = ()
    samples: tuple[dict[str, Any], ...] = ()
    engine: str = ""
    detail: str = ""

    @property
    def violating_rows(self) -> float:
        return self.metrics.get("violating_rows", 0.0)

    @property
    def scanned_rows(self) -> float:
        return self.metrics.get("scanned_rows", 0.0)

    @property
    def failing_segments(self) -> tuple[SegmentResult, ...]:
        return tuple(s for s in self.segments if s.verdict is Verdict.FAIL)

    def comparable(self) -> dict[str, Any]:
        """The part two engines must agree on.

        Engine name, samples and timings are excluded: a conformance failure
        should mean the engines disagree about the *data*, not that one of them
        returned its rows in a different order.
        """
        return {
            "verdict": self.verdict.value,
            "metrics": {k: _round(v) for k, v in sorted(self.metrics.items())},
            "segments": [s.comparable() for s in sorted(self.segments, key=lambda s: s.key)],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "engine": self.engine,
            "verdict": self.verdict.value,
            "metrics": self.metrics,
            "segments": [s.to_dict() for s in self.segments],
            "samples": list(self.samples),
            "detail": self.detail,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class SegmentResult:
    """One segment's outcome, kept separately so a fault cannot be averaged away."""

    key: str
    verdict: Verdict
    metrics: dict[str, float]

    def comparable(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "verdict": self.verdict.value,
            "metrics": {k: _round(v) for k, v in sorted(self.metrics.items())},
        }

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "verdict": self.verdict.value, "metrics": self.metrics}


def judge(plan: ControlPlan, metrics: dict[str, float], *, engine: str = "") -> ControlResult:
    """Apply a plan's threshold to metrics one engine computed."""
    enriched = _derive(plan, dict(metrics))
    return ControlResult(
        plan_id=plan.plan_id,
        verdict=_verdict(plan, enriched),
        metrics=enriched,
        engine=engine,
    )


def _derive(plan: ControlPlan, metrics: dict[str, float]) -> dict[str, float]:
    """Metrics that follow from the engine's answers rather than from a query.

    A duplicate cannot be identified row by row, so the engine returns the two
    counts and the count of offending rows follows. Deriving it here rather
    than asking each engine for it keeps one definition instead of three.
    """
    if plan.assertion_kind == "functional_dependency":
        determinants = metrics.get("distinct_determinants")
        pairs = metrics.get("distinct_pairs")
        if determinants is not None and pairs is not None:
            # Every combination beyond one per determinant is a determinant
            # carrying a second value — the thing the dependency says cannot
            # happen. Counted in determinants rather than rows, because "four
            # rows disagree" and "one account has two entities" are different
            # findings and only the second names the problem.
            metrics["violating_rows"] = max(0.0, float(pairs) - float(determinants))
        return metrics
    if plan.assertion_kind == "unique_key":
        scanned = metrics.get("scanned_rows")
        distinct = metrics.get("distinct_keys")
        if scanned is None or distinct is None:
            return metrics
        # Nulls are counted separately because every engine's COUNT(DISTINCT)
        # ignores them. Subtracting distinct from scanned without allowing for
        # that charges every null-keyed row as a duplicate, which it is not —
        # it is a different failure. A null key identifies nothing, so it
        # cannot be one row per anything; it counts once, as itself.
        null_keys = float(metrics.get("null_key_rows", 0.0))
        identified = max(0.0, float(scanned) - null_keys)
        duplicates = max(0.0, identified - float(distinct))
        metrics["duplicate_rows"] = duplicates
        metrics["violating_rows"] = duplicates + null_keys
    return metrics


def judge_segments(
    plan: ControlPlan,
    rows: list[tuple[str, dict[str, float]]],
    *,
    engine: str = "",
) -> ControlResult:
    """Judge each segment, then the control as a whole.

    The control fails if any segment does. Aggregating the segments back into
    one number and judging that would restore exactly the averaging the
    segmentation was written to avoid.
    """
    segments = tuple(
        SegmentResult(
            key=key,
            verdict=_verdict(plan, _derive(plan, dict(values))),
            metrics=_derive(plan, dict(values)),
        )
        for key, values in rows
    )
    totals: dict[str, float] = {}
    for segment in segments:
        for name, value in segment.metrics.items():
            totals[name] = totals.get(name, 0.0) + float(value)
    # A fail anywhere fails the control; an indeterminate *anywhere* makes the
    # control indeterminate. This used to require every segment to be
    # indeterminate before saying so, so two partitions that ran cleanly and
    # one that could not be evaluated reported PASS — which hides precisely the
    # partition nobody could measure (QA finding PQL-158).
    #
    # The whole reason to segment is that an answer about the parts is worth
    # more than an answer about the average. A control with a hole in it is not
    # a clean control, and the hole is the interesting part.
    overall = (
        Verdict.FAIL
        if any(s.verdict is Verdict.FAIL for s in segments)
        else Verdict.INDETERMINATE
        if not segments or any(s.verdict is Verdict.INDETERMINATE for s in segments)
        else Verdict.PASS
    )
    return ControlResult(
        plan_id=plan.plan_id,
        verdict=overall,
        metrics=totals,
        segments=segments,
        engine=engine,
    )


def _verdict(plan: ControlPlan, metrics: dict[str, float]) -> Verdict:
    if plan.assertion_kind == "row_count":
        return _row_count_verdict(plan, metrics)
    if plan.assertion_kind == "functional_dependency":
        return _dependency_verdict(metrics)
    if plan.assertion_kind == "unique_key":
        return _distinctness_verdict(metrics)
    return plan.threshold.evaluate(metrics)


def _row_count_verdict(plan: ControlPlan, metrics: dict[str, float]) -> Verdict:
    """A row count has no per-row violation; the count itself is the claim."""
    if "scanned_rows" not in metrics:
        return Verdict.INDETERMINATE
    rows = metrics["scanned_rows"]
    minimum = plan.detail.get("minimum")
    maximum = plan.detail.get("maximum")
    if minimum is not None and rows < minimum:
        return Verdict.FAIL
    if maximum is not None and rows > maximum:
        return Verdict.FAIL
    return Verdict.PASS


def _dependency_verdict(metrics: dict[str, float]) -> Verdict:
    """``a → b`` holds when each distinct a carries exactly one distinct b."""
    if "distinct_determinants" not in metrics or "distinct_pairs" not in metrics:
        return Verdict.INDETERMINATE
    if metrics.get("scanned_rows", 0.0) == 0:
        return Verdict.INDETERMINATE
    return (
        Verdict.PASS
        if metrics["distinct_pairs"] == metrics["distinct_determinants"]
        else Verdict.FAIL
    )


def _distinctness_verdict(metrics: dict[str, float]) -> Verdict:
    """A key holds when the distinct count equals the row count.

    Computed from the two counts rather than from a per-row predicate, because
    uniqueness is a property of the set and no row can be looked at alone and
    called a duplicate.
    """
    if "scanned_rows" not in metrics or "distinct_keys" not in metrics:
        return Verdict.INDETERMINATE
    if metrics["scanned_rows"] == 0:
        # Nothing to be unique. Not a pass: an empty scope has demonstrated
        # nothing, and reporting green is how a broken feed goes unnoticed.
        return Verdict.INDETERMINATE
    return Verdict.PASS if metrics.get("violating_rows", 0.0) == 0 else Verdict.FAIL


def _round(value: float) -> float:
    """Compare at a precision every engine can agree on.

    Engines differ in the last bits of a floating-point division. A conformance
    suite that compared raw doubles would fail on arithmetic rather than on
    meaning, and would teach everyone to ignore it.
    """
    return round(float(value), 9)

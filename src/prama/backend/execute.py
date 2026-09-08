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
    if plan.assertion_kind in ("unique_key", "functional_dependency"):
        scanned = metrics.get("scanned_rows")
        distinct = metrics.get("distinct_keys")
        if scanned is not None and distinct is not None:
            metrics["violating_rows"] = max(0.0, float(scanned) - float(distinct))
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
    overall = (
        Verdict.FAIL
        if any(s.verdict is Verdict.FAIL for s in segments)
        else Verdict.INDETERMINATE
        if not segments or all(s.verdict is Verdict.INDETERMINATE for s in segments)
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
    if plan.assertion_kind in ("unique_key", "functional_dependency"):
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
    return Verdict.PASS if metrics["distinct_keys"] == metrics["scanned_rows"] else Verdict.FAIL


def _round(value: float) -> float:
    """Compare at a precision every engine can agree on.

    Engines differ in the last bits of a floating-point division. A conformance
    suite that compared raw doubles would fail on arithmetic rather than on
    meaning, and would teach everyone to ignore it.
    """
    return round(float(value), 9)

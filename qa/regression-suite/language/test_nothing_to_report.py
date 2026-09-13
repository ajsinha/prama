"""An absent, empty or unknown input must not resolve to the best answer.

QA round 2, `IR-037`, `PQL-158`, `OPS-063`, `EXE-081`. The data-path agent in
round 1 named this family better than I would have:

    the paths that decide "nothing to report" are weaker than the paths that
    decide "something to report".

Each of these takes a case the author did not think about — a missing key, an
unrecognised string, a zero-length run — and lands on `pass`, which is the one
answer that requires the most evidence and here was reached with none.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.ir.model import Comparator, Threshold, Verdict


class TestAnEmptyScanIsNotAPass:
    """`IR-037`. The guard read `metrics.get("scanned_rows", -1.0) == 0.0`.

    Present-and-zero was caught. *Absent* returned the `-1.0` sentinel, which
    is not `0.0`, so it slipped past and the empty-scope case came back for the
    one shape nobody had tested. Q-09 fixed the value; this is the key.
    """

    def test_a_scan_of_zero_rows_is_indeterminate(self) -> None:
        """The half Q-09 fixed, pinned."""
        threshold = Threshold(metric="violating_rows", comparator=Comparator.LE, value=0.0)
        assert threshold.evaluate({"violating_rows": 0, "scanned_rows": 0}) is Verdict.INDETERMINATE

    def test_a_scan_that_never_said_how_many_rows_is_also_indeterminate(self) -> None:
        threshold = Threshold(metric="violating_rows", comparator=Comparator.LE, value=0.0)
        assert threshold.evaluate({"violating_rows": 0}) is Verdict.INDETERMINATE

    def test_a_real_scan_with_no_violations_still_passes(self) -> None:
        """The counterfactual.

        A guard that made everything indeterminate would satisfy both tests
        above and destroy the product. A control that ran over real rows and
        found nothing wrong is a pass, and must stay one.
        """
        threshold = Threshold(metric="violating_rows", comparator=Comparator.LE, value=0.0)
        assert threshold.evaluate({"violating_rows": 0, "scanned_rows": 1000}) is Verdict.PASS


class TestOneUnknownSegmentIsNotAPass:
    """`PQL-158`. `judge_segments` returned PASS unless *every* segment was
    indeterminate.

    Two partitions that ran and one that could not be evaluated is not a clean
    control — it is a control with a hole in it, and the hole is the
    interesting part. The whole reason to segment is that an answer about the
    parts is worth more than an answer about the average.
    """

    @staticmethod
    def _plan():
        from prama.ir.resolve import resolved
        from prama.pql.parser import parse

        return resolved(
            parse(
                "CHECK trades.uti IS NOT NULL BECAUSE 'a trade needs an id' OWNER 'ops'"
            ).all_controls[0]
        )

    def test_a_single_indeterminate_segment_makes_the_whole_indeterminate(self) -> None:
        from prama.backend.execute import judge_segments

        result = judge_segments(
            self._plan(),
            [
                ("EU", {"violating_rows": 0, "scanned_rows": 10}),
                ("US", {"violating_rows": 0, "scanned_rows": 10}),
                ("APAC", {"violating_rows": 0, "scanned_rows": 0}),
            ],
        )
        assert result.verdict is Verdict.INDETERMINATE

    def test_a_failing_segment_still_dominates(self) -> None:
        """A fail outranks an indeterminate; losing that would be worse."""
        from prama.backend.execute import judge_segments

        result = judge_segments(
            self._plan(),
            [
                ("EU", {"violating_rows": 3, "scanned_rows": 10}),
                ("APAC", {"violating_rows": 0, "scanned_rows": 0}),
            ],
        )
        assert result.verdict is Verdict.FAIL

    def test_segments_that_all_ran_cleanly_still_pass(self) -> None:
        """The counterfactual: segmentation must still be able to pass."""
        from prama.backend.execute import judge_segments

        result = judge_segments(
            self._plan(),
            [
                ("EU", {"violating_rows": 0, "scanned_rows": 10}),
                ("US", {"violating_rows": 0, "scanned_rows": 25}),
            ],
        )
        assert result.verdict is Verdict.PASS


class TestAnUnrecognisedVerdictRanksWorstNotBest:
    """`OPS-063`. The sort key was `order.index(v) if v in order else 0`.

    `order[0]` is `"pass"`, so a verdict string nobody recognised received the
    rank of the *best* possible outcome. A new verdict added anywhere, or a
    typo, silently improved the lineage event it appeared in.
    """

    def test_an_unknown_verdict_does_not_read_as_a_pass(self) -> None:
        from prama.telemetry.lineage import _worst_verdict

        assert _worst_verdict(["pass", "pass", "something_new"]) != "pass"

    def test_the_known_order_is_unchanged(self) -> None:
        from prama.telemetry.lineage import _worst_verdict

        assert _worst_verdict(["pass", "fail"]) == "fail"
        assert _worst_verdict(["pass", "skipped"]) == "skipped"
        assert _worst_verdict(["fail", "error"]) == "error"
        assert _worst_verdict(["pass", "pass"]) == "pass"


class TestAnEmptyRunMeasuredNothing:
    """`EXE-081`. `per_second` guarded on elapsed time and not on messages.

    An empty pass still takes a few `perf_counter` ticks, so the guard never
    fired and the answer was `0.0` — a measured throughput of zero, which is a
    claim about performance rather than an absence of one. Its sibling
    `percentile` returns None for the same case, with a docstring explaining
    exactly why.
    """

    def test_a_pass_over_no_messages_reports_no_rate(self) -> None:
        from prama.execute.inflight import Throughput

        assert Throughput(messages=0, elapsed_seconds=0.0001).per_second is None

    def test_a_pass_over_real_messages_still_reports_a_rate(self) -> None:
        from prama.execute.inflight import Throughput

        rate = Throughput(messages=50, elapsed_seconds=0.5).per_second
        assert rate == pytest.approx(100.0)

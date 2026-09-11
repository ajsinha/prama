"""Evaluating a control against a stream.

Batch and stream are usually two implementations of the same rules, and the two
drift. These pin that they cannot: the same IR, the same semantics, the same
threshold.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime, timedelta

from typing import Any, ClassVar

import pytest

from prama.backend.execute import judge as judge_batch
from prama.core.errors import ValidationError
from prama.execute.stream import (
    Lag,
    StreamAssertion,
    StreamSuite,
    Window,
    WindowKind,
)
from prama.ir.lower import Lowerer
from prama.ir.model import Verdict
from prama.pql.parser import parse_control

NOW = datetime(2026, 4, 2, 6, 0, tzinfo=UTC)


def a_plan(source: str = "CHECK trades.notional IS NOT NULL BECAUSE 'CDE'"):
    return Lowerer().control(parse_control(source))


def an_assertion(source: str | None = None, **window: object) -> StreamAssertion:
    options: dict = {"kind": WindowKind.COUNT, "size": 1_000_000}
    options.update(window)
    return StreamAssertion(
        a_plan(source) if source else a_plan(),
        window=Window(**options),  # type: ignore[arg-type]
    )


class TestPerMessage:
    def test_a_good_message_passes(self) -> None:
        assert an_assertion().judge({"notional": 100.0}).passed

    def test_a_violating_message_fails(self) -> None:
        assert not an_assertion().judge({"notional": None}).passed

    def test_an_unknown_is_a_violation_and_is_counted_as_unknown(self) -> None:
        # Kept distinct from a plain failure so the stream's unknown rate is
        # visible: a source that starts sending a field as null shows up here
        # before it shows up anywhere else.
        verdict = an_assertion("CHECK t.notional > 0 BECAUSE 'x'").judge({"notional": None})
        assert verdict.is_violation
        assert verdict.unknown

    def test_the_unknown_policy_is_honoured(self) -> None:
        lenient = an_assertion("CHECK t.notional > 0 TREAT UNKNOWN AS PASS BECAUSE 'declared'")
        verdict = lenient.judge({"notional": None})
        assert verdict.passed
        assert verdict.unknown


class TestTheSameMeaningAsABatch:
    """A control cannot mean one thing in flight and another overnight.

    **What this can and cannot catch.** Both sides evaluate the predicate with
    `ReferenceEvaluator.evaluate`, so an error *inside* that method moves both
    sides together and these tests stay green — the reviewer proved it by
    inverting every definite boolean it returns. That is not what they are for.
    Whether `evaluate` is right is settled by the engine conformance suite,
    against DuckDB, SQLite and PostgreSQL executing real SQL.

    What these are for is everything wrapped *around* it — the unknown policy,
    the residual stage, the threshold, the aggregation — where the streaming
    path and the batch path are separate code and did in fact diverge. Saying
    so matters, because a class named "the same meaning as a batch" reads like a
    stronger guarantee than it is, and `TestTheComparisonDiscriminates` below is
    what keeps it an honest one.
    """

    @pytest.mark.parametrize(
        "source",
        [
            "CHECK t.notional IS NOT NULL BECAUSE 'x'",
            "CHECK t.notional > 0 BECAUSE 'x'",
            "CHECK t.ccy IN ('GBP','USD') BECAUSE 'x'",
            "CHECK t.qty BETWEEN 1 AND 100 BECAUSE 'x'",
            "CHECK t SATISFIES NOT (side = 'BUY' AND qty < 0) BECAUSE 'x'",
            # Two-stage. Finding T3: the stream applied the screen and stopped,
            # so a fabricated identifier with an LEI's exact shape passed in
            # flight and failed overnight — PASS/0 against FAIL/1 on the same
            # three messages. Every case above is single-stage, which is why
            # five parametrised cases and a class named "the same meaning as a
            # batch" did not notice.
            "CHECK t.lei IS VALID 'lei' BECAUSE 'x'",
        ],
    )
    def test_a_window_reaches_the_same_verdict_as_a_batch(self, source: str) -> None:
        messages = [
            # 213800QILIUD4ROSUO03 is a real, check-digit-valid LEI.
            # AAAAAAAAAAAAAAAAAA00 has an LEI's exact shape and does not verify:
            # the screen accepts it and only the residual check rejects it.
            {
                "notional": 100.0,
                "ccy": "GBP",
                "qty": 5,
                "side": "BUY",
                "lei": "213800QILIUD4ROSUO03",
            },
            {
                "notional": None,
                "ccy": "XXX",
                "qty": 500,
                "side": "SELL",
                "lei": "AAAAAAAAAAAAAAAAAA00",
            },
            {
                "notional": -1.0,
                "ccy": "USD",
                "qty": 50,
                "side": "BUY",
                "lei": "213800QILIUD4ROSUO03",
            },
        ]
        plan = a_plan(source)
        assertion = StreamAssertion(plan, window=Window(kind=WindowKind.COUNT, size=3))

        closed = None
        for message in messages:
            closed = assertion.offer(message) or closed
        assert closed is not None

        from prama.backend.reference import ReferenceEvaluator

        batch = ReferenceEvaluator().run(plan, messages)
        assert closed.verdict is batch.verdict
        assert closed.violations == batch.metrics["violating_rows"]

    def test_the_threshold_is_the_plan_s_own(self) -> None:
        # A control that fails at 0.1% in a nightly run fails at 0.1% in
        # flight, which is the whole reason both go through the IR.
        plan = a_plan("CHECK t.notional IS NOT NULL BELOW 50% BECAUSE 'x'")
        assertion = StreamAssertion(plan, window=Window(kind=WindowKind.COUNT, size=4))
        closed = None
        for message in [
            {"notional": 1.0},
            {"notional": None},
            {"notional": 1.0},
            {"notional": 1.0},
        ]:
            closed = assertion.offer(message) or closed
        assert closed is not None
        assert closed.verdict is Verdict.PASS
        assert judge_batch(plan, {"scanned_rows": 4.0, "violating_rows": 1.0}).verdict is (
            Verdict.PASS
        )


class TestWindows:
    def test_a_count_window_closes_on_size(self) -> None:
        assertion = an_assertion(size=3)
        assert assertion.offer({"notional": 1.0}) is None
        assert assertion.offer({"notional": 1.0}) is None
        closed = assertion.offer({"notional": 1.0})
        assert closed is not None
        assert closed.messages == 3

    def test_a_tumbling_window_closes_on_time(self) -> None:
        assertion = StreamAssertion(
            a_plan(), window=Window(kind=WindowKind.TUMBLING, duration=timedelta(seconds=60))
        )
        assert assertion.offer({"notional": 1.0}, at=NOW) is None
        closed = assertion.offer({"notional": 1.0}, at=NOW + timedelta(seconds=61))
        assert closed is not None
        assert closed.opened_at == NOW

    def test_closing_resets_the_counters(self) -> None:
        assertion = an_assertion(size=2)
        assertion.offer({"notional": None})
        assertion.offer({"notional": None})
        assert assertion.open_messages == 0
        assert assertion.close().messages == 0

    def test_an_empty_window_is_indeterminate_not_a_pass(self) -> None:
        # A window in which nothing arrived has demonstrated nothing, and a
        # stream that went silent is exactly what somebody wants to hear about.
        assert an_assertion().close().verdict is Verdict.INDETERMINATE

    def test_a_window_needs_a_positive_bound(self) -> None:
        with pytest.raises(ValidationError, match="positive duration"):
            Window(kind=WindowKind.TUMBLING, duration=timedelta(0))
        with pytest.raises(ValidationError, match="positive size"):
            Window(kind=WindowKind.COUNT, size=0)

    def test_a_window_describes_itself(self) -> None:
        assert Window(duration=timedelta(seconds=30)).describe() == "every 30 seconds"
        assert Window(kind=WindowKind.COUNT, size=5000).describe() == "every 5,000 messages"


class TestASuiteOverOneStream:
    def test_a_message_is_seen_once_by_every_assertion(self) -> None:
        # The streaming equivalent of fusion: deserialise once, evaluate many.
        suite = StreamSuite(
            [
                StreamAssertion(a_plan(s), window=Window(kind=WindowKind.COUNT, size=2))
                for s in (
                    "CHECK t.notional IS NOT NULL BECAUSE 'x'",
                    "CHECK t.ccy IN ('GBP') BECAUSE 'x'",
                )
            ]
        )
        suite.offer({"notional": 1.0, "ccy": "GBP"})
        closed = suite.offer({"notional": None, "ccy": "XXX"})
        assert len(closed) == 2
        assert suite.seen == 2

    def test_open_windows_can_be_flushed(self) -> None:
        suite = StreamSuite([an_assertion(), an_assertion()])
        suite.offer({"notional": 1.0})
        assert len(suite.close_all()) == 2

    def test_a_suite_with_nothing_pending_flushes_nothing(self) -> None:
        assert StreamSuite([an_assertion()]).close_all() == []


class TestBackpressure:
    def test_falling_behind_is_reported_not_absorbed(self) -> None:
        # A streaming check that dropped messages under load would report green
        # because it stopped looking, exactly when the volume that broke it is
        # the thing worth looking at.
        suite = StreamSuite([an_assertion()], lag_threshold=100)
        for _ in range(50):
            suite.offer({"notional": 1.0})
        lag = suite.lag(produced=5_000)
        assert lag.is_falling_behind
        assert "not being dropped" in lag.render()
        assert "shed load or add capacity" in lag.render()

    def test_keeping_up_says_so_plainly(self) -> None:
        suite = StreamSuite([an_assertion()], lag_threshold=100)
        suite.offer({"notional": 1.0})
        assert not suite.lag(produced=2).is_falling_behind
        assert "within tolerance" in suite.lag(produced=2).render()

    def test_the_tolerance_is_declared_rather_than_guessed(self) -> None:
        assert not Lag(messages_behind=500, threshold=1000).is_falling_behind
        assert Lag(messages_behind=500, threshold=100).is_falling_behind


class TestTheHotPath:
    """DEC-17 turns on this number, so it has a test rather than a memory."""

    def test_evaluation_is_far_inside_the_latency_budget(self) -> None:
        # NFR-SCA-005 allows 5 ms of added p99. What Prama contributes is the
        # evaluation, and it is three orders of magnitude below that.
        plans = [
            a_plan(s)
            for s in (
                "CHECK t.notional IS NOT NULL BECAUSE 'x'",
                "CHECK t.notional > 0 BECAUSE 'x'",
                "CHECK t.ccy IN ('GBP','USD','EUR','JPY') BECAUSE 'x'",
                "CHECK t.qty BETWEEN 1 AND 1000000 BECAUSE 'x'",
                "CHECK t SATISFIES NOT (side = 'BUY' AND qty < 0) BECAUSE 'x'",
            )
        ]
        suite = StreamSuite(
            [StreamAssertion(p, window=Window(kind=WindowKind.COUNT, size=10**9)) for p in plans]
        )
        rng = random.Random(7)
        messages = [
            {
                "notional": rng.choice([100.0, None, -5.0]),
                "ccy": rng.choice(["GBP", "XXX"]),
                "qty": rng.randint(1, 5000),
                "side": rng.choice(["BUY", "SELL"]),
            }
            for _ in range(20_000)
        ]
        started = time.perf_counter()
        for message in messages:
            suite.offer(message)
        per_message_ms = (time.perf_counter() - started) / len(messages) * 1000
        # Loose by two orders of magnitude, because the assertion is that
        # latency is not the constraint — not that this machine is fast.
        assert per_message_ms < 0.5

    def test_bookkeeping_does_not_outweigh_the_evaluation(self) -> None:
        # Measured before the fix: five controls cost 7.07 µs per message, of
        # which 4.7 µs was allocating the objects that described the work. On a
        # hot path the report of the work is not allowed to outweigh it.
        #
        # Behavioural rather than by source inspection: what matters is the
        # cost, and an implementation that got there differently would still be
        # correct. (The first version of this test read the method's source and
        # failed on its own docstring, which is what asserting on text earns.)
        plan = a_plan()
        assertion = StreamAssertion(plan, window=Window(kind=WindowKind.COUNT, size=10**9))
        messages = [{"notional": 1.0 if n % 3 else None} for n in range(30_000)]

        started = time.perf_counter()
        for message in messages:
            assertion.judge(message)
        judging = time.perf_counter() - started

        started = time.perf_counter()
        for message in messages:
            assertion.offer(message)
        offering = time.perf_counter() - started

        # Offering does strictly more than judging — counters, a window check —
        # so it is expected to be slower. Twice is the ceiling; it was three
        # times before the allocation went.
        assert offering < judging * 2.5


class TestTheComparisonDiscriminates:
    """The equivalence tests above must be able to fail.

    Finding T3 was that they could not — every case was single-stage, so the
    one place the two paths genuinely differed was never exercised, and a
    divergence that existed in the shipped code went unnoticed by a test named
    for catching exactly it.

    These break the streaming side deliberately, one rule at a time, and require
    the comparison to notice. A test whose failure mode has never been observed
    is a test nobody has any reason to trust.
    """

    MESSAGES: ClassVar[list[dict[str, Any]]] = [
        {"notional": 100.0, "lei": "213800QILIUD4ROSUO03"},
        {"notional": None, "lei": "AAAAAAAAAAAAAAAAAA00"},
        {"notional": -1.0, "lei": "213800QILIUD4ROSUO03"},
    ]

    def run_both(self, source: str, assertion_class: type[StreamAssertion]) -> tuple[Any, Any]:
        from prama.backend.reference import ReferenceEvaluator

        plan = a_plan(source)
        assertion = assertion_class(plan, window=Window(kind=WindowKind.COUNT, size=3))
        closed = None
        for message in self.MESSAGES:
            closed = assertion.offer(message) or closed
        assert closed is not None
        return closed, ReferenceEvaluator().run(plan, self.MESSAGES)

    def test_the_honest_implementation_agrees(self) -> None:
        """The positive control. Without it every assertion below would be
        satisfied by a comparison that always reports a difference."""
        for source in (
            "CHECK t.notional > 0 BECAUSE 'x'",
            "CHECK t.lei IS VALID 'lei' BECAUSE 'x'",
        ):
            closed, batch = self.run_both(source, StreamAssertion)
            assert closed.verdict is batch.verdict, source
            assert closed.violations == batch.metrics["violating_rows"], source

    def test_a_stream_that_forgets_the_unknown_policy_is_caught(self) -> None:
        class Forgetful(StreamAssertion):
            def offer(self, message, *, at=None):  # type: ignore[no-untyped-def]
                self._unknown_is_violation = False
                return super().offer(message, at=at)

        closed, batch = self.run_both("CHECK t.notional > 0 BECAUSE 'x'", Forgetful)
        assert closed.violations != batch.metrics["violating_rows"]

    def test_a_stream_that_skips_the_second_stage_is_caught(self) -> None:
        """The actual defect, reintroduced. Before the fix this was the shipped
        behaviour, and no test in the suite reported it."""

        class ScreenOnly(StreamAssertion):
            def offer(self, message, *, at=None):  # type: ignore[no-untyped-def]
                self._has_residual = False
                return super().offer(message, at=at)

        closed, batch = self.run_both("CHECK t.lei IS VALID 'lei' BECAUSE 'x'", ScreenOnly)
        assert closed.verdict is not batch.verdict
        assert closed.violations != batch.metrics["violating_rows"]

    def test_judge_and_offer_agree_with_each_other(self) -> None:
        """Two entry points into the same rules, and they had drifted apart
        from the batch together — which is why agreeing with each other is
        necessary and is not sufficient."""
        for source in (
            "CHECK t.notional > 0 BECAUSE 'x'",
            "CHECK t.lei IS VALID 'lei' BECAUSE 'x'",
        ):
            plan = a_plan(source)
            per_message = StreamAssertion(plan)
            windowed = StreamAssertion(plan, window=Window(kind=WindowKind.COUNT, size=3))
            expected = sum(
                1 for message in self.MESSAGES if per_message.judge(message).is_violation
            )
            closed = None
            for message in self.MESSAGES:
                closed = windowed.offer(message) or closed
            assert closed is not None
            assert closed.violations == expected, source

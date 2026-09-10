"""In-flight enforcement.

Batch validation tells you a bad record is in the warehouse; enforcement stops
it arriving. That is a different promise, because the moment a control can drop
something its own correctness becomes a data-loss risk rather than an alerting
one — and every test here is about one of the four rules that keeps enforcement
from becoming destruction.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import PramaError
from prama.execute.actions import Action
from prama.execute.inflight import DeadLetterFull, Pipeline, Throughput
from prama.execute.stream import StreamAssertion
from prama.ir.resolve import resolved
from prama.pql import parse_control

NOT_NULL = (
    "CHECK payments.amount IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"
)
POSITIVE = (
    "CHECK payments.amount > 0 SEVERITY major DIMENSION validity BECAUSE 'a payment is positive'"
)


def assertion(pql: str = NOT_NULL) -> StreamAssertion:
    return StreamAssertion(resolved(parse_control(pql)))


class Bin:
    """A dead letter that records, and can be told to refuse."""

    def __init__(self, capacity: int | None = None) -> None:
        self.held: list[tuple[dict, str]] = []
        self.capacity = capacity

    def __call__(self, payload: dict, reason: str) -> bool:
        if self.capacity is not None and len(self.held) >= self.capacity:
            return False
        self.held.append((payload, reason))
        return True


GOOD = {"amount": 10}
BAD = {"amount": None}


class TestNothingIsDroppedWithoutBeingKept:
    def test_a_quarantined_message_reaches_the_dead_letter(self) -> None:
        """A pipeline that drops and then fails to record has destroyed data to
        enforce a rule about data quality."""
        bin_ = Bin()
        report = Pipeline([assertion()], action=Action.QUARANTINE, dead_letter=bin_).run(
            [GOOD, BAD]
        )

        assert report.count("quarantined") == 1
        assert len(bin_.held) == 1
        assert bin_.held[0][0] == BAD

    def test_a_blocked_message_reaches_it_too(self) -> None:
        bin_ = Bin()
        Pipeline([assertion()], action=Action.BLOCK, dead_letter=bin_).run([BAD])
        assert len(bin_.held) == 1

    def test_a_withheld_message_is_still_accounted_for(self) -> None:
        report = Pipeline([assertion()], action=Action.QUARANTINE, dead_letter=Bin()).run(
            [GOOD, BAD]
        )
        assert all(outcome.was_kept for outcome in report.outcomes)

    def test_a_pipeline_that_removes_without_a_dead_letter_is_refused(self) -> None:
        """Refused at construction, not at the first bad message — discovering
        it at runtime means it has already deleted something."""
        with pytest.raises(PramaError, match="needs a dead letter"):
            Pipeline([assertion()], action=Action.QUARANTINE)
        with pytest.raises(PramaError, match="needs a dead letter"):
            Pipeline([assertion()], action=Action.BLOCK)

    def test_tagging_and_alerting_need_none(self) -> None:
        """Neither removes a message, so neither can lose one."""
        assert Pipeline([assertion()], action=Action.TAG).action is Action.TAG
        assert Pipeline([assertion()], action=Action.ALERT).action is Action.ALERT


class TestBackPressureBeatsASilentDiscard:
    def test_a_full_dead_letter_halts_the_pipeline(self) -> None:
        """A full dead letter that silently fell back to dropping would convert
        a storage problem into permanent loss — and the storage problem is the
        one somebody can fix."""
        report = Pipeline([assertion()], action=Action.QUARANTINE, dead_letter=Bin(capacity=1)).run(
            [BAD, BAD, BAD]
        )

        assert not report.completed
        assert "would not accept" in report.halted_because

    def test_the_halt_is_unmistakable_in_the_summary(self) -> None:
        """A pass that stopped and one that finished look identical in their
        counts."""
        report = Pipeline([assertion()], action=Action.QUARANTINE, dead_letter=Bin(capacity=0)).run(
            [BAD, BAD]
        )
        assert report.describe().startswith("HALTED")
        assert "was not examined" in report.describe()

    def test_the_exception_names_what_to_do(self) -> None:
        pipeline = Pipeline([assertion()], action=Action.QUARANTINE, dead_letter=Bin(capacity=0))
        with pytest.raises(DeadLetterFull, match="stopped"):
            pipeline._judge(BAD)


class TestAnUnreadableMessageIsKept:
    def test_it_is_dead_lettered_rather_than_dropped(self) -> None:
        """An unparseable message is a finding about the sender. Discarding it
        removes the only evidence of what they sent."""
        bin_ = Bin()
        report = Pipeline([assertion()], action=Action.QUARANTINE, dead_letter=bin_).run(
            ["not a message at all"]
        )

        assert report.count("unreadable") == 1
        assert bin_.held[0][1] == "unreadable"
        assert "not a message at all" in bin_.held[0][0]["raw"]

    def test_it_does_not_reach_the_consumer(self) -> None:
        report = Pipeline([assertion()], action=Action.QUARANTINE, dead_letter=Bin()).run([12345])
        assert report.delivered == ()


class TestTheActionsMeanWhatTheyMean:
    def test_alert_lets_the_message_through(self) -> None:
        """Alerting does not touch the data. Anything else would make ALERT a
        different action from the one the estate approved."""
        report = Pipeline([assertion()], action=Action.ALERT).run([BAD])
        assert report.count("passed") == 1
        assert report.delivered[0].violated

    def test_tag_lets_it_through_with_a_mark(self) -> None:
        """The consumer decides. A control that silently removed tagged
        messages would be making a business decision on a quality signal."""
        report = Pipeline([assertion()], action=Action.TAG).run([BAD])
        [outcome] = report.outcomes
        assert outcome.reaches_the_consumer
        assert outcome.message["_prama"]["violated"]

    def test_tagging_does_not_mutate_the_original(self) -> None:
        message = {"amount": None}
        Pipeline([assertion()], action=Action.TAG).run([message])
        assert "_prama" not in message

    def test_quarantine_and_block_both_withhold(self) -> None:
        for action in (Action.QUARANTINE, Action.BLOCK):
            report = Pipeline([assertion()], action=action, dead_letter=Bin()).run([BAD])
            assert report.delivered == ()

    def test_a_clean_message_is_untouched_by_any_action(self) -> None:
        for action in (Action.ALERT, Action.TAG, Action.QUARANTINE, Action.BLOCK):
            report = Pipeline(
                [assertion()],
                action=action,
                dead_letter=Bin() if action.touches_the_data else None,
            ).run([GOOD])
            assert report.delivered[0].message == GOOD


class TestWhichControlFired:
    def test_the_violated_controls_are_named_not_counted(self) -> None:
        """A message quarantined by one control out of forty needs to say
        which."""
        report = Pipeline([assertion(NOT_NULL), assertion(POSITIVE)], action=Action.TAG).run(
            [{"amount": -5}]
        )
        [outcome] = report.outcomes
        assert len(outcome.violated) == 1
        assert all(identity for identity in outcome.violated)

    def test_both_can_fire_on_one_message(self) -> None:
        report = Pipeline([assertion(NOT_NULL), assertion(POSITIVE)], action=Action.TAG).run(
            [{"amount": None}]
        )
        [outcome] = report.outcomes
        assert len(outcome.violated) == 2

    def test_an_unknown_is_reported_separately_from_a_violation(self) -> None:
        """A source that starts sending a field as null shows up here before it
        shows up anywhere else."""
        report = Pipeline([assertion(POSITIVE)], action=Action.TAG).run([{"amount": None}])
        [outcome] = report.outcomes
        assert outcome.unknown


class TestTheCostIsMeasured:
    def test_a_pass_reports_its_own_latency(self) -> None:
        """A pipeline that cannot say what it costs is one nobody will put in
        front of a payment system."""
        report = Pipeline([assertion()], action=Action.TAG).run([GOOD] * 200)
        assert report.throughput.messages == 200
        assert report.throughput.p99_ms is not None
        assert report.throughput.per_second is not None

    def test_it_fits_the_published_budget(self) -> None:
        """docs/15 §7: five milliseconds added at p99."""
        report = Pipeline([assertion(), assertion(POSITIVE)], action=Action.TAG).run([GOOD] * 500)
        assert report.throughput.within(5.0) is True

    def test_an_empty_pass_measures_nothing_rather_than_zero(self) -> None:
        """A pass over no messages has not demonstrated a fast pipeline, and
        reporting 0 ms would say it had."""
        empty = Throughput()
        assert empty.p99_ms is None
        assert empty.per_second is None
        assert empty.within(5.0) is None
        assert "nothing was measured" in empty.describe()

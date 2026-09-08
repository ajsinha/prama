"""What happens when a control fails.

An alert is the weakest thing a data quality platform can do, and for most of
the industry it is the only thing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from prama.core.clock import Clock
from prama.execute.actions import (
    Action,
    Disposition,
    Enforcer,
    Quarantine,
)
from prama.ir.model import Verdict

ROWS = [{"account_id": "A1", "notional": None}, {"account_id": "A2", "notional": -1}]


class Movable(Clock):
    def __init__(self) -> None:
        self._now = datetime(2026, 4, 2, 6, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)

    def monotonic(self) -> float:
        return 0.0

    def epoch_millis(self) -> int:
        return int(self._now.timestamp() * 1000)


def enforce(enforcer: Enforcer, action: Action, verdict: Verdict = Verdict.FAIL, **changes):
    options = {
        "plan_id": "ir:sha256:" + "a" * 64,
        "dataset": "positions_eod",
        "verdict": verdict,
        "action": action,
        "reason": "the CDE is missing on two rows",
    }
    options.update(changes)
    return enforcer.enforce(**options)  # type: ignore[arg-type]


class TestOnlyAFailureActs:
    @pytest.mark.parametrize("verdict", [Verdict.PASS, Verdict.SKIPPED])
    def test_a_healthy_verdict_does_nothing(self, verdict: Verdict) -> None:
        assert enforce(Enforcer(), Action.BLOCK, verdict) is None

    def test_an_indeterminate_verdict_does_not_block(self) -> None:
        # It means the control demonstrated nothing. Blocking a pipeline
        # because a scope was empty would be acting on the absence of evidence
        # rather than on evidence.
        enforcer = Enforcer()
        assert enforce(enforcer, Action.BLOCK, Verdict.INDETERMINATE) is None
        assert enforcer.blocking() == []


class TestTheFourActions:
    def test_alerting_leaves_the_data_alone(self) -> None:
        enforcer = Enforcer()
        consequence = enforce(enforcer, Action.ALERT)
        assert consequence is not None
        assert not consequence.action.touches_the_data
        assert enforcer.blocking() == []

    def test_tagging_marks_it_and_lets_it_through(self) -> None:
        consequence = enforce(Enforcer(), Action.TAG)
        assert consequence is not None
        assert consequence.tag == "suspect"
        assert not consequence.is_blocking

    def test_quarantine_sets_the_rows_aside_and_the_rest_continues(self) -> None:
        # The answer when nine hundred rows of a million are wrong and the
        # batch is due.
        enforcer = Enforcer()
        consequence = enforce(enforcer, Action.QUARANTINE, rows=ROWS)
        assert consequence is not None
        assert consequence.quarantined_rows == 2
        assert not consequence.is_blocking
        assert enforcer.quarantine.get(consequence.quarantine_ref) == ROWS

    def test_blocking_stops_the_pipeline(self) -> None:
        enforcer = Enforcer()
        consequence = enforce(enforcer, Action.BLOCK)
        assert consequence is not None
        assert consequence.is_blocking
        assert enforcer.is_blocked("positions_eod")

    def test_each_action_explains_itself_distinctly(self) -> None:
        # Four explanations, four different consequences. Asserting a
        # particular word would be testing the phrasing; asserting they differ
        # tests that the four actions are actually four things.
        explanations = [action.explanation for action in Action]
        assert all(explanations)
        assert len(set(explanations)) == len(Action)

    def test_only_blocking_stops_the_pipeline(self) -> None:
        stopping = [a for a in Action if a.stops_the_pipeline]
        assert stopping == [Action.BLOCK]

    def test_only_alerting_leaves_the_data_untouched(self) -> None:
        # Which is why the other three need an override path and alerting does
        # not.
        untouched = [a for a in Action if not a.touches_the_data]
        assert untouched == [Action.ALERT]


class TestQuarantineKeepsTheDataApart:
    def test_the_consequence_holds_a_reference_not_the_rows(self) -> None:
        # Copying them into the consequence would double the exposure of
        # exactly the data somebody decided to isolate.
        consequence = enforce(Enforcer(), Action.QUARANTINE, rows=ROWS)
        assert consequence is not None
        assert "A1" not in str(consequence.to_dict())
        assert consequence.quarantine_ref

    def test_releasing_lets_the_rows_back_and_remembers_it(self) -> None:
        # "This was let through on purpose" is exactly what an investigation
        # needs six months later.
        enforcer = Enforcer()
        consequence = enforce(enforcer, Action.QUARANTINE, rows=ROWS)
        assert consequence is not None
        released = enforcer.release(consequence.plan_id)
        assert released is not None
        assert released.disposition is Disposition.RELEASED
        assert enforcer.quarantine.was_released(consequence.quarantine_ref)
        assert enforcer.quarantine.get(consequence.quarantine_ref) == ROWS

    def test_releasing_something_that_was_not_quarantined_does_nothing(self) -> None:
        enforcer = Enforcer()
        consequence = enforce(enforcer, Action.BLOCK)
        assert consequence is not None
        assert enforcer.release(consequence.plan_id) is None

    def test_a_quarantine_with_no_rows_still_records_the_action(self) -> None:
        consequence = enforce(Enforcer(), Action.QUARANTINE)
        assert consequence is not None
        assert consequence.quarantined_rows == 0


class TestOverrides:
    def test_proceeding_anyway_needs_a_name_and_a_reason(self) -> None:
        # An override without a name is an outage nobody owns; without a
        # reason, one nobody can learn from.
        enforcer = Enforcer()
        blocked = enforce(enforcer, Action.BLOCK)
        assert blocked is not None
        overridden = enforcer.override(
            blocked.plan_id, by="a.roy", reason="the feed is late, not wrong"
        )
        assert overridden is not None
        assert overridden.override is not None
        assert overridden.override.by == "a.roy"
        assert not enforcer.blocking()

    def test_an_expired_override_restores_the_block(self) -> None:
        # An override with no expiry is a control quietly switched off, and six
        # months later nobody remembers it was ever on.
        clock = Movable()
        enforcer = Enforcer(clock=clock)
        blocked = enforce(enforcer, Action.BLOCK)
        assert blocked is not None
        enforcer.override(
            blocked.plan_id,
            by="a.roy",
            reason="one-off",
            until=clock.now() + timedelta(hours=2),
        )
        assert not enforcer.blocking()
        clock.advance(hours=3)
        assert enforcer.blocking()

    def test_an_override_with_no_expiry_holds_indefinitely_and_shows_as_such(self) -> None:
        clock = Movable()
        enforcer = Enforcer(clock=clock)
        blocked = enforce(enforcer, Action.BLOCK)
        assert blocked is not None
        overridden = enforcer.override(blocked.plan_id, by="a.roy", reason="known issue")
        assert overridden is not None
        clock.advance(days=400)
        assert not enforcer.blocking()
        assert "with no expiry" in overridden.render()

    def test_resolving_closes_it(self) -> None:
        enforcer = Enforcer()
        blocked = enforce(enforcer, Action.BLOCK)
        assert blocked is not None
        resolved = enforcer.resolve(blocked.plan_id)
        assert resolved is not None
        assert resolved.disposition is Disposition.RESOLVED
        assert not enforcer.blocking()

    def test_overriding_something_that_never_acted_does_nothing(self) -> None:
        assert Enforcer().override("nothing", by="a", reason="b") is None


class TestTheReport:
    def test_it_says_what_is_stopped_and_what_was_waved_through(self) -> None:
        enforcer = Enforcer()
        first = enforce(enforcer, Action.BLOCK, dataset="positions_eod")
        second = enforce(enforcer, Action.BLOCK, dataset="trades", plan_id="ir:sha256:" + "b" * 64)
        assert first is not None and second is not None
        enforcer.override(second.plan_id, by="a.roy", reason="known")
        report = enforcer.report()
        assert len(report["blocking"]) == 1
        assert len(report["overridden"]) == 1
        assert "1 pipeline(s) stopped" in report["summary"]

    def test_a_consequence_reads_as_a_sentence(self) -> None:
        enforcer = Enforcer()
        consequence = enforce(enforcer, Action.QUARANTINE, rows=ROWS)
        assert consequence is not None
        rendered = consequence.render()
        assert "positions_eod: fail → quarantine" in rendered
        assert "2 row(s) set aside" in rendered
        assert "because: the CDE is missing" in rendered


class TestQuarantineStore:
    def test_it_keeps_batches_apart(self) -> None:
        store = Quarantine()
        store.put("a", [{"x": 1}])
        store.put("b", [{"x": 2}])
        assert len(store) == 2
        assert store.get("a") != store.get("b")

    def test_an_unknown_reference_is_empty_rather_than_an_error(self) -> None:
        assert Quarantine().get("nothing") == []

    def test_rows_are_copied_in_so_a_later_edit_cannot_change_them(self) -> None:
        rows = [{"x": 1}]
        store = Quarantine()
        store.put("a", rows)
        rows[0]["x"] = 99
        assert store.get("a") == [{"x": 1}]

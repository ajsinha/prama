"""Deciding what not to run, and saying so.

The failure this file exists to prevent: the dashboard is green because a third
of the estate did not run, and nobody can tell the difference between a control
that passed and one that never happened.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime

from prama.schedule import BudgetPolicy, Candidate, Priority

NOW = datetime(2026, 4, 2, 6, 0, tzinfo=UTC)

WORK = [
    Candidate("grain", "positions_eod", Priority.CRITICAL, cost=10),
    Candidate("cde-null", "positions_eod", Priority.CRITICAL, cost=8),
    Candidate("ccy", "positions_eod", Priority.HIGH, cost=6),
    Candidate("isin", "positions_eod", Priority.HIGH, cost=30),
    Candidate("volume", "trades", Priority.NORMAL, cost=5),
    Candidate("comment-len", "trades", Priority.LOW, cost=4, deferrals=4),
    Candidate("stale-ref", "reference", Priority.LOW, cost=40),
]


def allocate(budget: float, work: list[Candidate] | None = None):
    # `if work is None`, not `work or WORK`: an empty queue is a case worth
    # testing, and treating it as "not supplied" would silently run the default.
    return BudgetPolicy(budget, retry_after_minutes=120).allocate(
        WORK if work is None else work, now=NOW
    )


class TestNothingIsDroppedSilently:
    def test_every_deferral_is_named(self) -> None:
        # By name, never as a count. "12 deferred" is not something anybody can
        # act on.
        allocation = allocate(35)
        report = allocation.render()
        for deferral in allocation.deferred:
            assert deferral.candidate.identifier in report

    def test_a_deferral_says_why_and_when_it_will_run(self) -> None:
        deferral = allocate(35).deferred[0]
        assert "would cost" in deferral.reason
        assert deferral.next_attempt == datetime(2026, 4, 2, 8, 0, tzinfo=UTC)

    def test_the_allocation_serialises_for_a_coverage_report(self) -> None:
        payload = allocate(35).to_dict()
        assert payload["deferred"]
        assert all(entry["reason"] for entry in payload["deferred"])


class TestSheddingOrder:
    def test_critical_work_is_never_shed(self) -> None:
        # If the budget cannot cover it the budget is wrong, and that is a
        # sentence somebody has to read rather than a queue that quietly grows.
        allocation = allocate(1)
        assert {c.identifier for c in allocation.admitted} == {"grain", "cde-null"}
        assert allocation.over_committed
        assert "the budget is wrong" in allocation.render()

    def test_the_estate_keeps_the_most_controls_for_its_budget(self) -> None:
        # Cheapest first within a priority, so a single expensive control does
        # not displace four cheap ones.
        allocation = allocate(35)
        admitted = {c.identifier for c in allocation.admitted}
        assert "ccy" in admitted  # cheap and high priority
        assert "isin" not in admitted  # expensive, same priority

    def test_priority_beats_cost_across_bands(self) -> None:
        work = [
            Candidate("expensive-high", "d", Priority.HIGH, cost=9),
            Candidate("cheap-low", "d", Priority.LOW, cost=1),
        ]
        allocation = allocate(9, work)
        assert [c.identifier for c in allocation.admitted] == ["expensive-high"]

    def test_a_long_deferred_control_goes_before_its_equals(self) -> None:
        # The only thing standing between priority scheduling and permanent
        # starvation at the bottom.
        work = [
            Candidate("fresh", "d", Priority.LOW, cost=5, deferrals=0),
            Candidate("waiting", "d", Priority.LOW, cost=5, deferrals=6),
        ]
        allocation = allocate(5, work)
        assert [c.identifier for c in allocation.admitted] == ["waiting"]


class TestStarvation:
    def test_repeated_deferral_is_noticed(self) -> None:
        # A control deferred every night for a month is a control that does not
        # exist, and the coverage report should stop counting it.
        allocation = allocate(20)
        starving = {d.candidate.identifier for d in allocation.starving}
        assert "comment-len" in starving
        assert "deferred three times or more" in allocation.render()

    def test_a_first_deferral_is_not_starvation(self) -> None:
        work = [
            Candidate("a", "d", Priority.CRITICAL, cost=10),
            Candidate("b", "d", Priority.LOW, cost=10),
        ]
        assert not allocate(10, work).starving

    def test_the_deferral_count_advances(self) -> None:
        entry = allocate(20).to_dict()["deferred"]
        waiting = next(e for e in entry if e["identifier"] == "comment-len")
        assert waiting["deferrals"] == 5
        assert waiting["starving"] is True


class TestHeadroom:
    def test_an_ample_budget_runs_everything(self) -> None:
        allocation = allocate(1000)
        assert not allocation.deferred
        assert allocation.headroom > 0
        assert "Running 7 of 7" in allocation.render()

    def test_spending_never_exceeds_the_budget_except_for_critical_work(self) -> None:
        allocation = allocate(35)
        assert allocation.spent <= 35
        assert allocate(1).spent > 1  # the critical exception, and it says so

    def test_an_empty_queue_is_not_an_error(self) -> None:
        allocation = allocate(10, [])
        assert allocation.admitted == ()
        assert "Running 0 of 0" in allocation.render()

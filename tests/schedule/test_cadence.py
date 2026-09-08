"""How often to look, decided from what looking has found.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ValidationError
from prama.schedule import AdaptiveCadence, CadenceBounds, Observation

HOURLY_TO_DAILY = CadenceBounds(floor_minutes=60, ceiling_minutes=1440, initial_minutes=60)


def policy(bounds: CadenceBounds = HOURLY_TO_DAILY, **kwargs: object) -> AdaptiveCadence:
    return AdaptiveCadence(bounds, **kwargs)  # type: ignore[arg-type]


def settle(verdicts: list[str], start: int = 60) -> int:
    """Run a history through the policy and return where the cadence lands."""
    engine = policy()
    current = start
    for index in range(1, len(verdicts) + 1):
        current = engine.decide(
            Observation(tuple(verdicts[:index])), current_minutes=current
        ).minutes
    return current


class TestBounds:
    def test_both_bounds_are_declared_not_defaulted(self) -> None:
        # A floor invented by the platform would be the platform deciding how
        # late a bank may learn about a break.
        with pytest.raises(TypeError):
            CadenceBounds()  # type: ignore[call-arg]

    def test_impossible_bounds_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="impossible"):
            CadenceBounds(floor_minutes=60, ceiling_minutes=10)

    def test_a_dataset_with_no_history_starts_where_it_was_declared(self) -> None:
        decision = policy().decide(Observation())
        assert decision.minutes == 60
        assert "nothing has been observed yet" in decision.reason

    def test_the_bounds_explain_themselves(self) -> None:
        explanation = policy().explain_bounds()
        assert "at least once every day" in explanation
        assert "no more often than once every hour" in explanation
        assert "declared, not inferred" in explanation


class TestBackingOff:
    def test_a_short_quiet_patch_is_not_evidence(self) -> None:
        decision = policy().decide(Observation(("pass",) * 3), current_minutes=60)
        assert decision.minutes == 60
        assert "too small a sample" in decision.reason

    def test_sustained_quiet_widens_the_interval(self) -> None:
        decision = policy().decide(Observation(("pass",) * 10), current_minutes=60)
        assert decision.minutes > 60
        assert decision.direction == "widened"

    def test_it_widens_slowly(self) -> None:
        # Doubling would take a daily check to fortnightly in four quiet weeks,
        # which is a different control from the one somebody approved.
        after_ten = settle(["pass"] * 10)
        assert 60 < after_ten <= 120

    def test_it_never_passes_the_declared_ceiling(self) -> None:
        assert settle(["pass"] * 200) == 1440

    def test_at_the_ceiling_it_says_so(self) -> None:
        decision = policy().decide(Observation(("pass",) * 50), current_minutes=1440)
        assert decision.minutes == 1440
        assert "declared ceiling" in decision.reason

    def test_a_tier_one_floor_cannot_be_widened_away(self) -> None:
        # The cost of finding out late is not paid by the scheduler.
        tight = CadenceBounds(floor_minutes=15, ceiling_minutes=15)
        engine = AdaptiveCadence(tight)
        assert engine.decide(Observation(("pass",) * 500), current_minutes=15).minutes == 15


class TestReturningOnFailure:
    def test_one_failure_returns_to_the_floor_immediately(self) -> None:
        # Not gradually. The period just after a break is when the next one is
        # most likely and when somebody is watching.
        decision = policy().decide(Observation(("pass",) * 40 + ("fail",)), current_minutes=1440)
        assert decision.minutes == 60
        assert "returns to its floor" in decision.reason

    def test_an_error_counts_the_same_as_a_failure(self) -> None:
        assert policy().decide(Observation(("error",)), current_minutes=480).minutes == 60

    def test_the_widening_starts_again_from_scratch(self) -> None:
        after = settle(["pass"] * 30 + ["fail"] + ["pass"] * 3)
        assert after == 60


class TestIndeterminates:
    def test_a_run_of_indeterminates_holds_the_cadence(self) -> None:
        # Looking more often would not make an empty scope informative, and
        # widening would draw the wrong lesson from it.
        decision = policy().decide(Observation(("indeterminate",) * 4), current_minutes=120)
        assert decision.minutes == 120
        assert "while the scope is investigated" in decision.reason

    def test_a_single_indeterminate_is_not_a_pattern(self) -> None:
        decision = policy().decide(
            Observation(("pass",) * 12 + ("indeterminate",)), current_minutes=60
        )
        assert "indeterminate" not in decision.reason


class TestEveryChangeExplainsItself:
    """An adaptive system that cannot say why is one nobody trusts."""

    def test_a_decision_always_carries_a_reason(self) -> None:
        histories = [
            (),
            ("pass",),
            ("pass",) * 20,
            ("fail",),
            ("indeterminate",) * 5,
        ]
        for history in histories:
            decision = policy().decide(Observation(history), current_minutes=120)
            assert decision.reason
            assert decision.render().endswith(".")

    def test_a_change_says_what_it_changed_from(self) -> None:
        decision = policy().decide(Observation(("pass",) * 15), current_minutes=60)
        assert "instead of every hour" in decision.render()

    def test_an_unchanged_cadence_does_not_pretend_to_be_a_change(self) -> None:
        decision = policy().decide(Observation(("pass",) * 2), current_minutes=60)
        assert not decision.changed
        assert "instead of" not in decision.render()

    def test_intervals_land_on_a_grid_a_person_would_choose(self) -> None:
        # 202 minutes is correct and awkward: harder to reason about, harder to
        # stagger, and it churns.
        engine, current, seen = policy(), 60, []
        for n in range(10, 30):
            current = engine.decide(Observation(("pass",) * n), current_minutes=current).minutes
            seen.append(current)
        assert all(m % 15 == 0 or m < 60 for m in seen)

    def test_it_serialises_for_an_audit_of_the_schedule(self) -> None:
        payload = policy().decide(Observation(("fail",)), current_minutes=480).to_dict()
        assert payload["direction"] == "narrowed"
        assert payload["previous_minutes"] == 480
        assert payload["summary"]

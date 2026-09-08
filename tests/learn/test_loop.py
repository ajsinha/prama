"""Learning from decisions, and proving it helped.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random

from prama.learn.loop import Arm, Decision, Outcome, assign, consider, measure


def population(
    treatment_rate: float, control_rate: float, *, count: int = 600, seed: int = 11
) -> list[Decision]:
    rng = random.Random(seed)
    out = []
    for index in range(count):
        arm = assign(f"p{index}", holdout=0.2)
        rate = treatment_rate if arm is Arm.TREATMENT else control_rate
        outcome = Outcome.ACCEPTED if rng.random() < rate else Outcome.REJECTED
        rank = (
            rng.randrange(1, 8)
            if arm is Arm.TREATMENT and outcome is Outcome.ACCEPTED
            else rng.randrange(1, 20)
        )
        out.append(Decision(f"p{index}", arm, outcome, rank=rank))
    return out


# -- the control arm is the point --------------------------------------------


def test_a_real_improvement_is_significant_and_promotes() -> None:
    uplift = measure(population(0.72, 0.55))
    assert uplift.is_measurable
    assert uplift.is_significant
    assert consider(uplift).should_promote


def test_a_loop_doing_nothing_does_not_promote() -> None:
    """Precision rising over a quarter is equally consistent with the estate
    maturing, the worst feeds being fixed, or reviewers getting tired. A system
    that shows the graph and claims the credit is doing marketing."""
    uplift = measure(population(0.60, 0.60))
    assert not uplift.is_significant
    decision = consider(uplift)
    assert not decision.should_promote
    assert "the interval covers zero" in decision.reason


def test_a_point_estimate_alone_never_promotes() -> None:
    """Promoting on one is how a loop that is doing nothing accumulates a
    series of promotions and a story about continuous improvement."""
    uplift = measure(population(0.62, 0.60))
    assert uplift.difference > 0
    assert not consider(uplift).should_promote


def test_a_gain_too_small_to_be_worth_refreezing_is_named_as_such() -> None:
    uplift = measure(population(0.80, 0.76, count=20_000))
    decision = consider(uplift, minimum_gain=0.10)
    assert uplift.is_significant
    assert not decision.should_promote
    assert "real but small" in decision.reason


def test_a_learning_arm_that_is_worse_points_at_the_labels() -> None:
    """Something in the feedback is teaching it the wrong thing."""
    uplift = measure(population(0.45, 0.70))
    decision = consider(uplift)
    assert not decision.should_promote
    assert "labels are the place to look" in decision.reason


def test_too_little_data_is_not_measurable_rather_than_inconclusive() -> None:
    uplift = measure(population(0.9, 0.4, count=30))
    assert not uplift.is_measurable
    assert "wider than any effect worth claiming" in uplift.describe()


# -- assignment --------------------------------------------------------------


def test_assignment_is_deterministic_so_a_period_reproduces() -> None:
    """An item cannot drift between arms when it is re-proposed, which would
    contaminate both sides at once and in opposite directions."""
    assert assign("proposal-42") is assign("proposal-42")
    assert assign("proposal-42", holdout=0.5) is assign("proposal-42", holdout=0.5)


def test_the_holdout_is_roughly_the_size_asked_for() -> None:
    arms = [assign(f"p{index}", holdout=0.2) for index in range(4000)]
    control = sum(1 for arm in arms if arm is Arm.CONTROL)
    assert 0.17 < control / len(arms) < 0.23


def test_only_the_treatment_arm_learns() -> None:
    assert Arm.TREATMENT.learns
    assert not Arm.CONTROL.learns


# -- what is reported --------------------------------------------------------


def test_the_holdout_cost_is_stated_rather_than_hidden() -> None:
    """A system that hides it is one where somebody eventually turns the
    experiment off without understanding what they are giving up."""
    uplift = measure(population(0.72, 0.55))
    assert uplift.holdout_cost > 0
    assert "the price of knowing any of this" in uplift.describe()


def test_an_improvement_in_ordering_is_seen_where_precision_cannot_see_it() -> None:
    """A model that surfaces the same things in a better order has helped, and
    its precision is unchanged."""
    uplift = measure(population(0.72, 0.55))
    assert uplift.treatment.mean_accepted_rank < uplift.control.mean_accepted_rank
    assert "precision alone cannot see" in uplift.describe()


def test_unreviewed_items_are_counted_as_neither() -> None:
    """Treating them as rejected understates both arms and as accepted
    overstates both, and the bias is not equal when one arm surfaces more."""
    decisions = [
        Decision("a", Arm.TREATMENT, Outcome.PENDING),
        Decision("b", Arm.TREATMENT, Outcome.ACCEPTED),
    ]
    uplift = measure(decisions)
    assert uplift.treatment.surfaced == 2
    assert uplift.treatment.reviewed == 1
    assert uplift.treatment.pending == 1

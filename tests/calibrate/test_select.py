"""Selection: which alerts to raise, given a budget for being wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random

import pytest

from prama.calibrate.select import (
    Budget,
    HierarchicalSelector,
    Hypothesis,
    Level,
    Method,
    benjamini_hochberg,
    power_at,
    simes,
)


def estate(seed: int = 5) -> list[Hypothesis]:
    """A broken feed, twenty healthy datasets, and one quiet real finding."""
    rng = random.Random(seed)
    tests = [
        Hypothesis(f"broken.c{i}", rng.uniform(0, 0.001), Level.CHECK, parent="positions")
        for i in range(400)
    ]
    tests.extend(
        Hypothesis(f"d{d}.c{i}", rng.uniform(0, 1), Level.CHECK, parent=f"dataset{d}")
        for d in range(20)
        for i in range(100)
    )
    tests.append(
        Hypothesis(
            "d3.lei",
            0.00002,
            Level.CHECK,
            parent="dataset3",
            label="counterparty LEI validity",
        )
    )
    return tests


# -- the procedures ----------------------------------------------------------


def test_bh_takes_the_largest_k_and_not_the_first_failure() -> None:
    """The subtlety that catches people: a p-value above its line does not stop
    the procedure. Stopping there is uniformly less powerful and quietly
    wrong."""
    # p3 is above its line; p4 is below it. The correct answer rejects four.
    p_values = [0.001, 0.002, 0.031, 0.039]
    count, _ = benjamini_hochberg(p_values, 0.05)
    assert count == 4


def test_bh_rejects_nothing_when_nothing_is_significant() -> None:
    assert benjamini_hochberg([0.4, 0.6, 0.9], 0.05)[0] == 0


def test_by_is_strictly_more_conservative_than_bh() -> None:
    """The price of assuming nothing about dependence."""
    p_values = [0.001, 0.01, 0.02, 0.03, 0.04]
    assert (
        benjamini_hochberg(p_values, 0.05, method=Method.BY)[0]
        <= benjamini_hochberg(p_values, 0.05, method=Method.BH)[0]
    )


def test_bh_controls_the_false_discovery_rate() -> None:
    """Measured. With 200 nulls and 20 real effects, the proportion of raised
    alerts that are wrong should sit at or below the level."""
    rng = random.Random(3)
    false_discoveries = discoveries = 0
    for _ in range(300):
        nulls = [rng.random() for _ in range(200)]
        real = [rng.random() * 0.0005 for _ in range(20)]
        count, _ = benjamini_hochberg(nulls + real, 0.10)
        chosen = sorted(nulls + real)[:count]
        discoveries += count
        false_discoveries += sum(1 for p in chosen if p in nulls)
    assert false_discoveries / max(discoveries, 1) <= 0.10 + 0.02


def test_simes_summarises_a_family_without_testing_each_member() -> None:
    assert simes([0.5, 0.6, 0.7]) > 0.4
    assert simes([0.001, 0.6, 0.7]) < 0.01
    assert simes([]) == 1.0


# -- hierarchy ---------------------------------------------------------------


def test_a_wholesale_failure_becomes_one_finding_rather_than_four_hundred() -> None:
    """The reader gets four hundred alerts describing one incident, and the one
    that mattered is on page nine."""
    selection = HierarchicalSelector().select(estate(), alpha=0.05)
    assert selection.raised == 2
    rolled = [f for f in selection.findings if f.is_rolled_up]
    assert len(rolled) == 1
    assert len(rolled[0].covers) == 400
    assert selection.rolled_into_parent == 399


def test_the_quiet_finding_survives_beside_the_loud_incident() -> None:
    """The whole purpose of the hierarchy."""
    selection = HierarchicalSelector().select(estate(), alpha=0.05)
    labels = {f.test.label for f in selection.findings}
    assert "counterparty LEI validity" in labels


def test_the_roll_up_carries_the_family_p_value_not_the_worst_child() -> None:
    """The worst child reads as the severity of the incident and is not: one
    catastrophic control among marginal ones is a different incident from
    uniformly bad ones."""
    selection = HierarchicalSelector().select(estate(), alpha=0.05)
    rolled = next(f for f in selection.findings if f.is_rolled_up)
    children = [t.p_value for t in estate() if t.parent == "positions"]
    assert rolled.test.p_value == pytest.approx(simes(children))
    assert rolled.test.p_value > min(children)


def test_roll_up_is_decided_on_the_shape_of_the_failure_not_the_correction() -> None:
    """The defect this replaced: under BY, four hundred controls all below
    0.001 yielded four survivors after the correction — a hundredth of the
    family — so no roll-up fired and the report was four arbitrary members of
    one incident. The conservatism of the procedure had become a statement
    about the incident's extent, which it is not."""
    selection = HierarchicalSelector(method=Method.BY).select(estate(), alpha=0.05)
    rolled = [f for f in selection.findings if f.is_rolled_up]
    assert len(rolled) == 1
    assert len(rolled[0].covers) == 400
    assert not any(f.test.identity.startswith("broken.c") for f in selection.findings)


def test_a_small_family_is_never_rolled_up() -> None:
    """Three monitors failing is three findings; calling it an incident is a
    summary of nothing."""
    tests = [Hypothesis(f"t{i}", 0.0001, Level.CHECK, parent="tiny") for i in range(3)]
    selection = HierarchicalSelector().select(tests, alpha=0.05)
    assert not any(f.is_rolled_up for f in selection.findings)


def test_a_partial_failure_is_not_rolled_up() -> None:
    """Rolling up half a dataset hides which half is broken, and "most of it"
    is a different message from "half of it"."""
    tests = [Hypothesis(f"t{i}", 0.0001, Level.CHECK, parent="half") for i in range(5)]
    tests.extend(Hypothesis(f"u{i}", 0.9, Level.CHECK, parent="half") for i in range(15))
    selection = HierarchicalSelector().select(tests, alpha=0.05)
    assert not any(f.is_rolled_up for f in selection.findings)


def test_a_quiet_family_is_never_opened() -> None:
    """The efficiency of the hierarchy: a dataset with nothing wrong does not
    spend the estate's error budget on two hundred individual tests."""
    selection = HierarchicalSelector().select(estate(), alpha=0.05)
    assert selection.families_unopened >= 15


# -- dependence --------------------------------------------------------------


def test_which_procedure_ran_and_what_it_assumes_is_on_the_result() -> None:
    """A procedure whose assumptions nobody can name is a procedure nobody
    should trust."""
    bh = HierarchicalSelector().select(estate(), alpha=0.05)
    by = HierarchicalSelector(method=Method.BY).select(estate(), alpha=0.05)
    assert "positive regression dependency" in bh.describe()
    assert "assumes nothing about the dependence" in by.describe()


def test_the_price_of_assuming_nothing_is_stated_rather_than_implied() -> None:
    """It sounds free and is not: on this estate it is a factor of eight, and
    what it costs is the quiet LEI finding that BH raises."""
    bh = HierarchicalSelector().select(estate(), alpha=0.05)
    by = HierarchicalSelector(method=Method.BY).select(estate(), alpha=0.05)
    assert by.dependence_price > 5
    assert "costs about a factor of" in by.describe()
    bh_labels = {f.test.label for f in bh.findings}
    by_labels = {f.test.label for f in by.findings}
    assert "counterparty LEI validity" in bh_labels
    assert "counterparty LEI validity" not in by_labels


# -- the dial ----------------------------------------------------------------


def test_a_business_budget_becomes_a_statistical_level() -> None:
    """Every competitor has a sensitivity slider and none can say what number
    it puts on the wall."""
    budget = Budget(false_alarms=2, tests_per_period=10_000)
    assert budget.alpha == pytest.approx(0.0002)
    assert "2 false alarms per month across 10,000 monitor runs" in budget.describe()


def test_the_same_budget_over_ten_monitors_is_a_different_level() -> None:
    """The half that is usually forgotten."""
    assert Budget(2, 10).alpha > Budget(2, 10_000).alpha


def test_a_budget_the_history_cannot_honour_is_refused_with_the_arithmetic() -> None:
    """Saying so beats printing a threshold that means nothing."""
    budget = Budget(false_alarms=2, tests_per_period=10_000)
    assert not budget.achievable_with(resolution=0.011)
    shortfall = budget.shortfall(0.011)
    assert "4,999 comparable observations" in shortfall
    assert "110 false alarms per month" in shortfall


def test_an_achievable_budget_reports_no_shortfall() -> None:
    assert Budget(50, 1000).shortfall(0.001) == ""


def test_power_answers_the_other_question_a_person_asks() -> None:
    """ "What will I miss?" deserves a number rather than a shrug."""
    assert power_at(0.05, effect=0.0, n=100) < 0.10
    assert power_at(0.05, effect=3.0, n=100) > 0.8
    assert power_at(0.001, effect=3.0, n=100) < power_at(0.05, effect=3.0, n=100)

"""Scores that say which arithmetic produced them.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.pql import ast
from prama.score.composite import Measurement, Method, ServiceLevel, score
from prama.semantic.values import Criticality


def broken_cde() -> list[Measurement]:
    """One Tier 1 CDE badly broken, and fifty informational columns fine."""
    return [
        Measurement(
            "lei_valid",
            ast.Dimension.VALIDITY,
            1_000_000,
            380_000,
            Criticality.TIER_1,
        ),
        *(
            Measurement(
                f"c{index}",
                ast.Dimension.COMPLETENESS,
                1_000_000,
                0,
                Criticality.TIER_4,
            )
            for index in range(50)
        ),
    ]


# -- the failure this module exists to prevent -------------------------------


def test_the_weighted_score_is_not_dominated_by_column_count() -> None:
    """The obvious implementation weights each control by criticality times its
    rows and sums — and fails at exactly the job it was written for: fifty
    informational controls outweigh one Tier 1, sixteen-fold weighting and all,
    so a completely broken regulatory CDE scored 91% and the
    materiality-weighted number came out *higher* than the plain mean.
    """
    result = score("positions", broken_cde())
    assert result.composite(Method.WEIGHTED) < result.composite(Method.MEAN)
    assert result.composite(Method.WEIGHTED) == pytest.approx(0.64, abs=0.03)


def test_rows_weight_within_a_tier_and_never_across_one() -> None:
    """Rows are evidence and criticality is importance; multiplying them
    conflates the two."""
    tiny_critical = [
        Measurement("a", ast.Dimension.VALIDITY, 4, 4, Criticality.TIER_1),
        Measurement("b", ast.Dimension.COMPLETENESS, 10_000_000, 0, Criticality.TIER_4),
    ]
    # The four-row Tier 1 control still moves the number substantially.
    assert score("t", tiny_critical).composite(Method.WEIGHTED) < 0.5


def test_a_bigger_control_counts_for_more_within_its_own_tier() -> None:
    """A control over four million rows says more about the tier than one over
    four."""
    mixed = [
        Measurement("small", ast.Dimension.VALIDITY, 10, 10, Criticality.TIER_2),
        Measurement("large", ast.Dimension.VALIDITY, 1_000_000, 0, Criticality.TIER_2),
    ]
    assert score("t", mixed).composites[Method.WEIGHTED] > 0.99


# -- the composites disagree -------------------------------------------------


def test_the_three_composites_answer_different_questions() -> None:
    result = score("positions", broken_cde())
    assert result.composites[Method.MINIMUM] < result.composites[Method.MEAN]
    assert result.methods_disagree
    for method in Method:
        assert method.answers


def test_the_disagreement_is_reported_as_the_finding() -> None:
    """The mean saying 81% and the minimum saying 62% is not a contradiction;
    it is that most of the dataset is fine and one dimension is not."""
    described = score("positions", broken_cde()).describe()
    assert "the composites disagree" in described
    assert "rather than a contradiction" in described


def test_dimensions_come_before_composites() -> None:
    """ "Quality 91%" is not actionable; "completeness 99%, validity 62%" is."""
    result = score("positions", broken_cde())
    assert {item.dimension for item in result.dimensions} == {
        ast.Dimension.VALIDITY,
        ast.Dimension.COMPLETENESS,
    }
    assert result.worst is not None
    assert result.worst.dimension is ast.Dimension.VALIDITY


# -- controls that did not run -----------------------------------------------


def test_a_control_that_did_not_run_is_not_a_pass() -> None:
    """A dataset scoring 100% because half its controls were skipped is the
    most misleading number this module could produce."""
    measurements = [
        Measurement("ran", ast.Dimension.VALIDITY, 100, 0, Criticality.TIER_1),
        Measurement("skipped", ast.Dimension.VALIDITY, 0, 0, Criticality.TIER_1, ran=False),
    ]
    result = score("t", measurements)
    assert result.not_run == 1
    assert result.coverage == 0.5
    assert "did not run" in result.describe()


def test_nothing_measured_is_not_a_perfect_score() -> None:
    result = score(
        "t",
        [Measurement("x", ast.Dimension.VALIDITY, 0, 0, ran=False)],
    )
    assert result.dimensions == ()
    assert "nothing has been measured" in result.describe()


# -- service levels ----------------------------------------------------------


def test_an_objective_without_a_budget_is_a_wish() -> None:
    """The budget converts the promise into a quantity that depletes, which is
    the only form in which a promise changes anybody's behaviour."""
    slo = ServiceLevel("positions", ast.Dimension.VALIDITY, 0.995)
    assert slo.budget == pytest.approx(0.005)
    assert slo.consumed(1_000_000, 5_000) == pytest.approx(1.0)


def test_a_spent_budget_says_the_objective_is_missed() -> None:
    slo = ServiceLevel("positions", ast.Dimension.VALIDITY, 0.995)
    assert "budget is spent" in slo.describe(1_000_000, 380_000)
    assert "objective of 99.5% is missed" in slo.describe(1_000_000, 380_000)


def test_a_budget_running_out_warns_before_it_does() -> None:
    slo = ServiceLevel("positions", ast.Dimension.VALIDITY, 0.995)
    described = slo.describe(1_000_000, 4_000)
    assert "80% of the month's budget used" in described
    assert "missed before the period ends" in described


def test_a_comfortable_budget_says_so_without_alarm() -> None:
    slo = ServiceLevel("positions", ast.Dimension.VALIDITY, 0.995)
    assert "comfortably inside" in slo.describe(1_000_000, 100)

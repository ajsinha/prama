"""Three or more sides, and balances that must roll forward.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

from prama.recon.nway import RollForward, check_roll_forward, reconcile_n_way
from prama.semantic.relationships import Tolerance

TOLERANCE = Tolerance(absolute=1.0)


def three_sides() -> dict[str, dict[str, Decimal | None]]:
    return {
        "front_office": {
            "A": Decimal("1000"),
            "B": Decimal("2000"),
            "C": Decimal("500"),
            "D": Decimal("10"),
        },
        "subledger": {"A": Decimal("1000"), "B": Decimal("2000"), "C": Decimal("500")},
        "gl": {"A": Decimal("1000"), "B": Decimal("2500"), "C": Decimal("700"), "D": Decimal("99")},
    }


# -- N-way -------------------------------------------------------------------


def test_the_odd_side_is_named_rather_than_three_populations_produced() -> None:
    """Three pairwise runs produce three break populations in which a record
    missing from the middle system appears twice, and the two entries look like
    separate items to whoever is working the queue."""
    result = reconcile_n_way(three_sides(), TOLERANCE)
    disagreement = next(item for item in result.disagreements if item.key == "B")
    assert disagreement.odd_side == "gl"
    assert disagreement.consensus == Decimal("2000")
    assert "one side is wrong rather than three disagreeing" in disagreement.describe()


def test_a_side_that_is_repeatedly_odd_points_at_that_system() -> None:
    """One side being the odd one out four hundred times is that side's
    problem, and no pairwise view makes it visible."""
    result = reconcile_n_way(three_sides(), TOLERANCE)
    assert result.by_odd_side["gl"] == 2
    assert "points at that system rather than at the records" in result.describe()


def test_a_key_missing_from_one_side_is_one_finding() -> None:
    result = reconcile_n_way(three_sides(), TOLERANCE)
    missing = next(item for item in result.disagreements if item.key == "D")
    assert missing.missing_from == ("subledger",)


def test_agreement_within_tolerance_is_not_a_disagreement() -> None:
    result = reconcile_n_way(three_sides(), TOLERANCE)
    assert all(item.key != "A" for item in result.disagreements)


def test_every_side_disagreeing_is_a_different_and_worse_situation() -> None:
    """It is not one system being wrong, and calling it that would send
    somebody to a system chosen by iteration order."""
    sides = {
        "a": {"K": Decimal("100")},
        "b": {"K": Decimal("200")},
        "c": {"K": Decimal("300")},
    }
    disagreement = reconcile_n_way(sides, TOLERANCE).disagreements[0]
    assert disagreement.all_disagree
    assert "needs a person" in disagreement.describe()


def test_all_sides_agreeing_says_so_plainly() -> None:
    sides = {name: {"K": Decimal("1")} for name in ("a", "b", "c")}
    assert "all 3 sides agree" in reconcile_n_way(sides, TOLERANCE).describe()


# -- roll-forward ------------------------------------------------------------


def test_movements_that_do_not_explain_the_change_are_a_break() -> None:
    """The failure is invisible to any single-period control: yesterday's
    closing was right, today's closing is right, and the movements between them
    do not account for the difference."""
    entries = [
        RollForward("A", Decimal("1000"), Decimal("200"), Decimal("1200")),
        RollForward("B", Decimal("1000"), Decimal("200"), Decimal("1450")),
    ]
    breaks = check_roll_forward(entries, TOLERANCE)
    assert len(breaks) == 1
    assert breaks[0].key == "B"
    assert "a restatement nobody recorded" in breaks[0].because


def test_a_balanced_roll_forward_produces_nothing() -> None:
    entries = [RollForward("A", Decimal("1000"), Decimal("200"), Decimal("1200"))]
    assert check_roll_forward(entries, TOLERANCE) == ()


def test_the_expected_closing_is_shown_beside_the_actual() -> None:
    entry = RollForward("A", Decimal("1000"), Decimal("200"), Decimal("1450"))
    assert entry.expected == Decimal("1200")
    assert entry.difference == Decimal("250")

"""Rules generalised from a handful of labelled cells.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.core.provenance import Origin
from prama.induce.examples import ExampleInducer, Label, generalisation_provenance

GOOD_LEIS = [
    "5493001KJTIIGC8Y1R12",
    "213800LBQA1Y9L22JB70",
    "HWUPKR0MPOU8FGXBT394",
    "7LTWFZYICNSX8D621K86",
    "ZXTILKJKG63JELOEG630",
]
BAD_LEIS = ["AAAAAAAAAAAAAAAAAA00", "not-an-lei", "", "549300"]


def leis() -> list[Label]:
    return [Label(v, True) for v in GOOD_LEIS] + [Label(v, False) for v in BAD_LEIS]


# -- the Raha result ---------------------------------------------------------


def test_a_usable_rule_comes_from_a_handful_of_labels() -> None:
    """Six labels, and the rule found is the correct one rather than a
    description of the six."""
    few = [Label(v, True) for v in GOOD_LEIS[:3]] + [Label(v, False) for v in BAD_LEIS[:3]]
    result = ExampleInducer().generalise("exposures", "counterparty_lei", few)
    assert result.best is not None
    assert result.best.candidate.predicate == "IS VALID 'lei'"


def test_enumerating_the_labelled_values_is_memorisation_not_a_rule() -> None:
    """With five distinct good LEIs labelled, IN ('5493001…', …) has perfect
    recall on the labels and rejects every valid LEI in the world that is not
    one of those five. It is memorisation with a perfect score."""
    result = ExampleInducer().generalise("exposures", "counterparty_lei", leis())
    assert all("IN ('5493001" not in s.candidate.predicate for s in result.scored)


def test_a_repeated_value_does_signal_a_closed_domain() -> None:
    """Seeing BUY and SELL five times each says the column has two permitted
    values; seeing five identifiers once each says nothing except that there
    were five."""
    labels = [Label(v, True) for v in ["BUY", "SELL", "BUY", "SELL", "BUY"]] + [
        Label(v, False) for v in ["B", "buy", "PURCHASE"]
    ]
    result = ExampleInducer().generalise("trades", "side", labels)
    assert result.best is not None
    assert result.best.candidate.predicate == "IN ('BUY', 'SELL')"


# -- the asymmetry -----------------------------------------------------------


def test_a_single_false_alarm_eliminates_a_candidate() -> None:
    """With twenty labels, one false alarm is five percent, and a control that
    flags five percent of good data is the one that gets the suite switched
    off."""
    result = ExampleInducer().generalise("exposures", "counterparty_lei", leis())
    for scored in result.scored:
        if scored.false_alarms:
            assert not scored.is_admissible


def test_missing_a_bad_value_only_ranks_a_candidate_lower() -> None:
    """A rule that catches half the bad cells and nothing else is a real,
    shippable control."""
    result = ExampleInducer().generalise("exposures", "counterparty_lei", leis())
    admissible = [s for s in result.scored if s.is_admissible]
    assert any(s.missed > 0 for s in admissible)
    assert result.best is not None
    assert result.best.recall == max(s.recall for s in admissible)


# -- active learning ---------------------------------------------------------


def test_the_next_question_is_the_one_the_candidates_disagree_about() -> None:
    """A value they all agree about teaches nothing whichever way it is
    answered. This is the difference between twenty labels and two hundred."""
    result = ExampleInducer().generalise(
        "exposures",
        "counterparty_lei",
        leis(),
        unlabelled=[
            "549300E9PC51EN656011",  # a real LEI: everything accepts it
            "ABCDEFGHIJKLMNOPQR99",  # right shape, wrong check digits
            "12345",  # wrong shape: everything rejects it
        ],
    )
    assert result.next_question is not None
    assert result.next_question.value == "ABCDEFGHIJKLMNOPQR99"
    assert "eliminates about half" in result.next_question.reason


def test_nothing_is_asked_when_one_rule_stands_alone() -> None:
    labels = [
        Label(1.0, True),
        Label(2.0, True),
        Label(3.0, True),
        Label(-1.0, False),
        Label(-2.0, False),
        Label(-9.0, False),
    ]
    result = ExampleInducer().generalise("t", "x", labels, unlabelled=[4.0])
    assert result.best is not None


# -- honest refusals ---------------------------------------------------------


def test_too_few_labels_is_refused_with_the_reason() -> None:
    result = ExampleInducer().generalise("t", "x", [Label("a", True), Label("b", False)])
    assert result.best is None
    assert "too few" in result.refusal


def test_labels_that_are_all_good_have_nothing_to_separate() -> None:
    labels = [Label(v, True) for v in GOOD_LEIS] + [Label("549300E9PC51EN656011", True)]
    result = ExampleInducer().generalise("t", "x", labels)
    assert "nothing for a rule to separate" in result.refusal


def test_when_no_rule_separates_them_the_reason_points_elsewhere() -> None:
    """The distinction may not be about the value itself — it may depend on
    another column, and saying so is more useful than saying nothing."""
    labels = [Label("A", True), Label("A", False)] * 4
    result = ExampleInducer().generalise("t", "x", labels)
    assert result.best is None
    assert "may depend on another column" in result.refusal


def test_a_generalised_rule_is_an_example_origin_and_never_auto_applied() -> None:
    result = ExampleInducer().generalise("exposures", "counterparty_lei", leis())
    assert result.best is not None
    provenance = generalisation_provenance("exposures", "counterparty_lei", result.best, leis())
    assert provenance.origin is Origin.EXAMPLE
    assert not provenance.origin.may_auto_activate
    assert "9 values you labelled" in provenance.observations[0]

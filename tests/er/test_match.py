"""Entity resolution: a score with units.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.er.match import (
    BlockingKey,
    Comparison,
    Decision,
    Resolver,
    estimate_u,
    exact,
    expectation_maximisation,
    normalised,
    similar,
)

RECORDS = [
    {
        "id": "1",
        "name": "ACME Limited",
        "lei": "5493001KJTIIGC8Y1R12",
        "country": "GB",
        "town": "London",
    },
    {
        "id": "2",
        "name": "Acme Ltd.",
        "lei": "5493001KJTIIGC8Y1R12",
        "country": "GB",
        "town": "London",
    },
    {"id": "3", "name": "Acme Ltd", "lei": None, "country": "GB", "town": "London"},
    {
        "id": "4",
        "name": "Beta Corp",
        "lei": "213800LBQA1Y9L22JB70",
        "country": "US",
        "town": "Boston",
    },
    {
        "id": "5",
        "name": "Beta Corp",
        "lei": "213800LBQA1Y9L22JB70",
        "country": "US",
        "town": "Boston",
    },
    {"id": "6", "name": "Gamma SA", "lei": None, "country": "FR", "town": "Paris"},
]


def comparisons() -> list[Comparison]:
    return [
        Comparison("lei", exact, m=0.95, u=0.001),
        Comparison("name", normalised, m=0.9, u=0.05),
        Comparison("town", exact, m=0.85, u=0.2),
        Comparison("country", exact, m=0.98, u=0.35),
    ]


def blocking() -> list[BlockingKey]:
    return [
        BlockingKey("country", lambda record: record.get("country")),
        BlockingKey("name_prefix", lambda record: (record.get("name") or "")[:3].upper() or None),
    ]


def resolver() -> Resolver:
    return Resolver(comparisons(), blocking())


# -- the score has units -----------------------------------------------------


def test_a_rare_agreement_is_worth_more_than_a_common_one() -> None:
    """A matching surname is weak evidence in a population of Smiths and strong
    evidence in a population of Nakagawas, and the arithmetic says so on its
    own rather than needing somebody to notice."""
    rare = Comparison("lei", exact, m=0.95, u=0.001)
    common = Comparison("country", exact, m=0.98, u=0.35)
    assert rare.agreement_weight > common.agreement_weight * 5


def test_disagreement_carries_negative_weight() -> None:
    assert Comparison("lei", exact, m=0.95, u=0.001).disagreement_weight < 0


def test_a_probability_of_one_does_not_produce_an_infinite_weight() -> None:
    """One disagreement would then outvote every other piece of evidence
    forever."""
    certain = Comparison("x", exact, m=1.0, u=0.0)
    assert certain.agreement_weight < 100
    assert certain.disagreement_weight > -100


def test_a_missing_value_contributes_nothing_rather_than_disagreement() -> None:
    """The single most common implementation error here, and it systematically
    separates exactly the records most likely to be duplicates — the sparse
    ones."""
    comparison = Comparison("lei", exact, m=0.95, u=0.001)
    assert comparison.weigh({"lei": None}, {"lei": "X"}) is None
    assert comparison.weigh({"lei": ""}, {"lei": "X"}) is None
    assert comparison.weigh({"lei": "X"}, {"lei": "Y"}) is not None


def test_a_match_resting_on_less_evidence_says_so() -> None:
    """A match resting on two fields out of seven is a different claim from one
    resting on seven."""
    judgement = resolver().judge(RECORDS[0], RECORDS[2])
    assert "lei" in judgement.uninformative
    assert "rests on less evidence than it looks like" in judgement.describe()


# -- three decisions rather than two -----------------------------------------


def test_there_is_a_band_between_match_and_non_match() -> None:
    """A single threshold forces every uncertain pair into a decision nobody
    made, and the uncertain ones are exactly the ones worth a person."""
    judged = Resolver(comparisons(), blocking()).judge(
        {"id": "a", "country": "GB"}, {"id": "b", "country": "GB"}
    )
    assert judged.decision is Decision.REVIEW


def test_a_matching_lei_carries_a_pair_on_its_own() -> None:
    resolved = resolver().resolve(RECORDS)
    pairs = {(item.left, item.right) for item in resolved.matches}
    assert ("1", "2") in pairs
    assert ("4", "5") in pairs


def test_two_different_companies_are_not_matched() -> None:
    resolved = resolver().resolve(RECORDS)
    pairs = {(item.left, item.right) for item in resolved.matches}
    assert ("1", "6") not in pairs
    assert ("4", "6") not in pairs


# -- blocking ----------------------------------------------------------------


def test_blocking_is_where_recall_is_lost_for_good() -> None:
    """A pair never compared can never match, so a wrong key loses records
    silently and nothing downstream recovers them."""
    resolved = resolver().resolve(RECORDS)
    assert resolved.compared < resolved.total_possible
    assert resolved.reduction > 0.5


def test_a_key_that_brings_nothing_together_is_named() -> None:
    keys = [
        BlockingKey("country", lambda record: record.get("country")),
        BlockingKey("nothing", lambda _: None),
    ]
    resolved = Resolver(comparisons(), keys).resolve(RECORDS)
    assert "nothing" in resolved.useless_keys
    assert "brought no pairs together at all" in resolved.describe()


def test_a_redundant_key_is_distinguished_from_a_broken_one() -> None:
    """Reporting only the pairs a key found *first* makes every redundant key
    look broken, which is how somebody deletes the one carrying a population
    they had not thought about."""
    resolved = resolver().resolve(RECORDS)
    assert "name_prefix" not in resolved.useless_keys
    assert resolved.by_key["name_prefix"] > 0


# -- estimating the probabilities --------------------------------------------


def test_the_chance_rate_is_measured_rather_than_assumed() -> None:
    """Almost every random pair is a non-match: with ten thousand records there
    are fifty million pairs and at most a few thousand true matches."""
    population = [
        {"id": str(index), "country": "GB" if index % 4 else "US"} for index in range(200)
    ]
    measured = estimate_u(population, Comparison("country", exact), sample=500)
    assert 0.5 < measured < 0.8


def em_population() -> list[tuple[dict[str, object], dict[str, object]]]:
    """Candidate pairs with a mix of agreement patterns.

    A mix is required rather than convenient: EM separates two populations by
    the *pattern* of agreements, and a candidate set where every pair agrees on
    everything contains no pattern to separate.
    """
    records: list[dict[str, object]] = []
    for index in range(60):
        records.append({"id": f"a{index}", "name": f"Firm {index}", "town": "London"})
        records.append({"id": f"b{index}", "name": f"Firm {index}", "town": "London"})
    for index in range(60):
        records.append({"id": f"c{index}", "name": f"Other {index}", "town": "Paris"})

    pairs = [(records[index], records[index + 1]) for index in range(0, 120, 2)]
    pairs += [
        (records[0], records[121]),
        (records[2], records[125]),
        (records[4], records[130]),
    ]
    return pairs


def test_expectation_maximisation_recovers_the_match_rate_without_labels() -> None:
    """The whole reason to use this method rather than a classifier that needs
    a training set nobody has."""
    start = [
        Comparison("name", exact, m=0.5, u=0.5),
        Comparison("town", exact, m=0.5, u=0.5),
    ]
    learned = expectation_maximisation(start, em_population(), rounds=30)
    name = next(item for item in learned if item.field == "name")
    assert name.m > name.u
    assert name.agreement_weight > 1.0


def test_starting_with_m_equal_to_u_is_a_saddle_point_and_is_handled() -> None:
    """With the two equal, every pair receives exactly the prior as its
    responsibility, both parameters update to the same value, and the algorithm
    sits there for as many rounds as it is given — returning fields worth zero
    bits with no indication anything went wrong."""
    symmetric = [Comparison("name", exact, m=0.5, u=0.5)]
    learned = expectation_maximisation(symmetric, em_population(), rounds=30)
    assert learned[0].m != learned[0].u
    assert learned[0].agreement_weight > 0


def test_agreement_is_asked_for_directly_rather_than_read_off_a_weight() -> None:
    """Inferring it from the sign of the weight is wrong at exactly one point,
    and that point is where EM starts: with m == u the weight is zero, `> 0` is
    False, and every agreement counts as a disagreement."""
    flat = Comparison("x", exact, m=0.5, u=0.5)
    assert flat.agreement_weight == 0.0
    assert flat.agrees({"x": "a"}, {"x": "a"}) is True
    assert flat.agrees({"x": "a"}, {"x": "b"}) is False
    assert flat.agrees({"x": None}, {"x": "b"}) is None


# -- comparison functions ----------------------------------------------------


def test_legal_forms_do_not_make_two_companies_different() -> None:
    """ "ACME Ltd." and "Acme Limited" are the same company, and a comparison
    that says otherwise makes every entity resolution over company names
    useless before the arithmetic starts."""
    assert normalised("ACME Limited", "Acme Ltd.")
    assert normalised("Beta Corp", "beta corporation")
    assert not normalised("Acme", "Beta")


def test_similarity_is_available_for_the_cases_normalisation_misses() -> None:
    close = similar(0.6)
    assert close("Johnathan Smith", "Jonathan Smith")
    assert not close("Smith", "Nakagawa")


def test_every_contribution_is_visible_so_a_match_can_be_argued_with() -> None:
    judgement = resolver().judge(RECORDS[0], RECORDS[1])
    fields = {field for field, _ in judgement.contributions}
    assert fields == {"lei", "name", "town", "country"}
    assert judgement.score == pytest.approx(sum(weight for _, weight in judgement.contributions))

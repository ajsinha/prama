"""Coverage, measured so the number cannot flatter.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.derive.coverage import CoverageAnalyser
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.derive.generator import ControlGenerator
from prama.pql import ast
from prama.pql.parser import parse_control
from prama.semantic.values import (
    Criticality,
    Grain,
    Optionality,
    ValueDomain,
    ValueDomainKind,
)


def positions(**overrides: object) -> DatasetDeclaration:
    base: dict[str, object] = {
        "name": "positions",
        "criticality": Criticality.TIER_1,
        "grain": Grain(attributes=("account_id",), statement="one row per account"),
        "attributes": (
            AttributeDeclaration(name="account_id", optionality=Optionality.MANDATORY),
            AttributeDeclaration(
                name="counterparty_lei",
                semantic_type="lei",
                is_cde=True,
                obligations=("FR Y-14Q",),
                optionality=Optionality.MANDATORY,
            ),
            AttributeDeclaration(
                name="market_value",
                currency_attribute="ccy",
                optionality=Optionality.MANDATORY,
                value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0),
            ),
            AttributeDeclaration(name="ccy"),
            AttributeDeclaration(name="comment"),
        ),
    }
    base.update(overrides)
    return DatasetDeclaration(**base)  # type: ignore[arg-type]


def generated(declaration: DatasetDeclaration) -> list[ast.Control]:
    return [c.control for c in ControlGenerator().generate(declaration).controls]


# -- the number that flatters ------------------------------------------------


def test_coverage_is_measured_per_dimension_not_per_column() -> None:
    """A single IS NOT NULL makes a column "covered" while its format, its
    domain and its consistency go unchecked."""
    declaration = positions(
        grain=None,
        attributes=(
            AttributeDeclaration(
                name="lei",
                optionality=Optionality.MANDATORY,
                semantic_type="lei",
                is_cde=True,
            ),
        ),
    )
    completeness_only = [parse_control("CHECK positions.lei IS NOT NULL DIMENSION completeness")]
    coverage = CoverageAnalyser().analyse(declaration, completeness_only)
    assert coverage.touched_fraction == 1.0
    assert coverage.fraction < coverage.touched_fraction
    assert {g.dimension for g in coverage.gaps} == {
        ast.Dimension.VALIDITY,
        ast.Dimension.ACCURACY,
    }


def test_the_flattering_number_is_reported_beside_the_honest_one() -> None:
    """So the difference is visible rather than a choice somebody made about
    which to print. Shown on the case that makes it matter: every column has a
    completeness control and nothing else, which a per-column count calls
    fully covered."""
    declaration = positions(
        grain=None,
        attributes=(
            AttributeDeclaration(
                name="a",
                optionality=Optionality.MANDATORY,
                semantic_type="lei",
                is_cde=True,
            ),
            AttributeDeclaration(
                name="b",
                optionality=Optionality.MANDATORY,
                semantic_type="isin",
                is_cde=True,
            ),
        ),
    )
    completeness_only = [
        parse_control("CHECK positions.a IS NOT NULL DIMENSION completeness"),
        parse_control("CHECK positions.b IS NOT NULL DIMENSION completeness"),
    ]
    coverage = CoverageAnalyser().analyse(declaration, completeness_only)
    assert coverage.touched_fraction == 1.0
    assert coverage.fraction < 0.5
    assert "which is the number that flatters" in coverage.describe()


def test_a_completeness_control_alone_does_not_cover_validity() -> None:
    declaration = positions()
    only_completeness = [
        parse_control("CHECK positions.counterparty_lei IS NOT NULL DIMENSION completeness")
    ]
    coverage = CoverageAnalyser().analyse(declaration, only_completeness)
    missing = {g.dimension for g in coverage.gaps if g.attribute == "counterparty_lei"}
    assert ast.Dimension.VALIDITY in missing
    assert ast.Dimension.COMPLETENESS not in missing


# -- what applies -----------------------------------------------------------


def test_a_dimension_an_attribute_cannot_have_is_not_counted_against_it() -> None:
    """Counting them would make a well-covered estate look sparse and bury the
    real gaps in the noise."""
    plain = positions(
        grain=None,
        attributes=(AttributeDeclaration(name="comment", optionality=Optionality.MANDATORY),),
    )
    coverage = CoverageAnalyser().analyse(plain, [])
    assert {g.dimension for g in coverage.gaps} == {ast.Dimension.COMPLETENESS}


def test_a_column_declared_optional_has_its_completeness_question_answered() -> None:
    """By the declaration, which said no control is wanted. Counting it as a
    gap would mean an estate could only reach 100% by declaring every column
    mandatory — pushing people into false declarations to move a metric."""
    optional = positions(
        grain=None,
        attributes=(AttributeDeclaration(name="comment", optionality=Optionality.OPTIONAL),),
    )
    assert CoverageAnalyser().analyse(optional, []).gaps == ()


def test_only_a_cde_is_expected_to_have_an_accuracy_control() -> None:
    """For anything else there is nothing to compare against that is not
    equally unverified."""
    declaration = positions()
    coverage = CoverageAnalyser().analyse(declaration, [])
    accuracy = {g.attribute for g in coverage.gaps if g.dimension is ast.Dimension.ACCURACY}
    assert accuracy == {"counterparty_lei"}


def test_an_amount_is_expected_to_be_consistent_with_its_currency() -> None:
    declaration = positions()
    coverage = CoverageAnalyser().analyse(declaration, [])
    consistency = {g.attribute for g in coverage.gaps if g.dimension is ast.Dimension.CONSISTENCY}
    assert "market_value" in consistency


def test_a_referential_control_answers_the_accuracy_expectation() -> None:
    """It checks a value against another dataset, which is exactly what
    "compared with something outside the row" asks for. Treating them as
    different would report a CDE with a master-data check as having no accuracy
    control, which is not true in any sense a reviewer would recognise."""
    declaration = positions()
    referential = [
        parse_control("CHECK positions.counterparty_lei REFERENCES parties.lei DIMENSION integrity")
    ]
    coverage = CoverageAnalyser().analyse(declaration, referential)
    accuracy = {g.attribute for g in coverage.gaps if g.dimension is ast.Dimension.ACCURACY}
    assert "counterparty_lei" not in accuracy


def test_a_control_with_no_declared_dimension_covers_nothing() -> None:
    """A suite nobody has classified cannot be measured, and assuming a
    dimension would produce a number that is wrong and confident."""
    declaration = positions()
    unclassified = [parse_control("CHECK positions.account_id IS NOT NULL")]
    coverage = CoverageAnalyser().analyse(declaration, unclassified)
    assert any(
        g.attribute == "account_id" and g.dimension is ast.Dimension.COMPLETENESS
        for g in coverage.gaps
    )


# -- ranking -----------------------------------------------------------------


def test_an_uncontrolled_cde_feeding_a_return_ranks_first() -> None:
    """The question asked about it is not "how bad is the data?" but "what did
    you attest to?"."""
    declaration = positions()
    coverage = CoverageAnalyser().analyse(declaration, generated(declaration))
    assert coverage.worst(1)[0].attribute == "counterparty_lei"


def test_the_ranking_actually_discriminates() -> None:
    """An earlier version clamped each component to 1.0, so on a Tier 1 dataset
    every gap scored exactly 1.00 and "sort by risk" quietly became alphabetical
    order — the one thing a ranked list must not become."""
    declaration = positions()
    coverage = CoverageAnalyser().analyse(declaration, [])
    scores = {round(g.risk, 3) for g in coverage.gaps}
    assert len(scores) > 1
    assert max(scores) < 1.0001


def test_a_completeness_gap_outranks_other_gaps_at_the_same_tier() -> None:
    """A column that is half empty makes every other control on it a statement
    about the half that is there."""
    declaration = positions()
    coverage = CoverageAnalyser().analyse(declaration, [])
    same_attribute = [g for g in coverage.gaps if g.attribute == "market_value"]
    ranked = sorted(same_attribute, key=lambda g: -g.risk)
    assert ranked[0].dimension is ast.Dimension.COMPLETENESS


def test_every_gap_names_what_would_close_it() -> None:
    """A gap report that names the problem and not the fix is a list somebody
    reads once."""
    declaration = positions()
    for gap in CoverageAnalyser().analyse(declaration, []).gaps:
        assert gap.remedy
        assert gap.describe().endswith(".")


# -- the acceptance criterion ------------------------------------------------


def test_the_wave_target_is_measured_on_the_honest_number() -> None:
    """≥80% of columns and ≥95% of CDEs, per dimension rather than per
    column."""
    declaration = positions()
    assert not CoverageAnalyser().analyse(declaration, generated(declaration)).meets_target


def test_a_fully_controlled_dataset_meets_it() -> None:
    declaration = positions(
        grain=None,
        attributes=(AttributeDeclaration(name="x", optionality=Optionality.MANDATORY),),
    )
    covered = [parse_control("CHECK positions.x IS NOT NULL DIMENSION completeness")]
    coverage = CoverageAnalyser().analyse(declaration, covered)
    assert coverage.fraction == 1.0
    assert coverage.meets_target


def test_an_estate_is_ordered_worst_first() -> None:
    """The purpose of the list is to be worked from the top."""
    good = positions(
        name="clean",
        grain=None,
        attributes=(AttributeDeclaration(name="x", optionality=Optionality.MANDATORY),),
    )
    bad = positions(name="messy")
    estate = CoverageAnalyser().analyse_estate(
        [good, bad],
        {"clean": [parse_control("CHECK clean.x IS NOT NULL DIMENSION completeness")]},
    )
    assert estate[0].dataset == "messy"

"""The inference cascade: what a column holds, and how strongly we know it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from prama.classify.semantic import (
    Classification,
    ColumnSample,
    Conflict,
    ConflictKind,
    Fit,
    NoClassification,
    SemanticAdjudicator,
    SemanticClassifier,
    Stage,
)

ISINS = (
    "US0378331005",
    "GB0002634946",
    "DE0005190003",
    "FR0000131104",
    "US5949181045",
    "JP3633400001",
    "CH0012032048",
    "NL0011794037",
    "US02079K3059",
    "GB00B03MLX29",
)

LEIS = (
    "5493001KJTIIGC8Y1R12",
    "213800LBQA1Y9L22JB70",
    "HWUPKR0MPOU8FGXBT394",
    "7LTWFZYICNSX8D621K86",
    "ZXTILKJKG63JELOEG630",
    "549300E9PC51EN656011",
    "5493000F4ZO33MV32P92",
    "549300NRMB4RQ8XW1F53",
)

CURRENCIES = ("EUR", "USD", "GBP", "JPY", "CHF", "SEK", "NOK", "AUD", "CAD", "EUR")


def sample(name: str, values: Sequence[str | None], **kwargs: object) -> ColumnSample:
    return ColumnSample(name=name, values=tuple(values), **kwargs)  # type: ignore[arg-type]


# -- what the cascade is for ------------------------------------------------


def test_a_checksum_settles_the_type_whatever_the_column_is_called() -> None:
    result = SemanticClassifier().classify(sample("col_27", ISINS))
    assert isinstance(result, Classification)
    assert result.semantic_type == "isin"
    assert result.stage is Stage.CHECKSUM
    assert result.is_evidence


def test_confidence_is_derived_from_the_odds_of_the_accident() -> None:
    """Ten values satisfying a base-ten check digit is one in ten billion, and
    the number says so rather than being a taste."""
    result = SemanticClassifier().classify(sample("x", ISINS))
    assert isinstance(result, Classification)
    assert result.confidence > 0.999_999_99
    assert "chance" in result.rationale


def test_a_mod_97_type_reaches_certainty_faster_than_a_mod_10_one() -> None:
    """Two check characters carry more evidence than one, and the derivation
    reflects that instead of assigning both the same 0.9."""
    classifier = SemanticClassifier()
    lei = classifier.classify(sample("a", LEIS[:8]))
    isin = classifier.classify(sample("b", ISINS[:8]))
    assert isinstance(lei, Classification) and isinstance(isin, Classification)
    assert lei.confidence > isin.confidence


def test_a_code_list_settles_a_type_too() -> None:
    result = SemanticClassifier().classify(sample("ccy", CURRENCIES))
    assert isinstance(result, Classification)
    assert result.semantic_type == "iso4217"
    assert result.stage is Stage.CODELIST


# -- the part that matters: disagreement ------------------------------------


def test_a_column_named_for_a_type_it_does_not_contain_reports_the_conflict() -> None:
    """The failure this module exists for. A column called isin full of
    values that fail the check digit must not be quietly classified as the
    weaker type that its *shape* happens to fit."""
    fabricated = (ISINS[0], *("GB0000000000",) * 9)
    result = SemanticClassifier().classify(sample("isin", fabricated))
    assert isinstance(result, Classification)
    assert result.conflicts
    assert result.conflicts[0].kind is ConflictKind.NAME_CONTRADICTED
    assert "10.0%" in result.conflicts[0].message
    assert not result.may_auto_apply
    assert not result.is_evidence


def test_the_refutation_is_the_headline_not_a_footnote() -> None:
    """Ranking by fit alone gets this backwards: the fabricated values fit the
    weaker type perfectly *because* they fail the stronger one."""
    fabricated = ("GB0000000000",) * 12
    result = SemanticClassifier().classify(sample("isin", fabricated))
    assert isinstance(result, Classification)
    assert result.conflicts[0].kind is ConflictKind.NAME_CONTRADICTED
    assert "isin" in result.conflicts[0].candidates


def test_a_declared_type_the_data_refutes_is_questioned_not_enforced() -> None:
    """Generating the declared control would alert on 90% of rows and be
    switched off by Friday, taking the discovery with it."""
    fabricated = (LEIS[0], *("HWUPKR0MPOU8FGXBT395",) * 11)
    conflict = SemanticClassifier().contradicts_declaration(
        sample("counterparty_lei", fabricated, dataset="exposures"), "lei"
    )
    assert isinstance(conflict, Conflict)
    assert "exposures.counterparty_lei" in conflict.message
    assert "ISO 17442" in conflict.message


def test_a_declaration_the_data_supports_raises_nothing() -> None:
    assert SemanticClassifier().contradicts_declaration(sample("lei", LEIS), "lei") is None


def test_finding_cardholder_data_is_reported_as_a_sensitivity_conflict() -> None:
    """Usually a discovery that the data is somewhere it should not be, which
    is a different conversation from a quality finding."""
    cards = ("4111111111111111", "5500005555555559", "4012888888881881") * 4
    result = SemanticClassifier().classify(sample("ref", cards))
    assert isinstance(result, Classification)
    assert any(c.kind is ConflictKind.SENSITIVE_CONTENT for c in result.conflicts)


# -- honest limits ----------------------------------------------------------


def test_a_shape_match_on_a_small_sample_is_not_evidence() -> None:
    """Ten values of the right shape with no check digit behind them is a
    suggestion. A hundred is a finding."""
    classifier = SemanticClassifier()
    few = classifier.classify(sample("x", [str(uuid.UUID(int=i)) for i in range(10)]))
    many = classifier.classify(sample("x", [str(uuid.UUID(int=i)) for i in range(200)]))
    assert isinstance(few, Classification) and isinstance(many, Classification)
    assert few.stage is Stage.PATTERN
    assert not few.is_evidence
    assert many.is_evidence


def test_too_few_values_means_no_content_stage_speaks_at_all() -> None:
    """Six ISINs verifying is a coincidence worth noting; two is a Tuesday."""
    result = SemanticClassifier().classify(sample("x", ISINS[:3]))
    assert isinstance(result, NoClassification)


def test_a_refusal_distinguishes_a_small_sample_from_a_thorough_search() -> None:
    """Collapsing them sends a steward to look at a column never examined."""
    thin = SemanticClassifier().classify(sample("x", ISINS[:3]))
    searched = SemanticClassifier().classify(sample("x", ["free text note"] * 30))
    assert isinstance(thin, NoClassification) and isinstance(searched, NoClassification)
    assert "at least 8 are needed" in thin.reason
    assert "none matched" in searched.reason


def test_a_name_alone_never_produces_a_clean_fit() -> None:
    """Nothing was measured, so nothing is settled."""
    result = SemanticClassifier().classify(sample("counterparty_lei", ["", None, "  "]))
    assert isinstance(result, Classification)
    assert result.stage is Stage.NAME
    assert result.fit is not Fit.CLEAN
    assert not result.may_auto_apply
    assert "suggestion, not a finding" in result.rationale


def test_a_mixed_column_supports_no_control() -> None:
    """Two things in one column is a worse problem than bad values, and it
    needs a person rather than an alert."""
    mixed = (*ISINS[:5], *CURRENCIES[:5])
    result = SemanticClassifier().classify(sample("x", mixed))
    if isinstance(result, Classification):
        assert not result.may_auto_apply


def test_nothing_fitting_is_an_explained_refusal_not_a_none() -> None:
    result = SemanticClassifier().classify(
        sample("notes", ["a free text note about the trade"] * 20)
    )
    assert isinstance(result, NoClassification)
    assert "none matched" in result.reason
    assert result.attempted


def test_a_numeric_column_is_not_tested_against_letter_bearing_types() -> None:
    """Spending a pass to produce a guaranteed no, then reporting twelve types
    attempted when four were possible."""
    result = SemanticClassifier().classify(
        sample("amount", [str(i) for i in range(1000, 1030)], physical_type="numeric(18,2)")
    )
    attempted = result.attempted if isinstance(result, NoClassification) else ()
    assert "isin" not in attempted
    assert "lei" not in attempted


def test_alternatives_are_kept_because_one_of_two_is_a_real_answer() -> None:
    """An ISIN also has a UPI's shape. Collapsing that to a single guess loses
    the useful part."""
    result = SemanticClassifier().classify(sample("x", ISINS))
    assert isinstance(result, Classification)
    assert "upi" in result.alternatives


# -- the model stage, which may never decide anything -----------------------


class StubAdjudicator(SemanticAdjudicator):
    """Stands in for the model. Records what vocabulary it was given."""

    def __init__(self) -> None:
        self.offered: tuple[str, ...] = ()

    def adjudicate(
        self, sample: ColumnSample, vocabulary: Sequence[str]
    ) -> Classification | NoClassification:
        self.offered = tuple(vocabulary)
        return Classification(
            semantic_type=vocabulary[0],
            stage=Stage.MODEL,
            fit=Fit.CLEAN,
            hit_rate=1.0,
            examined=len(sample.populated),
            confidence=1.0,
            rationale="the model said so",
        )


def test_the_model_is_only_consulted_when_every_other_stage_is_silent() -> None:
    adjudicator = StubAdjudicator()
    classifier = SemanticClassifier(adjudicator=adjudicator)
    settled = classifier.classify(sample("x", ISINS))
    assert isinstance(settled, Classification)
    assert settled.stage is Stage.CHECKSUM
    assert adjudicator.offered == ()


def test_the_model_chooses_from_a_closed_vocabulary() -> None:
    """It may not invent a type. An unknown semantic type would compile to a
    check that passes everything."""
    adjudicator = StubAdjudicator()
    SemanticClassifier(adjudicator=adjudicator).classify(sample("notes", ["free text"] * 20))
    assert "isin" in adjudicator.offered
    assert "iso4217" in adjudicator.offered


def test_a_model_classification_can_never_be_auto_applied() -> None:
    """However confident it claims to be. A guess about what a column means is
    a fine thing to show somebody and an unacceptable thing to alert on."""
    adjudicator = StubAdjudicator()
    result = SemanticClassifier(adjudicator=adjudicator).classify(
        sample("notes", ["free text"] * 20)
    )
    assert isinstance(result, Classification)
    assert result.confidence == 1.0
    assert not result.may_auto_apply
    assert not result.is_evidence


def test_the_cascade_runs_to_a_useful_answer_with_no_model_at_all() -> None:
    """An air-gapped deployment loses nothing that produces a verdict."""
    classifier = SemanticClassifier(adjudicator=None)
    for values, expected in ((ISINS, "isin"), (LEIS, "lei"), (CURRENCIES, "iso4217")):
        result = classifier.classify(sample("x", values))
        assert isinstance(result, Classification)
        assert result.semantic_type == expected

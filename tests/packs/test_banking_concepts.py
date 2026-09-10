"""The banking concept model.

The concept model earns its place only if it declines. A matcher that always
returns something has moved the guessing from the analyst to the tool, where it
is harder to see and carries an air of authority.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.classify import VALIDATORS
from prama.packs.banking import concepts
from prama.packs.banking.concepts import Concept, Property, Role, Standing


class TestTheOntologyItself:
    def test_it_ships_the_concepts_the_design_names(self) -> None:
        names = {c.name for c in concepts.CONCEPTS}
        for expected in ("Account", "Trade", "Position", "Exposure", "Balance", "Loan"):
            assert expected in names

    def test_every_semantic_type_names_a_validator_that_exists(self) -> None:
        """The point of naming a validator rather than carrying a pattern: the
        check that a column holds LEIs lives in one place, and this ontology
        cannot drift from it."""
        known = set(VALIDATORS.names())
        for concept in concepts.CONCEPTS:
            for semantic_type in concept.semantic_types:
                assert semantic_type in known, f"{concept.name} names {semantic_type}"

    def test_a_property_naming_an_unknown_type_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="no validator provides"):
            Property(name="x", semantic_type="not_a_real_validator")

    def test_a_concept_with_no_identifying_property_is_refused(self) -> None:
        """It would match every table with the right shape, and be reported as
        a confident match."""
        with pytest.raises(ValueError, match="no identifying property"):
            Concept(
                name="Anything",
                description="",
                properties=(Property(name="amount", role=Role.DEFINING),),
            )

    def test_a_spelling_cannot_mean_two_properties_of_one_concept(self) -> None:
        """A column carrying it would be counted twice, inflating the match."""
        with pytest.raises(ValueError, match="spells two properties"):
            Concept(
                name="Muddled",
                description="",
                properties=(
                    Property(name="amount", role=Role.IDENTIFYING, aliases=("value",)),
                    Property(name="market_value", aliases=("value",)),
                ),
            )

    def test_every_concept_that_is_confusable_says_what_it_is_not(self) -> None:
        """Position, Balance and Exposure are confused by people, not only by
        matchers, and the boundary is the part a steward actually reads."""
        for name in ("Position", "Balance", "Exposure", "Trade", "Transaction", "Loan"):
            assert concepts.concept(name).boundary

    def test_lookup_is_case_and_separator_insensitive(self) -> None:
        assert concepts.concept("legal entity").name == "Legal Entity"
        assert concepts.concept("LEGAL_ENTITY").name == "Legal Entity"

    def test_an_unknown_concept_lists_the_known_ones(self) -> None:
        """Reached from the CLI with a name somebody typed. A KeyError
        traceback is not an answer to a typo."""
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError) as caught:
            concepts.concept("Sprocket")
        assert "Account" in caught.value.remedy


class TestRecognitionDeclines:
    """The behaviour that makes the rest trustworthy."""

    def test_a_shared_shape_is_recognised_as_nothing(self) -> None:
        """Position, Balance and Exposure all carry an amount, a currency and
        an as-of date. Counting overlapping properties calls a table all
        three."""
        assert concepts.identify(["as_of_date", "amount", "currency"]) == ()

    def test_a_missing_identifier_refutes_the_concept(self) -> None:
        result = concepts.recognise("Account", ["currency", "status", "product"])
        assert result.standing is Standing.NOT_RECOGNISED
        assert "account_id" in result.reason

    def test_an_identifier_alone_is_possible_not_recognised(self) -> None:
        """`account_id` appears on a payment, a fee, a statement line and an
        audit record, none of which is an Account."""
        result = concepts.recognise("Account", ["account_id"])
        assert result.standing is Standing.POSSIBLE
        assert "references Account" in result.reason

    def test_a_missing_defining_property_downgrades_rather_than_refutes(self) -> None:
        """An Exposure reported gross, with no netting set, is an Exposure —
        and one whose figure overstates large-exposure breaches."""
        result = concepts.recognise("Exposure", ["cpty_id", "exposure_date", "gross_exposure"])
        assert result.standing is Standing.POSSIBLE
        assert "net_notional" in result.reason
        assert "netting_set" in result.missing_defining

    def test_a_complete_table_is_recognised(self) -> None:
        result = concepts.recognise(
            "Balance",
            ["account_id", "balance_date", "bal_type", "balance", "ccy"],
        )
        assert result.standing is Standing.RECOGNISED
        assert bool(result) is True

    def test_recognition_is_falsy_unless_it_is_firm(self) -> None:
        """`if recognise(...)` must not be true for a maybe."""
        assert not concepts.recognise("Account", ["account_id"])
        assert not concepts.recognise("Account", ["colour"])


class TestRecognitionReportsRatherThanDecides:
    def test_it_returns_every_candidate_rather_than_a_winner(self) -> None:
        """A table of settled trades is a Trade and, grouped, a Position.
        Picking one silently is how a Position rule ends up asserted on trade
        rows."""
        candidates = concepts.identify(["account_id", "balance_date", "bal_type", "balance", "ccy"])
        assert len(candidates) > 1
        assert candidates[0].concept == "Balance"

    def test_firm_recognitions_rank_above_possible_ones(self) -> None:
        candidates = concepts.identify(["account_id", "balance_date", "bal_type", "balance", "ccy"])
        standings = [c.standing for c in candidates]
        assert standings == sorted(standings, key=lambda s: s is not Standing.RECOGNISED)

    def test_it_names_the_columns_it_could_not_place(self) -> None:
        """The unmatched columns are where a tenant's own vocabulary lives, and
        they are the input to extending the ontology."""
        result = concepts.recognise("Account", ["account_id", "ccy", "widget_flag"])
        assert "widget_flag" in result.unmatched_columns

    def test_it_says_which_column_should_validate_as_what(self) -> None:
        """The practical payoff: recognising a table as a Trade tells you which
        column ought to validate as an ISIN."""
        result = concepts.recognise(
            "Trade",
            ["trade_id", "execution_time", "buy_sell", "quantity", "price", "ccy", "isin"],
        )
        assert ("isin", "isin") in result.expected_types

    def test_an_alias_maps_to_the_canonical_property(self) -> None:
        result = concepts.recognise("Trade", ["deal_id", "execution_time", "venue_mic"])
        assert ("deal_id", "trade_id") in result.matched
        assert ("venue_mic", "venue") in result.matched

    def test_two_columns_cannot_both_claim_one_property(self) -> None:
        """`isin` and `security_isin` both spell Instrument's identifier. Both
        counting inflates the match past the number of properties there are."""
        result = concepts.recognise("Instrument", ["isin", "security_isin", "asset_class", "ccy"])
        claimed = [name for _, name in result.matched]
        assert claimed.count("isin") == 1

    def test_matching_is_exact_rather_than_fuzzy(self) -> None:
        """`settlement_amount` and `settled_amount` are the same thing to a
        reader and different here. The fix is an alias somebody wrote down,
        which is reviewable, not an edit distance nobody can predict."""
        result = concepts.recognise("Account", ["accountid", "acct_ccy"])
        assert ("accountid", "account_id") in result.matched  # separators only
        assert "acct_ccy" in result.unmatched_columns  # not fuzzily "currency"

    def test_a_copybook_spelling_is_the_same_spelling(self) -> None:
        """`ACCT-NO` from a copybook, `account_no` from a warehouse and
        `AccountNo` from an extract are one name to every person who reads
        them. Distinguishing them reports a mainframe extract as
        unrecognisable, which is the estate this pack exists for."""
        for spelling in ("ACCT-NO", "account_no", "AccountNo", "  acct no  "):
            result = concepts.recognise("Account", [spelling, "ccy", "status"])
            assert result.standing is Standing.RECOGNISED, spelling

    def test_the_dict_form_carries_the_reason(self) -> None:
        payload = concepts.recognise("Account", ["account_id"]).to_dict()
        assert payload["standing"] == "possible"
        assert payload["reason"]


class TestItNeverAdjudicates:
    def test_recognition_imports_no_model(self) -> None:
        """CON-007: a concept match is a proposal a steward confirms. It is
        column names against a fixed vocabulary — deterministic, reviewable,
        and wrong in ways somebody can see."""
        import pathlib

        source = pathlib.Path(concepts.__file__).read_text()
        for forbidden in ("prama.llm", "prama.assistant", "openai", "anthropic"):
            assert forbidden not in source

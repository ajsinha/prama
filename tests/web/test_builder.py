"""The no-code rule builder.

Prama's thesis is that a business owner, not a DBA, owns data quality. This is
the module where that claim is either true or marketing, so these tests are
written against the ways a builder is a toy rather than a tool: it emits PQL
that does not re-read, it silently produces a rule that can never pass, or it
lets a control out with no reason attached.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ValidationError
from prama.pql import parse_control
from prama.pql.ast import Severity, UnknownPolicy
from prama.web.builder import QUESTIONS, build, render_and_verify

#: One complete answer set per rule the builder offers. Kept exhaustive on
#: purpose: the parametrised round-trip test below is only a guarantee about
#: the whole catalogue if the catalogue is fully covered, so a new rule with no
#: entry here fails the coverage test rather than quietly going unchecked.
ANSWERS: dict[str, dict[str, str]] = {
    "not_null": {"column": "notional_amount"},
    "in_list": {"column": "status", "values": "NEW, SETTLED, CANCELLED"},
    "matches": {"column": "isin", "pattern": "^[A-Z]{2}[0-9A-Z]{9}[0-9]$"},
    "between": {"column": "weight", "lower": "0", "upper": "1"},
    "unique_key": {"columns": "account_id, instrument_id, as_of_date"},
    "row_count": {"minimum": "1000", "maximum": "50000"},
    "references": {
        "column": "account_id",
        "reference_dataset": "accounts",
        "reference_column": "id",
    },
    "fresh": {"tolerance_minutes": "30", "due_time": "06:30", "calendar": "TARGET2"},
}


def _build(rule: str, **overrides: str) -> object:
    answers = dict(ANSWERS[rule])
    answers.update(overrides)
    return build(
        dataset="positions_eod",
        rule=rule,
        because="declared by the business",
        **answers,  # type: ignore[arg-type]
    )


class TestEveryRuleRoundTrips:
    """``parse(render(c)) == c`` is the property the language rests on, and the
    builder is the one place that can break it invisibly: somebody who never
    reads PQL cannot notice that what was generated is not what re-parses."""

    def test_the_catalogue_is_fully_covered_by_these_tests(self) -> None:
        assert {q.key for q in QUESTIONS} == set(ANSWERS)

    @pytest.mark.parametrize("rule", sorted(ANSWERS))
    def test_it_renders_and_reads_back_identically(self, rule: str) -> None:
        control = _build(rule)
        text = render_and_verify(control)  # type: ignore[arg-type]
        assert parse_control(text) == control

    @pytest.mark.parametrize("rule", sorted(ANSWERS))
    def test_it_survives_a_threshold_and_an_unknown_policy(self, rule: str) -> None:
        """The two modifiers that attach to every rule, and the two most likely
        to render in a form the parser does not produce."""
        control = build(
            dataset="positions_eod",
            rule=rule,
            because="declared by the business",
            severity="critical",
            tolerated_percent="0.5",
            unknown_is_violation=False,
            **ANSWERS[rule],  # type: ignore[arg-type]
        )
        assert parse_control(render_and_verify(control)) == control

    def test_the_verifier_actually_rejects_a_mismatch(self) -> None:
        """The counterfactual. A guard that cannot fail is worth nothing, and
        this one caught two real defects while it was being written."""
        import dataclasses

        from prama.pql.ast import Threshold

        control = _build("not_null")
        # BELOW n% renders without a comparator and re-reads as "<=", so a "<"
        # renders identically and compares unequal.
        broken = dataclasses.replace(
            control,  # type: ignore[type-var]
            threshold=Threshold(unit="rate", value=0.005, comparator="<"),
        )
        with pytest.raises(ValidationError, match="does not read back"):
            render_and_verify(broken)


class TestItRefusesRatherThanGuesses:
    def test_a_control_with_no_reason_is_refused(self) -> None:
        """The one field that cannot be skipped: it is what the alert quotes
        when the control fires."""
        with pytest.raises(ValidationError, match="needs a reason"):
            build(dataset="positions_eod", rule="not_null", column="a", because="  ")

    def test_an_inverted_range_is_refused_with_the_consequence(self) -> None:
        """As written it can never pass, so it fires on every row for ever —
        said in those terms rather than as "invalid input"."""
        with pytest.raises(ValidationError, match="can never pass"):
            _build("between", lower="1", upper="0")

    def test_an_inverted_row_count_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="can never pass"):
            _build("row_count", minimum="500", maximum="100")

    def test_an_empty_value_list_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least one permitted value"):
            _build("in_list", values="  ,  ")

    def test_a_repeated_value_is_refused(self) -> None:
        """Always a mistake, and it makes the rendered control read as though
        somebody meant something by the repetition."""
        with pytest.raises(ValidationError, match="repeat"):
            _build("in_list", values="NEW, NEW")

    def test_a_row_count_rule_with_no_bound_at_all_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="minimum, a maximum, or both"):
            _build("row_count", minimum="", maximum="")

    def test_a_non_numeric_bound_says_which_field(self) -> None:
        with pytest.raises(ValidationError, match="lower bound"):
            _build("between", lower="about ten", upper="1")

    def test_a_tolerance_outside_zero_to_a_hundred_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="not a percentage"):
            _build("not_null", tolerated_percent="150")

    def test_an_unknown_rule_lists_the_real_ones(self) -> None:
        with pytest.raises(ValidationError, match="not_null"):
            build(dataset="d", rule="telepathy", because="why")


class TestWhatTheAnswersProduce:
    def test_unknown_counts_as_a_violation_by_default(self) -> None:
        """SQL's default is the opposite, and it is the most reliable source of
        false confidence in production suites: a rule over a column that is
        entirely null passes, silently, for years."""
        control = _build("not_null")
        assert control.unknown_policy is UnknownPolicy.VIOLATION  # type: ignore[attr-defined]
        assert "TREAT UNKNOWN AS PASS" not in control.render()  # type: ignore[attr-defined]

    def test_choosing_the_sql_behaviour_records_the_choice_in_the_control(self) -> None:
        control = _build("not_null", unknown_is_violation=False)  # type: ignore[arg-type]
        assert "TREAT UNKNOWN AS PASS" in control.render()  # type: ignore[attr-defined]

    def test_no_tolerance_means_no_violations_tolerated(self) -> None:
        assert "BELOW" not in _build("not_null").render()  # type: ignore[attr-defined]

    def test_each_rule_carries_the_dimension_it_belongs_to(self) -> None:
        """So the same rule always scores against the same dimension, and a
        scorecard cannot be reshaped by how somebody happened to fill the form
        in."""
        assert "DIMENSION completeness" in _build("not_null").render()  # type: ignore[attr-defined]
        assert "DIMENSION uniqueness" in _build("unique_key").render()  # type: ignore[attr-defined]
        assert "DIMENSION timeliness" in _build("fresh").render()  # type: ignore[attr-defined]
        assert "DIMENSION integrity" in _build("references").render()  # type: ignore[attr-defined]

    def test_severity_is_carried_through(self) -> None:
        control = _build("not_null", severity="critical")
        assert control.severity is Severity.CRITICAL  # type: ignore[attr-defined]

    def test_a_quoted_reason_is_escaped(self) -> None:
        """An apostrophe in a business reason is ordinary — "the front office's
        cut-off" — and it must not break the control it is embedded in."""
        control = build(
            dataset="positions_eod",
            rule="not_null",
            column="a",
            because="the front office's cut-off",
        )
        assert parse_control(render_and_verify(control)) == control

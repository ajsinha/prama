"""Declaration defaults from a profile — and the line they must not cross.

The whole product turns on the difference between what was observed and what
the business declared. A suggestion layer is where that line is easiest to lose,
because losing it looks like being helpful: a pre-filled form somebody clicks
through has produced a declaration nobody made, and every control derived from
it inherits an authority it never earned.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime

from prama.connect.spi import SamplePlan, SamplingStrategy
from prama.derive.suggestions import defaults_from
from prama.profile.profiler import from_rows

WHEN = datetime(2026, 9, 9, tzinfo=UTC)


def _defaults(rows, *, strategy=SamplingStrategy.FULL):
    profile = from_rows(
        ("positions",),
        rows,
        plan=SamplePlan(strategy=strategy, rows=None if strategy is SamplingStrategy.FULL else 100),
        computed_at=WHEN,
    )
    return defaults_from(profile)


class TestTheGrain:
    def test_a_single_unique_column_is_offered_with_its_evidence(self) -> None:
        rows = [{"trade_id": f"T{n:05d}", "book": "EQ"} for n in range(200)]
        grain = _defaults(rows).of("grain")
        assert grain is not None
        assert grain.value == "trade_id"
        assert "distinct in every row and never null" in grain.because
        assert grain.prefill

    def test_several_candidates_are_listed_and_none_is_chosen(self) -> None:
        """This profile tests each column alone. "These two together are
        unique" is a claim it has not made, and inventing it would be the one
        suggestion here nobody could check."""
        rows = [{"trade_id": f"T{n}", "ref": f"R{n}"} for n in range(200)]
        grain = _defaults(rows).of("grain")
        assert grain is not None
        assert grain.value == ""
        assert "has not tested whether any combination does" in grain.because
        assert not grain.prefill

    def test_a_nullable_column_is_never_a_key_candidate(self) -> None:
        rows = [{"trade_id": f"T{n}" if n else None} for n in range(200)]
        assert _defaults(rows).of("grain") is None

    def test_nothing_is_offered_when_nothing_is_unique(self) -> None:
        rows = [{"book": "EQ", "desk": "LDN"} for _ in range(200)]
        assert _defaults(rows).of("grain") is None


class TestAHeadSamplePrefillsNothing:
    def test_a_key_candidate_from_the_first_rows_is_offered_not_selected(self) -> None:
        """The first thousand rows of a table are the oldest thousand. They
        show shape and no rate at all, so accepting one has to be a deliberate
        act rather than an unchanged form."""
        rows = [{"trade_id": f"T{n:05d}"} for n in range(200)]
        defaults = _defaults(rows, strategy=SamplingStrategy.HEAD)
        grain = defaults.of("grain")
        assert grain is not None
        assert grain.value == "trade_id"
        assert not grain.prefill
        assert not defaults.anything_prefilled

    def test_the_same_data_read_fully_does_prefill(self) -> None:
        """The counterfactual to the test above: the difference is how the rows
        were obtained, not what they contain."""
        rows = [{"trade_id": f"T{n:05d}"} for n in range(200)]
        assert _defaults(rows).anything_prefilled

    def test_it_says_which_it_was(self) -> None:
        rows = [{"trade_id": f"T{n}"} for n in range(200)]
        assert "first 200 rows only" in _defaults(rows, strategy=SamplingStrategy.HEAD).confidence
        assert "measured over all 200 rows" in _defaults(rows).confidence


class TestWarningsAreNotDefaults:
    def test_an_empty_column_is_reported_with_its_consequence(self) -> None:
        rows = [{"trade_id": f"T{n}", "settled_at": None} for n in range(100)]
        [warning] = [w for w in _defaults(rows).warnings if w.column == "settled_at"]
        assert "null in every row read" in warning.message
        assert "stopped populating" in warning.consequence

    def test_a_dominant_value_is_reported_as_a_probable_unfilled_default(self) -> None:
        """A completeness control here passes every day while the column
        carries nothing, which is the failure the warning exists to prevent."""
        rows = [{"status": "NEW" if n < 95 else f"S{n}"} for n in range(100)]
        [warning] = [w for w in _defaults(rows).warnings if w.column == "status"]
        assert "95% of rows read" in warning.message
        assert "unfilled default" in warning.consequence

    def test_a_sparse_column_is_described_by_its_null_rate(self) -> None:
        rows = [{"tax_id": None if n < 70 else f"X{n}"} for n in range(100)]
        [warning] = [w for w in _defaults(rows).warnings if w.column == "tax_id"]
        assert "null in 70% of rows read" in warning.message

    def test_a_sparse_column_is_not_called_constant(self) -> None:
        """The bug this catches: the distinct count ignores nulls, so a column
        that is 70% null with one value in the rest satisfies "one distinct
        value" — and "holds one value in every row" is then a false sentence
        about it."""
        rows = [{"tax_id": None if n < 70 else "SAME"} for n in range(100)]
        [warning] = [w for w in _defaults(rows).warnings if w.column == "tax_id"]
        assert "null in 70%" in warning.message
        assert "every row" not in warning.message

    def test_a_genuinely_constant_column_is_called_constant(self) -> None:
        rows = [{"region": "EMEA"} for _ in range(100)]
        [warning] = [w for w in _defaults(rows).warnings if w.column == "region"]
        assert "one distinct value" in warning.message
        assert "Nothing can vary" in warning.consequence

    def test_at_most_one_warning_per_column(self) -> None:
        """Two sentences about one column invite the reader to work out which
        applies, and they will pick the reassuring one."""
        rows = [{"a": None, "b": "X", "c": None if n < 80 else "Y"} for n in range(100)]
        columns = [w.column for w in _defaults(rows).warnings]
        assert len(columns) == len(set(columns))

    def test_a_clean_column_produces_no_warning(self) -> None:
        rows = [{"notional": float(n) + 1} for n in range(100)]
        assert not _defaults(rows).warnings


class TestItSaysWhatItDidNotFind:
    def test_an_empty_result_is_a_statement_about_the_profile(self) -> None:
        """Not about the dataset. A panel that silently shows nothing reads as
        "there is nothing to say", which is the one thing it cannot know."""
        # Unremarkable: repeats, so no grain; three distinct values, so neither
        # constant nor dominant; no nulls, so not sparse.
        rows = [{"book": f"B{n % 3}"} for n in range(100)]
        described = _defaults(rows).describe()
        assert "suggested nothing" in described
        assert "a statement about the profile, not about the dataset" in described

    def test_every_suggestion_carries_the_profile_confidence(self) -> None:
        """A default whose basis is invisible is one nobody can disagree with,
        and one nobody can disagree with is not confirmed when it is accepted."""
        rows = [{"trade_id": f"T{n}"} for n in range(200)]
        defaults = _defaults(rows)
        assert all(s.confidence == defaults.confidence for s in defaults.suggestions)
        assert all(s.because for s in defaults.suggestions)

"""Baselines, and the absences the output has to admit to.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.bench import baselines, corpus
from prama.bench.corpus import Family


@pytest.fixture(scope="module")
def built():
    return corpus.build(seed=42)


@pytest.fixture(scope="module")
def comparison(built):
    return baselines.compare(built)


class TestTheBoundsAreTheAxes:
    def test_detecting_nothing_has_no_precision_rather_than_zero(self, built) -> None:
        """ "How many of your alerts were right" has no answer when there were
        none. Printing 0.00 would say it was wrong every time it spoke."""
        result = baselines.baseline("detect-nothing").run(built)
        assert result.precision is None
        assert result.recall == 0.0

    def test_alerting_on_everything_reaches_perfect_recall(self, built) -> None:
        """The reason a recall figure cannot be read on its own: this scores
        1.0 and is useless."""
        result = baselines.baseline("alert-on-everything").run(built)
        assert result.recall == 1.0
        assert result.precision is not None and result.precision < 0.2
        assert result.false_alarms > 100

    def test_the_bounds_are_labelled_as_bounds(self) -> None:
        """They are axes, not contenders, and a table that did not say so would
        read as a competitive result."""
        kinds = {b.name: b.kind for b in baselines.BASELINES}
        assert kinds["detect-nothing"] == "bound"
        assert kinds["alert-on-everything"] == "bound"


class TestTheAblationsAnswerWhichClaimDoesTheWork:
    def test_every_ablation_beats_detecting_nothing(self, comparison) -> None:
        ablations = [(b, s) for b, s in comparison.results if b.kind == "ablation"]
        assert ablations
        for _, result in ablations:
            assert result.recall > 0

    def test_no_ablation_comes_near_perfect_recall(self, comparison) -> None:
        """If one did, the rest of the system would have nothing to justify."""
        for entry, result in comparison.results:
            if entry.kind == "ablation":
                assert result.recall < 0.5

    def test_pattern_and_statistics_ablations_are_blind_to_the_semantic_family(
        self, comparison
    ) -> None:
        """The discriminating claim, stated as a measurement rather than an
        assertion: defects that pass every format and range check are not found
        by format or range checking."""
        assert comparison.corpus.of_family(Family.SEMANTIC)  # it is in the corpus at all
        semantic_recall = {}
        for entry, result in comparison.results:
            family = next((f for f in result.families if f.family == Family.SEMANTIC.value), None)
            semantic_recall[entry.name] = family.found if family else 0
        assert semantic_recall["patterns-only"] == 0
        assert semantic_recall["schema-only"] == 0

    def test_blind_families_are_reported(self, comparison) -> None:
        """A detector's blind spots are the argument for whatever covers them,
        and they do not appear in an aggregate F1 at all."""
        blind = comparison.blind_families
        assert set(blind["detect-nothing"]) == {f.value for f in Family}
        assert blind["alert-on-everything"] == ()
        assert "semantic" in blind["patterns-only"]

    def test_schema_only_sees_a_column_dropped_from_some_rows(self, built) -> None:
        """A column dropped from some rows is still in the union of keys, so
        comparing key sets alone reports nothing."""
        alerts = baselines.baseline("schema-only").detect(built)
        assert any("missing from some rows" in a.detail for a in alerts)


class TestWhatWasNotRun:
    def test_the_unrun_baselines_are_named(self) -> None:
        """A five-row table reads as five contenders, and nothing in it says
        fifteen others were never tried."""
        assert len(baselines.NOT_RUN) >= 10
        assert "Great Expectations" in baselines.NOT_RUN
        assert "Soda Core" in baselines.NOT_RUN

    def test_each_says_why_it_was_not_run(self) -> None:
        assert all(reason for reason in baselines.NOT_RUN.values())

    def test_the_comparison_carries_them(self, comparison) -> None:
        """So that no consumer of the JSON can present these numbers as a
        competitive comparison without the absence travelling with them."""
        assert comparison.to_dict()["not_run"] == baselines.NOT_RUN

    def test_no_unrun_baseline_is_also_a_shipped_one(self) -> None:
        assert not {b.name for b in baselines.BASELINES} & set(baselines.NOT_RUN)


class TestLookup:
    def test_an_unknown_baseline_lists_the_known_ones(self) -> None:
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError) as caught:
            baselines.baseline("nope")
        assert "detect-nothing" in caught.value.remedy

    def test_every_baseline_describes_what_it_stands_for(self) -> None:
        assert all(len(b.describes) > 40 for b in baselines.BASELINES)

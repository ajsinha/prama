"""The labelled defect corpus.

A benchmark is only as honest as the thing it plants. Everything here is about
one question: does the label set say what was actually done to the data, or
what the generator meant to do?

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random

import pytest

from prama.bench import corpus
from prama.bench.corpus import CLASSES, Difficulty, Family


class TestReproducibility:
    def test_the_same_seed_gives_the_same_corpus(self) -> None:
        """Otherwise a regression cannot be told apart from a reroll."""
        first = corpus.build(seed=7)
        second = corpus.build(seed=7)
        assert first.rows == second.rows
        assert first.defects == second.defects

    def test_a_different_seed_gives_a_different_corpus(self) -> None:
        assert corpus.build(seed=7).rows != corpus.build(seed=8).rows

    def test_the_seed_has_no_default(self) -> None:
        """A default seed is a seed nobody records, and an unrecorded seed
        makes every number an anecdote."""
        with pytest.raises(TypeError):
            corpus.build()  # type: ignore[call-arg]

    def test_the_seed_is_carried_in_the_result(self) -> None:
        assert corpus.build(seed=99).to_dict()["seed"] == 99


class TestTheLabelsFollowWhatHappened:
    def test_a_no_op_injection_plants_no_label(self) -> None:
        """A sign flip landing on an already-negative amount changes nothing.
        Labelling it would credit a detector for finding a defect that is not
        there."""
        row = {"amount": -50.0}
        assert corpus._sign_flip(row, random.Random(1)) is False
        assert row["amount"] == -50.0

    def test_every_labelled_scenario_actually_changed_rows(self) -> None:
        built = corpus.build(seed=11)
        for scenario in built.scenarios:
            if scenario.defect is not None:
                assert scenario.damaged_rows, scenario.defect_class

    def test_a_scenario_that_changed_nothing_carries_no_defect(self) -> None:
        built = corpus.build(seed=11)
        for scenario in built.scenarios:
            if not scenario.damaged_rows:
                assert scenario.defect is None

    def test_the_damaged_rows_differ_from_the_clean_ones(self) -> None:
        """The strongest form: for every planted defect, at least one row is
        genuinely not what it was."""
        built = corpus.build(seed=11)
        for scenario in built.scenarios:
            if scenario.defect is None:
                continue
            changed = [
                index
                for index in scenario.damaged_rows
                if scenario.rows[index] != scenario.clean[index]
            ]
            assert changed, scenario.defect_class

    def test_a_class_that_plants_nothing_is_reported_not_hidden(self) -> None:
        """Silence here becomes recall a detector never had to earn."""
        barren_class = corpus.DefectClass(
            "impossible",
            Family.CONTENT,
            Difficulty.OBVIOUS,
            "amount",
            lambda _row, _rng: False,
            "never plants anything",
        )
        built = corpus.build(seed=3, classes=[barren_class])
        assert built.planted == 0
        assert built.barren[0][0] == "impossible"
        assert "nothing is labelled" in built.barren[0][1]

    def test_the_note_records_how_many_rows_carry_it(self) -> None:
        built = corpus.build(seed=5)
        assert all("row(s)" in d.note for d in built.defects)


class TestOneWindowPerClass:
    def test_each_class_gets_its_own_window(self) -> None:
        """docs/corpus/15 §3.1 scores dataset, column *and* window. Six classes that
        all damage `amount` in one window share a locus, so a single alert on
        `amount` would be credited with finding all six."""
        built = corpus.build(seed=13)
        windows = [s.window for s in built.scenarios]
        assert len(set(windows)) == len(windows)

    def test_every_planted_defect_has_a_distinct_locus(self) -> None:
        built = corpus.build(seed=13)
        loci = [d.locus for d in built.defects]
        assert len(set(loci)) == len(loci)

    def test_rows_carry_the_window_they_belong_to(self) -> None:
        built = corpus.build(seed=13)
        for scenario in built.scenarios:
            assert all(row["window"] == scenario.window for row in scenario.clean)


class TestTheTaxonomy:
    def test_every_family_is_represented(self) -> None:
        families = {c.family for c in CLASSES}
        assert families == set(Family)

    def test_every_difficulty_tier_is_represented(self) -> None:
        tiers = {c.difficulty for c in CLASSES}
        assert tiers == set(Difficulty)

    def test_the_semantic_family_is_the_hard_one(self) -> None:
        """It is the discriminator: those defects pass every format and range
        check, so none of them can be obvious."""
        semantic = [c for c in CLASSES if c.family is Family.SEMANTIC]
        assert semantic
        assert all(c.difficulty is not Difficulty.OBVIOUS for c in semantic)

    def test_class_names_are_unique(self) -> None:
        names = [c.name for c in CLASSES]
        assert len(set(names)) == len(names)

    def test_every_class_describes_itself(self) -> None:
        assert all(c.description for c in CLASSES)

    def test_classes_can_be_selected_by_family(self) -> None:
        assert all(c.family is Family.TEMPORAL for c in corpus.classes_of(Family.TEMPORAL))
        assert corpus.classes_of() == CLASSES


class TestDateRelativeInjection:
    def test_late_arrival_is_relative_to_the_rows_own_window(self) -> None:
        """A fixed date is a no-op for whichever scenario happens to fall on
        it, and a class that plants nothing in one run and something in the
        next is not a benchmark."""
        built = corpus.build(seed=17)
        scenario = next(s for s in built.scenarios if s.defect_class == "late-arrival")
        assert scenario.defect is not None
        for index in scenario.damaged_rows:
            assert scenario.rows[index]["value_date"] != scenario.window

    def test_out_of_order_puts_booking_after_settlement(self) -> None:
        built = corpus.build(seed=17)
        scenario = next(s for s in built.scenarios if s.defect_class == "out-of-order")
        assert scenario.defect is not None
        for index in scenario.damaged_rows:
            row = scenario.rows[index]
            assert row["booking_date"] > row["value_date"]


class TestRefusals:
    """`ValueError` — Python's meaning for "right type, wrong value".

    These briefly asserted `ValidationError`, when `Q-68`'s fix for a stack
    trace in `prama bench run` was made by raising the taxonomy from the
    library. That broke every caller written as `except ValueError`, which
    `BCH-015`/`BCH-016` caught and `Q-77` resolved: the library keeps
    `ValueError` and `prama.cli.bench` translates at its boundary. The remedy
    lives there too, because that layer knows the flags are `--rate` and
    `--rows` and this one does not.

    `qa/regression-suite/platform/test_bench_refusals_keep_both_contracts.py`
    holds both halves together, so neither can be restored by breaking the
    other.
    """

    @pytest.mark.parametrize("rate", [0.0, -0.1, 1.5])
    def test_an_impossible_rate_is_refused(self, rate: float) -> None:
        with pytest.raises(ValueError, match="share of rows"):
            corpus.build(seed=1, rate=rate)

    def test_a_corpus_needs_rows(self) -> None:
        with pytest.raises(ValueError, match="needs rows"):
            corpus.build(seed=1, rows=0)

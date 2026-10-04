"""Benchmark scoring.

docs/corpus/15 §3.1 sets the rule most data quality benchmarks quietly break: a
detection counts only if it names the right dataset *and* column *and* window. A
tool that alerts on every table every day has perfect recall under a looser
match and is useless, so the looseness is what these tests are mostly about.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.bench import Alert, Defect, score

WHEN = "2026-09-09"


def defect(column: str = "notional", family: str = "completeness", **kw) -> Defect:
    return Defect(
        dataset=kw.pop("dataset", "positions"),
        column=column,
        window=kw.pop("window", WHEN),
        family=family,
        **kw,
    )


def alert(column: str = "notional", **kw) -> Alert:
    return Alert(
        dataset=kw.pop("dataset", "positions"),
        column=column,
        window=kw.pop("window", WHEN),
    )


class TestTheMatchIsExact:
    def test_the_right_locus_credits_the_defect(self) -> None:
        result = score([defect()], [alert()])
        assert result.found == 1
        assert result.recall == 1.0

    def test_the_wrong_column_does_not(self) -> None:
        """A generic "something is wrong with this table" scores zero."""
        result = score([defect()], [alert(column="quantity")])
        assert result.found == 0

    def test_the_wrong_window_does_not(self) -> None:
        """A detection in the wrong window is a detection of something else
        that happens to look similar."""
        result = score([defect()], [alert(window="2026-09-08")])
        assert result.found == 0

    def test_the_wrong_dataset_does_not(self) -> None:
        result = score([defect()], [alert(dataset="trades")])
        assert result.found == 0

    def test_alerting_on_everything_does_not_score_well(self) -> None:
        """The reason the rule exists. Two planted defects, forty alerts, and
        the score reflects the noise rather than the coverage."""
        planted = [defect(column="a"), defect(column="b")]
        noisy = [alert(column=f"col{n}") for n in range(40)] + [
            alert(column="a"),
            alert(column="b"),
        ]
        result = score(planted, noisy)
        assert result.recall == 1.0
        assert result.precision is not None
        assert result.precision < 0.1


class TestNearMissesAreReportedNotCredited:
    def test_a_right_table_wrong_column_alert_is_a_near_miss(self) -> None:
        result = score([defect()], [alert(column="quantity")])
        assert result.found == 0
        assert len(result.near_misses) == 1

    def test_a_right_table_wrong_window_alert_is_a_near_miss(self) -> None:
        result = score([defect()], [alert(window="2026-09-01")])
        assert len(result.near_misses) == 1

    def test_they_are_named_in_the_summary(self) -> None:
        """So the score is arguable rather than merely low."""
        described = score([defect()], [alert(column="quantity")]).describe()
        assert "near miss" in described
        assert "credited as misses" in described

    def test_an_alert_on_an_unrelated_table_is_not_a_near_miss(self) -> None:
        result = score([defect()], [alert(dataset="unrelated", column="x")])
        assert result.near_misses == ()
        assert result.false_alarms == 1


class TestRepeatedAlertsDoNotImproveRecall:
    def test_one_alert_credits_one_defect(self) -> None:
        """Otherwise a tool improves its recall by shouting."""
        result = score([defect()], [alert(), alert(), alert()])
        assert result.found == 1
        assert result.false_alarms == 2

    def test_two_defects_at_one_locus_need_two_alerts(self) -> None:
        planted = [defect(family="completeness"), defect(family="semantic")]
        assert score(planted, [alert()]).found == 1
        assert score(planted, [alert(), alert()]).found == 2


class TestPerFamilyBeforeAggregate:
    def test_the_weakest_family_leads_the_summary(self) -> None:
        """An aggregate F1 lets a tool average its way past the thing it is bad
        at, and the thing it is bad at is what a buyer hits in week two."""
        planted = [
            defect(column="a", family="completeness"),
            defect(column="b", family="semantic"),
            defect(column="c", family="semantic"),
        ]
        described = score(planted, [alert(column="a")]).describe()
        assert described.startswith("weakest family semantic")

    def test_a_family_is_scored_on_its_own_defects(self) -> None:
        planted = [
            defect(column="a", family="completeness"),
            defect(column="b", family="semantic"),
        ]
        result = score(planted, [alert(column="a")])
        by_name = {family.family: family for family in result.families}
        assert by_name["completeness"].recall == 1.0
        assert by_name["semantic"].recall == 0.0

    def test_a_family_with_nothing_planted_scores_nothing_not_one(self) -> None:
        """A benchmark reporting 1.0 for a family it never tested rewards not
        being tested."""
        from prama.bench.scoring import FamilyScore

        empty = FamilyScore(family="semantic", planted=0, found=0, false_alarms=3)
        assert empty.recall is None
        assert empty.f1 is None
        assert "nothing was planted" in empty.describe()

    def test_family_precision_is_not_computed(self) -> None:
        """A false alarm corresponds to no planted defect, so it belongs to no
        family. Attributing it to one is a guess; spreading it flatters every
        family."""
        result = score([defect()], [alert(dataset="other", column="x")])
        assert all(family.precision is None for family in result.families)
        assert "aggregate figure" in result.families[0].describe()

    def test_every_family_carries_the_same_run_total_of_false_alarms(self) -> None:
        planted = [
            defect(column="a", family="completeness"),
            defect(column="b", family="semantic"),
        ]
        result = score(planted, [alert(dataset="other", column="x")])
        assert {family.false_alarms for family in result.families} == {1}
        assert result.false_alarms == 1


class TestPrecisionAndRecallEdges:
    def test_no_alerts_gives_no_precision_rather_than_one(self) -> None:
        """Precision over zero predictions is undefined, and reporting 1.0
        rewards a tool for saying nothing."""
        result = score([defect()], [])
        assert result.precision is None
        assert result.recall == 0.0

    def test_nothing_planted_scores_nothing(self) -> None:
        result = score([], [alert()])
        assert result.recall is None
        assert "nothing was planted" in result.describe()

    def test_f1_needs_both_halves(self) -> None:
        assert score([defect()], []).f1 is None
        assert score([], [alert()]).f1 is None
        assert score([defect()], [alert()]).f1 == 1.0


class TestDifficulty:
    def test_it_is_reported_separately(self) -> None:
        """A tool that only finds the easy ones has a different problem from one
        that finds few of everything."""
        planted = [
            defect(column="a", difficulty="easy"),
            defect(column="b", difficulty="hard"),
            defect(column="c", difficulty="hard"),
        ]
        payload = score(planted, [alert(column="a")]).to_dict()
        assert payload["by_difficulty"]["easy"] == {"found": 1, "planted": 1}
        assert payload["by_difficulty"]["hard"] == {"found": 0, "planted": 2}


class TestTheDictionaryForm:
    def test_it_carries_families_near_misses_and_the_message(self) -> None:
        payload = score([defect()], [alert(column="quantity")]).to_dict()
        assert payload["planted"] == 1
        assert payload["found"] == 0
        assert payload["families"]
        assert payload["near_misses"]
        assert payload["message"]

"""One control, several engines, the same answer — or a refusal.

The claim Wave 4 makes, checked rather than asserted.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import pytest

from prama.backend.conformance import ConformanceRun, EngineOutcome
from prama.backend.corpus import CASES, Case
from prama.backend.execute import ControlResult
from prama.ir.model import Verdict


def case(name: str) -> Case:
    return next(c for c in CASES if c.name == name)


class TestTheEnginesAgree:
    def test_every_case_gives_the_same_answer_everywhere(
        self, engines: dict, conformance: ConformanceRun
    ) -> None:
        # The whole wave in one assertion. Comparing verdicts and metrics, not
        # SQL — the SQL differing is the point — and not sample row order,
        # which is not part of a control's meaning.
        report = conformance.summarise(engines)
        assert report["conforming"], "\n".join(report["disagreements"])
        assert report["cases"] == len(CASES)

    def test_at_least_two_genuinely_different_engines_took_part(self, engines: dict) -> None:
        # A suite that silently ran one engine twice would pass for ever and
        # prove nothing.
        assert len(engines) >= 2

    @pytest.mark.parametrize("name", [c.name for c in CASES])
    def test_each_case_individually(
        self, name: str, engines: dict, conformance: ConformanceRun
    ) -> None:
        # Reported per case so a failure names the construct that broke rather
        # than "conformance failed".
        run = conformance
        assert not run.compare(engines, cases=(case(name),))


class TestRefusalIsConformance:
    def test_sqlite_refuses_what_it_genuinely_cannot_do(
        self, sqlite_runner: Any, conformance: ConformanceRun
    ) -> None:
        """The refusal path is the promise, and it needs a live exemplar.

        It used to be the regular-expression case. SQLite now has regex,
        because it reserves the REGEXP operator for a function the host
        registers and Prama's executor registers one — so the capability is
        real rather than approximated, and substituting LIKE was never the
        alternative.

        What SQLite still cannot do is approximate distinct counts and
        sampling, and those are what this asserts now. A test asserting a
        refusal that no longer happens would pass by accident on the day the
        engine gained the feature and stop testing anything.
        """
        from prama.backend.dialect import APPROX_DISTINCT, SAMPLING, dialect

        sqlite = dialect("sqlite")
        assert APPROX_DISTINCT not in sqlite.capabilities
        assert SAMPLING not in sqlite.capabilities

    def test_sqlite_does_regex_through_a_registered_function(
        self, sqlite_runner: Any, conformance: ConformanceRun
    ) -> None:
        """And gets the same answer as every other engine.

        The whole point of claiming a capability rather than approximating one:
        if this disagreed with DuckDB the conformance run would say so, which
        is what ``test_every_case_gives_the_same_answer_everywhere`` is for.
        """
        outcome = conformance.run_case(case("regex"), "sqlite", sqlite_runner)
        assert outcome.status == "ran"
        assert outcome.result is not None
        assert outcome.result.verdict is Verdict.FAIL

    def test_an_engine_that_can_do_it_does(
        self, duckdb_runner: Any, conformance: ConformanceRun
    ) -> None:
        outcome = conformance.run_case(case("regex"), "duckdb", duckdb_runner)
        assert outcome.status == "ran"
        assert outcome.result is not None
        assert outcome.result.verdict is Verdict.FAIL


class TestTheCorpusDiscriminates:
    """A corpus that cannot tell right from wrong proves nothing."""

    def test_the_unknown_policy_changes_the_count(
        self, duckdb_runner: Any, conformance: ConformanceRun
    ) -> None:
        # The pair exists to pin the difference. If both gave the same number
        # the corpus would be passing without exercising the inversion of SQL's
        # default, which is one of the language's central decisions.
        run = conformance
        strict = run.run_case(case("unknown_is_violation"), "duckdb", duckdb_runner)
        lenient = run.run_case(case("unknown_may_pass"), "duckdb", duckdb_runner)
        assert strict.result is not None and lenient.result is not None
        assert strict.result.violating_rows == 3
        assert lenient.result.violating_rows == 2

    def test_a_duplicate_key_counts_once_not_twice(
        self, duckdb_runner: Any, conformance: ConformanceRun
    ) -> None:
        # Two rows share a key; one of them is the duplicate. Reporting 2 would
        # double every duplicate finding in the platform.
        outcome = conformance.run_case(case("unique_key"), "duckdb", duckdb_runner)
        assert outcome.result is not None
        assert outcome.result.metrics["violating_rows"] == 1
        assert outcome.result.metrics["distinct_keys"] == 7

    def test_a_segmented_control_fails_on_one_bad_segment(
        self, duckdb_runner: Any, conformance: ConformanceRun
    ) -> None:
        outcome = conformance.run_case(case("segmented"), "duckdb", duckdb_runner)
        assert outcome.result is not None
        assert outcome.result.verdict is Verdict.FAIL
        assert [s.key for s in outcome.result.failing_segments] == ["APAC"]

    def test_a_rate_is_judged_against_the_rows_actually_scanned(
        self, duckdb_runner: Any, conformance: ConformanceRun
    ) -> None:
        # 1 of 8 is 12.5%: under 20% and over 10%. Two cases either side of the
        # line, so a rate computed from the wrong denominator cannot pass both.
        run = conformance
        under = run.run_case(case("rate_threshold"), "duckdb", duckdb_runner)
        over = run.run_case(case("rate_threshold_fails"), "duckdb", duckdb_runner)
        assert under.result is not None and over.result is not None
        assert under.result.verdict is Verdict.PASS
        assert over.result.verdict is Verdict.FAIL

    def test_a_filter_moves_the_denominator_too(
        self, duckdb_runner: Any, conformance: ConformanceRun
    ) -> None:
        # A rate over a filtered scope must divide by the filtered count. Using
        # the unfiltered one understates every rate on every filtered control.
        outcome = conformance.run_case(case("not_null_filtered"), "duckdb", duckdb_runner)
        assert outcome.result is not None
        assert outcome.result.scanned_rows == 6

    def test_the_corpus_contains_both_passing_and_failing_cases(
        self, engines: dict, conformance: ConformanceRun
    ) -> None:
        # A corpus where everything failed would pass a backend that returned a
        # constant.
        report = conformance.summarise(engines)
        verdicts = {row["duckdb"] for row in report["rows"]}
        assert "pass" in verdicts and "fail" in verdicts


class TestAScreenThatScreensNothingIsCaught:
    """Finding T4. `_compare_two_stage` required only that an engine find no
    *more* violations than the exact check, which is true and is not enough.

    "Fewer" includes **none**. A screen that rejects nothing produced the same
    green report as one that works, so the release gate for the product's
    central claim — the two-stage verdict, executed on a real engine — could not
    tell a working predicate from a deleted one. The reviewer proved it by
    neutering the `FILTER (WHERE …)` of every two-stage plan: DuckDB reported
    PASS on data the reference reports three violations for, and all 119
    backend tests stayed green.

    The case now declares what the screen alone must find and it is required
    exactly. These exercise the comparison directly, with synthetic outcomes,
    because building a genuinely half-broken engine to test it is harder than
    the thing being tested and would prove less.
    """

    CASE_NAME = "semantic_type_two_stage"

    def outcome(self, engine: str, violations: float) -> EngineOutcome:
        return EngineOutcome(
            engine=engine,
            case=self.CASE_NAME,
            status="ran",
            result=ControlResult(
                plan_id=self.CASE_NAME,
                verdict=Verdict.FAIL if violations else Verdict.PASS,
                metrics={"scanned_rows": 8.0, "violating_rows": violations},
                engine=engine,
            ),
        )

    def compare(self, engine_violations: float) -> list[Any]:
        subject = case(self.CASE_NAME)
        assert subject.screen_violations is not None, "the corpus must declare the screen count"
        return ConformanceRun._compare_two_stage(
            subject,
            {
                "reference": self.outcome("reference", 3.0),
                "duckdb": self.outcome("duckdb", engine_violations),
            },
        )

    def test_a_correct_screen_agrees(self) -> None:
        """The positive control. Without it this class would pass by rejecting
        everything, which proves nothing about the comparison."""
        assert self.compare(2.0) == []

    def test_a_screen_that_finds_nothing_is_a_disagreement(self) -> None:
        """The defect, exactly: a neutered predicate used to be excused."""
        found = self.compare(0.0)
        assert found, "a screen finding zero violations was excused"
        assert "expected 2" in found[0].render()

    def test_a_screen_that_finds_too_few_is_a_disagreement(self) -> None:
        assert self.compare(1.0)

    def test_a_screen_that_over_rejects_is_still_a_disagreement(self) -> None:
        """The direction the original check did catch, kept."""
        assert self.compare(4.0)

    def test_every_two_stage_case_declares_its_screen_count(self) -> None:
        """Without the declaration the comparison has no floor, so a new
        two-stage case added without one would silently reopen the hole. The
        suite reports that as a disagreement rather than passing."""
        run = ConformanceRun()
        for subject in CASES:
            if run.plan_for(subject).is_two_stage:
                assert subject.screen_violations is not None, (
                    f"{subject.name} is two-stage and declares no screen_violations"
                )

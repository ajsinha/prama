"""One control, several engines, the same answer — or a refusal.

The claim Wave 4 makes, checked rather than asserted.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import pytest

from prama.backend.conformance import ConformanceRun
from prama.backend.corpus import CASES, Case
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
    def test_sqlite_refuses_a_pattern_rather_than_approximating_it(
        self, sqlite_runner: Any, conformance: ConformanceRun
    ) -> None:
        # Substituting LIKE would make the same control mean two different
        # things on two engines, and nothing would ever notice.
        outcome = conformance.run_case(case("regex"), "sqlite", sqlite_runner)
        assert outcome.status == "refused"
        assert "regular expression" in outcome.detail or "pushdown.regex" in outcome.detail

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

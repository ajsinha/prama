"""Generated controls, run on every engine, required to agree.

The fixed corpus tests the cases its author imagined. This tests the ones
nobody did — combinations of negation, filtering, segmentation, null handling
and thresholds that no one writes by hand in sufficient variety.

Every failure reports the seed that produced it, so a disagreement is a
one-line reproduction rather than a flaky "conformance failed" that nobody can
act on.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import collections
import os

import pytest

from prama.backend.conformance import ConformanceRun
from prama.backend.corpus import Case
from prama.backend.generate import ControlGenerator
from prama.ir.lower import Lowerer
from prama.pql.parser import parse_control

#: Kept small enough that the ordinary suite stays fast. CI and anybody chasing
#: a portability bug raise it: PRAMA_FUZZ_CONTROLS=5000 pytest tests/backend
COUNT = int(os.environ.get("PRAMA_FUZZ_CONTROLS", "250"))


@pytest.fixture(scope="module")
def generated() -> list:
    return ControlGenerator().many(COUNT)


class TestEveryGeneratedControlIsValid:
    """A generator that emitted nonsense would make its findings noise."""

    def test_all_of_them_parse(self, generated: list) -> None:
        for control in generated:
            assert parse_control(control.pql) is not None, control

    def test_all_of_them_lower_to_a_plan(self, generated: list) -> None:
        for control in generated:
            plan = Lowerer().control(parse_control(control.pql))
            assert plan.plan_id.startswith("ir:sha256:"), control

    def test_they_are_reproducible_from_their_seed(self, generated: list) -> None:
        # A conformance failure has to be reproducible. A suite that says
        # "some generated control disagreed" and cannot say which is worse
        # than no suite.
        again = ControlGenerator().many(COUNT)
        assert [c.pql for c in again] == [c.pql for c in generated]


class TestTheEnginesAgreeOnAllOfThem:
    def test_no_generated_control_produces_a_disagreement(
        self, generated: list, engines: dict
    ) -> None:
        run = ConformanceRun()
        failures = []
        for control in generated:
            disagreements = run.compare(
                engines, cases=(Case(name=f"gen-{control.seed}", pql=control.pql),)
            )
            if disagreements:
                failures.append(f"{control}\n{disagreements[0].render()}")
        assert not failures, "\n\n".join(failures[:5])

    def test_the_generated_set_exercises_all_three_outcomes(
        self, generated: list, duckdb_runner: object
    ) -> None:
        # A generator whose controls all failed would compare three engines all
        # returning the same constant, and would prove nothing.
        run = ConformanceRun()
        seen: collections.Counter[str] = collections.Counter()
        for control in generated:
            outcome = run.run_case(
                Case(name=f"gen-{control.seed}", pql=control.pql), "duckdb", duckdb_runner
            )
            seen[outcome.result.verdict.value if outcome.result else outcome.status] += 1
        assert seen["pass"] > 0
        assert seen["fail"] > 0
        # Indeterminate arises where a filter matches nothing: an empty scope
        # has demonstrated nothing, and reporting a pass is how a broken feed
        # goes unnoticed.
        assert seen["indeterminate"] > 0

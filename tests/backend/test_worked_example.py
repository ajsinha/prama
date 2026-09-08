"""The specification's worked example, executed.

Section 10 of the rule-language spec shows one screen of business declarations
becoming a production suite. Running it here keeps the document and the
implementation from drifting apart, and is the wave's demo made checkable.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest

from prama.backend import example as worked
from prama.backend.execute import ControlResult
from prama.backend.fuse import Fuser
from prama.backend.reference import Bindings, ReferenceEvaluator
from prama.ir.lower import Lowerer
from prama.ir.model import ControlPlan
from prama.pql.lint import Linter
from prama.pql.parser import parse


@pytest.fixture(scope="module")
def estate() -> Iterator[Any]:
    """Positions and the accounts master, with the planted faults."""
    connection = sqlite3.connect(":memory:")
    connection.execute(worked.create_positions(dialect="sqlite"))
    connection.execute(worked.create_accounts())
    connection.executemany(worked.insert_positions(), [list(r) for r in worked.POSITIONS])
    connection.executemany(worked.insert_accounts(), [list(r) for r in worked.ACCOUNTS])
    connection.commit()

    def run(sql: str) -> list[dict[str, Any]]:
        cursor = connection.execute(sql)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    yield run
    connection.close()


@pytest.fixture(scope="module")
def plans() -> list[ControlPlan]:
    lowerer = Lowerer(codelists={"iso4217": worked.ISO4217})
    return [lowerer.control(c) for c in parse(worked.SUITE).all_controls]


def results(plans: list[ControlPlan], runner: Any) -> dict[str, ControlResult]:
    fuser = Fuser("sqlite")
    found: list[ControlResult] = []
    for group in fuser.group(plans):
        query = fuser.fuse(group, table=group.dataset)
        found.extend(query.unpack(runner(query.sql)))
    return {r.plan_id: r for r in found}


class TestItCompilesAndRuns:
    def test_the_whole_suite_parses(self) -> None:
        assert len(parse(worked.SUITE).all_controls) == len(worked.EXPECTED)

    def test_every_control_lowers_to_a_plan(self, plans: list[ControlPlan]) -> None:
        assert all(p.plan_id.startswith("ir:sha256:") for p in plans)

    def test_it_runs_end_to_end_and_finds_what_was_planted(
        self, plans: list[ControlPlan], estate: Any
    ) -> None:
        # Every planted fault is caught by the control that should catch it,
        # and the healthy controls stay quiet. A demo where everything fails
        # proves as little as one where nothing does.
        found = results(plans, estate)
        verdicts = [found[p.plan_id].verdict.value for p in plans]
        assert verdicts == [e.verdict for e in worked.EXPECTED]

    def test_the_suite_runs_in_fewer_scans_than_it_has_controls(
        self, plans: list[ControlPlan]
    ) -> None:
        cost = Fuser("sqlite").cost(plans, rows={"positions_eod": len(worked.POSITIONS)})
        assert cost.controls == 7
        assert cost.scans == 2  # one unfiltered pass, one for the row count's filter

    def test_the_same_suite_runs_on_the_reference_interpreter(
        self, plans: list[ControlPlan]
    ) -> None:
        # The referential control needs the accounts master, which is exactly
        # the case an interpreter given one dataset cannot answer.
        rows = [dict(zip([n for n, _ in worked.COLUMNS], r, strict=True)) for r in worked.POSITIONS]
        related = {
            "accounts": [{"account_id": a, "legal_entity_id": e} for a, e in worked.ACCOUNTS]
        }
        evaluator = ReferenceEvaluator(Bindings(), related=related)
        verdicts = [evaluator.run(plan, rows).verdict.value for plan in plans]
        assert verdicts == [e.verdict for e in worked.EXPECTED]


class TestWhatEachControlCatches:
    def test_the_duplicate_breaks_the_declared_grain(
        self, plans: list[ControlPlan], estate: Any
    ) -> None:
        found = results(plans, estate)[plans[0].plan_id]
        assert found.metrics["duplicate_rows"] == 1
        assert found.metrics["null_key_rows"] == 0

    def test_the_missing_cde_is_one_row(self, plans: list[ControlPlan], estate: Any) -> None:
        assert results(plans, estate)[plans[1].plan_id].violating_rows == 1

    def test_the_codelist_catches_a_currency_that_is_not_iso_4217(
        self, plans: list[ControlPlan], estate: Any
    ) -> None:
        assert results(plans, estate)[plans[2].plan_id].violating_rows == 1

    def test_the_reference_catches_an_orphan(self, plans: list[ControlPlan], estate: Any) -> None:
        # And not merely a null: A9 has a value, and it is not in the master.
        assert results(plans, estate)[plans[3].plan_id].violating_rows == 1

    def test_the_dependency_counts_accounts_not_rows(
        self, plans: list[ControlPlan], estate: Any
    ) -> None:
        # One account carries two entities. Counting rows would say four, which
        # names a symptom rather than the problem.
        found = results(plans, estate)[plans[4].plan_id]
        assert found.violating_rows == 1
        assert found.metrics["distinct_determinants"] == 4


class TestTheCodelistIsClosedOver:
    def test_a_control_carries_the_values_it_was_approved_with(
        self, plans: list[ControlPlan]
    ) -> None:
        # Resolving at run time would let a codelist edited on Tuesday change
        # what Monday's evidence was asserting, with the plan hash unmoved.
        assert "GBP" in plans[2].to_json()

    def test_changing_the_codelist_changes_the_control(self) -> None:
        narrow = Lowerer(codelists={"iso4217": ("GBP",)})
        wide = Lowerer(codelists={"iso4217": worked.ISO4217})
        control = next(c for c in parse(worked.SUITE).all_controls if "currency" in c.render())
        assert narrow.control(control).plan_id != wide.control(control).plan_id

    def test_an_unregistered_codelist_is_refused(self) -> None:
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError, match="not registered"):
            Lowerer().control(
                next(c for c in parse(worked.SUITE).all_controls if "currency" in c.render())
            )


class TestHonestyAboutTheGap:
    def test_the_unimplemented_parts_are_recorded(self) -> None:
        # A reader of the example is never left to infer the gap from its
        # absence.
        assert len(worked.NOT_YET_IMPLEMENTED) == 3
        assert all(reason for _, reason in worked.NOT_YET_IMPLEMENTED)

    def test_every_control_traces_to_a_declaration(self) -> None:
        for control in parse(worked.SUITE).all_controls:
            assert control.because

    def test_the_suite_is_free_of_the_rot_the_linter_looks_for(self) -> None:
        # Except one: the null notional fires both the completeness control and
        # the range control, and the linter is right to say so. Recorded rather
        # than suppressed, because it is a real property of the example.
        findings = Linter().check_all(list(parse(worked.SUITE).all_controls))
        assert {f.rule for f in findings} == {"subsumed"}

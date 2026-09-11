"""Lowering with everything a control needs to resolve.

``lower`` defaults its validators and code lists to empty, which is right for a
unit test and wrong everywhere else: a control saying ``IN CODELIST 'iso4217'``
lowered without the lists refuses to compile, and the failure surfaces long
after the place that forgot to pass them.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
from datetime import date

import pytest

from prama.core.errors import PramaError
from prama.ir import lower
from prama.ir.resolve import resolved
from prama.pql import parse_control

CODELIST = (
    "CHECK trades.currency IN CODELIST iso4217 SEVERITY major DIMENSION validity BECAUSE 'ISO 4217'"
)
PLAIN = "CHECK trades.notional IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"


class TestItResolvesWhatBareLoweringCannot:
    def test_a_codelist_control_lowers(self) -> None:
        assert resolved(parse_control(CODELIST)).plan_id

    def test_bare_lowering_refuses_the_same_control(self) -> None:
        """The counterfactual. If this ever stopped raising, ``resolved`` would
        be doing nothing and nobody would notice."""
        with pytest.raises(PramaError, match="not registered"):
            lower(parse_control(CODELIST))

    def test_the_values_are_frozen_into_the_plan(self) -> None:
        """The IR wants values, not references: a plan has to mean one fixed
        thing, so a list edited on Tuesday cannot change what Monday's evidence
        meant."""
        from prama.backend import compile_for

        plan = resolved(parse_control(CODELIST))
        sql = compile_for(plan, "postgresql", table="trades").metric_query
        assert "'EUR'" in sql and "'JPY'" in sql


class TestItDoesNotChangeAnythingElse:
    def test_a_control_with_no_codelist_hashes_identically(self) -> None:
        """The bug this test was written for: passing ``as_of=None`` explicitly
        overrode the Lowerer's own default of ``""`` and produced a *different
        plan id* for the same control. Two callers disagreeing about a content
        hash is the precise drift content addressing exists to prevent.
        """
        control = parse_control(PLAIN)
        assert resolved(control).plan_id == lower(control).plan_id

    def test_an_as_of_date_still_reaches_the_plan(self) -> None:
        """And changes it, because it should: a control resolved against last
        year's code list is a different control."""
        control = parse_control(CODELIST)
        assert resolved(control, as_of=date(2022, 1, 1)).plan_id != resolved(control).plan_id


class TestEveryCallSiteUsesIt:
    def test_nothing_lowers_bare_outside_the_resolver(self) -> None:
        """Each caller remembering is how three of six call sites end up
        subtly different — which is what happened before this existed.

        Parsed rather than grepped. A line scan counted SQL's own ``lower()``
        inside a dialect's query text as a Python call, so the first dialect to
        lower-case a column name failed a guard about the IR. A guard that
        cries wolf gets an exclusion list, and an exclusion list is how a real
        violation eventually gets waved through.
        """
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parents[2] / "src" / "prama"
        offenders = []
        for path in src.rglob("*.py"):
            if path.name in ("lower.py", "resolve.py"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                # A bare `lower(...)`, not `x.lower()` and not the word inside
                # a string.
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "lower"
                ):
                    offenders.append(f"{path.relative_to(src)}:{node.lineno}")
        assert offenders == [], (
            "these lower a control without its code lists; use "
            f"prama.ir.resolve.resolved: {offenders}"
        )

    def test_the_guard_still_catches_a_bare_lower(self) -> None:
        """The counterfactual, because narrowing a guard is exactly when it can
        stop catching anything at all."""
        import ast

        offending = ast.parse("plan = lower(control)\n")
        found = [
            node
            for node in ast.walk(offending)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "lower"
        ]
        assert found

    def test_the_guard_ignores_sql_text_and_method_calls(self) -> None:
        innocent = ast.parse('sql = "SELECT lower(data_type) FROM t"\nname = column.lower()\n')
        found = [
            node
            for node in ast.walk(innocent)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "lower"
        ]
        assert not found

"""Nothing is not zero, and an approximation is not exact.

QA round 4: `IR-021`/`BE-055` and `BE-096`/`BE-097`. Three places that
substituted a confident value for one they did not have.

**The empty codelist.** The parser already refuses a hand-written `IN ()` —
*"an empty set fails every row, so it is a mistake rather than a style"*. A
codelist that resolves to nothing is the same control with the values arriving
from elsewhere, and had no equivalent guard.

The triage said this produced SQL no engine parses. That is **half true, and the
untrue half is the dangerous one**: DuckDB rejects `IN ()` outright, and SQLite
*accepts* it, evaluating it as false. So the same control crashes on one engine
and, on the other, reports **every row in the dataset as a violation**. A control
that fails everything reads as a data emergency, and the cause is a list somebody
emptied.

**The two `0.0` defaults in `ReferenceEvaluator._aggregate`.** This is the
interpreter every SQL engine is compared against, so a confident wrong number
here surfaces as a backend defect somewhere else.

`.get(aggregate, 0.0)` had no entry for `APPROX_COUNT_DISTINCT`, so it returned
**zero, presented as a real approximation**. And `SUM`/`MIN`/`MAX`/`AVG` over no
numeric values returned `0.0` where SQL answers NULL — *a sum of zero and a sum
of nothing are different facts*: the first says the values cancelled, the second
says there were none, and a threshold of `>= 0` passes on one and should never be
reached by the other.

**What a careless version of this test would assert.** For the codelist, that
the compiled SQL does not contain `"IN ()"` — satisfied by emitting `IN (NULL)`
or `1=0`, neither of which is what the parser does for the same mistake written
by hand. For the aggregate, `metric in (0.0, None)`, which erases exactly the
distinction the case exists to make.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import pytest

from prama.backend.reference import ReferenceEvaluator
from prama.backend.sql import SqlCompiler
from prama.core.errors import ValidationError
from prama.ir.lower import Lowerer
from prama.ir.model import Expr, Metric, MetricAggregate
from prama.pql.errors import PqlUnsupportedError
from prama.pql.parser import parse_control

CODELIST_CONTROL = (
    "CHECK corpus.ccy IN CODELIST 'currencies' "
    "SEVERITY major DIMENSION validity BECAUSE 'settlement needs a known currency'"
)


# -- IR-021 / BE-055: an empty codelist ------------------------------------


def test_an_empty_codelist_is_refused_rather_than_compiled() -> None:
    control = parse_control(CODELIST_CONTROL)

    with pytest.raises(ValidationError) as caught:
        Lowerer(codelists={"currencies": ()}).control(control)

    message = str(caught.value)
    assert "currencies" in message, f"the refusal does not name the codelist: {message}"
    assert caught.value.remedy


def test_the_refusal_matches_the_one_the_parser_already_gives() -> None:
    """The same mistake, written two ways, refused for the same reason.

    A codelist is values arriving from somewhere else. If the two paths give
    different reasons, a user who hits one and then the other learns that Prama
    has two opinions about empty sets.
    """
    with pytest.raises(Exception) as by_hand:
        parse_control(
            "CHECK corpus.ccy IN () SEVERITY major DIMENSION validity BECAUSE 'x'",
        )
    with pytest.raises(ValidationError) as by_codelist:
        Lowerer(codelists={"currencies": ()}).control(parse_control(CODELIST_CONTROL))

    assert "empty" in str(by_hand.value).lower()
    assert "empty" in str(by_codelist.value).lower(), (
        f"the codelist refusal does not say the set is empty: {by_codelist.value}"
    )


def test_a_populated_codelist_still_compiles() -> None:
    """The counterfactual. Refusing every codelist would satisfy both above."""
    plan = Lowerer(codelists={"currencies": ("GBP", "USD")}).control(
        parse_control(CODELIST_CONTROL)
    )
    sql = SqlCompiler("duckdb").compile(plan, table="corpus").metric_query

    assert "'GBP'" in sql and "'USD'" in sql
    assert "IN ()" not in sql


def test_an_unregistered_codelist_still_refuses_for_its_own_reason() -> None:
    """The refusal that already worked, so the new one did not displace it.

    "Registered but empty" and "not registered at all" are different mistakes
    with different fixes, and a check inserted before an existing one is exactly
    the change that makes the earlier branch unreachable.
    """
    with pytest.raises(ValidationError) as caught:
        Lowerer(codelists={}).control(parse_control(CODELIST_CONTROL))
    assert "not registered" in str(caught.value)


# -- BE-097: a sum of nothing is not a sum of zero --------------------------


BASE = (
    "CHECK corpus.notional IS NOT NULL "
    "SEVERITY major DIMENSION completeness BECAUSE 'every position has a notional'"
)


def plan_with(metric: Metric):
    """A real plan with its metrics replaced.

    Built by lowering a real control and swapping the metric tuple, rather than
    calling `ControlPlan(...)` with hand-written arguments. An earlier draft did
    the latter, invented three field names, and failed on the constructor rather
    than on the defect — which is the second time this round that writing
    against a remembered interface cost a red herring.
    """
    import dataclasses

    return dataclasses.replace(Lowerer().control(parse_control(BASE)), metrics=(metric,))


@pytest.mark.parametrize("aggregate", ["SUM", "MIN", "MAX", "AVG"], ids=str.lower)
def test_an_aggregate_over_no_numeric_values_is_not_zero(aggregate: str) -> None:
    metric = Metric(name="m", aggregate=MetricAggregate[aggregate], expression=None)
    plan = plan_with(metric)

    computed = ReferenceEvaluator()._metrics(plan, [])
    assert "m" not in computed, (
        f"{aggregate} over no values reported {computed.get('m')!r}. SQL answers "
        "NULL, and the SQL side of the conformance harness drops a NULL metric — "
        "so a 0.0 here is the interpreter and the engines disagreeing by "
        "construction, in the direction that looks like a passing threshold."
    )


def test_an_aggregate_over_real_values_still_computes() -> None:
    """The control. Dropping every metric would satisfy the test above."""
    metric = Metric(name="m", aggregate=MetricAggregate.SUM, expression=Expr.column("notional"))
    plan = plan_with(metric)
    rows: list[dict[str, Any]] = [{"notional": 10.0}, {"notional": 2.5}]

    assert ReferenceEvaluator()._metrics(plan, rows) == {"m": 12.5}


def test_a_sum_that_genuinely_cancels_is_still_zero() -> None:
    """Zero and absent must stay distinguishable in both directions.

    Returning `None` whenever the total happened to be zero would pass the test
    above and destroy the fact it exists to preserve.
    """
    metric = Metric(name="m", aggregate=MetricAggregate.SUM, expression=Expr.column("notional"))
    plan = plan_with(metric)
    rows: list[dict[str, Any]] = [{"notional": 5.0}, {"notional": -5.0}]

    assert ReferenceEvaluator()._metrics(plan, rows) == {"m": 0.0}


# -- BE-096: the interpreter does not invent an approximation ---------------


def test_the_interpreter_refuses_an_approximation_rather_than_returning_zero() -> None:
    metric = Metric(
        name="m",
        aggregate=MetricAggregate.APPROX_COUNT_DISTINCT,
        expression=Expr.column("isin"),
    )
    plan = plan_with(metric)

    with pytest.raises(PqlUnsupportedError) as caught:
        ReferenceEvaluator()._metrics(plan, [{"isin": "GB0002634946"}])

    assert "approx" in str(caught.value).lower()


def test_that_refusal_is_a_conforming_outcome_not_a_failure() -> None:
    """`refused` and `failed` are different claims about an engine.

    The harness's own words, fifteen lines above the reference path: "A refusal
    is a conforming outcome. It is the promise being kept." The interpreter's
    refusal was being reported as a failure, which is the harness calling its
    own correct behaviour a defect.
    """
    import inspect

    from prama.backend import conformance

    source = inspect.getsource(conformance.ConformanceRun._run_reference)
    assert "PqlUnsupportedError" in source and "refused" in source, (
        "the reference path does not treat an unsupported metric as a refusal"
    )

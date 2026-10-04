"""A PQL function, ``DAYS_BETWEEN``: the worked example of docs/developer/pql-functions.md.

``DAYS_BETWEEN(trade_date, settlement_date)`` is the number of calendar days
from the first ISO-8601 date to the second, so a control can say

    CHECK trades SATISFIES DAYS_BETWEEN(trade_date, settlement_date) <= 3

It is a good example because the three engines spell it three different ways,
which is exactly what ``sql_by_engine`` exists for, and because its reference
implementation is short enough to read beside them. The conformance test runs
each engine's SQL and this ``evaluate`` on the same inputs and requires the same
answer: the lowering is checked against the reference, not trusted.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from prama.pql.families import NUMBER, TEMPORAL
from prama.pql.functions import UNSET, Function, FunctionRegistry


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _days_between(arguments: list[Any]) -> Any:
    """The reference implementation. Exact, and unknown when either date is not a date."""
    start, end = _day(arguments[0]), _day(arguments[1])
    if start is None or end is None:
        # Not zero, and not an error value: a date nobody can read makes the
        # answer unknown, and unknown counts as a violation.
        return UNSET
    return Decimal((end - start).days)


DAYS_BETWEEN = Function(
    name="DAYS_BETWEEN",
    summary="Calendar days from the first ISO-8601 date to the second; negative if earlier.",
    arity=(2, 2),
    returns=NUMBER,
    argument_types=(TEMPORAL, TEMPORAL),
    # PostgreSQL: subtracting two dates is an integer number of days.
    sql="(CAST({1} AS DATE) - CAST({0} AS DATE))",
    sql_by_engine={
        "duckdb": "DATE_DIFF('day', CAST({0} AS DATE), CAST({1} AS DATE))",
        # SQLite has no date type; JULIANDAY of ISO text is a day number.
        "sqlite": "CAST(JULIANDAY({1}) - JULIANDAY({0}) AS INTEGER)",
    },
    evaluate=_days_between,
    excel_divergence=(
        "Excel's DAYS takes the end date first, DAYS(end, start). This takes them in "
        "the order they happen, start then end, which is how a settlement lag is "
        "read aloud; swapping them flips the sign, and a control comparing the "
        "result with 3 would then pass every late trade."
    ),
)


def install(registry: FunctionRegistry) -> FunctionRegistry:
    """Add ``DAYS_BETWEEN`` to *registry*. Explicit, never on import."""
    registry.register(DAYS_BETWEEN)
    return registry

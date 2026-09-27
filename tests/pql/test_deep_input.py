"""Pathological input is refused with a location, never a RecursionError.

QA C20 (`PQL-175`, `PQL-176`, `PQL-177`). Each of these inputs is reachable
from an HTTP endpoint, where a bare `RecursionError` is a 500 with a traceback.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.backend.sql import SqlCompiler
from prama.ir.lower import lower
from prama.pql.errors import PqlSyntaxError
from prama.pql.parser import MAX_NESTING, parse_control


def test_deep_parentheses_are_a_located_refusal() -> None:
    depth = 1000
    source = "CHECK p SATISFIES " + "(" * depth + "a > 0" + ")" * depth
    with pytest.raises(PqlSyntaxError, match="nested more than"):
        parse_control(source)


def test_reasonable_nesting_still_parses() -> None:
    # The control: well inside the bound.
    depth = MAX_NESTING // 2
    parse_control("CHECK p SATISFIES " + "(" * depth + "a > 0" + ")" * depth)


def test_a_thousand_ors_lower_and_compile() -> None:
    # 1,000 terms, not 100: Python's default limit is 1,000 frames, so a
    # small case passes whether or not the walk is recursive.
    terms = " OR ".join(f"a = {i}" for i in range(1000))
    plan = lower(parse_control(f"CHECK p.b IS NOT NULL WHERE {terms}"))
    assert "a" in plan.scope.filter.columns()
    assert SqlCompiler("sqlite").compile(plan, table="p").metric_query


def test_a_500_column_key_runs_where_the_engine_can_and_is_refused_where_it_cannot() -> None:
    import duckdb

    from prama.pql.errors import PqlUnsupportedError

    columns = [f"c{i}" for i in range(500)]
    plan = lower(parse_control(f"CHECK p HAS UNIQUE KEY ({', '.join(columns)})"))
    query = SqlCompiler("duckdb").compile(plan, table="p").metric_query
    db = duckdb.connect()
    db.execute("CREATE TABLE p (" + ", ".join(f"{c} INTEGER" for c in columns) + ")")
    db.execute("INSERT INTO p VALUES (" + ",".join(["1"] * 500) + ")")
    assert db.execute(query).fetchone() is not None
    # SQLite caps expression depth; it says so while compiling, not at run time.
    with pytest.raises(PqlUnsupportedError, match="500 columns"):
        SqlCompiler("sqlite").compile(plan, table="p")


def test_a_key_sqlite_can_hold_still_runs_there() -> None:
    import sqlite3

    columns = [f"c{i}" for i in range(200)]
    plan = lower(parse_control(f"CHECK p HAS UNIQUE KEY ({', '.join(columns)})"))
    query = SqlCompiler("sqlite").compile(plan, table="p").metric_query
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE p (" + ", ".join(f"{c} INTEGER" for c in columns) + ")")
    assert db.execute(query).fetchone() is not None

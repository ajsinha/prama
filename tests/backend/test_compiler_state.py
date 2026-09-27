"""The SQL compiler keeps no state between calls.

QA C9 (`BE-034`, `BE-037`): the current source table lived on the compiler.
With a scan limit, a correlated subquery was qualified by the whole
`(SELECT … LIMIT n)` text, which is invalid SQL on every engine. And a later
call that did not set the table inherited the previous compile's.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3

from prama.backend.sql import SqlCompiler
from prama.ir.lower import lower
from prama.pql.parser import parse_control

REFERENCE = "CHECK p.account_id REFERENCES accounts.account_id"


def _db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(
        'CREATE TABLE "p" (account_id TEXT); CREATE TABLE "accounts" (account_id TEXT);'
        "INSERT INTO p VALUES ('a1'), ('orphan'); INSERT INTO accounts VALUES ('a1');"
    )
    return db


def _orphans(sql: str) -> float:
    row = _db().execute(sql).fetchone()
    return float(row[-1])


def test_a_scan_limited_referential_control_runs_and_finds_the_orphan() -> None:
    plan = lower(parse_control(REFERENCE))
    compiled = SqlCompiler("sqlite").compile(plan, table="p", scan_limit=100)
    assert _orphans(compiled.metric_query) == 1  # previously: a syntax error


def test_the_unlimited_control_is_unchanged() -> None:
    # The control: the ordinary path gave the right answer before and after.
    plan = lower(parse_control(REFERENCE))
    compiled = SqlCompiler("sqlite").compile(plan, table="p")
    assert _orphans(compiled.metric_query) == 1


def test_a_later_call_does_not_inherit_the_last_table() -> None:
    compiler = SqlCompiler("sqlite")
    compiler.compile(lower(parse_control(REFERENCE)), table="stale_table")
    later = lower(parse_control(REFERENCE))
    assert "stale_table" not in compiler.expression(later.predicate)

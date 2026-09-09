"""Engines for the conformance suite.

DuckDB and SQLite are in-process and always run. PostgreSQL joins when
PRAMA_TEST_POSTGRES_DSN names a server — and when it does, the suite is
comparing three genuinely different query engines rather than two.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest

from prama.backend.conformance import REFERENCE, ConformanceRun
from prama.backend.corpus import COLUMNS, ROWS, create_table, insert_rows
from prama.connect.sources.query import register_regexp

DSN = os.environ.get("PRAMA_TEST_POSTGRES_DSN", "")


@pytest.fixture(scope="session")
def duckdb_runner() -> Iterator[Any]:
    import duckdb

    connection = duckdb.connect()
    connection.execute(create_table(dialect="duckdb"))
    connection.executemany(insert_rows(), [list(row) for row in ROWS])

    def run(sql: str) -> list[dict[str, Any]]:
        relation = connection.sql(sql)
        columns = [d[0] for d in relation.description]
        return [dict(zip(columns, row, strict=True)) for row in relation.fetchall()]

    yield run
    connection.close()


@pytest.fixture(scope="session")
def sqlite_runner() -> Iterator[Any]:
    connection = sqlite3.connect(":memory:")
    # The same registration Prama's own SQLite executor performs. The dialect
    # declares the regex capability on the strength of it, so a conformance
    # harness that opened a bare connection would be testing a configuration
    # Prama never ships — and would report a disagreement between engines that
    # does not exist in the product.
    register_regexp(connection)
    connection.execute(create_table(dialect="sqlite"))
    connection.executemany(insert_rows(), [list(row) for row in ROWS])
    connection.commit()

    def run(sql: str) -> list[dict[str, Any]]:
        cursor = connection.execute(sql)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    yield run
    connection.close()


@pytest.fixture(scope="session")
def postgres_runner() -> Iterator[Any]:
    if not DSN:
        pytest.skip("set PRAMA_TEST_POSTGRES_DSN to include PostgreSQL")
    import asyncio

    import asyncpg

    loop = asyncio.new_event_loop()

    async def prepare() -> Any:
        connection = await asyncpg.connect(DSN)
        await connection.execute('DROP TABLE IF EXISTS "corpus"')
        await connection.execute(create_table(dialect="postgresql"))
        await connection.executemany(insert_rows(placeholder="$"), [list(row) for row in ROWS])
        return connection

    connection = loop.run_until_complete(prepare())

    def run(sql: str) -> list[dict[str, Any]]:
        return [dict(r) for r in loop.run_until_complete(connection.fetch(sql))]

    yield run
    loop.run_until_complete(connection.close())
    loop.close()


#: The corpus as rows, for the implementation that does not speak SQL.
CORPUS_ROWS = [dict(zip([name for name, _ in COLUMNS], row, strict=True)) for row in ROWS]


@pytest.fixture
def engines(duckdb_runner: Any, sqlite_runner: Any, request: pytest.FixtureRequest) -> dict:
    """Every implementation available here.

    The reference interpreter is always among them, and is the one that makes
    this worth running: three SQL backends agreeing proves agreement about the
    compiler they share, not about the meaning.
    """
    available: dict[str, Any] = {
        "duckdb": duckdb_runner,
        "sqlite": sqlite_runner,
        REFERENCE: _no_sql,
    }
    if DSN:
        available["postgresql"] = request.getfixturevalue("postgres_runner")
    return available


@pytest.fixture
def conformance() -> ConformanceRun:
    return ConformanceRun(rows=CORPUS_ROWS)


def _no_sql(sql: str) -> list[dict[str, Any]]:
    """The reference interpreter is never asked for SQL, and never gives any."""
    raise AssertionError(f"the reference interpreter was asked to run SQL: {sql[:60]}")

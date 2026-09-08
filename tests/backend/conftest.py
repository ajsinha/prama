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

from prama.backend.corpus import ROWS, create_table, insert_rows

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


@pytest.fixture
def engines(duckdb_runner: Any, sqlite_runner: Any, request: pytest.FixtureRequest) -> dict:
    """Every engine available here, PostgreSQL included when it is reachable."""
    available: dict[str, Any] = {"duckdb": duckdb_runner, "sqlite": sqlite_runner}
    if DSN:
        available["postgresql"] = request.getfixturevalue("postgres_runner")
    return available

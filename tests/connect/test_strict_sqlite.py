"""A control on a misspelled column is an error on SQLite, as on every engine.

SQLite reads a double-quoted identifier it cannot resolve as a string literal,
so `"notionall" IS NOT NULL` tested a constant and passed every row. QA finding
Q-08 turned that off for Prama's own database only; a control over a SQLite
*source*, on the server or on an agent, still passed a typo. Measured before
this fix: `CHECK trades.notionall IS NOT NULL` reported pass, 0 of 2 rows
violating, over a table whose column is `notional`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from prama_agent.config import Source
from prama_agent.executors import SqliteExecutor
from prama_kernel import strict_sqlite
from prama_kernel.errors import ConfigError

from prama.connect.builtin import register_builtin
from prama.connect.registry import ConnectorRegistry

TYPO = 'SELECT COUNT(*) AS violating_rows FROM trades WHERE "notionall" IS NULL'


@pytest.fixture
def book(tmp_path: Path) -> Path:
    path = tmp_path / "book.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE trades (trade_id TEXT, notional REAL)")
        db.executemany("INSERT INTO trades VALUES (?, ?)", [("a", 1.0), ("b", None)])
    return path


def test_plain_sqlite_still_invents_the_string(book: Path) -> None:
    """The hazard itself, so the tests below cannot pass for the wrong reason."""
    with sqlite3.connect(book) as db:
        assert db.execute(TYPO).fetchone() == (0,)


def test_a_strict_connection_refuses_the_typo(book: Path) -> None:
    db = strict_sqlite.connect(str(book))
    with pytest.raises(sqlite3.OperationalError, match="no such column"):
        db.execute(TYPO)
    db.close()


async def test_the_servers_sqlite_source_refuses_it(book: Path) -> None:
    connector = register_builtin(ConnectorRegistry()).create("sqlite", {"database_path": str(book)})
    with pytest.raises(sqlite3.OperationalError, match="no such column"):
        await connector.run_metric_query(TYPO)


def test_the_agents_sqlite_executor_refuses_it(book: Path) -> None:
    execute = SqliteExecutor(Source("trades", "sqlite", path=str(book)))
    with pytest.raises(sqlite3.OperationalError, match="no such column"):
        execute(TYPO)


def test_a_python_that_cannot_switch_it_off_is_refused_not_trusted() -> None:
    class Lenient:
        """A connection without setconfig, as on Python 3.11."""

        closed = False

        def close(self) -> None:
            self.closed = True

    lenient = Lenient()
    with pytest.raises(ConfigError, match="cannot make SQLite refuse"):
        strict_sqlite.strict(lenient)  # type: ignore[arg-type]
    assert lenient.closed

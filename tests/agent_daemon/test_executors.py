"""Executors: read-only by construction, chosen by binding, never by guessing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import sys
from pathlib import Path

import pytest
from prama_agent.config import Source
from prama_agent.executors import (
    DuckdbExecutor,
    Executors,
    PostgresExecutor,
    SqliteExecutor,
)
from prama_kernel.errors import ConfigError, NotFoundError
from tests.agent_daemon.conftest import amount_present


def test_sqlite_answers_with_rows_as_mappings(source: Path) -> None:
    execute = SqliteExecutor(Source("trades", "sqlite", path=str(source)))
    rows = execute("SELECT trade_id, ccy FROM trades ORDER BY trade_id")
    assert rows[0] == {"trade_id": 1, "ccy": "EUR"} and len(rows) == 4
    batches = list(execute.batches("SELECT trade_id FROM trades", 3))
    assert [len(b) for b in batches] == [3, 1]


def test_sqlite_cannot_be_written_through_the_agent(source: Path) -> None:
    execute = SqliteExecutor(Source("trades", "sqlite", path=str(source)))
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        execute("DELETE FROM trades")
    # The counterfactual: the same statement on an ordinary connection works,
    # so it was the executor that refused, not the statement that was wrong.
    connection = sqlite3.connect(source)
    connection.execute("DELETE FROM trades WHERE trade_id = 4")
    connection.commit()
    connection.close()
    assert len(execute("SELECT * FROM trades")) == 3


def test_a_missing_sqlite_file_is_named(tmp_path: Path) -> None:
    execute = SqliteExecutor(Source("trades", "sqlite", path=str(tmp_path / "gone.db")))
    with pytest.raises(FileNotFoundError, match=r"gone\.db"):
        execute("SELECT 1")


def test_duckdb_is_read_only_too(tmp_path: Path) -> None:
    duckdb = pytest.importorskip("duckdb")
    path = tmp_path / "lake.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute("CREATE TABLE p AS SELECT 1 AS id")
    connection.close()
    execute = DuckdbExecutor(Source("lake", "duckdb", path=str(path)))
    assert execute("SELECT id FROM p") == [{"id": 1}]
    with pytest.raises(duckdb.Error):
        execute("INSERT INTO p VALUES (2)")


def test_a_missing_optional_driver_fails_at_start_with_the_install_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "duckdb", None)
    with pytest.raises(ConfigError, match=r"prama-agent\[duckdb\]"):
        DuckdbExecutor(Source("lake", "duckdb", path="/x"))


def test_postgres_reads_its_credential_from_the_environment_at_use() -> None:
    pytest.importorskip("psycopg")
    source = Source("ledger", "postgres", dsn="host=db user=u", password_env="PG_PW")
    missing = PostgresExecutor(source, environ={})
    with pytest.raises(ConfigError, match=r"\$PG_PW"):
        missing._conninfo()
    present = PostgresExecutor(source, environ={"PG_PW": "s3cret"})
    assert present._conninfo() == ("host=db user=u", {"password": "s3cret"})
    whole = PostgresExecutor(
        Source("ledger", "postgres", dsn_env="LEDGER_DSN"), environ={"LEDGER_DSN": "host=x"}
    )
    assert whole._conninfo() == ("host=x", {})


def test_the_executor_is_chosen_by_binding_then_by_dataset(source: Path) -> None:
    by_binding = Executors([Source("trades", "sqlite", path=str(source))])
    assignment = amount_present()
    assert by_binding(assignment).source.binding == "trades"

    by_dataset = Executors([Source("wh", "sqlite", path=str(source), datasets=("trades",))])
    assert by_dataset(assignment).source.binding == "wh"


def test_a_binding_this_agent_lacks_is_an_error_not_a_guess(source: Path) -> None:
    # One source, of the right engine, that is not the one named: running the
    # query there would judge the wrong data.
    executors = Executors([Source("elsewhere", "sqlite", path=str(source))])
    with pytest.raises(NotFoundError, match="no source bound to 'trades'"):
        executors(amount_present())


def test_an_engine_mismatch_is_refused_and_postgresql_means_postgres(source: Path) -> None:
    executors = Executors([Source("trades", "sqlite", path=str(source))])
    with pytest.raises(NotFoundError, match="compiled for duckdb"):
        executors(dataclasses.replace(amount_present(), engine="duckdb"))
    fake = SqliteExecutor(Source("trades", "postgres", dsn="host=x"))
    fake.engine = "postgres"
    aliased = Executors.of({"trades": fake})
    assert aliased(dataclasses.replace(amount_present(), engine="postgresql")) is fake

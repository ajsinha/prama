"""Running a compiled control against a real source.

Two guards, both because the statement being executed was written by a
compiler rather than a person, and defence in depth is cheap where the thing
executing is generated.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from prama.connect import ConnectorError
from prama.connect.sources.sqlite import SqliteConnector

pytestmark = pytest.mark.anyio


@pytest.fixture
def source(tmp_path: Path) -> Path:
    import sqlite3

    path = tmp_path / "source.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE positions (account_id TEXT, notional REAL)")
    connection.executemany("INSERT INTO positions VALUES (?, ?)", [("A1", 100.0), ("A2", None)])
    connection.commit()
    connection.close()
    return path


async def _connector(path: Path) -> Any:
    connector = SqliteConnector({"database_path": str(path)})
    await connector.open()
    return connector


class TestItRunsAControl:
    async def test_a_metric_query_returns_named_columns(self, source: Path) -> None:
        """Named, because a metric dictionary with invented keys would be
        judged against the wrong thresholds."""
        connector = await _connector(source)
        try:
            rows = await connector.run_metric_query(
                "SELECT count(*) AS scanned_rows, "
                "sum(CASE WHEN notional IS NULL THEN 1 ELSE 0 END) AS violating_rows "
                "FROM positions"
            )
        finally:
            await connector.close()
        assert rows == [{"scanned_rows": 2, "violating_rows": 1}]

    async def test_a_relational_source_says_it_can_run_controls(self, source: Path) -> None:
        connector = await _connector(source)
        try:
            assert connector.can_run_controls is True
        finally:
            await connector.close()

    async def test_a_trailing_semicolon_is_tolerated(self, source: Path) -> None:
        """Compilers emit them, and refusing one would be pedantry rather than
        safety."""
        connector = await _connector(source)
        try:
            assert await connector.run_metric_query("SELECT count(*) AS n FROM positions;")
        finally:
            await connector.close()


class TestItRefusesAnythingThatIsNotACheck:
    @pytest.mark.parametrize(
        "sql",
        [
            "DELETE FROM positions",
            "DROP TABLE positions",
            "UPDATE positions SET notional = 0",
            "INSERT INTO positions VALUES ('A3', 1.0)",
            "PRAGMA writable_schema = 1",
        ],
    )
    async def test_a_write_is_refused(self, source: Path, sql: str) -> None:
        """A control is a check. It has no business writing, and refusing
        anything that is not a read means a defect in the compiler cannot
        damage the data it was meant to examine."""
        connector = await _connector(source)
        try:
            with pytest.raises(ConnectorError, match="read-only"):
                await connector.run_metric_query(sql)
        finally:
            await connector.close()

    async def test_a_second_statement_is_refused(self, source: Path) -> None:
        """A trailing semicolon and a second statement is the shape of every
        SQL injection there has ever been, and a metric query has no
        legitimate reason to be two."""
        connector = await _connector(source)
        try:
            with pytest.raises(ConnectorError, match="single statement"):
                await connector.run_metric_query(
                    "SELECT count(*) AS n FROM positions; DROP TABLE positions"
                )
        finally:
            await connector.close()

    async def test_the_data_survives_a_refused_write(self, source: Path) -> None:
        """The counterfactual that matters: refusing must actually prevent it,
        not merely report it."""
        connector = await _connector(source)
        try:
            with pytest.raises(ConnectorError):
                await connector.run_metric_query("DELETE FROM positions")
            rows = await connector.run_metric_query("SELECT count(*) AS n FROM positions")
        finally:
            await connector.close()
        assert rows[0]["n"] == 2

    async def test_an_empty_query_says_it_is_a_compiler_defect(self, source: Path) -> None:
        connector = await _connector(source)
        try:
            with pytest.raises(ConnectorError, match="compiler defect"):
                await connector.run_metric_query("   ")
        finally:
            await connector.close()


class TestASourceWithoutAQueryEngine:
    async def test_it_says_so_rather_than_failing_obscurely(self, tmp_path: Path) -> None:
        """A caller landing here is not doing something wrong — it is talking
        to a source whose controls run a different way, and the refusal says
        which way."""
        from prama.connect.sources.filesystem import FilesystemConnector

        connector = FilesystemConnector({"root": str(tmp_path)})
        assert connector.can_run_controls is False
        with pytest.raises(ConnectorError, match="evaluated locally"):
            await connector.run_metric_query("SELECT 1")


class TestTheRunnerBridge:
    async def test_a_connector_becomes_an_executor(self, source: Path) -> None:
        """The runner's contract is a synchronous callable. The bridge is here
        rather than in the runner, which should not know that some sources are
        reached over a network and others are a file."""
        from prama.connect.sources.query import executor_from

        connector = await _connector(source)
        try:
            execute = executor_from(connector)
            assert execute("SELECT count(*) AS n FROM positions") == [{"n": 2}]
        finally:
            await connector.close()

    async def test_it_works_from_inside_a_running_event_loop(self, source: Path) -> None:
        """asyncio.run is fatal when a loop is already turning, and the runner
        is called from inside a request or a task. Finding that out at the
        moment a control executes is the worst possible place."""
        from prama.connect.sources.query import executor_from

        connector = await _connector(source)
        try:
            # This test function *is* the running loop.
            execute = executor_from(connector)
            assert execute("SELECT count(*) AS n FROM positions") == [{"n": 2}]
        finally:
            await connector.close()

    async def test_a_source_without_a_query_engine_refuses_up_front(self, tmp_path: Path) -> None:
        """Discovering it halfway through a run would leave a partial ledger
        and an error record blaming the source for something Prama should have
        known before it started."""
        from prama.connect.sources.filesystem import FilesystemConnector
        from prama.connect.sources.query import executor_from

        with pytest.raises(ConnectorError, match="evaluated locally"):
            executor_from(FilesystemConnector({"root": str(tmp_path)}))

    async def test_the_bridge_still_refuses_a_write(self, source: Path) -> None:
        from prama.connect.sources.query import executor_from

        connector = await _connector(source)
        try:
            with pytest.raises(ConnectorError, match="read-only"):
                executor_from(connector)("DELETE FROM positions")
        finally:
            await connector.close()

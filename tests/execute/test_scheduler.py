"""The always-on scheduler runs due controls, one server per tick.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.db import Database
from prama.execute.scheduler import LEASE, Scheduler, from_config


def _never_called(path: str, dialect: str) -> Any:
    raise AssertionError("a skipped tick must not open the source")


async def test_a_tick_that_holds_the_lease_runs(
    started_database: Database, tenant_id: str, tmp_path: Any
) -> None:
    import duckdb

    source = tmp_path / "w.duckdb"
    duckdb.connect(str(source)).close()
    scheduler = Scheduler(started_database, [tenant_id], against=str(source), dialect="duckdb")
    tick = await scheduler.tick()
    assert tick.outcome == "ran", tick.detail
    assert scheduler.history[0] is tick


async def test_a_second_server_skips_while_the_first_holds_the_lease(
    started_database: Database, tenant_id: str
) -> None:
    other = await started_database.lease_provider().acquire(LEASE, "other-server", 60)
    assert other is not None
    scheduler = Scheduler(
        started_database,
        [tenant_id],
        against="x",
        dialect="duckdb",
        holder="me",
        executor_for=_never_called,
    )
    tick = await scheduler.tick()
    assert tick.outcome == "skipped"
    await started_database.lease_provider().release(other)


async def test_a_failing_source_is_a_failed_tick_not_a_dead_loop(
    started_database: Database, tenant_id: str
) -> None:
    scheduler = Scheduler(
        started_database, [tenant_id], against="/nonexistent.duckdb", dialect="duckdb"
    )
    tick = await scheduler.tick()
    assert tick.outcome == "failed" and "nonexistent" in tick.detail
    # The lease was released, so the next tick can run.
    again = await scheduler.tick()
    assert again.outcome == "failed"


def test_it_is_off_unless_configured(sqlite_config: Any) -> None:
    assert from_config(sqlite_config, database=None) is None


def test_history_is_bounded() -> None:
    scheduler = Scheduler(None, [], against="x", dialect="duckdb")
    assert scheduler.history.maxlen is not None

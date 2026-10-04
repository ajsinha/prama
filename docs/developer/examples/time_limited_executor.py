"""An agent executor with a time limit: the worked example of docs/developer/agent-executors.md.

The `prama-agent` daemon runs SQL the server compiled, against a source only its
own machine can reach. Its SQLite executor is read-only by construction; this
one is also **bounded in time**: a statement still running after ``seconds`` is
interrupted by SQLite itself, through a progress handler, and the assignment
fails with a message naming the limit rather than holding the agent's only
worker for as long as the query cares to take.

It is embedded the way `prama_agent.executors.Executors.of` documents for an
embedder with executors of its own; adding an engine *to the daemon's
configuration* is the other path, described in the guide.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path

from prama_agent.config import Source
from prama_agent.executors import Rows, SqliteExecutor

#: SQLite virtual-machine instructions between checks of the clock.
CHECK_EVERY = 10_000


class TimeLimitedSqliteExecutor(SqliteExecutor):
    """A read-only SQLite executor that interrupts a statement after *seconds*."""

    engine = "sqlite"

    def __init__(self, source: Source, *, seconds: float = 30.0) -> None:
        super().__init__(source)
        self.seconds = seconds

    def batches(self, sql: str, size: int) -> Iterator[Rows]:
        path = Path(self.source.path)
        if not path.exists():
            raise FileNotFoundError(f"the sqlite source {self.source.binding} has no file {path}")
        # mode=ro: read-only by construction, exactly as the shipped executor.
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        deadline = time.monotonic() + self.seconds
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), CHECK_EVERY)
        try:
            cursor = connection.execute(sql)
            columns = [d[0] for d in cursor.description or ()]
            while chunk := cursor.fetchmany(size):
                yield [dict(zip(columns, row, strict=True)) for row in chunk]
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc):
                raise TimeoutError(
                    f"the statement on {self.source.binding} ran past {self.seconds:g}s and "
                    "was interrupted; raise the limit or narrow the control"
                ) from exc
            raise
        finally:
            connection.close()

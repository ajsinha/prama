"""Running a query against a customer's file, and handing back rows.

The control runner's whole interface to a source is a callable that takes SQL
and returns dictionaries. This is that callable for the two file-backed engines
Prama ships with, and it lives here because this is where database drivers are
allowed to be: ``prama.connect.sources`` talks to a customer's data, which is
the data plane and genuinely needs a driver.

It is not a convenience wrapper. Putting it anywhere else — the CLI, the
runner — would mean a layer that is not the data plane holding a driver, which
is the beginning of that layer doing persistence itself. An architecture test
enforces the boundary, and it caught this file being written in the wrong
place.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from prama.core.errors import ValidationError

#: Read-only, always. A control is a *check*: it has no business being able to
#: write, and opening read-only means a defect in a generated query cannot
#: damage the data it was meant to examine.
READ_ONLY = True


#: Engine name to the function that opens it. A table rather than a chain of
#: comparisons: a deployment adds an engine by registering one here, and the
#: architecture test that forbids branching on an engine name stays satisfied
#: for the reason it exists rather than by exemption.
BUILDERS: dict[
    str, Callable[[Path], tuple[Callable[[str], list[dict[str, Any]]], Callable[[], None]]]
] = {}


def executor_for(
    path: str | Path, engine: str
) -> tuple[Callable[[str], list[dict[str, Any]]], Callable[[], None]]:
    """A query callable over a local file, and the way to close it.

    Rows come back as dictionaries because that is what the runner's contract
    says. A driver that hands back tuples is adapted here rather than in the
    runner, which should not know what it is talking to.
    """
    target = Path(path)
    if not target.exists():
        raise ValidationError(
            f"there is no file at {target}",
            remedy="Check the path. A control cannot examine data that is not there.",
            context={"path": str(target)},
        )
    builder = BUILDERS.get(engine)
    if builder is None:
        raise ValidationError(
            f"no file-backed executor for {engine!r}",
            remedy=(
                "Available: " + ", ".join(sorted(BUILDERS)) + ". For anything else, "
                "supply your own executor — the runner's whole interface to a source "
                "is a callable that takes SQL and returns rows."
            ),
            context={"engine": engine},
        )
    return builder(target)


def _duckdb(path: Path) -> tuple[Callable[[str], list[dict[str, Any]]], Callable[[], None]]:
    import duckdb

    connection = duckdb.connect(str(path), read_only=READ_ONLY)

    def execute(sql: str) -> list[dict[str, Any]]:
        cursor = connection.execute(sql)
        names = [column[0] for column in cursor.description or ()]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    return execute, connection.close


def _sqlite(path: Path) -> tuple[Callable[[str], list[dict[str, Any]]], Callable[[], None]]:
    import sqlite3

    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row

    def execute(sql: str) -> list[dict[str, Any]]:
        return [dict(row) for row in connection.execute(sql).fetchall()]

    return execute, connection.close


BUILDERS["duckdb"] = _duckdb
BUILDERS["sqlite"] = _sqlite

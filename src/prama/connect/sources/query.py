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

from prama.core.concurrency.supervisor import run_sync
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
    if not target.is_file():
        # `exists()` is true for a directory, which then reached DuckDB and came
        # back as `_duckdb.IOException: Is a directory` — a driver's error for a
        # mistake made three layers above it. The same `exists()`-not-`is_file()`
        # confusion was found in `cli/contract.py::_rows`. QA round 4, `CLI-139`.
        raise ValidationError(
            f"{target} is not a file",
            remedy=(
                "--against names one data file for the control to read — a .csv, "
                ".parquet or .duckdb — not a directory of them."
            ),
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


def register_regexp(connection: Any) -> None:
    """Give a SQLite connection the REGEXP operator.

    SQLite ships no regular-expression engine. It *reserves* the ``REGEXP``
    operator and dispatches it to a two-argument function of that name if the
    host has registered one — a documented hook, and the only way SQLite ever
    does regex. Prama's SQLite dialect declares the capability on the strength
    of this function, so every SQLite connection Prama opens must call it.

    A ``None`` value yields ``NULL`` rather than ``False``: SQL's three-valued
    logic makes a null neither matching nor non-matching, and the control's
    ``TREAT UNKNOWN`` policy — not this function — decides what that means.

    That sentence was already here and the code returned ``False``, which is a
    definite *non-match* and not an unknown (QA finding Q-12). So a null
    reaching a validity check was a certain violation, the unknown policy never
    saw it, and ``TREAT UNKNOWN AS PASS`` could not rescue it: 11 violations on
    SQLite against 4 on DuckDB, for the same control over the same rows.
    """
    import re

    def regexp(pattern: str, value: Any) -> bool | None:
        # SQLite calls REGEXP with the pattern first: `x REGEXP y` is
        # `regexp(y, x)`. Getting this backwards matches nothing, silently, and
        # every validity control passes.
        if value is None:
            return None
        return re.search(pattern, str(value)) is not None

    connection.create_function("regexp", 2, regexp)


def _sqlite(path: Path) -> tuple[Callable[[str], list[dict[str, Any]]], Callable[[], None]]:
    import sqlite3

    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    register_regexp(connection)

    def execute(sql: str) -> list[dict[str, Any]]:
        return [dict(row) for row in connection.execute(sql).fetchall()]

    return execute, connection.close


BUILDERS["duckdb"] = _duckdb
BUILDERS["sqlite"] = _sqlite


def executor_from(connector: Any) -> Callable[[str], list[dict[str, Any]]]:
    """The runner's executor, backed by a connector.

    Synchronous because that is the runner's contract, and the runner's
    contract is synchronous because the same callable has to serve a warehouse,
    a test with a dictionary, and an agent forwarding into a zone. The bridge
    is here rather than in the runner, which should not know that some sources
    are reached over a network and others are a file.

    Refuses up front for a source with no query engine of its own. Discovering
    that halfway through a run would leave a partial ledger and an error record
    that blames the source for something Prama should have known before it
    started.
    """
    from prama.connect.spi import ConnectorError

    if not connector.can_run_controls:
        raise ConnectorError(
            f"{type(connector).__name__} cannot evaluate a control at the source",
            remedy=(
                "This source has no query engine, so its controls are evaluated "
                "locally over the rows `read` yields. Asking for an executor here "
                "would fail on the first control rather than now."
            ),
            context={"connector": type(connector).__name__},
        )

    def execute(sql: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = run_sync(connector.run_metric_query(sql))
        return rows

    return execute


#: Statements a control may run. A control is a check, and everything else is
#: either a mistake or an attack.
READ_PREFIXES = ("select", "with")


def sole_read_statement(sql: str) -> str:
    """The one read-only statement in *sql*, or a refusal naming why not.

    Two guards, both because the statement was written by a compiler rather
    than a person, and defence in depth is cheap where the thing executing is
    generated:

    * **Read-only.** A control is a check. It has no business writing, and
      refusing anything that is not a SELECT or a WITH means a defect in the
      compiler cannot damage the data it was meant to examine.
    * **One statement.** A trailing semicolon and a second statement is the
      shape of every SQL injection there has ever been, and a metric query has
      no legitimate reason to be two.
    """
    from prama.connect.spi import ConnectorError

    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise ConnectorError(
            "an empty query cannot be run",
            remedy="This is a compiler defect; the control produced no SQL.",
        )
    if ";" in stripped:
        raise ConnectorError(
            "a control's query must be a single statement",
            remedy=(
                "Two statements separated by a semicolon is the shape of every SQL "
                "injection there has ever been, and a metric query has no legitimate "
                "reason to be two."
            ),
            context={"sql": stripped[:120]},
        )
    if not stripped.lower().startswith(READ_PREFIXES):
        raise ConnectorError(
            "a control may only run a read-only query",
            remedy=(
                "A control is a check; it has no business writing. Permitted: "
                + ", ".join(prefix.upper() for prefix in READ_PREFIXES)
                + "."
            ),
            context={"sql": stripped[:120]},
        )
    return stripped

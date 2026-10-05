"""A registered connection opened for a run the server performs itself.

`executor_for` opens whatever file it is handed, which is right for the CLI and
the scheduler: the person typing ``--against`` or writing ``scheduler.against``
controls the host. A run requested over the HTTP API is different. The path
comes from a connection's stored ``config``, and anybody who may declare a
connection could otherwise point one at any file the server process can read —
another estate's data, or Prama's own database, whose evidence and sample rows
a custom-SQL control could then count and sample back.

So a source opened here is **confined**, three ways:

* **Its path must lie under a configured root** (``runs.roots``). The operator
  names the directories customer data lives in; nothing else is opened. With
  no roots configured, nothing is: the safe default for a server whose owner
  has not decided.
* **Prama's own store may not lie under a root.** Otherwise a control could
  read the ledger it writes to. Refused outright, naming the file.
* **The engine is fenced in as well as the path.** A DuckDB connection is given
  the roots as its only allowed directories and then has external access
  switched off — a switch that cannot be switched back on for that connection —
  so ``read_csv('/etc/…')`` inside a custom-SQL control is refused by the
  engine. Every statement must be a single read-only ``SELECT``/``WITH``, so a
  SQLite source cannot ``ATTACH`` another database either.

Three kinds of source, the three the case studies use:

* ``sqlite`` — one SQLite file, opened read-only.
* ``duckdb`` — one DuckDB file (often a catalogue of views over CSV and
  Parquet), opened read-only.
* ``files`` — a directory of ``.csv``, ``.parquet`` and JSON-lines files, each
  a table named after the file (or a sub-directory of like files, named after
  the directory), read in place by an in-memory DuckDB.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

from prama.connect.sources.query import register_regexp, sole_read_statement
from prama.core.errors import ForbiddenError, PramaError, ValidationError, first_line

Execute = Callable[[str], list[dict[str, Any]]]

#: How a file in a ``files`` directory is read, by extension.
READERS: dict[str, str] = {
    ".csv": "read_csv({path}, header = true, auto_detect = true)",
    ".tsv": "read_csv({path}, header = true, auto_detect = true, delim = '\t')",
    ".parquet": "read_parquet({path})",
    ".jsonl": "read_json({path}, format = 'newline_delimited')",
    ".ndjson": "read_json({path}, format = 'newline_delimited')",
    ".json": "read_json({path})",
}

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclasses.dataclass(frozen=True, slots=True)
class OpenedSource:
    """A query callable over a confined source, and how to close it."""

    execute: Execute
    close: Callable[[], None]
    #: The SQL dialect the source speaks, which is what controls compile for.
    engine: str
    path: Path
    #: Tables a ``files`` source exposes, and anything in it that was skipped.
    tables: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise ValidationError(
            f"{path} is not a file",
            remedy="This kind of connection names one database file in config.path.",
            context={"path": str(path)},
        )


def _guarded(execute: Execute, batches: Any = None) -> Execute:
    """Only ever one read-only statement, whatever the control's text says."""

    def run(sql: str) -> list[dict[str, Any]]:
        return execute(sole_read_statement(sql))

    if batches is not None:

        def batched(sql: str, size: int) -> Iterator[list[dict[str, Any]]]:
            return batches(sole_read_statement(sql), size)  # type: ignore[no-any-return]

        setattr(run, "batches", batched)  # noqa: B010
    return run


def _duckdb_executor(connection: Any) -> tuple[Execute, Any]:
    def execute(sql: str) -> list[dict[str, Any]]:
        cursor = connection.execute(sql)
        names = [column[0] for column in cursor.description or ()]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    def batches(sql: str, size: int) -> Iterator[list[dict[str, Any]]]:
        cursor = connection.execute(sql)
        names = [column[0] for column in cursor.description or ()]
        while chunk := cursor.fetchmany(size):
            yield [dict(zip(names, row, strict=True)) for row in chunk]

    return execute, batches


def _fence(connection: Any, roots: Sequence[Path]) -> None:
    """Limit a DuckDB connection to *roots*, irrevocably for its lifetime."""
    listed = ", ".join(_literal(str(root) + "/") for root in roots)
    connection.execute(f"SET allowed_directories = [{listed}]")
    connection.execute("SET enable_external_access = false")


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _sqlite(
    path: Path,
    roots: Sequence[Path],  # noqa: ARG001 - the path check is the fence; SQLite reads one file
    config: dict[str, Any],  # noqa: ARG001 - the opener signature is shared
) -> OpenedSource:
    import sqlite3

    _require_file(path)
    # Not tied to the opening thread: a preview runs its query off the event
    # loop (`asyncio.to_thread`), and the default check refuses that outright.
    # One caller uses the connection at a time, and it is read-only.
    from prama_kernel import strict_sqlite

    # Strict: a misspelled column is an error, not a string (Q-08).
    connection = strict_sqlite.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    register_regexp(connection)

    def execute(sql: str) -> list[dict[str, Any]]:
        return [dict(row) for row in connection.execute(sql).fetchall()]

    def batches(sql: str, size: int) -> Iterator[list[dict[str, Any]]]:
        cursor = connection.execute(sql)
        while chunk := cursor.fetchmany(size):
            yield [dict(row) for row in chunk]

    return OpenedSource(_guarded(execute, batches), connection.close, "sqlite", path)


def _duckdb(
    path: Path,
    roots: Sequence[Path],
    config: dict[str, Any],  # noqa: ARG001 - the opener signature is shared
) -> OpenedSource:
    import duckdb

    _require_file(path)
    connection = duckdb.connect(str(path), read_only=True)
    try:
        _fence(connection, roots)
    except Exception:
        connection.close()
        raise
    execute, batches = _duckdb_executor(connection)
    return OpenedSource(_guarded(execute, batches), connection.close, "duckdb", path)


def _files(path: Path, roots: Sequence[Path], config: dict[str, Any]) -> OpenedSource:
    import duckdb

    if not path.is_dir():
        raise ValidationError(
            f"{path} is not a directory",
            remedy="A files connection names the directory its CSV, Parquet and JSON files are in.",
            context={"path": str(path)},
        )
    tables, skipped = _tables_in(path, config.get("tables") or {})
    connection = duckdb.connect(":memory:")
    try:
        for name, reader in tables.items():
            connection.execute(f'CREATE VIEW "{name}" AS SELECT * FROM {reader}')
        _fence(connection, roots)
    except Exception:
        connection.close()
        raise
    execute, batches = _duckdb_executor(connection)
    return OpenedSource(
        _guarded(execute, batches),
        connection.close,
        "duckdb",
        path,
        tables=tuple(sorted(tables)),
        skipped=tuple(skipped),
    )


def _tables_in(directory: Path, declared: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Each table a directory holds, as the DuckDB reader that reads it."""
    tables: dict[str, str] = {}
    skipped: list[str] = []
    if declared:
        for name, relative in declared.items():
            _identifier(str(name))
            target = str(relative)
            if Path(target).is_absolute() or ".." in Path(target).parts:
                raise ValidationError(
                    f"table {name!r} names {target!r}, which is not inside the connection",
                    remedy="Name files relative to the connection's directory, without '..'.",
                    context={"table": str(name), "path": target},
                )
            suffix = Path(target).suffix.lower()
            if suffix not in READERS:
                raise ValidationError(
                    f"table {name!r} names a {suffix or 'extension-less'} file",
                    remedy="Readable here: " + ", ".join(sorted(READERS)) + ".",
                    context={"table": str(name)},
                )
            tables[str(name)] = READERS[suffix].format(path=_literal(str(directory / target)))
        return tables, skipped
    for entry in sorted(directory.iterdir()):
        if entry.is_file():
            suffix = entry.suffix.lower()
            if suffix not in READERS:
                continue
            name, target = entry.stem, str(entry)
        elif entry.is_dir():
            kinds = sorted(
                {p.suffix.lower() for p in entry.iterdir() if p.is_file()} & set(READERS)
            )
            if len(kinds) != 1:
                if kinds:
                    skipped.append(f"{entry.name}: mixes {', '.join(kinds)}")
                continue
            suffix, name, target = kinds[0], entry.name, str(entry / f"*{kinds[0]}")
        else:
            continue
        if not _IDENTIFIER.match(name):
            skipped.append(f"{entry.name}: {name!r} is not a table name")
            continue
        if name in tables:
            skipped.append(f"{entry.name}: a second table called {name!r}")
            continue
        tables[name] = READERS[suffix].format(path=_literal(target))
    return tables, skipped


def _identifier(name: str) -> None:
    if not _IDENTIFIER.match(name):
        raise ValidationError(
            f"{name!r} is not a table name",
            remedy="Use letters, digits and underscores, starting with a letter.",
            context={"table": name},
        )


#: Source type to the function that opens it, confined.
OPENERS: dict[str, Callable[[Path, Sequence[Path], dict[str, Any]], OpenedSource]] = {
    "sqlite": _sqlite,
    "duckdb": _duckdb,
    "files": _files,
}


def open_confined(
    source_type: str,
    config: dict[str, Any],
    *,
    roots: Sequence[str | Path],
    forbidden: Sequence[str | Path] = (),
) -> OpenedSource:
    """Open a registered connection for a server-side run, or refuse and say why.

    *roots* are the directories a run may read; *forbidden* are files that must
    never be readable (Prama's own database). Every refusal names the setting
    that would change it, because "forbidden" with no remedy sends somebody to
    widen a permission they do not need.
    """
    opener = OPENERS.get(source_type)
    if opener is None:
        raise ValidationError(
            f"a server-side run cannot read a {source_type!r} connection",
            remedy=(
                "Supported here: " + ", ".join(sorted(OPENERS)) + ". Other sources run "
                "through an agent in their own zone, or `prama control run` on a host "
                "that can reach them."
            ),
            context={"source_type": source_type},
        )
    fenced = [Path(root).expanduser().resolve() for root in roots if str(root).strip()]
    if not fenced:
        raise ForbiddenError(
            "this server has no directories a run may read",
            remedy=(
                "An operator sets runs.roots in config/application.local.yaml to the "
                "directories that hold customer data. Until then no connection's files "
                "are opened by a run requested over the API."
            ),
        )
    for protected in (Path(p).expanduser().resolve() for p in forbidden if str(p).strip()):
        for root in fenced:
            if protected.is_relative_to(root):
                raise ForbiddenError(
                    f"runs.roots includes {root}, which holds Prama's own database",
                    remedy=(
                        "Keep customer data and Prama's store in separate directories, "
                        "and list only the customer's in runs.roots. A control able to "
                        "read the ledger it writes to is not a control."
                    ),
                    context={"root": str(root)},
                )
    # `path`, or `database_path` as the SQLite connection form writes it: a
    # connection made in the console must run like one made from the SDK.
    raw = str(config.get("path", "") or config.get("database_path", "") or "").strip()
    if not raw:
        raise ValidationError(
            "this connection names no path",
            remedy="Set config.path on the connection to the file or directory it reads.",
        )
    path = Path(raw).expanduser().resolve()
    if not any(path.is_relative_to(root) for root in fenced):
        raise ForbiddenError(
            f"{path} is outside the directories a run may read",
            remedy=(
                "Move the data under one of runs.roots, or have an operator add its "
                "directory there. A connection cannot widen what the server reads."
            ),
            context={"path": str(path)},
        )
    if not path.exists():
        raise ValidationError(
            f"there is nothing at {path}",
            remedy=(
                "Check the connection's config.path. A control cannot examine data "
                "that is not there."
            ),
            context={"path": str(path)},
        )
    try:
        return opener(path, fenced, config)
    except PramaError:
        raise
    except Exception as exc:
        raise ValidationError(
            f"{path} could not be opened as a {source_type} source",
            remedy="Check that the file is what the connection's source_type says it is.",
            context={"path": str(path), "detail": first_line(exc)},
            cause=exc,
        ) from exc


__all__ = ["OPENERS", "READERS", "OpenedSource", "open_confined"]

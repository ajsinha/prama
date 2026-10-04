"""Running the server's compiled SQL against a source only this machine can reach.

One executor per configured source, each **read-only by construction** rather
than by convention: SQLite is opened with ``mode=ro``, DuckDB with
``read_only=True``, PostgreSQL in a read-only session. An agent executes a query
somebody else compiled; if that somebody were ever wrong, or ever hostile, the
source still cannot be written through it.

SQLite is the standard library. DuckDB and PostgreSQL are optional extras
(``pip install prama-agent[duckdb]`` / ``[postgres]``); a source naming one that
is not installed fails when the executor is built, at start, with the command
that installs it — not at three in the morning on the first assignment.

A connection is opened per statement. An agent runs a few statements a minute,
and a connection that outlives a file being replaced or a database restarting
turns one bad night into a daemon that errors until somebody restarts it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from prama_kernel import strict_sqlite
from prama_kernel.agent.protocol import Assignment
from prama_kernel.errors import ConfigError, NotFoundError

from prama_agent.config import Source, canonical_engine

Rows = list[dict[str, Any]]


class SourceExecutor:
    """Runs SQL against one source. Callable, as the runner's `Executor` is."""

    engine = ""

    def __init__(self, source: Source) -> None:
        self.source = source

    def __call__(self, sql: str) -> Rows:
        return [row for batch in self.batches(sql, 10_000) for row in batch]

    def batches(self, sql: str, size: int) -> Iterator[Rows]:  # pragma: no cover - abstract
        raise NotImplementedError


class SqliteExecutor(SourceExecutor):
    engine = "sqlite"

    def batches(self, sql: str, size: int) -> Iterator[Rows]:
        path = Path(self.source.path)
        if not path.exists():
            # mode=ro would say "unable to open database file"; this says which.
            raise FileNotFoundError(f"the sqlite source {self.source.binding} has no file {path}")
        # Strict: a misspelled column is an error, not a string (Q-08).
        connection = strict_sqlite.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            cursor = connection.execute(sql)
            columns = [d[0] for d in cursor.description or ()]
            while chunk := cursor.fetchmany(size):
                yield [dict(zip(columns, row, strict=True)) for row in chunk]
        finally:
            connection.close()


class DuckdbExecutor(SourceExecutor):
    engine = "duckdb"

    def __init__(self, source: Source) -> None:
        super().__init__(source)
        self._duckdb = _optional("duckdb", "duckdb", source)

    def batches(self, sql: str, size: int) -> Iterator[Rows]:
        connection = self._duckdb.connect(self.source.path, read_only=True)
        try:
            cursor = connection.execute(sql)
            columns = [d[0] for d in cursor.description or ()]
            while chunk := cursor.fetchmany(size):
                yield [dict(zip(columns, row, strict=True)) for row in chunk]
        finally:
            connection.close()


class PostgresExecutor(SourceExecutor):
    engine = "postgres"

    def __init__(self, source: Source, environ: Mapping[str, str] | None = None) -> None:
        super().__init__(source)
        self._psycopg = _optional("psycopg", "postgres", source)
        self._environ = os.environ if environ is None else environ

    def _conninfo(self) -> tuple[str, dict[str, str]]:
        """The DSN and extra keywords, read from the environment at each use."""
        source = self.source
        if source.dsn_env:
            dsn = self._environ.get(source.dsn_env, "")
            if not dsn:
                raise ConfigError(
                    f"the postgres source {source.binding} reads its DSN from "
                    f"${source.dsn_env}, which is not set",
                    remedy=f"Set {source.dsn_env} in the service's environment.",
                    context={"binding": source.binding, "variable": source.dsn_env},
                )
            return dsn, {}
        extra: dict[str, str] = {}
        if source.password_env:
            password = self._environ.get(source.password_env, "")
            if not password:
                raise ConfigError(
                    f"the postgres source {source.binding} reads its password from "
                    f"${source.password_env}, which is not set",
                    remedy=f"Set {source.password_env} in the service's environment.",
                    context={"binding": source.binding, "variable": source.password_env},
                )
            extra["password"] = password
        return source.dsn, extra

    def batches(self, sql: str, size: int) -> Iterator[Rows]:
        dsn, extra = self._conninfo()
        with self._psycopg.connect(dsn, **extra) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute(sql)
                columns = [d.name for d in cursor.description or ()]
                while chunk := cursor.fetchmany(size):
                    yield [dict(zip(columns, row, strict=True)) for row in chunk]


_BY_ENGINE: dict[str, type[SourceExecutor]] = {
    "sqlite": SqliteExecutor,
    "duckdb": DuckdbExecutor,
    "postgres": PostgresExecutor,
}


def executor_for_source(source: Source) -> SourceExecutor:
    return _BY_ENGINE[source.engine](source)


class Executors:
    """Every configured source's executor, chosen by an assignment's binding."""

    def __init__(self, sources: tuple[Source, ...] | list[Source]) -> None:
        self._by_binding = {s.binding: executor_for_source(s) for s in sources}

    @classmethod
    def of(cls, executors: Mapping[str, SourceExecutor]) -> Executors:
        """Already built — for tests, and for an embedder with its own executors."""
        built = cls(())
        built._by_binding = dict(executors)
        return built

    def __call__(self, assignment: Assignment) -> SourceExecutor:
        """The executor for this assignment. Raises when this agent has no such source.

        By binding first, then by a source that lists the dataset. Never by
        guessing: running a query against the wrong database gives a verdict
        about the wrong data, which is worse than an error that says so.
        """
        found = self._by_binding.get(assignment.binding)
        if found is None:
            found = next(
                (e for e in self._by_binding.values() if assignment.dataset in e.source.datasets),
                None,
            )
        if found is None:
            raise NotFoundError(
                f"this agent has no source bound to {assignment.binding!r}",
                remedy=(
                    f"Add a source named {assignment.binding} to agent.yaml, or list "
                    f"{assignment.dataset} under an existing source's datasets."
                ),
                context={"binding": assignment.binding, "dataset": assignment.dataset},
            )
        if found.engine != canonical_engine(assignment.engine):
            raise NotFoundError(
                f"the source {found.source.binding} is {found.engine} and the assignment "
                f"was compiled for {assignment.engine}",
                remedy="Bind the dataset to a source of the engine it was compiled for.",
                context={"binding": found.source.binding, "engine": assignment.engine},
            )
        return found

    def __len__(self) -> int:
        return len(self._by_binding)


def _optional(module: str, extra: str, source: Source) -> Any:
    import importlib

    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ConfigError(
            f"the source {source.binding} is {source.engine}, and {module} is not installed "
            f"beside this agent",
            remedy=f"pip install 'prama-agent[{extra}]', or remove the source from agent.yaml.",
            context={"binding": source.binding, "engine": source.engine},
        ) from exc

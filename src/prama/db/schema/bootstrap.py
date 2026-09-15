"""Applying the authoritative schema.

``prama db init`` executes every statement in the schema file. All of them are
``IF NOT EXISTS``, so the operation is idempotent: running it against an empty
database creates the schema, and running it against a current one is a no-op.

What it does **not** do is alter anything. There are no migrations. If the live
database has a table this file does not describe, or a column with a different
shape, ``init`` leaves it alone and ``verify`` reports it. That is deliberate:
a tool that quietly reshapes a production database is a tool that can quietly
lose data.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import getpass
import socket

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from prama.core.clock import utc_now
from prama.core.errors import DatabaseError, first_line
from prama.core.log import get_logger
from prama.db.dialects import Dialect
from prama.db.schema.loader import SchemaFile, SchemaLoader
from prama.version import SCHEMA_VERSION, VERSION

_log = get_logger(__name__)


@dataclasses.dataclass(frozen=True, slots=True)
class BootstrapResult:
    """What ``init`` did, in terms an operator can act on."""

    dialect: str
    schema_path: str
    digest: str
    statements_executed: int
    tables_present: int
    created: bool

    def summary(self) -> str:
        verb = "created" if self.created else "already current"
        return (
            f"schema {verb}: {self.tables_present} tables, "
            f"{self.statements_executed} statements from {self.schema_path} "
            f"(digest {self.digest[:12]})"
        )


class SchemaBootstrapper:
    """Applies the authoritative schema file idempotently."""

    def __init__(self, dialect: Dialect, loader: SchemaLoader | None = None) -> None:
        self._dialect = dialect
        self._loader = loader or SchemaLoader()

    def apply(self, engine: Engine, *, applied_by: str | None = None) -> BootstrapResult:
        schema = self._loader.load(self._dialect.settings.schema_file)
        before = set(self._dialect.list_tables(engine))
        self._refuse_if_drifted(engine, schema)
        executed = self._execute(engine, schema)
        after = self._dialect.list_tables(engine)
        self._record_state(engine, schema, applied_by=applied_by)
        return BootstrapResult(
            dialect=self._dialect.name,
            schema_path=str(schema.path),
            digest=schema.digest,
            statements_executed=executed,
            tables_present=len(after),
            created=set(after) != before,
        )

    def _refuse_if_drifted(self, engine: Engine, schema: SchemaFile) -> None:
        """Stop before overwriting the record of what this database was built from.

        `_record_state` upserts unconditionally, so running `db init` against a
        database built from a different schema file re-stamped the new digest
        and the drift became invisible — the evidence erased by the command
        that was supposed to be safe (QA finding CLI-040).

        That is the hard rule in CLAUDE.md, inverted: "a live schema that has
        drifted is a loud failure, never a silent migration." The DDL here is
        idempotent, so applying a changed file does not alter an existing
        table; the database stays as it was and only the digest moves. Which
        means the stamp claimed a match that had not happened.

        Missing row, or an equal digest, is the ordinary case and passes
        through. `db verify` is the command for seeing *what* differs; this one
        only has to refuse to pretend nothing does.
        """
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT file_digest FROM schema_state WHERE id = 1")
                ).first()
        except SQLAlchemyError:
            # No schema_state table yet: this is a first initialisation, which
            # is the whole point of the command.
            return
        if row is None or not row[0] or row[0] == schema.digest:
            return
        raise DatabaseError(
            "this database was built from a different schema file",
            remedy=(
                "Run `prama db verify` to see what differs. The schema files are "
                "the authority and there are no migrations, so a database that no "
                "longer matches one is restored from backup or rebuilt — not "
                "re-stamped. Applying the file again would not alter the existing "
                "tables; it would only overwrite the record of what they came from."
            ),
            context={
                "recorded_digest": str(row[0])[:12],
                "file_digest": schema.digest[:12],
                "schema_path": str(schema.path),
            },
        )

    def _execute(self, engine: Engine, schema: SchemaFile) -> int:
        executed = 0
        with engine.begin() as conn:
            for statement in schema.statements:
                try:
                    conn.execute(text(statement))
                    executed += 1
                except SQLAlchemyError as exc:
                    raise DatabaseError(
                        f"schema statement failed on {self._dialect.name}",
                        code="DB.SCHEMA_APPLY_FAILED",
                        remedy=(
                            "The statement below could not be applied. Prama does not "
                            "migrate: fix the database or the schema file, then re-run "
                            "`prama db init`."
                        ),
                        context={
                            "statement": statement[:300],
                            "detail": first_line(exc),
                        },
                        cause=exc,
                    ) from exc
        _log.info("applied %d schema statements for %s", executed, self._dialect.name)
        return executed

    def _record_state(self, engine: Engine, schema: SchemaFile, *, applied_by: str | None) -> None:
        """Stamp the digest of the file that was applied.

        This is drift *detection*, not migration history: exactly one row, always
        overwritten, describing what this database was last built from.
        """
        who = applied_by or f"{_current_user()}@{socket.gethostname()}"
        statement = self._dialect.upsert(
            "schema_state",
            [
                "id",
                "schema_version",
                "dialect",
                "file_digest",
                "applied_at",
                "applied_by",
                "product_version",
            ],
            ["id"],
        )
        with engine.begin() as conn:
            conn.execute(
                text(statement),
                {
                    "id": 1,
                    "schema_version": SCHEMA_VERSION,
                    "dialect": self._dialect.name,
                    "file_digest": schema.digest,
                    "applied_at": utc_now()
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z"),
                    "applied_by": who,
                    "product_version": VERSION,
                },
            )


def _current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"

"""Verifying the live database against the authoritative schema file.

This is what replaces migrations. Rather than a chain of edits whose net effect
nobody can state, Prama holds one description of the schema and checks reality
against it. Drift is **reported, never repaired**: a live database that has
diverged is a fact an operator must decide about, and a tool that silently
reshapes it can silently lose data.

Verification is intentionally strict about the things that change behaviour —
missing tables, missing columns, a column that has become nullable — and
tolerant about the things that do not, such as extra indexes an operator added
for their own workload.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from prama.core.errors import SchemaDriftError
from prama.db.dialects import Dialect
from prama.db.schema.loader import SchemaLoader
from prama.version import SCHEMA_VERSION


class DriftKind(enum.Enum):
    MISSING_TABLE = "missing_table"
    MISSING_COLUMN = "missing_column"
    NULLABILITY = "nullability"
    MISSING_INDEX = "missing_index"
    EXTRA_TABLE = "extra_table"
    DIGEST = "digest"
    VERSION = "version"


#: Drift that makes the database unsafe to use, versus drift that is only
#: informational. An operator's own extra index is not a defect.
BLOCKING: frozenset[DriftKind] = frozenset(
    {
        DriftKind.MISSING_TABLE,
        DriftKind.MISSING_COLUMN,
        DriftKind.NULLABILITY,
        DriftKind.VERSION,
    }
)


@dataclasses.dataclass(frozen=True, slots=True)
class Drift:
    kind: DriftKind
    object_name: str
    detail: str

    @property
    def blocking(self) -> bool:
        return self.kind in BLOCKING

    def __str__(self) -> str:
        mark = "!" if self.blocking else "-"
        return f"  {mark} [{self.kind.value}] {self.object_name}: {self.detail}"


@dataclasses.dataclass(frozen=True, slots=True)
class VerificationReport:
    dialect: str
    schema_path: str
    expected_digest: str
    recorded_digest: str | None
    drifts: tuple[Drift, ...]

    @property
    def blocking_drifts(self) -> tuple[Drift, ...]:
        return tuple(d for d in self.drifts if d.blocking)

    @property
    def ok(self) -> bool:
        return not self.blocking_drifts

    def summary(self) -> str:
        if not self.drifts:
            return (
                f"schema verified against {self.schema_path} "
                f"(digest {self.expected_digest[:12]}): no drift"
            )
        lines = [
            f"schema drift against {self.schema_path} "
            f"({len(self.blocking_drifts)} blocking, "
            f"{len(self.drifts) - len(self.blocking_drifts)} informational):"
        ]
        lines.extend(str(d) for d in self.drifts)
        return "\n".join(lines)

    def raise_if_blocking(self) -> None:
        if self.ok:
            return
        raise SchemaDriftError(
            f"the live {self.dialect} database does not match {self.schema_path}",
            remedy=(
                "Prama has no migrations. Either run `prama db init` (safe: it only "
                "creates missing objects), or reconcile the database with the schema "
                "file deliberately. Nothing will be altered automatically."
            ),
            context={
                "dialect": self.dialect,
                "schema": self.schema_path,
                "blocking": [f"{d.kind.value}:{d.object_name}" for d in self.blocking_drifts],
            },
        )


class SchemaVerifier:
    """Compares a live database with its authoritative schema file."""

    def __init__(self, dialect: Dialect, loader: SchemaLoader | None = None) -> None:
        self._dialect = dialect
        self._loader = loader or SchemaLoader()

    def verify(self, engine: Engine) -> VerificationReport:
        schema = self._loader.load(self._dialect.settings.schema_file)
        live_tables = set(self._dialect.list_tables(engine))
        drifts: list[Drift] = []

        for table in schema.tables:
            if table.name not in live_tables:
                drifts.append(
                    Drift(
                        DriftKind.MISSING_TABLE, table.name, "declared in the schema file, absent"
                    )
                )
                continue
            live_columns = self._dialect.list_columns(engine, table.name)
            for column in table.columns:
                live = live_columns.get(column.name)
                if live is None:
                    drifts.append(
                        Drift(
                            DriftKind.MISSING_COLUMN,
                            f"{table.name}.{column.name}",
                            f"declared {column.type}, absent",
                        )
                    )
                elif live["nullable"] and not column.nullable:
                    drifts.append(
                        Drift(
                            DriftKind.NULLABILITY,
                            f"{table.name}.{column.name}",
                            "declared NOT NULL, live column is nullable",
                        )
                    )
            live_indexes = set(self._dialect.list_indexes(engine, table.name))
            for index in table.indexes:
                if index not in live_indexes:
                    drifts.append(
                        Drift(DriftKind.MISSING_INDEX, index, f"declared on {table.name}, absent")
                    )

        for extra in sorted(live_tables - set(schema.table_names)):
            drifts.append(
                Drift(
                    DriftKind.EXTRA_TABLE, extra, "present in the database, not in the schema file"
                )
            )

        recorded_digest, recorded_version = self._recorded_state(engine)
        if recorded_version is not None and recorded_version != SCHEMA_VERSION:
            drifts.append(
                Drift(
                    DriftKind.VERSION,
                    "schema_state",
                    f"database built for schema version {recorded_version}, "
                    f"this build expects {SCHEMA_VERSION}",
                )
            )
        if recorded_digest is not None and recorded_digest != schema.digest:
            drifts.append(
                Drift(
                    DriftKind.DIGEST,
                    "schema_state",
                    f"applied digest {recorded_digest[:12]} differs from the current file "
                    f"({schema.digest[:12]}); re-run `prama db init` to re-apply",
                )
            )

        return VerificationReport(
            dialect=self._dialect.name,
            schema_path=str(schema.path),
            expected_digest=schema.digest,
            recorded_digest=recorded_digest,
            drifts=tuple(drifts),
        )

    def _recorded_state(self, engine: Engine) -> tuple[str | None, str | None]:
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT file_digest, schema_version FROM schema_state WHERE id = 1")
                ).first()
        except SQLAlchemyError:
            return None, None  # table absent: an unbootstrapped database
        return (row[0], row[1]) if row else (None, None)

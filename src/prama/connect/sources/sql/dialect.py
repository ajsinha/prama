"""What actually differs between one SQL source and the next.

Most of reading a relational source is the same everywhere: list the objects,
describe the columns, take a snapshot, page through the rows. The parts that
genuinely differ are small and specific — how an identifier is quoted, where the
catalogue lives, whether a cheap row estimate exists, how to ask for a sample,
and what constitutes a point-in-time marker.

Separating those out is what makes the difference between one connector per
database and one *dialect* per database. It also keeps the honest answer
available: a dialect that has no real sampling clause says so, and the base
connector degrades to something slower rather than quietly returning the first
n rows and calling it a sample.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from prama.connect.capability import CapabilityMatrix, PushdownFeature
from prama.connect.spi import SamplePlan, SamplingStrategy, SnapshotKind

#: A catalogue query returns rows of (schema, name, kind, rows, bytes, comment).
CatalogueRow = tuple[str, str, str, int | None, int | None, str]
#: A column query returns rows of (name, type, nullable, ordinal, comment,
#: precision, scale).
ColumnRow = tuple[str, str, bool, int, str, int | None, int | None]


class SqlDialect(ABC):
    """The database-specific half of a SQL connector."""

    #: Identifies the dialect in errors and evidence.
    name: str = "sql"
    #: What this source can be asked to do. Claiming a capability the source
    #: lacks produces a control that compiles and then fails at the source,
    #: which is worse than not having the capability at all.
    capabilities: CapabilityMatrix = CapabilityMatrix.of(
        PushdownFeature.SQL,
        PushdownFeature.FILTER,
        PushdownFeature.AGGREGATION,
        PushdownFeature.PREDICATE_PUSHDOWN,
    )
    #: The best point-in-time marker this source can offer.
    snapshot_kind: SnapshotKind = SnapshotKind.WALL_CLOCK
    #: Whether the catalogue can give a row count without scanning. On a large
    #: table the difference between an estimate and a count is the difference
    #: between discovery taking a second and taking an hour.
    has_cheap_row_estimate: bool = False
    #: Whether a genuine sampling clause exists. When it does not, the base
    #: connector reports the sample as approximate rather than pretending.
    has_native_sampling: bool = False
    #: Placeholder style. ``$n`` for asyncpg, ``?`` for most DB-API drivers.
    positional_placeholder: str = "$"

    # -- identifiers -------------------------------------------------------

    def quote(self, identifier: str) -> str:
        """Quote an identifier, doubling any embedded quote character.

        Not decoration: object names arrive from a catalogue that a customer
        controls, and they reach a query string. Quoting them properly is the
        boundary that keeps a table named ``x"; DROP TABLE y --`` inert.
        """
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    def qualify(self, path: tuple[str, ...]) -> str:
        return ".".join(self.quote(part) for part in path)

    def placeholder(self, index: int) -> str:
        return f"${index}" if self.positional_placeholder == "$" else "?"

    # -- catalogue ---------------------------------------------------------

    @abstractmethod
    def list_objects_sql(self, *, include_views: bool) -> str:
        """Return SQL yielding :data:`CatalogueRow` tuples."""

    @abstractmethod
    def describe_sql(self) -> str:
        """Return SQL yielding :data:`ColumnRow` tuples for one object.

        Takes the schema and object name as the first two placeholders.
        """

    def count_sql(self, path: tuple[str, ...]) -> str:
        return f"SELECT count(*) FROM {self.qualify(path)}"

    def estimate_rows_sql(self) -> str | None:
        """SQL for a catalogue row estimate, taking schema and name.

        ``None`` means this source cannot estimate without scanning, and the
        honest answer is then "unknown" rather than a count nobody asked for.
        """
        return None

    def snapshot_sql(self) -> str | None:
        """SQL returning one point-in-time identifier, if the source has one."""
        return None

    # -- reading -----------------------------------------------------------

    def select_sql(self, path: tuple[str, ...], plan: SamplePlan, limit: int, offset: int) -> str:
        """The query that reads one page.

        Offset paging is the portable default and is deliberately not the only
        option: on a large table it degrades quadratically, so dialects that can
        stream server-side override this and the base connector prefers that.
        """
        table = self.qualify(path)
        if plan.strategy in (SamplingStrategy.FULL, SamplingStrategy.HEAD):
            return f"SELECT * FROM {table} LIMIT {limit} OFFSET {offset}"
        return f"{self.sample_from(path, plan)} LIMIT {limit} OFFSET {offset}"

    def sample_from(self, path: tuple[str, ...], plan: SamplePlan) -> str:  # noqa: ARG002
        """A sampled scan, or an honest ordinary one when sampling is absent."""
        return f"SELECT * FROM {self.qualify(path)}"

    def stream_sql(self, path: tuple[str, ...], plan: SamplePlan) -> str:
        """The whole read as one statement, for drivers that stream results."""
        if plan.strategy in (SamplingStrategy.FULL, SamplingStrategy.HEAD):
            return f"SELECT * FROM {self.qualify(path)}"
        return self.sample_from(path, plan)

    # -- session -----------------------------------------------------------

    def session_setup_sql(self, *, statement_timeout_ms: int) -> tuple[str, ...]:  # noqa: ARG002
        """Statements run once per connection, before anything is read.

        This is where read-only mode and a statement timeout are imposed. Both
        matter more than they look: Prama points at production systems, and the
        guarantee that it cannot write, and cannot pin a database with a runaway
        scan, should be enforced by the server rather than by our good manners.
        """
        return ()


class GenericSqlDialect(SqlDialect):
    """ANSI-ish defaults for sources reached over ODBC, JDBC or a DB-API driver.

    Claims little: standard information_schema, no cheap row estimate, no
    sampling clause, no snapshot. A source that can do better gets its own
    dialect; this one exists so that reaching an unfamiliar database is possible
    at all, with its limits stated rather than discovered in production.
    """

    name = "generic-sql"
    positional_placeholder = "?"

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "('BASE TABLE', 'VIEW')" if include_views else "('BASE TABLE')"
        return (
            "SELECT table_schema, table_name, table_type, NULL, NULL, '' "
            "FROM information_schema.tables "
            f"WHERE table_type IN {kinds} "
            "AND table_schema NOT IN ('information_schema', 'pg_catalog', 'sys') "
            "ORDER BY table_schema, table_name"
        )

    def describe_sql(self) -> str:
        return (
            "SELECT column_name, data_type, is_nullable, ordinal_position, '', "
            "numeric_precision, numeric_scale "
            "FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? "
            "ORDER BY ordinal_position"
        )

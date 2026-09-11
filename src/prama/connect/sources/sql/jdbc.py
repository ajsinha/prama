"""Any JDBC-reachable database, through its own driver.

The source of last resort, and the one that makes the estate reachable: an
Oracle, a DB2, a Sybase, a Teradata, an SQL Server. Prama cannot redistribute
those drivers and does not try — the deployment supplies the jar.

Four things this connector insists on, and the first is the reason it exists at
all rather than being a thin wrapper.

**Exact numbers stay exact.** JayDeBeApi's own converter calls
``BigDecimal.doubleValue()`` on any scaled decimal, so ``numeric(38,12)`` arrives
as a float and 1953193.464900000000 becomes a value that rounds differently. In
a data quality product that is disqualifying: it is the same double-rounding
that once reported 131 rows of a clean blotter as a cent out. The converter is
replaced with one that reads the BigDecimal's own string, so a decimal column
arrives as :class:`decimal.Decimal` and money survives the journey.

**The placeholder style belongs to the driver, not the database.** PostgreSQL's
own dialect writes ``$1`` because that is what asyncpg wants; every JDBC driver
wants ``?``. So the dialect a JDBC connection is told to use is wrapped, and the
wrapper overrides that one property. Without it a catalogue query binds nothing
and the driver reports "column index out of range", which is a long way from
"your placeholder style is wrong".

**JDBC is a transport, not a dialect.** The same wire protocol fronts a dozen
databases whose SQL differs, so the connector must be *told* which dialect to
compile for and **refuses** when it is not. Guessing would send PostgreSQL SQL
to an Oracle and produce a control that compiles and fails at the source, which
is worse than not having the source.

**Every call runs on one dedicated thread, and it is not an optimisation.**
Two constraints meet here. JPype requires a thread to be *attached* to the JVM
before it may touch Java, and an unattached thread from a shared pool does not
raise — it deadlocks. And a JDBC ``Connection`` is not thread-safe, so a pool
would be wrong even if attachment were free. One thread per connector satisfies
both, and the thread detaches from the JVM on close: JPype's shutdown waits for
attached threads, so a thread that never detaches hangs the interpreter at exit
rather than anywhere a stack trace would help.

**The JVM starts once per process and cannot be restarted.** That is JPype's
constraint, not a choice: a second start in the same process fails, so the
classpath is fixed the first time any JDBC connector opens. A deployment reading
two databases through two drivers must name both jars.

**The driver is somebody else's code running in our process.** It is named in
configuration, loaded from a path the deployment controls, and never fetched.
`prama bundle sbom` will not see it, and that is stated here rather than
discovered during an audit.

Needs the ``jdbc`` extra **and** a Java runtime.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import decimal
from collections.abc import AsyncIterator
from typing import Any

from prama.connect.sources.sql.base import SqlConnector
from prama.connect.sources.sql.dialect import GenericSqlDialect, SqlDialect
from prama.connect.spi import ConnectorError, SourceKind
from prama.core.concurrency import DedicatedThread
from prama.core.registry import PluginManifest

__all__ = ["CAPABILITIES", "DIALECTS", "JdbcConnector"]

#: What a JDBC source is assumed to do. Deliberately modest: the transport says
#: nothing about the engine, and the dialect the deployment names narrows it.
#: Claiming a capability the database lacks produces a control that compiles and
#: then fails at the source.
CAPABILITIES = GenericSqlDialect().capabilities


def _dialects() -> dict[str, SqlDialect]:
    """Dialects a JDBC connection may be told it is talking to.

    Built from the dialects Prama already has rather than from a list typed
    here — a second list would name a dialect that had been renamed.
    """
    from prama.connect.sources.sql.postgres import PostgresDialect

    known: dict[str, SqlDialect] = {
        "generic": GenericSqlDialect(),
        "postgresql": PostgresDialect(),
    }
    return known


DIALECTS = tuple(sorted(_dialects()))


class JdbcConnector(SqlConnector):
    """A database reached over JDBC, with its dialect named in configuration."""

    plugin_key = "jdbc"
    source_kind = SourceKind.RELATIONAL
    credential_field = "password"
    #: Replaced in __init__ from configuration. The class attribute exists only
    #: so the base class has something before construction; every instance must
    #: be told, and one that is not refuses to open.
    dialect: SqlDialect = GenericSqlDialect()

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.describe_manifest(
            key="jdbc",
            display_name="Any JDBC database",
            capabilities=CAPABILITIES.to_capabilities(),
            description=(
                "A database reached through its own JDBC driver — Oracle, DB2, SQL "
                "Server, Teradata. The driver jar is supplied by the deployment; "
                "Prama does not redistribute one. Exact decimals arrive as decimals, "
                "which the usual Python JDBC bridge does not manage."
            ),
        )

    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._url = str(self.config.get("jdbc_url", ""))
        self._driver_class = str(self.config.get("driver_class", ""))
        self._driver_path = str(self.config.get("driver_path", ""))
        self._user = str(self.config.get("user", ""))
        self._password = str(self.config.get("password", ""))
        self._dialect_name = str(self.config.get("dialect", ""))
        self._fetch_size = int(self.config.get("fetch_size", 5000))
        self._connection: Any = None
        self._stream_columns: tuple[str, ...] = ()
        #: One thread, for the whole life of this connector. See the module
        #: docstring: a shared pool deadlocks on JVM attachment and would be
        #: wrong anyway, because a JDBC Connection is not thread-safe.
        self._worker: DedicatedThread | None = None
        if self._dialect_name:
            self.dialect = self._resolve_dialect(self._dialect_name)

    @staticmethod
    def _resolve_dialect(name: str) -> SqlDialect:
        known = _dialects()
        dialect = known.get(name.lower())
        if dialect is None:
            raise ConnectorError(
                f"no dialect called {name!r}",
                code="CONNECT.UNKNOWN_DIALECT",
                remedy=(
                    f"One of: {', '.join(sorted(known))}. JDBC is a transport and "
                    "not a dialect — the same protocol fronts a dozen databases "
                    "whose SQL differs, so Prama has to be told which."
                ),
                context={"dialect": name},
            )
        return _as_jdbc(dialect)

    # -- lifecycle ---------------------------------------------------------

    async def open(self) -> None:
        if not self._dialect_name:
            raise ConnectorError(
                "a JDBC source must say which dialect it is",
                code="CONNECT.NO_DIALECT",
                remedy=(
                    f"Set `dialect` to one of: {', '.join(DIALECTS)}. Guessing would "
                    "send one database's SQL to another and produce a control that "
                    "compiles and then fails at the source."
                ),
            )
        for field, what in (
            (self._url, "jdbc_url"),
            (self._driver_class, "driver_class"),
            (self._driver_path, "driver_path"),
        ):
            if not field:
                raise ConnectorError(
                    f"a JDBC source needs {what}",
                    code="CONNECT.INCOMPLETE",
                    remedy=(
                        "A JDBC connection is a URL, a driver class and the jar that "
                        "provides it. Prama does not ship drivers and will not fetch "
                        "one."
                    ),
                )

        bridge = self._bridge()
        _use_exact_decimals(bridge)
        self._worker = DedicatedThread(name=f"jdbc-{self._dialect_name}")
        self._connection = await self._call(
            bridge.connect,
            self._driver_class,
            self._url,
            [self._user, self._password],
            self._driver_path,
        )

    async def close(self) -> None:
        if self._connection is not None:
            connection = self._connection
            self._connection = None
            await self._call(connection.close)
        if self._worker is not None:
            # Detaching runs on the worker itself. JPype's shutdown waits for
            # every attached thread, so one that never detaches hangs the
            # interpreter at exit — a long way from anything explanatory.
            worker, self._worker = self._worker, None
            await worker.close(teardown=_detach_from_jvm)

    async def _call(self, function: Any, *arguments: Any) -> Any:
        """Run one piece of JDBC work on this connector's own thread."""
        if self._worker is None:
            raise ConnectorError(
                "the JDBC connector was used before it was opened",
                code="CONNECT.NOT_OPEN",
                remedy="Use the connector as an async context manager, or call open() first.",
            )
        return await self._worker.call(function, *arguments)

    # -- the three the base needs ------------------------------------------

    async def _fetch(self, sql: str, *params: Any) -> list[tuple[Any, ...]]:
        def run() -> list[tuple[Any, ...]]:
            cursor = self._require().cursor()
            try:
                cursor.execute(sql, list(params) if params else None)
                if cursor.description is None:
                    # A statement that produced no result set at all, which the
                    # bridge raises on rather than returning nothing. Distinct
                    # from a query that matched no rows, and both are legitimate
                    # answers to "run this and give me the rows".
                    return []
                return [tuple(row) for row in cursor.fetchall()]
            finally:
                cursor.close()

        rows: list[tuple[Any, ...]] = await self._call(run)
        return rows

    async def _stream(self, sql: str, batch_rows: int) -> AsyncIterator[list[tuple[Any, ...]]]:
        """Page through a server-side cursor.

        `fetchmany` rather than `fetchall`, and the JDBC fetch size set on the
        statement: without both, the driver materialises the whole result set in
        the JVM heap and a table read fails on memory rather than on anything to
        do with data.
        """
        cursor = await self._call(self._require().cursor)
        try:
            await self._call(cursor.execute, sql)
            self._stream_columns = tuple(
                str(description[0]) for description in (cursor.description or ())
            )
            while True:
                rows = await self._call(cursor.fetchmany, batch_rows)
                if not rows:
                    return
                yield [tuple(row) for row in rows]
        finally:
            await self._call(cursor.close)

    def _column_names(self) -> tuple[str, ...]:
        return self._stream_columns

    # -- plumbing ----------------------------------------------------------

    def _require(self) -> Any:
        if self._connection is None:
            raise ConnectorError(
                "the JDBC connector was used before it was opened",
                code="CONNECT.NOT_OPEN",
                remedy="Use the connector as an async context manager, or call open() first.",
            )
        return self._connection

    @staticmethod
    def _bridge() -> Any:
        try:
            import jaydebeapi
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ConnectorError(
                "the JDBC bridge is not installed",
                code="CONNECT.DRIVER_MISSING",
                remedy=(
                    'Install Prama\'s jdbc extra: pip install "prama[jdbc]". It also '
                    "needs a Java runtime on the host."
                ),
            ) from exc
        return jaydebeapi


def _as_jdbc(dialect: SqlDialect) -> SqlDialect:
    """The same dialect, speaking the driver's placeholder style.

    Copied rather than mutated: the dialect instances are shared, and setting
    the attribute in place would change how the native PostgreSQL connector
    binds its parameters.
    """
    import copy

    wrapped = copy.copy(dialect)
    wrapped.positional_placeholder = "?"
    return wrapped


def _detach_from_jvm() -> None:
    """Let go of the JVM from this thread, if it ever took hold."""
    try:
        import jpype
    except ImportError:  # pragma: no cover - the extra is absent
        return
    if jpype.isJVMStarted() and jpype.java.lang.Thread.isAttached():
        jpype.java.lang.Thread.detach()


def _exact_decimal_converter() -> Any:
    """Read a BigDecimal as its own string, not as a double.

    The library's converter calls ``doubleValue()`` for any scale other than
    zero, so ``numeric(38,12)`` arrives as a float. That is the exact
    double-rounding this codebase has already been bitten by once, and in a
    product whose job is to notice when money is wrong it is not a trade-off.
    """

    def to_py(rs: Any, col: Any) -> Any:
        value = rs.getObject(col)
        if value is None:
            return None
        try:
            return decimal.Decimal(str(value.toString()))
        except (AttributeError, decimal.InvalidOperation):
            # Not a BigDecimal after all. Better to hand back what arrived than
            # to invent a number from something that is not one.
            return value

    return to_py


#: Set once. The bridge keeps converters in a module-level table, so replacing
#: them per connection would be the same work repeated and a race between two
#: connectors opening at once.
_CONVERTERS_REPLACED = False


def _use_exact_decimals(bridge: Any) -> None:
    """Install the exact-decimal converter, in both places it can live.

    The bridge snapshots ``_DEFAULT_CONVERTERS`` into a second table keyed by
    java.sql.Types constants the first time a JVM starts. Replacing only the
    defaults therefore works when Prama opens the first connection and silently
    does nothing when something else did — a race whose symptom is money
    arriving as a float on some runs and not others, which is close to
    undebuggable.
    """
    global _CONVERTERS_REPLACED
    if _CONVERTERS_REPLACED:
        return
    converter = _exact_decimal_converter()
    for sql_type in ("NUMERIC", "DECIMAL"):
        bridge._DEFAULT_CONVERTERS[sql_type] = converter

    built = getattr(bridge, "_converters", None)
    if built:
        import jpype

        for sql_type in ("NUMERIC", "DECIMAL"):
            constant = getattr(jpype.java.sql.Types, sql_type, None)
            if constant is not None and constant in built:
                built[constant] = converter
    _CONVERTERS_REPLACED = True

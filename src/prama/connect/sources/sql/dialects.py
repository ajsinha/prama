"""Dialects for the databases a bank actually runs, reached over JDBC.

Oracle, SQL Server, DB2, Teradata and MySQL do not need five connectors. They
need five *dialects* on the transport :mod:`prama.connect.sources.sql.jdbc`
already provides — which is the whole reason the SQL connector was split into
choreography and dialect in the first place. A new enterprise database is a
catalogue query, a snapshot expression and a quoting rule, not another copy of
health, discovery, paging and budgeting with its own subtly different idea of
what a sample is.

**What is verified and what is not.** The transport is verified: JDBC is
exercised against a live database, and MySQL below is exercised against a live
MySQL 8.4 over Connector/J. The other four dialects are written from each
vendor's documented behaviour and **no Oracle, SQL Server, DB2 or Teradata has
answered them**. They are a starting point that will need a first run, and each
says so in its own docstring rather than in a footnote here.

That distinction is worth holding on to. The risky part of a new source is
usually the transport — connection lifecycle, threading, type fidelity, paging —
and that part is shared and tested. What remains per dialect is SQL, which is
wrong in ways a first run finds in minutes rather than in ways that corrupt
evidence quietly.

Three things recur and each is a real difference rather than syntax.

**Snapshots.** Oracle's SCN and DB2's commit sequence are genuinely exact: a
control can be replayed against the data it actually read. SQL Server's LSN is
too. Teradata and MySQL have no cheap statement-level marker, so they say
wall-clock and admit it is not a point in time. An evidence record carries that
flag and deterministic replay depends on it.

**Row estimates.** Every one of these keeps approximate row counts in its
catalogue, and every one of them is free. `count(*)` on a Teradata fact table is
not.

**Identifier folding.** Oracle and DB2 fold unquoted names to upper case, MySQL
folds to lower on some platforms and preserves on others, SQL Server preserves.
Quoting everything with the catalogue's own spelling is the only rule that is
correct on all of them.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.connect.capability import CapabilityMatrix, PushdownFeature
from prama.connect.sources.sql.dialect import SqlDialect
from prama.connect.spi import SamplePlan, SamplingStrategy, SnapshotKind

__all__ = [
    "BigQueryDialect",
    "DatabricksDialect",
    "Db2Dialect",
    "MySqlDialect",
    "OracleDialect",
    "RedshiftDialect",
    "SqlServerDialect",
    "SynapseDialect",
    "TeradataDialect",
    "TrinoDialect",
]

#: What a mature relational engine can be asked to do. Narrower than a
#: warehouse's: no dialect here claims approximate-distinct or quantile
#: pushdown, because support varies by version and claiming a capability the
#: source lacks produces a control that compiles and then fails at the source.
ENTERPRISE = CapabilityMatrix.of(
    PushdownFeature.SQL,
    PushdownFeature.FILTER,
    PushdownFeature.AGGREGATION,
    PushdownFeature.PREDICATE_PUSHDOWN,
    PushdownFeature.REGEX,
    PushdownFeature.WINDOW,
)


class _JdbcDialect(SqlDialect):
    """What every dialect reached over JDBC shares."""

    capabilities = ENTERPRISE
    #: Every JDBC driver binds with `?`. The style belongs to the driver, not
    #: the database — the same PostgreSQL is reachable through both asyncpg
    #: (`$1`) and JDBC.
    positional_placeholder = "?"
    has_cheap_row_estimate = True

    def quote(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'


class OracleDialect(_JdbcDialect):
    """Oracle 11g to 23ai. **Never run against an Oracle.**

    The SCN is the reason Oracle is worth doing properly: with flashback query
    a control can be re-executed against the exact data it read, which is what
    deterministic replay has always wanted and what most sources cannot give.
    """

    name = "oracle"
    #: Exact: `AS OF SCN` returns the database as it was.
    snapshot_kind = SnapshotKind.SCN
    has_native_sampling = True

    def list_objects_sql(self, *, include_views: bool) -> str:
        # ALL_TABLES rather than DBA_TABLES: a read-only account usually cannot
        # see DBA_ views, and failing on privilege at discovery is a worse first
        # experience than seeing only what the account may read anyway.
        tables = """
            SELECT t.owner, t.table_name, 'table',
                   t.num_rows, t.blocks * 8192,
                   COALESCE(c.comments, ' ')
            FROM all_tables t
            LEFT JOIN all_tab_comments c
              ON c.owner = t.owner AND c.table_name = t.table_name
            WHERE t.owner NOT IN ('SYS','SYSTEM','SYSAUX','OUTLN','DBSNMP')
        """
        if not include_views:
            return tables + " ORDER BY t.num_rows DESC NULLS LAST"
        return (
            tables
            + """
            UNION ALL
            SELECT v.owner, v.view_name, 'view', NULL, NULL, ' '
            FROM all_views v
            WHERE v.owner NOT IN ('SYS','SYSTEM','SYSAUX','OUTLN','DBSNMP')
            """
        )

    def describe_sql(self) -> str:
        return f"""
            SELECT c.column_name,
                   LOWER(c.data_type),
                   CASE WHEN c.nullable = 'Y' THEN 1 ELSE 0 END,
                   c.column_id,
                   COALESCE(m.comments, ' '),
                   c.data_precision,
                   c.data_scale
            FROM all_tab_columns c
            LEFT JOIN all_col_comments m
              ON m.owner = c.owner AND m.table_name = c.table_name
             AND m.column_name = c.column_name
            WHERE c.owner = {self.placeholder(1)} AND c.table_name = {self.placeholder(2)}
            ORDER BY c.column_id
        """

    def estimate_rows_sql(self) -> str | None:
        """From the optimiser's statistics, which may be stale and are free.

        A stale estimate is the right answer here: discovery is deciding what to
        show a person, not computing a metric, and a `count(*)` across a
        production Oracle is how a data quality tool becomes the thing the DBA
        blames.
        """
        return f"""
            SELECT num_rows FROM all_tables
            WHERE owner = {self.placeholder(1)} AND table_name = {self.placeholder(2)}
        """

    def snapshot_sql(self) -> str | None:
        return "SELECT CURRENT_SCN FROM V$DATABASE"

    def sample_from(self, path: tuple[str, ...], plan: SamplePlan) -> str:
        table = self.qualify(path)
        if plan.fraction is not None:
            return f"SELECT * FROM {table} SAMPLE ({max(0.000001, plan.fraction * 100):g})"
        return f"SELECT * FROM {table}"

    def select_sql(self, path: tuple[str, ...], plan: SamplePlan, limit: int, offset: int) -> str:
        """`OFFSET … FETCH NEXT`, which Oracle has had since 12c.

        `ROWNUM` paging is the older idiom and is wrong in a way that is easy to
        miss: `ROWNUM <= n` is evaluated before ORDER BY, so a paged read
        returns an arbitrary page rather than the one asked for.
        """
        base = (
            f"SELECT * FROM {self.qualify(path)}"
            if plan.strategy in (SamplingStrategy.FULL, SamplingStrategy.HEAD)
            else self.sample_from(path, plan)
        )
        return f"{base} OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"

    def session_setup_sql(self, *, statement_timeout_ms: int) -> tuple[str, ...]:  # noqa: ARG002
        """Isolation only.

        Oracle has no session-level statement timeout to set — the timeout is a
        property of the JDBC statement (`setQueryTimeout`) or of a Resource
        Manager plan, neither of which is SQL. Saying so here rather than
        emitting a plausible `ALTER SESSION` that Oracle would reject, or worse
        accept and ignore.
        """
        return ("ALTER SESSION SET ISOLATION_LEVEL = READ COMMITTED",)


class SqlServerDialect(_JdbcDialect):
    """SQL Server 2014+, Azure SQL. **Never run against a SQL Server.**"""

    name = "sqlserver"
    snapshot_kind = SnapshotKind.LSN
    has_native_sampling = True

    def quote(self, identifier: str) -> str:
        """Brackets, and `]` doubled.

        SQL Server accepts double quotes only when QUOTED_IDENTIFIER is ON,
        which is a session setting a connection may not control. Brackets always
        work.
        """
        return "[" + identifier.replace("]", "]]") + "]"

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "'U','V'" if include_views else "'U'"
        return f"""
            SELECT s.name, t.name,
                   CASE t.type WHEN 'V' THEN 'view' ELSE 'table' END,
                   SUM(p.rows), SUM(a.total_pages) * 8192,
                   COALESCE(CAST(e.value AS nvarchar(max)), '')
            FROM sys.objects t
            JOIN sys.schemas s ON s.schema_id = t.schema_id
            LEFT JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1)
            LEFT JOIN sys.allocation_units a ON a.container_id = p.partition_id
            LEFT JOIN sys.extended_properties e
              ON e.major_id = t.object_id AND e.minor_id = 0 AND e.name = 'MS_Description'
            WHERE t.type IN ({kinds}) AND t.is_ms_shipped = 0
            GROUP BY s.name, t.name, t.type, CAST(e.value AS nvarchar(max))
            ORDER BY SUM(p.rows) DESC
        """

    def describe_sql(self) -> str:
        return f"""
            SELECT c.COLUMN_NAME, LOWER(c.DATA_TYPE),
                   CASE WHEN c.IS_NULLABLE = 'YES' THEN 1 ELSE 0 END,
                   c.ORDINAL_POSITION, '',
                   c.NUMERIC_PRECISION, c.NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS c
            WHERE c.TABLE_SCHEMA = {self.placeholder(1)}
              AND c.TABLE_NAME = {self.placeholder(2)}
            ORDER BY c.ORDINAL_POSITION
        """

    def estimate_rows_sql(self) -> str | None:
        return f"""
            SELECT SUM(p.rows) FROM sys.partitions p
            JOIN sys.objects t ON t.object_id = p.object_id
            JOIN sys.schemas s ON s.schema_id = t.schema_id
            WHERE s.name = {self.placeholder(1)} AND t.name = {self.placeholder(2)}
              AND p.index_id IN (0,1)
        """

    def snapshot_sql(self) -> str | None:
        return "SELECT CONVERT(varchar(64), MIN_ACTIVE_ROWVERSION())"

    def sample_from(self, path: tuple[str, ...], plan: SamplePlan) -> str:
        table = self.qualify(path)
        if plan.fraction is not None:
            percent = max(0.000001, plan.fraction * 100)
            return f"SELECT * FROM {table} TABLESAMPLE ({percent:g} PERCENT)"
        return f"SELECT * FROM {table}"

    def select_sql(self, path: tuple[str, ...], plan: SamplePlan, limit: int, offset: int) -> str:
        """`OFFSET … FETCH` needs an ORDER BY on SQL Server.

        A constant one, because ordering by a real column would change what a
        page contains and paging a table with no key is exactly the case this
        has to survive.
        """
        base = (
            f"SELECT * FROM {self.qualify(path)}"
            if plan.strategy in (SamplingStrategy.FULL, SamplingStrategy.HEAD)
            else self.sample_from(path, plan)
        )
        return f"{base} ORDER BY (SELECT NULL) OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"

    def session_setup_sql(self, *, statement_timeout_ms: int) -> tuple[str, ...]:
        seconds = max(1, statement_timeout_ms // 1000)
        return (
            "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED",
            f"SET LOCK_TIMEOUT {seconds * 1000}",
        )


class Db2Dialect(_JdbcDialect):
    """DB2 LUW, DB2 for z/OS, DB2 for i. **Never run against a DB2.**

    z/OS is the one that matters commercially: it is where a lot of banking
    reference data still lives, and it is the reason the mainframe formats in
    `docs/12` exist.
    """

    name = "db2"
    snapshot_kind = SnapshotKind.TRANSACTION_ID

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "'T','V'" if include_views else "'T'"
        return f"""
            SELECT TRIM(t.TABSCHEMA), TRIM(t.TABNAME),
                   CASE t.TYPE WHEN 'V' THEN 'view' ELSE 'table' END,
                   t.CARD, t.FPAGES * 4096, COALESCE(t.REMARKS, ' ')
            FROM SYSCAT.TABLES t
            WHERE t.TYPE IN ({kinds})
              AND t.TABSCHEMA NOT LIKE 'SYS%'
            ORDER BY t.CARD DESC
        """

    def describe_sql(self) -> str:
        return f"""
            SELECT TRIM(c.COLNAME), LOWER(TRIM(c.TYPENAME)),
                   CASE WHEN c.NULLS = 'Y' THEN 1 ELSE 0 END,
                   c.COLNO + 1, COALESCE(c.REMARKS, ' '),
                   c.LENGTH, c.SCALE
            FROM SYSCAT.COLUMNS c
            WHERE c.TABSCHEMA = {self.placeholder(1)}
              AND c.TABNAME = {self.placeholder(2)}
            ORDER BY c.COLNO
        """

    def estimate_rows_sql(self) -> str | None:
        """CARD is -1 when statistics have never been gathered.

        Returned as-is rather than clamped to zero: "nobody has run RUNSTATS on
        this table" and "this table is empty" are different facts, and the
        second is a finding.
        """
        return f"""
            SELECT CASE WHEN CARD < 0 THEN NULL ELSE CARD END
            FROM SYSCAT.TABLES
            WHERE TABSCHEMA = {self.placeholder(1)} AND TABNAME = {self.placeholder(2)}
        """

    def select_sql(self, path: tuple[str, ...], plan: SamplePlan, limit: int, offset: int) -> str:
        base = (
            f"SELECT * FROM {self.qualify(path)}"
            if plan.strategy in (SamplingStrategy.FULL, SamplingStrategy.HEAD)
            else self.sample_from(path, plan)
        )
        return f"{base} LIMIT {limit} OFFSET {offset}"

    def session_setup_sql(self, *, statement_timeout_ms: int) -> tuple[str, ...]:  # noqa: ARG002
        """Uncommitted read, which on DB2 is how you avoid taking locks.

        No statement timeout: DB2's is a client configuration value
        (`QUERYTIMEOUTINTERVAL`), not a statement. A dialect that invented one
        would emit SQL the server rejects.
        """
        return ("SET CURRENT ISOLATION = UR",)


class TeradataDialect(_JdbcDialect):
    """Teradata Vantage. **Never run against a Teradata.**

    Common in Tier-1 banks and usually the system where a scan is most
    expensive, so every default here leans towards asking the catalogue.
    """

    name = "teradata"
    #: No cheap statement-level marker, so this says wall-clock and means it.
    snapshot_kind = SnapshotKind.WALL_CLOCK
    has_native_sampling = True

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "'T','V'" if include_views else "'T'"
        return f"""
            SELECT TRIM(t.DataBaseName), TRIM(t.TableName),
                   CASE t.TableKind WHEN 'V' THEN 'view' ELSE 'table' END,
                   CAST(NULL AS BIGINT), CAST(NULL AS BIGINT),
                   COALESCE(TRIM(t.CommentString), ' ')
            FROM DBC.TablesV t
            WHERE t.TableKind IN ({kinds})
              AND t.DataBaseName NOT IN ('DBC','SYSLIB','SYSUDTLIB','TD_SYSFNLIB')
        """

    def describe_sql(self) -> str:
        return f"""
            SELECT TRIM(c.ColumnName), LOWER(TRIM(c.ColumnType)),
                   CASE WHEN c.Nullable = 'Y' THEN 1 ELSE 0 END,
                   c.ColumnId, COALESCE(TRIM(c.CommentString), ' '),
                   c.DecimalTotalDigits, c.DecimalFractionalDigits
            FROM DBC.ColumnsV c
            WHERE c.DatabaseName = {self.placeholder(1)}
              AND c.TableName = {self.placeholder(2)}
            ORDER BY c.ColumnId
        """

    def estimate_rows_sql(self) -> str | None:
        """From collected statistics, and `None` when there are none.

        Teradata will happily answer `count(*)` and charge for it. Discovery
        across a large estate is exactly where that becomes a conversation with
        the platform team.
        """
        return f"""
            SELECT RowCount FROM DBC.StatsV
            WHERE DatabaseName = {self.placeholder(1)}
              AND TableName = {self.placeholder(2)}
              AND ColumnName IS NULL
        """

    def sample_from(self, path: tuple[str, ...], plan: SamplePlan) -> str:
        table = self.qualify(path)
        if plan.rows is not None:
            return f"SELECT * FROM {table} SAMPLE {plan.rows}"
        if plan.fraction is not None:
            return f"SELECT * FROM {table} SAMPLE {plan.fraction:g}"
        return f"SELECT * FROM {table}"

    def select_sql(self, path: tuple[str, ...], plan: SamplePlan, limit: int, offset: int) -> str:
        base = (
            f"SELECT * FROM {self.qualify(path)}"
            if plan.strategy in (SamplingStrategy.FULL, SamplingStrategy.HEAD)
            else self.sample_from(path, plan)
        )
        window = "ROW_NUMBER() OVER (ORDER BY 1)"
        return f"{base} QUALIFY {window} BETWEEN {offset + 1} AND {offset + limit}"


class MySqlDialect(_JdbcDialect):
    """MySQL 8, MariaDB, Aurora MySQL, TiDB.

    The one dialect here that has been run against a real database — MySQL 8.4
    over Connector/J — which is what makes the others a reasonable risk: the
    transport and the choreography are shared and exercised, and what remains
    per dialect is SQL.
    """

    name = "mysql"
    #: No cheap statement-level marker without reading the binlog position,
    #: which needs a privilege a read-only account will not have.
    snapshot_kind = SnapshotKind.WALL_CLOCK

    def quote(self, identifier: str) -> str:
        """Backticks. MySQL accepts double quotes only in ANSI_QUOTES mode."""
        return "`" + identifier.replace("`", "``") + "`"

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "'BASE TABLE','VIEW'" if include_views else "'BASE TABLE'"
        return f"""
            SELECT t.TABLE_SCHEMA, t.TABLE_NAME,
                   CASE t.TABLE_TYPE WHEN 'VIEW' THEN 'view' ELSE 'table' END,
                   t.TABLE_ROWS, t.DATA_LENGTH, COALESCE(t.TABLE_COMMENT, '')
            FROM information_schema.TABLES t
            WHERE t.TABLE_TYPE IN ({kinds})
              AND t.TABLE_SCHEMA NOT IN
                  ('mysql','information_schema','performance_schema','sys')
            ORDER BY t.DATA_LENGTH DESC
        """

    def describe_sql(self) -> str:
        return f"""
            SELECT c.COLUMN_NAME, LOWER(c.DATA_TYPE),
                   c.IS_NULLABLE = 'YES',
                   c.ORDINAL_POSITION, COALESCE(c.COLUMN_COMMENT, ''),
                   c.NUMERIC_PRECISION, c.NUMERIC_SCALE
            FROM information_schema.COLUMNS c
            WHERE c.TABLE_SCHEMA = {self.placeholder(1)}
              AND c.TABLE_NAME = {self.placeholder(2)}
            ORDER BY c.ORDINAL_POSITION
        """

    def estimate_rows_sql(self) -> str | None:
        """TABLE_ROWS, which for InnoDB is an estimate and can be far out.

        Reported anyway and never used as a metric: it decides what discovery
        shows a person first, and being wrong about the order of a list is
        cheap where `count(*)` on a large InnoDB table is not.
        """
        return f"""
            SELECT TABLE_ROWS FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = {self.placeholder(1)} AND TABLE_NAME = {self.placeholder(2)}
        """

    def select_sql(self, path: tuple[str, ...], plan: SamplePlan, limit: int, offset: int) -> str:
        base = (
            f"SELECT * FROM {self.qualify(path)}"
            if plan.strategy in (SamplingStrategy.FULL, SamplingStrategy.HEAD)
            else self.sample_from(path, plan)
        )
        return f"{base} LIMIT {limit} OFFSET {offset}"

    def session_setup_sql(self, *, statement_timeout_ms: int) -> tuple[str, ...]:
        return (
            "SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED",
            f"SET SESSION MAX_EXECUTION_TIME = {max(1, statement_timeout_ms)}",
        )


# -- the cloud warehouses --------------------------------------------------
#
# None of these has been run. Each is reachable over JDBC with the vendor's own
# driver, which is why they are dialects rather than connectors — and why the
# risk is confined to SQL rather than to connection handling, threading and
# type fidelity, which are shared and exercised.


class RedshiftDialect(_JdbcDialect):
    """Amazon Redshift. **Never run against a Redshift.**

    Redshift speaks the PostgreSQL wire protocol and diverged from it years
    ago, which is the trap: a PostgreSQL dialect connects, answers most things,
    and is wrong in the places that matter. `pg_stat` is not there,
    `information_schema` is incomplete for external tables, and the row
    estimate lives in `svv_table_info` rather than in `pg_class.reltuples`.
    """

    name = "redshift"
    #: Redshift has no LSN a reader can name and return to.
    snapshot_kind = SnapshotKind.WALL_CLOCK

    def describe_sql(self) -> str:
        return f"""
            SELECT column_name, lower(data_type),
                   is_nullable = 'YES', ordinal_position, '',
                   numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = {self.placeholder(1)}
              AND table_name = {self.placeholder(2)}
            ORDER BY ordinal_position
        """

    def select_sql(self, path: tuple[str, ...], plan: SamplePlan, limit: int, offset: int) -> str:
        base = (
            f"SELECT * FROM {self.qualify(path)}"
            if plan.strategy in (SamplingStrategy.FULL, SamplingStrategy.HEAD)
            else self.sample_from(path, plan)
        )
        return f"{base} LIMIT {limit} OFFSET {offset}"

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "'BASE TABLE','VIEW'" if include_views else "'BASE TABLE'"
        return f"""
            SELECT t.table_schema, t.table_name,
                   CASE t.table_type WHEN 'VIEW' THEN 'view' ELSE 'table' END,
                   i.tbl_rows, i.size * 1024 * 1024, ''
            FROM information_schema.tables t
            LEFT JOIN svv_table_info i
              ON i.schema = t.table_schema AND i.table = t.table_name
            WHERE t.table_type IN ({kinds})
              AND t.table_schema NOT IN ('pg_catalog','information_schema')
            ORDER BY i.size DESC NULLS LAST
        """

    def estimate_rows_sql(self) -> str | None:
        """`svv_table_info`, not `pg_class.reltuples`.

        The PostgreSQL column exists on Redshift and is not maintained, so a
        dialect that inherited it would report zero for every table and look
        like an empty warehouse.
        """
        return f"""
            SELECT tbl_rows FROM svv_table_info
            WHERE schema = {self.placeholder(1)} AND "table" = {self.placeholder(2)}
        """


class DatabricksDialect(_JdbcDialect):
    """Databricks SQL warehouses and Unity Catalog. **Never run against one.**

    Three-level naming — catalog, schema, table — where everything else here is
    two. The connector's path carries it, and a dialect that assumed two would
    address the wrong table in the default catalogue rather than failing.
    """

    name = "databricks"
    #: Delta keeps versions, so a read can name one and return to it.
    snapshot_kind = SnapshotKind.DELTA_VERSION
    has_native_sampling = True

    def quote(self, identifier: str) -> str:
        return "`" + identifier.replace("`", "``") + "`"

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "'MANAGED','EXTERNAL','VIEW'" if include_views else "'MANAGED','EXTERNAL'"
        return f"""
            SELECT table_schema, table_name,
                   CASE table_type WHEN 'VIEW' THEN 'view' ELSE 'table' END,
                   NULL, NULL, COALESCE(comment, '')
            FROM system.information_schema.tables
            WHERE table_type IN ({kinds})
              AND table_schema <> 'information_schema'
        """

    def describe_sql(self) -> str:
        return f"""
            SELECT column_name, lower(full_data_type),
                   is_nullable = 'YES', ordinal_position,
                   COALESCE(comment, ''), numeric_precision, numeric_scale
            FROM system.information_schema.columns
            WHERE table_schema = {self.placeholder(1)}
              AND table_name = {self.placeholder(2)}
            ORDER BY ordinal_position
        """

    def estimate_rows_sql(self) -> str | None:
        """None. Unity Catalog does not keep a row count a query can read.

        `None` is the honest answer and the base connector reports "unknown"
        rather than running `count(*)` across a warehouse somebody pays for by
        the second.
        """
        return None

    def sample_from(self, path: tuple[str, ...], plan: SamplePlan) -> str:
        table = self.qualify(path)
        if plan.fraction is not None:
            return f"SELECT * FROM {table} TABLESAMPLE ({plan.fraction * 100:g} PERCENT)"
        if plan.rows is not None:
            return f"SELECT * FROM {table} TABLESAMPLE ({plan.rows} ROWS)"
        return f"SELECT * FROM {table}"


class SynapseDialect(SqlServerDialect):
    """Azure Synapse dedicated SQL pools. **Never run against a Synapse.**

    SQL Server's dialect with two things removed. Synapse has no
    `MIN_ACTIVE_ROWVERSION`, and `TABLESAMPLE` is not supported on a
    distributed table — claiming either would produce SQL the pool rejects.
    """

    name = "synapse"
    snapshot_kind = SnapshotKind.WALL_CLOCK
    has_native_sampling = False

    def snapshot_sql(self) -> str | None:
        return None

    def sample_from(self, path: tuple[str, ...], plan: SamplePlan) -> str:  # noqa: ARG002
        return f"SELECT * FROM {self.qualify(path)}"


class TrinoDialect(_JdbcDialect):
    """Trino and Starburst. **Never run against a Trino.**

    A query engine rather than a store, so `information_schema` is per catalog
    and the row count depends on whichever connector Trino itself is using.
    Asking for one would be asking a federation layer to guess.
    """

    name = "trino"
    snapshot_kind = SnapshotKind.WALL_CLOCK
    has_native_sampling = True

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "'BASE TABLE','VIEW'" if include_views else "'BASE TABLE'"
        return f"""
            SELECT table_schema, table_name,
                   CASE table_type WHEN 'VIEW' THEN 'view' ELSE 'table' END,
                   NULL, NULL, ''
            FROM information_schema.tables
            WHERE table_type IN ({kinds})
              AND table_schema <> 'information_schema'
        """

    def describe_sql(self) -> str:
        return f"""
            SELECT column_name, lower(data_type),
                   is_nullable = 'YES', ordinal_position,
                   COALESCE(comment, ''), NULL, NULL
            FROM information_schema.columns
            WHERE table_schema = {self.placeholder(1)}
              AND table_name = {self.placeholder(2)}
            ORDER BY ordinal_position
        """

    def estimate_rows_sql(self) -> str | None:
        """None: Trino federates, and the count belongs to whatever is
        underneath. A number invented here would be a guess about somebody
        else's storage."""
        return None

    def sample_from(self, path: tuple[str, ...], plan: SamplePlan) -> str:
        table = self.qualify(path)
        if plan.fraction is not None:
            return f"SELECT * FROM {table} TABLESAMPLE BERNOULLI ({plan.fraction * 100:g})"
        return f"SELECT * FROM {table}"


class BigQueryDialect(_JdbcDialect):
    """Google BigQuery. **Never run against a BigQuery.**

    Backticked three-part names, and a cost model where the unit billed is
    *bytes scanned* rather than time. That makes `SELECT *` on a wide table the
    expensive operation rather than the slow one, which is the opposite of
    every row store here — and the reason its row estimate comes from
    `__TABLES__`, which is free.
    """

    name = "bigquery"
    snapshot_kind = SnapshotKind.WALL_CLOCK
    has_native_sampling = True

    def quote(self, identifier: str) -> str:
        # Backslash **first**, then backtick. Reversing them, or omitting the
        # backslash as this did (finding S5), leaves a name ending in a
        # backslash escaping its own closing delimiter: `a\` is an identifier
        # that never closes, and delimiter parity is broken for the rest of the
        # statement. Both engines honour backslash escapes inside backticks, so
        # doubling the backtick alone is not enough here the way it is for
        # MySQL. The threat model is this module's own: "object names arrive
        # from a catalogue that a customer controls, and they reach a query
        # string."
        escaped = identifier.replace("\\", "\\\\").replace("`", "\\`")
        return f"`{escaped}`"

    def list_objects_sql(self, *, include_views: bool) -> str:
        kinds = "'BASE TABLE','VIEW'" if include_views else "'BASE TABLE'"
        return f"""
            SELECT table_schema, table_name,
                   CASE table_type WHEN 'VIEW' THEN 'view' ELSE 'table' END,
                   NULL, NULL, ''
            FROM INFORMATION_SCHEMA.TABLES
            WHERE table_type IN ({kinds})
        """

    def describe_sql(self) -> str:
        return f"""
            SELECT column_name, lower(data_type),
                   is_nullable = 'YES', ordinal_position, '', NULL, NULL
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE table_schema = {self.placeholder(1)}
              AND table_name = {self.placeholder(2)}
            ORDER BY ordinal_position
        """

    def estimate_rows_sql(self) -> str | None:
        return f"""
            SELECT row_count FROM __TABLES__
            WHERE dataset_id = {self.placeholder(1)} AND table_id = {self.placeholder(2)}
        """

    def sample_from(self, path: tuple[str, ...], plan: SamplePlan) -> str:
        table = self.qualify(path)
        if plan.fraction is not None:
            return f"SELECT * FROM {table} TABLESAMPLE SYSTEM ({plan.fraction * 100:g} PERCENT)"
        return f"SELECT * FROM {table}"

"""The enterprise dialects, and the one of them that has met a database.

Oracle, SQL Server, DB2 and Teradata are written from documented behaviour and
none has been run. MySQL has: against a real MySQL 8.4 over Connector/J, which
is what makes the other four a reasonable risk rather than a guess. The transport
and the choreography are shared and exercised; what differs per dialect is SQL,
which is wrong in ways a first run finds in minutes rather than in ways that
corrupt evidence quietly.

Set PRAMA_TEST_MYSQL_JDBC_URL and PRAMA_TEST_MYSQL_DRIVER_PATH to run the live
half:

    docker run -d --name prama-mysql -e MYSQL_ROOT_PASSWORD=prama \\
      -e MYSQL_DATABASE=prama -e MYSQL_USER=prama -e MYSQL_PASSWORD=prama \\
      -p 33306:3306 mysql:8.4

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import decimal
import os
import shutil

import pytest

from prama.connect.sources.sql.dialects import (
    BigQueryDialect,
    DatabricksDialect,
    Db2Dialect,
    MySqlDialect,
    OracleDialect,
    RedshiftDialect,
    SqlServerDialect,
    SynapseDialect,
    TeradataDialect,
    TrinoDialect,
)
from prama.connect.sources.sql.jdbc import DIALECTS
from prama.connect.spi import SamplePlan, SamplingStrategy

#: Every dialect the JDBC transport carries. MySQL has been run; the rest are
#: code complete.
ALL = [
    OracleDialect(),
    SqlServerDialect(),
    Db2Dialect(),
    TeradataDialect(),
    MySqlDialect(),
    RedshiftDialect(),
    DatabricksDialect(),
    SynapseDialect(),
    TrinoDialect(),
    BigQueryDialect(),
]
UNVERIFIED = [d for d in ALL if d.name != "mysql"]

URL = os.environ.get("PRAMA_TEST_MYSQL_JDBC_URL", "")
DRIVER = os.environ.get("PRAMA_TEST_MYSQL_DRIVER_PATH", "")
live = pytest.mark.skipif(
    not (URL and DRIVER and shutil.which("java")),
    reason="set PRAMA_TEST_MYSQL_JDBC_URL and PRAMA_TEST_MYSQL_DRIVER_PATH, and install a JRE",
)


def ident(dialect) -> str:
    return dialect.name


class TestEveryDialectIsReachable:
    @pytest.mark.parametrize("dialect", ALL, ids=ident)
    def test_it_is_registered_with_the_jdbc_connector(self, dialect) -> None:
        """A dialect nobody can select is a dialect nobody has."""
        assert dialect.name in DIALECTS

    @pytest.mark.parametrize("dialect", ALL, ids=ident)
    def test_it_binds_with_question_marks(self, dialect) -> None:
        """The placeholder style belongs to the driver, not the database."""
        assert dialect.placeholder(1) == "?"

    @pytest.mark.parametrize("dialect", ALL, ids=ident)
    def test_describe_takes_schema_then_name(self, dialect) -> None:
        sql = dialect.describe_sql()
        assert sql.count("?") == 2

    @pytest.mark.parametrize("dialect", ALL, ids=ident)
    def test_it_declares_pushdown(self, dialect) -> None:
        assert dialect.capabilities.to_capabilities()

    @pytest.mark.parametrize("dialect", ALL, ids=ident)
    def test_a_quoted_identifier_survives_its_own_delimiter(self, dialect) -> None:
        """Object names come from a catalogue a customer controls and reach a
        query string. This is the boundary that keeps them inert.

        The closing delimiter is *derived* from the dialect rather than looked
        up — a table of "which dialect uses which quote" is a second source of
        truth, and it broke the moment three more dialects arrived.
        """
        plain = dialect.quote("x")
        closing = plain[-1]
        nasty = f"a{closing}b"
        quoted = dialect.quote(nasty)
        assert quoted.startswith(plain[0]) and quoted.endswith(closing)
        # The embedded delimiter must have been escaped somehow — doubled or
        # backslashed — so the quoted form is longer than a naive wrap.
        assert len(quoted) > len(nasty) + 2, (
            f"{dialect.name} wrapped {nasty!r} as {quoted!r} without escaping "
            "its own delimiter, so the name terminates the quote early"
        )


class TestTheUnverifiedOnesSaySo:
    @pytest.mark.parametrize("dialect", UNVERIFIED, ids=ident)
    def test_the_docstring_admits_it_has_never_been_run(self, dialect) -> None:
        """An unverified dialect is a reasonable thing to ship; one that has
        quietly stopped saying so is not."""
        assert "Never run against" in (type(dialect).__doc__ or "")

    def test_the_module_separates_verified_from_written(self) -> None:
        from prama.connect.sources.sql import dialects

        assert "no Oracle, SQL Server, DB2 or Teradata has" in (dialects.__doc__ or "")

    def test_mysql_does_not_claim_to_be_unverified(self) -> None:
        """It has been run, and saying otherwise would be its own kind of
        inaccuracy."""
        assert "Never run against" not in (MySqlDialect.__doc__ or "")


class TestSnapshotsAreHonest:
    def test_oracle_and_sql_server_and_db2_are_exact(self) -> None:
        """An SCN, an LSN and a commit sequence each name a real prior state,
        so a control can be replayed against the data it actually read."""
        for dialect in (OracleDialect(), SqlServerDialect(), Db2Dialect()):
            assert dialect.snapshot_kind.is_exact, dialect.name

    def test_teradata_and_mysql_admit_they_are_not(self) -> None:
        """Neither has a cheap statement-level marker a read-only account can
        see. Evidence carries the flag and replay depends on it."""
        for dialect in (TeradataDialect(), MySqlDialect()):
            assert not dialect.snapshot_kind.is_exact, dialect.name


class TestCostIsADesignConstraint:
    @pytest.mark.parametrize("dialect", ALL, ids=ident)
    def test_row_estimates_never_scan(self, dialect) -> None:
        """`count(*)` on a Teradata fact table is a conversation with the
        platform team, and on BigQuery it is a bill.

        `None` is an accepted answer and a better one than a count: Databricks
        and Trino genuinely cannot say without scanning, and the base connector
        then reports "unknown" rather than buying a number nobody asked for.
        """
        sql = dialect.estimate_rows_sql()
        if sql is None:
            return
        assert "count(*)" not in sql.lower()

    def test_the_ones_that_cannot_estimate_say_none_rather_than_guessing(self) -> None:
        """Unity Catalog keeps no readable row count, and Trino federates — the
        count belongs to whatever is underneath it."""
        assert DatabricksDialect().estimate_rows_sql() is None
        assert TrinoDialect().estimate_rows_sql() is None

    def test_redshift_does_not_inherit_postgres_row_counts(self) -> None:
        """Redshift speaks the PostgreSQL wire protocol and diverged years ago.
        `pg_class.reltuples` exists there and is not maintained, so a dialect
        that inherited it would report zero for every table and look like an
        empty warehouse."""
        sql = RedshiftDialect().estimate_rows_sql() or ""
        assert "svv_table_info" in sql
        assert "reltuples" not in sql

    @pytest.mark.parametrize("dialect", ALL, ids=ident)
    def test_discovery_never_scans(self, dialect) -> None:
        sql = dialect.list_objects_sql(include_views=False)
        assert "count(*)" not in sql.lower()

    def test_db2_distinguishes_no_statistics_from_empty(self) -> None:
        """CARD is -1 when RUNSTATS has never run. "Nobody has gathered
        statistics" and "this table is empty" are different facts, and the
        second is a finding."""
        assert "CARD < 0" in (Db2Dialect().estimate_rows_sql() or "")


class TestPagingIdioms:
    def test_oracle_uses_offset_fetch_not_rownum(self) -> None:
        """`ROWNUM <= n` is evaluated before ORDER BY, so a paged read returns
        an arbitrary page rather than the one asked for."""
        sql = OracleDialect().select_sql(("S", "t"), SamplePlan(), 100, 200)
        assert "OFFSET 200 ROWS FETCH NEXT 100" in sql
        assert "ROWNUM" not in sql

    def test_sql_server_supplies_an_order_by_it_must_have(self) -> None:
        """OFFSET/FETCH requires one, and a constant keeps paging correct on a
        table with no key."""
        sql = SqlServerDialect().select_sql(("S", "t"), SamplePlan(), 10, 0)
        assert "ORDER BY (SELECT NULL)" in sql

    def test_teradata_pages_with_qualify(self) -> None:
        sql = TeradataDialect().select_sql(("S", "t"), SamplePlan(), 10, 20)
        assert "QUALIFY" in sql
        assert "BETWEEN 21 AND 30" in sql

    def test_mysql_and_db2_use_limit_offset(self) -> None:
        for dialect in (MySqlDialect(), Db2Dialect()):
            sql = dialect.select_sql(("S", "t"), SamplePlan(), 10, 5)
            assert "LIMIT 10 OFFSET 5" in sql, dialect.name


class TestSamplingIsOnlyClaimedWhereItExists:
    def test_oracle_sql_server_and_teradata_sample_natively(self) -> None:
        plan = SamplePlan(strategy=SamplingStrategy.RESERVOIR, fraction=0.1)
        assert "SAMPLE (10)" in OracleDialect().sample_from(("S", "t"), plan)
        assert "TABLESAMPLE (10 PERCENT)" in SqlServerDialect().sample_from(("S", "t"), plan)
        assert "SAMPLE 0.1" in TeradataDialect().sample_from(("S", "t"), plan)

    def test_synapse_drops_what_sql_server_has(self) -> None:
        """Synapse is SQL Server with two things removed: no
        MIN_ACTIVE_ROWVERSION, and TABLESAMPLE is not supported on a
        distributed table. Inheriting either would emit SQL the pool rejects."""
        assert SynapseDialect().snapshot_sql() is None
        assert not SynapseDialect().has_native_sampling
        assert "TABLESAMPLE" not in SynapseDialect().sample_from(
            ("S", "t"), SamplePlan(strategy=SamplingStrategy.RESERVOIR, fraction=0.1)
        )

    def test_db2_and_mysql_do_not_claim_native_sampling(self) -> None:
        """The base connector then reports the result as approximate rather
        than pretending a sample was taken."""
        assert not Db2Dialect().has_native_sampling
        assert not MySqlDialect().has_native_sampling


class TestSessionSetup:
    def test_no_dialect_invents_a_statement_it_cannot_run(self) -> None:
        """Oracle and DB2 have no session-level statement timeout — it is a
        driver or client setting. A dialect emitting a plausible ALTER SESSION
        would produce SQL the server rejects, or worse accepts and ignores."""
        for dialect in (OracleDialect(), Db2Dialect()):
            statements = dialect.session_setup_sql(statement_timeout_ms=5000)
            assert not any("TIMEOUT" in s.upper() for s in statements), dialect.name

    def test_the_ones_that_can_set_a_timeout_do(self) -> None:
        for dialect in (SqlServerDialect(), MySqlDialect()):
            statements = dialect.session_setup_sql(statement_timeout_ms=5000)
            assert any("5000" in s for s in statements), dialect.name


@live
class TestMySqlAgainstARealDatabase:
    """The half that makes the rest credible."""

    def connector(self):
        from prama.connect.sources.sql.jdbc import JdbcConnector

        return JdbcConnector(
            {
                "jdbc_url": URL,
                "driver_class": os.environ.get(
                    "PRAMA_TEST_MYSQL_DRIVER_CLASS", "com.mysql.cj.jdbc.Driver"
                ),
                "driver_path": DRIVER,
                "dialect": "mysql",
                "user": os.environ.get("PRAMA_TEST_MYSQL_USER", "prama"),
                "password": os.environ.get("PRAMA_TEST_MYSQL_PASSWORD", "prama"),
            }
        )

    @pytest.fixture(autouse=True)
    async def seeded(self):
        async with self.connector() as source:
            await source._fetch("DROP TABLE IF EXISTS dialect_probe")
            await source._fetch(
                "CREATE TABLE dialect_probe ("
                " id int, amount decimal(38,12), big bigint unsigned, name varchar(50))"
            )
            await source._fetch(
                "INSERT INTO dialect_probe VALUES"
                " (1, 1953193.464900000000, 18446744073709551615, 'alpha'),"
                " (2, 0.005000000000, 1, NULL)"
            )
        yield

    async def test_it_is_healthy(self) -> None:
        from prama.connect.spi import HealthState

        async with self.connector() as source:
            assert (await source.health()).state is HealthState.HEALTHY

    async def test_discovery_finds_the_table(self) -> None:
        async with self.connector() as source:
            found = await source.discover()
        assert any("dialect_probe" in o.qualified_name for o in found)

    async def test_an_unsigned_bigint_survives(self) -> None:
        """MySQL answers it as java.math.BigInteger, which is neither a Python
        number nor a string — `int(that)` raises, and it did: discovery failed
        on *every* MySQL table until the converter handled it."""
        async with self.connector() as source:
            rows = await source._fetch("SELECT big FROM dialect_probe WHERE id = 1")
        assert rows[0][0] == 18446744073709551615

    async def test_decimals_stay_exact(self) -> None:
        async with self.connector() as source:
            rows = await source._fetch("SELECT amount FROM dialect_probe WHERE id = 1")
        assert rows[0][0] == decimal.Decimal("1953193.464900000000")

    async def test_reading_streams_rows(self) -> None:
        rows = []
        async with self.connector() as source:
            async for batch in source.read(("prama", "dialect_probe")):
                rows.extend(batch.to_pylist())
        assert len(rows) == 2

    async def test_describe_reports_the_columns(self) -> None:
        async with self.connector() as source:
            schema = await source.describe(("prama", "dialect_probe"))
        assert set(schema.column_names) == {"id", "amount", "big", "name"}


class TestAValueTooBigForItsNaturalType:
    """Arrow infers int64, and MySQL's unsigned BIGINT goes past it.

    18446744073709551615 is a real identifier, and inference raised
    OverflowError rather than producing anything — so a table with one could
    not be read at all.
    """

    def test_an_ordinary_column_still_infers(self) -> None:
        from prama.connect.arrow import to_array

        assert to_array([1, 2, 3]).to_pylist() == [1, 2, 3]

    def test_an_unsigned_bigint_becomes_uint64_not_an_error(self) -> None:
        from prama.connect.arrow import to_array

        array = to_array([18446744073709551615, 1])
        assert array.to_pylist() == [18446744073709551615, 1]

    def test_a_value_beyond_every_integer_type_becomes_a_string(self) -> None:
        """Deliberately not a float. A float makes the read succeed and the
        number wrong, which is the failure this connector tree exists to
        prevent; a string is visibly a string and the value survives."""
        from prama.connect.arrow import to_array

        enormous = 10**40
        array = to_array([enormous])
        assert array.to_pylist() == [str(enormous)]
        assert str(array.type) == "string"

    def test_nulls_survive_the_fallback(self) -> None:
        from prama.connect.arrow import to_array

        assert to_array([10**40, None]).to_pylist() == [str(10**40), None]

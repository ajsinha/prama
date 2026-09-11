"""The JDBC connector, against a real database through a real driver.

Skipped unless PRAMA_TEST_JDBC_URL, PRAMA_TEST_JDBC_DRIVER_PATH and a Java
runtime are all present:

    docker run -d --name prama-pg -e POSTGRES_PASSWORD=prama -e POSTGRES_USER=prama \\
      -e POSTGRES_DB=prama -p 55432:5432 postgres:16-alpine
    curl -sSLo /tmp/postgresql.jar \\
      https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.4/postgresql-42.7.4.jar
    export PRAMA_TEST_JDBC_URL=jdbc:postgresql://127.0.0.1:55432/prama
    export PRAMA_TEST_JDBC_DRIVER_PATH=/tmp/postgresql.jar
    pytest -q tests/connect/sql/test_jdbc.py

PostgreSQL is used because it is the database available here, not because it is
the interesting one — the point of this connector is Oracle and DB2. What
PostgreSQL proves is the transport, the dialect discipline and the type
fidelity, and those are the same whatever is on the other end.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import decimal
import os
import shutil

import pytest

from prama.connect.spi import ConnectorError, HealthState, SamplePlan, SamplingStrategy

URL = os.environ.get("PRAMA_TEST_JDBC_URL", "")
DRIVER_PATH = os.environ.get("PRAMA_TEST_JDBC_DRIVER_PATH", "")
DRIVER_CLASS = os.environ.get("PRAMA_TEST_JDBC_DRIVER_CLASS", "org.postgresql.Driver")

pytestmark = pytest.mark.skipif(
    not (URL and DRIVER_PATH and shutil.which("java")),
    reason="set PRAMA_TEST_JDBC_URL and PRAMA_TEST_JDBC_DRIVER_PATH, and install a JRE",
)


def connector(**changes):
    from prama.connect.sources.sql.jdbc import JdbcConnector

    config = {
        "jdbc_url": URL,
        "driver_class": DRIVER_CLASS,
        "driver_path": DRIVER_PATH,
        "dialect": "postgresql",
        "user": os.environ.get("PRAMA_TEST_JDBC_USER", "prama"),
        "password": os.environ.get("PRAMA_TEST_JDBC_PASSWORD", "prama"),
    }
    config.update(changes)
    return JdbcConnector(config)


@pytest.fixture(scope="module")
def seeded():
    """A table with the column types that matter, created once.

    Seeded through the driver directly rather than through the connector: a
    Prama connector reads, and using one to create a table would be exercising
    a path the product does not have.
    """
    import jaydebeapi

    connection = jaydebeapi.connect(
        DRIVER_CLASS,
        URL,
        [
            os.environ.get("PRAMA_TEST_JDBC_USER", "prama"),
            os.environ.get("PRAMA_TEST_JDBC_PASSWORD", "prama"),
        ],
        DRIVER_PATH,
    )
    cursor = connection.cursor()
    cursor.execute("DROP TABLE IF EXISTS jdbc_probe")
    cursor.execute(
        "CREATE TABLE jdbc_probe ("
        " id integer, name text, amount numeric(38,12),"
        " big bigint, flag boolean)"
    )
    cursor.execute(
        "INSERT INTO jdbc_probe VALUES"
        " (1,'alpha',1953193.464900000000,9223372036854775807,true),"
        " (2,'beta',0.005000000000,1,false),"
        " (3,NULL,-10.250000000000,0,NULL)"
    )
    cursor.close()
    connection.close()
    yield


class TestExactNumbersStayExact:
    """The reason this connector is not a thin wrapper.

    JayDeBeApi's own converter calls BigDecimal.doubleValue() for any non-zero
    scale, so money arrives as a float. In a product whose job is to notice when
    money is wrong, that is disqualifying rather than a trade-off.
    """

    async def test_a_decimal_column_arrives_as_decimal(self, seeded) -> None:
        async with connector() as source:
            rows = await source._fetch("SELECT amount FROM jdbc_probe ORDER BY id")
        assert isinstance(rows[0][0], decimal.Decimal), f"got {type(rows[0][0]).__name__}"

    async def test_the_value_is_exact_to_its_declared_scale(self, seeded) -> None:
        async with connector() as source:
            rows = await source._fetch("SELECT amount FROM jdbc_probe ORDER BY id")
        assert rows[0][0] == decimal.Decimal("1953193.464900000000")
        assert str(rows[0][0]) == "1953193.464900000000"

    async def test_a_small_decimal_does_not_become_a_float(self, seeded) -> None:
        """0.005 is the classic one: as a double it is 0.005000000000000000104…
        and a half-up rounding at three places goes the other way."""
        async with connector() as source:
            rows = await source._fetch("SELECT amount FROM jdbc_probe WHERE id = 2")
        assert rows[0][0] == decimal.Decimal("0.005000000000")

    async def test_a_bigint_at_the_edge_survives(self, seeded) -> None:
        """9223372036854775807 through a double is 9223372036854775808."""
        async with connector() as source:
            rows = await source._fetch("SELECT big FROM jdbc_probe WHERE id = 1")
        assert int(rows[0][0]) == 9223372036854775807

    async def test_null_stays_null_rather_than_becoming_zero(self, seeded) -> None:
        async with connector() as source:
            rows = await source._fetch("SELECT name, flag FROM jdbc_probe WHERE id = 3")
        assert rows[0][0] is None
        assert rows[0][1] is None


class TestJdbcIsATransportNotADialect:
    async def test_a_source_with_no_dialect_refuses_to_open(self) -> None:
        """Guessing would send one database's SQL to another and produce a
        control that compiles and then fails at the source."""
        with pytest.raises(ConnectorError, match="must say which dialect"):
            await connector(dialect="").open()

    def test_an_unknown_dialect_lists_the_known_ones(self) -> None:
        from prama.connect.sources.sql.jdbc import JdbcConnector

        with pytest.raises(ConnectorError, match="no dialect called"):
            JdbcConnector({"dialect": "oracle-ish"})

    def test_the_named_dialect_is_the_one_used(self) -> None:
        assert connector().dialect.name == "postgresql"


class TestIncompleteConfiguration:
    @pytest.mark.parametrize("missing", ["jdbc_url", "driver_class", "driver_path"])
    async def test_each_missing_field_is_named(self, missing: str) -> None:
        source = connector(**{missing: ""})
        with pytest.raises(ConnectorError, match="needs " + missing):
            await source.open()

    async def test_it_says_prama_does_not_ship_drivers(self) -> None:
        source = connector(driver_path="")
        with pytest.raises(ConnectorError) as caught:
            await source.open()
        assert "does not ship drivers" in caught.value.remedy

    async def test_using_it_unopened_is_a_clear_error(self) -> None:
        with pytest.raises(ConnectorError, match="before it was opened"):
            await connector()._fetch("SELECT 1")


class TestTheOrdinaryContract:
    async def test_a_reachable_database_is_healthy(self, seeded) -> None:
        async with connector() as source:
            assert (await source.health()).state is HealthState.HEALTHY

    async def test_discovery_finds_the_table(self, seeded) -> None:
        async with connector() as source:
            found = await source.discover()
        assert any("jdbc_probe" in o.qualified_name for o in found)

    async def test_describe_reports_the_columns(self, seeded) -> None:
        async with connector() as source:
            schema = await source.describe(("public", "jdbc_probe"))
        assert set(schema.column_names) >= {"id", "name", "amount", "big", "flag"}

    async def test_reading_streams_rows(self, seeded) -> None:
        rows = []
        async with connector() as source:
            async for batch in source.read(("public", "jdbc_probe")):
                rows.extend(batch.to_pylist())
        assert len(rows) == 3

    async def test_a_sample_plan_bounds_the_read(self, seeded) -> None:
        rows = []
        plan = SamplePlan(strategy=SamplingStrategy.HEAD, rows=2)
        async with connector() as source:
            async for batch in source.read(("public", "jdbc_probe"), plan=plan):
                rows.extend(batch.to_pylist())
        assert len(rows) <= 2

    async def test_it_claims_it_can_run_controls(self, seeded) -> None:
        """Unlike REST: there is a real query engine on the other end."""
        async with connector() as source:
            assert source.can_run_controls
            assert source.pushdown_capabilities()

    async def test_a_snapshot_is_produced(self, seeded) -> None:
        async with connector() as source:
            snapshot = await source.snapshot(("public", "jdbc_probe"))
        assert snapshot.identifier

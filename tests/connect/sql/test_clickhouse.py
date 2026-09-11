"""ClickHouse against a real server.

Skipped unless PRAMA_TEST_CLICKHOUSE_HOST names one::

    docker run -d --name prama-ch -p 18123:8123 \\
      -e CLICKHOUSE_USER=prama -e CLICKHOUSE_PASSWORD=prama -e CLICKHOUSE_DB=prama \\
      clickhouse/clickhouse-server:24.8-alpine
    PRAMA_TEST_CLICKHOUSE_HOST=127.0.0.1 PRAMA_TEST_CLICKHOUSE_PORT=18123 pytest -q

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import decimal
import os

import pytest

from prama.connect.sources.sql.clickhouse import ClickHouseConnector, ClickHouseDialect
from prama.connect.spi import ConnectorError, HealthState, SamplePlan, SamplingStrategy

HOST = os.environ.get("PRAMA_TEST_CLICKHOUSE_HOST", "")

pytestmark = pytest.mark.skipif(
    not HOST, reason="set PRAMA_TEST_CLICKHOUSE_HOST to run against a server"
)


def connector(**changes) -> ClickHouseConnector:
    config = {
        "host": HOST,
        "port": int(os.environ.get("PRAMA_TEST_CLICKHOUSE_PORT", "8123")),
        "database": os.environ.get("PRAMA_TEST_CLICKHOUSE_DB", "prama"),
        "user": os.environ.get("PRAMA_TEST_CLICKHOUSE_USER", "prama"),
        "password": os.environ.get("PRAMA_TEST_CLICKHOUSE_PASSWORD", "prama"),
    }
    config.update(changes)
    return ClickHouseConnector(config)


@pytest.fixture(scope="module", autouse=True)
def seeded():
    import clickhouse_connect

    client = clickhouse_connect.get_client(
        host=HOST,
        port=int(os.environ.get("PRAMA_TEST_CLICKHOUSE_PORT", "8123")),
        username=os.environ.get("PRAMA_TEST_CLICKHOUSE_USER", "prama"),
        password=os.environ.get("PRAMA_TEST_CLICKHOUSE_PASSWORD", "prama"),
        database=os.environ.get("PRAMA_TEST_CLICKHOUSE_DB", "prama"),
    )
    client.command("DROP TABLE IF EXISTS ch_probe")
    client.command(
        "CREATE TABLE ch_probe (id Int32, amount Decimal(38,12),"
        " big UInt64, name Nullable(String)) ENGINE=MergeTree ORDER BY id"
    )
    client.command(
        "INSERT INTO ch_probe VALUES"
        " (1, 1953193.464900000000, 18446744073709551615, 'alpha'),"
        " (2, 0.005000000000, 1, NULL)"
    )
    client.close()
    yield


class TestItWorksAgainstARealServer:
    async def test_it_is_healthy(self) -> None:
        async with connector() as source:
            assert (await source.health()).state is HealthState.HEALTHY

    async def test_discovery_finds_the_table(self) -> None:
        async with connector() as source:
            found = await source.discover()
        assert any("ch_probe" in o.qualified_name for o in found)

    async def test_describe_reports_the_columns(self) -> None:
        async with connector() as source:
            schema = await source.describe(("prama", "ch_probe"))
        assert set(schema.column_names) == {"id", "amount", "big", "name"}

    async def test_a_nullable_column_is_reported_nullable(self) -> None:
        """ClickHouse spells it in the type — `Nullable(String)` — rather than
        in a separate flag, which is a real difference from every other SQL
        source here."""
        async with connector() as source:
            schema = await source.describe(("prama", "ch_probe"))
        assert schema.column("name").nullable
        assert not schema.column("id").nullable

    async def test_reading_streams_rows(self) -> None:
        rows = []
        async with connector() as source:
            async for batch in source.read(("prama", "ch_probe")):
                rows.extend(batch.to_pylist())
        assert len(rows) == 2

    async def test_a_sample_plan_bounds_the_read(self) -> None:
        rows = []
        plan = SamplePlan(strategy=SamplingStrategy.HEAD, rows=1)
        async with connector() as source:
            async for batch in source.read(("prama", "ch_probe"), plan=plan):
                rows.extend(batch.to_pylist())
        assert len(rows) <= 1


class TestExactNumbers:
    async def test_a_decimal_arrives_exact(self) -> None:
        """The driver does this correctly, which is one fewer thing to fix than
        JDBC needed."""
        async with connector() as source:
            rows = await source._fetch("SELECT amount FROM ch_probe WHERE id = 1")
        assert rows[0][0] == decimal.Decimal("1953193.464900000000")

    async def test_a_uint64_at_the_edge_survives(self) -> None:
        """18446744073709551615 does not fit a signed int64, and the Arrow
        fallback exists because of exactly this value."""
        rows = []
        async with connector() as source:
            async for batch in source.read(("prama", "ch_probe")):
                rows.extend(batch.to_pylist())
        assert any(str(r["big"]) == "18446744073709551615" for r in rows)


class TestCostAndSafety:
    async def test_row_estimates_come_from_the_catalogue(self) -> None:
        async with connector() as source:
            found = await source.discover()
        probe = next(o for o in found if "ch_probe" in o.qualified_name)
        assert probe.estimated_rows == 2

    async def test_the_session_is_capped_by_time_and_memory(self) -> None:
        """On a column store a query can finish inside its time limit and still
        take the server down by allocating."""
        statements = ClickHouseDialect().session_setup_sql(statement_timeout_ms=30_000)
        assert any("max_execution_time = 30" in s for s in statements)
        assert any("max_memory_usage" in s for s in statements)

    async def test_the_session_is_read_only(self) -> None:
        statements = ClickHouseDialect().session_setup_sql(statement_timeout_ms=1000)
        assert any("readonly = 1" in s for s in statements)


class TestParametersAreBoundNotInterpolated:
    async def test_a_catalogue_name_cannot_become_a_query(self) -> None:
        """The dialect writes `?` and this driver wants `{name:Type}`. The
        alternative — interpolating into the string — is how a table name a
        customer controls becomes a statement.

        The connector refuses the name outright, which is stronger than binding
        it and finding nothing: the check is that the table is still there
        afterwards."""
        with pytest.raises(ConnectorError, match="no table or view named"):
            async with connector() as source:
                await source.describe(("prama", "ch_probe'; DROP TABLE ch_probe--"))
        async with connector() as source:
            still = await source.describe(("prama", "ch_probe"))
        assert still.columns, "the table was dropped, which is the whole point"

    def test_the_binder_produces_named_parameters(self) -> None:
        from prama.connect.sources.sql.clickhouse import _bind

        sql, arguments = _bind("SELECT 1 WHERE a = ? AND b = ?", ("x", "y"))
        assert "{p0:String}" in sql
        assert arguments == {"p0": "x", "p1": "y"}


class TestHonestyAboutSampling:
    def test_it_does_not_claim_native_sampling(self) -> None:
        """`SAMPLE` is only valid on a MergeTree with a sampling key, where it
        is a syntax error rather than a slower read on every other table."""
        assert not ClickHouseDialect().has_native_sampling

    def test_the_snapshot_is_wall_clock_and_says_so(self) -> None:
        """Parts merge in the background and a query id does not pin them."""
        assert not ClickHouseDialect().snapshot_kind.is_exact


class TestRefusals:
    async def test_using_it_unopened_is_a_clear_error(self) -> None:
        with pytest.raises(ConnectorError, match="before it was opened"):
            await connector()._fetch("SELECT 1")

    async def test_an_unreachable_server_says_which_port_to_use(self) -> None:
        """The driver's own exception carries no remedy, and the mistake it
        usually means is the native port rather than the HTTP one."""
        from prama.connect.spi import UnreachableError

        with pytest.raises(UnreachableError) as caught:
            async with connector(port=1):
                pass
        assert "8123 plain" in caught.value.remedy

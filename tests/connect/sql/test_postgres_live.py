"""The PostgreSQL connector against a real server.

Skipped unless ``PRAMA_TEST_POSTGRES_DSN`` names one. The dialect tests cover
the SQL; these cover the things only a server can answer — that the read-only
setting is actually enforced, that TABLESAMPLE returns roughly the fraction
asked for, that an LSN comes back and looks like an LSN.

To run them::

    docker run -d --rm --name prama-pg -e POSTGRES_PASSWORD=prama \\
        -e POSTGRES_DB=prama -p 55432:5432 postgres:16-alpine
    PRAMA_TEST_POSTGRES_DSN=postgresql://postgres:prama@localhost:55432/prama \\
        pytest tests/connect/sql/test_postgres_live.py

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from prama.connect.sources.sql import PostgresConnector
from prama.connect.spi import HealthState, SamplePlan, SamplingStrategy, SnapshotKind

DSN = os.environ.get("PRAMA_TEST_POSTGRES_DSN", "")

pytestmark = [
    pytest.mark.skipif(not DSN, reason="set PRAMA_TEST_POSTGRES_DSN to run these"),
    pytest.mark.asyncio,
]

ROWS = 5_000

SEED_SQL = f"""
DROP SCHEMA IF EXISTS prama_live CASCADE;
CREATE SCHEMA prama_live;
CREATE TABLE prama_live.orders (
    order_id bigint PRIMARY KEY,
    amount numeric(18,2),
    region text,
    booked date
);
COMMENT ON TABLE prama_live.orders IS 'customer orders';
COMMENT ON COLUMN prama_live.orders.amount IS 'gross notional in EUR';
INSERT INTO prama_live.orders
SELECT n, (n * 1.5)::numeric(18,2),
       CASE WHEN n % 3 = 0 THEN 'EMEA' ELSE 'APAC' END,
       DATE '2026-01-01' + (n % 90)
FROM generate_series(1, {ROWS}) n;
CREATE VIEW prama_live.large AS SELECT * FROM prama_live.orders WHERE amount > 100;
ANALYZE prama_live.orders;
"""


@pytest.fixture(scope="module")
async def seeded() -> Any:
    """A schema to read, created with a writable connection of our own.

    Deliberately not created through the connector: the connector cannot write,
    which is the property under test.
    """
    import asyncpg

    connection = await asyncpg.connect(DSN)
    try:
        await connection.execute(SEED_SQL)
    finally:
        await connection.close()
    return DSN


@pytest.fixture
async def connector(seeded: str) -> Any:
    instance = PostgresConnector({"dsn": seeded, "schemas": ["prama_live"]})
    async with instance:
        yield instance


class TestAgainstARealServer:
    async def test_it_connects_and_sees_the_schema(self, connector: PostgresConnector) -> None:
        report = await connector.health()
        assert report.state is HealthState.HEALTHY
        assert report.latency_ms is not None

    async def test_discovery_brings_back_comments_and_estimates(
        self, connector: PostgresConnector
    ) -> None:
        found = {o.leaf: o for o in await connector.discover()}
        assert found["orders"].comment == "customer orders"
        assert found["orders"].kind == "table"
        assert found["large"].kind == "view"
        # From the catalogue, so within a few percent rather than exact.
        assert 0.9 * ROWS <= (found["orders"].estimated_rows or 0) <= 1.1 * ROWS
        assert (found["orders"].estimated_bytes or 0) > 0

    async def test_column_comments_and_precision_survive(
        self, connector: PostgresConnector
    ) -> None:
        schema = await connector.describe(("prama_live", "orders"))
        amount = schema.column("amount")
        assert amount is not None
        assert amount.comment == "gross notional in EUR"
        assert (amount.precision, amount.scale) == (18, 2)
        assert schema.column("order_id").nullable is False  # type: ignore[union-attr]

    async def test_the_snapshot_is_a_real_wal_position(self, connector: PostgresConnector) -> None:
        snapshot = await connector.snapshot(("prama_live", "orders"))
        assert snapshot.kind is SnapshotKind.LSN
        assert snapshot.exact
        assert "/" in snapshot.identifier  # LSNs are rendered as XX/YYYYYYYY

    async def test_a_full_read_returns_every_row(self, connector: PostgresConnector) -> None:
        total = 0
        async for batch in connector.read(("prama_live", "orders")):
            total += batch.num_rows
        assert total == ROWS

    async def test_a_row_limit_costs_only_what_it_keeps(self, connector: PostgresConnector) -> None:
        batches = [
            b async for b in connector.read(("prama_live", "orders"), plan=SamplePlan(rows=25))
        ]
        assert sum(b.num_rows for b in batches) == 25
        assert len(batches) == 1

    async def test_the_sample_is_about_the_fraction_asked_for(
        self, connector: PostgresConnector
    ) -> None:
        plan = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.1, seed=7)
        total = 0
        async for batch in connector.read(("prama_live", "orders"), plan=plan):
            total += batch.num_rows
        # Bernoulli is a coin flip per row, so the count varies. Anything near
        # 10% confirms the server sampled; 0 or ROWS would mean it did not.
        assert 0.05 * ROWS < total < 0.16 * ROWS

    async def test_a_seeded_sample_repeats_exactly(self, connector: PostgresConnector) -> None:
        # An evidence record that cannot be reproduced is an assertion.
        async def sample() -> list[int]:
            plan = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.1, seed=99)
            out: list[int] = []
            async for batch in connector.read(("prama_live", "orders"), plan=plan):
                out.extend(batch.column("order_id").to_pylist())
            return out

        assert await sample() == await sample()

    async def test_the_connector_cannot_write(self, connector: PostgresConnector) -> None:
        """The guarantee that makes this safe to point at production.

        Enforced by the server, so it holds even if Prama's own query
        construction is wrong.
        """
        import asyncpg

        async with connector._acquire() as connection:
            with pytest.raises(asyncpg.exceptions.ReadOnlySQLTransactionError):
                await connection.execute("CREATE TABLE prama_live.nope (x int)")

    async def test_reading_a_forbidden_object_never_reaches_the_server(self, seeded: str) -> None:
        from prama.connect.spi import ReadPolicy, UnauthorisedError

        instance = PostgresConnector(
            {"dsn": seeded}, policy=ReadPolicy(allowed_paths=("prama_live.orders",))
        )
        async with instance:
            with pytest.raises(UnauthorisedError):
                await instance.describe(("prama_live", "large"))

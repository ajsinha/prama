"""The choreography every SQL source shares, exercised without a server.

A fake driver stands in for the database so that the parts worth testing — the
budget, the ordering, the error classification, the streaming contract — are
tested deterministically rather than against whatever a live instance happens
to contain.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from prama.connect.sources.sql import GenericSqlDialect, SqlConnector
from prama.connect.spi import (
    HealthState,
    ReadPolicy,
    SamplePlan,
    SnapshotKind,
    UnauthorisedError,
)
from prama.core.registry import PluginManifest

CATALOGUE = [
    ("sales", "orders", "BASE TABLE", 1_000_000, 900_000_000, "customer orders"),
    ("sales", "regions", "BASE TABLE", 12, 4_096, ""),
    ("risk", "exposures", "VIEW", None, None, ""),
]

COLUMNS = [
    ("order_id", "bigint", False, 1, "the order", None, None),
    ("amount", "numeric", True, 2, "", 18, 2),
]


class FakeConnector(SqlConnector):
    """A SQL connector whose database is a dictionary."""

    plugin_key = "fake-sql"
    dialect = GenericSqlDialect()

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.describe_manifest(key="fake-sql", display_name="Fake SQL source")

    def __init__(self, config: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(config or {}, **kwargs)
        self.rows: list[tuple[Any, ...]] = [(n, float(n)) for n in range(100)]
        self.statements: list[str] = []
        self.fail_with: Exception | None = None
        self.fail_catalogue: Exception | None = None

    async def _fetch(self, sql: str, *params: Any) -> list[tuple[Any, ...]]:
        self.statements.append(sql)
        if self.fail_with is not None:
            raise self.fail_with
        if "SELECT 1" in sql:
            return [(1,)]
        if "information_schema.tables" in sql:
            if self.fail_catalogue is not None:
                raise self.fail_catalogue
            return list(CATALOGUE)
        if "information_schema.columns" in sql:
            return list(COLUMNS) if params[1] == "orders" else []
        return []

    async def _stream(self, sql: str, batch_rows: int) -> AsyncIterator[list[tuple[Any, ...]]]:
        self.statements.append(sql)
        for start in range(0, len(self.rows), batch_rows):
            yield self.rows[start : start + batch_rows]

    def _column_names(self) -> tuple[str, ...]:
        return ("n", "amount")


async def read_rows(connector: SqlConnector, path: tuple[str, ...], **kwargs: Any) -> int:
    total = 0
    async for batch in connector.read(path, **kwargs):
        total += batch.num_rows
    return total


class TestHealth:
    @pytest.mark.asyncio
    async def test_a_reachable_source_reports_what_it_can_see(self) -> None:
        report = await FakeConnector().health()
        assert report.state is HealthState.HEALTHY
        assert "3 readable object(s)" in report.detail
        assert report.latency_ms is not None

    @pytest.mark.asyncio
    async def test_a_refused_connection_is_unreachable(self) -> None:
        connector = FakeConnector()
        connector.fail_with = OSError("connection refused")
        assert (await connector.health()).state is HealthState.UNREACHABLE

    @pytest.mark.asyncio
    async def test_a_credential_failure_is_not_a_network_failure(self) -> None:
        # These send someone to two different teams. Reporting both as
        # "connection failed" costs a day of the wrong investigation.
        connector = FakeConnector()
        connector.fail_with = OSError("password authentication failed for user prama")
        assert (await connector.health()).state is HealthState.UNAUTHORISED

    @pytest.mark.asyncio
    async def test_a_slow_source_is_degraded_rather_than_down(self) -> None:
        connector = FakeConnector()
        connector.fail_with = TimeoutError("statement timed out")
        assert (await connector.health()).state is HealthState.DEGRADED

    @pytest.mark.asyncio
    async def test_connected_but_no_catalogue_asks_for_a_grant(self) -> None:
        connector = FakeConnector()
        connector.fail_catalogue = PermissionError("permission denied for schema sales")
        report = await connector.health()
        assert report.state is HealthState.UNAUTHORISED
        assert report.needs_access_request
        assert report.missing_permissions == ("catalogue read",)


class TestDiscovery:
    @pytest.mark.asyncio
    async def test_the_biggest_objects_come_first(self) -> None:
        found = await FakeConnector().discover()
        assert next(o.qualified_name for o in found) == "sales.orders"
        assert found[0].estimated_rows == 1_000_000
        assert found[0].comment == "customer orders"

    @pytest.mark.asyncio
    async def test_discovery_is_filtered_by_the_read_policy(self) -> None:
        connector = FakeConnector(policy=ReadPolicy(allowed_paths=("sales.*",)))
        assert {o.qualified_name for o in await connector.discover()} == {
            "sales.orders",
            "sales.regions",
        }

    @pytest.mark.asyncio
    async def test_discovery_can_be_narrowed_to_one_schema(self) -> None:
        connector = FakeConnector({"schemas": ["risk"]})
        assert [o.qualified_name for o in await connector.discover()] == ["risk.exposures"]

    @pytest.mark.asyncio
    async def test_a_path_prefix_narrows_the_listing(self) -> None:
        found = await FakeConnector().discover(("sales",))
        assert all(o.path[0] == "sales" for o in found)


class TestDescription:
    @pytest.mark.asyncio
    async def test_columns_carry_their_business_comment(self) -> None:
        # Often the only business description that exists anywhere. Picking it
        # up turns declaring a dataset into editing rather than typing.
        schema = await FakeConnector().describe(("sales", "orders"))
        assert schema.column_names == ("order_id", "amount")
        assert schema.column("order_id").comment == "the order"  # type: ignore[union-attr]
        assert schema.column("amount").precision == 18  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_nullability_survives_whatever_the_driver_calls_it(self) -> None:
        schema = await FakeConnector().describe(("sales", "orders"))
        assert schema.column("order_id").nullable is False  # type: ignore[union-attr]
        assert schema.column("amount").nullable is True  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_a_missing_object_says_how_to_find_the_real_ones(self) -> None:
        from prama.connect.spi import ConnectorError

        with pytest.raises(ConnectorError) as caught:
            await FakeConnector().describe(("sales", "nonexistent"))
        assert "Discovery lists" in caught.value.remedy

    @pytest.mark.asyncio
    async def test_a_forbidden_object_is_refused_before_any_query_runs(self) -> None:
        connector = FakeConnector(policy=ReadPolicy(allowed_paths=("sales.*",)))
        with pytest.raises(UnauthorisedError):
            await connector.describe(("risk", "exposures"))
        assert connector.statements == []


class TestSnapshot:
    @pytest.mark.asyncio
    async def test_a_source_with_no_marker_says_so_rather_than_implying_one(self) -> None:
        # The alternative is a wall-clock snapshot that looks as good as an LSN
        # in the evidence record and cannot actually be replayed.
        snapshot = await FakeConnector().snapshot(("sales", "orders"))
        assert snapshot.kind is SnapshotKind.WALL_CLOCK
        assert not snapshot.exact
        assert "cannot be replayed exactly" in snapshot.detail["note"]


class TestReading:
    @pytest.mark.asyncio
    async def test_a_full_read_returns_every_row(self) -> None:
        assert await read_rows(FakeConnector(), ("sales", "orders")) == 100

    @pytest.mark.asyncio
    async def test_a_row_limit_in_the_plan_is_honoured(self) -> None:
        connector = FakeConnector()
        assert await read_rows(connector, ("sales", "orders"), plan=SamplePlan(rows=25)) == 25

    @pytest.mark.asyncio
    async def test_the_connections_policy_caps_a_plan_that_asks_for_more(self) -> None:
        # The policy is the estate's rule and the plan is one request; a request
        # that exceeds the rule must not win.
        connector = FakeConnector(policy=ReadPolicy(max_rows_read=10))
        assert await read_rows(connector, ("sales", "orders"), plan=SamplePlan(rows=1000)) == 10

    @pytest.mark.asyncio
    async def test_a_byte_ceiling_stops_the_read_after_one_batch(self) -> None:
        # A batch has to be fetched before its size is known, so a byte ceiling
        # can be overshot by at most one batch and never by more. Anything
        # tighter needs a row cap, which is exact.
        connector = FakeConnector(policy=ReadPolicy(max_bytes_scanned=1))
        connector.rows = [(n, float(n)) for n in range(25_000)]
        batches = [b async for b in connector.read(("sales", "orders"))]
        assert len(batches) == 1
        assert batches[0].num_rows == 10_000

    @pytest.mark.asyncio
    async def test_a_small_read_does_not_drag_a_full_batch_across_the_network(self) -> None:
        # Asking a production database for ten thousand rows to keep twenty-five
        # is work done on the customer's behalf for no reason.
        connector = FakeConnector()
        connector.rows = [(n, float(n)) for n in range(25_000)]
        seen: list[int] = []
        original = connector._stream

        def spy(sql: str, batch_rows: int) -> Any:
            seen.append(batch_rows)
            return original(sql, batch_rows)

        connector._stream = spy  # type: ignore[method-assign]
        assert await read_rows(connector, ("sales", "orders"), plan=SamplePlan(rows=25)) == 25
        assert seen == [25]

    @pytest.mark.asyncio
    async def test_reading_streams_rather_than_materialising(self) -> None:
        # The contract that lets a table larger than memory be profiled at all.
        connector = FakeConnector()
        connector.rows = [(n, float(n)) for n in range(25_000)]
        batches = [b async for b in connector.read(("sales", "orders"))]
        assert len(batches) > 1
        assert sum(b.num_rows for b in batches) == 25_000

    @pytest.mark.asyncio
    async def test_an_empty_table_yields_nothing_and_does_not_fail(self) -> None:
        connector = FakeConnector()
        connector.rows = []
        assert await read_rows(connector, ("sales", "orders")) == 0


class TestQuoting:
    def test_an_identifier_from_a_customers_catalogue_cannot_escape_its_quotes(self) -> None:
        # Object names come from a catalogue the customer controls and end up in
        # a query string. This is the boundary that keeps them inert.
        dialect = GenericSqlDialect()
        assert dialect.quote('x"; DROP TABLE y --') == '"x""; DROP TABLE y --"'
        assert dialect.qualify(("sa les", "or ders")) == '"sa les"."or ders"'

    def test_the_generic_dialect_admits_it_cannot_snapshot_or_estimate(self) -> None:
        # Claiming either would produce evidence that cannot be replayed, or a
        # row count bought with a full scan.
        dialect = GenericSqlDialect()
        assert dialect.snapshot_sql() is None
        assert dialect.estimate_rows_sql() is None
        assert not dialect.has_native_sampling

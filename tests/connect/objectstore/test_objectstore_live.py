"""The object store connector against a real S3-compatible server.

Skipped unless ``PRAMA_TEST_S3_ENDPOINT`` names one. To run them::

    docker run -d --rm --name prama-minio -p 59000:9000 \\
        -e MINIO_ROOT_USER=pramakey -e MINIO_ROOT_PASSWORD=pramasecret \\
        quay.io/minio/minio server /data
    docker exec prama-minio mc alias set local http://localhost:9000 pramakey pramasecret
    docker exec prama-minio mc mb local/prama-test
    PRAMA_TEST_S3_ENDPOINT=localhost:59000 pytest tests/connect/objectstore

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from prama.connect.sources.objectstore import ObjectStoreConnector
from prama.connect.spi import HealthState, SamplePlan, SamplingStrategy, SnapshotKind
from prama.profile import Profiler, Segmentation, SegmentedProfiler, SegmentGrain

ENDPOINT = os.environ.get("PRAMA_TEST_S3_ENDPOINT", "")
BUCKET = os.environ.get("PRAMA_TEST_S3_BUCKET", "prama-test")

pytestmark = [
    pytest.mark.skipif(not ENDPOINT, reason="set PRAMA_TEST_S3_ENDPOINT to run these"),
    pytest.mark.asyncio,
]

ROWS = 500
DAYS = ("2026-04-01", "2026-04-02", "2026-04-03")

CONFIG: dict[str, Any] = {
    "endpoint": ENDPOINT,
    "access_key_id": os.environ.get("PRAMA_TEST_S3_KEY", "pramakey"),
    "secret_access_key": os.environ.get("PRAMA_TEST_S3_SECRET", "pramasecret"),
    "use_ssl": "false",
    "url_style": "path",
    "region": "us-east-1",
}


@pytest.fixture(scope="module")
def seeded() -> str:
    """Hive-partitioned parquet and one CSV, written with DuckDB directly."""
    import duckdb

    connection = duckdb.connect()
    connection.execute("INSTALL httpfs")
    connection.execute("LOAD httpfs")
    connection.execute(
        f"CREATE OR REPLACE SECRET t (TYPE s3, KEY_ID '{CONFIG['access_key_id']}', "
        f"SECRET '{CONFIG['secret_access_key']}', ENDPOINT '{ENDPOINT}', "
        f"USE_SSL false, URL_STYLE 'path', REGION 'us-east-1')"
    )
    connection.execute(
        f"CREATE TABLE t AS SELECT i AS trade_id, i * 2.25 AS notional, "
        f"CASE WHEN i % 4 = 0 THEN NULL ELSE 'CP' || (i % 7) END AS counterparty "
        f"FROM range({ROWS}) tbl(i)"
    )
    for day in DAYS:
        connection.execute(
            f"COPY t TO 's3://{BUCKET}/live/trades/booked={day}/part-0.parquet' (FORMAT parquet)"
        )
    connection.execute(f"COPY t TO 's3://{BUCKET}/live/reference/entities.csv' (FORMAT csv)")
    connection.close()
    return BUCKET


@pytest.fixture
async def connector(seeded: str) -> Any:
    instance = ObjectStoreConnector({**CONFIG, "uri": f"s3://{seeded}/live"})
    async with instance:
        yield instance


class TestAgainstARealStore:
    async def test_it_connects_and_counts_datasets_not_objects(
        self, connector: ObjectStoreConnector
    ) -> None:
        report = await connector.health()
        assert report.state is HealthState.HEALTHY
        assert "2 dataset(s)" in report.detail
        assert "4 object(s)" in report.detail

    async def test_a_partitioned_table_is_one_dataset(
        self, connector: ObjectStoreConnector
    ) -> None:
        found = {o.path[-1]: o for o in await connector.discover()}
        assert set(found) == {"trades", "reference"}
        assert found["trades"].tags == ("booked",)
        assert found["trades"].estimated_rows == ROWS * len(DAYS)

    async def test_the_partition_becomes_a_real_column(
        self, connector: ObjectStoreConnector
    ) -> None:
        # Which is what lets a lake dataset be segmented by business date
        # without anybody parsing a path.
        schema = await connector.describe((BUCKET, "live", "trades"))
        assert "booked" in schema.column_names
        assert schema.partition_columns == ("booked",)

    async def test_row_counts_come_from_footers_not_from_a_scan(
        self, connector: ObjectStoreConnector
    ) -> None:
        found = {o.path[-1]: o for o in await connector.discover()}
        assert found["trades"].estimated_rows == ROWS * len(DAYS)
        # The CSV has no footer, so its count is honestly unknown rather than
        # guessed from the object size.
        assert found["reference"].estimated_rows is None

    async def test_parquet_gets_an_exact_snapshot_and_csv_does_not(
        self, connector: ObjectStoreConnector
    ) -> None:
        # An object rewritten under the same name leaves a key-only digest
        # untouched. Calling that exact would let incremental profiling skip
        # data that changed underneath it.
        parquet = await connector.snapshot((BUCKET, "live", "trades"))
        csv = await connector.snapshot((BUCKET, "live", "reference"))
        assert parquet.kind is SnapshotKind.FILE_DIGEST
        assert parquet.exact
        assert csv.kind is SnapshotKind.OBJECT_LISTING
        assert not csv.exact

    async def test_a_full_read_spans_every_partition(self, connector: ObjectStoreConnector) -> None:
        total = 0
        async for batch in connector.read((BUCKET, "live", "trades")):
            total += batch.num_rows
        assert total == ROWS * len(DAYS)

    async def test_sampling_happens_in_the_store(self, connector: ObjectStoreConnector) -> None:
        plan = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.2, seed=5)
        total = 0
        async for batch in connector.read((BUCKET, "live", "trades"), plan=plan):
            total += batch.num_rows
        assert 0.1 * ROWS * len(DAYS) < total < 0.35 * ROWS * len(DAYS)

    async def test_a_lake_dataset_can_be_profiled_by_business_date(
        self, connector: ObjectStoreConnector
    ) -> None:
        """The point of all of it: one day read without touching the rest."""
        from datetime import date

        segments = Segmentation("booked", SegmentGrain.DAY).over_dates(
            date(2026, 4, 1), date(2026, 4, 3)
        )
        profiler = SegmentedProfiler(Profiler())
        profile, plan = await profiler.refresh(
            connector, (BUCKET, "live", "trades"), segments, dataset="lake.trades"
        )
        assert len(plan.to_read) == 3
        assert len(profile) == 3
        for key in profile.segment_keys:
            one = profile.profile_of(key)
            assert one is not None
            assert one.provenance.rows_examined == ROWS
        folded = profile.folded()
        assert folded is not None
        assert folded.provenance.rows_examined == ROWS * len(DAYS)

    async def test_a_second_pass_over_a_lake_reads_nothing(
        self, connector: ObjectStoreConnector
    ) -> None:
        from datetime import date

        segments = Segmentation("booked", SegmentGrain.DAY).over_dates(
            date(2026, 4, 1), date(2026, 4, 3)
        )
        profiler = SegmentedProfiler(Profiler())
        profile, _ = await profiler.refresh(
            connector, (BUCKET, "live", "trades"), segments, dataset="lake.trades"
        )
        _, second = await profiler.refresh(
            connector, (BUCKET, "live", "trades"), segments, dataset="lake.trades", into=profile
        )
        assert second.to_read == ()

    async def test_a_csv_dataset_is_never_trusted_between_runs(
        self, connector: ObjectStoreConnector
    ) -> None:
        # Its snapshot is not exact, so a settled segment cannot be assumed
        # settled — which is the correct, conservative answer.
        from datetime import date

        segments = Segmentation("x", SegmentGrain.DAY).over_dates(
            date(2026, 4, 1), date(2026, 4, 1)
        )
        planner = SegmentedProfiler(Profiler()).planner
        snapshot = await connector.snapshot((BUCKET, "live", "reference"))
        planner.ledger.record(
            "lake.reference", segments[0], snapshot=snapshot, rows=1, at=snapshot.captured_at
        )
        plan = planner.plan("lake.reference", segments, snapshot=snapshot)
        assert plan.to_read == tuple(segments)

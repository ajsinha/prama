"""Folding an object listing into datasets.

The judgement that decides whether this connector is useful at all. Every
object as its own dataset gives a catalogue of a thousand daily partitions in
which nobody can find anything; one dataset for the whole bucket gives a single
entry that means nothing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from prama.connect.sources.objectstore import (
    ObjectStoreConnector,
    _group,
    _partition_depth,
    _StoredObject,
)
from prama.connect.spi import HealthState


def objects(*keys: str, rows: int | None = None, size: int | None = None) -> list:
    return [_StoredObject(key=k, rows=rows, size=size) for k in keys]


class TestPartitionDetection:
    def test_a_hive_directory_names_its_column(self) -> None:
        depth, columns = _partition_depth(("lake", "risk", "positions", "booked=2026-04-01"))
        assert (depth, columns) == (1, ("booked",))

    def test_several_hive_levels_are_all_partitions(self) -> None:
        depth, columns = _partition_depth(("lake", "trades", "year=2026", "month=04"))
        assert (depth, columns) == (2, ("year", "month"))

    def test_a_bare_date_directory_is_a_partition_without_a_column_name(self) -> None:
        # Extremely common, and it carries a value with no name — so the column
        # is unknown and Prama says so rather than inventing one.
        depth, columns = _partition_depth(("lake", "positions", "2026-04-01"))
        assert (depth, columns) == (1, ())

    def test_only_trailing_directories_count(self) -> None:
        # risk/2026/positions does not partition on 2026: a directory in the
        # middle is part of the dataset's identity, not a slice of it.
        depth, columns = _partition_depth(("lake", "2026", "positions"))
        assert (depth, columns) == (0, ())

    def test_a_prefix_with_no_partitions_is_left_alone(self) -> None:
        assert _partition_depth(("lake", "reference", "entities")) == (0, ())


class TestGrouping:
    def test_a_thousand_daily_partitions_are_one_dataset(self) -> None:
        # The failure this exists to prevent: a catalogue nobody can use.
        keys = [
            f"s3://lake/risk/positions/booked=2026-{m:02d}-{d:02d}/part-0.parquet"
            for m in (1, 2)
            for d in range(1, 29)
        ]
        datasets = _group(objects(*keys))
        assert len(datasets) == 1
        assert datasets[0].path == ("lake", "risk", "positions")
        assert datasets[0].partition_columns == ("booked",)
        assert len(datasets[0].objects) == 56

    def test_separate_prefixes_stay_separate_datasets(self) -> None:
        datasets = _group(
            objects(
                "s3://lake/risk/positions/booked=2026-04-01/a.parquet",
                "s3://lake/risk/trades/booked=2026-04-01/a.parquet",
                "s3://lake/reference/entities.csv",
            )
        )
        assert {d.path for d in datasets} == {
            ("lake", "risk", "positions"),
            ("lake", "risk", "trades"),
            ("lake", "reference"),
        }

    def test_many_parts_of_one_partition_are_still_one_dataset(self) -> None:
        datasets = _group(
            objects(*[f"s3://lake/t/booked=2026-04-01/part-{n}.parquet" for n in range(200)])
        )
        assert len(datasets) == 1
        assert len(datasets[0].objects) == 200

    def test_the_uri_points_at_the_prefix_not_at_a_file(self) -> None:
        datasets = _group(objects("s3://lake/risk/positions/booked=2026-04-01/part-0.parquet"))
        assert datasets[0].uri == "s3://lake/risk/positions"

    def test_the_reader_globs_across_every_partition(self) -> None:
        datasets = _group(
            objects(
                "s3://lake/t/booked=2026-04-01/a.parquet",
                "s3://lake/t/booked=2026-04-02/a.parquet",
            )
        )
        reader = datasets[0].reader()
        assert reader.startswith("read_parquet('s3://lake/t/*/*'")
        # The setting that turns booked=2026-04-01 into a real column, which is
        # what lets a lake dataset be segmented by business date at all.
        assert "hive_partitioning = true" in reader

    def test_probing_reads_one_object_rather_than_the_prefix(self) -> None:
        # Answering "what columns does this have" should not open a thousand
        # objects.
        datasets = _group(
            objects(*[f"s3://lake/t/booked=2026-04-{d:02d}/a.parquet" for d in range(1, 20)])
        )
        assert datasets[0].reader(probe=True).count("*") == 0


class TestWhatIsKnownAndWhatIsNot:
    def test_a_measured_dataset_reports_its_rows(self) -> None:
        datasets = _group(objects("s3://lake/t/a.parquet", rows=1000, size=50_000))
        assert datasets[0].total_rows == 1000
        assert datasets[0].total_bytes == 50_000
        assert datasets[0].is_measured

    def test_a_partly_measured_dataset_reports_nothing_rather_than_a_partial_sum(self) -> None:
        # Summing the objects whose footers we could read would give a total
        # that looks precise and is short by however many we could not.
        dataset = _group(
            [
                _StoredObject("s3://lake/t/a.parquet", size=1, rows=1),
                _StoredObject("s3://lake/t/b.parquet"),
            ]
        )[0]
        assert dataset.total_rows is None
        assert dataset.total_bytes is None
        assert not dataset.is_measured

    def test_an_unmeasured_dataset_says_so_in_its_description(self) -> None:
        dataset = _group(objects("s3://lake/t/a.csv"))[0]
        assert "rows" not in dataset.describe()
        assert "1 object(s)" in dataset.describe()


class TestConfiguration:
    def test_credentials_are_built_for_the_call_and_not_stored(self) -> None:
        connector = ObjectStoreConnector(
            {"uri": "s3://lake", "access_key_id": "AK", "secret_access_key": "SK"}
        )
        statement = connector._secret_statement()
        assert "KEY_ID 'AK'" in statement and "SECRET 'SK'" in statement

    def test_no_key_falls_back_to_the_machines_own_role(self) -> None:
        # The normal arrangement in a cloud estate, and better than a key in a
        # configuration file.
        statement = ObjectStoreConnector({"uri": "s3://lake"})._secret_statement()
        assert "PROVIDER credential_chain" in statement
        assert "KEY_ID" not in statement

    def test_a_quote_in_a_credential_cannot_break_out_of_the_statement(self) -> None:
        connector = ObjectStoreConnector(
            {"uri": "s3://lake", "access_key_id": "A", "secret_access_key": "a' OR '1'='1"}
        )
        assert "SECRET 'a'' OR ''1''=''1'" in connector._secret_statement()

    @pytest.mark.asyncio
    async def test_a_uri_that_is_not_an_object_store_is_misconfiguration(self) -> None:
        # Which sends somebody back to the connection form, not to the network
        # team — a distinction that saves a day each time.
        report = await ObjectStoreConnector({"uri": "/mnt/share"}).health()
        assert report.state is HealthState.MISCONFIGURED
        assert report.needs_reconfiguration
        assert "s3" in report.detail

    def test_azure_and_google_are_reached_the_same_way(self) -> None:
        assert ObjectStoreConnector({"uri": "az://container/x"}).scheme == "az"
        assert ObjectStoreConnector({"uri": "gs://bucket/x"}).scheme == "gs"

    def test_the_connector_takes_its_secret_from_the_vault(self) -> None:
        assert ObjectStoreConnector.credential_field == "secret_access_key"


class TestConcurrency:
    """Reads must not close each other's result streams."""

    @pytest.mark.asyncio
    async def test_concurrent_reads_of_one_source_do_not_collide(self, tmp_path: Path) -> None:
        # A DuckDB connection carries one result stream, so two reads sharing it
        # close each other's — surfacing as "Query Stream is closed" from
        # whichever lost. Segmented profiling reads its segments concurrently by
        # design, so this is the normal path rather than an edge case.
        import asyncio

        import pyarrow as pa
        import pyarrow.parquet as pq

        from prama.connect.sources.filesystem import FilesystemConnector

        for name in ("a", "b", "c", "d"):
            pq.write_table(
                pa.table({"x": list(range(5_000)), "g": [name] * 5_000}),
                tmp_path / f"{name}.parquet",
            )
        connector = FilesystemConnector({"root_path": str(tmp_path)})

        async def count(name: str) -> int:
            total = 0
            async for batch in connector.read((f"{name}.parquet",)):
                total += batch.num_rows
            return total

        async with connector:
            assert await asyncio.gather(*(count(n) for n in "abcd")) == [5_000] * 4

    @pytest.mark.asyncio
    async def test_a_large_file_is_streamed_not_materialised(self, tmp_path: Path) -> None:
        # Reading a whole extract into memory to hand back its first batch is
        # the difference between profiling a large file and falling over on one.
        import pyarrow as pa
        import pyarrow.parquet as pq

        from prama.connect.sources.filesystem import FilesystemConnector

        pq.write_table(pa.table({"x": list(range(120_000))}), tmp_path / "big.parquet")
        connector = FilesystemConnector({"root_path": str(tmp_path)})
        async with connector:
            batches = [b async for b in connector.read(("big.parquet",))]
        assert len(batches) > 1
        assert sum(b.num_rows for b in batches) == 120_000

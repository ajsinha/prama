"""Segmented profiling against a real source, and the fold that makes it exact.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from prama.connect.sources.sqlite import SqliteConnector
from prama.connect.spi import ConnectorError, SamplePlan
from prama.profile import (
    ColumnAccumulator,
    Profiler,
    Segmentation,
    SegmentedProfiler,
    SegmentGrain,
)

PATH = ("positions",)
DAYS = [date(2026, 4, 1) + __import__("datetime").timedelta(days=n) for n in range(6)]


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """Five clean days and one where the feed stopped sending counterparties."""
    database = tmp_path / "risk.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE positions (position_id INTEGER NOT NULL, booked TEXT NOT NULL, "
        "entity TEXT NOT NULL, counterparty TEXT)"
    )
    rows = []
    for n in range(600):
        day = DAYS[n % 6]
        broken = day == date(2026, 4, 5)
        rows.append(
            (n, day.isoformat(), "EMEA" if n % 2 else "APAC", None if broken else f"CP{n % 20}")
        )
    connection.executemany("INSERT INTO positions VALUES (?,?,?,?)", rows)
    connection.commit()
    connection.close()
    return database


@pytest.fixture
def connector(source: Path) -> SqliteConnector:
    return SqliteConnector({"database_path": str(source)})


def daily() -> list:
    return Segmentation("booked", SegmentGrain.DAY).over_dates(DAYS[0], DAYS[-1])


class TestWhatSegmentationIsFor:
    async def test_the_whole_table_rate_conceals_the_broken_day(
        self, connector: SqliteConnector
    ) -> None:
        # 16.7% reads as a tolerable data quality issue somebody will get to.
        async with connector:
            whole = await Profiler().profile(connector, PATH)
        rate = whole.column("counterparty").null_rate
        assert 0.15 < rate < 0.18

    async def test_segmented_the_same_data_shows_an_outage(
        self, connector: SqliteConnector
    ) -> None:
        # One day at 100% is not a tolerable issue; it is a feed that stopped.
        profiler = SegmentedProfiler(Profiler())
        async with connector:
            profile, _ = await profiler.refresh(connector, PATH, daily())
        rates = dict(profiler.compare(profile, "counterparty"))
        assert rates["2026-04-05"] == 1.0
        assert all(rates[day.isoformat()] == 0.0 for day in DAYS if day != date(2026, 4, 5))

    async def test_the_odd_segment_is_identified_against_the_median(
        self, connector: SqliteConnector
    ) -> None:
        # Against the mean, one catastrophic segment drags the average far
        # enough to make itself look ordinary.
        profiler = SegmentedProfiler(Profiler())
        async with connector:
            profile, _ = await profiler.refresh(connector, PATH, daily())
        odd = profiler.divergent(profiler.compare(profile, "counterparty"))
        assert [key for key, _ in odd] == ["2026-04-05"]

    def test_two_segments_cannot_say_which_is_the_odd_one(self) -> None:
        assert SegmentedProfiler.divergent([("a", 0.0), ("b", 1.0)]) == []


class TestTheFold:
    async def test_folding_segments_reproduces_the_single_pass_profile(
        self, connector: SqliteConnector
    ) -> None:
        # The identity the whole design rests on. If this drifts, an
        # incrementally refreshed profile silently stops matching reality.
        async with connector:
            whole = await Profiler().profile(connector, PATH)
            profile, _ = await SegmentedProfiler(Profiler()).refresh(connector, PATH, daily())
        folded = profile.folded()
        assert folded is not None
        assert folded.provenance.rows_examined == whole.provenance.rows_examined
        for column in whole.columns:
            merged = folded.column(column.name)
            assert merged is not None
            assert merged.rows == column.rows
            assert merged.nulls == column.nulls
            assert merged.distinct_estimate == column.distinct_estimate

    async def test_a_folded_profile_is_as_old_as_its_oldest_part(
        self, connector: SqliteConnector
    ) -> None:
        # Stamping it with the newest segment's time would make a segment
        # nobody has looked at for a month appear fresh.
        profiler = SegmentedProfiler(Profiler())
        async with connector:
            profile, _ = await profiler.refresh(connector, PATH, daily())
        folded = profile.folded()
        oldest = min(
            profile.state(key).provenance.computed_at  # type: ignore[union-attr]
            for key in profile.segment_keys
        )
        assert folded is not None
        assert folded.provenance.computed_at == oldest

    async def test_a_folded_profile_does_not_claim_to_be_one_segment(
        self, connector: SqliteConnector
    ) -> None:
        profiler = SegmentedProfiler(Profiler())
        async with connector:
            profile, _ = await profiler.refresh(connector, PATH, daily())
        folded = profile.folded()
        assert folded is not None
        assert folded.provenance.plan.predicate == ""

    def test_an_empty_segmented_profile_folds_to_nothing(self) -> None:
        from prama.profile import SegmentedProfile

        assert SegmentedProfile(PATH).folded() is None

    def test_merging_two_columns_by_different_names_is_refused(self) -> None:
        from prama.core.errors import ValidationError

        left, right = ColumnAccumulator("a", "TEXT"), ColumnAccumulator("b", "TEXT")
        with pytest.raises(ValidationError, match="column by column"):
            left.merge(right)

    def test_a_column_whose_type_changed_reports_both(self) -> None:
        # A segment written before a type change holds real data, so excluding
        # it would understate the table — but the merged profile must not claim
        # a single type the column no longer has.
        old, new = ColumnAccumulator("x", "INTEGER"), ColumnAccumulator("x", "TEXT")
        assert old.merge(new).type_name == "INTEGER|TEXT"


class TestIncrementalRefresh:
    async def test_the_second_refresh_reads_nothing(self, connector: SqliteConnector) -> None:
        profiler = SegmentedProfiler(Profiler())
        async with connector:
            profile, first = await profiler.refresh(connector, PATH, daily())
            _, second = await profiler.refresh(connector, PATH, daily(), into=profile)
        assert len(first.to_read) == 6
        assert second.to_read == ()
        assert second.saved_fraction == 1.0

    async def test_a_changed_source_is_noticed(
        self, connector: SqliteConnector, source: Path
    ) -> None:
        profiler = SegmentedProfiler(Profiler())
        async with connector:
            profile, _ = await profiler.refresh(connector, PATH, daily())
        writable = sqlite3.connect(source)
        writable.execute("INSERT INTO positions VALUES (9999, '2026-04-06', 'EMEA', 'CP1')")
        writable.commit()
        writable.close()
        async with connector:
            _, plan = await profiler.refresh(connector, PATH, daily(), into=profile)
        # The file's identity moved, so every segment is re-read. Coarse, and
        # honest: a whole-file marker cannot say which day changed.
        assert len(plan.to_read) == 6

    async def test_a_refresh_keeps_the_segments_it_did_not_read(
        self, connector: SqliteConnector
    ) -> None:
        profiler = SegmentedProfiler(Profiler())
        async with connector:
            profile, _ = await profiler.refresh(connector, PATH, daily())
            again, _ = await profiler.refresh(connector, PATH, daily(), into=profile)
        assert len(again) == 6
        assert again.folded() is not None


class TestSafety:
    async def test_a_connector_that_cannot_filter_refuses_the_whole_idea(self) -> None:
        # The quiet disaster this prevents: the predicate is dropped, the whole
        # table is read, and the result is filed as one day's profile.
        class Unfilterable(SqliteConnector):
            def pushdown_capabilities(self):  # type: ignore[no-untyped-def]
                return ()

        connector = Unfilterable({"database_path": ":memory:"})
        with pytest.raises(ConnectorError) as caught:
            await SegmentedProfiler(Profiler()).refresh(connector, PATH, daily())
        assert "calling it one segment" in caught.value.remedy

    async def test_a_predicate_is_never_silently_ignored(self) -> None:
        class Unfilterable(SqliteConnector):
            def pushdown_capabilities(self):  # type: ignore[no-untyped-def]
                return ()

        connector = Unfilterable({"database_path": ":memory:"})
        with pytest.raises(ConnectorError):
            async for _ in connector.read(PATH, plan=SamplePlan(predicate="1=1")):
                pass

    async def test_no_segments_is_refused_rather_than_silently_doing_nothing(
        self, connector: SqliteConnector
    ) -> None:
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError, match="at least one segment"):
            await SegmentedProfiler(Profiler()).refresh(connector, PATH, [])

    async def test_a_segment_profile_does_not_claim_to_be_complete(
        self, connector: SqliteConnector
    ) -> None:
        # It saw one day. Reporting its rates as the dataset's would be a
        # straightforward falsehood.
        profiler = SegmentedProfiler(Profiler())
        async with connector:
            profile, _ = await profiler.refresh(connector, PATH, daily())
        one = profile.profile_of("2026-04-05")
        assert one is not None
        assert not one.provenance.is_complete
        assert "booked" in one.provenance.plan.describe()


class TestTheSnapshotThatMakesThisSafe:
    """The marker incremental profiling trusts, and why it is not data_version."""

    async def test_the_marker_moves_when_the_file_does(
        self, connector: SqliteConnector, source: Path
    ) -> None:
        # PRAGMA data_version is the obvious candidate and is wrong: it reports
        # changes made by *other* connections during the life of the current
        # one, so a fresh connection always reads 1. Built on that, incremental
        # profiling would trust a stale profile forever while believing it had
        # checked.
        async with connector:
            before = await connector.snapshot(PATH)
        writable = sqlite3.connect(source)
        writable.execute("INSERT INTO positions VALUES (9999, '2026-04-06', 'EMEA', 'CP1')")
        writable.commit()
        writable.close()
        async with connector:
            after = await connector.snapshot(PATH)
        assert before.identifier != after.identifier
        assert before.exact and after.exact

    async def test_the_marker_holds_still_when_nothing_happens(
        self, connector: SqliteConnector
    ) -> None:
        # A marker that changed on every read would force a full re-read every
        # night, which is the same as having no incremental profiling at all.
        async with connector:
            first = await connector.snapshot(PATH)
            second = await connector.snapshot(PATH)
        assert first.identifier == second.identifier

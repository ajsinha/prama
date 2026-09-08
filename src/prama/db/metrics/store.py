"""The metric history store.

Append-only, columnar, and queried through DuckDB. It lives under ``prama.db``
because it is *Prama's own store* — the same reason ``EvidenceBase`` does — even
though it is a different engine from the relational one. The platform has more
than one store; it has exactly one package that owns persistence.

Parquet rather than rows in the relational database, for a reason that only
appears at scale: this is a high-cardinality time series. One tenant with 100,000
columns profiled daily writes tens of millions of points a year, and the queries
a monitor asks are always "one series, ordered by time" — the shape a columnar
file answers in a single scan and a row store answers by index-hopping.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from prama.core.clock import Clock, SystemClock
from prama.core.errors import DatabaseError
from prama.core.log import get_logger
from prama.db.metrics.model import MetricPoint, MetricSeries

_log = get_logger(__name__)

COLUMNS = (
    "tenant_id",
    "dataset_id",
    "attribute",
    "segment",
    "metric",
    "value",
    "computed_at",
    "snapshot_id",
    "snapshot_exact",
    "sampling",
    "representative",
    "rows_examined",
    "run_id",
    "connection_id",
)


class MetricStore(ABC):
    """Record observations; read a series back."""

    @abstractmethod
    def record(self, points: list[MetricPoint]) -> int:
        """Append observations. Never updates: history is not editable."""

    @abstractmethod
    def series(
        self,
        tenant_id: str,
        dataset_id: str,
        metric: str,
        *,
        attribute: str | None = None,
        segment: str | None = None,
        since: datetime | None = None,
        limit: int = 10_000,
    ) -> MetricSeries:
        """One series, oldest first."""

    @abstractmethod
    def latest(
        self, tenant_id: str, dataset_id: str, *, metric: str | None = None
    ) -> list[MetricPoint]:
        """The most recent observation of each metric for a dataset."""

    @abstractmethod
    def count(self, tenant_id: str) -> int: ...


class ParquetMetricStore(MetricStore):
    """Partitioned Parquet, read through DuckDB.

    Writes are buffered and flushed in batches: a profile of a wide table
    produces hundreds of points at once, and one file per point would turn a
    columnar store into a small-file problem — the classic way a data lake
    becomes slower than the database it replaced.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        clock: Clock | None = None,
        flush_threshold: int = 1_000,
    ) -> None:
        self._root = Path(root).expanduser()
        self._clock = clock or SystemClock()
        self._flush_threshold = flush_threshold
        self._buffer: list[MetricPoint] = []
        self._lock = threading.Lock()
        self._root.mkdir(parents=True, exist_ok=True)

    # -- writing -----------------------------------------------------------

    def record(self, points: list[MetricPoint]) -> int:
        if not points:
            return 0
        with self._lock:
            self._buffer.extend(points)
            if len(self._buffer) >= self._flush_threshold:
                return self._flush_locked()
        return len(points)

    def flush(self) -> int:
        with self._lock:
            return self._flush_locked()

    def _flush_locked(self) -> int:
        if not self._buffer:
            return 0
        import pyarrow as pa
        import pyarrow.parquet as pq

        rows = [point.to_row() for point in self._buffer]
        written = len(rows)
        self._buffer.clear()

        by_partition: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            moment = row["computed_at"].astimezone(UTC)
            row["computed_at"] = moment.replace(tzinfo=None)
            by_partition.setdefault((row["tenant_id"], moment.strftime("%Y-%m-%d")), []).append(row)

        for (tenant, day), partition_rows in by_partition.items():
            directory = self._partition(tenant, day)
            directory.mkdir(parents=True, exist_ok=True)
            table = pa.Table.from_pylist(partition_rows, schema=_arrow_schema())
            # A new file per flush, never an append: Parquet has no append, and
            # rewriting a file to add rows is how a store loses data on a crash.
            name = f"part-{self._clock.epoch_millis()}-{len(partition_rows)}.parquet"
            pq.write_table(table, directory / name, compression="zstd")
        _log.debug("recorded %d metric point(s)", written)
        return written

    def _partition(self, tenant_id: str, day: str) -> Path:
        return self._root / f"tenant={tenant_id}" / f"day={day}"

    # -- reading -----------------------------------------------------------

    def series(
        self,
        tenant_id: str,
        dataset_id: str,
        metric: str,
        *,
        attribute: str | None = None,
        segment: str | None = None,
        since: datetime | None = None,
        limit: int = 10_000,
    ) -> MetricSeries:
        self.flush()
        predicates = ["tenant_id = ?", "dataset_id = ?", "metric = ?"]
        parameters: list[Any] = [tenant_id, dataset_id, metric]
        predicates.append("attribute IS NULL" if attribute is None else "attribute = ?")
        if attribute is not None:
            parameters.append(attribute)
        predicates.append("segment IS NULL" if segment is None else "segment = ?")
        if segment is not None:
            parameters.append(segment)
        if since is not None:
            predicates.append("computed_at >= ?")
            parameters.append(since.astimezone(UTC).replace(tzinfo=None))

        rows = self._query(
            f"SELECT {', '.join(COLUMNS)} FROM metrics WHERE {' AND '.join(predicates)} "
            f"ORDER BY computed_at LIMIT {int(limit)}",
            parameters,
            tenant_id,
        )
        return MetricSeries(
            dataset_id=dataset_id,
            metric=metric,
            attribute=attribute,
            segment=segment,
            points=tuple(_point(row) for row in rows),
        )

    def latest(
        self, tenant_id: str, dataset_id: str, *, metric: str | None = None
    ) -> list[MetricPoint]:
        self.flush()
        predicates = ["tenant_id = ?", "dataset_id = ?"]
        parameters: list[Any] = [tenant_id, dataset_id]
        if metric is not None:
            predicates.append("metric = ?")
            parameters.append(metric)
        rows = self._query(
            f"SELECT {', '.join(COLUMNS)} FROM metrics WHERE {' AND '.join(predicates)} "
            f"QUALIFY row_number() OVER ("
            f"  PARTITION BY metric, attribute, segment ORDER BY computed_at DESC) = 1 "
            f"ORDER BY metric, attribute",
            parameters,
            tenant_id,
        )
        return [_point(row) for row in rows]

    def count(self, tenant_id: str) -> int:
        self.flush()
        rows = self._query(
            "SELECT count(*) AS n FROM metrics WHERE tenant_id = ?", [tenant_id], tenant_id
        )
        return int(rows[0][0]) if rows else 0

    def purge_before(self, tenant_id: str, cutoff: datetime) -> int:
        """Drop whole day partitions older than *cutoff*.

        Retention by partition drop rather than row deletion: an append-only
        store that starts deleting rows is no longer append-only, and the
        cheapest correct deletion is removing a file nobody will read again.
        """
        removed = 0
        boundary = cutoff.astimezone(UTC).strftime("%Y-%m-%d")
        tenant_root = self._root / f"tenant={tenant_id}"
        if not tenant_root.is_dir():
            return 0
        for directory in sorted(tenant_root.iterdir()):
            if not directory.name.startswith("day="):
                continue
            if directory.name.removeprefix("day=") < boundary:
                for file in directory.iterdir():
                    file.unlink()
                    removed += 1
                directory.rmdir()
        return removed

    # -- internals ---------------------------------------------------------

    def _query(self, sql: str, parameters: list[Any], tenant_id: str) -> list[tuple[Any, ...]]:
        import duckdb

        pattern = str(self._root / f"tenant={tenant_id}" / "**" / "*.parquet")
        # DuckDB will not accept a prepared parameter inside a view definition,
        # so the glob is inlined. The value is a ULID from our own store and is
        # quote-escaped regardless; a path is not a place to be casual.
        escaped = pattern.replace("'", "''")
        connection = duckdb.connect(":memory:")
        try:
            connection.execute(
                f"CREATE VIEW metrics AS "
                f"SELECT * FROM read_parquet('{escaped}', union_by_name=true)"
            )
            return connection.execute(sql, parameters).fetchall()
        except duckdb.IOException:
            # No files yet for this tenant. An empty history is a normal state
            # on day one, not an error.
            return []
        except duckdb.Error as exc:  # pragma: no cover - defensive
            raise DatabaseError(
                "the metric history could not be read",
                code="DB.METRICS_UNREADABLE",
                remedy="Check that the metric store path is readable and not corrupt.",
                context={"root": str(self._root), "detail": str(exc)[:200]},
                cause=exc,
            ) from exc
        finally:
            connection.close()


class MemoryMetricStore(MetricStore):
    """An in-process store, for tests and for a single-shot CLI run."""

    def __init__(self) -> None:
        self._points: list[MetricPoint] = []

    def record(self, points: list[MetricPoint]) -> int:
        self._points.extend(points)
        return len(points)

    def series(
        self,
        tenant_id: str,
        dataset_id: str,
        metric: str,
        *,
        attribute: str | None = None,
        segment: str | None = None,
        since: datetime | None = None,
        limit: int = 10_000,
    ) -> MetricSeries:
        selected = [
            p
            for p in self._points
            if p.tenant_id == tenant_id
            and p.dataset_id == dataset_id
            and p.metric == metric
            and p.attribute == attribute
            and p.segment == segment
            and (since is None or p.computed_at >= since)
        ]
        selected.sort(key=lambda p: p.computed_at)
        return MetricSeries(
            dataset_id=dataset_id,
            metric=metric,
            attribute=attribute,
            segment=segment,
            points=tuple(selected[:limit]),
        )

    def latest(
        self, tenant_id: str, dataset_id: str, *, metric: str | None = None
    ) -> list[MetricPoint]:
        newest: dict[tuple[Any, ...], MetricPoint] = {}
        for point in self._points:
            if point.tenant_id != tenant_id or point.dataset_id != dataset_id:
                continue
            if metric is not None and point.metric != metric:
                continue
            key = point.key
            if key not in newest or point.computed_at > newest[key].computed_at:
                newest[key] = point
        return sorted(newest.values(), key=lambda p: (p.metric, p.attribute or ""))

    def count(self, tenant_id: str) -> int:
        return sum(1 for p in self._points if p.tenant_id == tenant_id)


def _arrow_schema() -> Any:
    import pyarrow as pa

    return pa.schema(
        [
            ("tenant_id", pa.string()),
            ("dataset_id", pa.string()),
            ("attribute", pa.string()),
            ("segment", pa.string()),
            ("metric", pa.string()),
            ("value", pa.float64()),
            # Naive microsecond timestamps, understood as UTC. Everything in
            # Prama is UTC by construction, so no information is lost, and a
            # tz-aware Parquet column would drag in a timezone database purely
            # to re-attach an offset we already know is zero. The same reasoning
            # gave the relational schema ISO-8601 text.
            ("computed_at", pa.timestamp("us")),
            ("snapshot_id", pa.string()),
            ("snapshot_exact", pa.bool_()),
            ("sampling", pa.string()),
            ("representative", pa.bool_()),
            ("rows_examined", pa.int64()),
            ("run_id", pa.string()),
            ("connection_id", pa.string()),
        ]
    )


def _point(row: tuple[Any, ...]) -> MetricPoint:
    computed_at = row[6]
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=UTC)
    return MetricPoint(
        tenant_id=row[0],
        dataset_id=row[1],
        attribute=row[2],
        segment=row[3],
        metric=row[4],
        value=float(row[5]),
        computed_at=computed_at,
        snapshot_id=row[7],
        snapshot_exact=bool(row[8]),
        sampling=row[9],
        representative=bool(row[10]),
        rows_examined=int(row[11] or 0),
        run_id=row[12],
        connection_id=row[13],
    )


def retention_cutoff(days: int, *, clock: Clock | None = None) -> datetime:
    return (clock or SystemClock()).now() - timedelta(days=days)

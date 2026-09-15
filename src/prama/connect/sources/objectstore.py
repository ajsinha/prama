"""Object stores: S3, Azure Blob, Google Cloud Storage.

Where a bank's data lake actually lives, and the source most often modelled
wrongly. The mistake is to treat every object as a dataset, which turns one
table with four years of daily partitions into fourteen hundred "tables" and
makes the catalogue useless the moment it is built.

A dataset here is a **prefix**. ``s3://lake/risk/positions/`` holding
``booked=2026-04-01/part-0.parquet`` and nine hundred siblings is one dataset
with a partition column, and Prama says so — which is also what lets segmented
profiling read one day without touching the rest.

Everything runs through DuckDB's httpfs, which is already a dependency. That is
worth more than it sounds: no cloud SDK, no per-provider client to keep current,
and the same code path reaches ``s3://``, ``gs://`` and ``az://``. A bank that
will not install boto3 on a server can still be read.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import re
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from prama.connect.capability import CapabilityMatrix, PushdownFeature
from prama.connect.sources.filesystem import READERS
from prama.connect.spi import (
    ColumnSchema,
    Connector,
    ConnectorError,
    DiscoveredObject,
    HealthReport,
    HealthState,
    ObjectSchema,
    SamplePlan,
    SamplingStrategy,
    Snapshot,
    SnapshotKind,
    SourceKind,
    UnauthorisedError,
    Verification,
)
from prama.core.clock import utc_now
from prama.core.errors import ValidationError, first_line
from prama.core.log import get_logger
from prama.core.registry import PluginManifest

if TYPE_CHECKING:  # pragma: no cover
    import pyarrow as pa

_log = get_logger(__name__)

CAPABILITIES = CapabilityMatrix.of(
    PushdownFeature.SQL,
    PushdownFeature.FILTER,
    PushdownFeature.AGGREGATION,
    PushdownFeature.PREDICATE_PUSHDOWN,
    PushdownFeature.WINDOW,
    PushdownFeature.REGEX,
    PushdownFeature.SAMPLING,
    PushdownFeature.PARTITION_PRUNING,
    PushdownFeature.QUANTILES,
    PushdownFeature.APPROX_DISTINCT,
    PushdownFeature.JSON_PATH,
    PushdownFeature.EXACT_SNAPSHOT,
    PushdownFeature.PARALLEL_READ,
    regex_flavour="re2",
    max_decimal_precision=38,
    nulls_sort_first=True,
)

#: Schemes DuckDB's httpfs can address. Registered rather than hardcoded so an
#: estate on a private S3-compatible store is not a special case.
SCHEMES: dict[str, str] = {
    "s3": "Amazon S3, or any S3-compatible store",
    "gs": "Google Cloud Storage",
    "gcs": "Google Cloud Storage",
    "az": "Azure Blob Storage",
    "abfss": "Azure Data Lake Storage Gen2",
    "r2": "Cloudflare R2",
}

#: ``booked=2026-04-01`` — the Hive convention, and the one that tells us both
#: the partition column and its value.
_HIVE = re.compile(r"^(?P<column>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")

#: A bare date or number used as a directory: ``2026-04-01/`` or ``20260401/``.
#: Common, and carries a value with no column name, so the column is unknown
#: and Prama says so rather than inventing one.
_BARE_PARTITION = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{6,8}$|^\d{1,4}$")

BATCH_ROWS = 50_000

#: Objects sampled to identify a dataset's format and schema. Reading every one
#: of a million-object prefix to answer "what is this" is not a question worth
#: that price.
SCHEMA_PROBE_OBJECTS = 1


class ObjectStoreConnector(Connector):
    """A prefix in an object store, read as datasets rather than as files."""

    plugin_key = "objectstore"
    source_kind = SourceKind.OBJECT_STORE
    credential_field = "secret_access_key"

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.describe_manifest(
            key="objectstore",
            display_name="Object store (S3, Azure Blob, GCS)",
            capabilities=CAPABILITIES.to_capabilities(),
            description=(
                "A bucket or container. Prefixes are read as datasets rather than "
                "objects as tables, so a partitioned table stays one dataset instead "
                "of becoming a thousand. Read-only: nothing is ever written back."
            ),
            verification=Verification.VERIFIED,
        )

    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._uri = str(self.config.get("uri", "")).rstrip("/")
        self._endpoint = str(self.config.get("endpoint", ""))
        self._region = str(self.config.get("region", "us-east-1"))
        self._access_key_id = str(self.config.get("access_key_id", ""))
        self._secret_access_key = str(self.config.get("secret_access_key", ""))
        self._session_token = str(self.config.get("session_token", ""))
        self._use_ssl = str(self.config.get("use_ssl", "true")).lower() != "false"
        self._url_style = str(self.config.get("url_style", "vhost"))
        self._file_pattern = str(self.config.get("file_pattern", "*"))
        self._max_objects = int(self.config.get("max_objects", 50_000))
        self._connection: Any = None
        self._listing: list[_StoredObject] | None = None

    # -- lifecycle ---------------------------------------------------------

    async def open(self) -> None:
        # Before connecting, not after. `_connect` builds `TYPE <scheme>` into
        # DuckDB SQL, so an unrecognised scheme produced a raw DuckDB exception
        # about secret providers — while `health()` had always answered the same
        # question correctly and said MISCONFIGURED. The two entry points
        # disagreed, and `async with connector:` is the one everything else
        # uses. QA round 4, `CON-153`.
        if detail := self._scheme_problem():
            raise ValidationError(
                detail,
                remedy=f"Set `uri` to one of: {', '.join(sorted(SCHEMES))}.",
                context={"uri": self._uri, "scheme": self.scheme},
            )
        self._connection = await asyncio.to_thread(self._connect)

    async def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._listing = None

    def _connect(self) -> Any:
        import duckdb

        connection = duckdb.connect()
        connection.execute("INSTALL httpfs")
        connection.execute("LOAD httpfs")
        connection.execute(self._secret_statement())
        return connection

    def _secret_statement(self) -> str:
        """Credentials handed to DuckDB, never written anywhere.

        Built here rather than stored, because the connection record holds a
        vault reference and the value only exists for the life of the process.
        """
        scheme = self.scheme
        parts = [f"TYPE {('s3' if scheme in ('s3', 'r2') else scheme)}"]
        if self._access_key_id:
            parts.append(f"KEY_ID '{_escape(self._access_key_id)}'")
        if self._secret_access_key:
            parts.append(f"SECRET '{_escape(self._secret_access_key)}'")
        if self._session_token:
            parts.append(f"SESSION_TOKEN '{_escape(self._session_token)}'")
        if self._endpoint:
            parts.append(f"ENDPOINT '{_escape(self._endpoint)}'")
        parts.append(f"REGION '{_escape(self._region)}'")
        parts.append(f"USE_SSL {'true' if self._use_ssl else 'false'}")
        parts.append(f"URL_STYLE '{_escape(self._url_style)}'")
        if not self._access_key_id:
            # No key given: fall back to the instance's own role. The normal
            # arrangement in a cloud estate, and better than a key in a config.
            parts = [p for p in parts if not p.startswith(("KEY_ID", "SECRET", "SESSION_TOKEN"))]
            parts.insert(1, "PROVIDER credential_chain")
        return f"CREATE OR REPLACE SECRET prama_store ({', '.join(parts)})"

    @property
    def scheme(self) -> str:
        return self._uri.split("://", 1)[0].lower() if "://" in self._uri else ""

    def _scheme_problem(self) -> str:
        """Why this URI is not an object store, or "" if it is.

        One sentence, derived once. `open()` refuses on it and `health()`
        reports it; when the wording lived only in `health()`, `open()` had no
        way to say the same thing and said DuckDB's thing instead.
        """
        if self.scheme in SCHEMES:
            return ""
        return (
            f"{self._uri!r} does not name an object store. "
            f"Expected one of: {', '.join(sorted(SCHEMES))}."
        )

    # -- contract ----------------------------------------------------------

    async def health(self) -> HealthReport:
        checked = utc_now()
        if problem := self._scheme_problem():
            return HealthReport(
                state=HealthState.MISCONFIGURED,
                detail=problem,
                checked_at=checked,
            )
        started = utc_now()
        try:
            objects = await self._list()
        except Exception as exc:  # classified below, then reported
            return HealthReport(
                state=self._classify(exc),
                detail=first_line(exc),
                checked_at=checked,
                missing_permissions=("s3:ListBucket",) if _is_denied(exc) else (),
            )
        datasets = _group(objects)
        return HealthReport(
            state=HealthState.HEALTHY,
            detail=f"{len(datasets)} dataset(s) across {len(objects):,} object(s)",
            checked_at=checked,
            latency_ms=(utc_now() - started).total_seconds() * 1000,
        )

    async def discover(self, path: tuple[str, ...] = ()) -> list[DiscoveredObject]:
        """Datasets, not objects. Largest first."""
        datasets = _group(await self._list())
        found = [
            DiscoveredObject(
                path=dataset.path,
                kind=dataset.kind,
                estimated_rows=dataset.total_rows,
                estimated_bytes=dataset.total_bytes,
                comment=dataset.describe(),
                tags=dataset.partition_columns,
            )
            for dataset in datasets
            if self.policy.permits_path(dataset.path)
            and (not path or dataset.path[: len(path)] == path)
        ]
        found.sort(key=lambda o: (-(o.estimated_bytes or 0), o.qualified_name))
        return found

    async def describe(self, path: tuple[str, ...]) -> ObjectSchema:
        dataset = await self._dataset(path)
        statement = f"SELECT * FROM {dataset.reader(probe=True)} LIMIT 0"
        relation = await asyncio.to_thread(lambda: self._duck().cursor().sql(statement))
        columns = tuple(
            ColumnSchema(name=name, type_name=str(dtype), ordinal=index)
            for index, (name, dtype) in enumerate(
                zip(relation.columns, relation.types, strict=True)
            )
        )
        return ObjectSchema(
            path=path,
            columns=columns,
            partition_columns=dataset.partition_columns,
            estimated_rows=dataset.total_rows,
        )

    async def snapshot(self, path: tuple[str, ...]) -> Snapshot:
        """A digest of what the prefix contained when it was read.

        Keys, sizes and modification times of every object, hashed. Exact in
        the sense that matters: if any object is added, removed or rewritten,
        the identifier changes, so a stale profile can never be mistaken for a
        current one.
        """
        dataset = await self._dataset(path)
        digest = hashlib.blake2b(digest_size=16)
        for stored in dataset.objects:
            digest.update(f"{stored.key}:{stored.size}:{stored.rows}".encode())
        return Snapshot(
            # Exact only when every object's size and row count is known: an
            # object rewritten in place under the same name leaves a key-only
            # digest untouched, and calling that exact would let incremental
            # profiling skip data that changed underneath it.
            kind=(SnapshotKind.FILE_DIGEST if dataset.is_measured else SnapshotKind.OBJECT_LISTING),
            identifier=digest.hexdigest(),
            captured_at=utc_now(),
            detail={
                "objects": len(dataset.objects),
                "rows": dataset.total_rows,
                "bytes": dataset.total_bytes,
                "prefix": dataset.uri,
            },
        )

    async def read(
        self, path: tuple[str, ...], *, plan: SamplePlan | None = None
    ) -> AsyncIterator[pa.RecordBatch]:
        plan = plan or SamplePlan()
        self.require_predicate_support(plan)
        dataset = await self._dataset(path)
        query = self._select(dataset, plan)
        # A cursor, not the shared connection. A DuckDB connection carries one
        # result stream, so two concurrent reads on it close each other's —
        # which surfaces as "Query Stream is closed" from whichever lost, and
        # segmented profiling reads its segments concurrently by design. A
        # cursor is an independent connection over the same database, so the
        # registered credentials still apply.
        cursor = await asyncio.to_thread(lambda: self._duck().cursor())
        try:
            reader = await asyncio.to_thread(lambda: _arrow_reader(cursor.sql(query)))
            while True:
                batch = await asyncio.to_thread(_next_batch, reader)
                if batch is None:
                    return
                yield batch
        finally:
            await asyncio.to_thread(cursor.close)

    def pushdown_capabilities(self) -> tuple[Any, ...]:
        return CAPABILITIES.to_capabilities()

    # -- internals ---------------------------------------------------------

    def _select(self, dataset: _Dataset, plan: SamplePlan) -> str:
        source = dataset.reader()
        if plan.predicate:
            # Before the sample, so the sample is drawn from the segment rather
            # than the segment taken from the sample.
            source = f"{source} WHERE {plan.predicate}"
        if plan.strategy is SamplingStrategy.FULL:
            return f"SELECT * FROM {source}"
        if plan.strategy is SamplingStrategy.HEAD:
            return f"SELECT * FROM {source} LIMIT {int(plan.rows or 1000)}"
        if plan.fraction is not None:
            percent = max(0.0, min(100.0, plan.fraction * 100))
            return f"SELECT * FROM {source} USING SAMPLE {percent} PERCENT (bernoulli, {plan.seed})"
        return (
            f"SELECT * FROM {source} USING SAMPLE {int(plan.rows or 1000)} ROWS "
            f"(reservoir, {plan.seed})"
        )

    async def _dataset(self, path: tuple[str, ...]) -> _Dataset:
        if not self.policy.permits_path(path):
            raise UnauthorisedError(
                f"the read policy for this connection does not allow {'/'.join(path)}",
                remedy="Add the prefix to the connection's allowed paths.",
                context={"path": "/".join(path)},
            )
        for dataset in _group(await self._list()):
            if dataset.path == path:
                return dataset
        raise ConnectorError(
            f"no dataset at {'/'.join(path)}",
            code="CONNECT.OBJECT_MISSING",
            remedy="Discovery lists the prefixes this store holds.",
            context={"path": "/".join(path)},
        )

    async def _list(self) -> list[_StoredObject]:
        if self._listing is None:
            self._listing = await asyncio.to_thread(self._glob)
        return self._listing

    def _glob(self) -> list[_StoredObject]:
        pattern = f"{self._uri}/**/{self._file_pattern}"
        rows = (
            self._duck()
            .sql(f"SELECT file FROM glob('{_escape(pattern)}') LIMIT {self._max_objects + 1}")
            .fetchall()
        )
        if len(rows) > self._max_objects:
            # Truncating silently would report a prefix as smaller than it is
            # and profile a fraction of it as though it were the whole.
            raise ConnectorError(
                f"this prefix holds more than {self._max_objects:,} objects",
                code="CONNECT.TOO_MANY_OBJECTS",
                remedy=(
                    "Point the connection at a narrower prefix, or raise max_objects. "
                    "Reading a partial listing would profile part of the data as "
                    "though it were all of it."
                ),
                context={"uri": self._uri, "maximum": self._max_objects},
            )
        keys = [str(row[0]) for row in rows if _suffix(str(row[0])) in READERS]
        return self._with_metadata(keys)

    def _with_metadata(self, keys: list[str]) -> list[_StoredObject]:
        """Attach row counts and sizes where they can be had for free.

        Parquet keeps both in a footer, and DuckDB will read the footers of a
        whole glob in one call — so for the format a lake actually uses, a
        listing brings back exact row counts without touching a single data
        page. Every other format gets keys alone, and reports the difference
        rather than guessing: a row count invented from an object count would
        be wrong by whatever the compression ratio happens to be.
        """
        parquet = [k for k in keys if _suffix(k) in (".parquet", ".pq")]
        measured: dict[str, tuple[int | None, int | None]] = {}
        if parquet:
            try:
                for name, count, size in (
                    self._duck()
                    .sql(
                        "SELECT file_name, num_rows, file_size_bytes FROM "
                        f"parquet_file_metadata('{_escape(self._uri)}/**/*.parquet')"
                    )
                    .fetchall()
                ):
                    measured[str(name)] = (
                        int(size) if size is not None else None,
                        int(count) if count is not None else None,
                    )
            except Exception as exc:  # a footer we cannot read is not fatal
                _log.debug("parquet footers unavailable under %s: %s", self._uri, exc)
        return [
            _StoredObject(
                key=key,
                size=measured.get(key, (None, None))[0],
                rows=measured.get(key, (None, None))[1],
            )
            for key in keys
        ]

    def _duck(self) -> Any:
        if self._connection is None:
            raise ConnectorError(
                "the object store connector was used before it was opened",
                code="CONNECT.NOT_OPEN",
                remedy="Use the connector as an async context manager, or call open() first.",
            )
        return self._connection

    @staticmethod
    def _classify(exc: Exception) -> HealthState:
        if _is_denied(exc):
            return HealthState.UNAUTHORISED
        message = str(exc).lower()
        if "no such bucket" in message or "not found" in message:
            return HealthState.MISCONFIGURED
        return HealthState.UNREACHABLE


def _is_denied(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(word in message for word in ("access denied", "forbidden", "403", "signature"))


def _arrow_reader(relation: Any) -> Any:
    """A streaming reader, whatever this DuckDB calls it.

    ``fetch_arrow_reader`` was renamed to ``to_arrow_reader``; picking one and
    hoping turns a version difference into an AttributeError on somebody
    else's machine rather than on ours.
    """
    factory = getattr(relation, "to_arrow_reader", None) or relation.fetch_arrow_reader
    return factory(BATCH_ROWS)


def _next_batch(reader: Any) -> Any:
    try:
        return reader.read_next_batch()
    except StopIteration:
        return None


def _escape(value: str) -> str:
    return value.replace("'", "''")


def _suffix(key: str) -> str:
    name = key.rsplit("/", 1)[-1]
    return f".{name.rsplit('.', 1)[-1].lower()}" if "." in name else ""


@dataclasses.dataclass(frozen=True, slots=True)
class _StoredObject:
    key: str
    #: Known only where the format carries it in a footer we can read cheaply.
    #: ``None`` is reported as unknown rather than guessed.
    size: int | None = None
    rows: int | None = None

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(self.key.split("://", 1)[-1].split("/"))


@dataclasses.dataclass(frozen=True, slots=True)
class _Dataset:
    """A prefix and the objects under it, treated as one thing."""

    path: tuple[str, ...]
    objects: tuple[_StoredObject, ...]
    partition_columns: tuple[str, ...]
    partition_depth: int

    @property
    def kind(self) -> str:
        return _suffix(self.objects[0].key).lstrip(".") or "objects"

    @property
    def total_bytes(self) -> int | None:
        sizes = [o.size for o in self.objects if o.size is not None]
        return sum(sizes) if len(sizes) == len(self.objects) else None

    @property
    def total_rows(self) -> int | None:
        counts = [o.rows for o in self.objects if o.rows is not None]
        return sum(counts) if len(counts) == len(self.objects) else None

    @property
    def is_measured(self) -> bool:
        """Whether every object's size and row count is known.

        Decides how strong a snapshot this dataset can honestly offer.
        """
        return all(o.size is not None and o.rows is not None for o in self.objects)

    @property
    def uri(self) -> str:
        return self.objects[0].key.rsplit("/", 1 + self.partition_depth)[0]

    def describe(self) -> str:
        parts = [f"{len(self.objects):,} object(s)"]
        if self.total_rows is not None:
            parts.insert(0, f"{self.total_rows:,} rows")
        if self.partition_columns:
            parts.append(f"partitioned by {', '.join(self.partition_columns)}")
        elif self.partition_depth:
            parts.append(f"{self.partition_depth} level(s) of unnamed partitioning")
        return "; ".join(parts)

    def reader(self, *, probe: bool = False) -> str:
        """The DuckDB expression that reads this dataset.

        One glob across every object, so a partitioned table is read as the
        single table it is. ``hive_partitioning`` turns ``booked=2026-04-01``
        into a real column, which is what makes segmenting a lake dataset by
        business date work without anyone parsing a path.
        """
        function = READERS[_suffix(self.objects[0].key)]
        target = self.objects[0].key if probe else self._glob()
        options = ""
        if function == "read_parquet" and self.partition_columns:
            options = ", hive_partitioning = true"
        elif function == "read_parquet":
            options = ", union_by_name = true"
        return f"{function}('{_escape(target)}'{options})"

    def _glob(self) -> str:
        wildcards = "/".join(["*"] * self.partition_depth)
        return f"{self.uri}/{wildcards}/*" if wildcards else f"{self.uri}/*"


def _group(objects: list[_StoredObject]) -> list[_Dataset]:
    """Fold a flat object listing into datasets.

    The judgement that decides whether this connector is useful. Every object
    as its own dataset gives a catalogue of a thousand daily partitions and
    nobody can find anything; one dataset for the whole bucket gives a single
    entry that means nothing. The rule is that trailing path segments which
    look like partitions — ``booked=2026-04-01`` or a bare ``2026-04-01`` — are
    part of the dataset rather than a dataset of their own.
    """
    grouped: dict[tuple[tuple[str, ...], int], list[_StoredObject]] = {}
    columns: dict[tuple[tuple[str, ...], int], tuple[str, ...]] = {}
    for stored in objects:
        directories = stored.segments[:-1]
        depth, named = _partition_depth(directories)
        key = (directories[: len(directories) - depth], depth)
        grouped.setdefault(key, []).append(stored)
        columns.setdefault(key, named)
    datasets = [
        _Dataset(
            path=prefix,
            objects=tuple(sorted(members, key=lambda o: o.key)),
            partition_columns=columns[prefix, depth],
            partition_depth=depth,
        )
        for (prefix, depth), members in grouped.items()
    ]
    datasets.sort(key=lambda d: d.path)
    return datasets


def _partition_depth(directories: tuple[str, ...]) -> tuple[int, tuple[str, ...]]:
    """How many trailing directories are partitions, and their column names.

    Only *trailing* ones. ``risk/positions/booked=2026-04-01`` partitions on
    booked; ``risk/2026/positions`` does not partition on 2026, because the
    year is not the last thing before the file and a directory in the middle
    is part of the dataset's identity rather than a slice of it.
    """
    depth = 0
    named: list[str] = []
    for segment in reversed(directories):
        hive = _HIVE.match(segment)
        if hive:
            named.append(hive.group("column"))
            depth += 1
            continue
        if _BARE_PARTITION.match(segment):
            depth += 1
            continue
        break
    return depth, tuple(reversed(named))

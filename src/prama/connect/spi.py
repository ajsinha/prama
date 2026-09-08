"""The connector contract.

Every source Prama can reach — a warehouse, a Postgres instance, a landing zone
of CSV files, a Kafka topic, a COBOL feed — implements this one interface. The
uniformity is what lets a control written once run against any of them, and it
is why the awkward sources are first-class rather than perpetually "coming soon".

Eight operations, and the split between them matters:

    discover()               what exists here?
    describe()               what shape is this object?
    snapshot()               name the exact state I am about to read
    read() / sample()        give me rows, as Arrow
    pushdown_capabilities()  what may the compiler rely on?
    execute_plan()           run this at the source and return metrics
    health()                 can I reach you, and may I read?

A connector that cannot push down still works: the engine falls back to reading
Arrow batches and evaluating locally, with the cost implication shown to the
author rather than hidden. That fallback is what makes a new connector cheap to
write — correctness first, performance when it earns its place.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING, Any

from prama.connect.capability import PushdownFeature
from prama.core.errors import PramaError
from prama.core.registry import Capability, Plugin, PluginManifest

if TYPE_CHECKING:  # pragma: no cover - import cost avoided at runtime
    import pyarrow as pa


class SourceKind(enum.Enum):
    """The family a source belongs to.

    Determines which controls make sense: a feed has arrival and completeness
    controls that a table does not, and a stream has neither in the same form.
    """

    RELATIONAL = "relational"
    WAREHOUSE = "warehouse"
    LAKEHOUSE = "lakehouse"
    OBJECT_STORE = "object_store"
    FILESYSTEM = "filesystem"
    FEED = "feed"
    STREAM = "stream"
    API = "api"
    DOCUMENT = "document"
    MAINFRAME = "mainframe"


class ConnectorError(PramaError):
    """A source could not be reached, read, or understood."""

    code = "CONNECT.ERROR"


class UnreachableError(ConnectorError):
    code = "CONNECT.UNREACHABLE"


class UnauthorisedError(ConnectorError):
    """Reached the source; not permitted to do what was asked.

    Distinguished from unreachable because the remedy is completely different:
    one is a network problem, the other is an access request.
    """

    code = "CONNECT.UNAUTHORISED"


class BudgetExceededError(ConnectorError):
    code = "CONNECT.BUDGET_EXCEEDED"


class HealthState(enum.Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"
    UNAUTHORISED = "unauthorised"


@dataclasses.dataclass(frozen=True, slots=True)
class HealthReport:
    """The answer to "can I reach you, and may I read?", in business language.

    ``detail`` is written for a data architect, not an engineer: "connected, but
    this role cannot read the RISK schema" rather than a driver stack trace.
    """

    state: HealthState
    detail: str = ""
    latency_ms: float | None = None
    checked_at: datetime | None = None
    missing_permissions: tuple[str, ...] = ()

    @property
    def is_usable(self) -> bool:
        return self.state in (HealthState.HEALTHY, HealthState.DEGRADED)

    @property
    def needs_access_request(self) -> bool:
        """Whether the fix is an access request rather than a network change."""
        return self.state is HealthState.UNAUTHORISED or bool(self.missing_permissions)


@dataclasses.dataclass(frozen=True, slots=True)
class DiscoveredObject:
    """Something a source holds that could become a dataset.

    Ranked for a *business* reader: size, recency and usage, not alphabetical
    order. An alphabetical tree of four thousand objects is not discovery.
    """

    path: tuple[str, ...]
    kind: str = "table"
    estimated_rows: int | None = None
    estimated_bytes: int | None = None
    last_modified: datetime | None = None
    comment: str = ""
    tags: tuple[str, ...] = ()

    @property
    def qualified_name(self) -> str:
        return ".".join(self.path)

    @property
    def leaf(self) -> str:
        return self.path[-1] if self.path else ""


@dataclasses.dataclass(frozen=True, slots=True)
class ColumnSchema:
    name: str
    type_name: str
    nullable: bool = True
    ordinal: int = 0
    comment: str = ""
    precision: int | None = None
    scale: int | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class ObjectSchema:
    """The physical shape of one object."""

    path: tuple[str, ...]
    columns: tuple[ColumnSchema, ...]
    partition_columns: tuple[str, ...] = ()
    estimated_rows: int | None = None

    def column(self, name: str) -> ColumnSchema | None:
        return next((c for c in self.columns if c.name == name), None)

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)


class SnapshotKind(enum.Enum):
    """How exactly a source can name the state that was read."""

    ICEBERG_SNAPSHOT = "iceberg_snapshot"
    DELTA_VERSION = "delta_version"
    TRANSACTION_ID = "transaction_id"
    SCN = "scn"
    LSN = "lsn"
    FILE_DIGEST = "file_digest"
    OFFSET_RANGE = "offset_range"
    WALL_CLOCK = "wall_clock"

    @property
    def is_exact(self) -> bool:
        """Whether replaying against this identifier is guaranteed reproducible.

        ``WALL_CLOCK`` is not: it records when we looked, not what we saw. A
        snapshot that cannot guarantee reproduction must say so, because an
        evidence record that silently implies one is worse than none at all.
        """
        return self is not SnapshotKind.WALL_CLOCK


@dataclasses.dataclass(frozen=True, slots=True)
class Snapshot:
    """An identifier for the exact data state a control saw.

    Recorded on every evidence record. Where a source cannot supply an exact
    one, ``exact`` is False and the evidence says so rather than pretending.
    """

    kind: SnapshotKind
    identifier: str
    captured_at: datetime
    detail: dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def exact(self) -> bool:
        return self.kind.is_exact

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "id": self.identifier,
            "captured_at": self.captured_at,
            "exact": self.exact,
            **({"detail": self.detail} if self.detail else {}),
        }


class SamplingStrategy(enum.Enum):
    FULL = "full"
    HEAD = "head"
    SYSTEMATIC = "systematic"
    STRATIFIED = "stratified"
    RESERVOIR = "reservoir"
    RECENT_PARTITIONS = "recent_partitions"

    @property
    def is_representative(self) -> bool:
        """Whether a rate measured on this sample may be extrapolated.

        ``HEAD`` is not: the first thousand rows of a table sorted by insertion
        are the oldest thousand, and a defect rate measured there says nothing
        about the whole. It exists for previewing shape, never for a verdict.
        """
        return self is not SamplingStrategy.HEAD


@dataclasses.dataclass(frozen=True, slots=True)
class SamplePlan:
    """How much to read, and what may honestly be said about the result."""

    strategy: SamplingStrategy = SamplingStrategy.FULL
    rows: int | None = None
    fraction: float | None = None
    seed: int = 0
    stratify_by: tuple[str, ...] = ()
    partitions: int | None = None
    #: A source-native filter restricting the read to one slice — the mechanism
    #: behind segmented profiling. A connector that cannot apply it MUST raise
    #: rather than ignore it: silently reading the whole object and labelling
    #: the result as one segment would attribute a table's data to a single day
    #: and is worse than refusing. Declare PREDICATE_PUSHDOWN to accept one.
    predicate: str = ""

    @property
    def is_complete(self) -> bool:
        """Whether this read sees the whole object.

        A predicate makes it not complete even under a full-scan strategy: the
        rates it measures are the segment's, and stating them as the dataset's
        would be a straightforward falsehood.
        """
        return self.strategy is SamplingStrategy.FULL and not self.predicate

    def describe(self) -> str:
        scope = f" where {self.predicate}" if self.predicate else ""
        if self.strategy is SamplingStrategy.FULL:
            return f"full scan{scope}"
        if self.fraction is not None:
            return f"{self.strategy.value} sample at {self.fraction * 100:g}%{scope}"
        if self.rows is not None:
            return f"{self.strategy.value} sample of {self.rows:,} rows{scope}"
        return f"{self.strategy.value}{scope}"


@dataclasses.dataclass(frozen=True, slots=True)
class ReadPolicy:
    """What a connection is permitted to do, set once by a data architect.

    Exists so a source owner can be shown a bounded promise rather than asked to
    trust one. A control plane that can saturate a production database is a
    control plane that gets switched off.
    """

    allowed_paths: tuple[str, ...] = ()
    max_bytes_scanned: int | None = None
    max_rows_read: int | None = None
    permitted_hours: tuple[int, ...] = ()
    default_sampling: SamplingStrategy = SamplingStrategy.FULL
    retain_failing_samples: bool = False
    max_concurrency: int = 4
    #: Ceiling on Prama-attributable load, as a fraction of source capacity.
    load_ceiling: float = 0.05

    def permits_path(self, path: tuple[str, ...]) -> bool:
        if not self.allowed_paths:
            return True
        qualified = ".".join(path)
        return any(
            qualified == allowed or qualified.startswith(allowed.rstrip("*"))
            for allowed in self.allowed_paths
        )

    def permits_now(self, hour: int) -> bool:
        return not self.permitted_hours or hour in self.permitted_hours


@dataclasses.dataclass(frozen=True, slots=True)
class ReadResult:
    """What a read actually cost, so the promise can be checked afterwards."""

    rows: int = 0
    bytes_scanned: int = 0
    duration_seconds: float = 0.0
    truncated_by_budget: bool = False


class Connector(Plugin, ABC):
    """One source type. Constructed from a configuration, never from a URL."""

    #: The family this source belongs to.
    source_kind: SourceKind = SourceKind.RELATIONAL
    #: Which configuration field a resolved credential fills. Declared by the
    #: connector rather than encoded in the reference, because a reference's
    #: fragment already means something else — which field of a JSON document
    #: to take — and one syntax cannot carry both meanings without producing
    #: failures nobody can read.
    credential_field: str = "password"

    def __init__(self, config: dict[str, Any], *, policy: ReadPolicy | None = None) -> None:
        self.config = config
        self.policy = policy or ReadPolicy()

    # -- lifecycle ---------------------------------------------------------

    async def open(self) -> None:
        """Acquire whatever the connector needs. Default: nothing."""
        return

    async def close(self) -> None:
        """Release it again. Default: nothing."""
        return

    async def __aenter__(self) -> Connector:
        await self.open()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # -- the contract ------------------------------------------------------

    @abstractmethod
    async def health(self) -> HealthReport:
        """Can this source be reached, and may we read from it?"""

    @abstractmethod
    async def discover(self, path: tuple[str, ...] = ()) -> list[DiscoveredObject]:
        """What exists here, ranked for a business reader."""

    @abstractmethod
    async def describe(self, path: tuple[str, ...]) -> ObjectSchema:
        """The physical shape of one object."""

    @abstractmethod
    async def snapshot(self, path: tuple[str, ...]) -> Snapshot:
        """Name the exact state about to be read."""

    @abstractmethod
    def read(
        self, path: tuple[str, ...], *, plan: SamplePlan | None = None
    ) -> AsyncIterator[pa.RecordBatch]:
        """Stream the object as Arrow record batches.

        Arrow because it is the one representation every backend already speaks,
        so a connector never has to know which engine will consume its output.
        """

    def pushdown_capabilities(self) -> tuple[Capability, ...]:
        """What the compiler may rely on. Default: nothing.

        Declaring nothing is a correct answer, not a failure: the engine reads
        Arrow and evaluates locally. A connector earns pushdown by claiming it.
        """
        return ()

    async def execute_plan(self, plan: Any) -> dict[str, Any]:  # noqa: ARG002
        """Run a compiled plan at the source and return its metrics.

        Only meaningful where ``pushdown_capabilities`` claims support; the
        default refusal is honest rather than a silent local fallback the caller
        did not ask for.
        """
        raise ConnectorError(
            f"{type(self).__name__} does not support pushdown execution",
            code="CONNECT.NO_PUSHDOWN",
            remedy=(
                "Run this control through the Arrow backend instead, or use a connector "
                "that declares a pushdown capability."
            ),
            context={"connector": type(self).__name__},
        )

    # -- helpers -----------------------------------------------------------

    def supports(self, capability: str) -> bool:
        return any(c.name == capability for c in self.pushdown_capabilities())

    def require_predicate_support(self, plan: SamplePlan) -> None:
        """Refuse a filtered read this connector cannot actually filter.

        The alternative is the quiet disaster: the predicate is dropped, the
        whole object is read, and the result is recorded as the profile of one
        segment. A table's data then appears as a single day's, every rate is
        wrong, and nothing looks broken. Better to fail where the truth is.
        """
        if plan.predicate and not self.supports(PushdownFeature.PREDICATE_PUSHDOWN.value):
            raise ConnectorError(
                f"{type(self).__name__} cannot restrict a read to part of an object",
                code="CONNECT.NO_PREDICATE",
                remedy=(
                    "Profile this object whole, or reach it through a connector that "
                    "can filter. Reading everything and calling it one segment would "
                    "attribute the whole object's data to that segment."
                ),
                context={"connector": type(self).__name__, "predicate": plan.predicate},
            )

    @classmethod
    def describe_manifest(
        cls,
        *,
        key: str,
        display_name: str,
        version: str = "1.0",
        capabilities: tuple[Capability, ...] = (),
        description: str = "",
    ) -> PluginManifest:
        """Build the manifest, so every connector declares one the same way."""
        return PluginManifest(
            key=key,
            kind="connector",
            display_name=display_name,
            version=version,
            capabilities=capabilities,
            description=description,
            conformance_suite="tests/connect/test_conformance.py",
        )

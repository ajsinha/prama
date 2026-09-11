"""MongoDB.

The first source here with no schema at all, which changes what a connector can
honestly promise rather than only how it fetches.

**The schema is inferred and the disagreements are the finding.** A collection
has whatever shape its documents happen to have. Taking the first document's
keys would produce a schema nobody checked; so types are inferred across a
sample and a field that arrives as a string on some documents and a number on
others is *reported on that field*. In a relational source that is a defect the
database would have prevented; here it is the normal state of an estate nobody
has declared, and it is exactly what a business owner needs to see.

**A sampled schema is a sampled schema.** The count of documents examined is
carried with it, because "no document has a `settled_at`" and "none of the two
hundred I looked at has one" are different claims and only one of them is true.

**Decimal128 is Mongo's exact type and it must stay exact.** It arrives as a
BSON object that is neither a Python number nor a string, and the obvious
conversion — through float — is the one that loses money. Same discipline as
the JDBC connector, different library.

**Nested documents become JSON text, not columns.** Flattening invents columns
the collection never promised and changes shape as soon as a document nests one
level deeper; dropping them loses a field a control might be about.

**A read is not a snapshot.** Documents change between the first batch and the
last. A resume token from a change stream would be exact but needs a replica
set, which a standalone deployment does not have — so this says wall-clock and
means it.

Needs the ``mongo`` extra.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import decimal
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from prama.connect.arrow import to_array
from prama.connect.capability import CapabilityMatrix, PushdownFeature
from prama.connect.spi import (
    ColumnSchema,
    Connector,
    ConnectorError,
    DiscoveredObject,
    HealthReport,
    HealthState,
    ObjectSchema,
    SamplePlan,
    Snapshot,
    SnapshotKind,
    SourceKind,
    UnreachableError,
    Verification,
)
from prama.core.clock import utc_now
from prama.core.registry import PluginManifest

if TYPE_CHECKING:  # pragma: no cover
    import pyarrow as pa

__all__ = ["CAPABILITIES", "MongoConnector"]

#: Rows per Arrow batch.
BATCH_ROWS = 5_000

#: How many documents the schema is inferred from unless told otherwise.
SCHEMA_SAMPLE = 500

#: Filtering pushes down; nothing else does. Mongo has an aggregation pipeline,
#: but it is not SQL and claiming SQL pushdown would produce a control that
#: compiles and fails at the source.
CAPABILITIES = CapabilityMatrix.of(
    PushdownFeature.FILTER,
    PushdownFeature.PREDICATE_PUSHDOWN,
)


class MongoConnector(Connector):
    """A MongoDB database. Collections are datasets; documents are rows."""

    plugin_key = "mongodb"
    source_kind = SourceKind.DOCUMENT
    credential_field = "password"

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.describe_manifest(
            key="mongodb",
            display_name="MongoDB",
            capabilities=CAPABILITIES.to_capabilities(),
            description=(
                "A MongoDB database, where collections are datasets. The schema is "
                "inferred across a sample and every type disagreement is reported "
                "on the field it is about — in a collection nobody has declared, "
                "that is the finding rather than the noise."
            ),
            verification=Verification.VERIFIED,
        )

    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self._uri = str(self.config.get("uri", ""))
        self._host = str(self.config.get("host", "localhost"))
        self._port = int(self.config.get("port", 27017))
        self._database = str(self.config.get("database", ""))
        self._user = str(self.config.get("user", ""))
        self._password = str(self.config.get("password", ""))
        self._auth_source = str(self.config.get("auth_source", "admin"))
        self._sample_documents = int(self.config.get("schema_sample_documents", SCHEMA_SAMPLE))
        self._timeout_ms = int(self.config.get("timeout_ms", 10_000))
        self._client: Any = None
        #: Carried from the last describe, so a caller can tell "no document
        #: has this field" from "none of the ones I looked at".
        self.last_schema_sample = 0

    # -- lifecycle ---------------------------------------------------------

    async def open(self) -> None:
        driver = self._driver()
        if not self._database:
            raise ConnectorError(
                "a MongoDB source needs a database",
                code="CONNECT.INCOMPLETE",
                remedy=(
                    "Name the database. A Mongo deployment holds several and "
                    "Prama will not pick one — an estate declared against the "
                    "wrong database is worse than one that failed to connect."
                ),
            )
        self._client = driver(
            self._connection_uri(),
            serverSelectionTimeoutMS=self._timeout_ms,
        )

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _connection_uri(self) -> str:
        if self._uri:
            return self._uri
        credentials = f"{self._user}:{self._password}@" if self._user else ""
        return f"mongodb://{credentials}{self._host}:{self._port}/?authSource={self._auth_source}"

    def _db(self) -> Any:
        if self._client is None:
            raise ConnectorError(
                "the MongoDB connector was used before it was opened",
                code="CONNECT.NOT_OPEN",
                remedy="Use the connector as an async context manager, or call open() first.",
            )
        return self._client[self._database]

    # -- contract ----------------------------------------------------------

    async def health(self) -> HealthReport:
        checked = utc_now()
        try:
            await self._db().command("ping")
        except Exception as exc:
            # `classify_failure` lives on the SQL base rather than the SPI, so
            # the distinction is made here: whose problem it is — the network's
            # or whoever grants access — is the thing worth getting right, and
            # reporting both as "connection failed" wastes a day.
            message = str(exc).lower()
            if any(word in message for word in ("auth", "not authorized", "password")):
                state = HealthState.UNAUTHORISED
            elif "timed out" in message or "timeout" in message:
                state = HealthState.DEGRADED
            else:
                state = HealthState.UNREACHABLE
            return HealthReport(state=state, detail=str(exc), checked_at=checked)
        return HealthReport(state=HealthState.HEALTHY, detail="", checked_at=checked)

    async def discover(self, path: tuple[str, ...] = ()) -> list[DiscoveredObject]:
        if path:
            return []
        database = self._db()
        try:
            names = await database.list_collection_names()
        except Exception as exc:
            raise UnreachableError(
                f"could not list collections in {self._database}",
                remedy=(
                    "The connection worked and the catalogue did not. Usually the "
                    "role can read documents and not `listCollections`."
                ),
                context={"database": self._database},
            ) from exc

        found = []
        for name in sorted(names):
            # `estimated_document_count` reads collection metadata and is free;
            # `count_documents({})` scans. Discovery runs across everything.
            estimate = await database[name].estimated_document_count()
            found.append(
                DiscoveredObject(
                    path=(name,),
                    kind="collection",
                    estimated_rows=int(estimate),
                    comment="a collection; its shape is whatever its documents have",
                )
            )
        return sorted(found, key=lambda o: o.estimated_rows or 0, reverse=True)

    async def describe(self, path: tuple[str, ...]) -> ObjectSchema:
        documents = await self._sample(path, self._sample_documents)
        self.last_schema_sample = len(documents)
        columns, disagreements = _infer(documents)
        noted = dict(disagreements)
        return ObjectSchema(
            path=path,
            columns=tuple(
                ColumnSchema(
                    name=column.name,
                    type_name=column.type_name,
                    nullable=column.nullable,
                    ordinal=column.ordinal,
                    comment=noted.get(column.name, column.comment),
                )
                for column in columns
            ),
        )

    async def snapshot(self, path: tuple[str, ...]) -> Snapshot:  # noqa: ARG002
        """Wall-clock, and not exact.

        A change-stream resume token would be exact, and needs a replica set. A
        standalone deployment has none, so promising one would make replay claim
        something this source cannot honour.
        """
        now = utc_now()
        return Snapshot(
            kind=SnapshotKind.WALL_CLOCK,
            identifier=now.isoformat(),
            captured_at=now,
            detail={
                "why_inexact": (
                    "documents change between the first batch and the last; a "
                    "resume token would be exact but needs a replica set"
                )
            },
        )

    async def read(
        self, path: tuple[str, ...], *, plan: SamplePlan | None = None
    ) -> AsyncIterator[pa.RecordBatch]:
        import pyarrow as pa

        plan = plan or SamplePlan()
        self.require_predicate_support(plan)
        limit = plan.rows or 0
        documents = await self._sample(path, limit)
        if not documents:
            return
        columns, _ = _infer(documents)
        names = [column.name for column in columns]
        for start in range(0, len(documents), BATCH_ROWS):
            chunk = documents[start : start + BATCH_ROWS]
            # `to_array` rather than Arrow's own inference: a field that is a
            # number in one document and text in the next is the finding this
            # source exists to surface, and inference raises on it.
            yield pa.RecordBatch.from_arrays(
                [to_array([_scalar(row.get(name)) for row in chunk]) for name in names],
                names=names,
            )

    async def _sample(self, path: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
        collection = self._db()[path[0] if path else ""]
        cursor = collection.find({})
        if limit:
            cursor = cursor.limit(limit)
        return [document async for document in cursor]

    @property
    def can_run_controls(self) -> bool:
        """False. Mongo has an aggregation pipeline; it does not have SQL.

        Claiming otherwise would send a compiled SQL control to a source that
        cannot read one.
        """
        return False

    @staticmethod
    def _driver() -> Any:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ConnectorError(
                "the MongoDB driver is not installed",
                code="CONNECT.DRIVER_MISSING",
                remedy='Install Prama\'s mongo extra: pip install "prama[mongo]"',
            ) from exc
        return AsyncIOMotorClient


# -- inference -------------------------------------------------------------


def _infer(
    documents: list[dict[str, Any]],
) -> tuple[list[ColumnSchema], list[tuple[str, str]]]:
    """Fields across the sample, and every type disagreement.

    Not from the first document. A collection has whatever shape its documents
    happen to have, and one document's keys are a schema nobody checked.
    """
    seen: dict[str, set[str]] = {}
    present: dict[str, int] = {}
    for document in documents:
        for key, value in document.items():
            seen.setdefault(key, set()).add(_type_of(value))
            present[key] = present.get(key, 0) + 1

    columns: list[ColumnSchema] = []
    disagreements: list[tuple[str, str]] = []
    total = len(documents)
    for name, kinds in seen.items():
        concrete = sorted(kinds - {"null"})
        if len(concrete) > 1:
            disagreements.append(
                (
                    name,
                    f"arrives as {' and as '.join(concrete)} across {total} sampled document(s)",
                )
            )
        missing = total - present.get(name, 0)
        comment = "" if not missing else f"absent from {missing} of {total} sampled"
        columns.append(
            ColumnSchema(
                name=name,
                type_name=concrete[0] if concrete else "null",
                nullable="null" in kinds or missing > 0,
                ordinal=len(columns),
                comment=comment,
            )
        )
    return columns, disagreements


def _type_of(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "double"
    if isinstance(value, (list, dict)):
        return "json"
    name = type(value).__name__
    if name == "Decimal128":
        return "decimal"
    if name == "ObjectId":
        return "objectid"
    if name == "datetime":
        return "timestamp"
    return "string"


def _scalar(value: Any) -> Any:
    """One BSON value as something Arrow can hold, losing nothing.

    Decimal128 goes through its own string. The obvious conversion is through
    float, and that is the one that loses money — same trap as JDBC, different
    library.
    """
    if value is None:
        return None
    name = type(value).__name__
    if name == "Decimal128":
        return decimal.Decimal(str(value))
    if name == "ObjectId":
        return str(value)
    if isinstance(value, (list, dict)):
        # JSON text rather than flattening: flattening invents columns the
        # collection never promised and changes shape the moment a document
        # nests one level deeper.
        return json.dumps(value, sort_keys=True, default=str)
    return value

"""Registering the first-party connectors, with their presentation overlays.

The overlay is the *only* hand-written part of a connector's form, and it may
add nothing but presentation: which fields are secret, what input to render,
what to call them, and a line of help. Every field itself is derived from the
connector's own code, so a connector that gains an option gains it in the form
the moment the code is written.

``audit()`` reports any overlay key the code does not read, and the test suite
fails the build on it — which is what stops the two halves quietly disagreeing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.connect.capability import CapabilityMatrix
from prama.connect.config_schema import FieldPresentation, InputKind
from prama.connect.registry import ConnectorRegistry, default_registry
from prama.connect.sources.filesystem import CAPABILITIES as FILESYSTEM_CAPABILITIES
from prama.connect.sources.filesystem import FilesystemConnector
from prama.connect.sources.sqlite import CAPABILITIES as SQLITE_CAPABILITIES
from prama.connect.sources.sqlite import SqliteConnector

FILESYSTEM_OVERLAY: dict[str, FieldPresentation] = {
    "root_path": FieldPresentation(
        label="Folder",
        help=(
            "The directory Prama reads from. For a feed, this is the landing zone — "
            "the folder the file arrives in, not the file itself."
        ),
        input_kind=InputKind.PATH,
        required=True,
        order=10,
    ),
    "file_pattern": FieldPresentation(
        label="File pattern",
        help=(
            "Which files to consider, e.g. positions_*.csv. Date tokens are matched "
            "as wildcards; the arrival window is declared on the dataset, not here."
        ),
        order=20,
    ),
    "max_file_bytes": FieldPresentation(
        label="Digest ceiling",
        help=(
            "How much of a file to hash when recording a snapshot. An exact "
            "identifier for a 40 GB extract is not worth 40 GB of reading; the size "
            "and modification time recorded alongside make a collision implausible."
        ),
        input_kind=InputKind.BYTES,
        group="advanced",
        order=110,
    ),
    "schema_sample_rows": FieldPresentation(
        label="Rows sampled for schema inference",
        help="How many rows to read when inferring CSV column types.",
        input_kind=InputKind.NUMBER,
        group="advanced",
        order=120,
    ),
}

SQLITE_OVERLAY: dict[str, FieldPresentation] = {
    "database_path": FieldPresentation(
        label="Database file",
        help="Path to the .db or .sqlite file. It is opened read-only.",
        input_kind=InputKind.PATH,
        required=True,
        order=10,
    ),
    "busy_timeout_seconds": FieldPresentation(
        label="Busy timeout",
        help="How long to wait when another writer holds the database.",
        input_kind=InputKind.DURATION,
        group="advanced",
        order=110,
    ),
    "include_views": FieldPresentation(
        label="Include views",
        help="Whether discovery offers views as well as tables.",
        input_kind=InputKind.BOOLEAN,
        order=20,
    ),
}

BUILTIN: tuple[tuple[type, CapabilityMatrix, dict[str, FieldPresentation]], ...] = (
    (FilesystemConnector, FILESYSTEM_CAPABILITIES, FILESYSTEM_OVERLAY),
    (SqliteConnector, SQLITE_CAPABILITIES, SQLITE_OVERLAY),
)


def register_builtin(registry: ConnectorRegistry | None = None) -> ConnectorRegistry:
    """Register every first-party connector. Idempotent."""
    target = registry or default_registry()
    for connector_class, capabilities, overlay in BUILTIN:
        target.register(
            connector_class,
            capabilities=capabilities,
            overlay=overlay,
            replace=True,
        )
    return target

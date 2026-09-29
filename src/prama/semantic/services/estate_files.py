"""The declared estate as a directory of reviewable YAML, and drift against one.

``prama estate export`` and ``prama estate diff`` and ``/api/v1/estate/export``
and ``/api/v1/estate/diff`` are the same two operations: render every declared
object to its documented path, and compare such a set of files with the store,
reporting disagreement in both directions without resolving it.

Paths are relative to the directory the files are written into — what
``prama estate export --out DIR`` puts under ``DIR`` — so an export can be
written straight to disk and a directory read straight back into a diff.

Deliberately absent: ``apply``. Writing files back into the store is a mutation
of a governed record, and it belongs behind the same approval workflow as any
other change rather than behind one call.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from prama.semantic.gitops import Drift, DriftDetector, EstateSerialiser

#: The serialiser's paths start here; exported paths are relative to it.
ROOT = "prama"


def _relative(path: str) -> str:
    return str(PurePosixPath(path).relative_to(ROOT))


async def export(uow: Any, tenant_id: str) -> dict[str, str]:
    """Every declared object, rendered to YAML, by path relative to the export directory."""
    serialiser = EstateSerialiser()
    datasets = await uow.datasets.list_current(tenant_id, limit=10_000)
    slugs = {d.dataset_id: d.slug for d in datasets}
    files: dict[str, str] = {}

    for dataset in datasets:
        attributes = await uow.attributes.for_dataset(dataset.dataset_id, tenant_id=tenant_id)
        files[serialiser.path_for("Dataset", dataset.slug)] = serialiser.dump(
            serialiser.dataset_document(dataset, attributes, slug_of=slugs)
        )
    for relationship in await uow.relationships.list_current(tenant_id, limit=10_000):
        name = f"{relationship.kind}_{relationship.relationship_id[-8:].lower()}"
        files[serialiser.path_for("Relationship", name)] = serialiser.dump(
            serialiser.relationship_document(relationship, slug_of=slugs)
        )
    for journey in await uow.journeys.list_current(tenant_id, limit=10_000):
        files[serialiser.path_for("Journey", journey.slug)] = serialiser.dump(
            serialiser.journey_document(journey, slug_of=slugs)
        )
    for connection in await uow.connections.list_current(tenant_id, limit=10_000):
        files[serialiser.path_for("Connection", connection.slug)] = serialiser.dump(
            serialiser.connection_document(connection)
        )
    return {_relative(path): text for path, text in files.items()}


def diff(store: dict[str, str], repository: dict[str, str]) -> list[Drift]:
    """Where *repository* (path -> YAML) disagrees with *store*, both directions."""
    serialiser = EstateSerialiser()

    def specs(files: dict[str, str]) -> dict[str, dict[str, Any]]:
        return {
            path: serialiser.load(text).get("spec", {})
            for path, text in files.items()
            if path.endswith(".yaml")
        }

    return DriftDetector().compare(specs(store), specs(repository), kind="Document")


async def diff_against(uow: Any, tenant_id: str, repository: dict[str, str]) -> dict[str, Any]:
    """The store against a set of files: whether they agree, and each drift."""
    drifts = diff(await export(uow, tenant_id), repository)
    return {
        "in_sync": not drifts,
        "drifts": [d.to_dict() for d in drifts],
        "summary": DriftDetector.summarise(drifts),
    }


__all__ = ["diff", "diff_against", "export"]

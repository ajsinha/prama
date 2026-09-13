"""Wiring the MCP tools to a live database.

The tools take an :class:`Estate` of plain callables, which is what makes them
testable with a dictionary. This module is the one place that hands them real
data, and it does so synchronously — MCP's stdio transport is a blocking loop
and a tool that returns a coroutine returns a coroutine to the model.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
from typing import Any

from prama.assistant.tools import Estate
from prama.core.log import get_logger
from prama.db import Database

_log = get_logger(__name__)


class DatabaseEstate:
    """Reads the semantic layer for the MCP tools.

    Every method returns plain dictionaries and never an ORM row: what these
    return goes straight into another model's context, and an object whose
    repr leaks a connection string or a lazily-loaded relationship is not
    something to hand across that boundary.
    """

    def __init__(self, database: Database, tenant_id: str) -> None:
        self._database = database
        self._tenant_id = tenant_id

    def _run(self, coroutine: Any) -> Any:
        return asyncio.run(coroutine)

    def datasets(self) -> tuple[str, ...]:
        """Names only, which is what the tool's contract says it returns.

        The slug rather than the display name, because the slug is what a
        control is written against and what ``describe_dataset`` will accept
        back — a listing whose entries cannot be used as the next call's
        argument sends a model round in circles.
        """
        return tuple(self._run(self._datasets()))

    async def _datasets(self) -> list[str]:
        async with self._database.unit_of_work() as uow:
            versions = await uow.datasets.list_current(self._tenant_id, limit=5000)
            return [version.slug for version in versions]

    def describe(self, name: str) -> dict[str, Any]:
        return dict(self._run(self._describe(name)))

    async def _describe(self, name: str) -> dict[str, Any]:
        async with self._database.unit_of_work() as uow:
            version = await uow.datasets.by_slug(self._tenant_id, name)
            if version is None:
                return {}
            attributes = await uow.attributes.for_dataset(
                version.dataset_id, tenant_id=self._tenant_id
            )
            return {
                "name": version.slug,
                "description": version.description or "",
                "purpose": version.purpose or "",
                "shape": version.shape,
                "criticality": version.criticality,
                "connected": version.is_bound,
                "grain": (version.grain_json or {}).get("statement", "")
                or ", ".join((version.grain_json or {}).get("attributes", [])),
                "attributes": [
                    {
                        "name": attribute.name,
                        "definition": attribute.definition or "",
                        "interpretation": attribute.interpretation or "",
                        "critical": bool(attribute.is_cde),
                    }
                    for attribute in attributes
                ],
            }


def estate_for(database: Database, tenant_id: str) -> Estate:
    """An :class:`Estate` backed by the database.

    Controls, incidents and lineage are left at their empty defaults because
    there is nothing to read yet — the evidence ledger is not persistent. An
    empty list is the honest answer, and the tools' descriptions say what they
    are for, so a model gets "nothing recorded" rather than an invented one.
    """
    reader = DatabaseEstate(database, tenant_id)
    return Estate(datasets=reader.datasets, describe_dataset=reader.describe)

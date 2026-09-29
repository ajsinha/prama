"""Connectors over the API: what is installed, what each needs, and using a connection.

A connector's configuration form is derived from the connector's own code
(`ConnectorRegistry.schema`), so the form here, in the console and in
`prama connectors` is one form. A connection is configured with
`POST /connections`; these routes test it, browse what its source holds, and
profile an object in it. The credential is resolved from its reference at the
moment of use and never returned.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from prama.api.deps import Reader, Uow, Writer
from prama.connect.builtin import register_builtin
from prama.core.errors import NotFoundError

router = APIRouter(tags=["connectors"])


@router.get("/connectors")
async def catalogue(caller: Reader) -> list[dict[str, Any]]:
    """Every installed connector: kind, capabilities, and its configuration form."""
    return register_builtin().catalogue()


@router.get("/connectors/{key}")
async def form(key: str, caller: Reader) -> dict[str, Any]:
    """One connector's configuration form: each field, whether it is required, its default."""
    registry = register_builtin()
    if key not in registry:
        raise NotFoundError(
            f"no connector {key!r} is installed",
            remedy=f"Installed: {', '.join(registry.keys())}.",
        )
    return dict(registry.schema(key).to_form())


async def _service(uow: Any, tenant_id: str, connection_id: str) -> Any:
    """The connectivity service, once the connection is known to be this estate's.

    The service finds a connection's estate from its id (the CLI has no
    tenant), so the check that it is the caller's is made here, first.
    """
    from prama.semantic.services import ConnectivityService

    if await uow.connections.current(connection_id, tenant_id=tenant_id) is None:
        raise NotFoundError(
            f"connection {connection_id!r} does not exist",
            remedy="List them with client.connections.list().",
            context={"connection_id": connection_id},
        )
    register_builtin()
    return ConnectivityService(uow)


def _path(dotted: str) -> tuple[str, ...]:
    return tuple(part for part in dotted.split(".") if part)


@router.post("/connections/{connection_id}/test")
async def test(connection_id: str, caller: Writer, uow: Uow) -> dict[str, Any]:
    """Can the connection reach its source, and may it read it? Recorded on the connection.

    `needs_access_request` separates a permission problem from a network one.
    """
    service = await _service(uow, caller.tenant_id, connection_id)
    return dict(await service.test(connection_id))


@router.get("/connections/{connection_id}/objects")
async def browse(
    connection_id: str,
    caller: Reader,
    uow: Uow,
    path: str = Query("", description="a schema to look inside, dotted; empty for the top"),
    limit: int = Query(200, ge=1, le=5000),
) -> list[dict[str, Any]]:
    """What the source holds (schemas, tables, files), largest first."""
    service = await _service(uow, caller.tenant_id, connection_id)
    return [
        {
            "path": list(o.path),
            "name": o.qualified_name,
            "kind": o.kind,
            "rows": o.estimated_rows,
            "bytes": o.estimated_bytes,
            "last_modified": o.last_modified.isoformat() if o.last_modified else None,
            "comment": o.comment,
            "tags": list(o.tags),
        }
        for o in await service.discover(connection_id, _path(path), limit=limit)
    ]


@router.get("/connections/{connection_id}/cost")
async def cost(
    connection_id: str,
    caller: Reader,
    uow: Uow,
    target: str = Query(..., alias="object", min_length=1),
) -> dict[str, Any]:
    """What reading an object would cost, from catalogue metadata alone, without reading it."""
    service = await _service(uow, caller.tenant_id, connection_id)
    return dict(await service.preview_cost(connection_id, _path(target)))


class ProfileIn(BaseModel):
    object: str = Field("", description="one object, dotted (schema.table); empty sweeps")
    limit: int = Field(10, ge=1, le=200, description="objects in a sweep")


@router.post("/connections/{connection_id}/profile")
async def profile(
    connection_id: str, body: ProfileIn, caller: Writer, uow: Uow
) -> list[dict[str, Any]]:
    """Profile one object — or sweep the source, largest first — in one pass each."""
    service = await _service(uow, caller.tenant_id, connection_id)
    if body.object:
        runs = [await service.profile(connection_id, _path(body.object))]
    else:
        runs = await service.profile_source(connection_id, limit=body.limit)
    return [run.to_dict() for run in runs]

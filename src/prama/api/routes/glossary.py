"""The business glossary over the API: terms, imports from a catalog, and bindings.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from prama.api.deps import Reader, Uow, Writer
from prama.api.routes._knowledge import read_json
from prama.semantic.services import glossary as service

router = APIRouter(tags=["glossary"])


@router.get("/glossary/terms")
async def terms(caller: Reader, uow: Uow, q: str = "") -> list[dict[str, Any]]:
    """Every term with what it is bound to; *q* searches names, synonyms and definitions."""
    return await service.terms(uow, caller.tenant_id, q)


@router.get("/glossary/terms/{name}")
async def term(name: str, caller: Reader, uow: Uow) -> dict[str, Any]:
    return await service.term(uow, caller.tenant_id, name)


@router.post("/glossary/import")
async def import_terms(
    caller: Writer,
    uow: Uow,
    vendor: Literal["alation", "collibra"] = Form(...),
    export: UploadFile = File(...),
) -> dict[str, Any]:
    """Terms from an Alation or Collibra export.

    A term whose name matches a concept is bound to it (`bound_to_concepts`).
    What did not come across is listed under `dropped`, each with why — an
    import that silently lost a tenth of the glossary reads as a complete one.
    """
    from prama.importers.catalog import ingest, read

    imported = read(vendor, "terms", await read_json(export))
    return await ingest(uow, caller.tenant_id, imported)


class BindIn(BaseModel):
    kind: Literal["concept", "dataset", "attribute"]
    ref: str
    """A concept's name, a dataset slug, or `dataset.column`."""


@router.post("/glossary/terms/{name}/bindings")
async def bind(name: str, body: BindIn, caller: Writer, uow: Uow) -> dict[str, Any]:
    """Bind a term to a concept, dataset or attribute. Binding twice changes nothing."""
    await service.bind(
        uow, caller.tenant_id, name, body.kind, body.ref, by=caller.principal_id or None
    )
    return await service.term(uow, caller.tenant_id, name)

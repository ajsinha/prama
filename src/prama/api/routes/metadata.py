"""A dataset's business context and metadata, and search by meaning, for programs and agents.

Setting a metadata field whose template carries a rule (``mandatory=yes`` on an
attribute, say) does not create a control. It creates a *proposal*: the rule is
rendered, shown under ``proposals``, and becomes a control only when a person
accepts it on the proposals queue. Metadata implies; people decide.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from prama.api.deps import ControlProposer, Reader, Uow, Writer
from prama.core.errors import ValidationError
from prama.semantic.services import metadata as service

router = APIRouter(tags=["metadata"])

# Fixed paths are declared before `/metadata/{dataset}`, which would otherwise
# swallow them.


@router.get("/metadata/search")
async def search(uow: Uow, caller: Reader, q: str = Query(min_length=1)) -> list[dict[str, Any]]:
    return await service.search(uow, caller.tenant_id, q)


@router.get("/metadata/ask")
async def ask(
    request: Request, uow: Uow, caller: Reader, q: str = Query(min_length=1)
) -> dict[str, Any]:
    from prama.semantic.services.finding import find_data

    return await find_data(
        uow,
        caller.tenant_id,
        q,
        config=request.app.state.config,
        principal_id=caller.principal_id or None,
    )


@router.get("/metadata/correlation")
async def correlation(uow: Uow, caller: Reader) -> dict[str, Any]:
    return await service.correlation(uow, caller.tenant_id)


@router.get("/metadata/templates")
async def templates(uow: Uow, caller: Reader) -> dict[str, Any]:
    """The estate's templates, each field with its kind and the rules it implies."""
    return await service.templates(uow, caller.tenant_id)


class StarterIn(BaseModel):
    starter: str = Field(..., description="e.g. data-quality-attribute, data-quality-dataset")


@router.post("/metadata/templates/starter")
async def install_starter(body: StarterIn, uow: Uow, caller: Writer) -> dict[str, Any]:
    """Install one of the starter templates. Installing it again changes nothing."""
    return await service.install_starter(uow, caller.tenant_id, body.starter)


class TemplateIn(BaseModel):
    document: dict[str, Any] | None = Field(
        None, description="the template: name, applies_to, fields"
    )
    yaml: str | None = Field(None, description="the same, as YAML text")


@router.post("/metadata/templates")
async def save_template(body: TemplateIn, uow: Uow, caller: Writer) -> dict[str, Any]:
    """Save your own template, as a mapping or as YAML."""
    document: Any = body.document
    if document is None and body.yaml is not None:
        import yaml

        try:
            document = yaml.safe_load(body.yaml)
        except yaml.YAMLError as exc:
            raise ValidationError(
                f"the template could not be read: {exc}", remedy="Check the YAML."
            ) from exc
    if not isinstance(document, dict):
        raise ValidationError(
            "the template is not a mapping",
            remedy="Send `document` (or `yaml`) with name:, applies_to: and fields:.",
        )
    return await service.save_template(uow, caller.tenant_id, document)


@router.get("/metadata/proposals")
async def proposals(uow: Uow, caller: Reader, dataset: str = "") -> list[dict[str, Any]]:
    """Controls the estate's metadata implies, not yet accepted or rejected.

    *dataset* is a slug; omit it for the whole estate.
    """
    dataset_id = ""
    if dataset:
        version, _ = await service.resolve(uow, caller.tenant_id, dataset)
        dataset_id = version.dataset_id
    return await service.proposals(uow, caller.tenant_id, dataset_id=dataset_id)


class ValuesIn(BaseModel):
    values: dict[str, Any] = Field(..., description="field -> value; an empty value clears")


@router.put("/metadata/{target}/values")
async def set_values(target: str, body: ValuesIn, uow: Uow, caller: Writer) -> dict[str, Any]:
    """Set metadata on a dataset (`trades`) or an attribute (`trades.account_id`).

    Returns the fields that changed, and the proposals now implied for the
    dataset — the rules a field like `mandatory` carries, waiting for a person.
    """
    changed = await service.set_values(
        uow, caller.tenant_id, target, body.values, by=caller.principal_id or None
    )
    version, _ = await service.resolve(uow, caller.tenant_id, target)
    return {
        "target": target,
        "changed": changed,
        "proposals": await service.proposals(uow, caller.tenant_id, dataset_id=version.dataset_id),
    }


class ContextIn(BaseModel):
    text: str


@router.put("/metadata/{target}/context")
async def set_context(target: str, body: ContextIn, uow: Uow, caller: Writer) -> dict[str, Any]:
    """Record business context on a dataset or attribute — an amendment, so it is versioned."""
    await service.set_context(
        uow, caller.tenant_id, target, body.text, by=caller.principal_id or None
    )
    return await service.describe(uow, caller.tenant_id, target)


class RuleIn(BaseModel):
    pql: str = Field(..., min_length=1)


@router.post("/metadata/{dataset}/rules", status_code=201)
async def author_rule(
    dataset: str, body: RuleIn, uow: Uow, caller: ControlProposer
) -> dict[str, Any]:
    """Write a rule for a dataset by hand. It is proposed; somebody else approves it."""
    return await service.author_rule(
        uow, caller.tenant_id, dataset, body.pql, by=caller.principal_id
    )


@router.get("/metadata/{dataset}")
async def describe(dataset: str, uow: Uow, caller: Reader) -> dict[str, Any]:
    """A dataset's context, metadata, attributes, rules and implied rules."""
    return await service.describe(uow, caller.tenant_id, dataset)

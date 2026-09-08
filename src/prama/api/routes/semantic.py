"""Semantic-layer routes: datasets, attributes, relationships.

Every mutating route names its author, requires a reason where the model demands
one, and returns the bitemporal position of what it wrote. A caller therefore
always knows *which version* they are holding — the question that matters the
moment anything is amended.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Response, status

from prama.api.deps import Caller, Uow
from prama.api.mapping import attribute_out, dataset_out, relationship_out
from prama.api.schemas import (
    AttributeIn,
    AttributeOut,
    DatasetAmendIn,
    DatasetCorrectIn,
    DatasetIn,
    DatasetOut,
    DatasetPage,
    Page,
    RelationshipDecisionIn,
    RelationshipIn,
    RelationshipKindOut,
    RelationshipOut,
)
from prama.core.errors import NotFoundError
from prama.semantic.relationships import (
    MatchKey,
    RelationshipDeclaration,
    TimeOffset,
    Tolerance,
)
from prama.semantic.service import DatasetService, RelationshipService, relationship_kinds
from prama.semantic.values import Grain, Rhythm

router = APIRouter(tags=["semantic"])


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


@router.post("/datasets", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def declare_dataset(body: DatasetIn, caller: Caller, uow: Uow) -> DatasetOut:
    """Declare a dataset. It may be unbound — that is a first-class state."""
    _, version = await DatasetService(uow).declare(
        tenant_id=caller.tenant_id,
        name=body.name,
        description=body.description,
        purpose=body.purpose,
        domain_id=body.domain_id,
        owner_id=body.owner_id,
        criticality=body.criticality,
        shape=body.shape,
        grain=Grain(tuple(body.grain.attributes), body.grain.statement) if body.grain else None,
        rhythm=Rhythm(**body.rhythm.model_dump()) if body.rhythm else None,
        temporality=body.temporality,
        authoritativeness=body.authoritativeness,
        sensitivity=body.sensitivity,
        tags=body.tags,
        authored_by=caller.principal_id,
        approved_by=body.approved_by,
        reason=body.reason,
        valid_from=body.valid_from,
    )
    return dataset_out(version)


@router.get("/datasets", response_model=DatasetPage)
async def list_datasets(
    caller: Caller,
    uow: Uow,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    unbound: bool = Query(default=False, description="Only datasets not yet connected."),
    criticality: int | None = Query(default=None, ge=1, le=4),
) -> DatasetPage:
    if unbound:
        versions = await uow.datasets.unbound(caller.tenant_id)
    elif criticality is not None:
        versions = await uow.datasets.by_criticality(caller.tenant_id, criticality)
    else:
        versions = await uow.datasets.list_current(caller.tenant_id, limit=limit, offset=offset)
    return DatasetPage(
        items=[dataset_out(v) for v in versions],
        page=Page(
            total=await uow.datasets.count_current(caller.tenant_id), limit=limit, offset=offset
        ),
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
async def get_dataset(
    dataset_id: str,
    caller: Caller,
    uow: Uow,
    valid_at: datetime | None = Query(
        default=None, description="What we believe today was true at this instant."
    ),
    known_at: datetime | None = Query(
        default=None,
        description=(
            "What we believed at this instant. With valid_at, the full bitemporal "
            "question an evidence replay asks."
        ),
    ),
) -> DatasetOut:
    if valid_at and known_at:
        version = await uow.datasets.as_of(dataset_id, valid_at=valid_at, known_at=known_at)
    elif valid_at:
        version = await uow.datasets.valid_at(dataset_id, valid_at)
    else:
        version = await uow.datasets.current(dataset_id)
    if version is None:
        raise NotFoundError(
            f"dataset {dataset_id!r} has no version matching that point in time",
            remedy="Check the identifier, or widen the valid_at / known_at window.",
            context={"dataset_id": dataset_id},
        )
    return dataset_out(version)


@router.get("/datasets/{dataset_id}/history", response_model=list[DatasetOut])
async def dataset_history(dataset_id: str, caller: Caller, uow: Uow) -> list[DatasetOut]:
    """Every version, oldest first — the audit view of a declaration."""
    return [dataset_out(v) for v in await uow.datasets.history(dataset_id)]


@router.post("/datasets/{dataset_id}/amend", response_model=DatasetOut)
async def amend_dataset(
    dataset_id: str, body: DatasetAmendIn, caller: Caller, uow: Uow
) -> DatasetOut:
    """The world changed: close one validity period and open the next."""
    version = await DatasetService(uow).amend(
        tenant_id=caller.tenant_id,
        dataset_id=dataset_id,
        reason=body.reason,
        authored_by=caller.principal_id,
        approved_by=body.approved_by,
        effective_from=body.effective_from,
        **body.changes,
    )
    return dataset_out(version)


@router.post("/datasets/{dataset_id}/correct", response_model=DatasetOut)
async def correct_dataset(
    dataset_id: str, body: DatasetCorrectIn, caller: Caller, uow: Uow
) -> DatasetOut:
    """We were wrong: supersede the belief, leave validity untouched."""
    version = await DatasetService(uow).correct(
        tenant_id=caller.tenant_id,
        dataset_id=dataset_id,
        reason=body.reason,
        authored_by=caller.principal_id,
        **body.changes,
    )
    return dataset_out(version)


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def retire_dataset(dataset_id: str, caller: Caller, uow: Uow) -> Response:
    """Retire, never delete: history is needed to interpret past evidence."""
    await uow.datasets.retire(dataset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Attributes
# ---------------------------------------------------------------------------


@router.post(
    "/datasets/{dataset_id}/attributes",
    response_model=AttributeOut,
    status_code=status.HTTP_201_CREATED,
)
async def declare_attribute(
    dataset_id: str, body: AttributeIn, caller: Caller, uow: Uow
) -> AttributeOut:
    _, version = await DatasetService(uow).declare_attribute(
        tenant_id=caller.tenant_id,
        dataset_id=dataset_id,
        name=body.name,
        definition=body.definition,
        interpretation=body.interpretation,
        semantic_type=body.semantic_type,
        is_cde=body.is_cde,
        obligations=body.obligations,
        authored_by=caller.principal_id,
        unit=body.unit,
        currency_attribute=body.currency_attribute,
        optionality=body.optionality,
        sensitivity=body.sensitivity,
        concept_property_id=body.concept_property_id,
        glossary_term=body.glossary_term,
    )
    return attribute_out(version, dataset_id=dataset_id)


@router.get("/datasets/{dataset_id}/attributes", response_model=list[AttributeOut])
async def list_attributes(dataset_id: str, caller: Caller, uow: Uow) -> list[AttributeOut]:
    return [
        attribute_out(v, dataset_id=dataset_id)
        for v in await uow.attributes.for_dataset(dataset_id)
    ]


@router.get("/critical-data-elements", response_model=list[AttributeOut])
async def list_cdes(caller: Caller, uow: Uow) -> list[AttributeOut]:
    """Every CDE in the tenant: the population attracting the strictest controls."""
    return [
        attribute_out(v, dataset_id="")
        for v in await uow.attributes.critical_data_elements(caller.tenant_id)
    ]


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------


@router.get("/relationship-kinds", response_model=list[RelationshipKindOut])
async def list_relationship_kinds() -> list[RelationshipKindOut]:
    """The thirteen choices, in business language, with what each generates."""
    return [RelationshipKindOut(**k) for k in relationship_kinds()]


@router.post("/relationships", response_model=RelationshipOut, status_code=status.HTTP_201_CREATED)
async def declare_relationship(body: RelationshipIn, caller: Caller, uow: Uow) -> RelationshipOut:
    """Declare a relationship. Validation happens before anything is stored."""
    declaration = RelationshipDeclaration(
        kind=body.kind,
        from_dataset_id=body.from_dataset_id,
        to_dataset_id=body.to_dataset_id,
        match_keys=tuple(MatchKey(k.left, k.right) for k in body.match_keys),
        compare=tuple(body.compare),
        cardinality=body.cardinality,
        tolerance=Tolerance(**body.tolerance.model_dump()) if body.tolerance else None,
        offset=TimeOffset(**body.offset.model_dump()) if body.offset else None,
        filter_expression=body.filter_expression,
        name=body.name,
        description=body.description,
    )
    _, version = await RelationshipService(uow).declare(
        tenant_id=caller.tenant_id,
        declaration=declaration,
        owner_id=body.owner_id,
        criticality=body.criticality,
        authored_by=caller.principal_id,
        approved_by=body.approved_by,
        reason=body.reason,
    )
    return relationship_out(version)


@router.get("/relationships", response_model=list[RelationshipOut])
async def list_relationships(
    caller: Caller,
    uow: Uow,
    dataset_id: str | None = Query(default=None, description="Either side of the relationship."),
    kind: str | None = Query(default=None),
    confirmed_only: bool = Query(default=False),
) -> list[RelationshipOut]:
    if dataset_id:
        versions = await uow.relationships.touching(caller.tenant_id, dataset_id)
    elif kind:
        versions = await uow.relationships.of_kind(caller.tenant_id, kind)
    elif confirmed_only:
        versions = await uow.relationships.confirmed(caller.tenant_id)
    else:
        versions = await uow.relationships.list_current(caller.tenant_id, limit=500)
    return [relationship_out(v) for v in versions]


@router.post("/relationships/{relationship_id}/confirm", response_model=RelationshipOut)
async def confirm_relationship(
    relationship_id: str, body: RelationshipDecisionIn, caller: Caller, uow: Uow
) -> RelationshipOut:
    """Confirm a proposal. Until this, derived controls stay proposals too."""
    version = await RelationshipService(uow).confirm(
        tenant_id=caller.tenant_id,
        relationship_id=relationship_id,
        confirmed_by=caller.require_principal(),
        reason=body.reason,
    )
    return relationship_out(version)


@router.post("/relationships/{relationship_id}/reject", response_model=RelationshipOut)
async def reject_relationship(
    relationship_id: str, body: RelationshipDecisionIn, caller: Caller, uow: Uow
) -> RelationshipOut:
    """Reject a proposal. Recorded, not deleted: it is a training signal."""
    version = await RelationshipService(uow).reject(
        tenant_id=caller.tenant_id,
        relationship_id=relationship_id,
        rejected_by=caller.require_principal(),
        reason=body.reason or "rejected by steward",
    )
    return relationship_out(version)

"""Routes for concepts, journeys, connections and bindings.

The objects that connect datasets to each other and to the physical world.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from prama.api.deps import Reader, Uow, Writer
from prama.api.mapping import (
    attribute_out,
    binding_out,
    concept_out,
    concept_property_out,
    connection_out,
    journey_out,
)
from prama.api.schemas import (
    AttributeMappingIn,
    AttributeOut,
    BindingIn,
    BindingOut,
    ConceptIn,
    ConceptOut,
    ConceptPropertyIn,
    ConceptPropertyOut,
    ConnectionIn,
    ConnectionOut,
    JourneyIn,
    JourneyOut,
    JourneyStepsIn,
)
from prama.core.errors import NotFoundError
from prama.semantic.services import (
    BindingService,
    ConceptService,
    ConnectionService,
    JourneyService,
)

router = APIRouter(tags=["graph"])


# ---------------------------------------------------------------------------
# Concepts
# ---------------------------------------------------------------------------


@router.post("/concepts", response_model=ConceptOut, status_code=status.HTTP_201_CREATED)
async def declare_concept(body: ConceptIn, caller: Writer, uow: Uow) -> ConceptOut:
    """Declare a canonical business concept: Party, Instrument, Position."""
    _, version = await ConceptService(uow).declare_concept(
        tenant_id=caller.tenant_id,
        name=body.name,
        description=body.description,
        domain_id=body.domain_id,
        pack_ref=body.pack_ref,
        authored_by=caller.principal_id,
    )
    return concept_out(version)


@router.get("/concepts", response_model=list[ConceptOut])
async def list_concepts(caller: Reader, uow: Uow) -> list[ConceptOut]:
    return [concept_out(v) for v in await uow.concepts.list_current(caller.tenant_id, limit=500)]


@router.post(
    "/concepts/{concept_id}/properties",
    response_model=ConceptPropertyOut,
    status_code=status.HTTP_201_CREATED,
)
async def declare_property(
    concept_id: str, body: ConceptPropertyIn, caller: Writer, uow: Uow
) -> ConceptPropertyOut:
    """Declare a property. A control authored here reaches every mapped attribute."""
    _, version = await ConceptService(uow).declare_property(
        tenant_id=caller.tenant_id,
        concept_id=concept_id,
        name=body.name,
        definition=body.definition,
        semantic_type=body.semantic_type,
        unit=body.unit,
        value_domain=body.value_domain,
        is_identifier=body.is_identifier,
        authored_by=caller.principal_id,
    )
    return concept_property_out(version, concept_id=concept_id)


@router.get("/concepts/{concept_id}/properties", response_model=list[ConceptPropertyOut])
async def list_properties(concept_id: str, caller: Reader, uow: Uow) -> list[ConceptPropertyOut]:
    out: list[ConceptPropertyOut] = []
    for version in await uow.concept_properties.for_concept(concept_id, tenant_id=caller.tenant_id):
        mapped = await uow.attributes.mapped_to_property(version.property_id)
        out.append(concept_property_out(version, concept_id=concept_id, mapped_count=len(mapped)))
    return out


@router.post("/attributes/{attribute_id}/mapping", response_model=AttributeOut)
async def map_attribute(
    attribute_id: str, body: AttributeMappingIn, caller: Writer, uow: Uow
) -> AttributeOut:
    """Claim that an attribute *is* a canonical property.

    The claim is what makes conflict detection possible: two attributes
    asserting one meaning while disagreeing about units become visible.
    """
    version = await ConceptService(uow).map_attribute(
        tenant_id=caller.tenant_id,
        attribute_id=attribute_id,
        property_id=body.property_id,
        mapped_by=caller.principal_id,
    )
    return attribute_out(version, dataset_id="")


# ---------------------------------------------------------------------------
# Journeys
# ---------------------------------------------------------------------------


@router.post("/journeys", response_model=JourneyOut, status_code=status.HTTP_201_CREATED)
async def declare_journey(body: JourneyIn, caller: Writer, uow: Uow) -> JourneyOut:
    """Declare a business process as an ordered chain of datasets.

    Steps may be black boxes: a mainframe job or a manual upload that Prama
    cannot read is still part of the chain, and describing it is what gives
    business lineage its reach.
    """
    _, version = await JourneyService(uow).declare(
        tenant_id=caller.tenant_id,
        name=body.name,
        description=body.description,
        domain_id=body.domain_id,
        owner_id=body.owner_id,
        criticality=body.criticality,
        sla=body.sla,
        steps=[s.model_dump(exclude_none=True) for s in body.steps],
        authored_by=caller.principal_id,
        approved_by=body.approved_by,
    )
    return journey_out(version)


@router.get("/journeys", response_model=list[JourneyOut])
async def list_journeys(
    caller: Reader,
    uow: Uow,
    dataset_id: str | None = Query(
        default=None, description="Journeys a dataset appears in — its blast radius."
    ),
) -> list[JourneyOut]:
    if dataset_id:
        versions = await uow.journeys.containing(caller.tenant_id, dataset_id)
    else:
        versions = await uow.journeys.list_current(caller.tenant_id, limit=500)
    return [journey_out(v) for v in versions]


@router.get("/journeys/{journey_id}", response_model=JourneyOut)
async def get_journey(journey_id: str, caller: Reader, uow: Uow) -> JourneyOut:
    version = await uow.journeys.current(journey_id, tenant_id=caller.tenant_id)
    if version is None:
        raise NotFoundError(
            f"journey {journey_id!r} does not exist",
            remedy="Check the identifier, or list the declared journeys.",
            context={"journey_id": journey_id},
        )
    return journey_out(version)


@router.put("/journeys/{journey_id}/steps", response_model=JourneyOut)
async def set_journey_steps(
    journey_id: str, body: JourneyStepsIn, caller: Writer, uow: Uow
) -> JourneyOut:
    """Replace the chain wholesale: reordering touches every step."""
    version = await JourneyService(uow).set_steps(
        tenant_id=caller.tenant_id,
        journey_id=journey_id,
        steps=[s.model_dump(exclude_none=True) for s in body.steps],
        reason=body.reason,
        authored_by=caller.principal_id,
    )
    return journey_out(version)


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


@router.post("/connections", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def configure_connection(body: ConnectionIn, caller: Writer, uow: Uow) -> ConnectionOut:
    """Configure a route to a source. Never stores a secret."""
    _, version = await ConnectionService(uow).configure(
        tenant_id=caller.tenant_id,
        name=body.name,
        source_type=body.source_type,
        description=body.description,
        config=body.config,
        credential_ref=body.credential_ref,
        read_policy=body.read_policy,
        budget=body.budget,
        owner_id=body.owner_id,
        authored_by=caller.principal_id,
    )
    return connection_out(version)


@router.get("/connections", response_model=list[ConnectionOut])
async def list_connections(
    caller: Reader,
    uow: Uow,
    unhealthy_only: bool = Query(default=False),
) -> list[ConnectionOut]:
    versions = (
        await uow.connections.unhealthy(caller.tenant_id)
        if unhealthy_only
        else await uow.connections.list_current(caller.tenant_id, limit=500)
    )
    return [connection_out(v) for v in versions]


# ---------------------------------------------------------------------------
# Bindings
# ---------------------------------------------------------------------------


@router.post(
    "/datasets/{dataset_id}/bindings",
    response_model=BindingOut,
    status_code=status.HTTP_201_CREATED,
)
async def bind(dataset_id: str, body: BindingIn, caller: Writer, uow: Uow) -> BindingOut:
    """Bind a declared object to where it actually lives."""
    service = BindingService(uow)
    if body.attribute_id:
        _, version = await service.bind_attribute(
            tenant_id=caller.tenant_id,
            dataset_id=dataset_id,
            attribute_id=body.attribute_id,
            connection_id=body.connection_id,
            physical_ref=body.physical_ref,
            transform=body.transform,
            confidence=body.confidence,
            authored_by=caller.principal_id,
        )
    else:
        _, version = await service.bind_dataset(
            tenant_id=caller.tenant_id,
            dataset_id=dataset_id,
            connection_id=body.connection_id,
            physical_ref=body.physical_ref,
            shape=body.shape,
            confidence=body.confidence,
            authored_by=caller.principal_id,
        )
    return binding_out(version)


@router.get("/datasets/{dataset_id}/bindings", response_model=list[BindingOut])
async def list_bindings(dataset_id: str, caller: Reader, uow: Uow) -> list[BindingOut]:
    return [
        binding_out(v)
        for v in await uow.bindings.for_dataset(dataset_id, tenant_id=caller.tenant_id)
    ]


@router.get("/bindings/drifted", response_model=list[BindingOut])
async def list_drifted(caller: Reader, uow: Uow) -> list[BindingOut]:
    """Bindings whose physical target has moved beneath the declaration.

    Each is an incident for the business owner of the declaration, not for an
    engineer. Only a platform holding a declared model can detect this at all.
    """
    return [binding_out(v) for v in await uow.bindings.drifted(caller.tenant_id)]

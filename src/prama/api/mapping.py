"""Converting stored declarations into API responses.

Kept apart from both the ORM and the schemas so that neither has to know about
the other. One place to look when a field appears in the database and not in the
API, which is the failure everyone eventually hunts.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.api.schemas import (
    AttributeOut,
    DatasetOut,
    RelationshipOut,
    VersionMeta,
)
from prama.semantic.relationships import RelationshipKind


def version_meta(version: Any) -> VersionMeta:
    return VersionMeta(
        version=version.version,
        valid_from=version.valid_from,
        valid_to=version.valid_to,
        recorded_at=version.recorded_at,
        superseded_at=version.superseded_at,
        authored_by=version.authored_by,
        approved_by=version.approved_by,
        change_reason=version.change_reason,
        is_current=version.is_current,
    )


def dataset_out(version: Any) -> DatasetOut:
    return DatasetOut(
        id=version.dataset_id,
        slug=version.slug,
        name=version.name,
        description=version.description,
        purpose=version.purpose,
        domain_id=version.domain_id,
        owner_id=version.owner_id,
        steward_id=version.steward_id,
        criticality=version.criticality,
        shape=version.shape,
        is_bound=version.is_bound,
        grain=version.grain_json,
        rhythm=version.rhythm_json,
        temporality=version.temporality,
        authoritativeness=version.authoritativeness,
        sensitivity=version.sensitivity,
        lifecycle_state=version.lifecycle_state,
        tags=list(version.tags_json or []),
        meta=version_meta(version),
    )


def attribute_out(version: Any, *, dataset_id: str) -> AttributeOut:
    return AttributeOut(
        id=version.attribute_id,
        dataset_id=dataset_id,
        name=version.name,
        ordinal=version.ordinal,
        definition=version.definition,
        interpretation=version.interpretation,
        semantic_type=version.semantic_type,
        unit=version.unit,
        optionality=version.optionality,
        is_cde=version.is_cde,
        obligations=list(version.obligations_json or []),
        sensitivity=version.sensitivity,
        concept_property_id=version.concept_property_id,
        meta=version_meta(version),
    )


def relationship_out(version: Any) -> RelationshipOut:
    # A relationship's response states what it *generates*, because that is the
    # question a user actually has: "what did declaring this buy me?"
    generates = list(RelationshipKind(version.kind).generates)
    return RelationshipOut(
        id=version.relationship_id,
        kind=version.kind,
        from_dataset_id=version.from_dataset_id,
        to_dataset_id=version.to_dataset_id,
        name=version.name,
        description=version.description,
        match_keys=list(version.match_keys_json or []),
        compare=list(version.compare_json or []),
        cardinality=version.cardinality,
        tolerance=version.tolerance_json,
        offset=version.offset_json,
        status=version.status,
        confidence=version.confidence,
        discovered_by=version.discovered_by,
        evidence=version.evidence_json,
        generates=generates,
        meta=version_meta(version),
    )

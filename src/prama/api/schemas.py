"""Request and response shapes.

Separate from the ORM on purpose. A model is how a declaration is *stored*; a
schema is what the API *promises*, and the two must be free to change
independently — otherwise a storage refactor becomes a breaking API change and a
column rename becomes a customer's outage.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from prama.semantic.relationships import Cardinality, OffsetUnit, RelationshipKind
from prama.semantic.values import Frequency


class PramaModel(BaseModel):
    """Base: reject unknown fields rather than ignoring them.

    A typo in a request body that is silently dropped is the worst possible
    outcome — the caller believes they set something they did not.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


class GrainIn(PramaModel):
    attributes: list[str] = Field(min_length=1, description="Business attributes, in order.")
    statement: str = Field(
        default="",
        description="The sentence as written, kept verbatim for the control's rationale.",
    )


class RhythmIn(PramaModel):
    frequency: Frequency = Frequency.DAILY
    arrival_by: str | None = Field(default=None, description="HH:MM in the calendar's timezone.")
    calendar: str | None = Field(default=None, description="Business calendar, e.g. TARGET2.")
    lateness_tolerance_seconds: float = 0.0
    expected_volume_min: int | None = None
    expected_volume_max: int | None = None
    volume_drivers: list[str] = Field(
        default_factory=list,
        description="Declared causes of legitimate variation, e.g. month_end.",
    )


class DatasetIn(PramaModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    purpose: str = ""
    domain_id: str | None = None
    owner_id: str | None = None
    steward_id: str | None = None
    criticality: int = Field(default=4, ge=1, le=4)
    shape: str = Field(default="unbound", description="unbound | table | feed | stream | …")
    grain: GrainIn | None = None
    rhythm: RhythmIn | None = None
    temporality: str = "snapshot"
    authoritativeness: str = "unknown"
    sensitivity: str = "internal"
    tags: list[str] = Field(default_factory=list)
    approved_by: str | None = Field(
        default=None, description="Required for Tier-1 and Tier-2 declarations."
    )
    reason: str = ""
    valid_from: datetime | None = Field(
        default=None,
        description=(
            "When this became true of the world. Defaults to now. Backdating is "
            "normal: a declaration written today often describes something that "
            "has been true since January, and an evidence record from February "
            "must resolve against it."
        ),
    )


class DatasetAmendIn(PramaModel):
    reason: str = Field(min_length=1, description="Why the world changed. Required.")
    effective_from: datetime | None = None
    approved_by: str | None = None
    changes: dict[str, Any] = Field(default_factory=dict)


class DatasetCorrectIn(PramaModel):
    reason: str = Field(min_length=1, description="What was wrong. Required.")
    changes: dict[str, Any] = Field(default_factory=dict)


class AttributeIn(PramaModel):
    name: str = Field(min_length=1, max_length=128)
    definition: str = Field(default="", description="What the value is.")
    interpretation: str = Field(
        default="",
        description="How to read it: sign conventions, inclusions, calculation basis.",
    )
    semantic_type: str | None = None
    unit: str | None = None
    currency_attribute: str | None = None
    optionality: str = "optional"
    is_cde: bool = False
    obligations: list[str] = Field(default_factory=list)
    sensitivity: str = "internal"
    concept_property_id: str | None = None
    glossary_term: str | None = None


class MatchKeyIn(PramaModel):
    left: str
    right: str | None = None


class ToleranceIn(PramaModel):
    absolute: float | None = None
    relative: float | None = None
    currency: str | None = None
    rounding_scale: int | None = None


class OffsetIn(PramaModel):
    amount: int = 0
    unit: OffsetUnit = OffsetUnit.BUSINESS_DAYS
    calendar: str | None = None
    lagging_side: str = "to"


class RelationshipIn(PramaModel):
    kind: RelationshipKind
    from_dataset_id: str
    to_dataset_id: str
    match_keys: list[MatchKeyIn] = Field(default_factory=list)
    compare: list[str] = Field(default_factory=list)
    cardinality: Cardinality = Cardinality.MANY_TO_MANY
    tolerance: ToleranceIn | None = None
    offset: OffsetIn | None = None
    filter_expression: str | None = None
    name: str = ""
    description: str = ""
    owner_id: str | None = None
    criticality: int = Field(default=4, ge=1, le=4)
    approved_by: str | None = None
    reason: str = ""


class RelationshipDecisionIn(PramaModel):
    reason: str = ""


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class VersionMeta(PramaModel):
    """The bitemporal position of whatever is being returned.

    Present on every declaration response so a caller always knows *which*
    version they are holding — the question that matters as soon as anything is
    amended or corrected.
    """

    version: int
    valid_from: datetime
    valid_to: datetime | None = None
    recorded_at: datetime
    superseded_at: datetime | None = None
    authored_by: str | None = None
    approved_by: str | None = None
    change_reason: str = ""
    is_current: bool


class DatasetOut(PramaModel):
    id: str
    slug: str
    name: str
    description: str = ""
    purpose: str = ""
    domain_id: str | None = None
    owner_id: str | None = None
    steward_id: str | None = None
    criticality: int
    shape: str
    is_bound: bool
    grain: dict[str, Any] | None = None
    rhythm: dict[str, Any] | None = None
    temporality: str
    authoritativeness: str
    sensitivity: str
    lifecycle_state: str
    tags: list[str] = Field(default_factory=list)
    meta: VersionMeta


class AttributeOut(PramaModel):
    id: str
    dataset_id: str
    name: str
    ordinal: int
    definition: str = ""
    interpretation: str = ""
    semantic_type: str | None = None
    unit: str | None = None
    optionality: str
    is_cde: bool
    obligations: list[str] = Field(default_factory=list)
    sensitivity: str
    concept_property_id: str | None = None
    meta: VersionMeta


class RelationshipOut(PramaModel):
    id: str
    kind: str
    from_dataset_id: str
    to_dataset_id: str
    name: str = ""
    description: str = ""
    match_keys: list[dict[str, Any]] = Field(default_factory=list)
    compare: list[str] = Field(default_factory=list)
    cardinality: str
    tolerance: dict[str, Any] | None = None
    offset: dict[str, Any] | None = None
    status: str
    confidence: float | None = None
    discovered_by: str | None = None
    evidence: dict[str, Any] | None = None
    generates: list[str] = Field(
        default_factory=list, description="The control families this relationship produces."
    )
    meta: VersionMeta


class Page(PramaModel):
    total: int
    limit: int
    offset: int


class DatasetPage(PramaModel):
    items: list[DatasetOut]
    page: Page


class RelationshipKindOut(PramaModel):
    kind: str
    prompt: str = Field(description="How the choice is offered to a business user.")
    generates: list[str]
    needs_match_keys: bool
    needs_tolerance: bool
    directional: bool
    carries_trust: bool


class MaturityOut(PramaModel):
    scope: str
    score: float
    percent: int
    stage: str
    completion: dict[str, float]
    components: list[str]
    next_actions: list[dict[str, Any]]


class ConflictOut(PramaModel):
    kind: str
    severity: str
    property_id: str
    property_name: str
    values: dict[str, Any]
    attributes: dict[str, str]
    message: str


class HealthOut(PramaModel):
    status: str
    version: str
    schema_version: str
    dialect: str
    schema_file: str


class CapabilitiesOut(PramaModel):
    version: str
    ir_version: str
    schema_version: str
    dialects: list[str]
    relationship_kinds: list[str]
    features: dict[str, bool]


# ---------------------------------------------------------------------------
# Concepts, journeys, connections, bindings
# ---------------------------------------------------------------------------


class ConceptIn(PramaModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    domain_id: str | None = None
    pack_ref: str | None = Field(
        default=None, description="Set when the concept came from a domain pack."
    )


class ConceptPropertyIn(PramaModel):
    name: str = Field(min_length=1, max_length=128)
    definition: str = ""
    semantic_type: str | None = None
    unit: str | None = None
    value_domain: dict[str, Any] | None = None
    is_identifier: bool = Field(
        default=False, description="Whether this property identifies the concept."
    )


class AttributeMappingIn(PramaModel):
    property_id: str = Field(description="The canonical property this attribute claims to be.")


class ConceptOut(PramaModel):
    id: str
    name: str
    description: str = ""
    domain_id: str | None = None
    pack_ref: str | None = None
    meta: VersionMeta


class ConceptPropertyOut(PramaModel):
    id: str
    concept_id: str
    name: str
    definition: str = ""
    semantic_type: str | None = None
    unit: str | None = None
    value_domain: dict[str, Any] | None = None
    is_identifier: bool
    mapped_attribute_count: int = Field(
        default=0, description="How many attributes across the estate claim to be this."
    )
    meta: VersionMeta


class JourneyStepIn(PramaModel):
    kind: str = Field(default="dataset", description="dataset | black_box | manual")
    dataset_id: str | None = None
    description: str = ""
    expected_latency_seconds: float | None = None


class JourneyIn(PramaModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    domain_id: str | None = None
    owner_id: str | None = None
    criticality: int = Field(default=4, ge=1, le=4)
    sla: dict[str, Any] | None = None
    steps: list[JourneyStepIn] = Field(default_factory=list)
    approved_by: str | None = None


class JourneyStepsIn(PramaModel):
    reason: str = Field(min_length=1)
    steps: list[JourneyStepIn]


class JourneyOut(PramaModel):
    id: str
    slug: str
    name: str
    description: str = ""
    domain_id: str | None = None
    owner_id: str | None = None
    criticality: int
    sla: dict[str, Any] | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    step_count: int
    meta: VersionMeta


class ConnectionIn(PramaModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: str = Field(min_length=1, max_length=64)
    description: str = ""
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Typed per source family. May not contain a secret.",
    )
    credential_ref: str | None = Field(
        default=None,
        description=(
            "A vault reference, never a secret. A business user configures a connection "
            "they cannot read the credential for."
        ),
    )
    read_policy: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    owner_id: str | None = None


class ConnectionOut(PramaModel):
    id: str
    slug: str
    name: str
    source_type: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    credential_ref: str | None = None
    read_policy: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    owner_id: str | None = None
    health_state: str
    health_detail: str | None = None
    is_usable: bool
    meta: VersionMeta


class BindingIn(PramaModel):
    connection_id: str
    physical_ref: dict[str, Any] = Field(
        description="Where the object actually lives: schema, object, path, topic…"
    )
    shape: str = Field(default="table", description="What the dataset turned out to be.")
    attribute_id: str | None = Field(default=None, description="Omit to bind the dataset itself.")
    transform: str | None = None
    confidence: float | None = None


class BindingOut(PramaModel):
    id: str
    target_kind: str
    dataset_id: str
    attribute_id: str | None = None
    connection_id: str
    physical_ref: dict[str, Any] = Field(default_factory=dict)
    transform: str | None = None
    status: str
    confidence: float | None = None
    drift_state: str
    has_drifted: bool
    meta: VersionMeta

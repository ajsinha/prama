"""The semantic layer: datasets, attributes, relationships, concepts, journeys.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from prama.sdk.base import Resource, body, endpoint, namespace, seg


@namespace("datasets")
class Datasets(Resource):
    """Declared datasets and their attributes, versioned and bitemporal."""

    @endpoint("POST", "/datasets")
    def declare(self, name: str, **fields: Any) -> Any:
        """Declare a dataset. Fields: description, purpose, domain_id, owner_id,
        steward_id, criticality, shape, grain ({"attributes": [...], "statement": "one
        row is …"}), rhythm ({"frequency": "daily", "arrival_by": "07:00", …}),
        temporality, authoritativeness, sensitivity, tags, reason, valid_from.

        A Tier-1 or Tier-2 dataset is held (``lifecycle_state`` ``proposed``) until
        somebody holding ``declaration:approve`` approves it with `approve` — at
        Tier 1, somebody other than you."""
        return self._post("/datasets", body(name=name, **fields))

    @endpoint("GET", "/datasets")
    def list(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
        unbound: bool | None = None,
        criticality: int | None = None,
    ) -> Any:
        return self._get(
            "/datasets", limit=limit, offset=offset, unbound=unbound, criticality=criticality
        )

    @endpoint("GET", "/datasets/{dataset_id}")
    def get(
        self, dataset_id: str, *, valid_at: str | None = None, known_at: str | None = None
    ) -> Any:
        """A dataset as it is, or as it was valid (``valid_at``) or known (``known_at``)."""
        return self._get(f"/datasets/{seg(dataset_id)}", valid_at=valid_at, known_at=known_at)

    @endpoint("DELETE", "/datasets/{dataset_id}")
    def retire(self, dataset_id: str) -> Any:
        return self._delete(f"/datasets/{seg(dataset_id)}")

    @endpoint("GET", "/datasets/{dataset_id}/history")
    def history(self, dataset_id: str) -> Any:
        return self._get(f"/datasets/{seg(dataset_id)}/history")

    @endpoint("POST", "/datasets/{dataset_id}/amend")
    def amend(self, dataset_id: str, reason: str, **fields: Any) -> Any:
        """A new version, effective from a date. Fields: effective_from, changes.
        At Tier 1 or 2 the amendment is held until approved."""
        return self._post(f"/datasets/{seg(dataset_id)}/amend", body(reason=reason, **fields))

    @endpoint("POST", "/datasets/{dataset_id}/correct")
    def correct(self, dataset_id: str, reason: str, changes: dict[str, Any] | None = None) -> Any:
        """Fix what was recorded, keeping what was believed before."""
        return self._post(
            f"/datasets/{seg(dataset_id)}/correct", body(reason=reason, changes=changes)
        )

    @endpoint("POST", "/datasets/{dataset_id}/approve")
    def approve(self, dataset_id: str, *, reason: str | None = None) -> Any:
        """Approve a held declaration or amendment, as yourself. Needs
        ``declaration:approve``; at Tier 1 you cannot approve your own."""
        return self._post(f"/datasets/{seg(dataset_id)}/approve", body(reason=reason))

    @endpoint("POST", "/datasets/{dataset_id}/attributes")
    def add_attribute(
        self,
        dataset_id: str,
        name: str,
        *,
        codelist: Sequence[str] | None = None,
        minimum: float | None = None,
        maximum: float | None = None,
        **fields: Any,
    ) -> Any:
        """Declare an attribute. ``codelist`` (the permitted values) or ``minimum`` /
        ``maximum`` (a range) set its value domain, which Γ turns into a control; or pass
        ``value_domain`` whole ({kind, allowed_values, codelist_ref, minimum, maximum,
        pattern, case_sensitive}). Other fields: definition, interpretation,
        semantic_type, unit, currency_attribute, optionality ("mandatory"), is_cde,
        obligations, sensitivity, concept_property_id, glossary_term."""
        if codelist is not None:
            fields["value_domain"] = {"kind": "codelist", "allowed_values": list(codelist)}
        elif minimum is not None or maximum is not None:
            fields["value_domain"] = body(kind="range", minimum=minimum, maximum=maximum)
        return self._post(f"/datasets/{seg(dataset_id)}/attributes", body(name=name, **fields))

    @endpoint("GET", "/datasets/{dataset_id}/attributes")
    def attributes(self, dataset_id: str) -> Any:
        return self._get(f"/datasets/{seg(dataset_id)}/attributes")

    @endpoint("GET", "/critical-data-elements")
    def critical_data_elements(self) -> Any:
        return self._get("/critical-data-elements")


@namespace("relationships")
class Relationships(Resource):
    """How datasets relate: references, reconciliations, and the rest."""

    @endpoint("GET", "/relationship-kinds")
    def kinds(self) -> Any:
        return self._get("/relationship-kinds")

    @endpoint("POST", "/relationships")
    def declare(self, kind: str, from_dataset_id: str, to_dataset_id: str, **fields: Any) -> Any:
        """Fields: match_keys, compare, cardinality, tolerance, offset, filter_expression,
        name, description, owner_id, criticality, reason. At Tier 1 or 2 it is held as
        proposed; confirming it (`confirm`) is the approval, by somebody else at Tier 1."""
        return self._post(
            "/relationships",
            body(kind=kind, from_dataset_id=from_dataset_id, to_dataset_id=to_dataset_id, **fields),
        )

    @endpoint("GET", "/relationships")
    def list(
        self,
        *,
        dataset_id: str | None = None,
        kind: str | None = None,
        confirmed_only: bool | None = None,
    ) -> Any:
        return self._get(
            "/relationships", dataset_id=dataset_id, kind=kind, confirmed_only=confirmed_only
        )

    @endpoint("POST", "/relationships/{relationship_id}/confirm")
    def confirm(self, relationship_id: str, reason: str | None = None) -> Any:
        return self._post(f"/relationships/{seg(relationship_id)}/confirm", body(reason=reason))

    @endpoint("POST", "/relationships/{relationship_id}/reject")
    def reject(self, relationship_id: str, reason: str | None = None) -> Any:
        return self._post(f"/relationships/{seg(relationship_id)}/reject", body(reason=reason))


@namespace("concepts")
class Concepts(Resource):
    """Business concepts, their properties, and which attributes carry them."""

    @endpoint("POST", "/concepts")
    def declare(self, name: str, **fields: Any) -> Any:
        """Fields: description, domain_id, pack_ref."""
        return self._post("/concepts", body(name=name, **fields))

    @endpoint("GET", "/concepts")
    def list(self) -> Any:
        return self._get("/concepts")

    @endpoint("POST", "/concepts/{concept_id}/properties")
    def add_property(self, concept_id: str, name: str, **fields: Any) -> Any:
        """Fields: definition, semantic_type, unit, value_domain, is_identifier."""
        return self._post(f"/concepts/{seg(concept_id)}/properties", body(name=name, **fields))

    @endpoint("GET", "/concepts/{concept_id}/properties")
    def properties(self, concept_id: str) -> Any:
        return self._get(f"/concepts/{seg(concept_id)}/properties")

    @endpoint("POST", "/attributes/{attribute_id}/mapping")
    def map_attribute(self, attribute_id: str, property_id: str) -> Any:
        return self._post(f"/attributes/{seg(attribute_id)}/mapping", body(property_id=property_id))


@namespace("journeys")
class Journeys(Resource):
    """Declared business lineage: the steps a number takes."""

    @endpoint("POST", "/journeys")
    def declare(self, name: str, **fields: Any) -> Any:
        """Fields: description, domain_id, owner_id, criticality, sla, steps.
        Awaits approval (`approve`) until somebody signs it off."""
        return self._post("/journeys", body(name=name, **fields))

    @endpoint("GET", "/journeys")
    def list(self, *, dataset_id: str | None = None) -> Any:
        return self._get("/journeys", dataset_id=dataset_id)

    @endpoint("GET", "/journeys/{journey_id}")
    def get(self, journey_id: str) -> Any:
        return self._get(f"/journeys/{seg(journey_id)}")

    @endpoint("POST", "/journeys/{journey_id}/approve")
    def approve(self, journey_id: str, *, reason: str | None = None) -> Any:
        """Approve a journey declared without an approver, as yourself."""
        return self._post(f"/journeys/{seg(journey_id)}/approve", body(reason=reason))

    @endpoint("PUT", "/journeys/{journey_id}/steps")
    def set_steps(self, journey_id: str, reason: str, steps: Sequence[dict[str, Any]]) -> Any:
        return self._put(
            f"/journeys/{seg(journey_id)}/steps", body(reason=reason, steps=list(steps))
        )


@namespace("connections")
class Connections(Resource):
    """Where data lives, and how declared datasets bind to it."""

    @endpoint("POST", "/connections")
    def create(self, name: str, source_type: str, **fields: Any) -> Any:
        """Fields: description, config, credential_ref, read_policy, budget, owner_id."""
        return self._post("/connections", body(name=name, source_type=source_type, **fields))

    @endpoint("GET", "/connections")
    def list(self, *, unhealthy_only: bool | None = None) -> Any:
        return self._get("/connections", unhealthy_only=unhealthy_only)

    @endpoint("POST", "/datasets/{dataset_id}/bindings")
    def bind(self, dataset_id: str, connection_id: str, physical_ref: str, **fields: Any) -> Any:
        """Fields: shape, attribute_id, transform, confidence."""
        return self._post(
            f"/datasets/{seg(dataset_id)}/bindings",
            body(connection_id=connection_id, physical_ref=physical_ref, **fields),
        )

    @endpoint("GET", "/datasets/{dataset_id}/bindings")
    def bindings(self, dataset_id: str) -> Any:
        return self._get(f"/datasets/{seg(dataset_id)}/bindings")

    @endpoint("GET", "/bindings/drifted")
    def drifted(self) -> Any:
        return self._get("/bindings/drifted")


@namespace("estate")
class Estate(Resource):
    """The estate as a whole: maturity, conflicts, coverage gaps."""

    @endpoint("GET", "/estate/maturity")
    def maturity(self, *, domain_id: str | None = None, scope: str | None = None) -> Any:
        return self._get("/estate/maturity", domain_id=domain_id, scope=scope)

    @endpoint("GET", "/estate/conflicts")
    def conflicts(self) -> Any:
        return self._get("/estate/conflicts")

    @endpoint("GET", "/estate/coverage-gaps")
    def coverage_gaps(self) -> Any:
        return self._get("/estate/coverage-gaps")

    @endpoint("GET", "/estate/export")
    def export(self) -> Any:
        """The declared estate as YAML: ``{"files": {path: text}}``, to write under a directory."""
        return self._get("/estate/export")

    @endpoint("POST", "/estate/diff")
    def diff(self, files: dict[str, str]) -> Any:
        """Where these files (path -> YAML, as ``export`` gives them) disagree with the store."""
        return self._post("/estate/diff", body(files=dict(files)))

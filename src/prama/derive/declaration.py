"""The declaration, as the generator sees it.

A plain view of what a business owner wrote, with no database in it. The
generator cannot import SQLAlchemy — only ``prama.db`` may — and it should not
want to: Γ is a pure function from a declaration to a set of controls, and a
pure function is testable in a way a function that needs a session is not.

**These fields are a view, not a second definition.** The authority is
``SemDatasetVersion`` and ``SemAttributeVersion``; anything restated in a second
place drifts silently and in the flattering direction, so
``tests/architecture/test_declaration_coverage.py`` fails the build when a
control-generating column exists on the model and not here. That test is the
reason this file is allowed to exist at all.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.semantic.values import (
    Authoritativeness,
    Criticality,
    Grain,
    Optionality,
    Rhythm,
    Sensitivity,
    Temporality,
    ValueDomain,
)


@dataclasses.dataclass(frozen=True, slots=True)
class AttributeDeclaration:
    """What one field means, in the terms a control can be built from."""

    #: The physical column name. Controls are written against this.
    name: str
    #: What the value is.
    definition: str = ""
    #: What the attribute means to the business, in the owner's words.
    business_context: str = ""
    #: How to read it — sign conventions, inclusions, the calculation basis.
    #: Almost every cross-team disagreement about a number is an interpretation
    #: disagreement, and this is the only field it can be written in.
    interpretation: str = ""

    semantic_type: str = ""
    unit: str = ""
    #: The column holding the currency this amount is denominated in. A
    #: monetary column without one cannot be summed across rows, and an
    #: aggregate control over it would be adding euros to yen.
    currency_attribute: str = ""
    numeric_scale: int | None = None
    numeric_precision: int | None = None
    value_domain: ValueDomain = dataclasses.field(default_factory=ValueDomain)

    optionality: Optionality = Optionality.OPTIONAL
    #: When optionality is CONDITIONAL, the condition under which it is
    #: mandatory — a PQL expression, so it becomes the control's WHERE clause.
    optionality_condition: str = ""

    is_cde: bool = False
    #: Regulatory returns this attribute feeds: "FR Y-14Q", "FINREP".
    obligations: tuple[str, ...] = ()
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    masking_policy: str = ""
    #: How the value is expected to behave over time: "static", "monotonic",
    #: "volatile". Chooses the monitor, not the control.
    expected_behaviour: str = ""
    glossary_term: str = ""
    owner_id: str = ""

    @property
    def is_mandatory(self) -> bool:
        return self.optionality is Optionality.MANDATORY

    @property
    def is_monetary(self) -> bool:
        return self.unit.lower() in ("currency", "money", "amount") or bool(self.currency_attribute)

    @property
    def generates_a_domain_control(self) -> bool:
        return bool(self.semantic_type) or self.value_domain.is_constrained

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "definition": self.definition,
            "business_context": self.business_context,
            "interpretation": self.interpretation,
            "semantic_type": self.semantic_type,
            "unit": self.unit,
            "currency_attribute": self.currency_attribute,
            "numeric_scale": self.numeric_scale,
            "numeric_precision": self.numeric_precision,
            "value_domain": self.value_domain.to_dict(),
            "optionality": self.optionality.value,
            "optionality_condition": self.optionality_condition,
            "is_cde": self.is_cde,
            "obligations": list(self.obligations),
            "sensitivity": self.sensitivity.value,
            "masking_policy": self.masking_policy,
            "expected_behaviour": self.expected_behaviour,
            "glossary_term": self.glossary_term,
            "owner_id": self.owner_id,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AttributeDeclaration:
        """Build from the columns of ``sem_attribute_version``.

        Takes a mapping rather than the ORM object so this module stays free of
        SQLAlchemy, and so the same constructor serves a YAML declaration file
        and a test.
        """
        domain = row.get("value_domain_json") or {}
        return cls(
            name=row["name"],
            definition=row.get("definition") or "",
            business_context=row.get("business_context") or "",
            interpretation=row.get("interpretation") or "",
            semantic_type=row.get("semantic_type") or "",
            unit=row.get("unit") or "",
            currency_attribute=row.get("currency_attribute") or "",
            numeric_scale=row.get("numeric_scale"),
            numeric_precision=row.get("numeric_precision"),
            value_domain=ValueDomain.from_dict(domain) if domain else ValueDomain(),
            optionality=Optionality(row.get("optionality") or "optional"),
            optionality_condition=row.get("optionality_condition") or "",
            is_cde=bool(row.get("is_cde")),
            obligations=tuple(row.get("obligations_json") or ()),
            sensitivity=Sensitivity(row.get("sensitivity") or "internal"),
            masking_policy=row.get("masking_policy") or "",
            expected_behaviour=row.get("expected_behaviour") or "",
            glossary_term=row.get("glossary_term") or "",
            owner_id=row.get("owner_id") or "",
        )


@dataclasses.dataclass(frozen=True, slots=True)
class DatasetDeclaration:
    """What a dataset is, and everything about it that generates a control."""

    #: The name a control is written against. Physical, because a control has
    #: to run.
    name: str
    slug: str = ""
    description: str = ""
    purpose: str = ""
    #: What the dataset means to the business, in the owner's words.
    business_context: str = ""
    #: table, feed, stream, report … A feed's controls are not a table's.
    shape: str = "unbound"
    domain_id: str = ""
    owner_id: str = ""
    steward_id: str = ""
    #: Who runs the pipeline, as distinct from who owns the meaning. The
    #: routing difference that matters at 3am: a broken schema goes to the
    #: custodian and a wrong definition goes to the steward, and sending each
    #: to the other is how an incident spends its first hour.
    custodian_id: str = ""
    criticality: Criticality = Criticality.TIER_4

    grain: Grain | None = None
    business_key: tuple[str, ...] = ()
    temporality: Temporality = Temporality.SNAPSHOT
    rhythm: Rhythm | None = None
    authoritativeness: Authoritativeness = Authoritativeness.UNKNOWN
    #: The dataset this one is a copy of, when it is one. Generates parity and
    #: staleness controls, and demotes this dataset's independent trust score:
    #: a replica agreeing with its source is not a second opinion.
    source_of_truth: str = ""

    retention_days: int | None = None
    jurisdiction: str = ""
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    lifecycle_state: str = "proposed"
    tags: tuple[str, ...] = ()

    attributes: tuple[AttributeDeclaration, ...] = ()

    #: Who declared it and when, so a generated control can say so.
    declared_by: str = ""
    declared_at: str = ""
    #: The declaration's identifier, which is what "why does this exist?" links
    #: to.
    reference: str = ""

    @property
    def is_bound(self) -> bool:
        """A dataset with no physical shape is declared but not connected."""
        return self.shape != "unbound"

    @property
    def is_replica(self) -> bool:
        return self.authoritativeness.is_copy

    @property
    def is_live(self) -> bool:
        return self.lifecycle_state == "active"

    @property
    def cdes(self) -> tuple[AttributeDeclaration, ...]:
        return tuple(a for a in self.attributes if a.is_cde)

    @property
    def obligations(self) -> tuple[str, ...]:
        """Every regulatory return any attribute of this dataset feeds."""
        seen: dict[str, None] = {}
        for attribute in self.attributes:
            for obligation in attribute.obligations:
                seen.setdefault(obligation, None)
        return tuple(seen)

    def attribute(self, name: str) -> AttributeDeclaration | None:
        for candidate in self.attributes:
            if candidate.name == name:
                return candidate
        return None

    def has_attribute(self, name: str) -> bool:
        return self.attribute(name) is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "purpose": self.purpose,
            "business_context": self.business_context,
            "shape": self.shape,
            "domain_id": self.domain_id,
            "owner_id": self.owner_id,
            "steward_id": self.steward_id,
            "custodian_id": self.custodian_id,
            "criticality": int(self.criticality),
            "grain": self.grain.to_dict() if self.grain else None,
            "business_key": list(self.business_key),
            "temporality": self.temporality.value,
            "rhythm": self.rhythm.to_dict() if self.rhythm else None,
            "authoritativeness": self.authoritativeness.value,
            "source_of_truth": self.source_of_truth,
            "retention_days": self.retention_days,
            "jurisdiction": self.jurisdiction,
            "sensitivity": self.sensitivity.value,
            "lifecycle_state": self.lifecycle_state,
            "tags": list(self.tags),
            "attributes": [a.to_dict() for a in self.attributes],
            "declared_by": self.declared_by,
            "declared_at": self.declared_at,
            "reference": self.reference,
        }

    @classmethod
    def from_row(
        cls,
        row: dict[str, Any],
        attributes: tuple[dict[str, Any], ...] = (),
    ) -> DatasetDeclaration:
        """Build from the columns of ``sem_dataset_version`` and its attributes."""
        grain = row.get("grain_json")
        rhythm = row.get("rhythm_json")
        return cls(
            name=row["name"],
            slug=row.get("slug") or "",
            description=row.get("description") or "",
            purpose=row.get("purpose") or "",
            business_context=row.get("business_context") or "",
            shape=row.get("shape") or "unbound",
            domain_id=row.get("domain_id") or "",
            owner_id=row.get("owner_id") or "",
            steward_id=row.get("steward_id") or "",
            custodian_id=row.get("custodian_id") or "",
            criticality=Criticality(int(row.get("criticality", 4))),
            grain=Grain.from_dict(grain) if grain else None,
            business_key=tuple(row.get("business_key_json") or ()),
            temporality=Temporality(row.get("temporality") or "snapshot"),
            rhythm=Rhythm.from_dict(rhythm) if rhythm else None,
            authoritativeness=Authoritativeness(row.get("authoritativeness") or "unknown"),
            source_of_truth=row.get("source_of_truth_id") or "",
            retention_days=row.get("retention_days"),
            jurisdiction=row.get("jurisdiction") or "",
            sensitivity=Sensitivity(row.get("sensitivity") or "internal"),
            lifecycle_state=row.get("lifecycle_state") or "proposed",
            tags=tuple(row.get("tags_json") or ()),
            attributes=tuple(AttributeDeclaration.from_row(a) for a in attributes),
            declared_by=row.get("recorded_by") or "",
            declared_at=row.get("recorded_at") or "",
            reference=row.get("dataset_id") or "",
        )

"""Semantic conflict detection.

When twenty-three datasets map an attribute to ``Party.LEI``, the estate is
claiming they all mean the same thing. Usually they do. Sometimes two of them
disagree about units, or value domain, or optionality — and until now that
disagreement has had nowhere to become visible, so it has lived in a
reconciliation nobody could explain and a monthly argument between two teams.

Detection is only possible because the business *declared* the mapping. A
physical-first tool has nothing to compare: it sees two columns with different
names in different schemas and no reason to think they should agree.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any, ClassVar


class ConflictKind(enum.Enum):
    """What two attributes claiming one meaning can disagree about."""

    SEMANTIC_TYPE = "semantic_type"
    UNIT = "unit"
    VALUE_DOMAIN = "value_domain"
    OPTIONALITY = "optionality"
    SENSITIVITY = "sensitivity"
    CRITICALITY = "criticality"
    DEFINITION_ABSENT = "definition_absent"

    @property
    def severity(self) -> str:
        """How much this disagreement costs.

        A unit mismatch is the expensive one: two attributes that agree on
        everything except that one is in thousands will reconcile perfectly for
        years and be wrong by three orders of magnitude.
        """
        return {
            ConflictKind.UNIT: "critical",
            ConflictKind.SEMANTIC_TYPE: "critical",
            ConflictKind.VALUE_DOMAIN: "major",
            ConflictKind.OPTIONALITY: "minor",
            ConflictKind.SENSITIVITY: "major",
            ConflictKind.CRITICALITY: "minor",
            ConflictKind.DEFINITION_ABSENT: "info",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class SemanticConflict:
    """One disagreement, with enough context to act on it."""

    kind: ConflictKind
    property_id: str
    property_name: str
    values: dict[str, Any]  # attribute id -> the value it declares
    attribute_names: dict[str, str]  # attribute id -> its name

    @property
    def severity(self) -> str:
        return self.kind.severity

    @property
    def distinct_values(self) -> list[Any]:
        seen: list[Any] = []
        for value in self.values.values():
            if value not in seen:
                seen.append(value)
        return seen

    def render(self) -> str:
        rendered = ", ".join(
            f"{self.attribute_names.get(a, a)}={v!r}" for a, v in sorted(self.values.items())
        )
        return (
            f"{self.property_name}: {len(self.distinct_values)} different "
            f"{self.kind.value.replace('_', ' ')} values across "
            f"{len(self.values)} attributes ({rendered})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "severity": self.severity,
            "property_id": self.property_id,
            "property_name": self.property_name,
            "values": self.values,
            "attributes": self.attribute_names,
            "message": self.render(),
        }


class ConflictDetector:
    """Compares attributes that claim to be the same canonical property.

    Deliberately reports rather than resolves. Which of two definitions is right
    is a business decision, and a tool that picks one silently has made that
    decision on the business's behalf without telling anyone.
    """

    #: Attribute fields compared, and the conflict each mismatch produces.
    COMPARED: ClassVar[dict[str, ConflictKind]] = {
        "semantic_type": ConflictKind.SEMANTIC_TYPE,
        "unit": ConflictKind.UNIT,
        "optionality": ConflictKind.OPTIONALITY,
        "sensitivity": ConflictKind.SENSITIVITY,
    }

    def detect(
        self, property_id: str, property_name: str, attributes: list[Any]
    ) -> list[SemanticConflict]:
        """Find every disagreement among *attributes* mapped to one property."""
        if len(attributes) < 2:
            return []  # one claimant cannot disagree with itself

        names = {a.attribute_id: a.name for a in attributes}
        conflicts: list[SemanticConflict] = []

        for field, kind in self.COMPARED.items():
            values = {
                a.attribute_id: getattr(a, field, None)
                for a in attributes
                if getattr(a, field, None) is not None
            }
            if len(set(map(_hashable, values.values()))) > 1:
                conflicts.append(
                    SemanticConflict(
                        kind=kind,
                        property_id=property_id,
                        property_name=property_name,
                        values=values,
                        attribute_names=names,
                    )
                )

        domains = {
            a.attribute_id: _domain_signature(a.value_domain_json)
            for a in attributes
            if a.value_domain_json
        }
        if len(set(domains.values())) > 1:
            conflicts.append(
                SemanticConflict(
                    kind=ConflictKind.VALUE_DOMAIN,
                    property_id=property_id,
                    property_name=property_name,
                    values=dict(domains),
                    attribute_names=names,
                )
            )

        undefined = {a.attribute_id: "" for a in attributes if not (a.definition or "").strip()}
        if undefined and len(undefined) < len(attributes):
            # Some claimants define the property and some do not: the undefined
            # ones are inheriting a meaning nobody checked they agree with.
            conflicts.append(
                SemanticConflict(
                    kind=ConflictKind.DEFINITION_ABSENT,
                    property_id=property_id,
                    property_name=property_name,
                    values=undefined,
                    attribute_names=names,
                )
            )
        return conflicts

    def worst_severity(self, conflicts: list[SemanticConflict]) -> str | None:
        order = ["info", "minor", "major", "critical"]
        found = [c.severity for c in conflicts]
        return max(found, key=order.index) if found else None


def _hashable(value: Any) -> Any:
    return tuple(sorted(value.items())) if isinstance(value, dict) else value


def _domain_signature(domain: dict[str, Any] | None) -> str:
    """A comparable summary of a value domain.

    Compares what the domain *constrains*, not how it was written: two code-list
    domains pointing at the same list agree even if one spells out the values.
    """
    if not domain:
        return ""
    kind = domain.get("kind", "free_text")
    if kind == "codelist":
        return f"codelist:{domain.get('codelist_ref') or sorted(domain.get('allowed_values', []))}"
    if kind == "range":
        return f"range:{domain.get('minimum')}..{domain.get('maximum')}"
    if kind == "pattern":
        return f"pattern:{domain.get('pattern')}"
    return str(kind)

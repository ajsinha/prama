"""ODCS: importing and exporting the Open Data Contract Standard.

A data contract and a Prama declaration are the same idea reached from two
directions. A contract is what a producer promises a consumer; a declaration is
what a business owner states so controls can be derived. Most of the fields
line up, and the ones that do not are the interesting part.

**What does not come across is reported, not dropped.** An importer that
silently discarded half a contract would produce a declaration that looks
complete and generates a third of the controls it should. So the result carries
what was understood *and* a list of everything ignored, with the reason — the
same discipline `prama control import` already applies to dbt.

**Round-tripping is a property, not a hope.** A declaration exported and
re-imported must be the same declaration. Anything that survives one direction
and not the other is a field somebody will lose on the first migration, and the
test suite asserts it rather than trusting the mapping.

**Nothing is invented.** ODCS has no notion of a control's severity or of a
dataset's criticality tier, so an imported declaration carries the defaults and
*says so*. Guessing a tier from a description would produce a criticality
nobody assigned and controls nobody agreed to.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.semantic.values import Criticality, Optionality

#: The version of the standard this maps. Stated on every export, because a
#: contract with no version is one no consumer can validate against.
ODCS_VERSION = "3.0.0"

#: ODCS logical types to the semantic types Prama derives controls from. A type
#: absent here is carried as text and *reported*, rather than guessed at.
_TYPE_TO_SEMANTIC = {
    "string": "",
    "text": "",
    "number": "",
    "integer": "",
    "float": "",
    "decimal": "",
    "boolean": "",
    "date": "date",
    "timestamp": "timestamp",
    "object": "",
    "array": "",
}

_CRITICALITY_FROM = {
    "critical": Criticality.TIER_1,
    "high": Criticality.TIER_2,
    "medium": Criticality.TIER_3,
    "low": Criticality.TIER_4,
}
_CRITICALITY_TO = {value: key for key, value in _CRITICALITY_FROM.items()}


@dataclasses.dataclass(frozen=True, slots=True)
class Imported:
    """What came across, and what did not.

    The second half is the point. An importer that returned only a declaration
    would produce something that looks complete and generates a third of the
    controls it should.
    """

    declaration: DatasetDeclaration | None
    ignored: tuple[str, ...] = ()
    #: Facts Prama needs and the contract does not carry, so a reader knows the
    #: value is a default rather than a statement.
    defaulted: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        return not self.ignored and not self.defaulted

    def describe(self) -> str:
        if self.declaration is None:
            return "nothing was imported: " + ("; ".join(self.ignored) or "no reason given")
        parts = [f"{self.declaration.name}: {len(self.declaration.attributes)} attribute(s)"]
        if self.defaulted:
            # Before the ignored list, because a defaulted value is a number
            # that will appear on a screen as though somebody chose it.
            parts.append(
                f"{len(self.defaulted)} field(s) the contract does not carry, so they "
                f"hold defaults rather than statements: {', '.join(self.defaulted)}"
            )
        if self.ignored:
            parts.append(f"{len(self.ignored)} not imported: {'; '.join(self.ignored)}")
        return ". ".join(parts) + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            "imported": self.declaration is not None,
            "attributes": len(self.declaration.attributes) if self.declaration else 0,
            "ignored": list(self.ignored),
            "defaulted": list(self.defaulted),
            "complete": self.is_complete,
            "message": self.describe(),
        }


def load(contract: dict[str, Any]) -> Imported:
    """An ODCS contract as a Prama declaration, and what did not come across."""
    ignored: list[str] = []
    defaulted: list[str] = []

    schemas = contract.get("schema") or []
    if not schemas:
        return Imported(
            declaration=None,
            ignored=("the contract declares no schema, so there is no dataset to declare",),
        )
    if len(schemas) > 1:
        # Named rather than silently taking the first: a contract describing
        # four tables imported as one is three datasets nobody declared.
        ignored.append(
            f"{len(schemas) - 1} further schema object(s) — one contract imports as "
            "one dataset, so import the others separately"
        )

    schema = schemas[0]
    attributes: list[AttributeDeclaration] = []
    for column in schema.get("properties") or []:
        attributes.append(_attribute(column, ignored))

    if not contract.get("dataProduct") and not schema.get("name"):
        ignored.append("neither the contract nor its schema names the dataset")

    for absent, why in (
        ("criticality", "ODCS has no criticality tier"),
        ("grain", "ODCS has no grain declaration"),
        ("rhythm", "ODCS has no arrival rhythm"),
    ):
        if absent == "criticality" and _criticality(contract) is not None:
            continue
        defaulted.append(f"{absent} ({why})")

    for key in ("slaProperties", "team", "roles", "support", "price"):
        if contract.get(key):
            ignored.append(f"{key} — Prama has no field for it")

    # One mapping, stated once and used in both directions:
    #     ODCS description.purpose  <->  Prama purpose
    #     ODCS description.usage    <->  Prama description
    # The earlier version reached for the schema object's own description as a
    # fallback for one of them, which made a round trip *swap* the two — stable
    # under a single comparison and wrong on the second.
    described = contract.get("description")
    described = described if isinstance(described, dict) else {}

    declaration = DatasetDeclaration(
        name=schema.get("name") or contract.get("dataProduct") or "",
        purpose=described.get("purpose", ""),
        description=described.get("usage") or schema.get("description", ""),
        criticality=_criticality(contract) or Criticality.TIER_4,
        attributes=tuple(attributes),
        tags=tuple(contract.get("tags") or ()),
    )
    return Imported(declaration=declaration, ignored=tuple(ignored), defaulted=tuple(defaulted))


def _criticality(contract: dict[str, Any]) -> Criticality | None:
    for key in ("criticality", "dataQuality"):
        value = contract.get(key)
        if isinstance(value, str) and value.lower() in _CRITICALITY_FROM:
            return _CRITICALITY_FROM[value.lower()]
    return None


def _attribute(column: dict[str, Any], ignored: list[str]) -> AttributeDeclaration:
    name = column.get("name", "")
    logical = str(column.get("logicalType") or column.get("physicalType") or "").lower()
    if logical and logical not in _TYPE_TO_SEMANTIC:
        # Carried as text, and said out loud. A type quietly coerced is a
        # control generated against the wrong family.
        ignored.append(f"{name}: type {logical!r} is not one ODCS defines, kept as text")

    required = bool(column.get("required"))
    return AttributeDeclaration(
        name=name,
        definition=column.get("description", ""),
        semantic_type=_TYPE_TO_SEMANTIC.get(logical, ""),
        optionality=Optionality.MANDATORY if required else Optionality.OPTIONAL,
        is_cde=bool(column.get("criticalDataElement")),
        numeric_precision=column.get("precision"),
        numeric_scale=column.get("scale"),
    )


def dump(declaration: DatasetDeclaration) -> dict[str, Any]:
    """A declaration as an ODCS contract.

    Only what the standard has a place for. Prama's own fields — grain, rhythm,
    interpretation, custodian — have no ODCS equivalent, and inventing custom
    keys for them would produce a document that validates nowhere and that a
    consumer's tooling silently drops.
    """
    return {
        "apiVersion": ODCS_VERSION,
        "kind": "DataContract",
        "id": declaration.slug or declaration.name,
        "name": declaration.name,
        "version": "1.0.0",
        "status": declaration.lifecycle_state or "active",
        "description": {
            "purpose": declaration.purpose,
            "usage": declaration.description,
        },
        "criticality": _CRITICALITY_TO.get(declaration.criticality, "low"),
        "tags": list(declaration.tags),
        "schema": [
            {
                "name": declaration.name,
                "logicalType": "object",
                "physicalType": "table",
                "description": declaration.description,
                "properties": [_property(attribute) for attribute in declaration.attributes],
            }
        ],
    }


def _property(attribute: AttributeDeclaration) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": attribute.name,
        "logicalType": _logical_type(attribute),
        "description": attribute.definition,
        "required": attribute.optionality is Optionality.MANDATORY,
    }
    if attribute.is_cde:
        out["criticalDataElement"] = True
    if attribute.numeric_precision is not None:
        out["precision"] = attribute.numeric_precision
    if attribute.numeric_scale is not None:
        out["scale"] = attribute.numeric_scale
    return out


def _logical_type(attribute: AttributeDeclaration) -> str:
    if attribute.semantic_type in ("date", "timestamp"):
        return attribute.semantic_type
    if attribute.numeric_precision is not None or attribute.numeric_scale is not None:
        return "number"
    return "string"


__all__ = ["ODCS_VERSION", "Imported", "dump", "load"]

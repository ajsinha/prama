"""Declaring an estate the way a business owner would.

Every dataset here is described in business terms — what one row represents,
how often it arrives, how much a defect matters — and *nothing* is written in
SQL. That is the claim these studies exist to test: the controls come from the
declaration, not from somebody who already knew what to check.

These are plain descriptions, with no Prama import: the harness turns each into
the body of an SDK call. A study is a client of Prama like any other program,
and what it declares is exactly what a person could declare over the API.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True, slots=True)
class Attribute:
    """One field, described rather than typed."""

    name: str
    definition: str
    semantic_type: str = ""
    unit: str = ""
    mandatory: bool = False
    is_cde: bool = False
    codelist: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    currency_attribute: str = ""
    obligations: tuple[str, ...] = ()

    def to_api(self) -> dict[str, Any]:
        """The fields of ``client.datasets.add_attribute``."""
        fields: dict[str, Any] = {
            "definition": self.definition,
            "is_cde": self.is_cde,
            "optionality": "mandatory" if self.mandatory else "optional",
            "obligations": list(self.obligations),
        }
        for key, value in (
            ("semantic_type", self.semantic_type),
            ("unit", self.unit),
            ("currency_attribute", self.currency_attribute),
        ):
            if value:
                fields[key] = value
        if self.codelist:
            fields["value_domain"] = {"kind": "codelist", "allowed_values": list(self.codelist)}
        elif self.minimum is not None or self.maximum is not None:
            fields["value_domain"] = {
                "kind": "range",
                "minimum": self.minimum,
                "maximum": self.maximum,
            }
        return fields


@dataclasses.dataclass(frozen=True, slots=True)
class Dataset:
    """A dataset as its owner would describe it.

    There is no separate "physical name" field, deliberately. Prama derives the
    identifier a control is written against from the business name, and the
    generators name their tables and views to match. A study that carried both
    would be carrying a mapping — and a mapping is the thing that drifts.
    """

    name: str
    description: str
    grain_statement: str
    grain: tuple[str, ...]
    criticality: int
    shape: str = "table"
    attributes: tuple[Attribute, ...] = ()
    arrival_by: str = ""
    frequency: str = "daily"
    obligations: tuple[str, ...] = ()

    def to_api(self) -> dict[str, Any]:
        """The fields of ``client.datasets.declare``, after the name."""
        fields: dict[str, Any] = {
            "description": self.description,
            "criticality": self.criticality,
            "shape": self.shape,
            "tags": list(self.obligations),
            "reason": "declared for the case study",
        }
        if self.grain:
            fields["grain"] = {"attributes": list(self.grain), "statement": self.grain_statement}
        if self.arrival_by:
            fields["rhythm"] = {"frequency": self.frequency, "arrival_by": self.arrival_by}
        return fields


@dataclasses.dataclass(frozen=True, slots=True)
class Relationship:
    """What is true *between* two datasets, named by their slugs.

    ``kind`` is one of ``client.relationships.kinds()``: ``references``,
    ``reconciles_with`` and so on. ``match_keys`` pairs a column on the left with
    one on the right; ``compare`` states what must agree once rows are matched.
    """

    kind: str
    left: str
    right: str
    match_keys: tuple[tuple[str, str], ...] = ()
    compare: tuple[str, ...] = ()
    cardinality: str = "many_to_many"
    tolerance: dict[str, Any] | None = None
    offset: dict[str, Any] | None = None
    description: str = ""

    def to_api(self, ids: dict[str, str]) -> dict[str, Any]:
        """The fields of ``client.relationships.declare``, with slugs made ids."""
        fields: dict[str, Any] = {
            "kind": self.kind,
            "from_dataset_id": ids[self.left],
            "to_dataset_id": ids[self.right],
            "match_keys": [{"left": left, "right": right} for left, right in self.match_keys],
            "compare": list(self.compare),
            "cardinality": self.cardinality,
            "description": self.description,
            "criticality": 1,
            "reason": "declared for the case study",
        }
        if self.tolerance:
            fields["tolerance"] = self.tolerance
        if self.offset:
            fields["offset"] = self.offset
        return fields

    def render(self) -> str:
        keys = ", ".join(f"{a} = {b}" for a, b in self.match_keys)
        return f"{self.left} {self.kind} {self.right} on {keys}"

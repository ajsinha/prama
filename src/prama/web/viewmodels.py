"""What a template is allowed to see.

A projection, not a copy. Templates never touch an ORM row, for two reasons
that have nothing to do with taste: a lazily-loaded relationship resolved
inside Jinja is a query the request budget never accounted for, and a template
that reads ``version.grain_json["attributes"]`` couples the markup to a column
name that the schema is free to change.

Presentation logic that would otherwise be smeared across templates lives here
too — the tier label, the badge class, whether a dataset is describable at all.
Each of those has exactly one correct answer, and it should have exactly one
place that gives it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

# Criticality is 1-4 in the schema, and 1 is the most critical. Rendering that
# as the bare number invites the reader to assume bigger is worse, which is
# backwards, so it is never shown without its word. The words live beside
# `Criticality`, because the print packs name tiers too.
from prama.semantic.values import TIER_LABELS

TIER_CLASSES: dict[int, str] = {
    1: "text-bg-danger",
    2: "text-bg-warning",
    3: "text-bg-secondary",
    4: "text-bg-light",
}

SHAPE_ICONS: dict[str, str] = {
    "unbound": "bi-question-circle",
    "table": "bi-table",
    "table_set": "bi-stack",
    "schema": "bi-diagram-2",
    "feed": "bi-file-earmark-arrow-down",
    "feed_set": "bi-files",
    "stream": "bi-broadcast",
    "api": "bi-plug",
    "report": "bi-file-earmark-bar-graph",
    "query": "bi-search",
}


@dataclasses.dataclass(frozen=True, slots=True)
class DatasetCard:
    """A dataset as a list row or a map node."""

    id: str
    name: str
    slug: str
    description: str
    shape: str
    criticality: int
    lifecycle_state: str
    domain_id: str | None
    is_bound: bool
    has_grain: bool
    has_rhythm: bool
    owner_id: str | None

    @property
    def tier_label(self) -> str:
        return TIER_LABELS.get(self.criticality, f"Tier {self.criticality}")

    @property
    def tier_class(self) -> str:
        return TIER_CLASSES.get(self.criticality, "text-bg-light")

    @property
    def shape_icon(self) -> str:
        return SHAPE_ICONS.get(self.shape, "bi-box")

    @property
    def gaps(self) -> list[str]:
        """What this declaration still cannot generate a control from.

        Named as the missing capability rather than the missing field, because
        "no timeliness control can be generated" is actionable to a business
        owner and "rhythm_json is null" is not.
        """
        missing = []
        if not self.is_bound:
            missing.append("not connected — nothing can be executed against it")
        if not self.has_grain:
            missing.append("no grain — no uniqueness or completeness control")
        if not self.has_rhythm:
            missing.append("no rhythm — no timeliness control")
        if not self.description.strip():
            missing.append("no description — an incident here explains nothing")
        return missing

    @property
    def is_complete(self) -> bool:
        return not self.gaps

    @classmethod
    def of(cls, version: Any) -> DatasetCard:
        return cls(
            id=version.dataset_id,
            name=version.name,
            slug=version.slug,
            description=version.description or "",
            shape=version.shape,
            criticality=version.criticality,
            lifecycle_state=version.lifecycle_state,
            domain_id=version.domain_id,
            is_bound=version.is_bound,
            has_grain=version.has_grain,
            has_rhythm=version.has_rhythm,
            owner_id=version.owner_id,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class RelationshipEdge:
    """A declared or discovered relationship, as the map draws it."""

    id: str
    kind: str
    from_dataset_id: str
    to_dataset_id: str
    status: str
    confidence: float | None = None

    @property
    def is_proposed(self) -> bool:
        """Anything a human has not confirmed.

        Not ``status == "proposed"``. The schema also allows ``rejected`` and
        ``retired``, and drawing either of those as a solid declared edge would
        put a relationship somebody explicitly turned down on the map as
        though it were a fact.
        """
        return self.status != "confirmed"

    @property
    def style(self) -> str:
        """Proposed edges are dashed, and that is load-bearing.

        A discovered relationship drawn identically to a declared one invites
        the reader to treat an inference as a statement of fact — which is the
        exact confusion the confirm/reject workflow exists to prevent.
        """
        return "dashed" if self.is_proposed else "solid"

    @classmethod
    def of(cls, version: Any) -> RelationshipEdge:
        return cls(
            id=version.relationship_id,
            kind=version.kind,
            from_dataset_id=version.from_dataset_id,
            to_dataset_id=version.to_dataset_id,
            status=getattr(version, "status", "proposed"),
            confidence=getattr(version, "confidence", None),
        )

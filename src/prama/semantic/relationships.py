"""Business relationships: the declaration that turns an estate into a map.

Thirteen typed kinds, each of which generates a different family of controls.
This is the mechanism by which a sentence a business owner can say —

    "the sub-ledger reconciles with the GL on account and cost centre,
     in reporting currency, to within one euro, one day in arrears"

— becomes a running, evidenced reconciliation with a break workflow, without
anyone writing SQL.

Join keys are expressed in **business attribute** terms and resolved to physical
columns at compile time. A relationship therefore survives a column rename
beneath it, and can be declared before either side is bound to anything.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

from prama.core.errors import ValidationError


class RelationshipKind(enum.Enum):
    """What one dataset is to another.

    The plain-language prompt is what a user actually chooses from; the kind is
    what the generator dispatches on.
    """

    REFERENCES = "references"
    RECONCILES_WITH = "reconciles_with"
    DERIVES_FROM = "derives_from"
    FEEDS = "feeds"
    MIRRORS = "mirrors"
    AGGREGATES = "aggregates"
    ENRICHES = "enriches"
    SUPERSEDES = "supersedes"
    SAME_ENTITY_AS = "same_entity_as"
    TEMPORAL_SUCCESSOR = "temporal_successor"
    PARENT_OF = "parent_of"
    MUTUALLY_EXCLUSIVE = "mutually_exclusive"
    TOGETHER_COMPLETE = "together_complete"

    @property
    def prompt(self) -> str:
        """How the choice is offered to a business user, in their words."""
        return _PROMPTS[self]

    @property
    def generates(self) -> tuple[str, ...]:
        """The control families this kind produces (docs/03 §2.4)."""
        return _GENERATES[self]

    @property
    def requires_match_keys(self) -> bool:
        """Whether a declaration of this kind is meaningless without keys."""
        return self not in (
            RelationshipKind.FEEDS,
            RelationshipKind.SUPERSEDES,
            RelationshipKind.PARENT_OF,
        )

    @property
    def requires_tolerance(self) -> bool:
        """Kinds that compare values, and so need a materiality threshold."""
        return self in (
            RelationshipKind.RECONCILES_WITH,
            RelationshipKind.AGGREGATES,
            RelationshipKind.DERIVES_FROM,
        )

    @property
    def is_directional(self) -> bool:
        """Whether swapping the two sides changes the meaning."""
        return self not in (
            RelationshipKind.RECONCILES_WITH,
            RelationshipKind.SAME_ENTITY_AS,
            RelationshipKind.MUTUALLY_EXCLUSIVE,
            RelationshipKind.TOGETHER_COMPLETE,
        )

    @property
    def carries_trust(self) -> bool:
        """Whether quality propagates along this edge (docs/11 §2).

        Only kinds that move *data* propagate trust. ``MUTUALLY_EXCLUSIVE`` is a
        statement about populations, not a channel through which a defect
        travels, so trust does not flow along it.
        """
        return self in (
            RelationshipKind.DERIVES_FROM,
            RelationshipKind.FEEDS,
            RelationshipKind.MIRRORS,
            RelationshipKind.AGGREGATES,
            RelationshipKind.ENRICHES,
            RelationshipKind.TEMPORAL_SUCCESSOR,
        )


_PROMPTS: dict[RelationshipKind, str] = {
    RelationshipKind.REFERENCES: "records here point at records there",
    RelationshipKind.RECONCILES_WITH: "these two should agree",
    RelationshipKind.DERIVES_FROM: "this one is calculated from that one",
    RelationshipKind.FEEDS: "this one is delivered into that one",
    RelationshipKind.MIRRORS: "this one is a copy of that one",
    RelationshipKind.AGGREGATES: "this one summarises that one",
    RelationshipKind.ENRICHES: "this one adds fields to that one",
    RelationshipKind.SUPERSEDES: "this one replaces that one from a date",
    RelationshipKind.SAME_ENTITY_AS: "these describe the same real-world things",
    RelationshipKind.TEMPORAL_SUCCESSOR: "this one is the next period of that one",
    RelationshipKind.PARENT_OF: "this one sits above that one in a hierarchy",
    RelationshipKind.MUTUALLY_EXCLUSIVE: "a record should be in one or the other, never both",
    RelationshipKind.TOGETHER_COMPLETE: "together these cover the whole population",
}

_GENERATES: dict[RelationshipKind, tuple[str, ...]] = {
    RelationshipKind.REFERENCES: ("referential_integrity", "orphan_monitor", "key_coverage"),
    RelationshipKind.RECONCILES_WITH: ("reconciliation", "break_workflow", "certificate"),
    RelationshipKind.DERIVES_FROM: ("aggregate_parity", "trust_edge", "impact_path"),
    RelationshipKind.FEEDS: ("lineage_edge", "arrival_chain", "latency_sla"),
    RelationshipKind.MIRRORS: ("row_count_parity", "content_parity", "staleness"),
    RelationshipKind.AGGREGATES: ("rollup_parity", "trust_edge"),
    RelationshipKind.ENRICHES: ("enrichment_coverage", "provenance"),
    RelationshipKind.SUPERSEDES: ("migration_parity", "dual_run_comparison"),
    RelationshipKind.SAME_ENTITY_AS: (
        "entity_resolution",
        "duplicate_detection",
        "identifier_consistency",
    ),
    RelationshipKind.TEMPORAL_SUCCESSOR: ("roll_forward",),
    RelationshipKind.PARENT_OF: ("hierarchy_completeness", "cycle_detection", "orphan_node"),
    RelationshipKind.MUTUALLY_EXCLUSIVE: ("overlap_detection",),
    RelationshipKind.TOGETHER_COMPLETE: ("population_completeness",),
}


class Cardinality(enum.Enum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class RelationshipStatus(enum.Enum):
    """Proposed relationships are discovered; confirmed ones are declared.

    The distinction matters: a control derived from a *proposed* relationship is
    itself only a proposal, and never activates without a human confirming the
    relationship first.
    """

    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    RETIRED = "retired"


@dataclasses.dataclass(frozen=True, slots=True)
class MatchKey:
    """One join condition, in business attribute terms.

    ``left`` and ``right`` are attribute *names*, not columns. Where both sides
    use the same name — the common case — ``right`` may be omitted.
    """

    left: str
    right: str | None = None

    def __post_init__(self) -> None:
        if not self.left:
            raise ValidationError(
                "a match key needs an attribute on the left-hand side",
                remedy="Name the attribute the two datasets are joined on.",
            )

    @property
    def right_or_left(self) -> str:
        return self.right or self.left

    def render(self) -> str:
        return self.left if self.right in (None, self.left) else f"{self.left} = {self.right}"

    def to_dict(self) -> dict[str, Any]:
        return {"left": self.left, "right": self.right}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchKey:
        return cls(left=data["left"], right=data.get("right"))


@dataclasses.dataclass(frozen=True, slots=True)
class Tolerance:
    """How much difference is acceptable before it is a break.

    Both an absolute and a relative bound may be set; a difference must breach
    **both** to count. That is the convention finance operations already use —
    "a penny or a basis point, whichever is larger" — and encoding it here means
    the generated control matches the manual process it replaces.
    """

    absolute: float | None = None
    relative: float | None = None
    currency: str | None = None
    #: Compare after rounding to this many decimal places, if set.
    rounding_scale: int | None = None

    def __post_init__(self) -> None:
        if self.absolute is None and self.relative is None:
            raise ValidationError(
                "a tolerance needs an absolute or a relative bound",
                remedy="State the materiality, for example 1.00 EUR or 0.1%.",
            )
        if self.absolute is not None and self.absolute < 0:
            raise ValidationError(
                "an absolute tolerance cannot be negative",
                remedy="Use a positive materiality threshold.",
                context={"absolute": self.absolute},
            )
        if self.relative is not None and not 0 <= self.relative <= 1:
            raise ValidationError(
                f"a relative tolerance of {self.relative} is not a fraction between 0 and 1",
                remedy="Express 0.1% as 0.001.",
                context={"relative": self.relative},
            )

    def permits(self, difference: float, magnitude: float) -> bool:
        """Whether *difference* is within tolerance for a value of *magnitude*."""
        difference = abs(difference)
        absolute_ok = self.absolute is None or difference <= self.absolute
        relative_ok = (
            self.relative is None or not magnitude or difference / abs(magnitude) <= self.relative
        )
        # Both bounds must be breached for a difference to count as a break —
        # the "a penny or a basis point, whichever is larger" convention that
        # finance operations already use.
        return absolute_ok and relative_ok

    def render(self) -> str:
        parts = []
        if self.absolute is not None:
            parts.append(f"{self.absolute:g}{' ' + self.currency if self.currency else ''}")
        if self.relative is not None:
            parts.append(f"{self.relative * 100:g}%")
        return "within " + " or ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "absolute": self.absolute,
            "relative": self.relative,
            "currency": self.currency,
            "rounding_scale": self.rounding_scale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tolerance:
        return cls(
            absolute=data.get("absolute"),
            relative=data.get("relative"),
            currency=data.get("currency"),
            rounding_scale=data.get("rounding_scale"),
        )


class OffsetUnit(enum.Enum):
    BUSINESS_DAYS = "business_days"
    CALENDAR_DAYS = "calendar_days"
    HOURS = "hours"
    MINUTES = "minutes"
    PERIODS = "periods"


@dataclasses.dataclass(frozen=True, slots=True)
class TimeOffset:
    """How far apart in time the two sides are expected to be.

    "The GL is one business day behind the sub-ledger" is not a nuance — compare
    them without it and every reconciliation breaks every day.
    """

    amount: int = 0
    unit: OffsetUnit = OffsetUnit.BUSINESS_DAYS
    calendar: str | None = None
    #: Which side lags. ``to`` means the right-hand dataset is behind.
    lagging_side: str = "to"

    def __post_init__(self) -> None:
        if self.lagging_side not in ("from", "to"):
            raise ValidationError(
                f"lagging side {self.lagging_side!r} must be 'from' or 'to'",
                remedy="Say which of the two datasets is behind the other.",
            )
        if self.unit is OffsetUnit.BUSINESS_DAYS and self.amount and not self.calendar:
            raise ValidationError(
                "a business-day offset needs a calendar",
                remedy=(
                    "Name the calendar, for example TARGET2 or SIFMA. Without one, "
                    "'one business day' is not a defined quantity."
                ),
            )

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    def render(self) -> str:
        if self.is_zero:
            return "same period"
        unit = self.unit.value.replace("_", " ")
        if abs(self.amount) == 1:
            unit = unit.removesuffix("s")
        side = "the second" if self.lagging_side == "to" else "the first"
        cal = f" ({self.calendar})" if self.calendar else ""
        return f"{side} lags by {self.amount} {unit}{cal}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "amount": self.amount,
            "unit": self.unit.value,
            "calendar": self.calendar,
            "lagging_side": self.lagging_side,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimeOffset:
        return cls(
            amount=int(data.get("amount", 0)),
            unit=OffsetUnit(data.get("unit", "business_days")),
            calendar=data.get("calendar"),
            lagging_side=data.get("lagging_side", "to"),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class RelationshipDeclaration:
    """A complete, validated relationship declaration.

    Validation happens here rather than in the DAO so that a malformed
    declaration is refused at the point it is written — in the UI, in the API,
    or in a YAML file in CI — and never reaches storage.
    """

    kind: RelationshipKind
    from_dataset_id: str
    to_dataset_id: str
    match_keys: tuple[MatchKey, ...] = ()
    compare: tuple[str, ...] = ()
    cardinality: Cardinality = Cardinality.MANY_TO_MANY
    tolerance: Tolerance | None = None
    offset: TimeOffset | None = None
    filter_expression: str | None = None
    name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if self.from_dataset_id == self.to_dataset_id:
            raise ValidationError(
                "a relationship must join two different datasets",
                remedy=(
                    "To express a rule within one dataset, use a control rather than a "
                    "relationship."
                ),
                context={"dataset": self.from_dataset_id},
            )
        if self.kind.requires_match_keys and not self.match_keys:
            raise ValidationError(
                f"a {self.kind.value!r} relationship needs at least one match key",
                remedy=(
                    f"Name the attribute(s) that join the two datasets. "
                    f"Without them, '{self.kind.prompt}' cannot be checked."
                ),
                context={"kind": self.kind.value},
            )
        if self.kind.requires_tolerance and self.tolerance is None:
            raise ValidationError(
                f"a {self.kind.value!r} relationship needs a tolerance",
                remedy=(
                    "State the materiality — for example 'within 1.00 EUR'. A comparison "
                    "with no tolerance breaks on the first rounding difference."
                ),
                context={"kind": self.kind.value},
            )
        if self.kind is RelationshipKind.RECONCILES_WITH and not self.compare:
            raise ValidationError(
                "a reconciliation needs at least one attribute to compare",
                remedy="Name the value being reconciled, for example amount.",
            )

    @property
    def generates(self) -> tuple[str, ...]:
        return self.kind.generates

    def render(self) -> str:
        """The sentence that appears in every generated control's BECAUSE clause."""
        parts = [self.kind.prompt]
        if self.match_keys:
            parts.append("on " + ", ".join(k.render() for k in self.match_keys))
        if self.compare:
            parts.append("comparing " + ", ".join(self.compare))
        if self.tolerance is not None:
            parts.append(self.tolerance.render())
        if self.offset is not None and not self.offset.is_zero:
            parts.append(self.offset.render())
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "from_dataset_id": self.from_dataset_id,
            "to_dataset_id": self.to_dataset_id,
            "match_keys": [k.to_dict() for k in self.match_keys],
            "compare": list(self.compare),
            "cardinality": self.cardinality.value,
            "tolerance": self.tolerance.to_dict() if self.tolerance else None,
            "offset": self.offset.to_dict() if self.offset else None,
            "filter_expression": self.filter_expression,
            "name": self.name,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RelationshipDeclaration:
        return cls(
            kind=RelationshipKind(data["kind"]),
            from_dataset_id=data["from_dataset_id"],
            to_dataset_id=data["to_dataset_id"],
            match_keys=tuple(MatchKey.from_dict(k) for k in data.get("match_keys", ())),
            compare=tuple(data.get("compare", ())),
            cardinality=Cardinality(data.get("cardinality", "many_to_many")),
            tolerance=Tolerance.from_dict(data["tolerance"]) if data.get("tolerance") else None,
            offset=TimeOffset.from_dict(data["offset"]) if data.get("offset") else None,
            filter_expression=data.get("filter_expression"),
            name=data.get("name", ""),
            description=data.get("description", ""),
        )

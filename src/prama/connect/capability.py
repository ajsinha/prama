"""The capability matrix.

The compiler consults this and never guesses. A connector declares what its
engine can genuinely do; where a construct is unsupported, compilation fails at
authoring time with a clear message rather than degrading silently into
something that means almost the same thing.

"Almost the same thing" is the failure mode this exists to prevent: a regex that
matches slightly differently, a decimal that rounds differently, a null that
sorts the other way. Each is invisible in development and load-bearing in
production.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

from prama.core.registry import Capability


class PushdownFeature(enum.Enum):
    """What a source engine can be asked to do on Prama's behalf."""

    SQL = "pushdown.sql"
    AGGREGATION = "pushdown.aggregation"
    FILTER = "pushdown.filter"
    WINDOW = "pushdown.window"
    QUALIFY = "pushdown.qualify"
    REGEX = "pushdown.regex"
    APPROX_DISTINCT = "pushdown.approx_distinct"
    QUANTILES = "pushdown.quantiles"
    SAMPLING = "pushdown.sampling"
    JSON_PATH = "pushdown.json_path"
    TIME_TRAVEL = "pushdown.time_travel"
    PARTITION_PRUNING = "pushdown.partition_pruning"
    PREDICATE_PUSHDOWN = "pushdown.predicate"
    PARALLEL_READ = "pushdown.parallel_read"
    EXACT_SNAPSHOT = "snapshot.exact"
    CROSS_OBJECT_JOIN = "pushdown.join"

    @property
    def label(self) -> str:
        return self.value.split(".", 1)[1].replace("_", " ")


@dataclasses.dataclass(frozen=True, slots=True)
class CapabilityMatrix:
    """What one connector can be relied upon to do.

    Immutable and declared, never probed. Probing a production database to find
    out whether it supports a window function is both rude and unreliable.
    """

    features: frozenset[PushdownFeature] = frozenset()
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)

    def supports(self, feature: PushdownFeature) -> bool:
        return feature in self.features

    def require(self, feature: PushdownFeature) -> None:
        """Refuse at compile time rather than degrade at run time."""
        if not self.supports(feature):
            from prama.connect.spi import ConnectorError

            raise ConnectorError(
                f"this source cannot perform {feature.label} at the source",
                code="CONNECT.CAPABILITY_MISSING",
                remedy=(
                    "Rewrite the control without it, or run it through the Arrow backend "
                    "and accept the cost of moving the data. Prama will not substitute a "
                    "construct that means almost the same thing."
                ),
                context={"feature": feature.value},
            )

    @property
    def regex_flavour(self) -> str:
        """Which regex dialect the engine speaks.

        Recorded because the flavours genuinely differ, and a control that
        depends on one is not portable to the others — a fact the author should
        learn while writing it, not from a production mismatch.
        """
        return str(self.attributes.get("regex_flavour", "none"))

    @property
    def max_decimal_precision(self) -> int | None:
        value = self.attributes.get("max_decimal_precision")
        return int(value) if value is not None else None

    @property
    def nulls_sort_first(self) -> bool | None:
        value = self.attributes.get("nulls_sort_first")
        return bool(value) if value is not None else None

    def to_capabilities(self) -> tuple[Capability, ...]:
        """Render for a plugin manifest."""
        return tuple(
            Capability(feature.value, dict(self.attributes))
            for feature in sorted(self.features, key=lambda f: f.value)
        )

    def describe(self) -> list[str]:
        return sorted(f.value for f in self.features)

    @classmethod
    def of(cls, *features: PushdownFeature, **attributes: Any) -> CapabilityMatrix:
        return cls(features=frozenset(features), attributes=attributes)


#: A connector that declares nothing. Correct, and fully functional: the engine
#: reads Arrow and evaluates locally.
NO_PUSHDOWN = CapabilityMatrix()

#: What an ANSI-SQL engine can generally be relied on for. Individual connectors
#: narrow or widen it; none of them inherit a claim they cannot honour.
BASELINE_SQL = CapabilityMatrix.of(
    PushdownFeature.SQL,
    PushdownFeature.FILTER,
    PushdownFeature.AGGREGATION,
    PushdownFeature.PREDICATE_PUSHDOWN,
)

"""Estate maturity: how much of the estate the business has actually described.

A number that is useful precisely because it is uncomfortable. A domain with
four hundred datasets, six owners and no declared relationships has a low score,
and the score is the argument for doing something about it.

The design constraint from docs/corpus/03 §3 governs the weighting: **every declaration
must pay for itself immediately**. So the stages are weighted by the *control
value they unlock*, not by how much effort they take — and the next-best-action
ranking says what to do next in terms of controls gained, never in terms of
forms to fill in.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any


class MaturityStage(enum.Enum):
    """The seven stages of progressive formalisation (docs/corpus/03 §3)."""

    DISCOVERED = "discovered"  # 0: connected, profiled, nothing declared
    NAMED = "named"  # 1: named and owned
    SHAPED = "shaped"  # 2: grain and rhythm declared
    INTERPRETED = "interpreted"  # 3: attributes interpreted, CDEs marked
    RELATED = "related"  # 4: relationships declared
    MAPPED = "mapped"  # 5: attributes mapped to concepts
    JOURNEYED = "journeyed"  # 6: business processes declared

    @property
    def ordinal(self) -> int:
        return list(MaturityStage).index(self)


#: Weight per stage, chosen by the control value it unlocks rather than by the
#: effort it costs. Relationships weigh most because they generate the
#: highest-value controls in the product — reconciliation, roll-forward,
#: referential integrity — and because nothing else can generate them.
STAGE_WEIGHTS: dict[MaturityStage, float] = {
    MaturityStage.NAMED: 0.10,
    MaturityStage.SHAPED: 0.20,
    MaturityStage.INTERPRETED: 0.20,
    MaturityStage.RELATED: 0.30,
    MaturityStage.MAPPED: 0.10,
    MaturityStage.JOURNEYED: 0.10,
}


@dataclasses.dataclass(frozen=True, slots=True)
class EstateFacts:
    """The counts a maturity score is computed from.

    Held as a value object so the score is a pure function of stated facts —
    testable without a database, and explainable without re-running a query.
    """

    datasets: int = 0
    datasets_owned: int = 0
    datasets_with_grain: int = 0
    datasets_with_rhythm: int = 0
    datasets_bound: int = 0
    attributes: int = 0
    attributes_defined: int = 0
    attributes_mapped_to_concepts: int = 0
    critical_data_elements: int = 0
    tier_one_datasets: int = 0
    tier_one_datasets_with_grain: int = 0
    relationships_confirmed: int = 0
    journeys: int = 0
    journey_datasets: int = 0

    def _ratio(self, numerator: int, denominator: int) -> float:
        return 0.0 if denominator <= 0 else min(1.0, numerator / denominator)

    def stage_completion(self) -> dict[MaturityStage, float]:
        """How far through each stage the estate is, 0.0 to 1.0."""
        # A domain with no datasets has not failed to mature; it has nothing to
        # mature. Zero out cleanly rather than dividing by zero.
        if self.datasets == 0:
            return dict.fromkeys(STAGE_WEIGHTS, 0.0)

        # One confirmed relationship per two datasets is treated as full marks:
        # relationships are declared between things, so the population is
        # inherently smaller than the dataset count.
        expected_relationships = max(1, self.datasets // 2)

        return {
            MaturityStage.NAMED: self._ratio(self.datasets_owned, self.datasets),
            MaturityStage.SHAPED: (
                self._ratio(self.datasets_with_grain, self.datasets) * 0.6
                + self._ratio(self.datasets_with_rhythm, self.datasets) * 0.4
            ),
            MaturityStage.INTERPRETED: self._ratio(self.attributes_defined, self.attributes),
            MaturityStage.RELATED: self._ratio(
                self.relationships_confirmed, expected_relationships
            ),
            MaturityStage.MAPPED: self._ratio(self.attributes_mapped_to_concepts, self.attributes),
            MaturityStage.JOURNEYED: self._ratio(self.journey_datasets, self.datasets),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class NextAction:
    """What to do next, stated in controls gained rather than forms to fill."""

    stage: MaturityStage
    headline: str
    detail: str
    estimated_controls: int
    effort_items: int

    @property
    def value_per_item(self) -> float:
        return 0.0 if self.effort_items == 0 else self.estimated_controls / self.effort_items

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "headline": self.headline,
            "detail": self.detail,
            "estimated_controls": self.estimated_controls,
            "effort_items": self.effort_items,
            "value_per_item": round(self.value_per_item, 2),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class MaturityScore:
    """The score, its components, and what it implies doing next."""

    scope: str
    facts: EstateFacts
    completion: dict[MaturityStage, float]
    score: float
    stage: MaturityStage
    actions: tuple[NextAction, ...]

    @property
    def percent(self) -> int:
        return round(self.score * 100)

    def explain(self) -> list[str]:
        """Every component, so the number is never a black box."""
        return [
            f"{stage.value}: {self.completion[stage] * 100:.0f}% "
            f"(weight {STAGE_WEIGHTS[stage] * 100:.0f}%)"
            for stage in STAGE_WEIGHTS
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "score": round(self.score, 4),
            "percent": self.percent,
            "stage": self.stage.value,
            "completion": {s.value: round(v, 4) for s, v in self.completion.items()},
            "components": self.explain(),
            "next_actions": [a.to_dict() for a in self.actions],
        }


class MaturityAssessor:
    """Computes the score and ranks what to do next.

    Control estimates are deliberate approximations of the Γ generator's output
    (docs/corpus/03 §5): declaring a grain yields roughly three controls, a rhythm two,
    a relationship three. They are used only to *rank* actions, so being
    approximately right is enough and being precisely wrong would be worse.
    """

    CONTROLS_PER_GRAIN = 3
    CONTROLS_PER_RHYTHM = 2
    CONTROLS_PER_RELATIONSHIP = 3
    CONTROLS_PER_CDE = 2
    CONTROLS_PER_CONCEPT_MAPPING = 1

    def assess(self, scope: str, facts: EstateFacts) -> MaturityScore:
        completion = facts.stage_completion()
        score = sum(completion[stage] * weight for stage, weight in STAGE_WEIGHTS.items())
        return MaturityScore(
            scope=scope,
            facts=facts,
            completion=completion,
            score=score,
            stage=self._reached_stage(completion),
            actions=tuple(self.next_actions(facts)),
        )

    @staticmethod
    def _reached_stage(completion: dict[MaturityStage, float]) -> MaturityStage:
        """The furthest stage that is substantially complete.

        A stage counts as reached at 80%: insisting on 100% would leave every
        real estate stuck at stage one for ever, because there is always one
        dataset nobody has got to.
        """
        reached = MaturityStage.DISCOVERED
        for stage in STAGE_WEIGHTS:
            if completion.get(stage, 0.0) >= 0.8:
                reached = stage
            else:
                break
        return reached

    def next_actions(self, facts: EstateFacts) -> list[NextAction]:
        """Ranked by controls unlocked per item of effort."""
        actions: list[NextAction] = []

        # Tier-1 datasets without a grain are always the best next move: highest
        # criticality, and the grain is the single most generative declaration.
        missing_tier_one_grain = facts.tier_one_datasets - facts.tier_one_datasets_with_grain
        if missing_tier_one_grain > 0:
            actions.append(
                NextAction(
                    stage=MaturityStage.SHAPED,
                    headline=f"Declare the grain of {missing_tier_one_grain} Tier-1 dataset(s)",
                    detail=(
                        "One sentence each — 'what does one row represent?' — enables "
                        "uniqueness, duplicate and completeness controls on your most "
                        "critical data."
                    ),
                    estimated_controls=missing_tier_one_grain * self.CONTROLS_PER_GRAIN,
                    effort_items=missing_tier_one_grain,
                )
            )

        missing_grain = facts.datasets - facts.datasets_with_grain - missing_tier_one_grain
        if missing_grain > 0:
            actions.append(
                NextAction(
                    stage=MaturityStage.SHAPED,
                    headline=f"Declare the grain of {missing_grain} further dataset(s)",
                    detail="Enables uniqueness and duplicate detection.",
                    estimated_controls=missing_grain * self.CONTROLS_PER_GRAIN,
                    effort_items=missing_grain,
                )
            )

        missing_rhythm = facts.datasets - facts.datasets_with_rhythm
        if missing_rhythm > 0:
            actions.append(
                NextAction(
                    stage=MaturityStage.SHAPED,
                    headline=f"Declare when {missing_rhythm} dataset(s) are expected",
                    detail=(
                        "Arrival window and volume drivers enable freshness controls and a "
                        "volume monitor that already knows about month-end."
                    ),
                    estimated_controls=missing_rhythm * self.CONTROLS_PER_RHYTHM,
                    effort_items=missing_rhythm,
                )
            )

        expected_relationships = max(1, facts.datasets // 2)
        missing_relationships = expected_relationships - facts.relationships_confirmed
        if missing_relationships > 0:
            actions.append(
                NextAction(
                    stage=MaturityStage.RELATED,
                    headline=f"Declare {missing_relationships} relationship(s) between datasets",
                    detail=(
                        "The highest-value declarations in the product: reconciliation, "
                        "roll-forward and referential integrity can be generated no other way."
                    ),
                    estimated_controls=missing_relationships * self.CONTROLS_PER_RELATIONSHIP,
                    effort_items=missing_relationships,
                )
            )

        undefined = facts.attributes - facts.attributes_defined
        if undefined > 0:
            actions.append(
                NextAction(
                    stage=MaturityStage.INTERPRETED,
                    headline=f"Interpret {undefined} attribute(s)",
                    detail=(
                        "Semantic types and value domains generate format, checksum and "
                        "membership controls, and sharply improve rule induction."
                    ),
                    estimated_controls=undefined,
                    effort_items=undefined,
                )
            )

        unmapped = facts.attributes - facts.attributes_mapped_to_concepts
        if unmapped > 0 and facts.attributes_defined > 0:
            actions.append(
                NextAction(
                    stage=MaturityStage.MAPPED,
                    headline=f"Map {unmapped} attribute(s) to canonical concepts",
                    detail=(
                        "Enables estate-wide controls authored once, and makes "
                        "conflicting definitions of the same thing visible."
                    ),
                    estimated_controls=unmapped * self.CONTROLS_PER_CONCEPT_MAPPING,
                    effort_items=unmapped,
                )
            )

        unbound = facts.datasets - facts.datasets_bound
        if unbound > 0:
            actions.append(
                NextAction(
                    stage=MaturityStage.NAMED,
                    headline=f"Connect {unbound} declared dataset(s) to a source",
                    detail=(
                        "These are declared but unreachable: Prama knows they should exist "
                        "and cannot yet read them."
                    ),
                    estimated_controls=0,  # unblocks controls rather than creating them
                    effort_items=unbound,
                )
            )

        actions.sort(key=lambda a: (-a.value_per_item, a.effort_items))
        return actions

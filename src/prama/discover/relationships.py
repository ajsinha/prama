"""Candidate relationships between datasets, from several weak signals.

`FR-MET-065`: key overlap, containment, naming, schema signature, query-log
co-access. Five signals, and the design turns on the fact that **not one of
them is sufficient alone.**

*Naming* is the obvious one and the worst. Every table in every warehouse has
``id``, ``name``, ``status``, ``created_at`` and ``updated_at``; matching on
column name proposes a relationship between every pair of tables in the estate,
which is a report nobody can read and which discredits the ones that were real.

*Containment* is strong and has one specific false positive: a small code list
is contained in everything. Twelve currency codes appear in the currency column
of every table that has one, and none of those is a foreign key to the others.

*Schema signature* — two datasets sharing an unusual set of column names —
finds copies, replicas and migrations that nothing else finds, and cannot tell
them apart from two tables built from the same template.

*Query-log co-access* is the only signal that comes from what people actually
do rather than from what the data looks like. Two datasets joined in the same
query every morning are related, whatever their column names suggest. It is
also the only signal that is often unavailable.

So a candidate is the **combination**, with each signal's contribution stated
separately, and a candidate resting on one signal says so. A reviewer looking at
"the names match, the values are contained, and they are joined together in
forty queries a week" approves in a second; the same candidate showing only the
first is a question rather than a finding, and should look like one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Sequence
from typing import Any

from prama.core.provenance import Origin, Provenance, identity
from prama.mine.dependencies import InclusionMiner
from prama.mine.sample import Sample
from prama.semantic.relationships import MatchKey, RelationshipKind

#: Column names that carry no information about what a table is about. Matching
#: on one of these is the single largest source of false relationships, because
#: every table has them.
GENERIC_NAMES: frozenset[str] = frozenset(
    {
        "id",
        "name",
        "code",
        "type",
        "status",
        "value",
        "amount",
        "date",
        "created_at",
        "updated_at",
        "version",
        "source",
        "description",
        "comment",
        "flag",
        "key",
        "ref",
        "reference",
        "category",
        "level",
    }
)

#: A candidate resting on fewer than this many independent signals is reported
#: as weak. Not suppressed — a single strong signal is sometimes the whole
#: story — but a reviewer must be able to see which they are looking at.
CORROBORATING_SIGNALS = 2


class Signal:
    NAMING = "naming"
    CONTAINMENT = "containment"
    KEY_OVERLAP = "key_overlap"
    SCHEMA_SIGNATURE = "schema_signature"
    CO_ACCESS = "co_access"


@dataclasses.dataclass(frozen=True, slots=True)
class Evidence:
    """One signal's contribution, kept separate from the others."""

    signal: str
    strength: float
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal,
            "strength": round(self.strength, 4),
            "detail": self.detail,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class CandidateRelationship:
    """Two datasets that look related, and everything suggesting they are."""

    left: str
    right: str
    kind: RelationshipKind
    match_keys: tuple[MatchKey, ...]
    evidence: tuple[Evidence, ...]

    @property
    def confidence(self) -> float:
        """Combined strength, with agreement counting for more than volume.

        Signals are combined as independent evidence rather than averaged. Two
        weak agreeing signals beat one strong one, which is the whole reason to
        gather five of them — averaging would let a single naming match drag a
        well-corroborated candidate down to its level.
        """
        remaining = 1.0
        for item in self.evidence:
            remaining *= 1.0 - min(0.95, max(0.0, item.strength))
        return 1.0 - remaining

    @property
    def signals(self) -> tuple[str, ...]:
        return tuple(e.signal for e in self.evidence)

    @property
    def is_corroborated(self) -> bool:
        return len(self.evidence) >= CORROBORATING_SIGNALS

    def describe(self) -> str:
        keys = ", ".join(k.render() for k in self.match_keys)
        # The kind's prompt is written for a screen that already names both
        # datasets — "records here point at records there" — so it is quoted
        # rather than slotted into a sentence, which produced "positions may
        # records here point at records there accounts".
        head = f"{self.left} → {self.right} may be {self.kind.value}: {self.kind.prompt}"
        if keys:
            head += f", matched on {keys}"
        reasons = "; ".join(e.detail for e in self.evidence)
        if not self.is_corroborated:
            return (
                f"{head}. This rests on a single signal — {reasons} — which is a "
                f"question rather than a finding"
            )
        return f"{head}. {reasons}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "kind": self.kind.value,
            "match_keys": [k.to_dict() for k in self.match_keys],
            "confidence": round(self.confidence, 4),
            "signals": list(self.signals),
            "is_corroborated": self.is_corroborated,
            "evidence": [e.to_dict() for e in self.evidence],
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class DiscoveryReport:
    candidates: tuple[CandidateRelationship, ...] = ()
    #: Pairs that matched on a generic name alone, counted rather than listed.
    #: The number is the useful part: "412 pairs matched on `id`" tells
    #: somebody why the report is short, where 412 entries would tell them
    #: nothing and bury the four that mattered.
    suppressed: dict[str, int] = dataclasses.field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.candidates)

    @property
    def corroborated(self) -> tuple[CandidateRelationship, ...]:
        return tuple(c for c in self.candidates if c.is_corroborated)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "suppressed": dict(self.suppressed),
        }


class RelationshipDiscoverer:
    """Proposes relationships from what the data and its use look like."""

    def __init__(self, *, minimum_containment: float = 0.9) -> None:
        self._inclusions = InclusionMiner(minimum_containment=minimum_containment)

    def discover(
        self,
        left: Sample,
        right: Sample,
        *,
        co_access: int = 0,
        co_access_total: int = 0,
    ) -> DiscoveryReport:
        """Everything suggesting these two datasets are related.

        ``co_access`` is how many queries in the log touch both, out of
        ``co_access_total``. Passed in rather than read here, because the query
        log is a connector's concern and is frequently unavailable — a
        discoverer that needed it would be a discoverer that does not run.
        """
        suppressed: dict[str, int] = {}
        by_pair: dict[tuple[str, str], list[Evidence]] = {}

        for inclusion in self._inclusions.mine(left, right).inclusions:
            pair = (inclusion.left_column, inclusion.right_column)
            by_pair.setdefault(pair, []).append(
                Evidence(
                    signal=Signal.CONTAINMENT,
                    strength=0.8 if inclusion.is_exact else 0.65,
                    detail=(
                        f"{inclusion.evidence.support:.0%} of {left.dataset}."
                        f"{inclusion.left_column} values appear in {right.dataset}."
                        f"{inclusion.right_column}"
                    ),
                )
            )

        for name in set(left.columns) & set(right.columns):
            if _is_generic(name):
                # The single largest source of false relationships. Counted so
                # the report can say why it is short.
                suppressed["generic_name"] = suppressed.get("generic_name", 0) + 1
                continue
            by_pair.setdefault((name, name), []).append(
                Evidence(
                    signal=Signal.NAMING,
                    #: Weak on purpose. A shared name is a hint and has never
                    #: been evidence.
                    strength=0.35,
                    detail=f"both datasets have a column called {name}",
                )
            )

        signature = self._signature(left, right)
        if signature is not None:
            for evidence in by_pair.values():
                evidence.append(signature)

        if co_access and co_access_total:
            share = co_access / co_access_total
            access = Evidence(
                signal=Signal.CO_ACCESS,
                # The strongest signal available, because it is the only one
                # that reflects what people actually do rather than what the
                # data looks like.
                strength=min(0.9, 0.4 + share),
                detail=(f"{co_access} of {co_access_total} logged queries touch both datasets"),
            )
            for evidence in by_pair.values():
                evidence.append(access)

        candidates = [
            CandidateRelationship(
                left=left.dataset,
                right=right.dataset,
                kind=self._kind(evidence, signature is not None),
                match_keys=(MatchKey(left_column, right_column),),
                evidence=tuple(evidence),
            )
            for (left_column, right_column), evidence in by_pair.items()
        ]
        candidates.sort(key=lambda c: (-c.confidence, c.match_keys[0].left))
        return DiscoveryReport(candidates=tuple(candidates), suppressed=suppressed)

    @staticmethod
    def _signature(left: Sample, right: Sample) -> Evidence | None:
        """Whether the two share an unusually specific set of column names.

        Finds copies, replicas and migrations that nothing else finds, and
        genuinely cannot distinguish them from two tables built from the same
        template — which is why it contributes a signal rather than a verdict.
        """
        distinctive_left = {c for c in left.columns if not _is_generic(c)}
        distinctive_right = {c for c in right.columns if not _is_generic(c)}
        if len(distinctive_left) < 3 or len(distinctive_right) < 3:
            return None
        shared = distinctive_left & distinctive_right
        union = distinctive_left | distinctive_right
        overlap = len(shared) / len(union)
        if overlap < 0.6:
            return None
        return Evidence(
            signal=Signal.SCHEMA_SIGNATURE,
            strength=0.5 + 0.3 * overlap,
            detail=(
                f"the two share {len(shared)} of {len(union)} distinctive column names "
                f"({overlap:.0%}), which usually means one is a copy, a replica or a "
                f"migration of the other — or that both came from the same template"
            ),
        )

    @staticmethod
    def _kind(evidence: list[Evidence], has_signature: bool) -> RelationshipKind:
        """The most likely kind, which is a guess and is offered as one.

        A near-identical schema suggests a copy; containment suggests a
        reference. Both are the *usual* reading, and the declarer is the one
        who knows — which is why this produces a candidate to confirm rather
        than a relationship to store.
        """
        signals = {e.signal for e in evidence}
        if has_signature and Signal.SCHEMA_SIGNATURE in signals:
            return RelationshipKind.MIRRORS
        if Signal.CONTAINMENT in signals:
            return RelationshipKind.REFERENCES
        return RelationshipKind.SAME_ENTITY_AS


def _is_generic(name: str) -> bool:
    """Whether a column name says anything about what the table is about."""
    lowered = re.sub(r"[^a-z0-9_]", "", name.lower())
    return lowered in GENERIC_NAMES


def discovery_provenance(candidate: CandidateRelationship) -> Provenance:
    return Provenance(
        origin=Origin.MINING,
        rule="discover.relationship",
        source_ref=f"{candidate.left}~{candidate.right}",
        statement=candidate.describe(),
        observations=tuple(e.detail for e in candidate.evidence),
    )


def discovery_identity(candidate: CandidateRelationship) -> str:
    key = candidate.match_keys[0]
    return identity(
        candidate.left,
        "discover.relationship",
        candidate.right,
        f"{key.left}->{key.right_or_left}",
    )


def rank(reports: Sequence[DiscoveryReport]) -> tuple[CandidateRelationship, ...]:
    """Every candidate across several pairs, best-supported first."""
    everything = [c for report in reports for c in report.candidates]
    everything.sort(key=lambda c: (-c.confidence, c.left, c.right))
    return tuple(everything)

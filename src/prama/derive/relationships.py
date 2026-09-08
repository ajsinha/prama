"""Γ for the thirteen relationship kinds.

Half of a business's quality problems live *between* datasets rather than
inside one, and the declarations that describe them — "these two should agree",
"this one summarises that one", "a record should be in one or the other, never
both" — are the ones a business owner can answer without help.

**Two kinds of output, and the distinction is not bureaucratic.** PQL's
assertion catalogue is about one dataset and the rows in it, with a single
cross-dataset escape hatch: ``REFERENCES``, which lowers to a correlated
``EXISTS``. Some relationships fit that exactly, and they generate ordinary
controls that run today.

The rest are *comparisons*: two populations, matched on keys, with a tolerance
and often a time offset, where the answer is a difference rather than a count of
bad rows. Reconciliation is the obvious one — "the sub-ledger and the GL agree
to a euro, and the GL is one business day behind" is not a row predicate and
never will be. Compiling it into one would produce something that runs and
answers a different question, which is the failure mode this codebase is
organised against.

So a comparison declaration produces a :class:`ComparisonSpec`: a complete,
executable-by-the-reconciliation-engine description carrying both sides, the
match keys, the compared attributes, the tolerance and the offset. It is a
first-class artefact rather than a deferral — the declaration is captured
exactly, it can be reviewed, costed and shown, and nothing pretends to run that
cannot.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Callable
from typing import Any

from prama.core.provenance import Origin, Provenance, content_hash, identity
from prama.derive.generator import DerivedControl, Generation, Unsatisfiable
from prama.pql import ast
from prama.semantic.relationships import (
    Cardinality,
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
    TimeOffset,
    Tolerance,
)

# ---------------------------------------------------------------------------
# Comparisons: the half of the catalogue a row predicate cannot express
# ---------------------------------------------------------------------------


class ComparisonKind(enum.Enum):
    """What a two-population check actually asks."""

    #: Do the two sides have the same number of rows?
    ROW_COUNT_PARITY = "row_count_parity"
    #: For each matched key, do the named attributes agree within tolerance?
    VALUE_PARITY = "value_parity"
    #: Value parity, plus the break classification and ageing that turn a
    #: difference into a piece of work somebody owns.
    RECONCILIATION = "reconciliation"
    #: Does the summary equal the sum of what it summarises?
    AGGREGATE_PARITY = "aggregate_parity"
    #: Opening plus movements equals closing, across consecutive periods.
    ROLL_FORWARD = "roll_forward"
    #: Does any key appear on both sides when it should appear on one?
    OVERLAP = "overlap"
    #: Do the two sides together cover the whole population?
    COVERAGE = "coverage"
    #: Is the copy behind its source by more than the declared tolerance?
    STALENESS = "staleness"
    #: Do two records for the same real-world thing carry the same identifiers?
    IDENTIFIER_CONSISTENCY = "identifier_consistency"

    @property
    def needs_tolerance(self) -> bool:
        return self in (
            ComparisonKind.VALUE_PARITY,
            ComparisonKind.RECONCILIATION,
            ComparisonKind.AGGREGATE_PARITY,
            ComparisonKind.ROLL_FORWARD,
        )

    @property
    def needs_compared_attributes(self) -> bool:
        return self in (
            ComparisonKind.VALUE_PARITY,
            ComparisonKind.RECONCILIATION,
            ComparisonKind.AGGREGATE_PARITY,
            ComparisonKind.IDENTIFIER_CONSISTENCY,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ComparisonSpec:
    """A cross-dataset check, fully specified.

    Everything the reconciliation engine needs and nothing it has to infer. The
    inference is where cross-dataset checks go wrong: a comparison that guesses
    its join, its materiality or its time alignment produces breaks that are
    artefacts of the guess, and the first week of every reconciliation project
    is spent explaining those away.
    """

    identity: str
    kind: ComparisonKind
    left: str
    right: str
    match_keys: tuple[MatchKey, ...]
    compare: tuple[str, ...] = ()
    tolerance: Tolerance | None = None
    offset: TimeOffset | None = None
    cardinality: Cardinality = Cardinality.MANY_TO_MANY
    filter_expression: str = ""
    severity: ast.Severity = ast.Severity.MAJOR
    provenance: Provenance = dataclasses.field(
        default_factory=lambda: Provenance(origin=Origin.DECLARATION, rule="")
    )
    rule: str = ""
    #: What a break here means and what is done about it. Set for the kinds
    #: that carry an operational workflow rather than just an alert.
    workflow: str = ""

    @property
    def content_hash(self) -> str:
        return content_hash(self.render())

    def render(self) -> str:
        """A canonical one-line form, for diffing and for the review queue."""
        keys = ", ".join(k.render() for k in self.match_keys)
        parts = [f"COMPARE {self.left} WITH {self.right} ON ({keys})"]
        if self.compare:
            parts.append(f"MATCHING {', '.join(self.compare)}")
        if self.tolerance is not None:
            parts.append(self.tolerance.render().upper())
        if self.offset is not None and not self.offset.is_zero:
            parts.append(f"OFFSET {self.offset.render()}")
        if self.filter_expression:
            parts.append(f"WHERE {self.filter_expression}")
        parts.append(f"AS {self.kind.value.upper()}")
        return " ".join(parts)

    def describe(self) -> str:
        """The check as a sentence, for somebody who will approve it."""
        keys = " and ".join(k.render() for k in self.match_keys)
        head = _COMPARISON_SENTENCES[self.kind].format(
            left=self.left,
            right=self.right,
            keys=keys,
            compare=" and ".join(self.compare) or "the matched rows",
        )
        if self.tolerance is not None:
            head += f", {self.tolerance.render()}"
        if self.offset is not None and not self.offset.is_zero:
            head += f", allowing that {self.offset.render()}"
        return head + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "kind": self.kind.value,
            "rule": self.rule,
            "left": self.left,
            "right": self.right,
            "match_keys": [k.to_dict() for k in self.match_keys],
            "compare": list(self.compare),
            "tolerance": self.tolerance.to_dict() if self.tolerance else None,
            "offset": self.offset.to_dict() if self.offset else None,
            "cardinality": self.cardinality.value,
            "filter_expression": self.filter_expression,
            "severity": self.severity.value,
            "workflow": self.workflow,
            "content_hash": self.content_hash,
            "description": self.describe(),
            "provenance": self.provenance.to_dict(),
        }


_COMPARISON_SENTENCES: dict[ComparisonKind, str] = {
    ComparisonKind.ROW_COUNT_PARITY: "{left} and {right} hold the same number of rows",
    ComparisonKind.VALUE_PARITY: (
        "for every {keys} present in both, {left} and {right} agree on {compare}"
    ),
    ComparisonKind.RECONCILIATION: (
        "for every {keys}, {left} and {right} agree on {compare}, and every difference "
        "is classified, aged and owned until it is cleared"
    ),
    ComparisonKind.AGGREGATE_PARITY: (
        "{left} equals the sum of {right} over {compare}, grouped by {keys}"
    ),
    ComparisonKind.ROLL_FORWARD: (
        "for every {keys}, the opening balance in {left} plus the movements equals the "
        "closing balance in {right}"
    ),
    ComparisonKind.OVERLAP: (
        "no {keys} appears in both {left} and {right}; a record belongs to one of them"
    ),
    ComparisonKind.COVERAGE: (
        "every {keys} in the population appears in {left} or {right}, so together they cover it"
    ),
    ComparisonKind.STALENESS: ("{left} is not behind {right} by more than the declared tolerance"),
    ComparisonKind.IDENTIFIER_CONSISTENCY: (
        "where {left} and {right} describe the same thing, matched on {keys}, they "
        "carry the same {compare}"
    ),
}


@dataclasses.dataclass(frozen=True, slots=True)
class Edge:
    """A graph edge a relationship implies, distinct from any check.

    ``FEEDS`` generates no control at all; what it generates is knowledge —
    that a defect here reaches there, that an incident upstream has downstream
    consequences, and that a trust score should not be computed as though the
    two were independent. Recording it as an edge rather than as a control is
    the honest shape: it is used by impact analysis and by scoring, and it never
    produces a verdict.
    """

    kind: str
    source: str
    target: str
    #: Whether quality propagates along it (docs/11 §2).
    carries_trust: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "target": self.target,
            "carries_trust": self.carries_trust,
            "reason": self.reason,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class RelationshipGeneration:
    """Everything a relationship declaration produced."""

    controls: tuple[DerivedControl, ...] = ()
    comparisons: tuple[ComparisonSpec, ...] = ()
    edges: tuple[Edge, ...] = ()
    unsatisfiable: tuple[Unsatisfiable, ...] = ()

    def __len__(self) -> int:
        return len(self.controls) + len(self.comparisons)

    @property
    def is_complete(self) -> bool:
        return not self.unsatisfiable

    def merge(self, other: RelationshipGeneration) -> RelationshipGeneration:
        return RelationshipGeneration(
            controls=(*self.controls, *other.controls),
            comparisons=(*self.comparisons, *other.comparisons),
            edges=(*self.edges, *other.edges),
            unsatisfiable=(*self.unsatisfiable, *other.unsatisfiable),
        )

    def comparison(self, kind: ComparisonKind) -> ComparisonSpec | None:
        for spec in self.comparisons:
            if spec.kind is kind:
                return spec
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "controls": [c.to_dict() for c in self.controls],
            "comparisons": [c.to_dict() for c in self.comparisons],
            "edges": [e.to_dict() for e in self.edges],
            "unsatisfiable": [u.to_dict() for u in self.unsatisfiable],
        }


# ---------------------------------------------------------------------------
# The generator
# ---------------------------------------------------------------------------


class RelationshipGenerator:
    """Γ for relationships. One declaration in, controls and comparisons out."""

    def __init__(self, *, severity: ast.Severity = ast.Severity.MAJOR) -> None:
        #: The floor for controls generated here. A relationship spans two
        #: datasets whose criticalities may differ, and the honest default is
        #: the *higher* of the two — which the caller knows and this class does
        #: not, so it is passed in rather than guessed.
        self._severity = severity

    def generate(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        rule: Callable[[RelationshipGenerator, RelationshipDeclaration], RelationshipGeneration]
        rule = _DISPATCH[declaration.kind]
        result = rule(self, declaration)
        edge = self._edge(declaration)
        return result.merge(RelationshipGeneration(edges=(edge,)))

    # -- the kinds that fit a row predicate --------------------------------

    def _references(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        """``REFERENCES`` is the one cross-dataset shape PQL can already run.

        Lowered to a correlated ``EXISTS`` rather than a null check — an earlier
        implementation compiled it to ``IS NOT NULL``, which passes on every
        orphan there has ever been.
        """
        controls = [
            self._control(
                declaration,
                rule="references.integrity",
                subject=key.left,
                control=ast.Control(
                    target=declaration.from_dataset_id,
                    assertion=ast.ReferenceAssertion(
                        column=ast.ColumnRef(name=key.left),
                        target_dataset=declaration.to_dataset_id,
                        target_column=key.right_or_left,
                    ),
                    name=f"{declaration.from_dataset_id}_{key.left}_references",
                    severity=self._severity,
                    dimensions=(ast.Dimension.INTEGRITY,),
                    because=(
                        f"{declaration.kind.prompt}: every {key.left} in "
                        f"{declaration.from_dataset_id} must exist in "
                        f"{declaration.to_dataset_id}.{key.right_or_left}"
                    ),
                ),
            )
            for key in declaration.match_keys
        ]
        return RelationshipGeneration(controls=tuple(controls))

    def _enriches(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        """Enrichment coverage is a reference check with a different sentence.

        "Every enriched row traces back to a source row" is exactly
        ``REFERENCES``. Saying so, rather than inventing a second mechanism, is
        why the same executor runs both.
        """
        generation = self._references(declaration)
        controls = tuple(
            dataclasses.replace(
                derived,
                rule="enriches.coverage",
                control=dataclasses.replace(
                    derived.control,
                    dimensions=(ast.Dimension.COMPLETENESS,),
                    because=(
                        f"{declaration.to_dataset_id} adds fields to "
                        f"{declaration.from_dataset_id}. An enriched row with no source "
                        f"row is a value that came from nowhere, which is worse than a "
                        f"missing one because it will be used"
                    ),
                ),
            )
            for derived in generation.controls
        )
        return RelationshipGeneration(controls=controls)

    def _parent_of(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        """A hierarchy: the orphan check runs, the cycle check cannot.

        Detecting a cycle needs transitive closure, which is a recursive query
        rather than a row predicate. Emitting a one-level approximation would
        report a clean hierarchy containing a loop three levels down — a
        control that looks like coverage and is not.
        """
        if not declaration.match_keys:
            return RelationshipGeneration(
                unsatisfiable=(
                    Unsatisfiable(
                        rule="parent_of.orphan_node",
                        declared=declaration.render(),
                        reason="no match key names the parent pointer",
                        remedy=(
                            "Name the column holding the parent's identifier, for "
                            "example parent_id = node_id. Without it the hierarchy "
                            "cannot be walked."
                        ),
                        dataset=declaration.from_dataset_id,
                    ),
                )
            )
        controls = [
            self._control(
                declaration,
                rule="parent_of.orphan_node",
                subject=key.left,
                control=ast.Control(
                    target=declaration.to_dataset_id,
                    assertion=ast.ReferenceAssertion(
                        column=ast.ColumnRef(name=key.left),
                        target_dataset=declaration.from_dataset_id,
                        target_column=key.right_or_left,
                    ),
                    name=f"{declaration.to_dataset_id}_{key.left}_has_parent",
                    severity=self._severity,
                    dimensions=(ast.Dimension.INTEGRITY,),
                    because=(
                        f"{declaration.from_dataset_id} sits above "
                        f"{declaration.to_dataset_id} in a hierarchy. A node whose "
                        f"parent does not exist is unreachable from the root, so every "
                        f"rollup that walks the tree silently omits it"
                    ),
                ),
            )
            for key in declaration.match_keys
        ]
        return RelationshipGeneration(controls=tuple(controls))

    # -- the kinds that are comparisons ------------------------------------

    def _reconciles(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        return self._comparison(
            declaration,
            ComparisonKind.RECONCILIATION,
            rule="reconciles_with.reconciliation",
            workflow=(
                "differences are classified by cause, aged, and owned until cleared; a "
                "period closes with a certificate naming what was outstanding and who "
                "accepted it"
            ),
        )

    def _derives_from(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        return self._comparison(
            declaration,
            ComparisonKind.AGGREGATE_PARITY,
            rule="derives_from.aggregate_parity",
        )

    def _aggregates(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        return self._comparison(
            declaration, ComparisonKind.AGGREGATE_PARITY, rule="aggregates.rollup_parity"
        )

    def _mirrors(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        """A copy's real controls: is it the same, and is it current.

        Both, not either. Row-count parity alone passes a replica that copied
        the right number of rows with stale values in them; content parity
        alone passes one that is missing a thousand rows it never received.
        """
        result = self._comparison(
            declaration, ComparisonKind.ROW_COUNT_PARITY, rule="mirrors.row_count_parity"
        )
        if declaration.compare:
            result = result.merge(
                self._comparison(
                    declaration,
                    ComparisonKind.VALUE_PARITY,
                    rule="mirrors.content_parity",
                    # Exact by default, and no tolerance demanded. A replica is
                    # supposed to be identical to its source; asking what
                    # difference is acceptable in a copy invites an answer, and
                    # any answer above zero makes the control unable to detect
                    # the thing it exists for.
                    require_tolerance=False,
                )
            )
        return result.merge(
            self._comparison(declaration, ComparisonKind.STALENESS, rule="mirrors.staleness")
        )

    def _supersedes(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        return self._comparison(
            declaration,
            ComparisonKind.VALUE_PARITY,
            rule="supersedes.dual_run_comparison",
            workflow=(
                "run both and compare while the old system is still authoritative. A "
                "migration verified only after the cutover is a migration verified by "
                "the people who have to live with it"
            ),
        )

    def _same_entity(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        return self._comparison(
            declaration,
            ComparisonKind.IDENTIFIER_CONSISTENCY,
            rule="same_entity_as.identifier_consistency",
        )

    def _temporal_successor(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        return self._comparison(
            declaration, ComparisonKind.ROLL_FORWARD, rule="temporal_successor.roll_forward"
        )

    def _mutually_exclusive(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        return self._comparison(
            declaration, ComparisonKind.OVERLAP, rule="mutually_exclusive.overlap_detection"
        )

    def _together_complete(self, declaration: RelationshipDeclaration) -> RelationshipGeneration:
        return self._comparison(
            declaration, ComparisonKind.COVERAGE, rule="together_complete.population"
        )

    # -- the kind that generates knowledge rather than a check -------------

    def _feeds(
        self,
        declaration: RelationshipDeclaration,  # noqa: ARG002 — the edge is the output
    ) -> RelationshipGeneration:
        """``FEEDS`` produces an edge, and deliberately no control.

        The temptation is to generate an arrival control on the receiving side.
        That control already exists — it is the target's own rhythm — and
        generating a second one produces two alerts for one late file, from two
        different declarations, which is how an estate becomes unowned.

        What the declaration genuinely adds is the *edge*: that a defect here
        reaches there, that an incident upstream has downstream consequences,
        and that the two datasets' trust scores are not independent.
        """
        return RelationshipGeneration()

    # -- shared construction ------------------------------------------------

    def _comparison(
        self,
        declaration: RelationshipDeclaration,
        kind: ComparisonKind,
        *,
        rule: str,
        workflow: str = "",
        require_tolerance: bool | None = None,
    ) -> RelationshipGeneration:
        problem = self._comparison_problem(
            declaration,
            kind,
            rule,
            kind.needs_tolerance if require_tolerance is None else require_tolerance,
        )
        if problem is not None:
            return RelationshipGeneration(unsatisfiable=(problem,))
        spec = ComparisonSpec(
            identity=identity(
                declaration.name or declaration.kind.value,
                rule,
                declaration.from_dataset_id,
                declaration.to_dataset_id,
            ),
            kind=kind,
            left=declaration.from_dataset_id,
            right=declaration.to_dataset_id,
            match_keys=declaration.match_keys,
            compare=declaration.compare if kind.needs_compared_attributes else (),
            tolerance=declaration.tolerance,
            offset=declaration.offset,
            cardinality=declaration.cardinality,
            filter_expression=declaration.filter_expression or "",
            severity=self._severity,
            rule=rule,
            workflow=workflow,
            provenance=self._provenance(declaration, rule),
        )
        return RelationshipGeneration(comparisons=(spec,))

    @staticmethod
    def _comparison_problem(
        declaration: RelationshipDeclaration,
        kind: ComparisonKind,
        rule: str,
        require_tolerance: bool,
    ) -> Unsatisfiable | None:
        """What a comparison cannot be built without.

        Each of these produces a comparison that *runs* if it is guessed at,
        which is the reason to refuse rather than default. A reconciliation with
        no tolerance breaks on the first rounding difference and is switched off
        the same week; one with no compared attribute compares nothing and
        reports a clean reconciliation.
        """
        if kind.needs_compared_attributes and not declaration.compare:
            return Unsatisfiable(
                rule=rule,
                declared=declaration.render(),
                reason="no attribute was named to compare",
                remedy=(
                    "Name the value the two sides should agree on, for example amount. "
                    "A comparison with nothing to compare reports a clean result over "
                    "any two datasets at all."
                ),
                dataset=declaration.from_dataset_id,
            )
        if require_tolerance and declaration.tolerance is None:
            return Unsatisfiable(
                rule=rule,
                declared=declaration.render(),
                reason="no materiality tolerance was given",
                remedy=(
                    "State the materiality — for example 1.00 EUR, or 0.1%. A "
                    "comparison with no tolerance breaks on the first rounding "
                    "difference, and a control that breaks every day is switched off "
                    "within the week."
                ),
                dataset=declaration.from_dataset_id,
            )
        if not declaration.match_keys:
            return Unsatisfiable(
                rule=rule,
                declared=declaration.render(),
                reason="no match key joins the two datasets",
                remedy=(
                    "Name the attribute(s) the two sides are matched on. Without them "
                    "every row on the left matches every row on the right."
                ),
                dataset=declaration.from_dataset_id,
            )
        return None

    def _control(
        self,
        declaration: RelationshipDeclaration,
        *,
        rule: str,
        subject: str,
        control: ast.Control,
    ) -> DerivedControl:
        provenance = self._provenance(declaration, rule)
        return DerivedControl(
            identity=identity(
                declaration.name or declaration.kind.value,
                rule,
                declaration.from_dataset_id,
                subject,
            ),
            control=dataclasses.replace(control, derived_from=provenance.source_ref),
            provenance=provenance,
            rule=rule,
        )

    @staticmethod
    def _provenance(declaration: RelationshipDeclaration, rule: str) -> Provenance:
        return Provenance(
            origin=Origin.DECLARATION,
            rule=rule,
            source_ref=declaration.name
            or f"{declaration.from_dataset_id}->{declaration.to_dataset_id}",
            statement=declaration.render(),
        )

    @staticmethod
    def _edge(declaration: RelationshipDeclaration) -> Edge:
        kind = declaration.kind
        why = (
            "data moves along this edge, so a defect at the source becomes a defect at "
            "the target and the two scores are not independent"
            if kind.carries_trust
            else _NO_TRUST_BECAUSE[kind]
        )
        return Edge(
            kind=kind.value,
            source=declaration.from_dataset_id,
            target=declaration.to_dataset_id,
            carries_trust=kind.carries_trust,
            reason=(
                f"{declaration.from_dataset_id} → {declaration.to_dataset_id} "
                f"({kind.value}): {kind.prompt}. {why[0].upper()}{why[1:]}"
            ),
        )


#: Why quality does *not* propagate along the kinds that do not carry it. One
#: blanket sentence was wrong for most of them, and a wrong reason on a graph
#: edge is worse than none: it is the sentence somebody quotes back when they
#: ask why an incident did not raise an alarm downstream.
_NO_TRUST_BECAUSE: dict[RelationshipKind, str] = {
    RelationshipKind.REFERENCES: (
        "records point rather than flow. A defect in the target does not become a "
        "defect here; it becomes a dangling reference, which the integrity control "
        "already finds"
    ),
    RelationshipKind.RECONCILES_WITH: (
        "the two are independent by construction, and that independence is exactly "
        "what makes their agreement worth anything. Propagating a score between them "
        "would destroy the property the reconciliation relies on"
    ),
    RelationshipKind.SUPERSEDES: (
        "one replaces the other from a date; they are not both authoritative, so "
        "there is no ongoing channel between them"
    ),
    RelationshipKind.SAME_ENTITY_AS: (
        "two independent descriptions of the same real-world things, neither derived "
        "from the other. Their agreement is evidence; a shared score would not be"
    ),
    RelationshipKind.PARENT_OF: (
        "a hierarchy is structure rather than flow. A bad attribute on a parent does "
        "not make its children wrong, though a missing parent does make them "
        "unreachable — which the orphan control finds"
    ),
    RelationshipKind.MUTUALLY_EXCLUSIVE: (
        "a statement about which population a record belongs to, not a channel a "
        "defect travels along"
    ),
    RelationshipKind.TOGETHER_COMPLETE: (
        "a statement about coverage of a population, not a channel a defect travels along"
    ),
}


_DISPATCH: dict[
    RelationshipKind,
    Callable[[RelationshipGenerator, RelationshipDeclaration], RelationshipGeneration],
] = {
    RelationshipKind.REFERENCES: RelationshipGenerator._references,
    RelationshipKind.RECONCILES_WITH: RelationshipGenerator._reconciles,
    RelationshipKind.DERIVES_FROM: RelationshipGenerator._derives_from,
    RelationshipKind.FEEDS: RelationshipGenerator._feeds,
    RelationshipKind.MIRRORS: RelationshipGenerator._mirrors,
    RelationshipKind.AGGREGATES: RelationshipGenerator._aggregates,
    RelationshipKind.ENRICHES: RelationshipGenerator._enriches,
    RelationshipKind.SUPERSEDES: RelationshipGenerator._supersedes,
    RelationshipKind.SAME_ENTITY_AS: RelationshipGenerator._same_entity,
    RelationshipKind.TEMPORAL_SUCCESSOR: RelationshipGenerator._temporal_successor,
    RelationshipKind.PARENT_OF: RelationshipGenerator._parent_of,
    RelationshipKind.MUTUALLY_EXCLUSIVE: RelationshipGenerator._mutually_exclusive,
    RelationshipKind.TOGETHER_COMPLETE: RelationshipGenerator._together_complete,
}


def generation_for(
    declaration: RelationshipDeclaration, *, severity: ast.Severity = ast.Severity.MAJOR
) -> RelationshipGeneration:
    """Convenience entry point, so a caller need not build a generator."""
    return RelationshipGenerator(severity=severity).generate(declaration)


def as_generation(result: RelationshipGeneration) -> Generation:
    """The PQL-shaped part, for a caller that only handles controls.

    Deliberately lossy, and named so that it is obvious. A caller taking this
    view of a ``RECONCILES_WITH`` declaration gets nothing at all, which is the
    truth: there is no row predicate for it.
    """
    return Generation(controls=result.controls, unsatisfiable=result.unsatisfiable)

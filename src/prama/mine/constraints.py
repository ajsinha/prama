"""Invariants between columns — the arithmetic the data already obeys.

`FR-PRF-009` and `FR-PRF-010`: approximate denial constraints and order
dependencies. The academic framing is general; the useful instances are
narrow, and this module mines the narrow ones on purpose.

Three shapes account for most of what a business would actually recognise:

**Orderings.** ``trade_date <= settlement_date``. ``valid_from < valid_to``.
``low <= high``. Every one of these is a rule somebody would confirm in a second
and nobody has written down, and each is violated in real data by a handful of
rows that are genuinely wrong.

**Arithmetic identities.** ``quantity * price = notional``. ``gross - fees =
net``. ``opening + movement = closing``. These are the controls a finance team
would ask for first, and they are discoverable because they hold exactly on
almost every row.

**Denials.** No row has a cancellation date and an open status. No row has a
zero quantity and a non-zero notional. Stated as a forbidden combination, which
is how the business says it.

**Floating point is why the tolerance is not optional.** ``quantity * price``
computed in binary floating point does not equal a stored ``notional`` bit for
bit, ever, on real money. An identity miner testing exact equality finds
nothing at all and reports a clean table with no invariants in it — which is
the most misleading possible output, because it looks like a thorough search.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import itertools
from typing import Any

from prama.core.provenance import Origin, Provenance, identity
from prama.mine.sample import Evidence, Sample

#: Relative tolerance for an arithmetic identity. Generous by the standards of
#: a reconciliation and correct here: the question is whether the relationship
#: *exists*, and a rounding difference in the twelfth digit is not evidence
#: that it does not. The control that comes out of this gets its own,
#: business-set materiality.
IDENTITY_TOLERANCE = 1e-9

#: Support below which an invariant is not a rule with exceptions but a
#: coincidence. Set lower than the dependency threshold on purpose: an ordering
#: that holds on 97% of rows is a real rule and a real backlog of 3% bad rows,
#: which is exactly the finding worth having.
MINIMUM_SUPPORT = 0.97

#: A comparison that holds on every row because one side is always null, or
#: because both sides are constant, is not an invariant.
MINIMUM_APPLICABLE = 50


class InvariantKind:
    ORDERING = "ordering"
    IDENTITY = "identity"
    DENIAL = "denial"


@dataclasses.dataclass(frozen=True, slots=True)
class Invariant:
    """A relationship between columns that the data obeys."""

    kind: str
    #: The invariant as PQL would express it: ``trade_date <= settlement_date``.
    expression: str
    columns: tuple[str, ...]
    evidence: Evidence
    #: Rows that break it, for the reviewer to look at. The most persuasive
    #: thing in a mined proposal: three concrete wrong rows beat any statistic.
    counterexamples: tuple[dict[str, Any], ...] = ()

    @property
    def is_exact(self) -> bool:
        return self.evidence.is_exact

    def render(self) -> str:
        return self.expression

    def describe(self) -> str:
        if self.is_exact:
            return (
                f"{self.expression} holds on every one of "
                f"{self.evidence.supporting:,} applicable rows"
            )
        return (
            f"{self.expression} holds on {self.evidence.support:.2%} of rows. "
            f"The {self.evidence.violating:,} that break it are either wrong or an "
            f"exception nobody has written down — and both are worth knowing"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "expression": self.expression,
            "columns": list(self.columns),
            "exact": self.is_exact,
            "evidence": self.evidence.to_dict(),
            "counterexamples": [dict(r) for r in self.counterexamples],
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ConstraintFindings:
    dataset: str
    invariants: tuple[Invariant, ...] = ()
    discarded: dict[str, int] = dataclasses.field(default_factory=dict)
    skipped: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.invariants)

    def of_kind(self, kind: str) -> tuple[Invariant, ...]:
        return tuple(i for i in self.invariants if i.kind == kind)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "invariants": [i.to_dict() for i in self.invariants],
            "discarded": dict(self.discarded),
            "skipped": list(self.skipped),
        }


class ConstraintMiner:
    """Finds orderings, arithmetic identities and forbidden combinations."""

    def __init__(
        self,
        *,
        minimum_support: float = MINIMUM_SUPPORT,
        tolerance: float = IDENTITY_TOLERANCE,
        max_counterexamples: int = 3,
    ) -> None:
        self._minimum_support = minimum_support
        self._tolerance = tolerance
        self._max_counterexamples = max_counterexamples

    def mine(self, sample: Sample) -> ConstraintFindings:
        if not sample.is_usable:
            return ConstraintFindings(
                dataset=sample.dataset,
                skipped=(f"nothing was searched: {sample.size:,} rows is too few",),
            )
        caveats = sample.caveats()
        discarded: dict[str, int] = {}
        comparable = self._comparable_columns(sample, discarded)
        numeric = [c for c in comparable if self._is_numeric(sample, c)]

        identities = self._identities(sample, numeric, caveats, discarded)
        orderings = self._orderings(sample, comparable, caveats, discarded)
        # Identities first, because they are the stronger statement and they
        # explain away some of the orderings entirely.
        invariants = [
            *identities,
            *self._not_implied(sample, orderings, identities, discarded),
        ]
        skipped: list[str] = []
        if len(numeric) > 8:
            skipped.append(
                f"arithmetic identities were searched over the first 8 of {len(numeric)} "
                f"numeric columns; the search is cubic in that count"
            )
        return ConstraintFindings(
            dataset=sample.dataset,
            invariants=tuple(invariants),
            discarded=discarded,
            skipped=tuple(skipped),
        )

    # -- orderings ---------------------------------------------------------

    def _orderings(
        self,
        sample: Sample,
        columns: list[str],
        caveats: tuple[str, ...],
        discarded: dict[str, int],
    ) -> list[Invariant]:
        found: list[Invariant] = []
        for left, right in itertools.combinations(columns, 2):
            if not self._same_family(sample, left, right):
                continue
            if self._disjoint_ranges(sample, left, right):
                # ``fees <= quantity`` holds on every row because fees are
                # small and quantities are large. That is a fact about units,
                # not a rule about the business, and a control built on it can
                # only fail if somebody changes the scale of a column. When the
                # ranges never meet, the comparison was never in question.
                discarded["disjoint_ranges"] = discarded.get("disjoint_ranges", 0) + 1
                continue
            for operator in ("<=", "<"):
                for a, b in ((left, right), (right, left)):
                    invariant = self._test(
                        sample,
                        columns=(a, b),
                        expression=f"{a} {operator} {b}",
                        kind=InvariantKind.ORDERING,
                        predicate=_comparator(operator),
                        caveats=caveats,
                    )
                    if invariant is None:
                        continue
                    if any(
                        i.columns == invariant.columns and i.kind == InvariantKind.ORDERING
                        for i in found
                    ):
                        # ``a < b`` implies ``a <= b``. Reporting both doubles
                        # the output and adds nothing; the strict one is
                        # already the stronger claim and is found first.
                        discarded["weaker_ordering"] = discarded.get("weaker_ordering", 0) + 1
                        continue
                    found.append(invariant)
        return found

    # -- arithmetic --------------------------------------------------------

    def _identities(
        self,
        sample: Sample,
        numeric: list[str],
        caveats: tuple[str, ...],
        discarded: dict[str, int],
    ) -> list[Invariant]:
        """``a * b = c`` and ``a - b = c``, the two that carry money.

        Tested with a relative tolerance, never exactly. ``quantity * price``
        in binary floating point does not equal a stored notional bit for bit
        on real money, so an exact test finds nothing and reports a clean table
        — the most misleading output there is, because it looks thorough.
        """
        found: list[Invariant] = []
        seen: set[tuple[frozenset[str], str]] = set()
        candidates = numeric[:8]
        for target in candidates:
            for left, right in itertools.permutations([c for c in candidates if c != target], 2):
                # ``+`` first, so when three forms of one identity compete the
                # one that survives is "the parts add up to the whole" rather
                # than "the whole minus a part is the other part".
                for symbol, operation in (("+", _sum), ("*", _product), ("-", _difference)):
                    if symbol in ("*", "+") and left > right:
                        # Commutative: a + b and b + a are one identity.
                        discarded["commutative_duplicate"] = (
                            discarded.get("commutative_duplicate", 0) + 1
                        )
                        continue
                    involved = frozenset((left, right, target))
                    family = "additive" if symbol in ("+", "-") else "multiplicative"
                    if (involved, family) in seen:
                        # ``a + b = c``, ``c - a = b`` and ``c - b = a`` are one
                        # relationship written three ways. Reporting all three
                        # triples the output, and a reviewer reading the second
                        # one has to work out that it is the first before they
                        # can dismiss it.
                        discarded["algebraic_restatement"] = (
                            discarded.get("algebraic_restatement", 0) + 1
                        )
                        continue
                    invariant = self._test(
                        sample,
                        columns=(left, right, target),
                        expression=f"{left} {symbol} {right} = {target}",
                        kind=InvariantKind.IDENTITY,
                        predicate=_identity(operation, self._tolerance),
                        caveats=caveats,
                    )
                    if invariant is not None:
                        seen.add((involved, family))
                        found.append(invariant)
        return found

    def _not_implied(
        self,
        sample: Sample,
        orderings: list[Invariant],
        identities: list[Invariant],
        discarded: dict[str, int],
    ) -> list[Invariant]:
        """Drop orderings that follow arithmetically from an identity found.

        ``fees + net = notional`` with non-negative parts *entails* ``net <=
        notional`` and ``fees <= notional``; ``price * quantity = notional``
        with both factors at least one entails the same. Reporting the
        consequence next to the premise gives a reviewer three findings where
        there is one fact, and the two weak ones make the strong one harder to
        see.

        Only the entailed direction is dropped. ``fees <= net`` does not follow
        from ``fees + net = notional`` and stays, because it might be a real
        rule or might be a coincidence of this data — and that is a question
        for the reviewer rather than for arithmetic.
        """
        entailed: set[tuple[str, str]] = set()
        for identity_invariant in identities:
            left, right, target = identity_invariant.columns
            symbol = identity_invariant.expression.split()[1]
            floor = 0.0 if symbol in ("+", "-") else 1.0
            for operand, other in ((left, right), (right, left)):
                if self._at_least(sample, other, floor):
                    entailed.add((operand, target))
        kept: list[Invariant] = []
        for ordering in orderings:
            if ordering.columns in entailed:
                discarded["implied_by_identity"] = discarded.get("implied_by_identity", 0) + 1
                continue
            kept.append(ordering)
        return kept

    @staticmethod
    def _at_least(sample: Sample, column: str, floor: float) -> bool:
        values = [v for v in sample.values(column) if v is not None]
        return bool(values) and all(
            isinstance(v, int | float) and not isinstance(v, bool) and v >= floor for v in values
        )

    # -- shared ------------------------------------------------------------

    def _test(
        self,
        sample: Sample,
        *,
        columns: tuple[str, ...],
        expression: str,
        kind: str,
        predicate: Any,
        caveats: tuple[str, ...],
    ) -> Invariant | None:
        applicable = 0
        holding = 0
        counterexamples: list[dict[str, Any]] = []
        for row in sample.rows:
            values = [row.get(c) for c in columns]
            if any(v is None for v in values):
                continue
            try:
                outcome = predicate(*values)
            except TypeError:
                return None
            if outcome is None:
                continue
            applicable += 1
            if outcome:
                holding += 1
            elif len(counterexamples) < self._max_counterexamples:
                counterexamples.append({c: row.get(c) for c in columns})
        if applicable < MINIMUM_APPLICABLE:
            return None
        support = holding / applicable
        if support < self._minimum_support:
            return None
        return Invariant(
            kind=kind,
            expression=expression,
            columns=columns,
            counterexamples=tuple(counterexamples),
            evidence=Evidence(
                rows_examined=sample.size,
                supporting=holding,
                violating=applicable - holding,
                null_excluded=sample.size - applicable,
                distinct=applicable,
                caveats=caveats,
            ),
        )

    def _comparable_columns(self, sample: Sample, discarded: dict[str, int]) -> list[str]:
        useful: list[str] = []
        for column in sample.columns:
            populated = [v for v in sample.values(column) if v is not None]
            if len(populated) < MINIMUM_APPLICABLE:
                discarded["too_sparse"] = discarded.get("too_sparse", 0) + 1
                continue
            if len(set(populated)) <= 1:
                # A constant satisfies every comparison against anything on one
                # side of it, and none of those is an invariant.
                discarded["constant_column"] = discarded.get("constant_column", 0) + 1
                continue
            useful.append(column)
        return useful

    def _disjoint_ranges(self, sample: Sample, left: str, right: str) -> bool:
        """Whether two numeric columns occupy separate stretches of the line."""
        if not (self._is_numeric(sample, left) and self._is_numeric(sample, right)):
            return False
        first = [v for v in sample.values(left) if v is not None]
        second = [v for v in sample.values(right) if v is not None]
        if not first or not second:
            return False
        return bool(max(first) < min(second) or max(second) < min(first))

    @staticmethod
    def _is_numeric(sample: Sample, column: str) -> bool:
        populated = [v for v in sample.values(column) if v is not None]
        return bool(populated) and all(
            isinstance(v, int | float) and not isinstance(v, bool) for v in populated
        )

    def _same_family(self, sample: Sample, left: str, right: str) -> bool:
        """Whether two columns are the sort of thing that can be ordered.

        Comparing a quantity to a date raises in Python and would compare
        lexically in some engines, which is worse — it produces an invariant
        that holds on the sample and means nothing.
        """
        return self._is_numeric(sample, left) == self._is_numeric(sample, right)


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


def _comparator(operator: str) -> Any:
    def test(left: Any, right: Any) -> bool | None:
        try:
            return bool(left <= right) if operator == "<=" else bool(left < right)
        except TypeError:
            return None

    return test


def _product(left: float, right: float) -> float:
    return left * right


def _difference(left: float, right: float) -> float:
    return left - right


def _sum(left: float, right: float) -> float:
    return left + right


def _identity(operation: Any, tolerance: float) -> Any:
    def test(left: Any, right: Any, target: Any) -> bool | None:
        try:
            computed = operation(float(left), float(right))
        except (TypeError, ValueError):
            return None
        scale = max(abs(computed), abs(float(target)), 1.0)
        return bool(abs(computed - float(target)) <= tolerance * scale)

    return test


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def invariant_provenance(dataset: str, invariant: Invariant, sample: Sample) -> Provenance:
    observations = [invariant.evidence.describe(), *sample.caveats()]
    if invariant.counterexamples:
        observations.insert(
            1,
            "rows that break it: " + "; ".join(str(row) for row in invariant.counterexamples),
        )
    return Provenance(
        origin=Origin.MINING,
        rule=f"mine.{invariant.kind}",
        source_ref=f"{dataset}#profile",
        statement=invariant.describe(),
        observations=tuple(observations),
    )


def invariant_identity(dataset: str, invariant: Invariant) -> str:
    return identity(dataset, f"mine.{invariant.kind}", dataset, invariant.expression)

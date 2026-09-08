"""Functional and inclusion dependencies — the rules the data already follows.

`FR-PRF-007` and `FR-PRF-008`. A functional dependency says one value implies
another: each ISIN has one issuer, each cost centre one legal entity, each
product code one asset class. An inclusion dependency says one column's values
all appear in another's: a foreign key nobody declared.

**Almost everything a naive FD miner finds is true and worthless**, and the
filters below are the module. Three sources of noise dominate, and each one
produces hundreds of findings on an ordinary table:

*A key determines everything.* If ``trade_id`` is unique then ``trade_id →``
every other column, exactly, always, by construction. A miner without this
filter reports one dependency per column and none of them is a rule — they are
a restatement of the key, and a control built on any of them can only fail if
the key does.

*A constant is determined by everything.* If ``record_type`` is ``'P'`` on
every row then every column determines it. Same arithmetic, same worthlessness.

*A near-key determines nearly everything.* This is the subtle one. If
``account_id`` has 4,190,000 distinct values across 4,200,000 rows, it is not a
key, so the first filter misses it — and it still determines every column to
within 0.2%, so an approximate-FD miner reports all of them at 99.8% support.
The support looks like strong evidence and is an artefact of the cardinality.

**A partial inclusion dependency is usually the interesting one.** A column
whose values are entirely contained in another's is a working foreign key. A
column that is 97% contained is a foreign key *with three percent orphans*, and
that is a live defect somebody wants to know about today.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Sequence
from typing import Any

from prama.core.provenance import Origin, Provenance, identity
from prama.mine.sample import Evidence, Sample

#: Determinants wider than this are not searched. Two columns covers the
#: dependencies people recognise; three-column determinants are mostly
#: two-column ones with a passenger.
DEFAULT_MAX_DETERMINANT = 2

#: A determinant whose distinct-value count exceeds this fraction of the rows
#: is too close to a key for a dependency on it to mean anything. See the
#: near-key problem above — this is the filter that stops the noise.
NEAR_KEY_FRACTION = 0.9

#: An approximate dependency below this support is not a dependency with
#: exceptions; it is a pattern that does not hold.
MINIMUM_SUPPORT = 0.95

#: A conditional dependency must apply to at least this fraction of rows.
#: Below it, "the rule holds for the eleven rows where country = 'AD'" is a
#: description of eleven rows.
MINIMUM_CONDITION_COVERAGE = 0.05


@dataclasses.dataclass(frozen=True, slots=True)
class Dependency:
    """``determinant → dependent``, with what supports it."""

    determinant: tuple[str, ...]
    dependent: str
    evidence: Evidence
    #: The value of a condition column this holds *within*, if it is
    #: conditional. ``("country", "US")`` reads "within US rows".
    condition: tuple[str, Any] | None = None

    @property
    def is_exact(self) -> bool:
        return self.evidence.is_exact

    @property
    def is_conditional(self) -> bool:
        return self.condition is not None

    @property
    def is_completeness(self) -> bool:
        """Whether this says a column is *present*, not what determines it.

        A conditional completeness rule has the condition column as its own
        determinant — "within US rows, state is always populated" — and reads
        as nonsense if rendered as a determinant rule.
        """
        return (
            self.condition is not None
            and len(self.determinant) == 1
            and self.determinant[0] == self.condition[0]
        )

    def render(self) -> str:
        if self.is_completeness:
            assert self.condition is not None
            column, value = self.condition
            return f"{self.dependent} IS NOT NULL WHERE {column} = {value!r}"
        left = ", ".join(self.determinant)
        head = f"{left} -> {self.dependent}"
        if self.condition is not None:
            column, value = self.condition
            return f"{head} WHERE {column} = {value!r}"
        return head

    def describe(self) -> str:
        if self.is_completeness:
            assert self.condition is not None
            column, value = self.condition
            return (
                f"{self.dependent} is always populated where {column} is {value!r}, "
                f"and not always populated otherwise — so it is mandatory under that "
                f"condition rather than everywhere"
            )
        left = " and ".join(self.determinant)
        where = ""
        if self.condition is not None:
            column, value = self.condition
            where = f", among rows where {column} is {value!r}"
        if self.is_exact:
            return f"each {left} always has the same {self.dependent}{where}"
        return (
            f"each {left} nearly always has the same {self.dependent}{where} — "
            f"{self.evidence.support:.2%} of rows agree, and "
            f"{self.evidence.violating:,} do not"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "determinant": list(self.determinant),
            "dependent": self.dependent,
            "condition": list(self.condition) if self.condition else None,
            "exact": self.is_exact,
            "evidence": self.evidence.to_dict(),
            "rendered": self.render(),
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Inclusion:
    """``left.column`` values all appear in ``right.column`` — a foreign key."""

    left_dataset: str
    left_column: str
    right_dataset: str
    right_column: str
    evidence: Evidence
    #: Values present on the left and absent on the right. The finding, when
    #: this is partial.
    orphan_examples: tuple[Any, ...] = ()

    @property
    def is_exact(self) -> bool:
        return self.evidence.is_exact

    def render(self) -> str:
        return (
            f"{self.left_dataset}.{self.left_column} REFERENCES "
            f"{self.right_dataset}.{self.right_column}"
        )

    def describe(self) -> str:
        if self.is_exact:
            return (
                f"every {self.left_column} in {self.left_dataset} exists in "
                f"{self.right_dataset}.{self.right_column} — a foreign key nobody "
                f"declared"
            )
        examples = ", ".join(repr(v) for v in self.orphan_examples[:3])
        return (
            f"{self.evidence.support:.2%} of {self.left_column} values in "
            f"{self.left_dataset} exist in {self.right_dataset}.{self.right_column}. "
            f"The remaining {self.evidence.violating:,} are orphans"
            + (f" — for example {examples}" if examples else "")
            + ". This is a foreign key with a live defect in it, not a coincidence"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": f"{self.left_dataset}.{self.left_column}",
            "right": f"{self.right_dataset}.{self.right_column}",
            "exact": self.is_exact,
            "orphan_examples": [str(v) for v in self.orphan_examples[:5]],
            "evidence": self.evidence.to_dict(),
            "rendered": self.render(),
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class DependencyFindings:
    dataset: str
    dependencies: tuple[Dependency, ...] = ()
    inclusions: tuple[Inclusion, ...] = ()
    #: What was searched and rejected, in aggregate. The number matters: "412
    #: dependencies were found and 408 were true by construction" is the
    #: sentence that tells somebody the filters are earning their keep.
    discarded: dict[str, int] = dataclasses.field(default_factory=dict)
    skipped: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.dependencies) + len(self.inclusions)

    @property
    def exact(self) -> tuple[Dependency, ...]:
        return tuple(d for d in self.dependencies if d.is_exact)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "inclusions": [i.to_dict() for i in self.inclusions],
            "discarded": dict(self.discarded),
            "skipped": list(self.skipped),
        }


class DependencyMiner:
    """Finds functional dependencies worth a person's attention."""

    def __init__(
        self,
        *,
        max_determinant: int = DEFAULT_MAX_DETERMINANT,
        minimum_support: float = MINIMUM_SUPPORT,
        near_key_fraction: float = NEAR_KEY_FRACTION,
    ) -> None:
        self._max_determinant = max_determinant
        self._minimum_support = minimum_support
        self._near_key_fraction = near_key_fraction

    def mine(self, sample: Sample, *, conditions: Sequence[str] = ()) -> DependencyFindings:
        if not sample.is_usable:
            return DependencyFindings(
                dataset=sample.dataset,
                skipped=(
                    f"nothing was searched: {sample.size:,} rows is too few for a "
                    f"dependency to mean anything",
                ),
            )
        caveats = sample.caveats()
        useful, discarded = self._useful_columns(sample)
        found: list[Dependency] = []

        for arity in range(1, self._max_determinant + 1):
            for determinant in itertools.combinations(useful, arity):
                if self._is_near_key(sample, determinant):
                    discarded["near_key_determinant"] = discarded.get("near_key_determinant", 0) + 1
                    continue
                for dependent in useful:
                    if dependent in determinant:
                        continue
                    if any(
                        set(d.determinant) < set(determinant) and d.dependent == dependent
                        for d in found
                    ):
                        # A dependency implied by a narrower one already found.
                        # If a → c holds then (a, b) → c holds for free, and
                        # reporting both buries the one that says something.
                        discarded["implied"] = discarded.get("implied", 0) + 1
                        continue
                    dependency = self._evaluate(sample, determinant, dependent, caveats)
                    if dependency is not None:
                        found.append(dependency)

        for condition in conditions:
            found.extend(self._conditional(sample, useful, condition, caveats, discarded, found))
            found.extend(
                self._conditional_completeness(sample, useful, condition, caveats, discarded)
            )

        skipped: list[str] = []
        if len(useful) > self._max_determinant:
            skipped.append(
                f"determinants of more than {self._max_determinant} columns were not "
                f"searched; a wider one is usually a narrower one with a passenger"
            )
        return DependencyFindings(
            dataset=sample.dataset,
            dependencies=tuple(found),
            discarded=discarded,
            skipped=tuple(skipped),
        )

    # -- the filters that are the module ----------------------------------

    def _useful_columns(self, sample: Sample) -> tuple[list[str], dict[str, int]]:
        """Columns that can take part in a dependency worth reporting."""
        useful: list[str] = []
        discarded: dict[str, int] = {}
        for column in sample.columns:
            values = sample.values(column)
            populated = [v for v in values if v is not None]
            distinct = len(set(populated))
            if distinct <= 1:
                # Determined by everything, and by nothing meaningful. A
                # constant column produces one dependency per other column and
                # not one of them is a rule.
                discarded["constant_column"] = discarded.get("constant_column", 0) + 1
                continue
            useful.append(column)
        return useful, discarded

    def _is_near_key(self, sample: Sample, columns: tuple[str, ...]) -> bool:
        """Whether a determinant is so close to unique that it proves nothing.

        The filter that stops the flood. A determinant with 4.19m distinct
        values in 4.2m rows determines every column to within 0.2% — support
        that reads as overwhelming evidence and is entirely an artefact of the
        cardinality. It would be true of a column of random numbers.
        """
        tuples = [t for t in sample.tuples(columns) if not any(v is None for v in t)]
        if not tuples:
            return True
        return len(set(tuples)) / len(tuples) >= self._near_key_fraction

    def _evaluate(
        self,
        sample: Sample,
        determinant: tuple[str, ...],
        dependent: str,
        caveats: tuple[str, ...],
        rows: list[dict[str, Any]] | None = None,
        condition: tuple[str, Any] | None = None,
    ) -> Dependency | None:
        source = sample.rows if rows is None else rows
        groups: dict[tuple[Any, ...], dict[Any, int]] = {}
        excluded = 0
        for row in source:
            key = tuple(row.get(c) for c in determinant)
            value = row.get(dependent)
            if any(v is None for v in key) or value is None:
                # A dependency cannot be tested on a row where either side is
                # missing, and counting such rows as agreeing is how a column
                # that is mostly null gets reported as perfectly determined.
                excluded += 1
                continue
            counts = groups.setdefault(key, {})
            counts[value] = counts.get(value, 0) + 1

        applicable = len(source) - excluded
        if not applicable:
            return None
        # g3: the fewest rows that would have to be removed for the dependency
        # to hold exactly.
        agreeing = sum(max(counts.values()) for counts in groups.values())
        violating = applicable - agreeing
        support = agreeing / applicable
        if support < self._minimum_support:
            return None
        return Dependency(
            determinant=determinant,
            dependent=dependent,
            condition=condition,
            evidence=Evidence(
                rows_examined=len(source),
                supporting=agreeing,
                violating=violating,
                null_excluded=excluded,
                distinct=len(groups),
                caveats=caveats,
            ),
        )

    def _conditional(
        self,
        sample: Sample,
        useful: list[str],
        condition_column: str,
        caveats: tuple[str, ...],
        discarded: dict[str, int],
        already: list[Dependency],
    ) -> list[Dependency]:
        """Dependencies that hold within a subset **and not overall**.

        The second half of that sentence is the whole filter. Without it, every
        global dependency is re-reported once per value of the condition
        column: ``instrument -> issuer`` holds, so it also holds within US rows,
        within GB rows and within DE rows, and a table with a twelve-valued
        status column produces twelve copies of every real finding. The
        conditional ones worth a reviewer's time are exactly the ones that are
        *false globally* — that is what makes them a discovery rather than a
        restatement.
        """
        global_ones = {(d.determinant, d.dependent) for d in already if d.condition is None}
        found: list[Dependency] = []
        by_value: dict[Any, list[dict[str, Any]]] = {}
        for row in sample.rows:
            by_value.setdefault(row.get(condition_column), []).append(row)

        for value, rows in by_value.items():
            if value is None:
                continue
            coverage = len(rows) / sample.size
            if coverage < MINIMUM_CONDITION_COVERAGE or len(rows) < 50:
                # "The rule holds for the eleven rows where country = 'AD'" is
                # a description of eleven rows.
                discarded["condition_too_narrow"] = discarded.get("condition_too_narrow", 0) + 1
                continue
            for determinant in itertools.combinations(
                [c for c in useful if c != condition_column], 1
            ):
                for dependent in useful:
                    if dependent in determinant or dependent == condition_column:
                        continue
                    scoped = Sample.of(sample.dataset, rows)
                    if self._is_near_key(scoped, determinant):
                        continue
                    dependency = self._evaluate(
                        sample,
                        determinant,
                        dependent,
                        caveats,
                        rows=rows,
                        condition=(condition_column, value),
                    )
                    if dependency is None or not dependency.is_exact:
                        continue
                    if (determinant, dependent) in global_ones:
                        discarded["conditional_restates_global"] = (
                            discarded.get("conditional_restates_global", 0) + 1
                        )
                        continue
                    found.append(dependency)
        return found

    def _conditional_completeness(
        self,
        sample: Sample,
        useful: list[str],
        condition_column: str,
        caveats: tuple[str, ...],
        discarded: dict[str, int],
    ) -> list[Dependency]:
        """Columns that are mandatory only under a condition.

        The shape most business rules actually have, and one a determinant →
        dependent search cannot express at all. "Every US address has a state"
        is false globally, true within the US, and is not a functional
        dependency — it is a completeness rule with a filter.

        It is worth mining because it lands somewhere specific: it proposes a
        *conditional optionality* declaration, and Γ turns that into a control
        with a WHERE clause. The alternative a global miner offers is
        ``state IS NOT NULL``, which fails on every non-US row and gets
        switched off.
        """
        found: list[Dependency] = []
        by_value: dict[Any, list[dict[str, Any]]] = {}
        for row in sample.rows:
            by_value.setdefault(row.get(condition_column), []).append(row)

        for column in useful:
            if column == condition_column:
                continue
            overall = [r.get(column) for r in sample.rows]
            missing_overall = sum(1 for v in overall if v is None)
            if missing_overall == 0:
                # Mandatory everywhere. That is a plain completeness rule, and
                # dressing it as a conditional one narrows a true rule for no
                # reason.
                continue
            for value, rows in by_value.items():
                if value is None or len(rows) < 50:
                    continue
                if len(rows) / sample.size < MINIMUM_CONDITION_COVERAGE:
                    discarded["condition_too_narrow"] = discarded.get("condition_too_narrow", 0) + 1
                    continue
                present = sum(1 for r in rows if r.get(column) is not None)
                if present != len(rows):
                    continue
                found.append(
                    Dependency(
                        determinant=(condition_column,),
                        dependent=column,
                        condition=(condition_column, value),
                        evidence=Evidence(
                            rows_examined=len(rows),
                            supporting=present,
                            violating=0,
                            distinct=1,
                            caveats=caveats,
                        ),
                    )
                )
        return found


class InclusionMiner:
    """Finds candidate foreign keys between two samples."""

    def __init__(self, *, minimum_containment: float = 0.9) -> None:
        #: Below this, containment is coincidence — two columns of country
        #: codes overlap heavily without one referencing the other.
        self._minimum = minimum_containment

    @staticmethod
    def _is_key(sample: Sample, column: str) -> bool:
        """Whether a column could be the target of a reference.

        Near-unique rather than unique: a dimension table with three duplicate
        rows in it is still the thing being referenced, and refusing to notice
        the foreign key because of them would hide two findings instead of one.
        """
        values = [v for v in sample.values(column) if v is not None]
        if not values:
            return False
        return len(set(values)) / len(values) >= 0.99

    def mine(self, left: Sample, right: Sample) -> DependencyFindings:
        inclusions: list[Inclusion] = []
        discarded: dict[str, int] = {}
        caveats = (*left.caveats(), *right.caveats())

        right_values = {
            column: {v for v in right.values(column) if v is not None} for column in right.columns
        }
        for left_column in left.columns:
            values = [v for v in left.values(left_column) if v is not None]
            if not values:
                continue
            distinct_left = set(values)
            if len(distinct_left) <= 1:
                discarded["constant_column"] = discarded.get("constant_column", 0) + 1
                continue
            for right_column, target in right_values.items():
                if not target:
                    continue
                contained = sum(1 for v in values if v in target)
                support = contained / len(values)
                if support < self._minimum:
                    continue
                if not self._is_key(right, right_column):
                    # A foreign key points at a *key*. A right column with two
                    # hundred rows and three distinct values is a status code,
                    # and every column in the world is "contained" in it.
                    #
                    # An earlier version compared distinct counts instead —
                    # rejecting when the right had fewer distinct values than
                    # the left — and that destroyed the finding this miner
                    # exists for: a foreign key *with orphans* has more
                    # distinct values on the left, because the orphans are
                    # exactly the extra ones.
                    discarded["target_is_not_a_key"] = discarded.get("target_is_not_a_key", 0) + 1
                    continue
                orphans = sorted({v for v in distinct_left if v not in target}, key=repr)[:5]
                inclusions.append(
                    Inclusion(
                        left_dataset=left.dataset,
                        left_column=left_column,
                        right_dataset=right.dataset,
                        right_column=right_column,
                        orphan_examples=tuple(orphans),
                        evidence=Evidence(
                            rows_examined=len(left.rows),
                            supporting=contained,
                            violating=len(values) - contained,
                            null_excluded=len(left.rows) - len(values),
                            distinct=len(distinct_left),
                            caveats=caveats,
                        ),
                    )
                )
        return DependencyFindings(
            dataset=left.dataset, inclusions=tuple(inclusions), discarded=discarded
        )


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def dependency_provenance(dataset: str, dependency: Dependency, sample: Sample) -> Provenance:
    return Provenance(
        origin=Origin.MINING,
        rule="mine.functional_dependency",
        source_ref=f"{dataset}#profile",
        statement=dependency.describe(),
        observations=(dependency.evidence.describe(), *sample.caveats()),
    )


def inclusion_provenance(inclusion: Inclusion, sample: Sample) -> Provenance:
    return Provenance(
        origin=Origin.MINING,
        rule="mine.inclusion_dependency",
        source_ref=f"{inclusion.left_dataset}#profile",
        statement=inclusion.describe(),
        observations=(inclusion.evidence.describe(), *sample.caveats()),
    )


def dependency_identity(dataset: str, dependency: Dependency) -> str:
    return identity(
        dataset,
        "mine.functional_dependency",
        dataset,
        f"{','.join(dependency.determinant)}->{dependency.dependent}"
        + (f"|{dependency.condition[0]}={dependency.condition[1]}" if dependency.condition else ""),
    )


def inclusion_identity(inclusion: Inclusion) -> str:
    return identity(
        inclusion.left_dataset,
        "mine.inclusion_dependency",
        inclusion.left_dataset,
        f"{inclusion.left_column}->{inclusion.right_dataset}.{inclusion.right_column}",
    )

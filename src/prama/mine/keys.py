"""Unique column combinations — the keys nobody wrote down.

`FR-PRF-006`. Most tables have a key, most keys are not declared anywhere, and
finding them is the highest-value thing mining does: a grain follows from a
key, and a grain generates four controls (docs/corpus/03 §5).

**A mined key is an observation, and the distance between that and a rule is
where this goes wrong.** ``(account_id)`` is unique in Monday's extract and
repeats on Tuesday. ``(trade_id, version)`` is unique because nothing has been
amended yet. A miner cannot distinguish "this is the key" from "nothing has
happened yet that would break it", and pretending otherwise turns the first
legitimate duplicate into an incident. So every candidate carries its evidence
and its caveats, and none of them activates without somebody agreeing.

**Three filters, each of which is the difference between a useful proposal and
noise.** Supersets of a key are dropped, because if ``account_id`` is unique
then so is every pair containing it and proposing all of them buries the one
that matters. Near-unique columns are dropped as *determinants* elsewhere but
kept here with a warning, because a column that is 99.99% unique is usually a
key with a data problem rather than a non-key. And a "unique" column that is
mostly null is refused outright: SQL's ``COUNT(DISTINCT)`` skips nulls, so an
empty column with four values in it counts as unique, and that has fooled every
profiler that did not check.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import itertools
import re
from typing import Any

from prama.core.provenance import Origin, Provenance, identity
from prama.mine.sample import Evidence, Sample

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_ULID = re.compile(r"^[0-7][0-9ABCDEFGHJKMNPQRSTVWXYZ]{25}$")

#: Combinations wider than this are not searched. The search is exponential in
#: arity and a five-column key is vanishingly rare; more to the point, a
#: five-column "key" is nearly always four columns of noise plus the real one.
DEFAULT_MAX_ARITY = 3

#: A column with more nulls than this cannot be part of a proposed key,
#: however unique its populated values are.
MAXIMUM_NULL_FRACTION = 0.05

#: Uniqueness at or above this, but below 1.0, is reported as an
#: *approximate* key — almost certainly a real key with a handful of duplicate
#: rows, which is a finding rather than a reason to say nothing.
APPROXIMATE_THRESHOLD = 0.999


@dataclasses.dataclass(frozen=True, slots=True)
class Candidate:
    """A column combination that is unique, or nearly, in the sample."""

    columns: tuple[str, ...]
    evidence: Evidence
    #: True when a handful of rows violate it. Kept rather than discarded: a
    #: column that is unique on 4,199,997 of 4,200,000 rows is a key with three
    #: bad rows in it, and both halves of that sentence are worth reporting.
    approximate: bool = False
    #: A generated identifier — a row number, a sequence, a UUID — rather than
    #: anything the business would recognise. It is a real key and a real
    #: uniqueness control can be written on it. It is also useless as a
    #: *grain*: "one row per row_id" answers "what does one row represent?"
    #: with "a row", and offering it as the answer is worse than offering
    #: nothing, because it looks like one.
    surrogate: bool = False

    @property
    def arity(self) -> int:
        return len(self.columns)

    @property
    def is_exact(self) -> bool:
        return self.evidence.is_exact

    def render(self) -> str:
        return f"({', '.join(self.columns)})"

    def describe(self) -> str:
        head = (
            f"{self.render()} is unique"
            if self.is_exact
            else (
                f"{self.render()} is unique except for {self.evidence.violating:,} rows "
                f"— which is what a key with a duplicate problem looks like, not what a "
                f"non-key looks like"
            )
        )
        return f"{head}. {self.evidence.describe()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": list(self.columns),
            "arity": self.arity,
            "approximate": self.approximate,
            "evidence": self.evidence.to_dict(),
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class KeyFindings:
    """Everything the key miner concluded, including what it did not look at."""

    dataset: str
    candidates: tuple[Candidate, ...] = ()
    #: Combinations not searched, and why. Never silent: a report that says
    #: "found two keys" while having skipped every three-column combination
    #: reads as completeness and is not.
    skipped: tuple[str, ...] = ()
    #: Columns excluded before the search, with the reason.
    excluded: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.candidates)

    @property
    def best(self) -> Candidate | None:
        """The narrowest exact key that describes the business, not the storage.

        Surrogates are deliberately ranked last rather than excluded. A row
        number is genuinely unique and a uniqueness control on it is genuinely
        valid — but it answers "what does one row represent?" with "a row", and
        a table whose only mined key is a surrogate is a table whose grain has
        not been found. Saying that is more useful than offering the surrogate
        as though it were the answer.
        """
        exact = [c for c in self.candidates if c.is_exact]
        if not exact:
            return None
        return min(exact, key=lambda c: (c.surrogate, c.arity, c.columns))

    @property
    def business_key_found(self) -> bool:
        """Whether anything here could be declared as a grain."""
        best = self.best
        return best is not None and not best.surrogate

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "candidates": [c.to_dict() for c in self.candidates],
            "skipped": list(self.skipped),
            "excluded": list(self.excluded),
        }


class KeyMiner:
    """Finds minimal unique column combinations in a sample."""

    def __init__(
        self,
        *,
        max_arity: int = DEFAULT_MAX_ARITY,
        maximum_null_fraction: float = MAXIMUM_NULL_FRACTION,
    ) -> None:
        self._max_arity = max_arity
        self._maximum_null_fraction = maximum_null_fraction

    def mine(self, sample: Sample) -> KeyFindings:
        if not sample.is_usable:
            return KeyFindings(
                dataset=sample.dataset,
                skipped=(
                    f"nothing was searched: {sample.size:,} rows is too few for a "
                    f"uniqueness claim to mean anything",
                ),
            )
        eligible, excluded = self._eligible(sample)
        caveats = sample.caveats()
        found: list[Candidate] = []
        skipped: list[str] = []

        for arity in range(1, self._max_arity + 1):
            for combination in itertools.combinations(eligible, arity):
                if any(set(c.columns) <= set(combination) for c in found):
                    # A superset of a key is unique by construction. Proposing
                    # it buries the key it contains.
                    continue
                candidate = self._evaluate(sample, combination, caveats)
                if candidate is not None:
                    found.append(candidate)

        if len(eligible) > self._max_arity:
            skipped.append(
                f"combinations of more than {self._max_arity} columns were not searched "
                f"({len(eligible)} columns were eligible). A wider key is rare, and one "
                f"found here would usually be a real key plus columns that came along"
            )
        return KeyFindings(
            dataset=sample.dataset,
            candidates=tuple(found),
            skipped=tuple(skipped),
            excluded=tuple(excluded),
        )

    def _eligible(self, sample: Sample) -> tuple[list[str], list[str]]:
        """Columns that could be part of a key, and why the others cannot.

        The null check is the one that matters. ``COUNT(DISTINCT x)`` ignores
        nulls, so a column with four values and a million blanks reports four
        distinct values in four non-null rows and looks perfectly unique. Every
        profiler that has not checked this has proposed such a column as a key.
        """
        eligible: list[str] = []
        excluded: list[str] = []
        for column in sample.columns:
            values = sample.values(column)
            nulls = sum(1 for v in values if v is None)
            fraction = nulls / len(values) if values else 1.0
            if fraction > self._maximum_null_fraction:
                excluded.append(
                    f"{column}: {fraction:.1%} of its values are missing, and a column "
                    f"that is mostly empty looks unique to any test that skips nulls"
                )
                continue
            if _is_continuous(values):
                # A float column is unique because floats are continuous, not
                # because it identifies anything. Businesses do not key on
                # measurements, and proposing a market value as a candidate key
                # is the kind of finding that makes people stop reading them.
                excluded.append(
                    f"{column}: a continuous numeric column. Its values are distinct "
                    f"because they are measurements, not because they identify a row"
                )
                continue
            eligible.append(column)
        return eligible, excluded

    def _evaluate(
        self, sample: Sample, columns: tuple[str, ...], caveats: tuple[str, ...]
    ) -> Candidate | None:
        rows = sample.tuples(columns)
        applicable = [t for t in rows if not any(v is None for v in t)]
        null_excluded = len(rows) - len(applicable)
        if not applicable:
            return None
        distinct = len(set(applicable))
        duplicates = len(applicable) - distinct
        uniqueness = distinct / len(applicable)
        if uniqueness < APPROXIMATE_THRESHOLD:
            return None
        evidence = Evidence(
            rows_examined=len(rows),
            supporting=distinct,
            violating=duplicates,
            null_excluded=null_excluded,
            distinct=distinct,
            caveats=caveats,
        )
        return Candidate(
            columns=columns,
            evidence=evidence,
            approximate=duplicates > 0,
            surrogate=len(columns) == 1 and _is_surrogate(columns[0], applicable),
        )


#: Column names that announce a generated identifier. Checked alongside the
#: values, because either alone is wrong: a column called ``id`` holding
#: ISINs is not a surrogate, and a column called ``ref`` holding 1..n is.
_SURROGATE_NAMES = ("id", "row_id", "rowid", "seq", "sequence", "pk", "key", "_id", "row_num")


def _is_continuous(values: list[Any]) -> bool:
    """Whether a column holds measurements rather than identifiers."""
    populated = [v for v in values if v is not None]
    if not populated:
        return False
    return all(isinstance(v, float) for v in populated)


def _is_surrogate(column: str, values: list[tuple[Any, ...]]) -> bool:
    """Whether a unique column looks generated rather than meaningful.

    Two shapes cover almost every case in practice. A dense integer run —
    values covering most of their own range — is a sequence or a row number. A
    UUID or ULID is a surrogate whatever it is called, since nothing in a
    business names a thing that way.
    """
    flat = [v[0] for v in values]
    lowered = column.lower()
    named = lowered in _SURROGATE_NAMES or lowered.endswith(("_id", "_seq", "_key"))

    if all(isinstance(v, int) and not isinstance(v, bool) for v in flat) and len(flat) > 1:
        span = max(flat) - min(flat) + 1
        # Dense means the values nearly enumerate their own range. A sequence
        # does; an account number drawn from a wider space does not.
        if span and len(flat) / span > 0.9:
            return True

    if flat and all(isinstance(v, str) for v in flat):
        sample = flat[: min(len(flat), 50)]
        if all(_UUID.match(str(v)) or _ULID.match(str(v)) for v in sample):
            return True
        # A name like `trade_id` alone is not enough: it is what most business
        # identifiers are called. It counts only alongside a value shape that
        # carries no meaning — fixed width, all digits.
        if named and all(str(v).isdigit() for v in sample):
            widths = {len(str(v)) for v in sample}
            return len(widths) == 1
    return False


def as_provenance(dataset: str, candidate: Candidate, sample: Sample) -> Provenance:
    """The provenance a mined key carries into the review queue.

    The observations are written so the reviewer can *re-run the observation* —
    "unique across 4.2m rows spanning 90 days" is checkable, where "confidence
    0.97" is not.
    """
    observations = [
        f"{candidate.render()} was unique across {candidate.evidence.rows_examined:,} "
        f"rows of {dataset}"
        + (
            ""
            if candidate.is_exact
            else f" except for {candidate.evidence.violating:,} duplicate rows"
        ),
        *sample.caveats(),
    ]
    return Provenance(
        origin=Origin.MINING,
        rule="mine.unique_key",
        source_ref=f"{dataset}#profile",
        statement=candidate.describe(),
        observations=tuple(observations),
    )


def key_identity(dataset: str, candidate: Candidate) -> str:
    return identity(dataset, "mine.unique_key", dataset, ",".join(candidate.columns))

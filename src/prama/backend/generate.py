"""Generating controls, so the conformance suite finds what nobody thought of.

A fixed corpus tests the cases its author imagined. That is worth a great deal
and is not enough: the interesting portability failures are combinations —
a negated predicate inside a filtered scope with a rate threshold and a null in
the segment column — and nobody writes those by hand in sufficient variety.

So controls are generated instead. Every generated control is run on every
engine and the answers must match; a disagreement is reported with the seed
that produced it, which makes it immediately reproducible and turns a flaky
"conformance failed" into a one-line repro.

The generator is deliberately conservative about what it emits. It builds only
controls the language guarantees, over a schema it knows, so a failure means
the *engines* disagree rather than that the generator invented something
meaningless. Generating nonsense and calling the resulting errors findings is
the commonest way a fuzzer becomes noise nobody reads.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import random

#: Columns of the conformance corpus, with what can sensibly be said about each.
NUMERIC = ("notional", "row_id")
TEXTUAL = ("isin", "ccy", "status", "entity", "account_id", "instrument_id")
SEGMENTABLE = ("entity", "ccy", "status")

#: Values drawn from and around the corpus, so predicates sometimes match and
#: sometimes do not. A generator whose predicates never matched would compare
#: three engines all returning zero.
TEXT_VALUES = ("GBP", "USD", "EUR", "XXX", "ACTIVE", "CANCELLED", "EMEA", "APAC", "MISSING")
NUMBERS = (-10.0, 0.0, 1.0, 100.0, 250.0, 500.0, 1000.0, 1001.0)


@dataclasses.dataclass(frozen=True, slots=True)
class Generated:
    """One generated control, with the seed that made it."""

    seed: int
    pql: str

    def __str__(self) -> str:
        return f"seed {self.seed}: {self.pql}"


class ControlGenerator:
    """Deterministic random controls over the conformance corpus.

    Deterministic because a conformance failure has to be reproducible: a suite
    that reports "some generated control disagreed" and cannot say which is
    worse than no suite, since nobody can act on it.
    """

    def __init__(self, dataset: str = "corpus") -> None:
        self._dataset = dataset

    def one(self, seed: int) -> Generated:
        rng = random.Random(seed)
        body = self._assertion(rng)
        clauses = [body]
        if rng.random() < 0.4:
            clauses.append(f"WHERE {self._condition(rng)}")
        if rng.random() < 0.25:
            clauses.append(f"FOR EACH {rng.choice(SEGMENTABLE)}")
        clauses.append(self._threshold(rng))
        return Generated(seed=seed, pql=" ".join(c for c in clauses if c))

    def many(self, count: int, *, start: int = 0) -> list[Generated]:
        return [self.one(start + n) for n in range(count)]

    # -- pieces ------------------------------------------------------------

    def _assertion(self, rng: random.Random) -> str:
        choice = rng.randrange(8)
        head = f"CHECK {self._dataset}"
        if choice == 0:
            column = rng.choice(TEXTUAL + NUMERIC)
            return f"{head}.{column} IS {'NOT ' if rng.random() < 0.7 else ''}NULL"
        if choice == 1:
            column = rng.choice(TEXTUAL)
            values = ", ".join(f"'{v}'" for v in rng.sample(TEXT_VALUES, rng.randint(1, 3)))
            negated = "NOT " if rng.random() < 0.3 else ""
            return f"{head}.{column} {negated}IN ({values})"
        if choice == 2:
            column = rng.choice(NUMERIC)
            lower, upper = sorted(rng.sample(NUMBERS, 2))
            return f"{head}.{column} BETWEEN {lower:g} AND {upper:g}"
        if choice == 3:
            column = rng.choice(NUMERIC)
            operator = rng.choice((">", ">=", "<", "<=", "=", "<>"))
            return f"{head}.{column} {operator} {rng.choice(NUMBERS):g}"
        if choice == 4:
            keys = ", ".join(rng.sample(TEXTUAL + NUMERIC, rng.randint(1, 3)))
            return f"{head} HAS UNIQUE KEY ({keys})"
        if choice == 5:
            lower = rng.randint(0, 8)
            return f"{head} HAS ROW COUNT BETWEEN {lower} AND {lower + rng.randint(0, 8)}"
        if choice == 6:
            return f"{head} SATISFIES {self._condition(rng)}"
        column = rng.choice(TEXTUAL)
        lower = rng.randint(1, 12)
        return f"{head}.{column} HAS LENGTH BETWEEN {lower} AND {lower + rng.randint(0, 6)}"

    def _condition(self, rng: random.Random) -> str:
        left = self._comparison(rng)
        if rng.random() < 0.45:
            joiner = rng.choice(("AND", "OR"))
            right = self._comparison(rng)
            condition = f"{left} {joiner} {right}"
            return f"NOT ({condition})" if rng.random() < 0.25 else condition
        return f"NOT ({left})" if rng.random() < 0.2 else left

    def _comparison(self, rng: random.Random) -> str:
        if rng.random() < 0.5:
            column = rng.choice(NUMERIC)
            operator = rng.choice((">", ">=", "<", "<=", "=", "<>"))
            return f"{column} {operator} {rng.choice(NUMBERS):g}"
        column = rng.choice(TEXTUAL)
        if rng.random() < 0.3:
            return f"{column} IS {'NOT ' if rng.random() < 0.5 else ''}NULL"
        operator = rng.choice(("=", "<>"))
        return f"{column} {operator} '{rng.choice(TEXT_VALUES)}'"

    def _threshold(self, rng: random.Random) -> str:
        choice = rng.randrange(4)
        if choice == 0:
            return f"AT MOST {rng.randint(0, 4)} ROWS"
        if choice == 1:
            return f"BELOW {rng.choice((5, 10, 20, 30, 50))}%"
        if choice == 2 and rng.random() < 0.4:
            # The policy that inverts SQL's default, exercised as often as the
            # engines disagree about nulls — which is often.
            return "TREAT UNKNOWN AS PASS BECAUSE 'generated'"
        return ""

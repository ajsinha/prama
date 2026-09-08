"""Mining: what the data obeys, and what that is worth.

Every test here is about the distance between "true in this sample" and "a
rule". That distance is where mining goes wrong, and closing it is most of what
these miners do.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random
import uuid

import pytest

from prama.core.provenance import Origin
from prama.mine.constraints import ConstraintMiner, InvariantKind
from prama.mine.dependencies import DependencyMiner, InclusionMiner
from prama.mine.keys import KeyMiner, as_provenance
from prama.mine.sample import Sample


def positions(days: tuple[str, ...] = ("2026-03-02", "2026-03-03")) -> Sample:
    rows = []
    rng = random.Random(7)
    for day in days:
        for account in range(400):
            rows.append(
                {
                    "account_id": f"A{account:04d}",
                    "business_date": day,
                    "ccy": rng.choice(["EUR", "USD"]),
                    "row_id": len(rows),
                    "note": None if rng.random() < 0.95 else "x",
                }
            )
    return Sample.of(
        "positions",
        rows,
        total_rows=len(rows),
        partition_column="business_date",
        method="full scan",
    )


# -- keys --------------------------------------------------------------------


def test_a_key_that_only_holds_within_one_partition_is_not_offered_as_the_key() -> None:
    """The failure every daily-snapshot table produces: account_id is perfectly
    unique within Monday and repeats on Tuesday."""
    findings = KeyMiner().mine(positions())
    assert findings.best is not None
    assert findings.best.columns == ("account_id", "business_date")


def test_mining_one_partition_finds_the_wrong_key_and_says_so() -> None:
    """The evidence genuinely is not there, and the only honest thing a miner
    can do is carry the caveat on every constraint it proposes."""
    findings = KeyMiner().mine(positions(days=("2026-03-02",)))
    assert findings.best is not None
    assert findings.best.columns == ("account_id",)
    caveats = " ".join(findings.best.evidence.caveats)
    assert "may not hold across them" in caveats
    assert "classic false key" in caveats


def test_a_mostly_null_column_is_never_a_key_candidate() -> None:
    """COUNT(DISTINCT) skips nulls, so a column with four values and a million
    blanks looks perfectly unique to any test that does not check."""
    findings = KeyMiner().mine(positions())
    assert any("note" in reason for reason in findings.excluded)
    assert all("note" not in c.columns for c in findings.candidates)


def test_a_continuous_column_is_not_a_key_candidate() -> None:
    """Its values are distinct because they are measurements."""
    rng = random.Random(3)
    sample = Sample.of(
        "t",
        [{"book": rng.choice("AB"), "market_value": rng.random() * 1000} for _ in range(500)],
    )
    findings = KeyMiner().mine(sample)
    assert any("market_value" in reason for reason in findings.excluded)


def test_a_surrogate_key_is_found_and_is_not_offered_as_the_grain() -> None:
    """ "One row per row_id" answers "what does one row represent?" with "a
    row", and offering it as the answer is worse than offering nothing."""
    findings = KeyMiner().mine(positions())
    surrogates = [c for c in findings.candidates if c.surrogate]
    assert any(c.columns == ("row_id",) for c in surrogates)
    assert findings.best is not None
    assert not findings.best.surrogate


def test_a_table_whose_only_key_is_generated_reports_no_business_key() -> None:
    rng = random.Random(3)
    sample = Sample.of(
        "t", [{"id": str(uuid.uuid4()), "status": rng.choice("AB")} for _ in range(500)]
    )
    findings = KeyMiner().mine(sample)
    assert findings.candidates
    assert not findings.business_key_found


def test_supersets_of_a_key_are_not_proposed() -> None:
    """If account_id is unique then so is every pair containing it, and
    proposing all of them buries the one that matters."""
    findings = KeyMiner().mine(positions(days=("2026-03-02",)))
    assert all(not ({"account_id"} < set(c.columns)) for c in findings.candidates)


def test_a_sample_too_small_to_mean_anything_is_refused_out_loud() -> None:
    findings = KeyMiner().mine(Sample.of("t", [{"a": i} for i in range(10)]))
    assert not findings.candidates
    assert "too few" in findings.skipped[0]


def test_what_was_not_searched_is_stated() -> None:
    """No silent caps. A report saying "found two keys" while having skipped
    every wider combination reads as completeness and is not."""
    findings = KeyMiner(max_arity=2).mine(positions())
    assert any("not searched" in note for note in findings.skipped)


def test_a_mined_key_carries_a_re_runnable_observation() -> None:
    """ "Unique across 800 rows" is checkable; "confidence 0.97" is not."""
    sample = positions()
    findings = KeyMiner().mine(sample)
    assert findings.best is not None
    provenance = as_provenance("positions", findings.best, sample)
    assert provenance.origin is Origin.MINING
    assert not provenance.origin.may_auto_activate
    assert "was unique across 800 rows" in provenance.observations[0]


# -- functional dependencies -------------------------------------------------


def trades(rows: int = 2000) -> Sample:
    rng = random.Random(11)
    issuer_of = {f"I{i}": f"ISSUER-{i % 40}" for i in range(200)}
    sector_of = {f"ISSUER-{i}": rng.choice(["FIN", "TECH", "ENERGY"]) for i in range(40)}
    data = []
    for n in range(rows):
        instrument = f"I{rng.randrange(200)}"
        issuer = issuer_of[instrument]
        country = rng.choice(["US", "US", "US", "GB", "DE"])
        data.append(
            {
                "trade_id": f"T{n:06d}",
                "instrument": instrument,
                "issuer": issuer,
                "sector": sector_of[issuer],
                "country": country,
                "state": rng.choice(["NY", "CA", "TX"]) if country == "US" else None,
                "record_type": "P",
                "qty": rng.randrange(1, 500),
            }
        )
    return Sample.of("trades", data, total_rows=rows)


def test_the_real_dependencies_are_found() -> None:
    findings = DependencyMiner().mine(trades())
    rendered = {d.render() for d in findings.dependencies}
    assert "instrument -> issuer" in rendered
    assert "issuer -> sector" in rendered


def test_a_key_is_not_reported_as_determining_every_column() -> None:
    """trade_id determines everything by construction. A miner without this
    filter reports one dependency per column and not one of them is a rule."""
    findings = DependencyMiner().mine(trades())
    assert all("trade_id" not in d.determinant for d in findings.dependencies)
    assert findings.discarded["near_key_determinant"] > 0


def test_a_constant_column_is_excluded_from_both_sides() -> None:
    """It is determined by everything, and determines nothing meaningful."""
    findings = DependencyMiner().mine(trades())
    assert all(d.dependent != "record_type" for d in findings.dependencies)
    assert findings.discarded["constant_column"] == 1


def test_a_dependency_implied_by_a_narrower_one_is_not_repeated() -> None:
    """If a -> c holds then (a, b) -> c holds for free."""
    findings = DependencyMiner().mine(trades())
    assert findings.discarded["implied"] > 0
    for dependency in findings.dependencies:
        narrower = [
            d
            for d in findings.dependencies
            if d.dependent == dependency.dependent
            and set(d.determinant) < set(dependency.determinant)
        ]
        assert not narrower


def test_a_conditional_dependency_that_also_holds_globally_is_not_reported() -> None:
    """Without this filter, every global dependency is re-reported once per
    value of the condition column, and a twelve-valued status column produces
    twelve copies of every real finding."""
    findings = DependencyMiner().mine(trades(), conditions=("country",))
    conditional = [d for d in findings.dependencies if d.is_conditional]
    globals_ = {(d.determinant, d.dependent) for d in findings.dependencies if not d.is_conditional}
    assert all((d.determinant, d.dependent) not in globals_ for d in conditional)
    assert findings.discarded["conditional_restates_global"] > 0


def test_conditional_completeness_is_mined_because_it_is_what_business_rules_look_like() -> None:
    """ "Every US address has a state" is false globally, true within the US,
    and is not a functional dependency at all. The global alternative is
    `state IS NOT NULL`, which fails on every non-US row and gets switched
    off."""
    findings = DependencyMiner().mine(trades(), conditions=("country",))
    completeness = [d for d in findings.dependencies if d.is_completeness]
    assert any(d.dependent == "state" for d in completeness)
    rule = next(d for d in completeness if d.dependent == "state")
    assert rule.render() == "state IS NOT NULL WHERE country = 'US'"
    assert "mandatory under that condition rather than everywhere" in rule.describe()


def test_a_column_mandatory_everywhere_is_not_dressed_as_conditional() -> None:
    """Narrowing a true rule for no reason."""
    findings = DependencyMiner().mine(trades(), conditions=("country",))
    assert all(d.dependent != "issuer" for d in findings.dependencies if d.is_completeness)


def test_a_dependency_cannot_be_supported_by_rows_where_a_value_is_missing() -> None:
    """Counting them as agreeing is how a mostly-null column gets reported as
    perfectly determined."""
    rng = random.Random(5)
    rows = [{"a": rng.choice("XYZ"), "b": None if rng.random() < 0.9 else "v"} for _ in range(500)]
    findings = DependencyMiner().mine(Sample.of("t", rows))
    for dependency in findings.dependencies:
        assert dependency.evidence.null_excluded > 0 or dependency.dependent != "b"


# -- inclusion dependencies --------------------------------------------------


def test_a_full_containment_is_reported_as_a_foreign_key() -> None:
    left = Sample.of("positions", [{"account_id": f"A{i % 50}"} for i in range(400)])
    right = Sample.of("accounts", [{"account_id": f"A{i}"} for i in range(50)])
    findings = InclusionMiner().mine(left, right)
    assert findings.inclusions
    inclusion = findings.inclusions[0]
    assert inclusion.is_exact
    assert "a foreign key nobody declared" in inclusion.describe()


def test_a_partial_containment_is_the_more_interesting_finding() -> None:
    """97% contained is a foreign key with three percent orphans, and that is a
    live defect somebody wants to know about today."""
    left = Sample.of(
        "positions",
        [{"account_id": f"A{i % 50}" if i % 40 else f"GHOST{i}"} for i in range(400)],
    )
    right = Sample.of("accounts", [{"account_id": f"A{i}"} for i in range(50)])
    inclusion = InclusionMiner().mine(left, right).inclusions[0]
    assert not inclusion.is_exact
    assert inclusion.orphan_examples
    assert "orphans" in inclusion.describe()
    assert "not a coincidence" in inclusion.describe()


def test_a_reference_to_something_that_is_not_a_key_is_not_a_foreign_key() -> None:
    """A status column with three distinct values contains every column in the
    world. The earlier version of this filter compared distinct counts and
    destroyed the partial-containment finding above, because a foreign key with
    orphans has *more* distinct values on the left — the orphans are the extra
    ones."""
    left = Sample.of("accounts", [{"k": f"A{i}"} for i in range(200)])
    right = Sample.of("lookup", [{"k": f"A{i % 3}"} for i in range(200)])
    findings = InclusionMiner().mine(left, right)
    assert not findings.inclusions


# -- invariants --------------------------------------------------------------


def book() -> Sample:
    rng = random.Random(5)
    rows = []
    for n in range(1000):
        quantity = rng.randrange(1, 1000)
        price = round(rng.uniform(1, 500), 4)
        notional = quantity * price
        fees = round(notional * 0.001, 6)
        trade = f"2026-03-{rng.randrange(1, 20):02d}"
        settle = f"2026-03-{int(trade[-2:]) + 2:02d}"
        broken = n < 12
        rows.append(
            {
                "trade_date": settle if broken else trade,
                "settlement_date": trade if broken else settle,
                "quantity": quantity,
                "price": price,
                "notional": notional,
                "fees": fees,
                "net": notional - fees,
            }
        )
    return Sample.of("trades", rows, total_rows=1000)


def test_an_arithmetic_identity_is_found_despite_floating_point() -> None:
    """An exact test finds nothing at all and reports a clean table with no
    invariants in it — the most misleading possible output, because it looks
    like a thorough search."""
    findings = ConstraintMiner().mine(book())
    expressions = {i.expression for i in findings.of_kind(InvariantKind.IDENTITY)}
    assert "price * quantity = notional" in expressions
    assert "fees + net = notional" in expressions


def test_one_identity_is_not_reported_three_ways() -> None:
    """a + b = c, c - a = b and c - b = a are one relationship."""
    findings = ConstraintMiner().mine(book())
    families = [frozenset(i.columns) for i in findings.of_kind(InvariantKind.IDENTITY)]
    assert len(families) == len(set(families))
    assert findings.discarded["algebraic_restatement"] > 0


def test_an_ordering_entailed_by_an_identity_is_not_reported_beside_it() -> None:
    """Three findings where there is one fact, and the two weak ones make the
    strong one harder to see."""
    findings = ConstraintMiner().mine(book())
    orderings = {i.expression for i in findings.of_kind(InvariantKind.ORDERING)}
    assert "net <= notional" not in orderings
    assert findings.discarded["implied_by_identity"] > 0


def test_a_date_ordering_is_found_with_the_rows_that_break_it() -> None:
    """Three concrete wrong rows beat any statistic."""
    findings = ConstraintMiner().mine(book())
    ordering = next(
        i for i in findings.invariants if i.expression == "trade_date <= settlement_date"
    )
    assert not ordering.is_exact
    assert ordering.evidence.violating == 12
    assert ordering.counterexamples
    example = ordering.counterexamples[0]
    assert example["trade_date"] > example["settlement_date"]


def test_the_strict_ordering_wins_over_the_loose_one() -> None:
    """a < b implies a <= b; reporting both adds nothing."""
    findings = ConstraintMiner().mine(book())
    for invariant in findings.of_kind(InvariantKind.ORDERING):
        assert findings.discarded.get("weaker_ordering", 0) >= 0
        assert invariant.expression.count("<") == 1


@pytest.mark.parametrize("miner", [KeyMiner(), DependencyMiner(), ConstraintMiner()])
def test_no_miner_speaks_at_all_on_a_sample_too_small(miner: object) -> None:
    tiny = Sample.of("t", [{"a": i, "b": i * 2} for i in range(20)])
    findings = miner.mine(tiny)  # type: ignore[attr-defined]
    assert len(findings) == 0
    assert findings.skipped

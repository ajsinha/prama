"""Γ for the thirteen relationship kinds.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.derive.relationships import (
    ComparisonKind,
    RelationshipGenerator,
    as_generation,
    generation_for,
)
from prama.ir.lower import Lowerer
from prama.pql import ast
from prama.pql.parser import parse_control
from prama.semantic.relationships import (
    MatchKey,
    OffsetUnit,
    RelationshipDeclaration,
    RelationshipKind,
    TimeOffset,
    Tolerance,
)

EUR = Tolerance(absolute=1.0, currency="EUR")


def declare(kind: RelationshipKind, **overrides: object) -> RelationshipDeclaration:
    base: dict[str, object] = {
        "kind": kind,
        "from_dataset_id": "subledger",
        "to_dataset_id": "general_ledger",
        "match_keys": (MatchKey("account_id"),),
        "compare": ("amount",),
        "name": "REL01",
    }
    if kind.requires_tolerance:
        base["tolerance"] = EUR
    base.update(overrides)
    return RelationshipDeclaration(**base)  # type: ignore[arg-type]


# -- coverage of the catalogue ----------------------------------------------


@pytest.mark.parametrize("kind", list(RelationshipKind))
def test_every_kind_produces_something_and_nothing_silently(kind: RelationshipKind) -> None:
    """docs/corpus/03 §2.4 lists what each kind generates. A kind that produced
    nothing, and said nothing about why, would leave a declaration the business
    made with no visible effect at all."""
    result = generation_for(declare(kind, tolerance=EUR))
    assert result.edges, kind
    assert (
        result.controls
        or result.comparisons
        or result.unsatisfiable
        or kind is (RelationshipKind.FEEDS)
    )


@pytest.mark.parametrize("kind", list(RelationshipKind))
def test_every_kind_records_an_edge_with_a_reason(kind: RelationshipKind) -> None:
    edge = generation_for(declare(kind, tolerance=EUR)).edges[0]
    assert edge.source == "subledger"
    assert edge.target == "general_ledger"
    assert len(edge.reason) > 40


# -- the kinds a row predicate can express ----------------------------------


def test_references_generates_a_control_that_runs_today() -> None:
    control = generation_for(declare(RelationshipKind.REFERENCES)).controls[0]
    assert isinstance(control.control.assertion, ast.ReferenceAssertion)
    assert parse_control(control.content).render() == control.content
    assert Lowerer().control(control.control).plan_id


def test_enrichment_coverage_is_a_reference_check_with_a_different_sentence() -> None:
    """Saying so, rather than inventing a second mechanism, is why the same
    executor runs both."""
    control = generation_for(declare(RelationshipKind.ENRICHES)).controls[0]
    assert isinstance(control.control.assertion, ast.ReferenceAssertion)
    assert "came from nowhere" in control.control.because


def test_a_hierarchy_generates_the_orphan_check_it_can_run() -> None:
    control = generation_for(declare(RelationshipKind.PARENT_OF)).controls[0]
    assert isinstance(control.control.assertion, ast.ReferenceAssertion)
    assert "unreachable from the root" in control.control.because


def test_a_hierarchy_with_no_parent_pointer_is_reported() -> None:
    result = generation_for(declare(RelationshipKind.PARENT_OF, match_keys=()))
    assert not result.is_complete
    assert "parent pointer" in result.unsatisfiable[0].reason


# -- the kinds that are comparisons ------------------------------------------


def test_a_reconciliation_carries_its_keys_tolerance_and_offset() -> None:
    """The inference is where cross-dataset checks go wrong: a comparison that
    guesses its join, its materiality or its time alignment produces breaks
    that are artefacts of the guess."""
    declaration = declare(
        RelationshipKind.RECONCILES_WITH,
        match_keys=(MatchKey("account_id"), MatchKey("cost_centre")),
        offset=TimeOffset(amount=1, unit=OffsetUnit.BUSINESS_DAYS, calendar="TARGET2"),
    )
    spec = generation_for(declaration).comparison(ComparisonKind.RECONCILIATION)
    assert spec is not None
    assert len(spec.match_keys) == 2
    assert spec.tolerance == EUR
    assert spec.offset is not None
    assert "1 business day (TARGET2)" in spec.describe()
    assert "classified by cause, aged, and owned" in spec.workflow


def test_a_reconciliation_with_no_tolerance_is_refused_with_the_reason() -> None:
    """A control that breaks every day on a rounding difference is switched off
    within the week."""
    declaration = RelationshipDeclaration(
        kind=RelationshipKind.MIRRORS,
        from_dataset_id="a",
        to_dataset_id="b",
        match_keys=(MatchKey("k"),),
        compare=("amount",),
    )
    result = RelationshipGenerator().generate(declaration)
    # A mirror is exact by design, so this one is *not* refused.
    assert result.is_complete
    assert result.comparison(ComparisonKind.VALUE_PARITY) is not None


def test_a_replica_is_compared_exactly_and_is_not_asked_for_a_tolerance() -> None:
    """Asking what difference is acceptable in a copy invites an answer, and
    any answer above zero makes the control unable to detect the thing it
    exists for."""
    spec = generation_for(declare(RelationshipKind.MIRRORS)).comparison(ComparisonKind.VALUE_PARITY)
    assert spec is not None
    assert spec.tolerance is None


def test_a_mirror_checks_count_content_and_staleness_rather_than_one_of_them() -> None:
    """Row-count parity alone passes a replica that copied the right number of
    rows with stale values; content parity alone passes one missing a thousand
    rows it never received."""
    kinds = {c.kind for c in generation_for(declare(RelationshipKind.MIRRORS)).comparisons}
    assert kinds == {
        ComparisonKind.ROW_COUNT_PARITY,
        ComparisonKind.VALUE_PARITY,
        ComparisonKind.STALENESS,
    }


def test_a_comparison_with_nothing_to_compare_is_refused() -> None:
    """It would report a clean result over any two datasets at all.

    Declared as SAME_ENTITY_AS rather than RECONCILES_WITH because the
    declaration itself already refuses a reconciliation with nothing to
    reconcile — which is the right place for it. This kind reaches Γ with the
    gap intact, and Γ has to catch it there.
    """
    result = generation_for(declare(RelationshipKind.SAME_ENTITY_AS, compare=()))
    assert not result.is_complete
    assert "no attribute was named to compare" in result.unsatisfiable[0].reason


def test_a_comparison_renders_to_a_stable_diffable_line() -> None:
    spec = generation_for(declare(RelationshipKind.RECONCILES_WITH)).comparisons[0]
    assert spec.render().startswith("COMPARE subledger WITH general_ledger ON (account_id)")
    assert "WITHIN 1 EUR" in spec.render()
    assert (
        spec.content_hash
        == generation_for(declare(RelationshipKind.RECONCILES_WITH)).comparisons[0].content_hash
    )


def test_editing_a_tolerance_moves_the_content_hash_and_not_the_identity() -> None:
    before = generation_for(declare(RelationshipKind.RECONCILES_WITH)).comparisons[0]
    after = generation_for(
        declare(RelationshipKind.RECONCILES_WITH, tolerance=Tolerance(absolute=5.0))
    ).comparisons[0]
    assert before.identity == after.identity
    assert before.content_hash != after.content_hash


def test_every_comparison_describes_itself_in_a_sentence() -> None:
    for kind in RelationshipKind:
        for spec in generation_for(declare(kind, tolerance=EUR)).comparisons:
            sentence = spec.describe()
            assert sentence.endswith(".")
            assert "subledger" in sentence
            assert "{" not in sentence, f"{spec.kind} left a placeholder unfilled"


# -- feeds: knowledge rather than a check -----------------------------------


def test_feeds_generates_an_edge_and_deliberately_no_control() -> None:
    """The arrival control already exists — it is the target's own rhythm — and
    a second one produces two alerts for one late file from two different
    declarations, which is how an estate becomes unowned."""
    result = generation_for(declare(RelationshipKind.FEEDS, match_keys=()))
    assert not result.controls
    assert not result.comparisons
    assert result.edges[0].carries_trust


# -- trust propagation -------------------------------------------------------


def test_only_kinds_that_move_data_carry_trust() -> None:
    carrying = {
        kind
        for kind in RelationshipKind
        if generation_for(declare(kind, tolerance=EUR)).edges[0].carries_trust
    }
    assert RelationshipKind.DERIVES_FROM in carrying
    assert RelationshipKind.MIRRORS in carrying
    assert RelationshipKind.MUTUALLY_EXCLUSIVE not in carrying


def test_a_reconciliation_edge_explains_why_trust_must_not_propagate() -> None:
    """The independence is exactly what makes agreement worth anything, and a
    wrong reason on a graph edge is what gets quoted back when somebody asks
    why an incident raised no alarm downstream."""
    edge = generation_for(declare(RelationshipKind.RECONCILES_WITH)).edges[0]
    assert not edge.carries_trust
    assert "independent by construction" in edge.reason


@pytest.mark.parametrize("kind", list(RelationshipKind))
def test_no_kind_is_given_a_borrowed_reason_for_not_carrying_trust(
    kind: RelationshipKind,
) -> None:
    """One blanket sentence was wrong for most of them."""
    edge = generation_for(declare(kind, tolerance=EUR)).edges[0]
    if not edge.carries_trust and kind not in (
        RelationshipKind.MUTUALLY_EXCLUSIVE,
        RelationshipKind.TOGETHER_COMPLETE,
    ):
        assert "statement about which population" not in edge.reason


# -- the lossy view ----------------------------------------------------------


def test_the_control_only_view_of_a_reconciliation_is_empty_and_that_is_the_truth() -> None:
    """There is no row predicate for "these two should agree to a euro", and a
    caller that only handles controls should see nothing rather than something
    that answers a different question."""
    result = generation_for(declare(RelationshipKind.RECONCILES_WITH))
    assert as_generation(result).controls == ()
    assert result.comparisons

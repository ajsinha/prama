"""Trust that flows along lineage, over a semiring somebody chose.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.lineage.graph import Column, Edge, LineageGraph, Transform
from prama.score.trust import (
    Containment,
    Semiring,
    TrustPropagator,
    ranked_by_trust,
)

C = Column.parse


def chain() -> LineageGraph:
    """A bad feed and a good rate table, meeting at a position value."""
    graph = LineageGraph()
    graph.add_all(
        [
            Edge(C("feed.amount"), C("staging.amount"), Transform.IDENTITY),
            Edge(C("staging.amount"), C("positions.value"), Transform.DERIVED),
            Edge(C("positions.value"), C("finrep.line_23"), Transform.AGGREGATED),
            Edge(C("reference.rate"), C("positions.value"), Transform.DERIVED),
        ]
    )
    return graph


LOCAL = {C("feed.amount"): 0.4, C("reference.rate"): 0.95}


# -- the defence against "arbitrary" -----------------------------------------


def test_the_default_treats_inputs_as_complementary() -> None:
    """A derived value needs every one of its inputs. Taking the best across
    complementary paths is the classic error, and it is seductive because it
    produces reassuring numbers: a report built from a corrupt feed and a
    healthy rate table scores as though the feed were fine."""
    propagator = TrustPropagator(chain())
    complementary = propagator.trust(C("finrep.line_23"), LOCAL).score
    redundant = (
        TrustPropagator(chain(), semiring=Semiring.REDUNDANT_SOURCES)
        .trust(C("finrep.line_23"), LOCAL)
        .score
    )
    assert complementary < redundant
    assert complementary == pytest.approx(0.853, abs=0.01)


def test_the_semirings_genuinely_disagree() -> None:
    """Which is the point: different businesses mean different things, and a
    constant buried in a loop would pick for them."""
    scores = {
        semiring: TrustPropagator(chain(), semiring=semiring)
        .trust(C("finrep.line_23"), LOCAL)
        .score
        for semiring in Semiring
    }
    assert len({round(score, 3) for score in scores.values()}) > 1


def test_every_semiring_can_say_what_it_means() -> None:
    """A person choosing has an opinion about the meaning and none about the
    algebra."""
    for semiring in Semiring:
        assert len(semiring.explains) > 40


def test_the_derivation_shows_the_path_that_decided_the_score() -> None:
    """Showing the best path under a semiring that takes the worst produces an
    explanation whose arithmetic does not reach its own conclusion — the
    "arbitrary number" complaint arrived at by another route."""
    trust = TrustPropagator(chain()).trust(C("finrep.line_23"), LOCAL)
    explanation = trust.explain()
    assert "feed.amount (0.40)" in explanation
    assert trust.derivation[0].edge.source == C("feed.amount")


def test_the_alternatives_considered_are_counted() -> None:
    """A score that took the worst of four paths is a different claim from one
    that had only the path it took."""
    trust = TrustPropagator(chain()).trust(C("finrep.line_23"), LOCAL)
    assert trust.alternatives >= 1
    assert "other paths were considered" in trust.explain()


def test_a_column_with_nothing_upstream_scores_on_its_own_evidence() -> None:
    trust = TrustPropagator(chain()).trust(C("feed.amount"), LOCAL)
    assert trust.score == 0.4
    assert not trust.is_inherited
    assert "nothing upstream of it is known" in trust.explain()


def test_a_column_downstream_of_a_defect_inherits_it() -> None:
    trust = TrustPropagator(chain()).trust(C("staging.amount"), LOCAL)
    assert trust.is_inherited
    assert trust.score == pytest.approx(0.4)


# -- containment, the honest half --------------------------------------------


def test_a_control_that_caught_the_problem_stops_it_propagating() -> None:
    """A dataset whose own controls would catch the upstream defect, and which
    passed them, did not receive the defect. Continuing to discount it punishes
    it for a fault it demonstrably does not have."""
    contained = TrustPropagator(
        chain(),
        containment=[Containment(C("positions.value"), "value range check", passed=True)],
    )
    assert contained.trust(C("finrep.line_23"), LOCAL).score == pytest.approx(1.0)


def test_a_control_that_did_not_run_contains_nothing() -> None:
    """A control that exists and did not run is not evidence about anything."""
    not_run = TrustPropagator(
        chain(),
        containment=[Containment(C("positions.value"), "value range check", passed=False)],
    )
    assert not_run.trust(C("finrep.line_23"), LOCAL).score < 0.9


def test_containment_is_visible_in_the_derivation() -> None:
    """Showing *why* nothing was inherited is more useful than the hop being
    absent."""
    contained = TrustPropagator(
        chain(),
        containment=[Containment(C("positions.value"), "value range check", passed=True)],
    )
    explanation = contained.trust(C("finrep.line_23"), LOCAL).explain()
    assert "contained by value range check" in explanation
    assert "did not arrive here" in explanation


# -- the aggregate direction -------------------------------------------------


def test_an_aggregate_makes_a_column_more_trustworthy_than_its_source() -> None:
    """One bad row in ten thousand barely moves a total. Applying the
    transform's attenuation to the score rather than to the deficit would make
    every aggregate less trustworthy than its inputs, which is backwards."""
    graph = LineageGraph()
    graph.add(Edge(C("a.x"), C("b.total"), Transform.AGGREGATED))
    propagator = TrustPropagator(graph)
    assert propagator.trust(C("b.total"), {C("a.x"): 0.2}).score > 0.2


def test_a_copy_inherits_the_defect_intact() -> None:
    graph = LineageGraph()
    graph.add(Edge(C("a.x"), C("b.x"), Transform.IDENTITY))
    assert TrustPropagator(graph).trust(C("b.x"), {C("a.x"): 0.2}).score == pytest.approx(0.2)


# -- the remediation queue ---------------------------------------------------


def test_trust_ranks_the_consequence_where_severity_ranks_the_finding() -> None:
    """`RQ8`. The two disagree exactly where the disagreement is worth having:
    a low-severity defect sitting upstream of something important."""
    graph = LineageGraph()
    graph.add_all(
        [
            Edge(C("feed.minor"), C("positions.value"), Transform.IDENTITY),
            Edge(C("positions.value"), C("finrep.line_23"), Transform.IDENTITY),
            Edge(C("scratch.note"), C("scratch.copy"), Transform.IDENTITY),
        ]
    )
    # A mild problem upstream of a return, and a severe one in a scratch table.
    local = {C("feed.minor"): 0.7, C("scratch.note"): 0.2}
    trusts = TrustPropagator(graph).trust_all(local)

    by_severity = sorted(local, key=lambda column: local[column])
    assert by_severity[0] == C("scratch.note")

    # By consequence, the mild upstream defect has reached the regulatory
    # return; the severe one has reached a scratch copy.
    affected = {column.qualified for column, trust in trusts.items() if trust.score < 1.0}
    assert "finrep.line_23" in affected
    assert trusts[C("finrep.line_23")].score == pytest.approx(0.7)


def test_the_queue_is_least_trustworthy_first() -> None:
    trusts = TrustPropagator(chain()).trust_all(LOCAL)
    ordered = ranked_by_trust(trusts, limit=3)
    assert ordered[0].column == C("feed.amount")
    assert ordered[0].score <= ordered[-1].score


def test_a_cycle_does_not_hang_the_propagation() -> None:
    graph = LineageGraph()
    graph.add_all(
        [
            Edge(C("a.x"), C("b.y"), Transform.DERIVED),
            Edge(C("b.y"), C("a.x"), Transform.DERIVED),
        ]
    )
    assert TrustPropagator(graph).trust(C("b.y"), {C("a.x"): 0.5}).score < 1.0

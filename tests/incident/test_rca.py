"""Ranked causes, each with the thing to go and look at.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from prama.incident.correlate import Change, Correlator, Finding
from prama.incident.rca import Evidence, RootCause, learn_from
from prama.lineage.graph import Column, Edge, LineageGraph, Transform

C = Column.parse
BASE = datetime(2026, 4, 1, 6, 0)


def graph() -> LineageGraph:
    g = LineageGraph()
    g.add_all(
        [
            Edge(C("vendor.price"), C("feed.amount"), Transform.IDENTITY),
            Edge(C("feed.amount"), C("staging.amount"), Transform.IDENTITY),
            Edge(C("staging.amount"), C("positions.value"), Transform.DERIVED),
            Edge(C("staging.amount"), C("positions.value2"), Transform.DERIVED),
        ]
    )
    return g


def incident():  # type: ignore[no-untyped-def]
    findings = [
        Finding("f1", "positions", "value", BASE),
        Finding("f2", "positions", "value2", BASE),
    ]
    return Correlator(graph()).correlate(findings).incidents[0]


# -- what makes a hypothesis worth ranking -----------------------------------


def test_every_hypothesis_says_how_to_check_it() -> None:
    """ "The 06:30 feed did not arrive" is verifiable in thirty seconds; "there
    may be an upstream data quality issue" is not verifiable at all."""
    analysis = RootCause(graph(), failing=[C("feed.amount")]).analyse(incident())
    assert analysis.hypotheses
    for hypothesis in analysis.hypotheses:
        assert hypothesis.check
        assert hypothesis.confirms
        assert hypothesis.rules_out


def test_a_hypothesis_says_what_would_kill_it() -> None:
    """A check that can only confirm is a check that always confirms."""
    analysis = RootCause(graph(), failing=[C("feed.amount")]).analyse(incident())
    best = analysis.best
    assert best is not None
    assert "started afterwards" in best.rules_out


def test_the_check_is_specific_to_the_evidence() -> None:
    """A generic "investigate upstream" would rank the same and help nobody."""
    failing = RootCause(graph(), failing=[C("feed.amount")]).analyse(incident())
    assert failing.best is not None
    assert "read the last result of the controls" in failing.best.check

    changed = RootCause(
        graph(),
        changes=[
            Change("c", BASE - timedelta(minutes=10), "mapping edited", touched=("feed.amount",))
        ],
    ).analyse(incident())
    assert changed.best is not None
    assert "read the change" in changed.best.check


# -- the ranking -------------------------------------------------------------


def test_a_demonstrated_upstream_failure_outranks_everything() -> None:
    """Something upstream is known to be broken, and a system that ranks a
    speculative cause above it is ranking on the wrong axis."""
    analysis = RootCause(
        graph(),
        failing=[C("feed.amount")],
        priors={"vendor.price": 10},
    ).analyse(incident())
    assert analysis.best is not None
    assert analysis.best.column == C("feed.amount")
    assert analysis.best.is_demonstrated


def test_a_change_is_strong_evidence_because_most_incidents_are_somebody_s_tuesday() -> None:
    analysis = RootCause(
        graph(),
        changes=[
            Change(
                "c9",
                BASE - timedelta(minutes=30),
                "vendor mapping changed",
                "a.sinha",
                touched=("feed.amount",),
            )
        ],
    ).analyse(incident())
    assert analysis.best is not None
    assert "vendor mapping changed" in analysis.best.cause
    assert Evidence.CHANGE in {kind for kind, _ in analysis.best.evidence}


def test_the_nearest_upstream_is_likelier_than_the_furthest() -> None:
    """A defect that travelled six hops would have been caught by something on
    the way if anything on the way were watching."""
    analysis = RootCause(graph()).analyse(incident())
    columns = [item.column for item in analysis.hypotheses if item.column]
    assert columns.index(C("feed.amount")) < columns.index(C("vendor.price"))


def test_the_origin_appears_in_its_own_analysis() -> None:
    """Where the failures converge is the single most likely place for the
    defect to be, and an earlier version gave it no evidence at all — so it was
    omitted and the nearest *upstream* column ranked first. The most obvious
    answer has to be on the list even when it is obvious."""
    analysis = RootCause(graph()).analyse(incident())
    assert analysis.hypotheses[0].column == C("staging.amount")
    assert "converges here" in analysis.hypotheses[0].evidence[0][1]


def test_a_prior_is_weak_and_worth_having_because_it_is_free() -> None:
    assert Evidence.PRIOR.weight < Evidence.PROXIMITY.weight
    assert Evidence.UPSTREAM_FAILING.weight > Evidence.CHANGE.weight


def test_priors_are_counts_rather_than_a_model() -> None:
    """There is nothing a model would add that a count does not, and a great
    deal it would take away: this one can be printed and reset."""
    assert learn_from([("i1", "feed.amount"), ("i2", "feed.amount")]) == {"feed.amount": 2}


# -- honesty about how sure it is --------------------------------------------


def test_a_close_field_says_it_is_where_to_start_rather_than_the_answer() -> None:
    """ "We think it is one of these four" is a useful and different answer from
    "it is this", and presenting the first as the second is how an RCA loses
    its reader the second time it is wrong."""
    analysis = RootCause(graph()).analyse(incident())
    if not analysis.is_conclusive:
        assert "where to start rather than the answer" in analysis.describe()


def test_one_clear_leader_is_reported_as_conclusive() -> None:
    analysis = RootCause(graph(), failing=[C("feed.amount")]).analyse(incident())
    assert analysis.is_conclusive


def test_nothing_upstream_means_the_cause_is_here() -> None:
    """Which is an answer rather than a shrug: a column with nothing feeding it
    that is failing is failing on its own account."""
    empty = LineageGraph()
    empty.add(Edge(C("a.x"), C("b.y")))
    findings = [Finding("f", "a", "x", BASE)]
    lone = Correlator(empty).correlate(findings).incidents[0]
    analysis = RootCause(empty).analyse(lone)
    assert len(analysis.hypotheses) == 1
    assert analysis.hypotheses[0].column == C("a.x")
    assert "originates in a.x" in analysis.hypotheses[0].cause


def test_a_finding_with_no_column_at_all_offers_nothing_rather_than_a_guess() -> None:
    """Rather than a ranked list of nothing."""
    empty = LineageGraph()
    findings = [Finding("f", "a", "", BASE)]
    lone = Correlator(empty).correlate(findings).incidents[0]
    analysis = RootCause(empty).analyse(lone)
    assert not analysis.hypotheses
    assert "not in the lineage graph" in analysis.describe()


def test_how_wide_it_looked_is_reported_without_listing_forty_things() -> None:
    analysis = RootCause(graph()).analyse(incident())
    assert analysis.considered >= 3
    assert len(analysis.hypotheses) <= 5

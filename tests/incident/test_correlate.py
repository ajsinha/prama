"""One upstream defect, one incident.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from prama.incident.correlate import Change, Correlator, Finding, Signal
from prama.lineage.graph import Column, Edge, LineageGraph, Transform

C = Column.parse
BASE = datetime(2026, 4, 1, 6, 0)


def fan_out(width: int = 12, depth: int = 3) -> LineageGraph:
    """One feed column into `width` datasets, each with `depth` derived columns."""
    graph = LineageGraph()
    for index in range(width):
        graph.add(Edge(C("feed.amount"), C(f"d{index}.amount"), Transform.DERIVED))
        for inner in range(depth):
            graph.add(Edge(C(f"d{index}.amount"), C(f"d{index}.derived{inner}"), Transform.DERIVED))
    return graph


def findings(width: int = 12, depth: int = 3) -> list[Finding]:
    out = []
    for index in range(width):
        out.append(Finding(f"f{index}", f"d{index}", "amount", BASE + timedelta(minutes=index)))
        for inner in range(depth):
            out.append(
                Finding(
                    f"f{index}.{inner}",
                    f"d{index}",
                    f"derived{inner}",
                    BASE + timedelta(minutes=index),
                )
            )
    return out


# -- the acceptance criterion ------------------------------------------------


def test_one_upstream_defect_produces_one_incident() -> None:
    """Not four hundred. Wave 7's selector already folds a dataset's
    simultaneous failures into one finding, and twelve datasets going stale
    still produces twelve — which is eleven more than there are incidents."""
    result = Correlator(fan_out()).correlate(findings())
    assert len(result.incidents) == 1
    assert len(result.incidents[0].findings) == 48
    assert result.reduction > 0.9


def test_the_incident_is_about_the_column_rather_than_the_warehouse() -> None:
    """The payoff for column-level lineage. Table-level would name the common
    ancestor as "the warehouse", which groups everything into one incident
    every night and is worse than not grouping at all."""
    incident = Correlator(fan_out()).correlate(findings()).incidents[0]
    assert incident.common_ancestor == C("feed.amount")
    assert "downstream of feed.amount" in incident.describe()


def test_an_unrelated_problem_stays_its_own_incident() -> None:
    """Correlation that swallows everything is the same failure as correlation
    that swallows nothing, arrived at from the other side."""
    everything = [
        *findings(),
        Finding("other", "reference", "lei", BASE + timedelta(minutes=5)),
    ]
    result = Correlator(fan_out()).correlate(everything)
    assert len(result.incidents) == 2
    assert any(incident.findings[0].identity == "other" for incident in result.incidents)


# -- the signals -------------------------------------------------------------


def test_a_change_beforehand_is_the_first_place_to_look() -> None:
    """It converts "these twelve things broke" into "these twelve things broke
    twenty minutes after somebody changed that", and the second is a sentence
    with a next step in it."""
    change = Change(
        "c1",
        BASE - timedelta(minutes=20),
        "mapping edited",
        "a.sinha",
        touched=("feed.amount",),
    )
    incident = Correlator(fan_out(), changes=[change]).correlate(findings()).incidents[0]
    assert incident.change is not None
    assert "mapping edited by a.sinha" in incident.describe()
    assert Signal.CHANGE in {signal for signal, _ in incident.signals}


def test_a_change_that_touched_nothing_involved_is_not_offered() -> None:
    """A list of eleven changes is a list nobody reads."""
    unrelated = Change(
        "c2", BASE - timedelta(minutes=10), "unrelated deploy", touched=("other.thing",)
    )
    incident = Correlator(fan_out(), changes=[unrelated]).correlate(findings()).incidents[0]
    assert incident.change is None


def test_a_change_long_before_the_failure_is_not_a_cause() -> None:
    stale = Change("c3", BASE - timedelta(days=5), "mapping edited", touched=("feed.amount",))
    incident = Correlator(fan_out(), changes=[stale]).correlate(findings()).incidents[0]
    assert incident.change is None


def test_timing_alone_is_almost_no_evidence() -> None:
    """At six in the morning everything fails together because everything runs
    together."""
    assert Signal.TIME.strength < 0.2
    assert Signal.CHANGE.strength > Signal.LINEAGE.strength > Signal.TIME.strength


def test_grouping_on_timing_alone_says_so() -> None:
    """Usually right and occasionally merges two unrelated problems, and the
    person triaging needs to know which kind they are holding."""
    result = Correlator(None).correlate(
        [
            Finding("a", "same", "x", BASE),
            Finding("b", "same", "y", BASE + timedelta(minutes=2)),
        ]
    )
    incident = result.incidents[0]
    assert len(incident.findings) == 2
    assert Signal.LINEAGE not in {signal for signal, _ in incident.signals}


def test_a_lone_finding_is_certain_rather_than_uncertain() -> None:
    """There is no grouping to be wrong about. Reporting zero reads as "we are
    not sure this is an incident", which is a much more alarming claim."""
    incident = Correlator(None).correlate([Finding("a", "d", "x", BASE)]).incidents[0]
    assert incident.confidence == 1.0
    assert not incident.is_speculative


def test_corroborating_signals_beat_one_strong_one() -> None:
    """Averaging would let a time coincidence drag a well-supported grouping
    down to its level."""
    change = Change("c", BASE - timedelta(minutes=5), "edited", touched=("feed.amount",))
    with_change = Correlator(fan_out(), changes=[change]).correlate(findings()).incidents[0]
    without = Correlator(fan_out()).correlate(findings()).incidents[0]
    assert with_change.confidence > without.confidence


# -- degrading rather than failing -------------------------------------------


def test_findings_with_no_lineage_fall_back_to_dataset_and_time() -> None:
    """A graph that does not reach everywhere degrades rather than fails."""
    result = Correlator(fan_out()).correlate(
        [
            Finding("a", "unknown", "", BASE),
            Finding("b", "unknown", "", BASE + timedelta(minutes=2)),
        ]
    )
    assert len(result.incidents) == 1


def test_findings_far_apart_in_time_are_not_one_incident() -> None:
    result = Correlator(None).correlate(
        [
            Finding("a", "same", "", BASE),
            Finding("b", "same", "", BASE + timedelta(hours=9)),
        ]
    )
    assert len(result.incidents) == 2


def test_no_findings_is_no_incidents() -> None:
    assert Correlator(None).correlate([]).incidents == ()


def test_the_reduction_is_the_number_to_publish() -> None:
    result = Correlator(fan_out()).correlate(findings())
    assert "fewer things to look at" in result.describe()

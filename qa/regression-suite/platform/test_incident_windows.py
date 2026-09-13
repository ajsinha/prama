"""An incident is a claim that findings share one cause.

QA round 2, `INC-011`. Sharing an upstream column was the only test applied, so
two unrelated failures three days apart merged into one incident — because
everything in a warehouse shares a feed eventually.

A cause that acted on Monday and again on Thursday, with nothing between, is
two causes. Merging them sends one responder to explain both.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from prama.incident.correlate import Correlator, Finding
from prama.lineage.graph import Column, Edge, LineageGraph, Transform

BASE = datetime(2026, 9, 14, 6, 0)


def _fan_out() -> LineageGraph:
    """One feed column into two datasets — the shape that made everything share."""
    graph = LineageGraph()
    for index in range(2):
        graph.add(
            Edge(
                Column.parse("feed.amount"),
                Column.parse(f"d{index}.amount"),
                Transform.DERIVED,
            )
        )
    return graph


def test_findings_days_apart_are_separate_incidents() -> None:
    findings = [
        Finding("a", "d0", "amount", BASE),
        Finding("b", "d1", "amount", BASE + timedelta(days=3)),
    ]
    assert len(Correlator(_fan_out()).correlate(findings).incidents) == 2


def test_findings_minutes_apart_are_one_incident() -> None:
    """The counterfactual.

    A window that separated everything would destroy the correlation this
    module exists to do — the acceptance criterion is that one upstream defect
    produces one incident, not forty-eight.
    """
    findings = [
        Finding("a", "d0", "amount", BASE),
        Finding("b", "d1", "amount", BASE + timedelta(minutes=5)),
    ]
    assert len(Correlator(_fan_out()).correlate(findings).incidents) == 1

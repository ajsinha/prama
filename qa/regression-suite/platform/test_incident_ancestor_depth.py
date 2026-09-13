"""An incident names the nearest shared column, measured from the graph.

QA round 3, `INC-010`, recorded as `Q-65`. `_shared_ancestor` ranked candidate
columns by ``(vote count, len(key))`` — the number of findings that share the
column, then **the length of its name**. Its own docstring says what the second
term is for:

    Deepest rather than any: everything shares "the raw feed" eventually, and an
    incident about the raw feed when the fault is in one derived column sends
    people to the wrong system.

Name length is a proxy for depth only by coincidence. A staging column called
`staging_raw.ingested_source_column` is the raw feed and has the longest name in
the graph; the derived column `d.m` downstream of it is deeper and shorter. On
that shape the tiebreak chose the raw feed and the incident pointed at the wrong
system — the failure the docstring was written to prevent.

Depth is now taken from the lineage graph: how many sources a candidate has of
its own. A raw feed has none, a derived column has some, and the ranking no
longer depends on what anybody named a column.

**What this test does not settle.** `Q-65` is about the ordering between
*broadest* and *deepest* when the vote counts genuinely differ — one upstream
defect must produce one incident, and two findings sharing a nearer derived
column deserve their own — and those two requirements conflict. Answering it
needs incidents that can have a parent, not a different sort key, and that is a
wave rather than a batch. This file fixes only the case where the two rankings
disagree *at equal vote counts*, which is unambiguous.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime

from prama.incident.correlate import Correlator, Finding
from prama.lineage.graph import Column, Edge, LineageGraph, Transform

OPENED = datetime(2026, 3, 31, 2, 0, tzinfo=UTC)


def col(qualified: str) -> Column:
    dataset, name = qualified.split(".", 1)
    return Column(dataset, name)


def test_the_nearest_shared_column_wins_even_when_the_raw_feed_has_a_longer_name() -> None:
    """The counterfactual case: depth and name length rank the candidates oppositely."""
    graph = LineageGraph()
    graph.add_all(
        [
            # The raw feed, with the longest name in the graph.
            Edge(col("staging_raw.ingested_source_column"), col("d.m"), Transform.DERIVED),
            # One derived column, with the shortest, feeding both findings.
            Edge(col("d.m"), col("a.one"), Transform.DERIVED),
            Edge(col("d.m"), col("a.two"), Transform.DERIVED),
        ]
    )

    incidents = Correlator(graph).correlate(
        [Finding("a.one", "a", "one", OPENED), Finding("a.two", "a", "two", OPENED)]
    ).incidents

    assert len(incidents) == 1
    ancestor = incidents[0].common_ancestor
    assert ancestor is not None
    assert ancestor.qualified == "d.m", (
        f"the incident names {ancestor.qualified!r}. Both findings descend from "
        "d.m, which is nearer than the staging column; naming the raw feed sends "
        "people to the wrong system, which is what the ranking exists to prevent."
    )


def test_depth_comes_from_the_graph_and_not_from_the_name() -> None:
    """Renaming a column must not change which incident is reported.

    The sharper statement of the same defect: the verdict of a correlation
    should be a property of the lineage, and under the old tiebreak it was a
    property of somebody's naming convention.
    """
    findings = [Finding("a.one", "a", "one", OPENED), Finding("a.two", "a", "two", OPENED)]

    def ancestor_for(raw_name: str, derived_name: str) -> str:
        graph = LineageGraph()
        graph.add_all(
            [
                Edge(col(raw_name), col(derived_name), Transform.DERIVED),
                Edge(col(derived_name), col("a.one"), Transform.DERIVED),
                Edge(col(derived_name), col("a.two"), Transform.DERIVED),
            ]
        )
        found = Correlator(graph).correlate(findings).incidents[0].common_ancestor
        assert found is not None
        return "raw" if found.qualified == raw_name else "derived"

    short_raw = ancestor_for("r.f", "a_much_longer_derived.column_name")
    long_raw = ancestor_for("a_much_longer_staging.ingested_column", "d.m")

    assert short_raw == long_raw == "derived", (
        "which column the incident names changed when the columns were renamed: "
        f"short raw name gave {short_raw!r}, long raw name gave {long_raw!r}"
    )

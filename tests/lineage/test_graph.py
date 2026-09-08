"""Column-level lineage, and the blast radius it supports.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.lineage.graph import (
    IMPACT_FLOOR,
    Column,
    Edge,
    LineageGraph,
    Transform,
    merge,
)

C = Column.parse


def warehouse() -> LineageGraph:
    graph = LineageGraph()
    graph.add_all(
        [
            Edge(C("feed.amount"), C("staging.amount"), Transform.IDENTITY, produced_by="ingest"),
            Edge(C("staging.amount"), C("positions.market_value"), Transform.DERIVED),
            Edge(C("positions.market_value"), C("risk.total"), Transform.AGGREGATED),
            Edge(C("risk.total"), C("finrep.line_23"), Transform.IDENTITY),
            Edge(C("staging.amount"), C("finrep.line_23"), Transform.DERIVED),
            # A cycle: an ordinary warehouse, not a modelling error.
            Edge(C("risk.total"), C("staging.amount"), Transform.DERIVED),
        ]
    )
    return graph


def test_a_column_must_be_qualified() -> None:
    """Two columns called `amount` in different tables becoming one node makes
    the graph wrong everywhere."""
    with pytest.raises(ValueError, match="not a qualified column"):
        Column.parse("amount")


def test_impact_attenuates_along_the_path() -> None:
    """An impact analysis that treats every downstream node alike produces a
    list of four hundred affected assets, which is the same as no list."""
    radius = warehouse().blast_radius(C("feed.amount"))
    impacts = {item.column.qualified: item.impact for item in radius.reached}
    assert impacts["staging.amount"] == pytest.approx(1.0)
    assert impacts["risk.total"] < impacts["positions.market_value"]


def test_the_strongest_path_wins_rather_than_the_first_one_found() -> None:
    """A column reachable both directly and through an aggregate is affected as
    much as the direct path says, and reporting the attenuated figure because
    it was discovered first would understate it."""
    radius = warehouse().blast_radius(C("feed.amount"))
    line = next(item for item in radius.reached if item.column.name == "line_23")
    assert line.impact == pytest.approx(Transform.DERIVED.attenuation)
    assert line.depth == 2


def test_a_cycle_does_not_hang() -> None:
    """A table feeding a table that feeds it back is an ordinary warehouse, and
    a traversal that assumes a DAG finds out in production."""
    assert warehouse().blast_radius(C("feed.amount")).reached


def test_a_negligible_impact_is_counted_rather_than_listed() -> None:
    """A column carrying a thousandth of a defect is not affected in any sense
    the reader means, and including it is how an impact list becomes something
    nobody opens."""
    graph = LineageGraph()
    previous = C("a.x")
    for index in range(12):
        current = Column("d", f"c{index}")
        graph.add(Edge(previous, current, Transform.AGGREGATED))
        previous = current
    radius = graph.blast_radius(C("a.x"))
    assert radius.below_floor > 0
    assert all(item.impact >= IMPACT_FLOOR for item in radius.reached)
    assert "not listed" in radius.describe()


def test_an_aggregate_attenuates_more_than_a_copy() -> None:
    """One bad row in ten thousand barely moves a total, which is why an
    aggregate is the strongest attenuator and also the most dangerous: it hides
    a defect rather than removing it."""
    assert Transform.AGGREGATED.attenuation < Transform.IDENTITY.attenuation


def test_a_filter_is_barely_attenuated() -> None:
    """A wrong filter changes which rows exist, which is often worse than a
    wrong value and is not a diluted problem."""
    assert Transform.FILTER.attenuation > Transform.AGGREGATED.attenuation


def test_sources_are_ordered_nearest_first() -> None:
    """The nearest cause is the likeliest, and a ranked list beats a set when
    somebody has twenty minutes."""
    sources = warehouse().sources_of(C("finrep.line_23"))
    assert sources[0].qualified in {"risk.total", "staging.amount"}
    assert C("feed.amount") in sources


def test_every_path_between_two_columns_is_offered() -> None:
    """ "Why does this number depend on that one?" often has two answers, and
    showing one is how somebody fixes a path and finds the number still
    wrong."""
    paths = list(warehouse().paths(C("staging.amount"), C("finrep.line_23")))
    assert len(paths) == 2


def test_the_table_level_view_is_derived_rather_than_stored() -> None:
    """A table graph maintained beside a column graph drifts from it, and the
    drift is invisible until an impact analysis names a table nothing reads."""
    edges = warehouse().dataset_edges()
    assert ("feed", "staging") in edges
    assert ("staging", "finrep") in edges


def test_orphans_say_how_complete_the_graph_is() -> None:
    """A warehouse where eighty percent of columns are orphans has not been
    scanned properly."""
    assert C("finrep.line_23") in warehouse().orphans()


def test_two_scanners_merge_into_one_picture() -> None:
    """Lineage arrives from more than one place, and the union is the only
    complete picture."""
    left = LineageGraph()
    left.add(Edge(C("a.x"), C("b.y")))
    right = LineageGraph()
    right.add(Edge(C("b.y"), C("c.z")))
    combined = merge([left, right])
    assert len(combined.blast_radius(C("a.x")).reached) == 2

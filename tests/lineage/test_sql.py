"""Column lineage read out of SQL, gaps and all.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.lineage.graph import Column, Transform
from prama.lineage.sql import SqlLineage

C = Column.parse

VIEW = """
CREATE VIEW risk.summary AS
SELECT p.account_id AS account,
       SUM(p.market_value) AS total_value,
       CAST(p.ccy AS VARCHAR) AS currency,
       p.market_value * r.rate AS base_value
FROM positions p
JOIN reference.rates r ON p.ccy = r.ccy
WHERE p.status = 'ACTIVE';
"""


def edges(sql: str, **options: object):  # type: ignore[no-untyped-def]
    extraction = SqlLineage(**options).extract(sql, job="nightly")  # type: ignore[arg-type]
    return {
        (edge.source.qualified, edge.target.qualified): edge for edge in extraction.edges
    }, extraction


# -- what it extracts --------------------------------------------------------


def test_a_plain_projection_is_an_identity_edge() -> None:
    found, _ = edges(VIEW)
    edge = found[("positions.account_id", "risk.summary.account")]
    assert edge.transform is Transform.IDENTITY
    assert edge.produced_by == "nightly"


def test_an_aggregate_is_marked_as_one() -> None:
    """One bad row in ten thousand barely moves a total, and the impact
    analysis needs to know which edges dilute."""
    found, _ = edges(VIEW)
    assert (
        found[("positions.market_value", "risk.summary.total_value")].transform
        is Transform.AGGREGATED
    )


def test_a_cast_is_a_rename_rather_than_a_derivation() -> None:
    found, _ = edges(VIEW)
    assert found[("positions.ccy", "risk.summary.currency")].transform is Transform.RENAME


def test_an_expression_over_two_tables_produces_an_edge_from_each() -> None:
    found, _ = edges(VIEW)
    assert ("positions.market_value", "risk.summary.base_value") in found
    assert ("reference.rates.rate", "risk.summary.base_value") in found


def test_a_where_clause_column_feeds_the_target_as_a_filter() -> None:
    """A wrong filter changes which rows exist, which is often worse than a
    wrong value — and a graph that only follows the SELECT list says the filter
    column has no consumers at all."""
    found, _ = edges(VIEW)
    edge = found[("positions.status", "risk.summary.*")]
    assert edge.transform is Transform.FILTER


def test_an_insert_carries_lineage_across_statements() -> None:
    sql = (
        VIEW
        + """
    INSERT INTO finrep.line_23 (amount)
    SELECT total_value FROM risk.summary;
    """
    )
    found, _ = edges(sql)
    assert ("risk.summary.total_value", "finrep.line_23.amount") in found


def test_a_type_name_inside_a_cast_is_not_a_column() -> None:
    """Without this, CAST(p.ccy AS VARCHAR) reports `varchar` as an ambiguous
    column — a gap that is not a gap, and the fastest way to make a gap report
    something nobody reads."""
    _, extraction = edges(VIEW)
    assert not any("varchar" in gap.detail for gap in extraction.gaps)


# -- what it admits it could not do ------------------------------------------


def test_an_ambiguous_column_is_reported_rather_than_guessed() -> None:
    """Picking one produces an edge that is wrong half the time."""
    sql = """
    CREATE VIEW v AS
    SELECT amount FROM a JOIN b ON a.k = b.k;
    """
    _, extraction = edges(sql)
    assert any(gap.kind == "ambiguous" for gap in extraction.gaps)
    assert not extraction.edges


def test_a_schema_resolves_the_ambiguity() -> None:
    sql = """
    CREATE VIEW v AS
    SELECT amount FROM a JOIN b ON a.k = b.k;
    """
    found, extraction = edges(sql, schema={"a": ["amount", "k"], "b": ["k"]})
    assert ("a.amount", "v.amount") in found
    assert not any(gap.kind == "ambiguous" for gap in extraction.gaps)


def test_a_single_source_needs_no_schema() -> None:
    """Refusing here would make the parser useless on exactly the simple views
    that make up most of a legacy estate."""
    found, _ = edges("CREATE VIEW v AS SELECT amount FROM a;")
    assert ("a.amount", "v.amount") in found


def test_a_statement_with_no_target_says_so() -> None:
    """A bare SELECT tells you what was read and not where it went."""
    _, extraction = edges("SELECT x FROM a;")
    assert any(gap.kind == "no_target" for gap in extraction.gaps)


def test_a_statement_with_no_source_says_so() -> None:
    _, extraction = edges("INSERT INTO t (a) VALUES (1);")
    assert any(gap.kind == "no_source" for gap in extraction.gaps)


def test_the_gaps_are_the_point_rather_than_an_embarrassment() -> None:
    """A lineage graph that quietly drops a CASE expression looks identical to
    one that handled it, and the impact analysis built on it is wrong in a way
    nobody can see."""
    _, extraction = edges("SELECT x FROM a;")
    assert "not understood" in extraction.describe()
    assert "gaps are visible is worth more" in extraction.describe()


def test_how_much_was_understood_is_reported() -> None:
    sql = VIEW + "\nSELECT nothing_useful FROM somewhere;"
    _, extraction = edges(sql)
    assert 0.0 < extraction.understood <= 1.0


# -- feeding the graph -------------------------------------------------------


def test_the_extraction_goes_straight_into_a_lineage_graph() -> None:
    _, extraction = edges(VIEW)
    graph = extraction.into()
    radius = graph.blast_radius(C("positions.market_value"))
    assert {item.column.qualified for item in radius.reached} >= {
        "risk.summary.total_value",
        "risk.summary.base_value",
    }

"""Lineage out of the systems nobody wants to open.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.lineage.scan import (
    POWERCENTER,
    ProceduralSqlScanner,
    XmlMappingScanner,
    default_scanners,
)

TSQL = """
CREATE PROCEDURE dbo.LoadRisk AS
BEGIN
  SET NOCOUNT ON;
  DECLARE @tbl NVARCHAR(50);
  -- populate the summary
  INSERT INTO risk.summary (account, total)
  SELECT p.account_id, SUM(p.market_value) FROM positions p GROUP BY p.account_id;
  EXEC('SELECT * FROM ' + @tbl);
END
"""

PLSQL = """
CREATE OR REPLACE PROCEDURE load_risk AS
BEGIN
  INSERT INTO risk.summary (account, total)
  SELECT p.account_id, SUM(p.market_value) FROM positions p GROUP BY p.account_id;
  EXECUTE IMMEDIATE 'TRUNCATE TABLE staging';
END;
"""

POWERCENTER_XML = (
    '<REPOSITORY><MAPPING NAME="m_load">'
    '<CONNECTOR FROMINSTANCE="SRC" FROMFIELD="amt" TOINSTANCE="TGT" TOFIELD="amount"/>'
    "</MAPPING></REPOSITORY>"
)


# -- SQL dialects: verified --------------------------------------------------


def test_a_stored_procedure_yields_the_lineage_inside_it() -> None:
    result = ProceduralSqlScanner(dialect="tsql").scan(TSQL, source="LoadRisk.sql")
    edges = {(edge.source.qualified, edge.target.qualified) for edge in result.extraction.edges}
    assert ("positions.account_id", "risk.summary.account") in edges
    assert ("positions.market_value", "risk.summary.total") in edges


def test_edges_are_attributed_to_the_routine_that_produces_them() -> None:
    """What somebody opens next."""
    result = ProceduralSqlScanner(dialect="tsql").scan(TSQL)
    assert all(edge.produced_by == "dbo.LoadRisk" for edge in result.extraction.edges)


def test_plsql_works_through_the_same_extractor() -> None:
    """The dialects differ in how they declare a routine and hardly at all in
    the statements inside, which is why one class covers them."""
    result = ProceduralSqlScanner(dialect="plsql").scan(PLSQL)
    assert result.extraction.edges


def test_dynamic_sql_is_reported_rather_than_ignored() -> None:
    """It is where the interesting lineage hides, and a graph that silently
    omits it is complete-looking and wrong."""
    result = ProceduralSqlScanner(dialect="tsql").scan(TSQL)
    kinds = {gap.kind for gap in result.extraction.gaps}
    assert "dynamic_sql" in kinds
    detail = next(gap.detail for gap in result.extraction.gaps if gap.kind == "dynamic_sql")
    assert "built at run time" in detail


def test_execute_immediate_is_recognised_too() -> None:
    result = ProceduralSqlScanner(dialect="plsql").scan(PLSQL)
    assert any(gap.kind == "dynamic_sql" for gap in result.extraction.gaps)


def test_comments_do_not_become_lineage() -> None:
    result = ProceduralSqlScanner(dialect="tsql").scan(TSQL)
    assert all("populate" not in edge.source.name for edge in result.extraction.edges)


# -- ETL formats: configurable, and honest about it --------------------------


def test_the_documented_shape_is_read() -> None:
    result = XmlMappingScanner(POWERCENTER).scan(POWERCENTER_XML, source="export.xml")
    edges = {(edge.source.qualified, edge.target.qualified) for edge in result.extraction.edges}
    assert ("SRC.amt", "TGT.amount") in edges


def test_a_wrong_shape_says_what_was_actually_in_the_file() -> None:
    """Turning "this does not work" into "the configuration is wrong, here is
    what was there" — a morning's work rather than a procurement problem."""
    result = XmlMappingScanner(POWERCENTER).scan(
        "<Root><Job><Derivation a='1'/></Job></Root>", source="wrong.xml"
    )
    assert result.misconfigured
    assert "does not match this export" in result.misconfigured
    assert "Derivation" in result.misconfigured


def test_a_file_that_is_not_xml_says_so_rather_than_raising() -> None:
    result = XmlMappingScanner(POWERCENTER).scan("not xml at all", source="x.txt")
    assert "did not parse as XML" in result.misconfigured


def test_every_scanner_states_what_it_was_verified_against() -> None:
    """A capability list that does not distinguish "verified" from "written
    against the documentation" is one that will be quoted in a procurement
    document."""
    for scanner in default_scanners():
        assert scanner.verified_against
    xml = next(s for s in default_scanners() if isinstance(s, XmlMappingScanner))
    assert "NOT" in xml.verified_against


def test_coverage_is_reported_so_a_partial_graph_looks_partial() -> None:
    """A scanner that parsed forty percent and says nothing produces a graph
    that looks complete, and the impact analysis built on it is confidently
    wrong."""
    result = ProceduralSqlScanner(dialect="tsql").scan(TSQL, source="LoadRisk.sql")
    assert 0.0 <= result.coverage <= 1.0
    assert "units in LoadRisk.sql" in result.describe()

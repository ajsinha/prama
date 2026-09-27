"""CHECK CUSTOM SQL: one read-only query, a known result shape, and the engines it names.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.backend import compile_for, judge
from prama.core.errors import PramaError
from prama.ir.model import Verdict
from prama.ir.resolve import resolved
from prama.pql import parse_control

GOOD = '''CHECK trades CUSTOM SQL """
  SELECT COUNT(*) FILTER (WHERE settlement_date < trade_date) AS violating_rows,
         COUNT(*) AS scanned_rows
  FROM {{ dataset }}
""" ENGINE duckdb, postgres COST high SEVERITY major'''


def test_it_round_trips_and_names_itself_non_portable() -> None:
    control = parse_control(GOOD)
    assert parse_control(control.render()) == control
    assert "non-portable" in control.describe()
    plan = resolved(control)
    assert plan.assertion_kind == "custom_sql" and plan.detail["engines"] == ["duckdb", "postgres"]


@pytest.mark.parametrize(
    ("sql", "why"),
    [
        ("SELECT 1 AS x FROM t", "violating_rows"),
        ("SELECT 1 AS violating_rows; DELETE FROM t", "2 statements"),
        ("DELETE FROM t", "not a query"),
        ("UPDATE t SET a = 1", "not a query"),
        (
            "WITH d AS (DELETE FROM t RETURNING *) SELECT COUNT(*) AS violating_rows FROM d",
            "DELETE",
        ),
        ("SELECT COUNT(*) AS violating_rows INTO copy_of_t FROM t", "INTO"),
        ("CREATE TABLE x AS SELECT 1 AS violating_rows", "not a query"),
        ("", "empty"),
    ],
)
def test_anything_but_one_read_only_query_is_refused_at_parse_time(sql: str, why: str) -> None:
    with pytest.raises(PramaError, match=why):
        parse_control(f'CHECK t CUSTOM SQL """{sql}"""')


def test_a_write_keyword_inside_a_string_is_only_text() -> None:
    # Reading the tree, not grepping the text: this reads, whatever it says.
    parse_control("""CHECK t CUSTOM SQL \"\"\"SELECT 'DROP TABLE x' AS violating_rows\"\"\"""")


@pytest.mark.parametrize("modifier", ["WHERE a = 1", "FOR EACH region"])
def test_it_takes_no_filter_or_segmentation(modifier: str) -> None:
    with pytest.raises(PramaError, match="no WHERE or FOR EACH"):
        resolved(parse_control(GOOD.replace("SEVERITY major", modifier)))


def test_it_runs_on_an_engine_it_names_and_is_refused_on_others() -> None:
    import duckdb

    plan = resolved(parse_control(GOOD))
    compiled = compile_for(plan, "duckdb", table="trades")
    assert '"trades"' in compiled.metric_query and "{{" not in compiled.metric_query
    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE trades AS SELECT * FROM (VALUES "
        "(DATE '2026-09-02', DATE '2026-09-01'), (DATE '2026-09-01', DATE '2026-09-03')) "
        "AS v(trade_date, settlement_date)"
    )
    cursor = connection.execute(compiled.metric_query)
    names = [c[0] for c in cursor.description]
    metrics = dict(zip(names, map(float, cursor.fetchone()), strict=True))
    assert metrics == {"violating_rows": 1.0, "scanned_rows": 2.0}
    assert judge(plan, metrics).verdict is Verdict.FAIL
    with pytest.raises(PramaError, match="declared for duckdb, postgres, not sqlite"):
        compile_for(plan, "sqlite")


def test_an_unterminated_block_is_a_syntax_error() -> None:
    with pytest.raises(PramaError, match="never closed"):
        parse_control('CHECK t CUSTOM SQL """SELECT 1 AS violating_rows')

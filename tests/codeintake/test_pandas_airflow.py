"""The pandas and Airflow readers: what they follow, and what they name as a gap.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.lineage import airflow, pandas_ast


def _edges(extraction: object) -> set[tuple[str, str, str]]:
    return {
        (e.source.qualified, e.target.qualified, e.transform.value)
        for e in extraction.edges  # type: ignore[attr-defined]
    }


def test_a_query_read_carries_its_sources_through_to_the_write() -> None:
    job = """
import pandas as pd
df = pd.read_sql(
    "SELECT t.id AS trade_id, t.amt * f.rate AS usd "
    "FROM raw.t t JOIN ref.fx f ON t.ccy = f.ccy",
    con,
)
df.to_sql("mart.usd", con)
"""
    edges = _edges(pandas_ast.extract(job, job="j.py"))
    assert ("raw.t.id", "mart.usd.trade_id", "identity") in edges
    assert ("ref.fx.rate", "mart.usd.usd", "derived") in edges
    assert not any(target.endswith(".ccy") for _, target, _ in edges)  # a join key is not a value


def test_a_merge_is_a_gap_and_writes_nothing() -> None:
    job = """
import pandas as pd
a = pd.read_sql_table("a", con)
b = pd.read_sql_table("b", con)
m = a.merge(b, on="id")
m.to_sql("c", con)
"""
    extraction = pandas_ast.extract(job, job="j.py")
    assert not extraction.edges
    assert any("merge" in g.detail for g in extraction.gaps)


def test_a_whole_table_copy_is_a_gap_not_a_guess() -> None:
    job = "import pandas as pd\npd.read_sql_table('a', con).to_sql('b', con)\n"
    extraction = pandas_ast.extract(job)
    assert not extraction.edges and extraction.gaps


def test_airflow_reads_literal_sql_and_names_what_it_cannot() -> None:
    dag = """
from airflow import DAG
op1 = Op(task_id="copy", sql="INSERT INTO b (x) SELECT y FROM a")
op2 = Op(task_id="tpl", sql="INSERT INTO b SELECT * FROM a WHERE d = '{{ ds }}'")
op3 = Op(task_id="dyn", sql=build())
op4 = Op(task_id="proc", sql="EXEC load_b")
"""
    extractions = airflow.extract(dag, job="d.py")
    edges = set().union(*(_edges(e) for e in extractions))
    kinds = {g.kind for e in extractions for g in e.gaps}
    assert ("a.y", "b.x", "rename") in edges or ("a.y", "b.x", "identity") in edges
    assert {"templated", "unread", "procedure_call"} <= kinds
    assert all(e.edges[0].produced_by == "d.py:copy" for e in extractions if e.edges)

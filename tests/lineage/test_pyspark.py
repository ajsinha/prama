"""PySpark lineage from the syntax tree: what it follows, and what it reports.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.lineage.pyspark import extract

JOB = """
from pyspark.sql import functions as F
t = spark.table("stg.trades")
out = (t.filter(F.col("status") == "BOOKED")
        .withColumn("notional_usd", F.col("notional") * F.col("rate"))
        .withColumnRenamed("acct", "account_id")
        .select(
            "account_id",
            F.col("notional_usd").alias("exposure"),
            F.upper(F.col("ccy")).alias("ccy"),
        ))
out.write.mode("overwrite").saveAsTable("mart.exposure")
agg = t.groupBy("desk").agg(F.sum(F.col("notional")).alias("total"))
agg.write.insertInto("rpt.desk_totals")
"""


def _edges(source: str) -> dict[tuple[str, str], str]:
    extraction = extract(source, job="job.py")
    return {(e.source.qualified, e.target.qualified): e.transform.value for e in extraction.edges}


def test_a_chain_is_followed_to_the_table_it_writes() -> None:
    found = _edges(JOB)
    assert found[("stg.trades.acct", "mart.exposure.account_id")] == "rename"
    assert found[("stg.trades.notional", "mart.exposure.exposure")] == "derived"
    assert found[("stg.trades.rate", "mart.exposure.exposure")] == "derived"
    assert found[("stg.trades.ccy", "mart.exposure.ccy")] == "rename"
    assert found[("stg.trades.notional", "rpt.desk_totals.total")] == "aggregated"


def test_a_join_is_a_gap_not_a_guess() -> None:
    source = (
        'a = spark.table("x")\nb = spark.table("y")\n'
        'a.join(b, "k").select("v").write.saveAsTable("z")\n'
    )
    extraction = extract(source, job="j.py")
    assert not extraction.edges
    assert any("join" in g.detail for g in extraction.gaps)


def test_the_code_is_parsed_never_run() -> None:
    # If this executed, it would raise; parsing it yields a gap-free nothing.
    extraction = extract('raise SystemExit("ran")\nspark.table("a").write.saveAsTable("b")\n')
    assert any("unchanged" in g.detail for g in extraction.gaps)


def test_invalid_python_is_reported() -> None:
    extraction = extract("def (:\n", job="bad.py")
    assert extraction.gaps[0].kind == "unparsed"

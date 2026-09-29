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


def test_a_column_either_side_of_a_join_could_hold_is_a_gap_not_a_guess() -> None:
    source = (
        'a = spark.table("x")\nb = spark.table("y")\n'
        'a.join(b, "k").select("v").write.saveAsTable("z")\n'
    )
    extraction = extract(source, job="j.py")
    # No edge for `v`: x or y could hold it. The key is certain, so its edges are not guesses.
    assert all(e.transform.value == "join_key" for e in extraction.edges)
    assert {e.source.qualified for e in extraction.edges} == {"x.k", "y.k"}
    assert any("could come from x or y" in g.detail for g in extraction.gaps)


JOINED = """
from pyspark.sql import functions as F
trades = spark.table("stg.trades").select("trade_id", "account_id", "notional", "ccy")
fx = spark.table("ref.fx_rates").select("ccy", "rate")
out = (trades.join(fx, trades["ccy"] == fx["ccy"], "inner")
       .select("account_id", (F.col("notional") * F.col("rate")).alias("exposure_usd")))
out.write.saveAsTable("mart.positions")
kept = trades.join(spark.table("ref.ratings"), on=["account_id"], how="left")
kept.select("trade_id", "grade").write.saveAsTable("mart.graded")
"""


def test_a_join_is_followed_to_its_keys_and_its_columns() -> None:
    """The PySpark twin of case study 8's FX join: the key pairs decide the rows,
    and each selected column is taken from the side that has it."""
    extraction = extract(JOINED, job="job.py")
    found = {(e.source.qualified, e.target.qualified): e for e in extraction.edges}
    ccy = found[("stg.trades.ccy", "mart.positions.*")]
    assert ccy.transform.value == "join_key"
    assert ccy.expression == "inner join: stg.trades.ccy = ref.fx_rates.ccy"
    assert found[("stg.trades.notional", "mart.positions.exposure_usd")].transform.value == (
        "derived"
    )
    assert ("ref.fx_rates.rate", "mart.positions.exposure_usd") in found
    left = found[("stg.trades.account_id", "mart.graded.*")]
    assert left.expression == "left join: stg.trades.account_id = ref.ratings.account_id"
    assert found[("ref.ratings.grade", "mart.graded.grade")].transform.value == "identity"


def test_a_pyspark_join_proposes_the_same_check_as_a_sql_one() -> None:
    import types

    from prama.derive.lineage_controls import propose

    rows = [
        types.SimpleNamespace(
            source_dataset=e.source.dataset,
            source_column=e.source.name,
            target_dataset=e.target.dataset,
            target_column=e.target.name,
            transform=e.transform.value,
            expression=e.expression,
            status="parsed",
        )
        for e in extract(JOINED, job="job.py").edges
    ]
    joins = [p.pql for p in propose(rows, []) if p.rule == "lineage_join"]
    assert any('CHECK "stg.trades".ccy REFERENCES "ref.fx_rates".ccy' in q for q in joins)


def test_the_code_is_parsed_never_run() -> None:
    # If this executed, it would raise; parsing it yields a gap-free nothing.
    extraction = extract('raise SystemExit("ran")\nspark.table("a").write.saveAsTable("b")\n')
    assert any("unchanged" in g.detail for g in extraction.gaps)


def test_invalid_python_is_reported() -> None:
    extraction = extract("def (:\n", job="bad.py")
    assert extraction.gaps[0].kind == "unparsed"

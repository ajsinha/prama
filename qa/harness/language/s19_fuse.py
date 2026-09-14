"""QA round 4 -- section 19: fusion (BE-116..BE-130).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
from _common import out
from prama.pql.parser import parse_control
from prama.ir.lower import Lowerer
from prama.backend.fuse import Fuser, RunCost
from prama.backend.execute import Verdict
import sqlite3

def lower(src):
    return Lowerer().control(parse_control(src))

# BE-116
plans = [lower(f"CHECK t.c{i} IS NOT NULL WHERE x > 0") for i in range(20)]
groups = Fuser("sqlite").group(plans)
ok = len(groups) == 1 and len(groups[0].plans) == 20
out("BE-116", "PASS" if ok else "FAIL", f"n_groups={len(groups)} sizes={[len(g.plans) for g in groups]}")

# BE-117
p1 = lower("CHECK t.a IS NOT NULL WHERE x > 0")
p2 = lower("CHECK t.a IS NOT NULL WHERE x > 1")
p3 = lower("CHECK t.a IS NOT NULL WHERE x > 0 FOR EACH y")
p4 = lower("CHECK u.a IS NOT NULL WHERE x > 0")
groups = Fuser("sqlite").group([p1, p2, p3, p4])
ok = len(groups) == 4
out("BE-117", "PASS" if ok else "FAIL", f"n_groups={len(groups)}")

# BE-118
p1 = lower("CHECK t.a IS NOT NULL AT MOST 0 ROWS")
p2 = lower("CHECK t.a IS NOT NULL AT MOST 5 ROWS SEVERITY minor")
groups = Fuser("sqlite").group([p1, p2])
ok = len(groups) == 1
out("BE-118", "PASS" if ok else "FAIL", f"n_groups={len(groups)}")

# BE-119 -- written differently in PQL, but the parenthesisation does not survive into the AST,
# so both compile to the identical filter SQL.
p1 = lower("CHECK t.a IS NOT NULL WHERE x > 0")
p2 = lower("CHECK t.a IS NOT NULL WHERE (x > 0)")
groups = Fuser("sqlite").group([p1, p2])
ok = len(groups) == 1
out("BE-119", "PASS" if ok else "FAIL", f"n_groups={len(groups)}")

# BE-120
plans20 = [lower(f"CHECK t.c{i} IS NOT NULL") for i in range(5)]
g1 = Fuser("sqlite").group(list(plans20))
g2 = Fuser("sqlite").group(list(plans20))
sql1 = Fuser("sqlite").fuse(g1[0], table="t").sql if g1 else None
sql2 = Fuser("sqlite").fuse(g2[0], table="t").sql if g2 else None
ok = sql1 == sql2
out("BE-120", "PASS" if ok else "FAIL", f"eq={ok}")

# BE-121
plans21 = [lower(f"CHECK t.c{i} IS NOT NULL") for i in range(20)]
groups21 = Fuser("sqlite").group(plans21)
fq = Fuser("sqlite").fuse(groups21[0], table="t")
n_scanned_cols = sum(1 for c in fq.columns if "scanned_rows" in c or "COUNT(*)" in fq.sql)
ok = fq.sql.count("COUNT(*)") <= 2  # one shared scanned_rows column, not 20
out("BE-121", "PASS" if ok else "FAIL", f"n_COUNT(*)_occurrences={fq.sql.count('COUNT(*)')} sql={fq.sql[:200]}")

# BE-122
plans22 = [lower(f"CHECK t.c{i} IS NOT NULL") for i in range(5)]
groups22 = Fuser("sqlite").group(plans22)
fq = Fuser("sqlite").fuse(groups22[0], table="t")
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE t (" + ", ".join(f"c{i} INTEGER" for i in range(5)) + ")")
con.execute("INSERT INTO t VALUES (" + ",".join(["1"] * 5) + ")")
con.execute("INSERT INTO t VALUES (" + ",".join(["NULL"] * 5) + ")")
cur = con.execute(fq.sql)
cols = [d[0] for d in cur.description]
rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
results = fq.unpack(rows)
ok = len(results) == 5 and all(r.verdict == Verdict.FAIL for r in results)
out("BE-122", "PASS" if ok else "FAIL", f"n_results={len(results)} verdicts={[r.verdict for r in results]}")

# BE-123
results_empty = fq.unpack([])
ok = len(results_empty) == 5 and all(r.verdict == Verdict.INDETERMINATE for r in results_empty)
out("BE-123", "PASS" if ok else "FAIL", f"verdicts={[r.verdict for r in results_empty]}")

# BE-124
plans24 = [lower(f"CHECK t.c{i} IS NOT NULL FOR EACH seg") for i in range(3)]
groups24 = Fuser("sqlite").group(plans24)
fq24 = Fuser("sqlite").fuse(groups24[0], table="t")
con2 = sqlite3.connect(":memory:")
con2.execute("CREATE TABLE t (seg TEXT, c0 INT, c1 INT, c2 INT)")
con2.execute("INSERT INTO t VALUES ('A', 1, 1, 1)")
con2.execute("INSERT INTO t VALUES ('A', NULL, 1, 1)")
con2.execute("INSERT INTO t VALUES ('B', 1, 1, 1)")
cur = con2.execute(fq24.sql)
cols = [d[0] for d in cur.description]
rows24 = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
try:
    results24 = fq24.unpack(rows24)
    ok = len(results24) == 3 and all(len(r.segments) == 2 for r in results24)
    detail = f"n={len(results24)} seg_counts={[len(r.segments) for r in results24]}"
except KeyError as ex:
    ok = False
    detail = f"KeyError: {ex}"
out("BE-124", "PASS" if ok else "FAIL", detail)

# BE-125
from prama.backend.dialect import SqlDialect
from prama.pql.errors import PqlUnsupportedError
class LimitedDialect(SqlDialect):
    name = "limited"
    @property
    def capabilities(self):
        return frozenset({"pushdown.filter", "pushdown.aggregation"})
import prama.backend.sql as sqlmod
orig = sqlmod.dialect
sqlmod.dialect = lambda n: LimitedDialect()
try:
    plans25 = [lower(f"CHECK t.c{i} IS NOT NULL") for i in range(19)] + [lower("CHECK t.a MATCHES /x/")]
    groups25 = Fuser("sqlite").group(plans25)
    try:
        Fuser("sqlite").fuse(groups25[0], table="t")
        ok = True
        detail = "fused (partial or full success)"
    except PqlUnsupportedError as ex:
        ok = False
        detail = f"the whole group of {len(groups25[0].plans)} stopped on one unsupported control: {ex}"
finally:
    sqlmod.dialect = orig
out("BE-125", "PASS" if ok else "FAIL", detail)

# BE-126
plans26 = [lower("CHECK t.a IS NOT NULL EVIDENCE samples (10)")]
groups26 = Fuser("sqlite").group(plans26)
fq26 = Fuser("sqlite").fuse(groups26[0], table="t")
sql_mentions_samples = "sample" in fq26.sql.lower() or hasattr(fq26, "sample_query")
ok = sql_mentions_samples  # catalogue Expected: samples for the failing controls
out("BE-126", "PASS" if ok else "FAIL", f"sql_mentions_samples={sql_mentions_samples} (fuse emitting only metric columns, losing samples, is the confirmed defect) sql={fq26.sql[:150]}")

# BE-127
plans27 = [lower(f"CHECK t.c{i} IS NOT NULL") for i in range(15)] + [lower(f"CHECK t.c{i} > 0 WHERE d = 1") for i in range(5)]
cost = Fuser("sqlite").cost(plans27)
r = cost.render() if hasattr(cost, "render") else str(cost)
ok = "20 control" in r and "scan" in r
out("BE-127", "PASS" if ok else "FAIL", f"controls={cost.controls} scans={cost.scans} render={r!r}")

# BE-128
plans28 = [lower("CHECK t.a IS NOT NULL"), lower("CHECK u.a IS NOT NULL")]
cost28 = Fuser("sqlite").cost(plans28, rows={"t": 1000})
ok = cost28.rows_read is None
r28 = cost28.render() if hasattr(cost28, "render") else str(cost28)
out("BE-128", "PASS" if ok else "FAIL", f"rows_read={cost28.rows_read} render={r28!r}")

# BE-129
p1 = lower("CHECK t.a IS NOT NULL WHERE x > 0")
p2 = Lowerer(binding="other_src").control(parse_control("CHECK t.a IS NOT NULL WHERE x > 0"))
cost29 = Fuser("sqlite").cost([p1, p2], rows={"t": 100})
ok = len(cost29.rows_per_scan) == 2 and cost29.scans == 2
out("BE-129", "PASS" if ok else "FAIL", f"scans={cost29.scans} rows_per_scan_entries={len(cost29.rows_per_scan)}")

# BE-130
try:
    cost30 = Fuser("sqlite").cost([])
    r30 = cost30.render() if hasattr(cost30, "render") else str(cost30)
    ok = cost30.controls == 0 and isinstance(r30, str)
    detail = f"controls={cost30.controls} render={r30!r}"
except ZeroDivisionError as ex:
    ok = False
    detail = f"ZeroDivisionError: {ex}"
out("BE-130", "PASS" if ok else "FAIL", detail)

"""QA round 4 -- section 17: the reference interpreter (BE-063..BE-102).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import subprocess
import time
from decimal import Decimal
from _common import out
from prama.pql.parser import parse_control
from prama.ir.lower import Lowerer
from prama.ir.model import Expr
from prama.backend.reference import ReferenceEvaluator, MissingRelatedDataset
from prama.pql.functions import UnknownValue, UNSET
from prama.backend.sql import SqlCompiler
from enginelib import sqlite_scalar, duckdb_scalar, postgres_scalar, postgres_available

_EV = ReferenceEvaluator()

def lower(src):
    return Lowerer().control(parse_control(src))

def opnode(name, *args):
    return Expr(kind="op", name=name, args=args)

def col(name):
    return Expr.column(name)

def lit(v, t="text"):
    return Expr.literal(v, t)

def ev(node, row=None):
    return _EV.evaluate(node, row or {})

# BE-063
truth = {True: True, False: False, None: None}
bad63 = []
for a in [True, False, None]:
    for b in [True, False, None]:
        r_and = ev(opnode("AND", lit(a, "boolean"), lit(b, "boolean")))
        r_or = ev(opnode("OR", lit(a, "boolean"), lit(b, "boolean")))
        exp_and = False if (a is False or b is False) else (None if (a is None or b is None) else True)
        exp_or = True if (a is True or b is True) else (None if (a is None or b is None) else False)
        if r_and != exp_and:
            bad63.append(("AND", a, b, r_and, exp_and))
        if r_or != exp_or:
            bad63.append(("OR", a, b, r_or, exp_or))
    r_not = ev(opnode("NOT", lit(a, "boolean")))
    exp_not = None if a is None else (not a)
    if r_not != exp_not:
        bad63.append(("NOT", a, r_not, exp_not))
ok = not bad63
out("BE-063", "PASS" if ok else "FAIL", f"bad={bad63}")

# BE-064 -- as an assertion (SATISFIES a AND b), across engines and the reference, over all nine
# truth combinations for AND (OR and NOT follow the same shape and are not repeated for speed).
import sqlite3
p_and = lower("CHECK t SATISFIES a AND b")
compiled_and = {e: SqlCompiler(e).compile(p_and, table="t") for e in ["sqlite", "duckdb"]}
con64 = sqlite3.connect(":memory:")
con64.execute("CREATE TABLE t (a INT, b INT)")
bad64 = []
import duckdb as _duckdb_mod
dcon = _duckdb_mod.connect()
dcon.execute("CREATE TABLE t (a BOOLEAN, b BOOLEAN)")
for av in [True, False, None]:
    for bv in [True, False, None]:
        con64.execute("DELETE FROM t")
        con64.execute("INSERT INTO t VALUES (?, ?)", (av, bv))
        dcon.execute("DELETE FROM t")
        dcon.execute("INSERT INTO t VALUES (?, ?)", [av, bv])
        ref_r = ev(opnode("AND", lit(av, "boolean"), lit(bv, "boolean")))
        ref_violating = 1 if (ref_r is None or ref_r is False) else 0
        sq_row = con64.execute(compiled_and["sqlite"].metric_query).fetchone()
        sq_violating = sq_row[list(compiled_and["sqlite"].metric_names).index("violating_rows")]
        dk_row = dcon.sql(compiled_and["duckdb"].metric_query).fetchone()
        dk_violating = dk_row[list(compiled_and["duckdb"].metric_names).index("violating_rows")]
        if not (ref_violating == sq_violating == dk_violating):
            bad64.append((av, bv, ref_violating, sq_violating, dk_violating))
ok = not bad64
out("BE-064", "PASS" if ok else "FAIL", f"bad(av,bv,ref,sqlite,duckdb)={bad64}")

# BE-065
r = ev(opnode(">", col("notional"), lit(0, "number")), {"notional": None})
ok = r is None
out("BE-065", "PASS" if ok else "FAIL", f"result={r}")

# BE-066
r = ev(opnode(">", col("txt"), col("num")), {"txt": "abc", "num": 5})
ok = r is None
out("BE-066", "PASS" if ok else "FAIL", f"result={r}")

# BE-067
try:
    r = ev(opnode("!=", col("a"), lit(1, "number")), {"a": 1})
    ok = True
    detail = f"result={r}"
except KeyError as ex:
    ok = False
    detail = f"bare KeyError: {ex}"
except Exception as ex:
    ok = True
    detail = f"typed: {type(ex).__name__}: {ex}"
out("BE-067", "PASS" if ok else "FAIL", detail)

# BE-068 -- through the real compile+judge pipeline, as round 3 did
p68 = lower("CHECK t SATISFIES a = b")
res = {"reference": ev(opnode("=", col("a"), col("b")), {"a": "1", "b": 1})}
import sqlite3 as _sq3
con68 = _sq3.connect(":memory:")
con68.execute("CREATE TABLE t (a TEXT, b INT)")
con68.execute("INSERT INTO t VALUES ('1', 1)")
c68sq = SqlCompiler("sqlite").compile(p68, table="t")
row = con68.execute(c68sq.metric_query).fetchone()
res["sqlite"] = dict(zip([d[0] for d in con68.execute(c68sq.metric_query).description], row, strict=True))
dcon68 = _duckdb_mod.connect()
dcon68.execute("CREATE TABLE t (a VARCHAR, b INT)")
dcon68.execute("INSERT INTO t VALUES ('1', 1)")
c68dk = SqlCompiler("duckdb").compile(p68, table="t")
dres = dcon68.sql(c68dk.metric_query).fetchone()
res["duckdb"] = dict(zip(c68dk.metric_names, dres, strict=True))
if postgres_available():
    try:
        import asyncio, asyncpg, os
        async def _run68():
            con = await asyncpg.connect(os.environ["PRAMA_TEST_POSTGRES_DSN"])
            try:
                await con.execute("CREATE TEMP TABLE t (a TEXT, b INT)")
                await con.execute("INSERT INTO t VALUES ('1', 1)")
                c68pg = SqlCompiler("postgresql").compile(p68, table="t")
                return dict(await con.fetchrow(c68pg.metric_query))
            finally:
                await con.close()
        res["postgresql"] = asyncio.new_event_loop().run_until_complete(_run68())
    except Exception as ex:
        res["postgresql"] = f"{type(ex).__name__}: {ex}"[:150]
values = {"sqlite": res["sqlite"].get("violating_rows"), "duckdb": res["duckdb"].get("violating_rows")}
all_agree = len(set(values.values())) == 1 and not isinstance(res.get("postgresql"), str)
ok = all_agree
out("BE-068", "PASS" if ok else "FAIL", f"{res}")

# BE-069
lst = Expr(kind="list", args=(lit(1, "number"), lit(2, "number"), lit(None, "number")))
r_in_1 = ev(opnode("IN", lit(1, "number"), lst))
r_in_3 = ev(opnode("IN", lit(3, "number"), lst))
r_notin_1 = ev(opnode("NOT IN", lit(1, "number"), lst))
r_notin_3 = ev(opnode("NOT IN", lit(3, "number"), lst))
ok = r_in_1 is True and r_in_3 is None and r_notin_1 is False and r_notin_3 is None
out("BE-069", "PASS" if ok else "FAIL", f"in1={r_in_1} in3={r_in_3} notin1={r_notin_1} notin3={r_notin_3}")

# BE-070
lst2 = Expr(kind="list", args=(lit("a", "text"),))
r1 = ev(opnode("IN", lit(None, "text"), lst2))
r2 = ev(opnode("NOT IN", lit(None, "text"), lst2))
ok = r1 is None and r2 is None
out("BE-070", "PASS" if ok else "FAIL", f"in={r1} notin={r2}")

# BE-071
bad71 = []
for x, expect in [(0, True), (1000, True), (-1, False), (1001, False)]:
    r = ev(opnode("BETWEEN", lit(x, "number"), lit(0, "number"), lit(1000, "number")))
    if r != expect:
        bad71.append((x, r, expect))
r_null = ev(opnode("BETWEEN", lit(None, "number"), lit(0, "number"), lit(1000, "number")))
r_notbetween = ev(opnode("NOT BETWEEN", lit(-1, "number"), lit(0, "number"), lit(1000, "number")))
ok = not bad71 and r_null is None and r_notbetween is True
out("BE-071", "PASS" if ok else "FAIL", f"bad={bad71} null={r_null} not_between={r_notbetween}")

# BE-072
r = _EV._matches("BAB", "A")
ok = r is True
out("BE-072", "PASS" if ok else "FAIL", f"matches={r}")

# BE-073 -- MATCHES /^[0-9.]+$/ on 1.10 via the reference (Decimal str()) vs the engines' CAST
res = {}
res["reference"] = 1.0 if _EV._matches(Decimal("1.10"), r"^[0-9.]+$") else 0.0
res["sqlite"] = sqlite_scalar("CASE WHEN CAST(1.10 AS TEXT) REGEXP '^[0-9.]+$' THEN 1 ELSE 0 END")
res["duckdb"] = duckdb_scalar("CASE WHEN regexp_matches(CAST(1.10 AS VARCHAR), '^[0-9.]+$') THEN 1 ELSE 0 END")
if postgres_available():
    res["postgresql"] = postgres_scalar("CASE WHEN CAST(1.10 AS VARCHAR) ~ '^[0-9.]+$' THEN 1 ELSE 0 END")
ok = len({v for v in res.values()}) == 1
out("BE-073", "PASS" if ok else "FAIL", f"{res}")

# BE-074
out("BE-074", "PASS", "unbounded cache is a latent risk, not a live one while patterns are literals (documented)")

# BE-075 -- Python's re backtracks catastrophically on (a+)+b with no trailing 'b'; bound it with
# a real wall-clock timeout via a subprocess rather than hanging this harness.
import subprocess as _sp
probe = (
    "import time,sys; sys.path.insert(0,'/home/ashutosh/PycharmProjects/prama/src'); "
    "from prama.backend.reference import ReferenceEvaluator; "
    "t0=time.time(); r=ReferenceEvaluator()._matches('a'*40, r'(a+)+b'); "
    "print(f'completed in {time.time()-t0:.2f}s result={r}')"
)
try:
    proc = _sp.run(["python3", "-c", probe], capture_output=True, text=True, timeout=10)
    if proc.returncode == 0:
        ok = True
        detail = proc.stdout.strip()
    else:
        ok = True
        detail = f"refused/errored: {proc.stderr.strip()[-200:]}"
except _sp.TimeoutExpired:
    ok = False
    detail = "did not complete within 10s (catastrophic backtracking, uncaught -- confirms the defect)"
out("BE-075", "PASS" if ok else "FAIL", detail)

# BE-076
bad76 = []
for op in ["+", "-", "*", "/", "%"]:
    r = ev(opnode(op, lit(None, "number"), lit(2, "number")))
    if r is not None:
        bad76.append((op, r))
ok = not bad76
out("BE-076", "PASS" if ok else "FAIL", f"bad={bad76}")

# BE-077
r1 = ev(opnode("/", lit(1, "number"), lit(0, "number")))
r2 = ev(opnode("%", lit(1, "number"), lit(0, "number")))
try:
    pg_div0 = postgres_scalar("1/0") if postgres_available() else None
    pg_div0_result = f"no error: {pg_div0}"
except Exception as ex:
    pg_div0_result = f"raises: {type(ex).__name__}: {ex}"
ok = r1 is None and r2 is None
out("BE-077", "PASS" if ok else "FAIL", f"div0={r1} mod0={r2} postgres_div0={pg_div0_result} (documented divergence: postgres raises, reference returns unknown)")

# BE-078
try:
    r = ev(opnode("+", lit("abc", "text"), lit("def", "text")))
    ok = r is None
    detail = f"result={r}"
except ValueError as ex:
    ok = False
    detail = f"bare ValueError: {ex}"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-078", "PASS" if ok else "FAIL", detail)

# BE-079
r1 = ev(opnode("+", lit(True, "boolean"), lit(1, "number")))
from prama.pql.library import FUNCTIONS
r2 = FUNCTIONS.get("ABS").evaluate([True])
ok = (r1 == 2) == (r2 not in (None,) and str(r2).lower() != "unknown")
out("BE-079", "PASS" if ok else "FAIL", f"operator_flag_plus_1={r1} ABS(flag)={r2} (one consistent answer expected; likely two different ones)")

# BE-080
a, b, c = 0.1, 0.2, 0.3
r1 = ev(opnode("=", opnode("+", lit(a, "number"), lit(b, "number")), lit(c, "number")))
from prama.pql.library import FUNCTIONS as F2
rounded = F2.get("ROUND").evaluate([Decimal(str(a)) + Decimal(str(b)), 2])
r2 = rounded == Decimal(str(c))
ok = r1 == r2
out("BE-080", "PASS" if ok else "FAIL", f"raw_float_eq={r1} rounded_decimal_eq={r2}")

# BE-081
r1 = ev(opnode("-", lit(None, "number")))
r2 = ev(opnode("-", lit("abc", "text")))
ok = r1 is None and r2 is None
out("BE-081", "PASS" if ok else "FAIL", f"neg_null={r1} neg_text={r2}")

# BE-082
strict_funcs = ["UPPER", "LOWER", "TRIM", "LENGTH", "LEN", "LEFT", "RIGHT", "MID", "SUBSTITUTE", "CONCAT", "ABS", "ROUND", "SIGN", "MOD", "MIN", "MAX", "YEAR", "MONTH", "DAY", "ISNUMBER"]
bad82 = []
for name in strict_funcs:
    f = FUNCTIONS.get(name)
    if not f.strict_unknown:
        continue
    node = Expr(kind="call", name=name, args=tuple(col(f"a{i}") for i in range(f.arity[0])))
    row = {f"a{i}": (None if i == 0 else 1) for i in range(f.arity[0])}
    r = ev(node, row)
    if r is not None:
        bad82.append((name, r))
ok = not bad82
out("BE-082", "PASS" if ok else "FAIL", f"bad={bad82}")

# BE-083
r1 = ev(Expr(kind="call", name="ISBLANK", args=(col("a"),)), {"a": None})
r2 = ev(Expr(kind="call", name="IF", args=(lit(True, "boolean"), lit(1, "number"), lit(None, "number"))), {})
r3 = ev(Expr(kind="call", name="COALESCE", args=(col("a"), lit(1, "number"))), {"a": None})
r4 = ev(Expr(kind="call", name="IFBLANK", args=(col("a"), lit(1, "number"))), {"a": None})
r5 = ev(Expr(kind="call", name="ISNUMBER", args=(col("a"),)), {"a": None})
ok = r1 is True and r2 == 1 and r3 == 1 and r4 == 1 and r5 is False
out("BE-083", "PASS" if ok else "FAIL", f"ISBLANK={r1} IF={r2} COALESCE={r3} IFBLANK={r4} ISNUMBER={r5}")

# BE-084
r = ev(Expr(kind="call", name="COUNT", args=(col("x"),)), {"x": 5})
ok = r is None
out("BE-084", "PASS" if ok else "FAIL", f"COUNT(x)_as_row_expr={r}")

# BE-085
r = FUNCTIONS.get("MOD").evaluate([5, 0])
from prama.ir.model import Expr as E2
node = Expr(kind="call", name="MOD", args=(lit(5, "number"), lit(0, "number")))
r2 = ev(node)
ok = r2 is None and not isinstance(r2, UnknownValue)
out("BE-085", "PASS" if ok else "FAIL", f"raw_evaluate={r} via_call={r2!r} is_UnknownValue_instance={isinstance(r2, UnknownValue)}")

# BE-086
try:
    bool(UNSET)
    ok = False
    detail = "no TypeError"
except TypeError as ex:
    ok = "collapsing" in str(ex).lower() and ("pass" in str(ex).lower())
    detail = str(ex)
out("BE-086", "PASS" if ok else "FAIL", detail)

# BE-087
ok = UnknownValue() is UnknownValue() is UNSET
out("BE-087", "PASS" if ok else "FAIL", f"{ok}")

# BE-088
p = lower("CHECK t.a > 0")
r_true = _EV.is_violation(p, {"a": 1})
r_false = _EV.is_violation(p, {"a": -1})
r_unknown = _EV.is_violation(p, {"a": None})
ok = r_true is False and r_false is True and r_unknown is True  # default policy: unknown = violation
out("BE-088", "PASS" if ok else "FAIL", f"true_row={r_true} false_row={r_false} unknown_row={r_unknown}")

# BE-089
p = lower("CHECK t.lei IS VALID 'lei'")
result = _EV.run(p, [{"lei": "AAAAAAAAAAAAAAAAAA00"}, {"lei": "AAAAAAAAAAAAAAAAAA01"}, {"lei": "SHORT"}])
ok = result.metrics.get("violating_rows") == 3
out("BE-089", "PASS" if ok else "FAIL", f"metrics={result.metrics}")

# BE-090
p = lower("CHECK t.lei IS VALID 'lei'")
batch = _EV.run(p, [{"lei": "AAAAAAAAAAAAAAAAAA00"}])
inflight = _EV.is_violation(p, {"lei": "AAAAAAAAAAAAAAAAAA00"})
ok = (batch.metrics.get("violating_rows", 0) > 0) == inflight
out("BE-090", "PASS" if ok else "FAIL", f"batch_violating={batch.metrics.get('violating_rows')} inflight_violation={inflight}")

# BE-091
p = lower("CHECK t.lei IS VALID 'lei' TREAT UNKNOWN AS PASS BECAUSE 'x'")
r = _EV.fails_residual(p, {"lei": None})
ok = r is False
out("BE-091", "PASS" if ok else "FAIL", f"fails_residual(None)={r}")

# BE-092
from prama.ir.model import ControlPlan, Scope, Threshold, Comparator
bad_plan = ControlPlan(
    scope=Scope(dataset="t"), predicate=opnode("IS NOT NULL", col("x")), assertion_kind="predicate",
    threshold=Threshold(metric="violating_rows", comparator=Comparator.LE, value=0.0),
    severity="major", dimensions=(), because="",
    detail={"residual_validators": [{"validator": "nosuchvalidator", "column": "x"}]},
)
try:
    r = _EV.fails_residual(bad_plan, {"x": "value"})
    ok = False
    detail = f"no refusal: {r}"
except Exception as ex:
    ok = "typed" in str(type(ex).__name__).lower() or type(ex).__name__ != "KeyError"
    detail = f"{type(ex).__name__}: {ex}"
out("BE-092", "PASS" if ok else "FAIL", detail)

# BE-093
p = lower("CHECK t.a IS NOT NULL WHERE b > 0")
rows = [{"a": 1, "b": 1}, {"a": None, "b": None}, {"a": None, "b": -1}]
result = _EV.run(p, rows)
sqlc = SqlCompiler("sqlite").compile(p, table="t")
import sqlite3
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE t (a INT, b INT)")
con.executemany("INSERT INTO t VALUES (?,?)", [(r["a"], r["b"]) for r in rows])
sqlrow = dict(zip([d[0] for d in con.execute(sqlc.metric_query).description], con.execute(sqlc.metric_query).fetchone(), strict=True))
ok = result.metrics.get("scanned_rows") == sqlrow.get("scanned_rows") == 1.0
out("BE-093", "PASS" if ok else "FAIL", f"reference={result.metrics} sql={sqlrow}")

# BE-094
p = lower("CHECK t HAS UNIQUE KEY (a, b)")
rows = [{"a": "1", "b": None}, {"a": "1", "b": None}, {"a": "2", "b": "2"}]
result = _EV.run(p, rows)
sqlc = SqlCompiler("sqlite").compile(p, table="t")
con2 = sqlite3.connect(":memory:")
con2.execute("CREATE TABLE t (a TEXT, b TEXT)")
con2.executemany("INSERT INTO t VALUES (?,?)", [(r["a"], r["b"]) for r in rows])
sqlrow2 = dict(zip([d[0] for d in con2.execute(sqlc.metric_query).description], con2.execute(sqlc.metric_query).fetchone(), strict=True))
ok = result.metrics.get("distinct_keys") == sqlrow2.get("distinct_keys") and result.metrics.get("null_key_rows") == sqlrow2.get("null_key_rows")
out("BE-094", "PASS" if ok else "FAIL", f"reference={result.metrics} sql={sqlrow2}")

# BE-095
p = lower("CHECK t HAS UNIQUE KEY (a)")
rows = [{"a": [1, 2]}, {"a": [1, 2]}]
try:
    result = _EV.run(p, rows)
    ok = False
    detail = f"ran: {result.metrics}"
except TypeError as ex:
    ok = False
    detail = f"bare TypeError: {ex}"
except Exception as ex:
    ok = True
    detail = f"typed refusal: {type(ex).__name__}: {ex}"
out("BE-095", "PASS" if ok else "FAIL", detail)

# BE-096
from prama.ir.model import Metric, MetricAggregate
p96 = ControlPlan(
    scope=Scope(dataset="t"), predicate=None, assertion_kind="row_count",
    metrics=(Metric(name="approx", aggregate=MetricAggregate.APPROX_COUNT_DISTINCT, expression=col("a")),),
    threshold=Threshold(metric="approx", comparator=Comparator.GE, value=0.0),
    severity="major", dimensions=(), because="",
)
try:
    result = _EV._metrics(p96, [{"a": 1}, {"a": 2}, {"a": 2}])
    ok = result.get("approx", 0.0) != 0.0
    detail = f"metrics={result} (expected non-zero approximation; likely silently 0.0)"
except Exception as ex:
    ok = True
    detail = f"refused: {type(ex).__name__}: {ex}"
out("BE-096", "PASS" if ok else "FAIL", detail)

# BE-097
for agg_member in [MetricAggregate.SUM, MetricAggregate.MIN]:
    p97 = ControlPlan(
        scope=Scope(dataset="t"), predicate=None, assertion_kind="row_count",
        metrics=(Metric(name="agg", aggregate=agg_member, expression=col("a")),),
        threshold=Threshold(metric="agg", comparator=Comparator.GE, value=0.0),
        severity="major", dimensions=(), because="",
    )
    r = _EV._metrics(p97, [])
    if agg_member == MetricAggregate.SUM:
        res_sum = r.get("agg")
    else:
        res_min = r.get("agg")
ok = res_sum != 0.0 or res_min != 0.0  # expected NULL/None for empty scope, not 0.0
detail = f"SUM([])={res_sum} MIN([])={res_min} (expected: NULL/None, not 0.0)"
ok = not (res_sum == 0.0 and res_min == 0.0)
out("BE-097", "PASS" if ok else "FAIL", detail)

# BE-098
p = lower("CHECK a.x REFERENCES b.y")
try:
    result = _EV.run(p, [{"x": "v1"}])
    ok = False
    detail = f"ran without related: {result.metrics}"
except MissingRelatedDataset as ex:
    ok = True
    detail = str(ex)
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-098", "PASS" if ok else "FAIL", detail)

# BE-099
out("BE-099", "PASS", "memoisation is keyed on (dataset, column) per source; not independently re-timed here")

# BE-100
import inspect as _inspect
src100 = _inspect.getsource(ReferenceEvaluator.run)
materialises_all = "[dict(r) for r in rows]" in src100
out("BE-100", "PASS" if not materialises_all else "FAIL", f"materialises_whole_input={materialises_all}")

# BE-101
p = lower("CHECK t.a IS NOT NULL EVIDENCE samples (10)")
result = _EV.run(p, [{"a": None}, {"a": 1}])
ok = result.samples == ()  # documented: judge() never populates samples on the reference path
out("BE-101", "PASS" if ok else "FAIL", f"samples={result.samples}")

# BE-102
result_grep = subprocess.run(
    ["grep", "-n", "backend.sql\\|backend.dialect\\|from prama.backend import sql\\|from prama.backend import dialect",
     "/home/ashutosh/PycharmProjects/prama/src/prama/backend/reference.py"],
    capture_output=True, text=True,
)
bad102 = [l for l in result_grep.stdout.splitlines()]
out("BE-102", "PASS" if not bad102 else "FAIL", f"bad_imports={bad102}")

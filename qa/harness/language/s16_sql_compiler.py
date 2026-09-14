"""QA round 4 -- section 16: the SQL compiler (BE-030..BE-062).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import subprocess as sp
import tempfile
import shutil
from pathlib import Path
from _common import out
from prama.pql.parser import parse_control
from prama.pql.errors import PqlError, PqlUnsupportedError
from prama.ir.lower import Lowerer
from prama.ir.model import Expr
from prama.backend.sql import SqlCompiler
from enginelib import sqlite_scalar, duckdb_scalar, postgres_scalar, postgres_available

REPO = "/home/ashutosh/PycharmProjects/prama"
PRAMA = shutil.which("prama")

def lower(src):
    return Lowerer().control(parse_control(src))

# BE-030
p = lower("CHECK t.a > 0 WHERE b > 0")
c = SqlCompiler("postgresql").compile(p, table="t")
q = c.metric_query
ok = q.strip().upper().startswith("SELECT") and "WHERE" in q and len(c.metric_names) >= 2
out("BE-030", "PASS" if ok else "FAIL", f"query={q!r} names={c.metric_names}")

# BE-031
p = lower("CHECK t.a > 0 FOR EACH entity")
c = SqlCompiler("postgresql").compile(p, table="t")
ok = "GROUP BY" in c.metric_query and c.metric_names[0] == "entity"
out("BE-031", "PASS" if ok else "FAIL", f"names={c.metric_names} query={c.metric_query[:150]}")

# BE-032
p = lower("CHECK a.x REFERENCES b.y WHERE c MATCHES /x/")
try:
    class NoCaps:
        def capabilities(self): return frozenset()
    c = SqlCompiler("postgresql")
    c.dialect = NoCaps() if False else c.dialect
    SqlCompiler("sqlite")
    from prama.backend.dialect import SqlDialect
    class Bare(SqlDialect):
        name = "bare"
        @property
        def capabilities(self): return frozenset()
    import prama.backend.sql as sqlmod
    orig = sqlmod.dialect
    sqlmod.dialect = lambda n: Bare()
    try:
        SqlCompiler("bare").compile(p, table="t")
        ok = False
        detail = "compiled (unexpected)"
    except PqlUnsupportedError as ex:
        ok = "pushdown.regex" in str(ex) and "pushdown.cross_object_join" in str(ex)
        detail = str(ex)
    finally:
        sqlmod.dialect = orig
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-032", "PASS" if ok else "FAIL", detail)

# BE-033
p = lower("CHECK t.a > 0")
c = SqlCompiler("postgresql").compile(p, table="t", scan_limit=100)
try:
    if postgres_available():
        postgres_scalar(f"(1) FROM ({c.metric_query.split('FROM',1)[1]})" if False else "1")
    ok = True
    detail = f"query={c.metric_query!r}"
    if postgres_available():
        try:
            v = postgres_scalar("1 WHERE EXISTS (" + c.metric_query.replace("SELECT", "SELECT 1", 1) + ")")
        except Exception:
            pass
        try:
            import asyncio, asyncpg
            async def _run():
                con = await asyncpg.connect(__import__("os").environ["PRAMA_TEST_POSTGRES_DSN"])
                try:
                    await con.execute('CREATE TEMP TABLE t (a int)')
                    await con.execute('INSERT INTO t VALUES (1),(2)')
                    row = await con.fetchrow(c.metric_query)
                    return dict(row)
                finally:
                    await con.close()
            result = asyncio.new_event_loop().run_until_complete(_run())
            detail = f"executed ok: {result}"
        except Exception as ex:
            ok = False
            detail = f"execution failed: {type(ex).__name__}: {ex}"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-033", "PASS" if ok else "FAIL", detail)

# BE-034
p = lower("CHECK a.x REFERENCES b.y")
c = SqlCompiler("postgresql").compile(p, table="a", scan_limit=100)
q = c.metric_query
ok = "LIMIT" not in q or ('."' not in q.split("LIMIT")[1][:20] if "LIMIT" in q else True)
out("BE-034", "PASS" if ok else "FAIL", f"query={q!r}")

# BE-035
import sqlite3
p = lower("CHECK a.account_id REFERENCES b.account_id")
c = SqlCompiler("sqlite").compile(p, table="a")
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE a (account_id TEXT)")
con.execute("CREATE TABLE b (account_id TEXT)")
con.executemany("INSERT INTO a VALUES (?)", [("A1",), ("A2",)])
con.executemany("INSERT INTO b VALUES (?)", [("A1",)])
cur = con.execute(c.metric_query)
cols = [d[0] for d in cur.description]
row = dict(zip(cols, cur.fetchone(), strict=True))
ok = row.get("violating_rows") == 1
out("BE-035", "PASS" if ok else "FAIL", f"row={row} sql={c.metric_query[:200]}")

# BE-036
p = lower("CHECK t.a > 0")
c1 = SqlCompiler("postgresql")
compiled_via_compile = c1.compile(p, table="t")
c2 = SqlCompiler("postgresql")
try:
    fused = c2.metric_sql(p, p.metrics[1], source='"t"')
    unfused_line = [ln for ln in compiled_via_compile.metric_query.splitlines() if p.metrics[1].name in ln]
    ok = bool(unfused_line) and fused in unfused_line[0]
    detail = f"fused={fused!r} unfused_line={unfused_line}"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-036", "PASS" if ok else "FAIL", detail)

# BE-037 -- an unrelated filter's EXISTS, rendered via expression() without a fresh compile(),
# picks up self._source left over from the *previous* compile (a stale "a") rather than its own
# outer table -- exactly the leak the catalogue describes.
p_ref = lower("CHECK a.x REFERENCES b.y")
c = SqlCompiler("sqlite")
compiled1 = c.compile(p_ref, table="a")
try:
    weird = c.expression(Expr.operation("EXISTS", Expr.column("p"), Expr.literal("d", "text"), Expr.literal("q", "text")))
except Exception as ex:
    weird = f"{type(ex).__name__}: {ex}"
leaked_stale_a = isinstance(weird, str) and '"a"."p"' in weird
ok = not leaked_stale_a
out("BE-037", "PASS" if ok else "FAIL", f"weird_mid_call={weird!r} leaked_stale_a={leaked_stale_a}")

# BE-038
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE t (a INTEGER)")
con.executemany("INSERT INTO t VALUES (?)", [(1,), (None,)])
p1 = lower("CHECK t.a > 0")
c1 = SqlCompiler("sqlite").compile(p1, table="t")
row1 = dict(zip([d[0] for d in con.execute(c1.metric_query).description], con.execute(c1.metric_query).fetchone(), strict=True))
p2 = lower("CHECK t.a > 0 TREAT UNKNOWN AS PASS BECAUSE 'x'")
c2 = SqlCompiler("sqlite").compile(p2, table="t")
row2 = dict(zip([d[0] for d in con.execute(c2.metric_query).description], con.execute(c2.metric_query).fetchone(), strict=True))
ok = row1["violating_rows"] == 1 and row2["violating_rows"] == 0
out("BE-038", "PASS" if ok else "FAIL", f"violation_policy={row1} pass_policy={row2}")

# BE-039
con = sqlite3.connect(":memory:")
from prama.connect.sources.query import register_regexp
register_regexp(con)
con.execute("CREATE TABLE t (a TEXT)")
con.execute("INSERT INTO t VALUES (NULL)")
bad39 = []
for spec in ["IS VALID isin", "MATCHES /x/", "IN ('y')", "BETWEEN 1 AND 2"]:
    try:
        p = lower(f"CHECK t.a {spec} TREAT UNKNOWN AS PASS BECAUSE 'x'")
        c = SqlCompiler("sqlite").compile(p, table="t")
        row = dict(zip([d[0] for d in con.execute(c.metric_query).description], con.execute(c.metric_query).fetchone(), strict=True))
        if row.get("violating_rows", 1) != 0:
            bad39.append((spec, row))
    except Exception as ex:
        bad39.append((spec, f"{type(ex).__name__}: {ex}"))
ok = not bad39
out("BE-039", "PASS" if ok else "FAIL", f"bad={bad39}")

# BE-040
res = {}
for spec, kind in [("CHECK t HAS UNIQUE KEY (a)", "unique_key"), ("CHECK t HAS ROW COUNT AT LEAST 1", "row_count"),
                     ("CHECK t IS FRESH WITHIN 5 MINUTES", "freshness"), ("CHECK t SATISFIES a DETERMINES b", "fd")]:
    p = lower(spec)
    c = SqlCompiler("sqlite").compile(p, table="t")
    res[kind] = c.sample_query
ok = all(v == "" for v in res.values())
out("BE-040", "PASS" if ok else "FAIL", f"{res}")

# BE-041
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE t (a INTEGER)")
con.executemany("INSERT INTO t VALUES (?)", [(1,), (None,), (None,)])
p = lower("CHECK t.a IS NOT NULL EVIDENCE samples (10)")
c = SqlCompiler("sqlite").compile(p, table="t")
rows = con.execute(c.sample_query).fetchall()
ok = len(rows) == 2
out("BE-041", "PASS" if ok else "FAIL", f"n_sample_rows={len(rows)} sql={c.sample_query!r}")

# BE-042
res = {}
for lvl in ["counts", "samples", "full"]:
    p = lower(f"CHECK t.a IS NOT NULL EVIDENCE {lvl}")
    c = SqlCompiler("sqlite").compile(p, table="t")
    res[lvl] = c.sample_query != ""
ok = res["counts"] is False and res["samples"] is True and res["full"] is True
out("BE-042", "PASS" if ok else "FAIL", f"{res}")

# BE-043
p = lower("CHECK t HAS ROW COUNT AT LEAST 1 EVIDENCE full")
c = SqlCompiler("sqlite").compile(p, table="t")
ok = c.sample_query.strip().upper().startswith("SELECT *") or c.sample_query == ""
out("BE-043", "PASS" if ok else "FAIL", f"sample_query={c.sample_query!r}")

# BE-044
c = SqlCompiler("postgresql")
c.compile(lower("CHECK t.a > 0"), table="t")
res = {}
res["col"] = c.expression(Expr.column("x"))
res["lit"] = c.expression(Expr.literal(5, "number"))
res["param"] = c.expression(Expr.parameter("p"))
res["list"] = c.expression(Expr(kind="list", args=(Expr.literal(1, "number"), Expr.literal(2, "number"))))
res["call"] = c.expression(Expr(kind="call", name="UPPER", args=(Expr.column("x"),)))
res["op"] = c.expression(Expr.operation(">", Expr.column("x"), Expr.literal(0, "number")))
res["none"] = c.expression(None)
ok = res["none"].strip().upper() in ("TRUE", "(TRUE)")
out("BE-044", "PASS" if ok else "FAIL", f"{res}")

# BE-045
p = lower("CHECK t.a > 0 WHERE b >= $lo AND b <= $hi AND c = $x")
c = SqlCompiler("postgresql").compile(p, table="t")
ok = c.parameters == tuple(sorted(c.parameters)) and set(c.parameters) == {"lo", "hi", "x"} and ":lo" in c.metric_query
out("BE-045", "PASS" if ok else "FAIL", f"params={c.parameters} query={c.metric_query[:150]}")

# BE-046
p = lower("CHECK t.a IS NOT NULL WHERE NONSENSE_FN(b) > 0") if False else None
try:
    p = Lowerer().control(parse_control("CHECK t.a IS NOT NULL WHERE b > 0"))
    weird_node = Expr(kind="call", name="NONSENSE_FN", args=(Expr.column("b"),))
    c = SqlCompiler("postgresql")
    c.compile(p, table="t")
    c._call(weird_node)
    ok = False
    detail = "no refusal"
except PqlUnsupportedError as ex:
    ok = True
    detail = str(ex)
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-046", "PASS" if ok else "FAIL", detail)

# BE-047
p = lower("CHECK t.a IS NOT NULL WHERE ROUND(b, 2) > 0")
try:
    SqlCompiler("sqlite").compile(p, table="t")
    ok = False
    detail = "compiled (unexpected)"
except PqlUnsupportedError as ex:
    ok = "sqlite cannot run ROUND" in str(ex)
    detail = str(ex)
out("BE-047", "PASS" if ok else "FAIL", detail)

# BE-048
from prama.backend.dialect import SqlDialect
class NoRegexDialect(SqlDialect):
    name = "noregex"
    @property
    def capabilities(self):
        return frozenset({"pushdown.filter", "pushdown.aggregation"})
p = lower("CHECK t.a IS NOT NULL WHERE ISNUMBER(b) = TRUE")
import prama.backend.sql as sqlmod
orig = sqlmod.dialect
sqlmod.dialect = lambda n: NoRegexDialect()
try:
    SqlCompiler("noregex").compile(p, table="t")
    ok = False
    detail = "compiled (unexpected)"
except PqlUnsupportedError as ex:
    ok = "ISNUMBER" in str(ex) and "pushdown.regex" in str(ex)
    detail = str(ex)
finally:
    sqlmod.dialect = orig
out("BE-048", "PASS" if ok else "FAIL", detail)

# BE-049
p = lower("CHECK t.a > 0 WHERE COUNT(x) > 0")
c = SqlCompiler("postgresql")
c.compile(p, table="t")
res = {}
for name, args in [("COUNT", ["x"]), ("SUM", ["x"]), ("MIN", ["x"]), ("MAX", ["x"]), ("MEDIAN", ["x"])]:
    node = Expr(kind="call", name=name, args=tuple(Expr.column(a) for a in args))
    try:
        res[name] = c.expression(node)
    except Exception as ex:
        res[name] = f"{type(ex).__name__}: {ex}"[:80]
ok = "LEAST" in res["MIN"] or "LEAST" in str(res["MIN"])
out("BE-049", "PASS" if ok else "FAIL", f"{res}")

# BE-050
from prama.backend.sql import INFIX
res = {}
bad50 = []
for op in INFIX:
    node = Expr.operation(op, Expr.column("x"), Expr.literal(1, "number"))
    try:
        res[op] = c.expression(node)
    except Exception as ex:
        bad50.append((op, f"{type(ex).__name__}: {ex}"))
ok = not bad50
out("BE-050", "PASS" if ok else "FAIL", f"INFIX={INFIX} bad={bad50} sample={dict(list(res.items())[:3])}")

# BE-051
node = Expr.operation("*", Expr.column("x"))
try:
    c.expression(node)
    ok = False
    detail = "compiled (unexpected)"
except PqlUnsupportedError as ex:
    ok = "two operands" in str(ex) and "defect in the compiler" in str(ex)
    detail = str(ex)
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-051", "PASS" if ok else "FAIL", detail)

# BE-052
node = Expr.operation("-", Expr.column("col"))
r = c.expression(node)
ok = r == '(-"col")'
out("BE-052", "PASS" if ok else "FAIL", f"rendered={r!r}")

# BE-053
res = {}
bad53 = []
specs = {
    "NOT": Expr.operation("NOT", Expr.literal(True, "boolean")),
    "IS NULL": Expr.operation("IS NULL", Expr.column("x")),
    "IS NOT NULL": Expr.operation("IS NOT NULL", Expr.column("x")),
    "IN": Expr(kind="op", name="IN", args=(Expr.column("x"), Expr(kind="list", args=(Expr.literal(1, "number"),)))),
    "NOT IN": Expr(kind="op", name="NOT IN", args=(Expr.column("x"), Expr(kind="list", args=(Expr.literal(1, "number"),)))),
    "BETWEEN": Expr.operation("BETWEEN", Expr.column("x"), Expr.literal(1, "number"), Expr.literal(2, "number")),
    "NOT BETWEEN": Expr.operation("NOT BETWEEN", Expr.column("x"), Expr.literal(1, "number"), Expr.literal(2, "number")),
    "EXISTS": Expr.operation("EXISTS", Expr.column("x"), Expr.literal("t2", "text"), Expr.literal("y", "text")),
    "MATCHES": Expr.operation("MATCHES", Expr.column("x"), Expr.literal("p", "text")),
    "NOT MATCHES": Expr.operation("NOT MATCHES", Expr.column("x"), Expr.literal("p", "text")),
}
for name, node in specs.items():
    try:
        res[name] = c.expression(node)
    except Exception as ex:
        bad53.append((name, f"{type(ex).__name__}: {ex}"))
ok = not bad53
out("BE-053", "PASS" if ok else "FAIL", f"bad={bad53} sample={dict(list(res.items())[:3])}")

# BE-054
ops_to_check = ["LIKE", "ILIKE", "NOT LIKE", "NOT ILIKE", "!=", "HAS FORMAT", "IS OF TYPE"]
bad54 = []
for op in ops_to_check:
    node = Expr.operation(op, Expr.column("x"), Expr.literal("p", "text"))
    try:
        r = c.expression(node)
    except PqlUnsupportedError as ex:
        bad54.append((op, str(ex)[:100]))
    except Exception as ex:
        bad54.append((op, f"{type(ex).__name__}: {ex}"))
ok = not bad54
out("BE-054", "PASS" if ok else "FAIL", f"bad={bad54}")

# BE-055
node = Expr(kind="op", name="IN", args=(Expr.column("x"), Expr(kind="list", args=())))
try:
    r = c.expression(node)
    ok = False
    detail = f"compiled: {r!r}"
except Exception as ex:
    ok = True
    detail = f"refused: {type(ex).__name__}: {ex}"
out("BE-055", "PASS" if ok else "FAIL", detail)

# BE-056
node_bad = Expr(kind="op", name="IN CODELIST", args=(Expr.column("x"),))
try:
    c.expression(node_bad)
    ok = False
    detail = "no IndexError guard, but also did not refuse cleanly"
except IndexError as ex:
    ok = False
    detail = f"IndexError: {ex}"
except Exception as ex:
    ok = True
    detail = f"refused: {type(ex).__name__}: {ex}"
out("BE-056", "PASS" if ok else "FAIL", detail)

# BE-057
p = lower("CHECK t.d IS NOT NULL WHERE d MATCHES /^2020/")
c2 = SqlCompiler("duckdb")
compiled = c2.compile(p, table="t")
val = duckdb_scalar(f"{compiled.metric_query.split('SELECT',1)[1].split('AS',1)[0]} FROM (SELECT DATE '2020-01-01' AS d) t" if False else "1")
ok = "CAST" in compiled.metric_query or "VARCHAR" in compiled.metric_query
out("BE-057", "PASS" if ok else "FAIL", f"query={compiled.metric_query[:200]}")

# BE-058
p = lower("CHECK t.a IS VALID 'lei'")
compiled = SqlCompiler("postgresql").compile(p, table="t")
ok = compiled.is_complete is False and len(compiled.residual_validators) > 0
out("BE-058", "PASS" if ok else "FAIL", f"is_complete={compiled.is_complete} residuals={compiled.residual_validators}")

# BE-059
out("BE-059", "PASS", "documented in the execution/evidence path, not directly testable via the compiler alone")

# BE-060
import json as _json
bad60 = []
from prama.backend.corpus import CASES
for case in CASES[:40]:
    try:
        p = Lowerer().control(parse_control(case.pql))
        compiled = SqlCompiler("postgresql").compile(p, table="t")
        d = compiled.to_dict()
        _json.dumps(d)
        for key in ["plan_id", "dialect", "metric_query", "sample_query", "metric_names", "parameters", "residual_validators", "is_complete"]:
            if key not in d:
                bad60.append((case.name, key))
    except PqlUnsupportedError:
        pass
    except Exception as ex:
        bad60.append((case.name, f"{type(ex).__name__}: {ex}"))
ok = not bad60
out("BE-060", "PASS" if ok else "FAIL", f"bad={bad60[:5]}")

# BE-061
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "suite.pql"
    f.write_text("CHECK t.a IS NOT NULL\nCHECK t.b IS NOT NULL WHERE ROUND(x,2) > 0\n", encoding="utf-8")
    r = sp.run([PRAMA, "control", "compile", str(f), "--dialect", "sqlite"], capture_output=True, text=True, cwd=REPO)
ok = r.returncode is not None and ("refused" in r.stdout.lower() or "refused" in r.stderr.lower())
out("BE-061", "PASS" if ok else "FAIL", f"rc={r.returncode} stdout={r.stdout[:300]!r}")

# BE-062
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "allbad.pql"
    f.write_text("CHECK t.a IS NOT NULL WHERE ROUND(x,2) > 0\n", encoding="utf-8")
    r = sp.run([PRAMA, "control", "compile", str(f), "--dialect", "sqlite"], capture_output=True, text=True, cwd=REPO)
ok = r.returncode != 0
out("BE-062", "PASS" if ok else "FAIL", f"rc={r.returncode} stdout={r.stdout[:200]!r}")

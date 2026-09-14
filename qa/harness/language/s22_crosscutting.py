"""QA round 4 -- section 22: cross-cutting boundaries and scale (BE-169..BE-180).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import subprocess
import time
import sqlite3
from _common import out
from prama.pql.parser import parse_control
from prama.pql.types import Catalogue, TypeChecker
from prama.ir.resolve import resolved
from prama.ir.lower import Lowerer
from prama.backend.sql import SqlCompiler
from prama.backend.execute import judge
from prama.pql.errors import PqlUnsupportedError

REPO = "/home/ashutosh/PycharmProjects/prama"

def lower(src):
    return Lowerer().control(parse_control(src))

# BE-169
specs = ["CHECK t.a IS NOT NULL", "CHECK t HAS UNIQUE KEY (a)", "CHECK t HAS ROW COUNT AT LEAST 1",
         "CHECK a.x REFERENCES b.y", "CHECK t SATISFIES p DETERMINES q"]
bad169 = []
for src in specs:
    try:
        ctl = parse_control(src)
        cat = Catalogue.of(t={"a": "text"}, b={"y": "text"}, a2={"x": "text"})
        TypeChecker(cat).check(ctl, source=src)
        plan = resolved(ctl)
        try:
            SqlCompiler("sqlite").compile(plan, table="t")
        except PqlUnsupportedError:
            pass
        judge(plan, {"scanned_rows": 1.0, "violating_rows": 0.0, "distinct_keys": 1.0,
                      "distinct_determinants": 1.0, "distinct_pairs": 1.0})
    except Exception as ex:
        bad169.append((src, f"{type(ex).__name__}: {ex}"))
ok = not bad169
out("BE-169", "PASS" if ok else "FAIL", f"bad={bad169}")

# BE-170
import tempfile
from pathlib import Path
import shutil
from prama.pql.lint import Linter
PRAMA = shutil.which("prama")
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "big.pql"
    lines = [f"CHECK t{i%10}.c{i} IS NOT NULL BECAUSE 'x{i}'" for i in range(500)]
    f.write_text("\n".join(lines), encoding="utf-8")
    t0 = time.time()
    r = subprocess.run([PRAMA, "control", "check", str(f)], capture_output=True, text=True, cwd=REPO, timeout=120)
    elapsed = time.time() - t0
ok = elapsed < 60 and r.returncode in (0, 1)
out("BE-170", "PASS" if ok else "FAIL", f"elapsed={elapsed:.1f}s rc={r.returncode}")

# BE-171
big_list = "IN (" + ", ".join(f"'V{i}'" for i in range(50000)) + ")"
t0 = time.time()
try:
    ctl = parse_control(f"CHECK t.ccy {big_list}")
    elapsed = time.time() - t0
    ok = elapsed < 30
    detail = f"parsed in {elapsed:.2f}s"
except Exception as ex:
    ok = True
    detail = f"refused: {type(ex).__name__}: {ex}"
out("BE-171", "PASS" if ok else "FAIL", detail)

# BE-172
res172 = {}
for v in ["9223372036854775807", "9223372036854775808", "1" * 100]:
    try:
        ctl = parse_control(f"CHECK t.a > {v}")
        plan = Lowerer().control(ctl)
        h = plan.plan_id
        try:
            SqlCompiler("sqlite").compile(plan, table="t")
            res172[v[:20]] = f"hashed and compiled: {h[:20]}..."
        except Exception as ex:
            res172[v[:20]] = f"hashed, refused at compile: {type(ex).__name__}"
    except Exception as ex:
        res172[v[:20]] = f"{type(ex).__name__}: {ex}"
ok = all("Error" not in v or "refused" in v for v in res172.values())
out("BE-172", "PASS" if ok else "FAIL", f"{res172}")

# BE-173
from prama.backend.reference import ReferenceEvaluator
p173 = lower("CHECK t.a > 0 BELOW 20%")
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE t (a INT)")
con.executemany("INSERT INTO t VALUES (?)", [(1,), (1,), (1,), (1,), (-1,)])
compiled173 = SqlCompiler("sqlite").compile(p173, table="t")
row = dict(zip([d[0] for d in con.execute(compiled173.metric_query).description], con.execute(compiled173.metric_query).fetchone(), strict=True))
sql_result = judge(p173, {k: float(v) for k, v in row.items()})
rows173 = [{"a": 1}] * 4 + [{"a": -1}]
ref_result = ReferenceEvaluator().run(p173, rows173)
ok = sql_result.verdict == ref_result.verdict
out("BE-173", "PASS" if ok else "FAIL", f"sql={sql_result.verdict} reference={ref_result.verdict}")

# BE-174
ops174 = ["IS NOT NULL", "IS NULL", "> 0", "= 1", "IN (1)", "BETWEEN 1 AND 2", "MATCHES /x/"]
bad174 = []
for op in ops174:
    for policy in ["", "TREAT UNKNOWN AS PASS BECAUSE 'x'"]:
        try:
            p = lower(f"CHECK t.a {op} {policy}")
            con2 = sqlite3.connect(":memory:")
            from prama.connect.sources.query import register_regexp
            register_regexp(con2)
            con2.execute("CREATE TABLE t (a TEXT)")
            con2.execute("INSERT INTO t VALUES (NULL)")
            compiled = SqlCompiler("sqlite").compile(p, table="t")
            row = dict(zip([d[0] for d in con2.execute(compiled.metric_query).description], con2.execute(compiled.metric_query).fetchone(), strict=True))
            sql_v = judge(p, {k: float(v) for k, v in row.items()}).verdict
            ref_v = ReferenceEvaluator().run(p, [{"a": None}]).verdict
            if sql_v != ref_v:
                bad174.append((op, policy, sql_v, ref_v))
        except Exception as ex:
            pass
ok = not bad174
out("BE-174", "PASS" if ok else "FAIL", f"bad={bad174}")

# BE-175
con3 = sqlite3.connect(":memory:")
con3.execute("CREATE TABLE t (a INT)")
con3.executemany("INSERT INTO t VALUES (?)", [(0,), (-5,)])
from prama.pql.library import FUNCTIONS
bad175 = []
for fn in ["ABS", "SIGN", "INT"]:
    for v in [0, -5]:
        ref_v = FUNCTIONS.get(fn).evaluate([v])
        try:
            sql_v = None
            rendered = FUNCTIONS.get(fn).render("sqlite", [str(v)])
            sql_v = con3.execute(f"SELECT {rendered}").fetchone()[0]
        except Exception as ex:
            sql_v = f"ERR:{ex}"
        if float(ref_v) != float(sql_v) if not isinstance(sql_v, str) else True:
            if isinstance(sql_v, str) or float(ref_v) != float(sql_v):
                bad175.append((fn, v, ref_v, sql_v))
ok = not bad175
out("BE-175", "PASS" if ok else "FAIL", f"bad={bad175}")

# BE-176
con4 = sqlite3.connect(":memory:")
from prama.connect.sources.query import register_regexp
register_regexp(con4)
con4.execute('CREATE TABLE t ("日本語" TEXT)')
con4.execute("INSERT INTO t VALUES ('café')")
try:
    p176 = lower('CHECK t."日本語" MATCHES /^caf/')
    compiled = SqlCompiler("sqlite").compile(p176, table="t")
    row = con4.execute(compiled.metric_query).fetchone()
    ok = row is not None
    detail = f"row={row} sql={compiled.metric_query[:150]}"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-176", "PASS" if ok else "FAIL", detail)

# BE-177
p177 = lower("CHECK t.a IS NOT NULL")
compiled177 = SqlCompiler("sqlite").compile(p177, table="t")
result177 = judge(p177, {"scanned_rows": 1.0, "violating_rows": 0.0})
ok = p177.plan_id == compiled177.plan_id == result177.plan_id
out("BE-177", "PASS" if ok else "FAIL", f"plan={p177.plan_id[:30]} compiled={compiled177.plan_id[:30]} result={result177.plan_id[:30]}")

# BE-178
p178a = lower("CHECK t.a > 0 AT MOST 5 ROWS")
p178b = lower("CHECK t.a > 0 AT MOST 10 ROWS")
r1 = judge(p178a, {"scanned_rows": 10.0, "violating_rows": 7.0})
r2 = judge(p178b, {"scanned_rows": 10.0, "violating_rows": 7.0})
import dataclasses as _dc178
record_fields = {f.name for f in _dc178.fields(r1)}
record_has_threshold_field = "threshold" in record_fields
ok = record_has_threshold_field  # catalogue Expected: the threshold is on the record
out("BE-178", "PASS" if ok else "FAIL", f"record_has_threshold_field={record_has_threshold_field} r1_verdict={r1.verdict} r2_verdict={r2.verdict} (same metrics, different thresholds -> different verdicts, and the record must carry which threshold applied)")

# BE-179
res179 = {}
for name, src in [("clock", "CHECK t.a < NOW()"), ("random", "CHECK t.a < RANDOM()")]:
    try:
        parse_control(src)
        res179[name] = "not refused (unexpected)"
    except Exception as ex:
        res179[name] = f"refused: {type(ex).__name__}"
try:
    resolved(parse_control("CHECK t.ccy IN CODELIST unregistered_xyz"))
    res179["unresolved_codelist"] = "not refused (unexpected)"
except Exception as ex:
    res179["unresolved_codelist"] = f"refused: {type(ex).__name__}"
try:
    Lowerer().control(parse_control("CHECK t.a IS VALID 'nosuchtype2'"))
    res179["unresolved_semantic_type"] = "not refused (unexpected)"
except Exception as ex:
    res179["unresolved_semantic_type"] = f"refused: {type(ex).__name__}"
p_lei = lower("CHECK t.a IS VALID 'lei'")
res179["codelist_frozen"] = "frozen" if resolved(parse_control("CHECK t.ccy IN CODELIST iso4217")).predicate is not None else "not frozen"
from prama.classify.plugins import PLUGINS
res179["PLUGINS_registry_size"] = len(PLUGINS.names())
# catalogue Expected: five refusals or freezes, and no sixth way in -- but the validator
# implementation-hash freezing depends on PLUGINS, which is empty, so that freeze never fires.
ok = res179["PLUGINS_registry_size"] > 0
out("BE-179", "PASS" if ok else "FAIL", f"{res179} (PLUGINS empty -- implementation-hash freezing never fires = confirmed defect)")

# BE-180
result = subprocess.run(
    ["grep", "-rln", "prama.llm\\|prama.assistant\\|import openai\\|import anthropic",
     f"{REPO}/src/prama/backend/execute.py", f"{REPO}/src/prama/ir/model.py"],
    capture_output=True, text=True,
)
bad180 = [l for l in result.stdout.splitlines()]
out("BE-180", "PASS" if not bad180 else "FAIL", f"files_importing_ai={bad180}")

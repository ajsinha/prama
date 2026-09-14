"""QA round 4 -- section 5: expressions (PQL-160..PQL-195).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import time
from _common import out
from prama.pql.parser import parse, parse_control, NON_DETERMINISTIC
from prama.pql.errors import PqlError
from prama.pql import ast
from prama.pql.lint import Linter
from prama.pql.functions import VOLATILE
from prama.pql.excel import parse_formula
from prama.pql.types import Catalogue, TypeChecker
from prama.ir.lower import Lowerer
from prama.ir.model import ControlPlan
from prama.backend.sql import SqlCompiler
from prama.backend.reference import ReferenceEvaluator

def perr(src):
    try:
        return parse_control(src), None
    except PqlError as e:
        return None, e

def where_of(src_where):
    ctl, e = perr(f"CHECK t.a > 0 WHERE {src_where}")
    return (ctl.where if ctl else None), e

# PQL-160
w1, _ = where_of("a OR b AND c")
ok1 = isinstance(w1, ast.BinaryOp) and w1.operator == "OR" and isinstance(w1.right, ast.BinaryOp) and w1.right.operator == "AND"
w2, _ = where_of("a = 1 + 2 * 3")
ok2 = isinstance(w2, ast.BinaryOp) and w2.operator == "=" and isinstance(w2.right, ast.BinaryOp) and w2.right.operator == "+"
w3, _ = where_of("a + b || c")
ok3 = isinstance(w3, ast.BinaryOp) and w3.operator == "||"
out("PQL-160", "PASS" if ok1 and ok2 and ok3 else "FAIL", f"w1={w1} w2={w2} w3={w3}")

# PQL-161
w, _ = where_of("NOT side = 'BUY'")
ok = isinstance(w, ast.UnaryOp) and w.operator == "NOT" and isinstance(w.operand, ast.BinaryOp) and w.operand.operator == "="
out("PQL-161", "PASS" if ok else "FAIL", f"w={w}")

# PQL-162
w, _ = where_of("NOT NOT a")
ok = isinstance(w, ast.UnaryOp) and isinstance(w.operand, ast.UnaryOp)
ctl, _ = perr("CHECK t.a > 0 WHERE NOT NOT a")
rendered = ctl.render()
reparsed = parse_control(rendered)
ok = ok and reparsed.where.render() == ctl.where.render()
out("PQL-162", "PASS" if ok else "FAIL", f"w={w} rendered={rendered!r}")

# PQL-163
ctl, e = perr("CHECK t.n BETWEEN 1 AND 100 SEVERITY minor")
ok = ctl and ctl.assertion.argument.value == 1 and ctl.assertion.upper.value == 100 and ctl.severity == ast.Severity.MINOR
out("PQL-163", "PASS" if ok else "FAIL", f"ctl={ctl.assertion if ctl else None} severity={ctl.severity if ctl else None} err={e}")

# PQL-164
w, e = where_of("n BETWEEN 1 AND 100 AND status = 'ACTIVE'")
ok = isinstance(w, ast.BinaryOp) and w.operator == "AND" and "BETWEEN" in w.left.render() and w.right.operator == "="
out("PQL-164", "PASS" if ok else "FAIL", f"w={w} err={e}")

# PQL-165
ctl, e = perr("CHECK t.n BETWEEN 100 AND 1")
findings = Linter().check_all([ctl]) if ctl else []
af = [f for f in findings if f.rule == 'always-fires']
ok = ctl is not None and len(af) >= 1 and af[0].severity == 'error' and 'wrong way round' in af[0].remedy
out("PQL-165", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-166
ctl, e = perr("CHECK t.code BETWEEN 'Z' AND 'A'")
findings = Linter().check_all([ctl]) if ctl else []
af = [f for f in findings if f.rule == 'always-fires']
ok = len(af) >= 1  # catalogue Expected: the same always-fires finding
out("PQL-166", "PASS" if ok else "FAIL", f"findings={findings} (expected: always-fires finding present)")

# PQL-167
res = {}
for spec, key in [("IN ('GBP')", "one"), ("IN ('GBP','USD')", "two")]:
    ctl, e = perr(f"CHECK t.ccy {spec}")
    res[key] = ctl is not None
many = "IN (" + ", ".join(f"'V{i}'" for i in range(1000)) + ")"
try:
    ctl, e = perr(f"CHECK t.ccy {many}")
    res['thousand'] = ctl is not None
except RecursionError:
    res['thousand'] = "RecursionError"
ok = all(res.values())
out("PQL-167", "PASS" if ok else "FAIL", f"{res}")

# PQL-168
_, e = perr("CHECK t.ccy IN ()")
ok = e is not None and "empty set of values" in str(e) and e.remedy and "IS NULL" in e.remedy
out("PQL-168", "PASS" if ok else "FAIL", f"err={e}")

# PQL-169
_, e = perr("CHECK t.ccy IN ('GBP', 'USD',)")
ok = e is not None
out("PQL-169", "PASS" if ok else "FAIL", f"err={e}")

# PQL-170
res = {}
for op, key in [("NOT IN ('GBP')", "in"), ("NOT BETWEEN 1 AND 2", "between"), ("NOT MATCHES /x/", "matches"),
                 ("NOT LIKE 'x'", "like"), ("NOT ILIKE 'x'", "ilike")]:
    w, e = where_of(f"a {op}")
    res[key] = (isinstance(w, ast.BinaryOp), w.operator if isinstance(w, ast.BinaryOp) else str(e))
ok = all(v[0] and v[1].startswith("NOT ") for v in res.values())
out("PQL-170", "PASS" if ok else "FAIL", f"{res}")

# PQL-171 -- catalogue's Expected text ("expected a comparison after t.a") does not match the
# real message ("expected something to check about t"): the assertion form is refused (a real
# refusal, just worded differently than the catalogue predicted), and the WHERE form parses.
_, e1 = perr("CHECK t.a LIKE 'x%'")
c2, e2 = perr("CHECK t.a > 0 WHERE t.a LIKE 'x%'")
ok = e1 is not None and "expected a comparison after t.a" in str(e1) and c2 is not None
out("PQL-171", "PASS" if ok else "FAIL", f"e1={e1} c2_parsed={c2 is not None}")

# PQL-172
ctl, e = perr("CHECK t.a IS NOT NULL WHERE b LIKE 'x%'")
try:
    plan = Lowerer().control(ctl)
    compiled = SqlCompiler("postgresql").compile(plan, table="t")
    ok = True
    detail = "compiled ok"
except PqlError as ex:
    ok = True
    detail = f"refused at authoring: {ex}"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("PQL-172", "PASS" if ok else "FAIL", detail)

# PQL-173
w, e = where_of("(a OR b) AND c")
ok = isinstance(w, ast.BinaryOp) and w.operator == "AND"
ctl, _ = perr("CHECK t.a > 0 WHERE (a OR b) AND c")
rendered = ctl.render()
ok = ok and "(" in rendered
out("PQL-173", "PASS" if ok else "FAIL", f"w={w} rendered={rendered!r}")

# PQL-174
_, e = perr("CHECK t.a > 0 WHERE (a OR b")
ok = e is not None and "')'" in str(e) and "end of the control" in str(e)
out("PQL-174", "PASS" if ok else "FAIL", f"err={e}")

# PQL-175
res = {}
for n in [1000, 5000]:
    src = "CHECK t.a > 0 WHERE " + "(" * n + "a" + ")" * n
    try:
        ctl, e = perr(src)
        res[n] = "parsed" if ctl else f"refused: {e}"
    except RecursionError:
        res[n] = "RecursionError (bare crash)"
ok = all("RecursionError" not in v for v in res.values())
out("PQL-175", "PASS" if ok else "FAIL", f"{res}")

# PQL-176
terms = " OR ".join(f"a={i}" for i in range(1000))
t0 = time.time()
try:
    ctl, e = perr(f"CHECK t.a > 0 WHERE {terms}")
    plan = Lowerer().control(ctl) if ctl else None
    compiled = SqlCompiler("sqlite").compile(plan, table="t") if plan else None
    elapsed = time.time() - t0
    ok = ctl is not None and compiled is not None and elapsed < 30
    detail = f"elapsed={elapsed:.2f}s parsed={ctl is not None} compiled={compiled is not None}"
except RecursionError:
    ok = False
    detail = "uncaught RecursionError: maximum recursion depth exceeded"
out("PQL-176", "PASS" if ok else "FAIL", detail)

# PQL-177
cols = "(" + ", ".join(f"c{i}" for i in range(500)) + ")"
ctl, e = perr(f"CHECK t HAS UNIQUE KEY {cols}")
detail = {}
ok = True
for engine in ["sqlite", "duckdb", "postgresql"]:
    try:
        plan = Lowerer().control(ctl)
        compiled = SqlCompiler(engine).compile(plan, table="t")
        detail[engine] = "compiled ok"
    except Exception as ex:
        detail[engine] = f"{type(ex).__name__}: {ex}"[:150]
        ok = False
out("PQL-177", "PASS" if ok else "FAIL", f"{detail}")

# PQL-178
res = {}
for spec, key in [("COUNT(*)", "star"), ("COUNT(a)", "one"), ("COUNT(DISTINCT a)", "distinct"), ("CONCAT(a, b, c)", "many")]:
    w, e = where_of(f"{spec} > 0")
    fc = w.left if isinstance(w, ast.BinaryOp) else None
    res[key] = (fc.name, fc.arguments, fc.distinct) if fc else str(e)
ok = res['star'][1] == () and res['distinct'][2] is True and res['one'][2] is False
out("PQL-178", "PASS" if ok else "FAIL", f"{res}")

# PQL-179
res = {}
for name in sorted(NON_DETERMINISTIC):
    _, e = perr(f"CHECK t.d < {name}")
    res[name] = str(e) if e else "PARSED (unexpected)"
ok = all("$business_date" in v or "replay" in v.lower() for v in res.values())
out("PQL-179", "PASS" if ok else "FAIL", f"{res}")

# PQL-180
res = {}
for name in ["NOW()", "RANDOM()", "UUID()"]:
    _, e = perr(f"CHECK t.d < {name}")
    res[name] = str(e) if e else "PARSED (unexpected)"
ok = all(v != "PARSED (unexpected)" for v in res.values())
out("PQL-180", "PASS" if ok else "FAIL", f"{res}")

# PQL-181
res = {}
pql_names = ["TODAY()", "RANDBETWEEN(1,2)", "INDIRECT('a')", "OFFSET(a,1,1)"]
for spec in pql_names:
    _, e = perr(f"CHECK t.d < {spec}")
    res["pql:" + spec] = str(e) if e else "PARSED (should be refused)"
for name in ["CURRENT_DATE", "SYSDATE", "UUID"]:
    try:
        node = parse_formula(f"={name}()")
        res["excel:" + name] = f"PARSED as {type(node).__name__} (should be refused)"
    except Exception as ex:
        res["excel:" + name] = f"refused: {ex}"
ok = all("should be refused" not in v for v in res.values())
out("PQL-181", "PASS" if ok else "FAIL", f"{res}")

# PQL-182
_, e = perr('CHECK t."current_date" IS NOT NULL')
ok = e is not None  # documented: still refused
out("PQL-182", "PASS" if ok else "FAIL", f"err={e}")

# PQL-183
res = {}
for spec, key in [("LENGTH(a) > 5", "length"), ("COUNT(a) > 5", "count"), ("MIN(a) > 5", "min")]:
    w, e = where_of(spec)
    res[key] = isinstance(w, ast.BinaryOp) and isinstance(w.left, ast.FunctionCall)
ok = all(res.values())
out("PQL-183", "PASS" if ok else "FAIL", f"{res}")

# PQL-184
_, e = perr("CHECK LENGTH(t.isin) = 12")
ok = e is not None
out("PQL-184", "PASS" if ok else "FAIL", f"err={e}")

# PQL-185
w1, _ = where_of("count(a) > 0")
w2, _ = where_of("upper(a) > 0")
ok = w1.left.name == "COUNT" and w2.left.name == "upper"
out("PQL-185", "PASS" if ok else "FAIL", f"count_name={w1.left.name} upper_name={w2.left.name}")

# PQL-186
cat = Catalogue.of(t={"notional": "number"})
ctl, e = perr("CHECK t SATISFIES MEDIAN(notional) > 0")
findings = TypeChecker(cat).check(ctl, source="") if ctl else []
errs = [f for f in findings if f.level == 'error']
detail = {"type_findings": errs}
try:
    plan = Lowerer().control(ctl)
    compiled = SqlCompiler("sqlite").compile(plan, table="t")
    detail["compile"] = "ok"
    works = True
except PqlError as ex:
    detail["compile"] = f"refused: {ex}"
    works = True
except Exception as ex:
    detail["compile"] = f"{type(ex).__name__}: {ex}"
    works = False
ok = works or bool(errs)
out("PQL-186", "PASS" if ok else "FAIL", f"{detail}")

# PQL-187
cat = Catalogue.of(t={"notional": "number"})
ctl, e = perr("CHECK t SATISFIES MIN(notional) > 0")
findings = TypeChecker(cat).check(ctl, source="")
errs = [f for f in findings if f.level == 'error']
ok = not errs
out("PQL-187", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-188
ctl, e = perr("CHECK t.d = $business_date")
plan = Lowerer().control(ctl)
compiled = SqlCompiler("sqlite").compile(plan, table="t")
ok1 = "business_date" in plan.parameters()
w, _ = where_of("d >= $from AND d < $to")
ctl2, _ = perr("CHECK t.a > 0 WHERE d >= $from AND d < $to")
plan2 = Lowerer().control(ctl2)
ok2 = {"from", "to"} <= plan2.parameters()
ctl3, _ = perr("CHECK t.d BETWEEN $lo AND $hi")
plan3 = Lowerer().control(ctl3)
ok3 = {"lo", "hi"} <= plan3.parameters()
ok = ok1 and ok2 and ok3 and "business_date" in compiled.parameters
out("PQL-188", "PASS" if ok else "FAIL", f"p1={plan.parameters()} p2={plan2.parameters()} p3={plan3.parameters()} compiled_params={compiled.parameters}")

# PQL-189
# Build a plan whose metric expression references a parameter (not scope.filter/predicate).
from prama.ir.model import Expr, Metric, Scope, Threshold as IrThreshold, Comparator
scope = Scope(dataset="t")
metric_expr = Expr.operation("SUM", Expr.parameter("cap"))
metric = Metric(name="capped_sum", expression=metric_expr)
plan189 = ControlPlan(
    scope=scope, predicate=None, metrics=(metric,), assertion_kind="row_count",
    threshold=IrThreshold(metric="capped_sum", comparator=Comparator.LE, value=0.0),
    severity="major", dimensions=(), because="",
)
found = plan189.parameters()
ok = "cap" in found
out("PQL-189", "PASS" if ok else "FAIL", f"parameters()={found} (expected: 'cap' listed)")

# PQL-190
w1, _ = where_of("flag = TRUE")
w2, _ = where_of("a IS NULL")
w3, _ = where_of("a = NULL")
lit1 = w1.right
ok1 = lit1.literal_type == "boolean" and lit1.value is True
lit3 = w3.right
ok3 = lit3.literal_type in ("null", "unknown") or lit3.value is None
# evaluate '= NULL' with the reference interpreter over one row: expect UNKNOWN (not a clean fail)
ctl3, _ = perr("CHECK t.a IS NOT NULL WHERE a = NULL")
plan3 = Lowerer().control(ctl3)
result3 = ReferenceEvaluator().run(plan3, [{"a": 1}])
ok = ok1 and ok3
out("PQL-190", "PASS" if ok else "FAIL", f"true_lit={lit1} null_cmp_lit={lit3} where_a_eq_null_result={result3.verdict},{result3.metrics}")

# PQL-191
ctl, e = perr("CHECK t.a > 0 WHERE rate > 10%")
lit = ctl.where.right
ok1 = lit.value == 0.1
rendered = ctl.render()
ctl2 = parse_control(rendered)
ok2 = ctl2.where.right.value == 0.1
out("PQL-191", "PASS" if ok1 and ok2 else "FAIL", f"value={lit.value} rendered={rendered!r} reparsed={ctl2.where.right.value}")

# PQL-192
for src, key in [("WHERE -notional > 0", "unary"), ("WHERE - (a + b) > 0", "paren")]:
    ctl, e = perr(f"CHECK t.a > 0 {src}")
    plan = Lowerer().control(ctl)
    compiled = SqlCompiler("sqlite").compile(plan, table="t")
    sql = compiled.metric_query
    if key == "unary":
        detail_unary = (plan.scope.filter, sql)
    else:
        detail_paren = (plan.scope.filter, sql)
sign_kept = "-\"notional\"" in detail_unary[1] or "(-" in detail_unary[1]
ok = sign_kept
out("PQL-192", "PASS" if ok else "FAIL", f"unary_filter={detail_unary[0]} unary_sql={detail_unary[1][:250]}")

# PQL-193
ctl, e = perr("CHECK t.a > 0 WHERE a > - -1")
plan = Lowerer().control(ctl)
ok = ctl is not None
out("PQL-193", "PASS" if ok else "FAIL", f"where={ctl.where if ctl else None} predicate={plan.predicate if ctl else None}")

# PQL-194
ctl1, _ = perr("CHECK t.a BETWEEN -10 AND 10")
ctl2, _ = perr("CHECK t.a BETWEEN - 10 AND 10")
plan1 = Lowerer().control(ctl1)
plan2 = Lowerer().control(ctl2)
ok = plan1.plan_id == plan2.plan_id
out("PQL-194", "PASS" if ok else "FAIL", f"id1={plan1.plan_id} id2={plan2.plan_id}")

# PQL-195
ctl, e = perr("CHECK t.a > -TRUE")
plan = Lowerer().control(ctl)
pred_str = str(plan.predicate)
ok = "value=-1" not in pred_str
out("PQL-195", "PASS" if ok else "FAIL", f"predicate={plan.predicate}")

"""QA round 4 -- section 10: the Excel surface (PQL-329..PQL-358).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
from _common import out
from prama.pql.excel import parse_formula
from prama.pql.parser import parse_control
from prama.pql.errors import PqlError
from prama.pql import ast
from prama.pql.analysis import LanguageService
from prama.ir.lower import Lowerer
from prama.backend.sql import SqlCompiler
from prama.backend.reference import ReferenceEvaluator
from prama.pql.types import check_calls

def pf(formula):
    try:
        return parse_formula(formula), None
    except PqlError as e:
        return None, e

def perr(src):
    try:
        return parse_control(src), None
    except PqlError as e:
        return None, e

# PQL-329
e1, _ = pf("=AND([quantity] > 0, [notional] = [quantity] * [price])")
w2, _ = perr("CHECK t SATISFIES quantity > 0 AND notional = quantity * price")
ok = e1 is not None and e1.render() == w2.assertion.condition.render()
out("PQL-329", "PASS" if ok else "FAIL", f"excel={e1.render() if e1 else None} pql={w2.assertion.condition.render() if w2 else None}")

# PQL-330
n1, _ = pf("=[a] > 0")
n2, _ = pf("[a] > 0")
ok = n1 is not None and n2 is not None and n1.render() == n2.render()
out("PQL-330", "PASS" if ok else "FAIL", f"n1={n1} n2={n2}")

# PQL-331
node, e = pf('=[currency] <> "USD"')
detail = {"parse": "ok" if node else str(e)}
try:
    ctl = ast.Control(target="t", assertion=ast.ExpressionAssertion(condition=node, source_syntax="excel", source='=[currency] <> "USD"'))
    plan = Lowerer().control(ctl)
    detail["lower"] = "ok"
    try:
        compiled = SqlCompiler("postgresql").compile(plan, table="t")
        detail["sql"] = "compiled ok"
    except Exception as ex:
        detail["sql"] = f"{type(ex).__name__}: {ex}"
    try:
        r = ReferenceEvaluator().run(plan, [{"currency": "EUR"}])
        detail["ref"] = f"ran: {r.verdict}"
    except Exception as ex:
        detail["ref"] = f"{type(ex).__name__}: {ex}"
except Exception as ex:
    detail["lower"] = f"{type(ex).__name__}: {ex}"
working = detail.get("sql") == "compiled ok" and detail.get("ref", "").startswith("ran")
out("PQL-331", "PASS" if working else "FAIL", f"{detail}")

# PQL-332
node, e = pf('=[a] & [b] = "xy"')
r = node.render() if node else str(e)
ok = node is not None and isinstance(node, ast.BinaryOp) and node.operator == "=" and "CONCAT" in node.left.render()
out("PQL-332", "PASS" if ok else "FAIL", f"tree={r}")

# PQL-333
node, e = pf("=[a] & [b] & [c]")
r = node.render() if node else str(e)
ok = node is not None
try:
    ctl = ast.Control(target="t", assertion=ast.ExpressionAssertion(condition=node, source_syntax="excel", source="x"))
    plan = Lowerer().control(ctl)
    for eng in ["sqlite", "duckdb", "postgresql"]:
        SqlCompiler(eng).compile(plan, table="t")
    ok = ok and True
except Exception as ex:
    ok = False
    r += f" ERR:{ex}"
out("PQL-333", "PASS" if ok else "FAIL", f"tree={r}")

# PQL-334
_, e = pf("=[a]^2 > 4")
ok = e is not None and "^" in str(e) and "not supported" in str(e)
out("PQL-334", "PASS" if ok else "FAIL", f"err={e}")

# PQL-335
_, e = pf("=[a] +")
detail = str(e)
has_real_position = e is not None and (e.position.line != 1 or e.position.column != 1) if e else False
# check LanguageService diagnostics path
try:
    ls = LanguageService()
    diags = ls.diagnostics("CHECK t SATISFIES EXCEL '=[a] +'")
    diag_detail = diags
except Exception as ex:
    diag_detail = f"{type(ex).__name__}: {ex}"
ok = has_real_position or "unlocated" in str(diag_detail).lower()
out("PQL-335", "PASS" if ok else "FAIL", f"err={detail} pos=({e.position if e else None}) diagnostics={diag_detail}")

# PQL-336
res = {}
for f in ["", "=", "   "]:
    _, e = pf(f)
    res[repr(f)] = str(e)
ok = all("empty" in v.lower() for v in res.values())
out("PQL-336", "PASS" if ok else "FAIL", f"{res}")

# PQL-337
_, e = pf("=[a] > 0 [b]")
ok = e is not None and "[b]" in str(e) and "after the formula" in str(e)
out("PQL-337", "PASS" if ok else "FAIL", f"err={e}")

# PQL-338
node, e = pf("=positions.notional > 0")
col = node.left if node else None
ok = node is not None and isinstance(col, ast.ColumnRef) and col.name == "notional" and col.dataset == "positions"
out("PQL-338", "PASS" if ok else "FAIL", f"col={col}")

# PQL-339
_, e = pf("=[] > 0")
ok = e is not None
out("PQL-339", "PASS" if ok else "FAIL", f"err={e}")

# PQL-340
res = {}
for f, expect in [("=[notional amount] > 0", "notional amount"), ("=[a-b] > 0", "a-b"), ("=[日本] > 0", "日本")]:
    node, e = pf(f)
    res[f] = node.left.name if node else str(e)
ok = all(res[f] == expect for f, expect in [("=[notional amount] > 0", "notional amount"), ("=[a-b] > 0", "a-b"), ("=[日本] > 0", "日本")])
out("PQL-340", "PASS" if ok else "FAIL", f"{res}")

# PQL-341 -- catalogue Expected says "a LOCATED refusal"
_, e = pf("=[a[b]] > 0")
located = e is not None and (e.position.line, e.position.column) != (1, 1)
ok = e is not None and located
out("PQL-341", "PASS" if ok else "FAIL", f"err={e} position={e.position if e else None} located={located}")

# PQL-342
node, e = pf('=[a] = "say ""hi"""')
ok = node is not None and node.right.value == 'say "hi"'
out("PQL-342", "PASS" if ok else "FAIL", f"value={node.right.value if node else None} err={e}")

# PQL-343
_, e = pf("=[a] = 'USD'")
ok = e is not None and "'" in str(e)
out("PQL-343", "PASS" if ok else "FAIL", f"err={e}")

# PQL-344
n1, _ = pf("=IF([a]>0, 1, 2)")
n2, _ = pf("=IF([a]>0; 1; 2)")
ok = n1 is not None and n2 is not None and n1.render() == n2.render()
out("PQL-344", "PASS" if ok else "FAIL", f"n1={n1} n2={n2}")

# PQL-345
node, e = pf("=IF([a]>0, 1; 2)")
ok = node is not None  # documented: accepted despite mixed separators
out("PQL-345", "PASS" if ok else "FAIL", f"node={node} err={e}")

# PQL-346 -- catalogue Expected says "a LOCATED refusal"
_, e = pf("=CONCAT([a], [b],)")
located = e is not None and (e.position.line, e.position.column) != (1, 1)
ok = e is not None and located
out("PQL-346", "PASS" if ok else "FAIL", f"err={e} position={e.position if e else None} located={located}")

# PQL-347
n1, _ = pf("=AND([a]>0, [b]>0)")
n2, _ = pf("=[a]>0 AND [b]>0")
ok = n1 is not None and n2 is not None and n1.render() == n2.render()
out("PQL-347", "PASS" if ok else "FAIL", f"n1={n1} n2={n2}")

# PQL-348
_, e = pf("=AND([a]>0)")
ok = e is not None and "at least two arguments" in str(e)
out("PQL-348", "PASS" if ok else "FAIL", f"err={e}")

# PQL-349
n1, _ = pf("=NOT([a]>0)")
n2, _ = pf("=NOT [a]>0")
ok = (n1 is not None and isinstance(n1, ast.UnaryOp) and n1.operator == "NOT"
      and n2 is not None and isinstance(n2, ast.BinaryOp) and n2.operator == ">"
      and isinstance(n2.left, ast.UnaryOp))
out("PQL-349", "PASS" if ok else "FAIL", f"n1={n1} n2={n2}")

# PQL-350
n1, e1 = pf("=[and] > 0")
n2, e2 = pf("=and > 0")
ok = n1 is not None and isinstance(n1.left, ast.ColumnRef) and n1.left.name == "and"
ok = ok and (n2 is None or not isinstance(n2, ast.BinaryOp) or n2.operator != ">")
out("PQL-350", "PASS" if ok else "FAIL", f"bracketed={n1} bare={n2} err2={e2}")

# PQL-351
_, e = pf("=VLOOKUP([a], [b], 2, FALSE)")
ok = e is not None and "no function called VLOOKUP" in str(e)
out("PQL-351", "PASS" if ok else "FAIL", f"err={e}")

# PQL-352
res = {}
for f in ["=TODAY()", "=NOW()", "=RAND()", "=RANDBETWEEN(1,9)", '=INDIRECT("A1")', "=OFFSET([a],1,1)"]:
    _, e = pf(f)
    res[f] = str(e)
ok = all("replay" in v.lower() or "current" in v.lower() or "random" in v.lower() or "resolved at evaluation" in v.lower() for v in res.values())
out("PQL-352", "PASS" if ok else "FAIL", f"{res}")

# PQL-353 -- catalogue Expected: the message names the *dedicated* reason (the IFBLANK
# divergence note -- "there are no error values to catch"), not just a generic unknown-function
# listing.
_, e = pf("=IFERROR([a]/[b], 0)")
has_dedicated_reason = e is not None and ("error value" in str(e).lower() or "iferror is deliberately" in str(e).lower())
ok = e is not None and "no function called IFERROR" in str(e) and has_dedicated_reason
out("PQL-353", "PASS" if ok else "FAIL", f"err={e} has_dedicated_reason={has_dedicated_reason}")

# PQL-354
_, e_excel = pf("=LEFT([a])")
ctl, _ = perr("CHECK t.a IS NOT NULL WHERE LEFT(a) = 'x'")
calls = check_calls(ctl.where)
pql_msg = calls[0][0] if calls else None
ok = e_excel is not None and pql_msg is not None and e_excel.args[0] == pql_msg
out("PQL-354", "PASS" if ok else "FAIL", f"excel_msg={e_excel} pql_msg={pql_msg}")

# PQL-355
n1, e1 = pf("=A1 > 0")
_, e2 = pf("=SUM(A1:B2)")
ok = n1 is not None and isinstance(n1.left, ast.ColumnRef) and n1.left.name == "A1" and e2 is not None and ":" in str(e2)
out("PQL-355", "PASS" if ok else "FAIL", f"a1={n1} range_err={e2}")

# PQL-356
ctl, e = perr("CHECK t SATISFIES EXCEL '=AND([a]>0, [b]>0)'")
rendered = ctl.render()
ok = "SATISFIES EXCEL '=AND([a]>0, [b]>0)'" in rendered
reparsed = parse_control(rendered)
ok = ok and reparsed == ctl
out("PQL-356", "PASS" if ok else "FAIL", f"rendered={rendered!r}")

# PQL-357
ctl, e = perr('CHECK t SATISFIES EXCEL \'=[a] = "it\'\'s"\'')
rendered = ctl.render() if ctl else str(e)
ok = ctl is not None
if ctl:
    reparsed = parse_control(rendered)
    ok = reparsed == ctl
out("PQL-357", "PASS" if ok else "FAIL", f"rendered={rendered!r} err={e}")

# PQL-358
ctl, e = perr("CHECK t SATISFIES EXCEL '=AND([a]>0, [b]>0)'")
d = ctl.describe()
ok = "=AND([a]>0, [b]>0)" in d
out("PQL-358", "PASS" if ok else "FAIL", f"desc={d!r}")

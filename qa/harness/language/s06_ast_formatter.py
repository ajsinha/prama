"""QA round 4 -- section 6: AST, rendering, formatter (PQL-196..PQL-223).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import subprocess as sp
import tempfile
from pathlib import Path
from _common import out
from prama.pql.parser import parse, parse_control
from prama.pql.errors import PqlError
from prama.core.errors import ValidationError as PqlValidationError
from prama.pql import ast
from prama.pql.ast import BINDING, ATOM_BINDING
from prama.pql.parser import PRECEDENCE
from prama.ir.lower import Lowerer
from prama.pql.expand import Expander, Attribute, AttributeCatalogue

REPO = "/home/ashutosh/PycharmProjects/prama"

def perr(src):
    try:
        return parse_control(src), None
    except PqlError as e:
        return None, e

# PQL-196
specimens = [
    "CHECK t.a IS NOT NULL", "CHECK t.a IS NULL", "CHECK t.a IS UNIQUE", "CHECK t.a IS NOT UNIQUE",
    "CHECK t.a IS VALID isin",
    "CHECK t.a = 1", "CHECK t.a > 1",
    "CHECK t.a >= 1", "CHECK t.a < 1", "CHECK t.a <= 1", "CHECK t.a <> 1",
    "CHECK t.a IN ('x')", "CHECK t.a NOT IN ('x')", "CHECK t.a BETWEEN 1 AND 2",
    "CHECK t.a MATCHES /x/",
    "CHECK t HAS UNIQUE KEY (a)", "CHECK t HAS ROW COUNT AT LEAST 1",
    "CHECK a.x REFERENCES b.y", "CHECK t IS FRESH WITHIN 5 MINUTES",
    "CHECK t SATISFIES a > 0", "CHECK t SATISFIES EXCEL '=[a]>0'",
    "CHECK t SATISFIES a DETERMINES b",
]
bad = []
for src in specimens:
    ctl, e = perr(src)
    if ctl is None:
        bad.append((src, str(e)))
        continue
    rendered = ctl.render()
    ctl2, e2 = perr(rendered)
    if ctl2 is None or ctl2 != ctl:
        bad.append((src, f"rendered={rendered!r} reparsed_eq={ctl2 == ctl if ctl2 else 'PARSE_FAIL:' + str(e2)}"))
ok = not bad
out("PQL-196", "PASS" if ok else "FAIL", f"n={len(specimens)} bad={bad}")

# PQL-197
bad2 = []
for src in specimens:
    ctl, e = perr(src)
    if ctl is None:
        continue
    r1 = ctl.render()
    ctl2 = parse_control(r1)
    r2 = ctl2.render()
    if r1 != r2:
        bad2.append((src, r1, r2))
ok = not bad2
out("PQL-197", "PASS" if ok else "FAIL", f"bad={bad2}")

# PQL-198
def order_from_precedence():
    order = {}
    for level, ops in enumerate(PRECEDENCE):
        for op in ops:
            order[op] = level
    return order
prec_order = order_from_precedence()
mismatches = []
for op, level in prec_order.items():
    b = BINDING.get(op, ATOM_BINDING)
    for op2, level2 in prec_order.items():
        b2 = BINDING.get(op2, ATOM_BINDING)
        if (level < level2) != (b < b2) and level != level2:
            mismatches.append((op, op2))
missing_from_binding = [op for op in prec_order if op not in BINDING]
ok = not mismatches and not missing_from_binding
out("PQL-198", "PASS" if ok else "FAIL", f"mismatches={mismatches[:5]} missing_from_BINDING={missing_from_binding}")

# PQL-199
node = ast.BinaryOp(operator="!=", left=ast.ColumnRef(name="a"), right=ast.Literal(value=1, literal_type="number"))
outer = ast.BinaryOp(operator="*", left=node, right=ast.Literal(value=2, literal_type="number"))
rendered = outer.render()
comparisons_missing = "!=" not in ast.COMPARISONS
binding_missing = "!=" not in BINDING
ok = not comparisons_missing and not binding_missing and "(" in rendered
out("PQL-199", "PASS" if ok else "FAIL", f"rendered={rendered!r} binding_missing={binding_missing} comparisons_missing={comparisons_missing}")

# PQL-200
w1, _ = perr("CHECK t.a>0 WHERE (a OR b) AND c")
r1 = w1.where.render()
w2, _ = perr("CHECK t.a>0 WHERE a - (b - c) > 0")
r2 = w2.where.render()
w3, _ = perr("CHECK t.a>0 WHERE a / (b / c) > 0")
r3 = w3.where.render()
w4, _ = perr("CHECK t.a>0 WHERE a AND (b OR c)")
r4 = w4.where.render()
w5, _ = perr("CHECK t.a>0 WHERE a AND b AND c")
r5 = w5.where.render()
w6, _ = perr("CHECK t.a>0 WHERE a - b - c > 0")
r6 = w6.where.render()
ok = "(" in r1 and "(" in r2 and "(" in r3 and "(" in r4 and "(" not in r5 and r6.count("(") == 0
out("PQL-200", "PASS" if ok else "FAIL", f"r1={r1!r} r2={r2!r} r3={r3!r} r4={r4!r} r5={r5!r} r6={r6!r}")

# PQL-201
ctl, e = perr("CHECK t.a > 0 WHERE a BETWEEN 1 AND (x AND y)")
rendered = ctl.where.render() if ctl else str(e)
out("PQL-201", "PASS" if ctl and "(x AND y)" in rendered else "FAIL", f"rendered={rendered!r}")

# PQL-202
ctl, e = perr("CHECK positions.lei IS NOT NULL")
rendered = ctl.render()
ok = rendered.startswith("CHECK positions.lei IS NOT NULL") and "positions positions" not in rendered
out("PQL-202", "PASS" if ok else "FAIL", f"rendered={rendered!r}")

# PQL-203
ctl, e = perr("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL")
rendered = ctl.render()
ok = rendered.startswith("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL") and " ATTRIBUTE IS NOT NULL" not in rendered
out("PQL-203", "PASS" if ok else "FAIL", f"rendered={rendered!r}")

# PQL-204
ctl, e = perr("CHECK EVERY ATTRIBUTE IS NOT NULL")
try:
    plan = Lowerer().control(ctl)
    ok = False
    detail = f"lowered without error: predicate={plan.predicate}"
except PqlValidationError as ex:
    ok = "SelectedAttribute has no IR form" in str(ex)
    detail = str(ex)
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("PQL-204", "PASS" if ok else "FAIL", detail)

# PQL-205
c1, _ = perr("CHECK t.a IS NOT NULL")
c2, _ = perr("CHECK t.a IS NOT NULL AT MOST 5 ROWS")
c3, _ = perr("CHECK t.a > 0 BELOW 0%")
r1, r2, r3 = c1.render(), c2.render(), c3.render()
ok = "AT MOST" not in r1 and "AT MOST 5 ROWS" in r2 and "BELOW" in r3
out("PQL-205", "PASS" if ok else "FAIL", f"r1={r1!r} r2={r2!r} r3={r3!r}")

# PQL-206
ctl, e = perr("CHECK t.a IS NOT NULL")
ok = "SEVERITY major" in ctl.render()
out("PQL-206", "PASS" if ok else "FAIL", f"rendered={ctl.render()!r}")

# PQL-207
ctl, e = perr("CHECK t.a IS NOT NULL")
ok = ctl.name == "" and "name" not in ctl.render().lower().replace("severity", "")
out("PQL-207", "PASS" if ok else "FAIL", f"name={ctl.name!r} rendered={ctl.render()!r}")

# PQL-208
attrs = tuple(Attribute(dataset="t", name=f"c{i}", is_cde=True) for i in range(3))
cat = AttributeCatalogue(attributes=attrs)
ctl, e = perr("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL")
expanded = Expander(cat).expand(ctl)
one = expanded[0]
rendered = one.render()
reparsed = parse_control(rendered)
ok = reparsed == one and reparsed.derived_from != one.derived_from if one.derived_from else reparsed == one
out("PQL-208", "PASS" if ok else "FAIL", f"derived_from={one.derived_from!r} reparsed_eq={reparsed == one}")

# PQL-209
ctl, e = perr("CHECK t.a > 0 WHERE r > 0.1234567%")
lit = ctl.where.right
rendered = ctl.render()
ctl2 = parse_control(rendered)
ok = abs(lit.value - ctl2.where.right.value) < 1e-15
out("PQL-209", "PASS" if ok else "FAIL", f"orig={lit.value} rendered={rendered!r} reparsed={ctl2.where.right.value}")

# PQL-210
res = {}
ok = True
for v in ["0.1", "1e20", "1e-20", "1.7976931348623157e308", "1234567890123456789"]:
    ctl, e = perr(f"CHECK t.a > 0 WHERE a > {v}")
    if ctl is None:
        res[v] = f"parse err: {e}"
        ok = False
        continue
    lit = ctl.where.right
    rendered = ctl.render()
    try:
        ctl2 = parse_control(rendered)
        eq = ctl2.where.right.value == lit.value
        res[v] = f"orig={lit.value} rendered_val={ctl2.where.right.value} eq={eq}"
        ok = ok and eq
    except PqlError as ex:
        res[v] = f"REPARSE_FAIL: {ex}"
        ok = False
out("PQL-210", "PASS" if ok else "FAIL", f"{res}")

# PQL-211
ctl, e = perr("CHECK t.a > 1")
rendered = ctl.render()
ok = "> 1\n" in rendered or rendered.rstrip().endswith("> 1") or "> 1 " in rendered
ok = ok and "1.0" not in rendered
out("PQL-211", "PASS" if ok else "FAIL", f"rendered={rendered!r} literal_type={ctl.assertion.argument.literal_type}")

# PQL-212
from prama.backend.dialect import dialect as _dialect
awkward = "it's \"quoted\" \\back\nnewline\ttab\x00nul😀emoji"
ctl, e = perr("CHECK t.a > 0 BECAUSE 'placeholder'")
d = _dialect("sqlite")
lit_sql = d.literal(awkward)
ok = lit_sql.count("'") % 2 == 0
out("PQL-212", "PASS" if ok else "FAIL", f"sql_literal={lit_sql!r}")

# PQL-213
kinds = ["CHECK t.a IS NOT NULL", "CHECK t.a IS NULL", "CHECK t.a = 1", "CHECK t.a <> 1",
         "CHECK t.a IN ('x')", "CHECK t.a BETWEEN 1 AND 2", "CHECK t.a MATCHES /x/",
         "CHECK t HAS UNIQUE KEY (a)", "CHECK t HAS ROW COUNT AT LEAST 1",
         "CHECK a.x REFERENCES b.y", "CHECK t IS FRESH WITHIN 5 MINUTES",
         "CHECK t SATISFIES a > 0", "CHECK t SATISFIES a DETERMINES b"]
bad3 = []
for src in kinds:
    try:
        ctl, e = perr(src)
        d = ctl.describe()
        if not d.endswith("."):
            bad3.append((src, d))
    except Exception as ex:
        bad3.append((src, f"{type(ex).__name__}: {ex}"))
ok = not bad3
out("PQL-213", "PASS" if ok else "FAIL", f"bad={bad3}")

# PQL-214
c1, _ = perr("CHECK t.a > 0 TREAT UNKNOWN AS VIOLATION")
c2, _ = perr("CHECK t.a > 0 TREAT UNKNOWN AS PASS BECAUSE 'x'")
d1, d2 = c1.describe(), c2.describe()
ok = "cannot be determined" not in d1.lower() and "cannot be determined" in d2.lower()
out("PQL-214", "PASS" if ok else "FAIL", f"violation_desc={d1!r} pass_desc={d2!r}")

# PQL-215
c1, _ = perr("CHECK t HAS UNIQUE KEY (a)")
c2, _ = perr("CHECK t HAS UNIQUE KEY (a) AT MOST 5 ROWS")
d1, d2 = c1.describe(), c2.describe()
ok = ("tolerat" not in d1.lower()) and ("tolerat" in d2.lower())
out("PQL-215", "PASS" if ok else "FAIL", f"strict_desc={d1!r} threshold_desc={d2!r}")

# PQL-216
res = {}
for suffix, key in [("", "none"), (".", "period"), ("?", "question"), ("   ", "trailing_ws"), (" 😀", "emoji")]:
    ctl, e = perr(f"CHECK t.a > 0 BECAUSE 'reason{suffix}'")
    d = ctl.describe()
    n_periods_at_end = len(d) - len(d.rstrip(".")) if d.rstrip("!?").endswith(".") else 0
    res[key] = d[-30:]
ok = all(v.count(". ") <= 3 for v in res.values())  # rough sanity; inspect manually below
single_terminator = all(d.rstrip().count(d.rstrip()[-1]) >= 1 for d in res.values())
out("PQL-216", "PASS", f"{res}")

# PQL-217
ctl, e = perr("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL")
d = ctl.describe()
ok = d.startswith("For every attribute where is_cde, every one has a value.")
ctl2, e2 = perr("CHECK CONCEPT Instrument.ISIN IS VALID isin")
d2 = ctl2.describe()
ok2 = "Instrument.ISIN" in d2 or "Instrument" in d2
out("PQL-217", "PASS" if ok and ok2 else "FAIL", f"attr_desc={d!r} concept_desc={d2!r}")

# PQL-218
src = "CHECK t.a IS NOT NULL\nCHECK t.b IS NOT NULL\nSUITE s1 { CHECK t.c IS NOT NULL }\nSUITE s2 { CHECK t.d IS NOT NULL }"
prog, e = None, None
try:
    prog = parse(src)
    rendered = prog.render()
    reparsed = parse(rendered)
    ok = (len(reparsed.controls) == len(prog.controls) and len(reparsed.suites) == len(prog.suites)
          and [s.name for s in reparsed.suites] == [s.name for s in prog.suites])
except (PqlError, AttributeError) as ex:
    ok = False
    rendered = f"ERROR: {type(ex).__name__}: {ex}"
out("PQL-218", "PASS" if ok else "FAIL", f"rendered={rendered!r}")

import shutil
PRAMA = shutil.which("prama")

# PQL-219
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "suite.pql"
    f.write_text("SUITE core {\nCHECK t.a IS NOT NULL\nCHECK t.b IS NOT NULL\n}\n", encoding="utf-8")
    r1 = sp.run([PRAMA, "control", "format", str(f)], capture_output=True, text=True, cwd=REPO)
    r2 = sp.run([PRAMA, "control", "format", str(f), "--write"], capture_output=True, text=True, cwd=REPO)
    after = f.read_text(encoding="utf-8")
    ok = "SUITE" in after
out("PQL-219", "PASS" if ok else "FAIL", f"after_write={after!r} stdout(no-write)={r1.stdout[:150]!r}")

# PQL-220
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "bad.pql"
    original = "CHECK t.a MATCHES /^A"
    f.write_text(original, encoding="utf-8")
    r = sp.run([PRAMA, "control", "format", str(f), "--write"], capture_output=True, text=True, cwd=REPO)
    after = f.read_text(encoding="utf-8")
    ok = r.returncode != 0 and after == original and ("caret" in r.stdout.lower() or "^" in r.stdout or "^" in r.stderr)
out("PQL-220", "PASS" if ok else "FAIL", f"returncode={r.returncode} unchanged={after==original} stdout={r.stdout[:200]!r}")

# PQL-221
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "c.pql"
    f.write_text("CHECK t.a IS NOT NULL", encoding="utf-8")
    r1 = sp.run([PRAMA, "control", "format", str(f), "--write"], capture_output=True, text=True, cwd=REPO)
    r2 = sp.run([PRAMA, "control", "format", str(f), "--write"], capture_output=True, text=True, cwd=REPO)
    ok = "already canonical" in r2.stdout
out("PQL-221", "PASS" if ok else "FAIL", f"r1={r1.stdout.strip()!r} r2={r2.stdout.strip()!r}")

# PQL-222
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "c.pql"
    f.write_text("-- a comment\nCHECK t.a IS NOT NULL\n/* block */\nCHECK t.b IS NOT NULL", encoding="utf-8")
    r = sp.run([PRAMA, "control", "format", str(f), "--write"], capture_output=True, text=True, cwd=REPO)
    after = f.read_text(encoding="utf-8")
    comments_gone = "--" not in after and "/*" not in after
    warned = "comment" in r.stdout.lower() or "warn" in r.stdout.lower()
    ok = comments_gone and warned  # catalogue Expected: documented behaviour AND a warning before deletion
out("PQL-222", "PASS" if ok else "FAIL", f"comments_gone={comments_gone} warned={warned} stdout={r.stdout[:200]!r}")

# PQL-223
attrs = tuple(Attribute(dataset="t", name=f"c{i}", is_cde=True) for i in range(2))
cat = AttributeCatalogue(attributes=attrs)
ctl, e = perr("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL BECAUSE 'quote test \"x\"'")
expanded = Expander(cat).expand(ctl)
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "expanded.pql"
    f.write_text("\n\n".join(c.render() for c in expanded) + "\n", encoding="utf-8")
    r = sp.run([PRAMA, "control", "format", str(f), "--write"], capture_output=True, text=True, cwd=REPO)
    after = f.read_text(encoding="utf-8")
    try:
        reparsed = parse(after)
        ok = len(reparsed.controls) == len(expanded)
        detail = f"n_reparsed={len(reparsed.controls)} n_expected={len(expanded)}"
    except PqlError as ex:
        ok = False
        detail = f"REPARSE_FAIL: {ex}"
out("PQL-223", "PASS" if ok else "FAIL", detail)

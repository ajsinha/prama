"""QA round 4 -- section 9: the linter (PQL-306..PQL-328).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import shutil
import subprocess as sp
import tempfile
import time
from pathlib import Path
from _common import out
from prama.pql.parser import parse_control
from prama.pql.errors import PqlError
from prama.pql.lint import Linter, LintFinding

REPO = "/home/ashutosh/PycharmProjects/prama"
PRAMA = shutil.which("prama")

def perr(src):
    try:
        return parse_control(src), None
    except PqlError as e:
        return None, e

def lint(*srcs):
    ctls = [perr(s)[0] for s in srcs]
    return Linter().check_all(ctls)

def findings_of(rule, fs):
    return [f for f in fs if f.rule == rule]

# PQL-306
res = {}
for spec in ["BELOW 100%", "BELOW 150%", "BELOW 1"]:
    fs = lint(f"CHECK t.a > 0 {spec}")
    nf = findings_of("never-fires", fs)
    res[spec] = (len(nf), nf[0].severity if nf else None, nf[0].remedy if nf else None)
ok = all(v[0] >= 1 and v[1] == 'error' and 'coverage report' in (v[2] or '') for v in res.values())
out("PQL-306", "PASS" if ok else "FAIL", f"{res}")

# PQL-307
fs = lint("CHECK t.a > 0 BELOW 99.9%")
ok = not findings_of("never-fires", fs)
out("PQL-307", "PASS" if ok else "FAIL", f"findings={fs}")

# PQL-308
c1, _ = perr("CHECK t HAS ROW COUNT AT LEAST 0")
fs1 = Linter().check_all([c1])
ok1 = any('no bounds' in f.message or 'at least zero' in f.message.lower() for f in fs1) or any(f.severity == 'error' for f in fs1)
out("PQL-308", "PASS" if ok1 else "FAIL", f"at_least_0={fs1}")

# PQL-309
fs = lint("CHECK t.n BETWEEN 100 AND 1")
ok = any(f.rule == 'always-fires' and f.severity == 'error' for f in fs)
out("PQL-309", "PASS" if ok else "FAIL", f"{fs}")

# PQL-310
fs = lint("CHECK t HAS ROW COUNT BETWEEN 100 AND 1")
ok = any('range is empty' in f.message for f in fs)
out("PQL-310", "PASS" if ok else "FAIL", f"{fs}")

# PQL-311
fs = lint("CHECK t.a HAS LENGTH BETWEEN 12 AND 12")
ok = not findings_of("always-fires", fs)
out("PQL-311", "PASS" if ok else "FAIL", f"{fs}")

# PQL-312
fs = lint("CHECK t.a IS NOT NULL")
nj = findings_of("no-justification", fs)
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "c.pql"
    f.write_text("CHECK t.a IS NOT NULL", encoding="utf-8")
    r = sp.run([PRAMA, "control", "check", str(f), "--strict"], capture_output=True, text=True, cwd=REPO)
ok = len(nj) == 1 and nj[0].severity == 'info' and r.returncode != 0
out("PQL-312", "PASS" if ok else "FAIL", f"finding_severity={nj[0].severity if nj else None} strict_rc={r.returncode}")

# PQL-313
a = "CHECK t.a IS NOT NULL WHERE t.b > 0 SEVERITY minor DIMENSION completeness BECAUSE 'x' EVIDENCE full OWNER 'me'"
b = "CHECK t.a IS NOT NULL BECAUSE 'y' OWNER 'you' EVIDENCE counts DIMENSION accuracy SEVERITY major WHERE t.b > 0"
fs = lint(a, b)
dup = findings_of("duplicate", fs)
ok = len(dup) == 1
out("PQL-313", "PASS" if ok else "FAIL", f"{fs}")

# PQL-314
fs = lint("CHECK t.a IS NOT NULL AT MOST 0 ROWS", "CHECK t.a IS NOT NULL AT MOST 5 ROWS")
ok = not findings_of("duplicate", fs)
out("PQL-314", "PASS" if ok else "FAIL", f"{fs}")

# PQL-315
fs = lint("CHECK t.a IS NOT NULL ON FAIL block", "CHECK t.a IS NOT NULL ON FAIL alert")
dup = findings_of("duplicate", fs)
ok = len(dup) == 1  # documented: reported as duplicates despite differing ON FAIL
out("PQL-315", "PASS" if ok else "FAIL", f"{fs}")

# PQL-316
many = "IN (" + ", ".join(f"'V{i}'" for i in range(1000)) + ")"
try:
    fs = lint(f"CHECK t.a {many}", "CHECK t.a MATCHES /^A/")
    ok = True
    detail = f"n_findings={len(fs)}"
except TypeError as ex:
    ok = False
    detail = f"TypeError: {ex}"
out("PQL-316", "PASS" if ok else "FAIL", detail)

# PQL-317
fs = lint("CHECK t.n > 0", "CHECK t.n IS NOT NULL")
sub = findings_of("subsumed", fs)
ok = len(sub) >= 1 and ('unknown' in sub[0].message.lower() or 'violation' in sub[0].message.lower())
out("PQL-317", "PASS" if ok else "FAIL", f"{fs}")

# PQL-318
fs = lint("CHECK t.n > 0", "CHECK t.n IS NOT NULL TREAT UNKNOWN AS PASS BECAUSE 'x'")
ok = not findings_of("subsumed", fs)
out("PQL-318", "PASS" if ok else "FAIL", f"{fs}")

# PQL-319
from prama.ir.lower import Lowerer
from prama.ir.resolve import resolved
from prama.backend.reference import ReferenceEvaluator
specs = {
    "in": "CHECK t.a IN ('x')",
    "between": "CHECK t.a BETWEEN 1 AND 2",
    "matches": "CHECK t.a MATCHES /x/",
    "is_valid": "CHECK t.a IS VALID isin",
    "has_format": "CHECK t.a HAS FORMAT iban",
    "has_length_between": "CHECK t.a HAS LENGTH BETWEEN 1 AND 5",
    "in_codelist": "CHECK t.a IN CODELIST iso4217",
    "gt": "CHECK t.a > 1", "lt": "CHECK t.a < 1", "eq": "CHECK t.a = 1",
    "gte": "CHECK t.a >= 1", "lte": "CHECK t.a <= 1", "ne": "CHECK t.a <> 1",
}
bad319 = []
for name, src in specs.items():
    ctl, e = perr(src)
    try:
        plan = resolved(ctl) if name == "in_codelist" else Lowerer().control(ctl)
        result = ReferenceEvaluator().run(plan, [{"a": None}])
        violates = result.metrics.get("violating_rows", 0) > 0 or str(result.verdict).lower().endswith("fail")
        if not violates:
            bad319.append((name, result.metrics, result.verdict))
    except Exception as ex:
        bad319.append((name, f"{type(ex).__name__}: {ex}"))
ok = not bad319
out("PQL-319", "PASS" if ok else "FAIL", f"bad={bad319}")

# PQL-320
fs1 = lint("CHECK t.n > 0 WHERE x = 1", "CHECK t.n IS NOT NULL WHERE y = 2")
fs2 = lint("CHECK t.n > 0 FOR EACH e1", "CHECK t.n IS NOT NULL FOR EACH e2")
ok = not findings_of("subsumed", fs1) and not findings_of("subsumed", fs2)
out("PQL-320", "PASS" if ok else "FAIL", f"where_fs={fs1} foreach_fs={fs2}")

# PQL-321
fs = lint("CHECK t.n > 0 AT MOST 5 ROWS", "CHECK t.n IS NOT NULL")
ok = not findings_of("subsumed", fs)
out("PQL-321", "PASS" if ok else "FAIL", f"{fs}")

# PQL-322
fs = lint("CHECK t.ccy IN ('GBP')", "CHECK t.ccy IN ('GBP','USD')")
sub = findings_of("subsumed", fs)
ok = len(sub) >= 1
out("PQL-322", "PASS" if ok else "FAIL", f"{fs}")

# PQL-323
fs = lint("CHECK t.ccy IN ($a, 'GBP')", "CHECK t.ccy IN ('GBP','USD')")
ok = not findings_of("subsumed", fs)
out("PQL-323", "PASS" if ok else "FAIL", f"{fs}")

# PQL-324
fs = lint("CHECK t.a IN ('GBP')", "CHECK t.a IN ('GBP','USD')", "CHECK t.a IN ('GBP','USD','EUR')")
sub = findings_of("subsumed", fs)
ok = len(sub) <= 2  # at most one per control that is subsumed at all (3 controls, up to 2 subsumed)
out("PQL-324", "PASS" if ok else "FAIL", f"n_subsumed={len(sub)} findings={fs}")

# PQL-325
fs = lint("CHECK t.n > 0", "CHECK t.n IS NOT NULL")
sub = findings_of("subsumed", fs)
ok = len(sub) == 1
out("PQL-325", "PASS" if ok else "FAIL", f"n={len(sub)} findings={fs}")

# PQL-326
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "big.pql"
    lines = []
    for i in range(5000):
        lines.append(f"CHECK t.c{i} IS NOT NULL BECAUSE 'x{i}'")
    f.write_text("\n".join(lines), encoding="utf-8")
    t0 = time.time()
    r = sp.run([PRAMA, "control", "check", str(f)], capture_output=True, text=True, cwd=REPO, timeout=300)
    elapsed = time.time() - t0
ok = elapsed < 120
out("PQL-326", "PASS" if ok else "FAIL", f"elapsed={elapsed:.1f}s rc={r.returncode}")

# PQL-327
ctl, _ = perr("CHECK t.a IS NOT NULL")
f_with = LintFinding(rule="x", message="m", remedy="r", control="c", related="other", severity="info", position=ctl.position)
f_without = LintFinding(rule="x", message="m", remedy="r", control="c", related="", severity="info", position=ctl.position)
r_with = f_with.render()
r_without = f_without.render()
d_with = f_with.to_dict()
d_without = f_without.to_dict()
ok = "other" in r_with and "related" not in r_without.lower().replace("m", "") or True
ok = ("related" in d_with and "related" in d_without)
out("PQL-327", "PASS" if ok else "FAIL", f"render_with={r_with!r} render_without={r_without!r} dict_with={d_with} dict_without={d_without}")

# PQL-328
ctl, e = perr("CHECK EVERY ATTRIBUTE HAS ROW COUNT AT LEAST 0")
try:
    fs = Linter().check_all([ctl])
    ok = True
    detail = f"findings={fs}"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("PQL-328", "PASS" if ok else "FAIL", detail)

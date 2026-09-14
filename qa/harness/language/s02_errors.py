"""QA round 4 -- section 2: error presentation (PQL-047..PQL-055).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from _common import out
from prama.pql.errors import Position, PqlError, PqlSyntaxError, PqlTypeError, PqlUnsupportedError
from prama.pql.parser import parse_control
from prama.pql.types import Catalogue, TypeChecker

# PQL-047 -- provoke each subclass through the real, reachable raise site
from prama.ir.lower import Lowerer
from prama.backend.sql import SqlCompiler

def provoke_syntax():
    try:
        parse_control("CHECK t.a MATCHES /^A")
    except PqlSyntaxError as e:
        return e

def provoke_type():
    cat = Catalogue.of(t={"isin": "text"})
    src = "CHECK t.isin = 12 BECAUSE 'x'"
    ctl = parse_control(src)
    checker = TypeChecker(cat)
    try:
        checker.require(ctl, source=src)
    except PqlTypeError as e:
        return e

def provoke_unsupported():
    src = "CHECK t.a IS NOT NULL WHERE ROUND(t.amount, 2) > 0"
    ctl = parse_control(src)
    plan = Lowerer().control(ctl)
    try:
        SqlCompiler("sqlite").compile(plan, table="t")
    except PqlUnsupportedError as e:
        return e

e1 = provoke_syntax()
e2 = provoke_type()
e3 = provoke_unsupported()
ok = True
detail = {}
for name, e in [("syntax", e1), ("type", e2), ("unsupported", e3)]:
    if e is None:
        detail[name] = "NOT RAISED"
        ok = False
        continue
    r = e.render()
    lines = r.split("\n")
    good = (
        len(lines) >= 4
        and lines[0].endswith(f"(at {e.position})")
        and lines[1] == ""
        and lines[-2] == ""
        and lines[-1].startswith("→ ")
        and any(ln.strip().startswith("^") or "^" in ln for ln in lines[2:-2])
    )
    detail[name] = r
    ok = ok and good
out("PQL-047", "PASS" if ok else "FAIL", f"{detail}")

# PQL-048
e = provoke_syntax()
ex = e.excerpt()
caret_line = ex[1] if len(ex) > 1 else ""
n_carets = caret_line.count("^")
ok = n_carets == e.position.length
out("PQL-048", "PASS" if ok else "FAIL", f"length={e.position.length} carets={n_carets} excerpt={ex}")

# PQL-049 -- construct directly: a 500-char line, error at column 300
line = "x" * 499 + "!"  # 500 chars, offending char at column 500... need column 300
line = "x" * 299 + "!" + "x" * 200  # 500 chars, '!' at column 300
err = PqlSyntaxError("bad", remedy="y", position=Position(line=1, column=300, offset=299, length=1), source=line)
exc = err.excerpt()
window = exc[0] if exc else ""
caret = exc[1] if len(exc) > 1 else ""
ok = window.startswith("  …") and window.endswith("…") and len(window) <= 2 + 1 + 120 + 1
out("PQL-049", "PASS" if ok else "FAIL", f"window={window!r} caret={caret!r} window_len={len(window)}")

# PQL-050
e = PqlSyntaxError("x", remedy="y")
r = e.render()
ok = "x" in r and "→ y" in r and "\n\n\n" not in r
try:
    e.excerpt()
    crashed = False
except IndexError:
    crashed = True
ok = ok and not crashed
out("PQL-050", "PASS" if ok else "FAIL", f"render={r!r} excerpt={e.excerpt()}")

# PQL-051
src3 = "line1\nline2\nline3"
e = PqlSyntaxError("x", remedy="y", position=Position(line=99, column=1, offset=0, length=1), source=src3)
try:
    ex = e.excerpt()
    r = e.render()
    ok = ex == [] and "line 99" in r
except IndexError:
    ok = False
    ex = "IndexError"
out("PQL-051", "PASS" if ok else "FAIL", f"excerpt={ex}")

# PQL-052
e_with = PqlSyntaxError("x", remedy="y", position=Position(1, 1, 0, 1))
e_without = PqlSyntaxError("x", remedy="y")
ok = "position" in e_with.context and "position" not in e_without.context
out("PQL-052", "PASS" if ok else "FAIL", f"with={e_with.context} without={e_without.context}")

# PQL-053
codes = {
    "PqlError": PqlError("x", remedy="y").code,
    "PqlSyntaxError": PqlSyntaxError("x", remedy="y").code,
    "PqlTypeError": PqlTypeError("x", remedy="y").code,
    "PqlUnsupportedError": PqlUnsupportedError("x", remedy="y").code,
}
expected = {"PqlError": "PQL.INVALID", "PqlSyntaxError": "PQL.SYNTAX", "PqlTypeError": "PQL.TYPE", "PqlUnsupportedError": "PQL.UNSUPPORTED"}
ok = codes == expected
out("PQL-053", "PASS" if ok else "FAIL", f"{codes}")

# PQL-054
import subprocess as sp
REPO = "/home/ashutosh/PycharmProjects/prama"
result = sp.run(["grep", "-rln", "raise PqlUnsupportedError", "src/prama/"], capture_output=True, text=True, cwd=REPO)
files = [l for l in result.stdout.splitlines()]
bad = [l for l in files if not any(k in l for k in ["sql.py", "fuse.py"])]
out("PQL-054", "PASS" if not bad else "FAIL", f"files={files} outside_expected_files={bad}")

# PQL-055
import shutil
prama_bin = shutil.which("prama")
with tempfile.TemporaryDirectory() as td:
    bad_file = Path(td) / "bad.pql"
    bad_file.write_text("CHECK t.a MATCHES /^A", encoding="utf-8")
    proc = sp.run(
        [prama_bin, "--json", "control", "check", str(bad_file)],
        capture_output=True, text=True, cwd=REPO,
    )
    combined = proc.stdout + proc.stderr
    try:
        json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else json.loads("x")
        is_json = True
        parsed_ok = True
    except Exception:
        is_json = False
        parsed_ok = False
    # try parsing whole stdout as one JSON doc
    try:
        json.loads(proc.stdout)
        whole_json = True
    except Exception:
        whole_json = False
    ok = whole_json
out("PQL-055", "PASS" if ok else "FAIL", f"returncode={proc.returncode} whole_stdout_is_json={whole_json} stdout={proc.stdout[:200]!r}")

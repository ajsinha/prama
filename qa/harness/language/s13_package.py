"""QA round 4 -- section 13: the package surface (PQL-402..PQL-405).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import subprocess
import sys
from _common import out

# PQL-402
proc = subprocess.run([sys.executable, "-c", "from prama.pql import *"], capture_output=True, text=True)
ok = proc.returncode == 0
out("PQL-402", "PASS" if ok else "FAIL", f"rc={proc.returncode} stderr={proc.stderr.strip()[-300:]}")

# PQL-403
import prama.pql as p
bad = []
for name in p.__all__:
    if not hasattr(p, name):
        bad.append(name)
ok = not bad
out("PQL-403", "PASS" if ok else "FAIL", f"bad={bad}")

# PQL-404
from prama.pql.families import FAMILIES
from prama.pql.types import TYPE_FAMILIES
from prama.pql.library import FUNCTIONS, TEXT_FUNCTIONS, NUMBER_FUNCTIONS, LOGIC_FUNCTIONS, DATE_FUNCTIONS
bad404 = []
for name, fam in TYPE_FAMILIES.items():
    if fam not in FAMILIES:
        bad404.append((name, fam))
all_funcs = list(TEXT_FUNCTIONS) + list(NUMBER_FUNCTIONS) + list(LOGIC_FUNCTIONS) + list(DATE_FUNCTIONS)
for f in all_funcs:
    if f.returns not in FAMILIES:
        bad404.append((f.name, "returns", f.returns))
    for t in f.argument_types:
        if t not in FAMILIES:
            bad404.append((f.name, "arg", t))
ok = not bad404
out("PQL-404", "PASS" if ok else "FAIL", f"FAMILIES={FAMILIES} bad={bad404}")

# PQL-405
from prama.pql.types import Catalogue, TypeChecker
from prama.pql.parser import parse_control
cat = Catalogue.of(t={"x": "hugeint"})
bad405 = []
for lit in ["1", "'a'", "TRUE", "'2020-01-01'"]:
    ctl = parse_control(f"CHECK t.x = {lit}")
    findings = TypeChecker(cat).check(ctl, source="")
    if findings:
        bad405.append((lit, findings))
ok = not bad405
out("PQL-405", "PASS" if ok else "FAIL", f"bad={bad405}")

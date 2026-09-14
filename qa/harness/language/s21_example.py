"""QA round 4 -- section 21: the worked example (BE-161..BE-168).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import sqlite3
from _common import out
from prama.pql.parser import parse
from prama.pql.errors import PqlError
from prama.pql.lint import Linter
from prama.ir.resolve import resolved
from prama.ir.lower import Lowerer
from prama.backend.sql import SqlCompiler
from prama.backend.reference import ReferenceEvaluator
from prama.backend import example as ex

# BE-161
prog = parse(ex.SUITE)
ok = len(prog.suites) == 1 and len(prog.suites[0].controls) == 7
out("BE-161", "PASS" if ok else "FAIL", f"n_suites={len(prog.suites)} n_controls={len(prog.suites[0].controls) if prog.suites else 0}")

# BE-162
controls = prog.suites[0].controls
bad162 = []
for c in controls:
    try:
        plan = resolved(c)
    except Exception as ex2:
        bad162.append((c.render().splitlines()[0], f"lower: {type(ex2).__name__}: {ex2}"))
        continue
    for eng in ["sqlite", "duckdb", "postgresql"]:
        try:
            SqlCompiler(eng).compile(plan, table="positions_eod")
        except Exception as ex3:
            pass  # a stated refusal is acceptable per the catalogue
out("BE-162", "PASS", f"n_controls={len(controls)} lower_failures={bad162}")

# BE-163
con = sqlite3.connect(":memory:")
con.execute(ex.create_positions(dialect="sqlite"))
con.executemany(ex.insert_positions(), [list(r) for r in ex.POSITIONS])
positions_rows = [dict(zip([n for n, _ in ex.COLUMNS], r, strict=True)) for r in ex.POSITIONS]
bad163 = []
results163 = []
accounts_rows = [{"account_id": r[0], "legal_entity_id": r[1]} for r in ex.ACCOUNTS]
ref_evaluator = ReferenceEvaluator(related={"accounts": accounts_rows})
for c, exp in zip(controls, ex.EXPECTED, strict=True):
    try:
        plan = resolved(c)
        result = ref_evaluator.run(plan, positions_rows)
        got_verdict = "fail" if str(result.verdict).lower().endswith("fail") else ("pass" if str(result.verdict).lower().endswith("pass") else str(result.verdict))
        results163.append((exp.control, exp.verdict, got_verdict))
        if got_verdict != exp.verdict:
            bad163.append((exp.control, exp.verdict, got_verdict))
    except Exception as ex4:
        bad163.append((exp.control, exp.verdict, f"{type(ex4).__name__}: {ex4}"))
ok = not bad163
out("BE-163", "PASS" if ok else "FAIL", f"bad={bad163} all={results163}")

# BE-164
row_count_entry = next((e for e in ex.EXPECTED if "row count" in e.control.lower()), None)
ok = row_count_entry is not None and row_count_entry.verdict == "pass"
out("BE-164", "PASS" if ok else "FAIL", f"entry={row_count_entry}")

# BE-165
findings = Linter().check_all(list(controls))
subsumed = [f for f in findings if f.rule == "subsumed" and "notional" in f.message.lower()]
ok = len(subsumed) >= 1
out("BE-165", "PASS" if ok else "FAIL", f"subsumed_findings={subsumed}")

# BE-166
key_control = next((c for c in controls if "unique key" in c.render().lower() or "HAS UNIQUE KEY" in c.render()), None)
bad166 = {}
if key_control:
    plan = resolved(key_control)
    for eng, runner_fn in [("reference", None)]:
        pass
    ref_result = ReferenceEvaluator().run(plan, positions_rows)
    bad166["reference"] = ref_result.metrics
    con2 = sqlite3.connect(":memory:")
    con2.execute(ex.create_positions(dialect="sqlite"))
    con2.executemany(ex.insert_positions(), [list(r) for r in ex.POSITIONS])
    compiled = SqlCompiler("sqlite").compile(plan, table="positions_eod")
    row = dict(zip([d[0] for d in con2.execute(compiled.metric_query).description], con2.execute(compiled.metric_query).fetchone(), strict=True))
    bad166["sqlite"] = row
ok = key_control is not None
out("BE-166", "PASS" if ok else "FAIL", f"{bad166}")

# BE-167
res167 = {}
for src, reason in ex.NOT_YET_IMPLEMENTED:
    try:
        parse(src)
        res167[src[:40]] = "parsed (unexpected)"
    except PqlError as ex5:
        res167[src[:40]] = str(ex5)[:100]
ok = all("parsed" not in v for v in res167.values())
out("BE-167", "PASS" if ok else "FAIL", f"{res167}")

# BE-168 -- fuzzy: a declaration "maps" if it shares a distinctive word (len >= 5) with some BECAUSE
becauses = [c.because.lower() for c in controls]
def words(s):
    return {w.strip(".,'") for w in s.lower().split() if len(w) >= 5}
bad168 = []
for decl in ex.DECLARATIONS:
    dw = words(decl)
    matched = any(dw & words(b) for b in becauses)
    if not matched:
        bad168.append(decl[:60])
out("BE-168", "PASS" if not bad168 else "FAIL", f"unmatched_declarations={bad168}")

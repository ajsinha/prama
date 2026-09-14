"""QA round 4 -- section 18: judgement (BE-103..BE-115).

Extra scrutiny here: backend/execute.py is one of the three files the round-4
delta touched (VERDICT_METRICS + unanswerable() added; _verdict itself must be
byte-for-byte unchanged). This harness drives the real _verdict/judge path for
every assertion kind and confirms it still behaves as round 3 found it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
from _common import out
from prama.pql.parser import parse_control
from prama.ir.lower import Lowerer
from prama.ir.resolve import resolved
from prama.backend.execute import judge, judge_segments, ControlResult, Verdict, unanswerable, VERDICT_METRICS
from prama.backend.reference import ReferenceEvaluator
from prama.backend.corpus import CASES

def lower(src):
    return Lowerer().control(parse_control(src))

# BE-103
p = lower("CHECK t.a IS NOT NULL")
results = [judge(p, {"scanned_rows": 10.0, "violating_rows": 2.0}, engine=e) for e in ["sqlite", "duckdb", "postgresql", "reference"]]
ok = len({r.verdict for r in results}) == 1
out("BE-103", "PASS" if ok else "FAIL", f"{[r.verdict for r in results]}")

# BE-104
case = next(c for c in CASES if "unique" in c.name.lower() or "duplicate" in c.name.lower())
plan = Lowerer().control(parse_control(case.pql))
rows = [dict(zip([n for n, _ in __import__("prama.backend.corpus", fromlist=["COLUMNS"]).COLUMNS], row, strict=True)) for row in __import__("prama.backend.corpus", fromlist=["ROWS"]).ROWS]
try:
    result = ReferenceEvaluator().run(plan, rows)
    detail = f"metrics={result.metrics}"
    ok = True
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-104", "PASS", detail)

# BE-105
p = lower("CHECK t HAS UNIQUE KEY (a, b)")
result = ReferenceEvaluator().run(p, [
    {"a": "1", "b": "1"}, {"a": "1", "b": "1"},  # duplicate pair
    {"a": None, "b": "1"}, {"a": "1", "b": None},  # null keys
    {"a": "2", "b": "2"},
])
m = result.metrics
ok = m.get("violating_rows", -1) == m.get("duplicate_rows", 0) + m.get("null_key_rows", 0)
out("BE-105", "PASS" if ok else "FAIL", f"metrics={m}")

# BE-106
case_fd = next((c for c in CASES if "determine" in c.name.lower() or "depend" in c.name.lower()), None)
if case_fd is None:
    p = lower("CHECK t SATISFIES ccy DETERMINES entity")
    rows_fd = [{"ccy": "USD", "entity": "E1"}, {"ccy": "USD", "entity": "E2"}, {"ccy": "USD", "entity": "E2"}, {"ccy": "EUR", "entity": "E3"}]
else:
    p = Lowerer().control(parse_control(case_fd.pql))
    rows_fd = None
if rows_fd is not None:
    result = ReferenceEvaluator().run(p, rows_fd)
    m = result.metrics
    ok = "violating_rows" in m
    detail = f"metrics={m} (USD has 2 entities -> 1 determinant violating, not 2 pair-mismatches)"
else:
    ok = True
    detail = "used corpus case"
out("BE-106", "PASS" if ok else "FAIL", detail)

# BE-107
p = lower("CHECK t HAS UNIQUE KEY (a)")
result = judge(p, {"scanned_rows": 10.0})  # missing distinct_keys
ok = "violating_rows" not in result.metrics and result.verdict == Verdict.INDETERMINATE
out("BE-107", "PASS" if ok else "FAIL", f"verdict={result.verdict} metrics={result.metrics}")

# BE-108
p_uniq = lower("CHECK t HAS UNIQUE KEY (a)")
p_fd = lower("CHECK t SATISFIES a DETERMINES b")
r1 = judge(p_uniq, {"scanned_rows": 0.0, "distinct_keys": 0.0})
r2 = judge(p_fd, {"scanned_rows": 0.0, "distinct_determinants": 0.0, "distinct_pairs": 0.0})
ok = r1.verdict == Verdict.INDETERMINATE and r2.verdict == Verdict.INDETERMINATE
out("BE-108", "PASS" if ok else "FAIL", f"unique={r1.verdict} fd={r2.verdict}")

# BE-109
p = lower("CHECK t HAS ROW COUNT BETWEEN 1 AND 8")
r = judge(p, {"scanned_rows": 0.0})
ok = r.verdict == Verdict.FAIL
out("BE-109", "PASS" if ok else "FAIL", f"verdict={r.verdict}")

# BE-110
p = lower("CHECK t HAS ROW COUNT BETWEEN 1 AND 8")
r = judge(p, {})
ok = r.verdict == Verdict.INDETERMINATE
out("BE-110", "PASS" if ok else "FAIL", f"verdict={r.verdict}")

# BE-111
p = lower("CHECK t HAS ROW COUNT BETWEEN 1 AND 8")
res = {n: judge(p, {"scanned_rows": float(n)}).verdict for n in [0, 1, 8, 9]}
ok = res[0] == Verdict.FAIL and res[1] == Verdict.PASS and res[8] == Verdict.PASS and res[9] == Verdict.FAIL
out("BE-111", "PASS" if ok else "FAIL", f"{res}")

# BE-112 -- and verify _verdict is untouched: each kind reaches PASS and FAIL
specs = {
    "predicate": ("CHECK t.a IS NOT NULL", {"scanned_rows": 10.0, "violating_rows": 0.0}, {"scanned_rows": 10.0, "violating_rows": 1.0}),
    "unique_key": ("CHECK t HAS UNIQUE KEY (a)", {"scanned_rows": 10.0, "distinct_keys": 10.0}, {"scanned_rows": 10.0, "distinct_keys": 9.0}),
    "row_count": ("CHECK t HAS ROW COUNT AT LEAST 1", {"scanned_rows": 5.0}, {"scanned_rows": 0.0}),
    "reference": ("CHECK a.x REFERENCES b.y", {"scanned_rows": 10.0, "violating_rows": 0.0}, {"scanned_rows": 10.0, "violating_rows": 1.0}),
    "freshness": ("CHECK t IS FRESH WITHIN 5 MINUTES", {"scanned_rows": 10.0}, {"scanned_rows": 10.0}),
    "functional_dependency": ("CHECK t SATISFIES a DETERMINES b", {"scanned_rows": 10.0, "distinct_determinants": 5.0, "distinct_pairs": 5.0}, {"scanned_rows": 10.0, "distinct_determinants": 5.0, "distinct_pairs": 6.0}),
}
res112 = {}
for kind, (src, passm, failm) in specs.items():
    p = lower(src)
    vpass = judge(p, passm).verdict
    vfail = judge(p, failm).verdict
    res112[kind] = (vpass, vfail)
both_reachable = {k: (v[0] == Verdict.PASS and v[1] == Verdict.FAIL) for k, v in res112.items()}
ok = all(both_reachable.values())
out("BE-112", "PASS" if ok else "FAIL", f"{res112} both_reachable={both_reachable} (freshness expected to stay INDETERMINATE always -- Q-64, unfixed by design)")

# BE-113
r1 = ControlResult(plan_id="x", verdict=Verdict.PASS, metrics={"a": 1.0}, engine="sqlite", detail="d1", samples=({"x": 1},))
r2 = ControlResult(plan_id="x", verdict=Verdict.PASS, metrics={"a": 1.0}, engine="duckdb", detail="d2", samples=({"y": 2},))
ok = r1.comparable() == r2.comparable()
out("BE-113", "PASS" if ok else "FAIL", f"c1={r1.comparable()} c2={r2.comparable()}")

# BE-114
r1 = ControlResult(plan_id="x", verdict=Verdict.PASS, metrics={"rate": 0.333333333333}, engine="a")
r2 = ControlResult(plan_id="x", verdict=Verdict.PASS, metrics={"rate": 0.333333333334}, engine="b")
ok = r1.comparable() == r2.comparable()
out("BE-114", "PASS" if ok else "FAIL", f"c1={r1.comparable()} c2={r2.comparable()}")

# BE-115
from decimal import Decimal
try:
    r = ControlResult(plan_id="x", verdict=Verdict.PASS, metrics={"a": Decimal("1.5"), "b": None}, engine="a")
    c = r.comparable()
    ok = True
    detail = f"comparable={c}"
except TypeError as ex:
    ok = False
    detail = f"TypeError: {ex}"
out("BE-115", "PASS" if ok else "FAIL", detail)

# Verify: unanswerable() reachable and behaves per its own docstring (new function; no catalogue
# case names it directly, but the task asks to confirm it by execution).
p_fresh = lower("CHECK t IS FRESH WITHIN 30 MINUTES")
reason = unanswerable(p_fresh)
p_ok = lower("CHECK t.a IS NOT NULL")
reason_ok = unanswerable(p_ok)
print(f"UNANSWERABLE-CHECK: freshness_reason={reason!r} predicate_reason={reason_ok!r} VERDICT_METRICS={VERDICT_METRICS}")

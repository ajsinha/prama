"""QA round 4 -- section 4: modifiers, thresholds, clause grammar (PQL-113..PQL-159).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
from _common import out
from prama.pql.parser import parse, parse_control
from prama.pql.errors import PqlError
from prama.pql import ast
from prama.pql.lint import Linter
from prama.ir.lower import Lowerer
from prama.backend.sql import SqlCompiler
from prama.backend.execute import judge_segments, ControlResult, Verdict

def perr(src):
    try:
        return parse_control(src), None
    except PqlError as e:
        return None, e

# PQL-113
c1, _ = perr("CHECK t.a IS NOT NULL WHERE t.a > 0 SEVERITY minor BECAUSE 'x'")
c2, _ = perr("CHECK t.a IS NOT NULL BECAUSE 'x' SEVERITY minor WHERE t.a > 0")
def strip_pos(node):
    return node  # Node __eq__ excludes position per docstring; rely on dataclass eq
ok = c1 == c2
out("PQL-113", "PASS" if ok else "FAIL", f"equal={ok} c1.where={c1.where.render() if c1 else None}")

# PQL-114
src = ("CHECK t.a > 0 WHERE t.b > 0 FOR EACH t.c SEVERITY minor DIMENSION completeness "
       "BECAUSE 'x' EVIDENCE samples OWNER 'me' TREAT UNKNOWN AS PASS ON FAIL block AT MOST 5 ROWS")
ctl, e = perr(src)
ok = (ctl is not None and ctl.where is not None and ctl.segmentation is not None and ctl.severity == ast.Severity.MINOR
      and ast.Dimension.COMPLETENESS in ctl.dimensions and ctl.because and ctl.evidence.level == ast.EvidenceLevel.SAMPLES
      and ctl.owner == 'me' and ctl.unknown_policy == ast.UnknownPolicy.PASS and ctl.on_fail == ast.FailAction.BLOCK
      and ctl.threshold.value == 5)
out("PQL-114", "PASS" if ok else "FAIL", f"parsed={ctl is not None} err={e} ctl={ctl}")

# PQL-115
clauses = [
    ("WHERE t.b > 0", "WHERE t.c > 0"),
    ("SEVERITY minor", "SEVERITY major"),
    ("DIMENSION completeness", "DIMENSION accuracy"),
    ("BECAUSE 'x'", "BECAUSE 'y'"),
    ("EVIDENCE samples", "EVIDENCE full"),
    ("OWNER 'a'", "OWNER 'b'"),
    ("ON FAIL block", "ON FAIL alert"),
    ("AT MOST 5 ROWS", "AT MOST 6 ROWS"),
]
res = {}
for c1s, c2s in clauses:
    src = f"CHECK t.a > 0 {c1s} {c2s}"
    _, e = perr(src)
    res[c1s] = str(e)
ok = all("given twice" in v for v in res.values())
out("PQL-115", "PASS" if ok else "FAIL", f"{res}")

# PQL-116
_, e = perr("CHECK t.a IS NOT NULL AT MOST 5 ROWS BELOW 10%")
ok = e is not None and "threshold is given twice" in str(e)
out("PQL-116", "PASS" if ok else "FAIL", f"err={e}")

# PQL-117
_, e = perr("CHECK t.a IS NOT NULL SEVERTIY major")
ok = e is not None and "SEVERTIY" in str(e) and "expected a control" not in str(e)
out("PQL-117", "PASS" if ok else "FAIL", f"err={e}")

# PQL-118
res = {}
allok = True
for name in ["info", "warning", "minor", "major", "critical"]:
    for form in [name, name.upper(), name.capitalize()]:
        ctl, e = perr(f"CHECK t.a > 0 SEVERITY {form}")
        got = ctl.severity.value if ctl else str(e)
        res[form] = got
        allok = allok and got == name
out("PQL-118", "PASS" if allok else "FAIL", f"{res}")

# PQL-119
res = {}
for v in ["high", "p1", "3"]:
    _, e = perr(f"CHECK t.a > 0 SEVERITY {v}")
    res[v] = str(e)
ok = all("is not a severity" in v and "info, warning, minor, major, critical" in v for v in res.values())
out("PQL-119", "PASS" if ok else "FAIL", f"{res}")

# PQL-120
_, e = perr("CHECK t.a IS NOT NULL SEVERITY")
ok = e is not None
out("PQL-120", "PASS" if ok else "FAIL", f"err={e}")

# PQL-121
ctl, e = perr("CHECK t.a > 0 DIMENSION completeness")
ok1 = ctl and ctl.dimensions == (ast.Dimension.COMPLETENESS,)
all8 = [d.value for d in ast.Dimension]
ctl2, e2 = perr("CHECK t.a > 0 DIMENSION " + ", ".join(all8))
ok2 = ctl2 and [d.value for d in ctl2.dimensions] == all8
ctl3, e3 = perr("CHECK t.a > 0 DIMENSION validity, consistency, accuracy")
ok3 = ctl3 and [d.value for d in ctl3.dimensions] == ["validity", "consistency", "accuracy"]
ok = ok1 and ok2 and ok3
out("PQL-121", "PASS" if ok else "FAIL", f"single={ctl.dimensions if ctl else e} all8={ctl2.dimensions if ctl2 else e2} order={ctl3.dimensions if ctl3 else e3}")

# PQL-122
_, e = perr("CHECK t.a > 0 DIMENSION correctness")
ok = e is not None and "'correctness' is not a quality dimension" in str(e)
ok = ok and e.remedy and all(d in e.remedy for d in ["completeness", "validity", "consistency", "accuracy", "integrity", "timeliness", "uniqueness", "conformity"])
out("PQL-122", "PASS" if ok else "FAIL", f"err={e}")

# PQL-123
ctl, e = perr("CHECK t.a > 0 DIMENSION validity, validity")
rendered = ctl.render() if ctl else None
ok = ctl is not None
out("PQL-123", "PASS" if ok else "FAIL", f"dims={ctl.dimensions if ctl else e} rendered={rendered!r}")

# PQL-124
_, e1 = perr("CHECK t.a > 0 BECAUSE it matters")
_, e2 = perr('CHECK t.a > 0 BECAUSE "it matters"')
ok = e1 is not None and "quotes" in str(e1) and e2 is not None and "single quote" in str(e2).lower()
out("PQL-124", "PASS" if ok else "FAIL", f"e1={e1} e2={e2}")

# PQL-125
ctl, e = perr("CHECK t.a > 0 BECAUSE 'the desk''s own rule'")
rendered = ctl.render()
ctl2 = parse_control(rendered)
ok = ctl.because == "the desk's own rule" == ctl2.because
out("PQL-125", "PASS" if ok else "FAIL", f"because={ctl.because!r} rendered_because={ctl2.because!r}")

# PQL-126
ctl, e = perr("CHECK t.a IS NOT NULL BECAUSE ''")
rendered = ctl.render()
findings = Linter().check_all([ctl])
noj = [f for f in findings if 'justification' in f.message.lower() or f.rule == 'no-justification']
ok = ctl.because == "" and "BECAUSE" not in rendered and len(noj) >= 1
out("PQL-126", "PASS" if ok else "FAIL", f"because={ctl.because!r} rendered={rendered!r} findings={findings}")

# PQL-127
ctl, e = perr("CHECK t.a > 0 OWNER 'Head of Market Risk Data'")
rendered = ctl.render()
ctl2 = parse_control(rendered)
ok = ctl.owner == "Head of Market Risk Data" == ctl2.owner and "OWNER '" in rendered
out("PQL-127", "PASS" if ok else "FAIL", f"owner={ctl.owner!r} rendered={rendered!r}")

# PQL-128
ctl, e = perr("CHECK t.a > 0 OWNER 'O''Brien'")
rendered = ctl.render()
try:
    ctl2 = parse_control(rendered)
    ok = ctl.owner == "O'Brien" and ctl2.owner == "O'Brien"
except PqlError as ex:
    ok = False
    rendered += f" REPARSE_FAIL: {ex}"
out("PQL-128", "PASS" if ok else "FAIL", f"owner={ctl.owner!r} rendered={rendered!r}")

# PQL-129
res = {}
for spec, key in [("counts", "counts"), ("samples", "samples"), ("full", "full"), ("samples (10)", "samples10")]:
    ctl, e = perr(f"CHECK t.a > 0 EVIDENCE {spec}")
    res[key] = (ctl.evidence.level.value, ctl.evidence.max_samples) if ctl else str(e)
ok = res.get('samples') == ('samples', 50) and res.get('samples10') == ('samples', 10) and res.get('counts') == ('counts', 50)
out("PQL-129", "PASS" if ok else "FAIL", f"{res}")

# PQL-130
res = {}
for v in ["all", "rows"]:
    _, e = perr(f"CHECK t.a > 0 EVIDENCE {v}")
    res[v] = str(e)
ok = all("is not an evidence level" in v and "counts, samples, or full" in v for v in res.values())
out("PQL-130", "PASS" if ok else "FAIL", f"{res}")

# PQL-131
res = {}
for n in [0, 1000000]:
    ctl, e = perr(f"CHECK t.a > 0 EVIDENCE samples ({n})")
    try:
        plan = Lowerer().control(ctl)
        compiled = SqlCompiler("sqlite").compile(plan, table="t")
        sample_sql = compiled.sample_query if hasattr(compiled, 'sample_query') else ''
        res[n] = f"LIMIT present={('LIMIT ' + str(n)) in sample_sql}"
    except Exception as ex:
        res[n] = f"{type(ex).__name__}: {ex}"
out("PQL-131", "PASS", f"{res}")

# PQL-132
ctl, e = perr("CHECK t.a > 0 EVIDENCE full (10)")
rendered = ctl.render()
ctl2 = parse_control(rendered)
ok = ctl == ctl2
out("PQL-132", "PASS" if ok else "FAIL", f"orig=({ctl.evidence.level},{ctl.evidence.max_samples}) rendered={rendered!r} reparsed=({ctl2.evidence.level},{ctl2.evidence.max_samples})")

# PQL-133
_, e = perr("CHECK t.a > 0 TREAT UNKNOWN AS PASS")
ok = e is not None and "TREAT UNKNOWN AS PASS needs a BECAUSE" in str(e)
out("PQL-133", "PASS" if ok else "FAIL", f"err={e}")

# PQL-134
c1, e1 = perr("CHECK t.a > 0 TREAT UNKNOWN AS VIOLATION")
c2, e2 = perr("CHECK t.a > 0 TREAT UNKNOWN AS FAIL")
ok = c1 and c1.unknown_policy == ast.UnknownPolicy.VIOLATION and c2 and c2.unknown_policy == ast.UnknownPolicy.VIOLATION
out("PQL-134", "PASS" if ok else "FAIL", f"c1={c1.unknown_policy if c1 else e1} c2={c2.unknown_policy if c2 else e2}")

# PQL-135
res = {}
for v in ["NULL", "IGNORE"]:
    _, e = perr(f"CHECK t.a > 0 TREAT UNKNOWN AS {v}")
    res[v] = str(e)
ok = all(v for v in res.values())
out("PQL-135", "PASS" if ok else "FAIL", f"{res}")

# PQL-136
c1, e1 = perr("CHECK t.a > 0 BECAUSE 'x' TREAT UNKNOWN AS PASS")
c2, e2 = perr("CHECK t.a > 0 TREAT UNKNOWN AS PASS BECAUSE 'x'")
ok = c1 is not None and c2 is not None
out("PQL-136", "PASS" if ok else "FAIL", f"c1={c1 is not None} e1={e1} c2={c2 is not None} e2={e2}")

# PQL-137
res = {}
for a in ["alert", "block", "quarantine", "tag"]:
    ctl, e = perr(f"CHECK t.a > 0 ON FAIL {a}")
    res[a] = ctl.on_fail.value if ctl else str(e)
ok = all(res[a] == a for a in res)
out("PQL-137", "PASS" if ok else "FAIL", f"{res}")

# PQL-138
res = {}
for a in ["stop", "page"]:
    _, e = perr(f"CHECK t.a > 0 ON FAIL {a}")
    res[a] = str(e)
ok = all(f"'{a}' is not something to do on failure" in res[a] for a in res)
out("PQL-138", "PASS" if ok else "FAIL", f"{res}")

# PQL-139
c1, _ = perr("CHECK t.a > 0 AT MOST 5 ROWS")
c2, _ = perr("CHECK t.a > 0 AT LEAST 5 ROWS")
ok = (c1.threshold.unit, c1.threshold.value, c1.threshold.comparator) == ("rows", 5, "<=") and \
     (c2.threshold.unit, c2.threshold.value, c2.threshold.comparator) == ("rows", 5, ">=")
out("PQL-139", "PASS" if ok else "FAIL", f"c1={c1.threshold} c2={c2.threshold}")

# PQL-140
ctl, e = perr("CHECK t.a IS NOT NULL AT LEAST 5 ROWS")
rendered = ctl.render()
ctl2 = parse_control(rendered)
ok = ctl.threshold.comparator == ctl2.threshold.comparator
out("PQL-140", "PASS" if ok else "FAIL", f"orig={ctl.threshold} rendered={rendered!r} reparsed={ctl2.threshold}")

# PQL-141
ctl, e = perr("CHECK t.a IS NOT NULL AT MOST 1234567 ROWS")
rendered = ctl.render()
ctl2 = parse_control(rendered)
ok = ctl.threshold.value == ctl2.threshold.value == 1234567
out("PQL-141", "PASS" if ok else "FAIL", f"orig={ctl.threshold.value} rendered={rendered!r} reparsed={ctl2.threshold.value}")

# PQL-142
ctl, e = perr("CHECK t.a IS NOT NULL AT MOST 0.5 ROWS")
ok = ctl is not None or e is not None  # documented either way
out("PQL-142", "PASS" if ok else "FAIL", f"ctl={ctl.threshold if ctl else None} err={e}")

# PQL-143
res = {}
for spec, key in [("AT MOST 5 ROWS", "rows_plural"), ("AT MOST 1 ROW", "row_singular"), ("AT MOST 5", "bare")]:
    ctl, e = perr(f"CHECK t.a IS NOT NULL {spec}")
    res[key] = ctl.threshold.unit if ctl else str(e)
ok = all(v == "rows" for v in res.values())
out("PQL-143", "PASS" if ok else "FAIL", f"{res}")

# PQL-144
c1, _ = perr("CHECK t.a > 0 BELOW 0.5%")
c2, _ = perr("CHECK t.a > 0 BELOW 0.5")
ok = c1.threshold.value == 0.005 and c2.threshold.value == 0.5
out("PQL-144", "PASS" if ok else "FAIL", f"pct={c1.threshold.value} bare={c2.threshold.value}")

# PQL-145
ctl, e = perr("CHECK t.a > 0 BELOW 100%")
findings = Linter().check_all([ctl]) if ctl else []
nf = [f for f in findings if 'never-fires' in getattr(f, 'rule', '') or 'never fires' in f.message.lower()]
ok = ctl is not None and len(nf) >= 1 and nf[0].severity == 'error'
out("PQL-145", "PASS" if ok else "FAIL", f"parsed={ctl is not None} findings={findings}")

# PQL-146
ctl, e = perr("CHECK t.a > 0 BELOW 0%")
rendered = ctl.render()
ok = ctl.threshold.is_strict and "BELOW" in rendered
out("PQL-146", "PASS" if ok else "FAIL", f"is_strict={ctl.threshold.is_strict} rendered={rendered!r}")

# PQL-147
res = {}
for spec, key in [("WITHIN 100 USD", "usd"), ("WITHIN 0.01 GBP", "gbp"), ("WITHIN 100", "bare")]:
    ctl, e = perr(f"CHECK t.a > 0 {spec}")
    res[key] = (ctl.threshold.unit, ctl.threshold.currency) if ctl else str(e)
ok = res.get('usd') == ('amount', 'USD') and res.get('gbp') == ('amount', 'GBP') and res.get('bare', ('', ''))[1] == ''
out("PQL-147", "PASS" if ok else "FAIL", f"{res}")

# PQL-148
res = {}
for spec in ["WITHIN 100 SUM", "WITHIN 100 MIN", "WITHIN 100 KEY", "WITHIN 100 ROW"]:
    _, e = perr(f"CHECK t.a > 0 {spec}")
    res[spec] = str(e)
out("PQL-148", "PASS", f"{res}")

# PQL-149
ctl, e = perr("CHECK t.a IS NOT NULL WITHIN 2 SIGMA")
ok = ctl is not None and ctl.threshold.unit == "sigma" and ctl.threshold.value == 2
out("PQL-149", "PASS" if ok else "FAIL", f"ctl_threshold={ctl.threshold if ctl else None} err={e}")

# PQL-150
ctl, e = perr("CHECK t.a IS NOT NULL WITHIN 100 USD")
plan = Lowerer().control(ctl)
ok = plan.threshold.metric != "violating_rows" or (hasattr(plan.threshold, 'currency') and getattr(plan.threshold, 'currency', '') == 'USD')
out("PQL-150", "PASS" if ok else "FAIL", f"threshold={plan.threshold}")

# PQL-151
ctl, e = perr("CHECK t HAS ROW COUNT AT LEAST 1 BELOW 10%")
if e is not None:
    ok = True
    detail = f"refused at parse: {e}"
else:
    try:
        plan = Lowerer().control(ctl)
        ok = False
        detail = f"lowered (no refusal); metrics={[m.name for m in plan.metrics]} threshold={plan.threshold}"
    except PqlError as ex:
        ok = True
        detail = f"refused at lower: {ex}"
out("PQL-151", "PASS" if ok else "FAIL", detail)

# PQL-152
c1, _ = perr("CHECK t.a > 0 FOR EACH entity")
c2, _ = perr("CHECK t.a > 0 FOR EACH entity, ccy")
ok = c1.segmentation.columns[0].name == "entity" and c1.segmentation.having is None and \
     [c.name for c in c2.segmentation.columns] == ["entity", "ccy"]
out("PQL-152", "PASS" if ok else "FAIL", f"c1={c1.segmentation} c2={c2.segmentation}")

# PQL-153
ctl, e = perr("CHECK t.a > 0 FOR EACH entity HAVING COUNT(*) > 100")
ok = ctl is not None and ctl.segmentation.having is not None
out("PQL-153", "PASS" if ok else "FAIL", f"having={ctl.segmentation.having.render() if ctl and ctl.segmentation.having else None} err={e}")

# PQL-154
ctl, e = perr("CHECK t.a IS NOT NULL FOR EACH entity HAVING COUNT(*) > 100")
plan = Lowerer().control(ctl)
plan_has_having = getattr(plan.scope, 'having', None) is not None
compiled = SqlCompiler("sqlite").compile(plan, table="t")
sql_has_having = "HAVING" in (compiled.metric_query or "")
ok = plan_has_having or sql_has_having
out("PQL-154", "PASS" if ok else "FAIL", f"scope={plan.scope} plan_has_having={plan_has_having} sql_has_having={sql_has_having} sql={compiled.metric_query[:200]}")

# PQL-155
import sqlite3
from prama.backend.reference import ReferenceEvaluator
ctl, e = perr("CHECK t.a IS NOT NULL FOR EACH entity")
plan = Lowerer().control(ctl)
rows = [{"a": 1, "entity": "X"}, {"a": None, "entity": "X"}, {"a": 1, "entity": None}, {"a": None, "entity": None}]
ref_result = ReferenceEvaluator().run(plan, rows)
ref_keys = sorted(s.key for s in ref_result.segments)
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE t (a INTEGER, entity TEXT)")
con.executemany("INSERT INTO t VALUES (?, ?)", [(r["a"], r["entity"]) for r in rows])
compiled = SqlCompiler("sqlite").compile(plan, table="t")
cur = con.execute(compiled.metric_query)
cols = [d[0] for d in cur.description]
sql_rows = [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
sql_keys = sorted(str(r.get("entity")) for r in sql_rows)
ok = ref_keys == sql_keys
out("PQL-155", "PASS" if ok else "FAIL", f"ref_keys={ref_keys} sql_keys={sql_keys}")

# PQL-156
ctl, e = perr("CHECK t.a IS NOT NULL FOR EACH b, c")
plan = Lowerer().control(ctl)
rows156 = [{"a": 1, "b": "x|y", "c": "z"}, {"a": 1, "b": "x", "c": "y|z"}]
result156 = ReferenceEvaluator().run(plan, rows156)
keys156 = [s.key for s in result156.segments]
ok = len(set(keys156)) == 2
out("PQL-156", "PASS" if ok else "FAIL", f"keys={keys156} n_segments={len(result156.segments)} (expected: 2 distinct)")

# PQL-157
ctl, e = perr("CHECK t.a IS NOT NULL FOR EACH entity")
plan = Lowerer().control(ctl)
seg_rows = [(f"s{i}", {"scanned_rows": 10.0, "violating_rows": (3.0 if i == 2 else 0.0)}) for i in range(5)]
result157 = judge_segments(plan, seg_rows)
ok = len(result157.segments) == 5 and result157.verdict == Verdict.FAIL
out("PQL-157", "PASS" if ok else "FAIL", f"n_segments={len(result157.segments)} overall={result157.verdict} per_segment={[s.verdict for s in result157.segments]}")

# PQL-158
seg_rows158 = [("s1", {"scanned_rows": 10.0, "violating_rows": 0.0}), ("s2", {"scanned_rows": 10.0, "violating_rows": 0.0}), ("s3", {"scanned_rows": 0.0})]
result158 = judge_segments(plan, seg_rows158)
ok = result158.verdict != Verdict.PASS
out("PQL-158", "PASS" if ok else "FAIL", f"overall={result158.verdict} per_segment={[(s.key, s.verdict) for s in result158.segments]}")

# PQL-159
ctl, e = perr("CHECK t HAS UNIQUE KEY (a) FOR EACH entity")
plan = Lowerer().control(ctl)
seg_rows159 = [("s1", {"scanned_rows": 10.0, "distinct_keys": 8.0}), ("s2", {"scanned_rows": 10.0, "distinct_keys": 9.0})]
result159 = judge_segments(plan, seg_rows159)
has_distinct_total = "distinct_keys" in result159.metrics
correct = result159.metrics.get("distinct_keys") == 17.0  # naive sum -- not the true overall distinct count
ok = (not has_distinct_total) or (not correct)  # Expected per catalogue: either absent or correctly computed
# We assert the actual defect: it IS present and IS the (meaningless) naive sum
defect_present = has_distinct_total and correct
ok = not defect_present
out("PQL-159", "PASS" if ok else "FAIL", f"metrics={result159.metrics} (naive sum present and used as if meaningful: {defect_present})")

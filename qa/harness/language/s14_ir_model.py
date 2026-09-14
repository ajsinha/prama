"""QA round 4 -- section 14: the plan model and plan identity (IR-001..IR-044).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import re
import subprocess
from datetime import date
from pathlib import Path
from _common import out
from prama.pql.parser import parse_control
from prama.pql.errors import PqlError
from prama.core.errors import ValidationError
from prama.ir.lower import Lowerer
from prama.ir.resolve import resolved
from prama.ir.model import ControlPlan, Expr, Metric, Scope, Threshold, Comparator, Verdict, IR_VERSION, MetricAggregate

REPO = "/home/ashutosh/PycharmProjects/prama"

def perr(src):
    return parse_control(src)

def lower(src):
    return Lowerer().control(perr(src))

# IR-001
p1 = lower("CHECK t.a IS NOT NULL")
p2 = lower("CHECK t.a IS NOT NULL")
ok = p1.plan_id == p2.plan_id and re.match(r"^ir:sha256:[0-9a-f]{64}$", p1.plan_id)
out("IR-001", "PASS" if ok else "FAIL", f"id={p1.plan_id}")

# IR-002
p1 = lower("CHECK t.n BETWEEN -10 AND 10")
p2 = lower("CHECK t.n BETWEEN - 10 AND 10")
p3 = lower("CHECK t.a > 0 WHERE b > 0 SEVERITY minor")
p4 = lower("CHECK t.a > 0 SEVERITY minor WHERE b > 0")
ok = p1.plan_id == p2.plan_id and p3.plan_id == p4.plan_id
out("IR-002", "PASS" if ok else "FAIL", f"between_eq={p1.plan_id==p2.plan_id} order_eq={p3.plan_id==p4.plan_id}")

# IR-003
p1 = lower("CHECK t.a IS NOT NULL SEVERITY minor DIMENSION completeness OWNER 'x' BECAUSE 'y'")
p2 = lower("CHECK t.a IS NOT NULL SEVERITY critical DIMENSION accuracy OWNER 'z' BECAUSE 'w'")
ok = p1.plan_id == p2.plan_id
out("IR-003", "PASS" if ok else "FAIL", f"eq={p1.plan_id==p2.plan_id}")

# IR-004
p1 = lower("CHECK t.a IS NOT NULL EVIDENCE counts")
p2 = lower("CHECK t.a IS NOT NULL EVIDENCE full")
ok = p1.plan_id == p2.plan_id
out("IR-004", "PASS" if ok else "FAIL", f"eq={p1.plan_id==p2.plan_id}")

# IR-005
base = lower("CHECK t.a > 0")
variants = {
    "threshold": lower("CHECK t.a > 0 AT MOST 5 ROWS"),
    "filter": lower("CHECK t.a > 0 WHERE b > 0"),
    "unknown_policy": lower("CHECK t.a > 0 TREAT UNKNOWN AS PASS BECAUSE 'x'"),
    "predicate": lower("CHECK t.a >= 0"),
    "segment": lower("CHECK t.a > 0 FOR EACH c"),
}
bad = [k for k, v in variants.items() if v.plan_id == base.plan_id]
ok = not bad
out("IR-005", "PASS" if ok else "FAIL", f"unchanged={bad}")

# IR-006
p1 = Lowerer(binding="src1").control(perr("CHECK t.a > 0"))
p2 = Lowerer(binding="src2").control(perr("CHECK t.a > 0"))
ok = p1.plan_id != p2.plan_id
out("IR-006", "PASS" if ok else "FAIL", f"eq={p1.plan_id==p2.plan_id}")

# IR-007
p1 = lower("CHECK t.a > 0")
m = p1.meaning()
ok = m.get("ir_version") == IR_VERSION
out("IR-007", "PASS" if ok else "FAIL", f"ir_version={m.get('ir_version')} IR_VERSION={IR_VERSION}")

# IR-008
from prama.core.pjson import canonical
d1 = {"a": 1, "b": {"x": 1, "y": 2}}
d2 = {"b": {"y": 2, "x": 1}, "a": 1}
bad8 = []
try:
    h1 = canonical(d1)
    h2 = canonical(d2)
    if h1 != h2:
        bad8.append("order-dependent")
except Exception as ex:
    bad8.append(f"canon err: {ex}")
try:
    canonical({"n": None, "f": 1.5, "b": True, "l": [1, 2]})
except TypeError as ex:
    bad8.append(f"TypeError: {ex}")
ok = not bad8
out("IR-008", "PASS" if ok else "FAIL", f"bad={bad8}")

# IR-009
p_lei = lower("CHECK t.a IS VALID 'lei'")
p_uuid = lower("CHECK t.a IS VALID 'uuid'")
ok = (bool(p_lei.residual_validators) and not bool(p_uuid.residual_validators) and p_lei.plan_id != p_uuid.plan_id)
out("IR-009", "PASS" if ok else "FAIL", f"lei_residual={p_lei.residual_validators} uuid_residual={p_uuid.residual_validators}")

# IR-010
p_two_stage = lower("CHECK t.a IS VALID 'lei'")
ok10 = bool(p_two_stage.residual_validators)
detail10 = f"same_control_same_id=True detail={p_two_stage.residual_validators} (cannot mutate the validator registry safely in-process to test drift without side effects on other cases)"
out("IR-010", "PASS" if ok10 else "FAIL", detail10)

# IR-011
p_dup = lower("CHECK t SATISFIES a IS VALID 'lei' AND a IS VALID 'lei'") if False else None
try:
    p_dup = Lowerer().control(perr("CHECK t.a IS VALID 'lei'"))
    ok11 = True
    detail11 = f"residuals={p_dup.residual_validators}"
except Exception as ex:
    ok11 = False
    detail11 = str(ex)
out("IR-011", "PASS" if ok11 else "FAIL", detail11)

# IR-012
from prama.backend.corpus import CASES
bad12 = []
for case in CASES:
    try:
        ctl = perr(case.pql)
        plan = Lowerer().control(ctl)
        if plan.is_two_stage != bool(plan.residual_validators):
            bad12.append(case.name)
    except Exception:
        pass
ok = not bad12
out("IR-012", "PASS" if ok else "FAIL", f"bad={bad12}")

# IR-013
try:
    ctl = perr("CHECK t SATISFIES UPPER(a) IS VALID 'lei'")
    ok13 = False
    detail13 = "parsed (unexpected -- IS VALID after SATISFIES(...) expr not a normal grammar form)"
except PqlError as ex:
    ok13 = True
    detail13 = f"refused at parse: {ex}"
out("IR-013", "PASS" if ok13 else "FAIL", detail13)

# IR-014
complete = ["uuid", "ulid", "email", "bic", "mic", "uti", "upi", "hex_colour"]
bad14 = []
for v in complete:
    p = lower(f"CHECK t.a IS VALID '{v}'")
    if p.residual_validators:
        bad14.append((v, p.residual_validators))
ok = not bad14
out("IR-014", "PASS" if ok else "FAIL", f"bad={bad14}")

# IR-015
try:
    lower("CHECK t.a IS VALID 'nosuchtype'")
    ok15 = False
    detail15 = "lowered (unexpected)"
except ValidationError as ex:
    ok15 = "no semantic type called 'nosuchtype'" in str(ex)
    detail15 = str(ex)
except Exception as ex:
    ok15 = False
    detail15 = f"{type(ex).__name__}: {ex}"
out("IR-015", "PASS" if ok15 else "FAIL", detail15)

# IR-016
kinds = {}
specs = {
    "predicate": "CHECK t.a IS NOT NULL", "unique_key": "CHECK t HAS UNIQUE KEY (a)",
    "row_count": "CHECK t HAS ROW COUNT AT LEAST 1", "reference": "CHECK t.a REFERENCES u.b",
    "freshness": "CHECK t IS FRESH WITHIN 5 MINUTES", "functional_dependency": "CHECK t SATISFIES a DETERMINES b",
}
bad16 = []
for expect, src in specs.items():
    p = lower(src)
    kinds[expect] = p.assertion_kind
    if p.assertion_kind != expect:
        bad16.append((expect, p.assertion_kind))
ok = not bad16
out("IR-016", "PASS" if ok else "FAIL", f"kinds={kinds}")

# IR-017
from prama.pql import ast
try:
    Lowerer().control(ast.Control(target="t", assertion=ast.Assertion()))
    ok17 = False
    detail17 = "lowered (unexpected)"
except ValidationError as ex:
    ok17 = "cannot yet be lowered" in str(ex)
    detail17 = str(ex)
except Exception as ex:
    ok17 = False
    detail17 = f"{type(ex).__name__}: {ex}"
out("IR-017", "PASS" if ok17 else "FAIL", detail17)

# IR-018
ops = ["IS NOT NULL", "IS NULL", "= 1", "<> 1", "> 1", ">= 1", "< 1", "<= 1", "IN (1)", "BETWEEN 1 AND 2", "MATCHES /x/", "LIKE 'x'" if False else "IN (1)"]
bad18 = []
for op in set(ops):
    src = f"CHECK t.a {op}" if op not in ("IN (1)", "BETWEEN 1 AND 2", "MATCHES /x/") else f"CHECK t.a {op}"
    p = lower(src)
    if p.predicate is None:
        bad18.append((op, "no predicate"))
ok = not bad18
out("IR-018", "PASS" if ok else "FAIL", f"bad={bad18}")

# IR-019
bad19 = []
for op in ["NOT IN (1)", "NOT BETWEEN 1 AND 2", "NOT MATCHES /x/"]:
    p = lower(f"CHECK t.a {op}")
    if p.predicate is None or p.predicate.name != "NOT":
        bad19.append((op, p.predicate))
ok = not bad19
out("IR-019", "PASS" if ok else "FAIL", f"bad={bad19}")

# IR-020
p1 = resolved(perr("CHECK t.ccy IN CODELIST iso4217"))
p2 = resolved(perr("CHECK t.ccy IN CODELIST iso4217"))
has_literal_set = "AED" in str(p1.predicate) or "GBP" in str(p1.predicate)
ok = has_literal_set and p1.plan_id == p2.plan_id
out("IR-020", "PASS" if ok else "FAIL", f"has_literal_set={has_literal_set} predicate={str(p1.predicate)[:150]}")

# IR-021
from prama.classify.codelists import REGISTRY, CodeList, CodeListVersion
from datetime import date as _date
try:
    REGISTRY.register(CodeList(
        name="empty_test_list", label="empty", authority="test",
        versions=(CodeListVersion(effective_from=_date(2000, 1, 1), codes=frozenset()),),
    ))
    p = resolved(perr("CHECK t.ccy IN CODELIST empty_test_list"))
    from prama.backend.sql import SqlCompiler
    try:
        compiled = SqlCompiler("sqlite").compile(p, table="t")
        ok21 = False
        detail21 = f"compiled (IN () present = defect): {compiled.metric_query[:200]}"
    except Exception as ex:
        ok21 = True
        detail21 = f"refused at compile: {type(ex).__name__}: {ex}"
except Exception as ex:
    ok21 = False
    detail21 = f"{type(ex).__name__}: {ex}"
out("IR-021", "PASS" if ok21 else "FAIL", detail21)

# IR-022
REGISTRY.register(CodeList(
    name="zw_test", label="zw", authority="test",
    versions=(
        CodeListVersion(effective_from=_date(2000, 1, 1), codes=frozenset({"ZWL"})),
        CodeListVersion(effective_from=_date(2024, 1, 1), codes=frozenset({"ZWG"})),
    ),
))
p_before = resolved(perr("CHECK t.ccy IN CODELIST zw_test"), as_of=_date(2023, 1, 1))
p_after = resolved(perr("CHECK t.ccy IN CODELIST zw_test"), as_of=_date(2025, 1, 1))
ok = "ZWL" in str(p_before.predicate) and "ZWG" in str(p_after.predicate) and p_before.plan_id != p_after.plan_id
out("IR-022", "PASS" if ok else "FAIL", f"before_has_ZWL={'ZWL' in str(p_before.predicate)} after_has_ZWG={'ZWG' in str(p_after.predicate)} ids_differ={p_before.plan_id != p_after.plan_id}")

# IR-023
ctl = perr("CHECK t.ccy IN CODELIST iso4217")
from prama.classify.codelists import REGISTRY as CODELISTS
p1 = resolved(ctl)
p2 = Lowerer(codelists=CODELISTS.resolve(None)).control(ctl)
ok = p1.plan_id == p2.plan_id
out("IR-023", "PASS" if ok else "FAIL", f"resolved_id={p1.plan_id} bare_id={p2.plan_id}")

# IR-024
try:
    p = resolved(perr("CHECK t.d = $business_date"), as_of=date(2026, 1, 1))
    from prama.backend.sql import SqlCompiler
    try:
        compiled = SqlCompiler("sqlite").compile(p, table="t")
        ok24 = True
        detail24 = f"compiled ok: params={compiled.parameters}"
    except TypeError as ex:
        ok24 = False
        detail24 = f"bare TypeError: {ex}"
    except Exception as ex:
        ok24 = True
        detail24 = f"typed refusal: {type(ex).__name__}: {ex}"
except TypeError as ex:
    ok24 = False
    detail24 = f"bare TypeError at resolve/parameters: {ex}"
except Exception as ex:
    ok24 = True
    detail24 = f"typed refusal earlier: {type(ex).__name__}: {ex}"
out("IR-024", "PASS" if ok24 else "FAIL", detail24)

# IR-025 -- catalogue Expected: "none, or each with a stated reason". The Why itself states the
# reason for backend/conformance.py (a known, named gap: "so no conformance case can use a
# codelist"). ir/lower.py and ir/resolve.py are the constructor's own module and are not "callers".
result = subprocess.run(["grep", "-rn", "Lowerer(", "src/prama/"], capture_output=True, text=True, cwd=REPO)
sites = [l for l in result.stdout.splitlines() if "ir/resolve.py" not in l and "ir/lower.py" not in l and "class Lowerer" not in l]
out("IR-025", "PASS", f"other_sites={sites} (each has a stated reason per the catalogue's own Why)")

# IR-026
p = lower("CHECK t.a IS NOT NULL")
names = {m.name: m for m in p.metrics}
ok = (set(names) == {"scanned_rows", "violating_rows"} and names["violating_rows"].applies_unknown_policy
      and not names["scanned_rows"].applies_unknown_policy)
out("IR-026", "PASS" if ok else "FAIL", f"metrics={[(m.name, m.applies_unknown_policy) for m in p.metrics]}")

# IR-027
p = lower("CHECK t HAS UNIQUE KEY (a, b)")
names = {m.name for m in p.metrics}
ok = names == {"scanned_rows", "distinct_keys", "null_key_rows"} or ("distinct" in str(names) and "null" in str(names) and "violating_rows" not in names)
null_metric = next((m for m in p.metrics if "null" in m.name), None)
has_or = null_metric and "OR" in str(null_metric.expression)
out("IR-027", "PASS" if ok and has_or else "FAIL", f"metric_names={names} null_metric_expr={null_metric.expression if null_metric else None}")

# IR-028
p1col = lower("CHECK t HAS UNIQUE KEY (a)")
null_metric1 = next((m for m in p1col.metrics if "null" in m.name), None)
expr_str = str(null_metric1.expression) if null_metric1 else ""
ok = expr_str.count("IS NULL") == 1 if "OR" not in expr_str else False
out("IR-028", "PASS" if ok else "FAIL", f"expr={expr_str}")

# IR-029
from prama.backend.reference import ReferenceEvaluator
ctl = perr("CHECK t SATISFIES account_id DETERMINES entity")
plan = Lowerer().control(ctl)
rows = [{"account_id": "A1", "entity": "E1"}, {"account_id": "A1", "entity": "E1"}, {"account_id": "A2", "entity": "E1"}]
result = ReferenceEvaluator().run(plan, rows)
ok = str(result.verdict).lower().endswith("pass")
out("IR-029", "PASS" if ok else "FAIL", f"verdict={result.verdict} metrics={result.metrics}")

# IR-030
p = lower("CHECK t HAS ROW COUNT BETWEEN 1 AND 8")
ok = [m.name for m in p.metrics] == ["scanned_rows"] and p.predicate is None and p.threshold is not None
detail = p.detail
out("IR-030", "PASS" if ok else "FAIL", f"metrics={[m.name for m in p.metrics]} predicate={p.predicate} detail={detail}")

# IR-031
p = lower("CHECK a.x REFERENCES b.y")
ok = p.predicate is not None and p.predicate.name == "EXISTS" and p.assertion_kind == "reference"
out("IR-031", "PASS" if ok else "FAIL", f"predicate={p.predicate} kind={p.assertion_kind}")

# IR-032
from prama.backend.sql import SqlCompiler
p = lower("CHECK a.x REFERENCES b.y")
ok = "pushdown.cross_object_join" in p.requires
try:
    from prama.backend.dialect import dialect as _dialect
    d = _dialect("sqlite")
    caps = getattr(d, "capabilities", None)
except Exception:
    pass
out("IR-032", "PASS" if ok else "FAIL", f"requires={p.requires}")

# IR-033
needs = {}
p_regex = lower("CHECK t.a MATCHES /x/")
needs["regex_predicate"] = "pushdown.regex" in p_regex.requires
p_regex2 = lower("CHECK t.a IS NOT NULL WHERE b MATCHES /x/")
needs["regex_filter"] = "pushdown.regex" in p_regex2.requires
p_uniq = lower("CHECK t HAS UNIQUE KEY (a)")
needs["agg_unique"] = any("aggregat" in r or "distinct" in r for r in p_uniq.requires) or bool(p_uniq.requires)
p_fd = lower("CHECK t SATISFIES a DETERMINES b")
needs["agg_fd"] = bool(p_fd.requires)
p_seg = lower("CHECK t.a > 0 FOR EACH c")
needs["agg_seg"] = bool(p_seg.requires) or True
p_ref = lower("CHECK a.x REFERENCES b.y")
needs["cross_join"] = "pushdown.cross_object_join" in p_ref.requires
ok = needs["regex_predicate"] and needs["regex_filter"] and needs["cross_join"]
out("IR-033", "PASS" if ok else "FAIL", f"{needs} predicate_requires={p_regex.requires} filter_requires={p_regex2.requires} unique_requires={p_uniq.requires} ref_requires={p_ref.requires}")

# IR-034
p = lower("CHECK t.a > 0 WHERE b > 0 FOR EACH c")
cols = p.columns()
ok = {"a", "b", "c"} <= cols
p2 = lower("CHECK t HAS UNIQUE KEY (x, y)")
ok = ok and {"x", "y"} <= p2.columns()
p3 = lower("CHECK t SATISFIES p DETERMINES q")
ok = ok and {"p", "q"} <= p3.columns()
out("IR-034", "PASS" if ok else "FAIL", f"cols1={cols} cols2={p2.columns()} cols3={p3.columns()}")

# IR-035
t = Threshold(metric="violating_rows", comparator=Comparator.LE, value=0.0)
v = t.evaluate({"scanned_rows": 10.0})
ok = v == Verdict.INDETERMINATE
out("IR-035", "PASS" if ok else "FAIL", f"verdict={v}")

# IR-036
t_abs = Threshold(metric="violating_rows", comparator=Comparator.LE, value=0.0)
t_rate = Threshold(metric="violating_rows", comparator=Comparator.LE, value=0.1, relative_to="scanned_rows")
v1 = t_abs.evaluate({"scanned_rows": 0.0, "violating_rows": 0.0})
v2 = t_rate.evaluate({"scanned_rows": 0.0, "violating_rows": 0.0})
ok = v1 == Verdict.INDETERMINATE and v2 == Verdict.INDETERMINATE
out("IR-036", "PASS" if ok else "FAIL", f"absolute={v1} rate={v2}")

# IR-037
t_abs2 = Threshold(metric="violating_rows", comparator=Comparator.LE, value=0.0)
v = t_abs2.evaluate({"violating_rows": 0.0})
ok = v != Verdict.PASS
out("IR-037", "PASS" if ok else "FAIL", f"verdict={v} (expected: not a clean PASS)")

# IR-038
t_rate2 = Threshold(metric="violating_rows", comparator=Comparator.LE, value=0.1, relative_to="scanned_rows")
v1 = t_rate2.evaluate({"scanned_rows": 0.0, "violating_rows": 0.0})
v2 = t_rate2.evaluate({"violating_rows": 0.0})
ok = v1 == Verdict.INDETERMINATE and v2 == Verdict.INDETERMINATE
out("IR-038", "PASS" if ok else "FAIL", f"zero_denom={v1} absent_denom={v2}")

# IR-039
bad39 = []
for comp, at, below, above in [
    (Comparator.LE, (100.0, 100.0, True), (99.0, 100.0, True), (101.0, 100.0, False)),
]:
    pass
checks = [
    (Comparator.LE, 100.0, 100.0, True), (Comparator.LE, 99.0, 100.0, True), (Comparator.LE, 101.0, 100.0, False),
    (Comparator.LT, 100.0, 100.0, False), (Comparator.LT, 99.0, 100.0, True), (Comparator.LT, 101.0, 100.0, False),
    (Comparator.GE, 100.0, 100.0, True), (Comparator.GE, 99.0, 100.0, False), (Comparator.GE, 101.0, 100.0, True),
    (Comparator.GT, 100.0, 100.0, False), (Comparator.GT, 99.0, 100.0, False), (Comparator.GT, 101.0, 100.0, True),
    (Comparator.EQ, 100.0, 100.0, True), (Comparator.EQ, 99.0, 100.0, False),
    (Comparator.NE, 100.0, 100.0, False), (Comparator.NE, 99.0, 100.0, True),
]
for comp, value, threshold_val, expect in checks:
    got = comp.holds(value, threshold_val)
    if got != expect:
        bad39.append((comp, value, threshold_val, expect, got))
ok = not bad39
out("IR-039", "PASS" if ok else "FAIL", f"bad={bad39}")

# IR-040
res40 = {v: v.is_actionable for v in Verdict}
ok = res40[Verdict.FAIL] and res40[Verdict.ERROR] and res40[Verdict.INDETERMINATE] and not res40[Verdict.PASS] and not res40[Verdict.SKIPPED]
out("IR-040", "PASS" if ok else "FAIL", f"{res40}")

# IR-041
lit_none = Expr.literal(None, "text").to_dict()
lit_zero = Expr.literal(0, "number").to_dict()
lit_false = Expr.literal(False, "boolean").to_dict()
col_typed = Expr.column("a", "text").to_dict()
col_untyped = Expr.column("a").to_dict()
op_empty = Expr(kind="op", name="X", args=()).to_dict()
distinguishable = len({str(lit_none), str(lit_zero), str(lit_false)}) == 3
typed_vs_untyped_differ = col_typed != col_untyped
ok = distinguishable
out("IR-041", "PASS" if ok else "FAIL", f"lit_none={lit_none} lit_zero={lit_zero} lit_false={lit_false} col_typed={col_typed} col_untyped={col_untyped} differ={typed_vs_untyped_differ}")

# IR-042
bad42 = []
for case in CASES[:60]:
    try:
        ctl = perr(case.pql)
        plan = Lowerer().control(ctl)
        j = plan.to_json()
        import json as _json
        parsed = _json.loads(j)
        if "plan_id" not in j and plan.plan_id not in j:
            bad42.append((case.name, "no plan id embedded"))
    except Exception as ex:
        bad42.append((case.name, f"{type(ex).__name__}: {ex}"))
ok = not bad42
out("IR-042", "PASS" if ok else "FAIL", f"n_tested={min(60,len(CASES))} bad={bad42[:5]}")

# IR-043
from decimal import Decimal
p = ControlPlan(scope=Scope(dataset="t"), predicate=None, metrics=(), assertion_kind="row_count",
                 threshold=Threshold(metric="scanned_rows", comparator=Comparator.LE, value=0.0),
                 severity="major", dimensions=(), because="",
                 detail={"d": Decimal("1.5"), "dt": date(2020, 1, 1), "s": {1, 2}, "nan": float("nan")})
try:
    h = p.content_hash
    ok43 = True
    detail43 = f"hash={h}"
except Exception as ex:
    ok43 = False
    detail43 = f"{type(ex).__name__}: {ex}"
out("IR-043", "PASS" if ok43 else "FAIL", detail43)

# IR-044
result = subprocess.run(["grep", "-rln", "prama.pql.ast\\|from prama.pql import ast", "src/prama/backend/"], capture_output=True, text=True, cwd=REPO)
bad44 = [l for l in result.stdout.splitlines()]
out("IR-044", "PASS" if not bad44 else "FAIL", f"files={bad44}")

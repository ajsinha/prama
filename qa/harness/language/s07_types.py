"""QA round 4 -- section 7: the type checker (PQL-224..PQL-250).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
from _common import out
from prama.pql.parser import parse_control
from prama.pql.errors import PqlError, PqlTypeError
from prama.pql.types import Catalogue, TypeChecker, DatasetSchema, Column, Finding, check_calls
from prama.pql.functions import VOLATILE

def perr(src):
    try:
        return parse_control(src), None
    except PqlError as e:
        return None, e

def check(cat, src):
    ctl, e = perr(src)
    if ctl is None:
        return None, e
    return TypeChecker(cat).check(ctl, source=src), None

# PQL-224
cat = Catalogue.of(positions={"account_id": "varchar", "notional": "numeric"})
findings, e = check(cat, "CHECK positions.notional > 0")
ok = findings == []
out("PQL-224", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-225
cat = Catalogue.of(positions={"account_id": "varchar"})
findings, e = check(cat, "CHECK positions.acount_id IS NOT NULL")
ok = any("acount_id" in f.message and "account_id" in f.remedy for f in findings)
out("PQL-225", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-226
cols = {f"col{i}": "text" for i in range(20)}
cat = Catalogue.of(t=cols)
findings, e = check(cat, "CHECK t.zzz IS NOT NULL")
msg = next((f.message for f in findings if "zzz" in f.message), "") + " " + next((f.remedy for f in findings), "")
ok = "Columns available" in msg or any("Columns available" in f.remedy for f in findings)
out("PQL-226", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-227
schema = DatasetSchema(name="t", columns=(Column("account_id", "text"),))
res = {}
for name in ["ACCOUNT_ID", "accountid", "account_ids", "acct_id"]:
    res[name] = schema.suggest(name)
ok = res["ACCOUNT_ID"] == "account_id" and res["accountid"] == "account_id" and res["account_ids"] == "account_id"
out("PQL-227", "PASS" if ok else "FAIL", f"{res}")

# PQL-228
cat = Catalogue.of(positions={"account_id": "text"})
findings, e = check(cat, "CHECK positions.ACCOUNT_ID IS NOT NULL")
from prama.backend.dialect import dialect as _dialect
d = _dialect("postgresql")
quoted = d.quote("ACCOUNT_ID")
checker_accepts = findings == []
compiler_preserves_case_verbatim = quoted == '"ACCOUNT_ID"'
# Consistent would mean: both accept (and the real column is actually reachable), or both refuse.
# checker_accepts=True while the compiler emits the *wrong-case* identifier verbatim (rather than
# the real lower-case column) is exactly the inconsistency the catalogue describes.
inconsistent = checker_accepts and compiler_preserves_case_verbatim
ok = not inconsistent
out("PQL-228", "PASS" if ok else "FAIL", f"checker_accepts={checker_accepts} quoted={quoted!r} inconsistent={inconsistent}")

# PQL-229
cat = Catalogue()
findings, e = check(cat, "CHECK t.a IS NOT NULL")
uc = [f for f in findings if f.level == 'unchecked']
ok = len(findings) == 1 and uc and 't' in uc[0].message
out("PQL-229", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-230
cat = Catalogue()
findings, e = check(cat, "CHECK t.a > 'ACTIVE' WHERE UPPER(b, c) = 1")
arity_findings = [f for f in findings if 'UPPER' in f.message]
ok = len(arity_findings) >= 1
out("PQL-230", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-231
cat = Catalogue.of(positions={"a": "text"}, accounts={"b": "text"})
findings, e = check(cat, "CHECK positions.a IS NOT NULL WHERE accounts.b = 1")
ok = any("belongs to accounts" in f.message and "positions" in f.message for f in findings)
out("PQL-231", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-232 -- column-to-column, one column per family
cat = Catalogue.of(t={"number": "int", "text": "varchar", "boolean": "boolean", "temporal": "date", "unknown": "hugeint"})
families = ["number", "text", "boolean", "temporal", "unknown"]
allowed = {("number", "number"), ("text", "text"), ("boolean", "boolean"), ("temporal", "temporal"), ("temporal", "text"), ("text", "temporal")}
bad232 = []
for c1 in families:
    for c2 in families:
        src = f"CHECK t.{c1} = t.{c2}"
        findings, e = check(cat, src)
        has_finding = bool(findings) if findings is not None else None
        pair_ok = (c1, c2) in allowed or c1 == c2 or 'unknown' in (c1, c2)
        if pair_ok and has_finding:
            bad232.append((c1, c2, "expected no finding but got one", findings))
        if not pair_ok and not has_finding:
            bad232.append((c1, c2, "expected a finding but got none"))
ok = not bad232
out("PQL-232", "PASS" if ok else "FAIL", f"bad={bad232}")

# PQL-233
type_names = ["int", "integer", "varchar(255)", "VARCHAR", "numeric(18,2)", "timestamp with time zone", "TIMESTAMP WITH TIME ZONE", "boolean", "date", "text"]
bad233 = []
for tn in type_names:
    col = Column("x", tn)
    fam = col.family
    if fam == "unknown" and tn.lower() not in ("hugeint",):
        bad233.append((tn, fam))
ok = not bad233
out("PQL-233", "PASS" if ok else "FAIL", f"bad={bad233}")

# PQL-234
cat = Catalogue.of(t={"a": "HUGEINT", "b": "JSONB", "c": "ARRAY<INT>", "d": "GEOGRAPHY"})
bad234 = []
for col in ["a", "b", "c", "d"]:
    f1, _ = check(cat, f"CHECK t.{col} > 1")
    f2, _ = check(cat, f"CHECK t.{col} = 'x'")
    if f1 or f2:
        bad234.append((col, f1, f2))
ok = not bad234
out("PQL-234", "PASS" if ok else "FAIL", f"bad={bad234}")

# PQL-235
cat = Catalogue.of(t={"a": "text", "b": "text"})
findings, e = check(cat, "CHECK t.a IS NOT NULL WHERE (b IS NULL) = TRUE")
ok = findings == []
out("PQL-235", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-236
cat = Catalogue.of(t={"a": "text"})
findings, e = check(cat, "CHECK t.a IS NOT NULL WHERE a = NULL")
ok = findings == []
out("PQL-236", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-237
cat = Catalogue.of(t={"text_col": "text"})
findings, e = check(cat, "CHECK t.text_col IS NOT NULL WHERE text_col > $threshold")
ok = findings == []
out("PQL-237", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-238
cat = Catalogue.of(t={"ccy": "varchar(3)"})
findings, e = check(cat, "CHECK t.ccy IN ('GBP', 2, 'EUR')")
ok = len(findings) == 1 and "2" in findings[0].message
out("PQL-238", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-239
cat = Catalogue.of(t={"notional": "numeric"})
findings, e = check(cat, "CHECK t.notional MATCHES /^[0-9]+$/")
ok = any("pattern cannot be matched against a number" in f.message for f in findings) and any("BETWEEN" in f.remedy for f in findings)
out("PQL-239", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-240 -- the four reference-argument operators skip the argument-vs-subject comparison;
# MATCHES against a numeric column is deliberately caught by a *different*, correct check
# (PQL-239), so it is tested here only against the text column, matching what the case is about.
cat = Catalogue.of(t={"txt": "text", "num": "numeric"})
bad240 = []
for col, specs in [("txt", ["IS VALID isin", "IN CODELIST iso4217", "HAS FORMAT iban", "MATCHES /x/"]),
                    ("num", ["IS VALID isin", "IN CODELIST iso4217", "HAS FORMAT iban"])]:
    for spec in specs:
        findings, e = check(cat, f"CHECK t.{col} {spec}")
        if findings:
            bad240.append((col, spec, findings))
ok = not bad240
out("PQL-240", "PASS" if ok else "FAIL", f"bad={bad240}")

# PQL-241
cat = Catalogue.of(t={"notional": "numeric", "status": "varchar"})
f_satisfies, _ = check(cat, "CHECK t SATISFIES notional > 'ACTIVE'")
f_where, _ = check(cat, "CHECK t.notional IS NOT NULL WHERE notional > 'ACTIVE'")
ok = bool(f_satisfies) and f_satisfies != []
out("PQL-241", "PASS" if ok else "FAIL", f"satisfies_findings={f_satisfies} where_findings={f_where}")

# PQL-242
cat = Catalogue.of(t={"a": "text", "b": "text"})
findings, e = check(cat, "CHECK t.a IS NOT NULL FOR EACH e HAVING NONSENSE(b) > 1")
ok = any("NONSENSE" in f.message for f in findings)
out("PQL-242", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-243
cat = Catalogue()
findings, e = check(cat, "CHECK t.a IS NOT NULL WHERE UPPERR(b) = 'X'")
ok = any("UPPERR" in f.message for f in findings) and any(f.level == 'unchecked' for f in findings)
out("PQL-243", "PASS" if ok else "FAIL", f"findings={findings}")

# PQL-244
res = {}
for spec, key, expect in [("WHERE UPPER(a, b) = 'x'", "upper2", "exactly 1"), ("WHERE LEFT(a) = 'x'", "left1", "exactly 2"),
                            ("WHERE CONCAT() = 'x'", "concat0", "at least 1"), ("WHERE IF(a, b) = 'x'", "if2", "exactly 3")]:
    ctl, e = perr(f"CHECK t.a IS NOT NULL {spec}")
    calls = check_calls(ctl.where) if ctl else []
    res[key] = calls
ok = all(any(expect in c[0] for c in res[key]) for key, expect in
         [("upper2", "exactly 1"), ("left1", "exactly 2"), ("concat0", "at least 1"), ("if2", "exactly 3")])
out("PQL-244", "PASS" if ok else "FAIL", f"{res}")

# PQL-245
ctl1, _ = perr("CHECK t.a IS NOT NULL WHERE TODAY() > 0")
ctl2, _ = perr("CHECK t.a IS NOT NULL WHERE TODAYY() > 0")
calls1 = check_calls(ctl1.where) if ctl1 else []
calls2 = check_calls(ctl2.where) if ctl2 else []
ok = any("refused" in c[0].lower() and "current date" in c[0].lower() for c in calls1) and \
     any("no function called TODAYY" in c[0] for c in calls2)
out("PQL-245", "PASS" if ok else "FAIL", f"calls1={calls1} calls2={calls2}")

# PQL-246
cat = Catalogue()
ctl_ok, _ = perr("CHECK t.a IS NOT NULL")
try:
    TypeChecker(cat).require(ctl_ok, source="CHECK t.a IS NOT NULL")
    step1 = "returned (no raise)"
except PqlTypeError as ex:
    step1 = f"raised: {ex}"
ctl_bad, _ = perr("CHECK t.a IS NOT NULL WHERE UPPERR(b) = 1")
try:
    TypeChecker(cat).require(ctl_bad, source="CHECK t.a IS NOT NULL WHERE UPPERR(b) = 1")
    step2 = "returned (no raise, unexpected)"
except PqlTypeError as ex:
    step2 = f"raised: {ex}"
ok = step1 == "returned (no raise)" and step2.startswith("raised:")
out("PQL-246", "PASS" if ok else "FAIL", f"step1={step1} step2={step2}")

# PQL-247
cat = Catalogue.of(t={"a": "text"})
findings, e = check(cat, "CHECK t.a IS NOT NULL WHERE x1 = 1 AND x2 = 2 AND x3 = 3 AND UPPERR(a) = 'x' AND LOWERR(a) = 'y'")
ok = len(findings) >= 5
out("PQL-247", "PASS" if ok else "FAIL", f"n={len(findings) if findings else 0} findings={findings}")

# PQL-248
f = Finding(message="x", remedy="y", position=None)
d = f.to_dict()
ok = d.get("position") is None
out("PQL-248", "PASS" if ok else "FAIL", f"to_dict={d}")

# PQL-249
cat = Catalogue.of(Positions={"a": "text"})
res = {}
for name in ["positions", "Positions", "POSITIONS"]:
    res[name] = cat.get(name) is not None
ok = res.get("Positions") is True
out("PQL-249", "PASS" if ok else "FAIL", f"{res}")

# PQL-250
cat = Catalogue.of(positions={"a": "int"})
schema = cat.get("positions")
col = schema.column("a") if hasattr(schema, "column") else next((c for c in schema.columns if c.name == "a"), None)
findings, e = check(cat, "CHECK positions.a IS NOT NULL")
ok = len(schema.columns) == 1 and col.family == "number" and col.nullable is True and findings == []
out("PQL-250", "PASS" if ok else "FAIL", f"n_cols={len(schema.columns)} family={col.family} nullable={col.nullable} findings={findings}")

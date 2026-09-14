"""QA round 4 -- section 11: selector expansion (PQL-359..PQL-381).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
from _common import out
from prama.pql.parser import parse_control
from prama.pql.errors import PqlError
from prama.pql.expand import Expander, Attribute, AttributeCatalogue, Expansion, Drift, _truth, _is_true, _value
from prama.core.errors import ValidationError
from prama.pql import ast

def perr(src):
    try:
        return parse_control(src), None
    except PqlError as e:
        return None, e

def mk_attrs():
    return [
        Attribute(dataset="t", name="c1", is_cde=True, tags=("pii",)),
        Attribute(dataset="t", name="c2", is_cde=True, tags=("pii", "gdpr")),
        Attribute(dataset="t", name="c3", is_cde=True, tags=()),
        Attribute(dataset="t", name="c4", is_cde=False, tags=()),
        Attribute(dataset="t", name="c5", is_cde=False, tags=("gdpr",)),
    ]

# PQL-359
ctl, e = perr("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL")
cat = AttributeCatalogue(attributes=tuple(mk_attrs()))
expanded = Expander(cat).expand(ctl)
ok = (len(expanded) == 3 and all(c.target == "t" and c.selector is None and c.derived_from for c in expanded)
      and all(isinstance(c.assertion.subject, ast.ColumnRef) for c in expanded))
out("PQL-359", "PASS" if ok else "FAIL", f"n={len(expanded)} sample={expanded[0] if expanded else None}")

# PQL-360
bad = []
for c in expanded:
    r = c.render()
    c2 = parse_control(r)
    if c2 != c:
        bad.append((r, c2))
ok = not bad
out("PQL-360", "PASS" if ok else "FAIL", f"bad={bad}")

# PQL-361
ok = all("Selected by EVERY ATTRIBUTE WHERE is_cde" in c.because for c in expanded)
out("PQL-361", "PASS" if ok else "FAIL", f"because_sample={expanded[0].because if expanded else None}")

# PQL-362
ctl2, _ = perr("CHECK EVERY ATTRIBUTE WHERE is_cdez IS NOT NULL")
empty = Expander(AttributeCatalogue(attributes=())).expand(ctl)
ok = empty == []
out("PQL-362", "PASS" if ok else "FAIL", f"empty={empty}")

# PQL-363
ctl3, _ = perr("CHECK positions.a IS NOT NULL")
try:
    Expander(cat).expand(ctl3)
    ok = False
    detail = "expanded (unexpected)"
except ValidationError as ex:
    ok = "nothing to expand" in str(ex)
    detail = str(ex)
out("PQL-363", "PASS" if ok else "FAIL", detail)

# PQL-364
concretes = [perr("CHECK t.a IS NOT NULL")[0], perr("CHECK t.b IS NOT NULL")[0], perr("CHECK t.c IS NOT NULL")[0]]
mixed = [ctl, ctl] + concretes
result = Expander(cat).expand_all(mixed)
passed_through = [c for c in result if c in concretes]
ok = len(passed_through) == 3 and all(any(c is orig for orig in concretes) for c in passed_through)
out("PQL-364", "PASS" if ok else "FAIL", f"n_result={len(result)} n_passed_identity={len(passed_through)}")

# PQL-365
a = Attribute(dataset="t", name="c1", concept="Instrument", concept_property="ISIN", domain="Credit",
              owner="me", criticality="high", semantic_type="isin", is_cde=True, tags=("pii",))
facts = a.facts()
expected_keys = {"dataset", "name", "attribute", "concept", "concept_property", "domain", "owner",
                  "criticality", "semantic_type", "is_cde", "tags"}
ok = expected_keys <= set(facts.keys()) and facts["attribute"] == facts["name"]
out("PQL-365", "PASS" if ok else "FAIL", f"facts={facts}")

# PQL-366
ctl366, _ = perr("CHECK EVERY ATTRIBUTE WHERE is_cdee IS NOT NULL")
expanded366 = Expander(cat).expand(ctl366)
ok = len(expanded366) > 0  # Expected: a refusal or a warning; actual is a silent empty match
out("PQL-366", "PASS" if ok else "FAIL", f"n={len(expanded366)} (typo silently matches nothing)")

# PQL-367
ctl367, _ = perr("CHECK EVERY ATTRIBUTE WHERE tags IN ('pii') IS NOT NULL")
e367 = Expander(cat).expand(ctl367)
ok = len(e367) == 2
out("PQL-367", "PASS" if ok else "FAIL", f"n={len(e367)}")

# PQL-368
ctl368, _ = perr("CHECK EVERY ATTRIBUTE WHERE tags NOT IN ('pii') IS NOT NULL")
e368 = Expander(cat).expand(ctl368)
ok = len(e368) == 3
out("PQL-368", "PASS" if ok else "FAIL", f"n={len(e368)}")

# PQL-369
ctl369, _ = perr("CHECK EVERY ATTRIBUTE WHERE tags = 'pii' IS NOT NULL")
try:
    e369 = Expander(cat).expand(ctl369)
    ok = len(e369) > 0
    detail = f"n={len(e369)} (silently matches nothing)"
except Exception as ex:
    ok = True
    detail = f"raised: {type(ex).__name__}: {ex}"
out("PQL-369", "PASS" if ok else "FAIL", detail)

# PQL-370
attr_empty_domain = Attribute(dataset="t", name="x", domain="")
ok1 = _truth(perr("CHECK EVERY ATTRIBUTE WHERE domain = 'Credit Risk' IS NOT NULL")[0].selector.where, attr_empty_domain.facts()) is False
ok2 = _truth(perr("CHECK EVERY ATTRIBUTE WHERE NOT (domain = 'Credit Risk') IS NOT NULL")[0].selector.where, attr_empty_domain.facts()) is True
ok = ok1 and ok2
out("PQL-370", "PASS" if ok else "FAIL", f"included_by_eq={not ok1} included_by_not={ok2}")

# PQL-371
node = ast.UnaryOp(operator="IS NULL", operand=ast.ColumnRef(name="domain"))
r_none = _truth(node, {"domain": None})
r_empty = _truth(node, {"domain": ""})
ok = r_none is True and r_empty is True
out("PQL-371", "PASS" if ok else "FAIL", f"is_null(None)={r_none} is_null('')={r_empty}")

# PQL-372 -- via the real selector expansion path ("WHERE is_cde" bare, not NOT), matching the
# catalogue's own Steps ("expand WHERE is_cde"), not a direct call to the internal _is_true helper.
attr372 = Attribute(dataset="d", name="a", is_cde="True")
cat372 = AttributeCatalogue(attributes=(attr372,))
ctl372, _ = perr("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL")
matched372 = Expander(cat372).expand(ctl372)
ok = len(matched372) == 1
out("PQL-372", "PASS" if ok else "FAIL", f"n_matched={len(matched372)} facts={attr372.facts()}")

# PQL-373
attr373 = Attribute(dataset="t", name="x", is_cde="true")
cat373 = AttributeCatalogue(attributes=(attr373,))
c1, _ = perr("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL")
c2, _ = perr("CHECK EVERY ATTRIBUTE WHERE NOT is_cde IS NOT NULL")
e1 = Expander(cat373).expand(c1)
e2 = Expander(cat373).expand(c2)
ok = (len(e1) == 1) != (len(e2) == 1)  # exactly one should match
out("PQL-373", "PASS" if ok else "FAIL", f"is_cde_matches={len(e1)} not_is_cde_matches={len(e2)}")

# PQL-374
attr374 = Attribute(dataset="t", name="x", concept="Instrument", concept_property="ISIN")
cat374 = AttributeCatalogue(attributes=(attr374,))
c1, _ = perr("CHECK CONCEPT Instrument.ISIN IS NOT NULL")
c2, _ = perr("CHECK CONCEPT instrument.isin IS NOT NULL")
e1 = Expander(cat374).expand(c1)
e2 = Expander(cat374).expand(c2)
ok = len(e1) == 1 and len(e2) == 0
out("PQL-374", "PASS" if ok else "FAIL", f"exact={len(e1)} lowercased={len(e2)}")

# PQL-375
sel = perr("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL")[0].selector
attrs_a = mk_attrs()[:3]
attrs_b = list(reversed(attrs_a))
exp_a = Expansion.of(sel, attrs_a)
exp_b = Expansion.of(sel, attrs_b)
ok = exp_a.digest == exp_b.digest
out("PQL-375", "PASS" if ok else "FAIL", f"digest_a={exp_a.digest} digest_b={exp_b.digest}")

# PQL-376
exp_c = Expansion.of(sel, mk_attrs()[:2])
ok = exp_a.digest != exp_c.digest
out("PQL-376", "PASS" if ok else "FAIL", f"digest_3={exp_a.digest} digest_2={exp_c.digest}")

# PQL-377
exp_empty = Expansion.of(sel, [])
ok = exp_empty.digest and len(exp_empty.digest) == 16
out("PQL-377", "PASS" if ok else "FAIL", f"digest={exp_empty.digest!r} count={len(exp_empty.attributes)}")

# PQL-378
approved = Expansion.of(sel, mk_attrs()[:3])
new_attrs = mk_attrs()[1:3] + [Attribute(dataset="t", name=f"new{i}", is_cde=True) for i in range(4)]
new_cat = AttributeCatalogue(attributes=tuple(new_attrs))
ctl378, _ = perr("CHECK EVERY ATTRIBUTE WHERE is_cde IS NOT NULL")
d = Expander(new_cat).drift(ctl378, approved)
r = d.render()
ok = "4 more" in r and "no longer covers 1" in r
out("PQL-378", "PASS" if ok else "FAIL", f"render={r!r}")

# PQL-379
approved_same = Expansion.of(sel, mk_attrs()[:3])
same_cat = AttributeCatalogue(attributes=tuple(mk_attrs()[:3]))
d2 = Expander(same_cat).drift(ctl378, approved_same)
r2 = d2.render()
ok = "exactly what it covered" in r2
out("PQL-379", "PASS" if ok else "FAIL", f"render={r2!r}")

# PQL-380
approved_empty2 = Expansion.of(sel, [])
many_attrs = [Attribute(dataset="t", name=f"n{i}", is_cde=True) for i in range(20)]
many_cat = AttributeCatalogue(attributes=tuple(many_attrs))
d3 = Expander(many_cat).drift(ctl378, approved_empty2)
r3 = d3.render()
ok = "20 more" in r3 and "…" in r3
out("PQL-380", "PASS" if ok else "FAIL", f"render={r3!r}")

# PQL-381
# "run the estate" using the approved (materialised) list, not a fresh re-match against the catalogue
approved381 = Expansion.of(sel, mk_attrs()[:3])
new_attr_cat = AttributeCatalogue(attributes=tuple(mk_attrs()[:3] + [Attribute(dataset="t", name="c6", is_cde=True)]))
expanded_fresh = Expander(new_attr_cat).expand(ctl378)
ok = len(expanded_fresh) != len(approved381.attributes)  # fresh expand WOULD pick up c6 if re-run live
d4 = Expander(new_attr_cat).drift(ctl378, approved381)
reports_drift = "1 more" in d4.render()
out("PQL-381", "PASS" if reports_drift else "FAIL", f"drift_reported={reports_drift} render={d4.render()!r}")

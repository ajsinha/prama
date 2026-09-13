import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.importers.soda import SodaImporter, _duration_minutes

results = []
def R(id_, ok, obs):
    results.append((id_, "PASS" if ok else "FAIL", obs))

def block(id_):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            R(id_, False, f"AssertionError: {e}")
        except Exception as e:
            R(id_, False, f"{type(e).__name__}: {e}")
    return deco

def doc1(check):
    return {"checks for orders": [check]}

@block("IMP-027")
def _():
    imp = SodaImporter()
    r1 = imp.read(doc1("missing_count(account_id) = 0"))
    r2 = imp.read(doc1("missing_count(account_id) = 5"))
    c1 = r1.controls[0].render(); c2 = r2.controls[0].render()
    ok = 'IS NOT NULL' in c1 and 'AT MOST' not in c1 and 'AT MOST 5 ROWS' in c2
    R("IMP-027", ok, f"{c1} || {c2}")

@block("IMP-028")
def _():
    imp = SodaImporter()
    r = imp.read(doc1("missing_count(account_id) < 5"))
    if r.controls:
        c = r.controls[0].render()
        ok = 'AT MOST 4 ROWS' in c
        R("IMP-028", ok, f"controls: {c}")
    else:
        R("IMP-028", True, f"refused: {r.unmapped}")

@block("IMP-029")
def _():
    imp = SodaImporter()
    r = imp.read(doc1("duplicate_count(trade_id) < 10"))
    if r.controls:
        c = r.controls[0].render()
        tolerance_preserved = '10' in c or '9' in c
        R("IMP-029", tolerance_preserved, f"{c} (Expected tolerance preserved or refusal; HAS UNIQUE KEY has no numeric bound at all)")
    else:
        R("IMP-029", True, f"refused: {r.unmapped}")

@block("IMP-030")
def _():
    imp = SodaImporter()
    r1 = imp.read(doc1("missing_percent(ccy) < 2 %"))
    r2 = imp.read(doc1("missing_percent(x) = 0"))
    c1 = r1.controls[0].render() if r1.controls else str(r1.unmapped)
    c2 = r2.controls[0].render() if r2.controls else str(r2.unmapped)
    ok = 'BELOW 2%' in c1 and 'BELOW 0%' in c2
    R("IMP-030", ok, f"{c1} || {c2}")

@block("IMP-031")
def _():
    imp = SodaImporter()
    r = imp.read(doc1("missing_count(x) > 0"))
    ok = not r.controls and 'broken' in r.unmapped[0].reason
    R("IMP-031", ok, f"{r.unmapped}")

@block("IMP-032")
def _():
    imp = SodaImporter()
    r = imp.read(doc1("freshness(as_of) < 1d"))
    c = r.controls[0].render()
    ok = 'IS FRESH WITHIN 1440 MINUTES' in c and 'SodaCL measures staleness from now' in r.caveats[0].note
    R("IMP-032", ok, f"{c}; caveat={r.caveats[0].note if r.caveats else None}")

@block("IMP-033")
def _():
    cases = [('30m',30),('4h',240),('1d',1440),('90min',90),('2hr',120)]
    mism = [(t,e,_duration_minutes(t)) for t,e in cases if _duration_minutes(t)!=e]
    R("IMP-033", not mism, f"mismatches={mism}")

@block("IMP-034")
def _():
    imp = SodaImporter()
    r1 = imp.read(doc1("freshness(as_of) < 1w"))
    r2 = imp.read(doc1("freshness(as_of) < yesterday"))
    ok = not r1.controls and 'Durations are written like 30m, 4h or 1d' in r1.unmapped[0].remedy
    ok2 = not r2.controls
    R("IMP-034", ok and ok2, f"1w={r1.unmapped}; yesterday={r2.unmapped}")

@block("IMP-035")
def _():
    imp = SodaImporter()
    r = imp.read(doc1("freshness(as_of) > 1d"))
    ok = not r.controls and 'upper bound' in r.unmapped[0].reason
    R("IMP-035", ok, f"{r.unmapped}")

@block("IMP-036")
def _():
    imp = SodaImporter()
    cases = [('>','AT LEAST 101'),('>=','AT LEAST 100'),('<','AT MOST 99'),('<=','AT MOST 100')]
    detail=[]
    ok=True
    for op,exp in cases:
        r = imp.read(doc1(f"row_count {op} 100"))
        c = r.controls[0].render() if r.controls else str(r.unmapped)
        got_ok = exp in c
        ok &= got_ok
        detail.append(f"{op}: {c} (exp {exp})")
    r_eq = imp.read(doc1("row_count = 100"))
    eq_refused = not r_eq.controls and 'range' in r_eq.unmapped[0].remedy
    ok &= eq_refused
    detail.append(f"=: refused={eq_refused} {r_eq.unmapped}")
    R("IMP-036", ok, "; ".join(detail))

@block("IMP-037")
def _():
    imp = SodaImporter()
    r1 = imp.read(doc1("row_count > -1"))
    r2 = imp.read(doc1("row_count >= 0"))
    c1 = r1.controls[0].render() if r1.controls else None
    c2 = r2.controls[0].render() if r2.controls else None
    flagged1 = c1 is None or 'AT LEAST 0' not in c1
    flagged2 = c2 is None or 'AT LEAST 0' not in c2
    R("IMP-037", flagged1 and flagged2, f"'>-1'->{c1 or r1.unmapped}; '>=0'->{c2 or r2.unmapped}")

@block("IMP-038")
def _():
    imp = SodaImporter()
    r1 = imp.read(doc1("row_count between 100 and 200"))
    r2 = imp.read(doc1("missing_count(x) between 1 and 5"))
    c1 = r1.controls[0].render() if r1.controls else None
    ok = c1 and 'HAS ROW COUNT BETWEEN 100 AND 200' in c1 and not r2.controls
    R("IMP-038", ok, f"rowcount={c1}; metriccount_unmapped={r2.unmapped}")

@block("IMP-039")
def _():
    imp = SodaImporter()
    r = imp.read(doc1("values in (account_id) must exist in accounts (account_id)"))
    c = r.controls[0].render() if r.controls else None
    ok = c and 'REFERENCES accounts.account_id' in c
    R("IMP-039", ok, f"{c}")

@block("IMP-040")
def _():
    imp = SodaImporter()
    r = imp.read(doc1("invalid_count(ccy) = 0"))
    ok = not r.controls and 'validity definition' in r.unmapped[0].remedy.lower() or 'elsewhere' in r.unmapped[0].remedy.lower()
    R("IMP-040", ok, f"{r.unmapped}")

@block("IMP-041")
def _():
    imp = SodaImporter()
    r1 = imp.read({"checks for orders": [{"invalid_count(ccy) = 0": {"valid values":["EUR","USD"]}}]})
    r2 = imp.read({"checks for orders": [{"invalid_count(ccy) = 0": {"valid regex":"^[A-Z]{3}$"}}]})
    r3 = imp.read({"checks for orders": [{"invalid_count(amt) = 0": {"valid min":0,"valid max":100}}]})
    c1 = r1.controls[0].render() if r1.controls else str(r1.unmapped)
    c2 = r2.controls[0].render() if r2.controls else str(r2.unmapped)
    c3 = r3.controls[0].render() if r3.controls else str(r3.unmapped)
    ok = 'IN (' in c1 and 'MATCHES /' in c2 and 'BETWEEN' in c3
    from prama.pql.parser import parse_control
    parses = True
    for c, r_ in ((c1,r1),(c2,r2),(c3,r3)):
        if r_.controls:
            try: parse_control(r_.controls[0].render())
            except Exception: parses = False
    R("IMP-041", ok and parses, f"{c1} || {c2} || {c3}; all_parse={parses}")

@block("IMP-042")
def _():
    imp = SodaImporter()
    doc = {"configurations for orders": [], "checks for orders": ["missing_count(x) = 0"], "for each dataset t": []}
    r = imp.read(doc)
    named_non_checks = [u.source for u in r.unmapped]
    ok = any('configurations' in s for s in named_non_checks) and any('for each' in s for s in named_non_checks) and len(r.controls)==1
    R("IMP-042", ok, f"unmapped={r.unmapped} controls={len(r.controls)}")

@block("IMP-043")
def _():
    imp = SodaImporter()
    r1 = imp.read(doc1("anomaly score for row_count < default"))
    r2 = imp.read({"checks for orders":[{"schema": {"fail":{"when required column missing":["x"]}}}]})
    ok = not r1.controls and len(r1.unmapped)==1
    R("IMP-043", ok, f"r1={r1.unmapped}")

print("=== IMP soda 027-043 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

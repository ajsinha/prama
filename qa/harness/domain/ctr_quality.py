import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.contract.quality import controls_from, LIBRARY_RULES, ROUTABLE_ENGINES, QualityImport
from prama.pql.parser import parse_control

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

def contract_with(quality_block, column='amount', at_column=True):
    prop = {"name": column}
    if at_column:
        prop["quality"] = [quality_block]
    schema = {"name":"orders", "properties":[prop]}
    if not at_column:
        schema["quality"] = [quality_block]
    return {"schema":[schema]}

@block("CTR-017")
def _():
    failures = []
    for rule in LIBRARY_RULES:
        block_ = {"rule": rule.name}
        if rule.name == "validValues":
            block_["validValues"] = ["A","B"]
        if rule.name == "invalidCount":
            block_["validValues"] = ["A","B"]
        if rule.name == "pattern":
            block_["pattern"] = "^[A-Z]+$"
        if rule.name == "rowCount":
            block_["mustBeGreaterOrEqualTo"]=10; block_["mustBeLessOrEqualTo"]=1000
        if rule.name == "freshness":
            block_["mustBeLessThan"]=4
        c = contract_with(block_, at_column=(rule.name not in ("rowCount","freshness")))
        result = controls_from(c)
        if not result.controls:
            failures.append((rule.name, result.refused))
            continue
        try:
            parse_control(result.controls[0])
        except Exception as e:
            failures.append((rule.name, f"parse error: {e}"))
    R("CTR-017", not failures, f"failures={failures}")

@block("CTR-018")
def _():
    c = contract_with({"type":"text","description":"looks sensible"})
    r = controls_from(c)
    ok = not r.controls and len(r.refused)==1 and 'prose' in r.refused[0][1]
    R("CTR-018", ok, f"{r.refused}")

@block("CTR-019")
def _():
    q = "SELECT COUNT(*) FROM orders WHERE amount < 0 AND status = 'PENDING' AND created_at > '2020-01-01' HAVING COUNT(*) = 0"
    c = contract_with({"type":"sql","query":q})
    r = controls_from(c)
    ok = not r.controls and len(r.refused)==1
    reason = r.refused[0][1]
    preserved = any(part in reason for part in q.split()[:5])
    truncated = len(reason) < len(q) + 100
    R("CTR-019", ok and preserved, f"{reason}")

@block("CTR-020")
def _():
    detail = {}
    for engine in ('soda','sodaCL','great-expectations','dbt'):
        c = contract_with({"type":"custom","engine":engine})
        r = controls_from(c)
        detail[engine] = (r.routed, r.refused)
    ok = all(detail[e][0] and 'prama control import --from' in detail[e][0][0][1] for e in detail)
    R("CTR-020", ok, f"{detail}")

@block("CTR-021")
def _():
    c1 = contract_with({"type":"custom","engine":"montecarlo"})
    r1 = controls_from(c1)
    c2 = contract_with({"type":"custom"})
    r2 = controls_from(c2)
    ok = (len(r1.refused)==1 and 'montecarlo' in r1.refused[0][0] and
          len(r2.refused)==1 and 'unnamed engine' in r2.refused[0][0])
    R("CTR-021", ok, f"r1={r1.refused} r2={r2.refused}")

@block("CTR-022")
def _():
    c = contract_with({"rule":"referentialIntegrity"})
    r = controls_from(c)
    ok = not r.controls and len(r.refused)==1
    mapped_listed = all(rule.name in r.refused[0][1] for rule in LIBRARY_RULES)
    R("CTR-022", ok and mapped_listed, f"{r.refused}")

@block("CTR-023")
def _():
    c1 = contract_with({"rule":"duplicateCount","mustBeLessThan":10})
    r1 = controls_from(c1)
    c2 = contract_with({"rule":"duplicateCount","mustBeLessOrEqualTo":10})
    r2 = controls_from(c2)
    ok = 'AT MOST 9 ROWS' in r1.controls[0] and 'AT MOST 10 ROWS' in r2.controls[0]
    R("CTR-023", ok, f"lt10={r1.controls} lte10={r2.controls}")

@block("CTR-024")
def _():
    c1 = contract_with({"rule":"nullCount"})
    r1 = controls_from(c1)
    c2 = contract_with({"rule":"nullPercent"})
    r2 = controls_from(c2)
    ok = 'AT MOST 0 ROWS' in r1.controls[0] and 'BELOW 0%' in r2.controls[0]
    R("CTR-024", ok, f"count={r1.controls} percent={r2.controls}")

@block("CTR-025")
def _():
    c = contract_with({"rule":"nullPercent","mustBeLessThan":2})
    r = controls_from(c)
    ok = not r.controls and len(r.refused)==1 and 'inclusive' in r.refused[0][1]
    R("CTR-025", ok, f"{r.refused}")

@block("CTR-026")
def _():
    c = contract_with({"rule":"duplicateCount","mustBe":5})
    r = controls_from(c)
    ok = not r.controls and 'bound rather than an equality' in r.refused[0][1]
    R("CTR-026", ok, f"{r.refused}")

@block("CTR-027")
def _():
    c = contract_with({"rule":"invalidCount","mustBeGreaterThan":0, "validValues":["A"]})
    r = controls_from(c)
    ok = not r.controls and 'at least' in r.refused[0][1]
    R("CTR-027", ok, f"{r.refused}")

@block("CTR-028")
def _():
    c = contract_with({"rule":"duplicateCount","mustBeLessThan":"ten"})
    r = controls_from(c)
    ok = not r.controls and 'ten' in r.refused[0][1]
    R("CTR-028", ok, f"{r.refused}")

@block("CTR-029")
def _():
    c = contract_with({"rule":"rowCount","mustBeGreaterOrEqualTo":900000,"mustBeLessThan":1200000}, at_column=False)
    r = controls_from(c)
    ok = r.controls and ('1199999' in r.controls[0].replace(',','') or not r.controls)
    R("CTR-029", ok, f"controls={r.controls} refused={r.refused} (expected max 1,199,999 or a refusal; mustBeLessThan used raw as inclusive BETWEEN upper bound would be an off-by-one)")

@block("CTR-030")
def _():
    c = contract_with({"rule":"rowCount","mustBeGreaterOrEqualTo":900000}, at_column=False)
    r = controls_from(c)
    ok = not r.controls and 'minimum and a maximum' in r.refused[0][1]
    R("CTR-030", ok, f"{r.refused}")

@block("CTR-031")
def _():
    c = contract_with({"rule":"freshness","mustBeLessThan":4}, at_column=False)
    r = controls_from(c)
    ok = not r.controls or '4 HOURS' in r.controls[0] or 'hour' in ' '.join(x[1] for x in r.refused).lower()
    R("CTR-031", ok, f"controls={r.controls} refused={r.refused} (mustBeLessThan:4 meaning 4 hours; code renders '{{window}} day' unconditionally)")

@block("CTR-032")
def _():
    c = contract_with({"rule":"validValues","validValues":["GBP","O'Brien",5,True]})
    r = controls_from(c)
    ok = r.controls and "O''Brien" in r.controls[0]
    parses = False
    if r.controls:
        try:
            parse_control(r.controls[0])
            parses = True
        except Exception:
            parses = False
    R("CTR-032", ok and parses, f"{r.controls} parses={parses}")

@block("CTR-033")
def _():
    c = contract_with({"rule":"pattern","pattern":"^/api/.*$"})
    r = controls_from(c)
    ok = not r.controls and 'delimiter' in r.refused[0][1]
    R("CTR-033", ok, f"{r.refused}")

@block("CTR-034")
def _():
    c = contract_with({"rule":"nullCount"}, at_column=False)
    r = controls_from(c)
    ok = not r.controls and 'about a column' in r.refused[0][1]
    R("CTR-034", ok, f"{r.refused}")

@block("CTR-035")
def _():
    c = contract_with({"rule":"uniqueCount","mustBeGreaterThan":100})
    r = controls_from(c)
    ok = not r.controls
    reason = r.refused[0][1] if r.refused else ""
    right_reason = 'distinct' in reason.lower() or 'at least 100 distinct' in reason.lower()
    R("CTR-035", ok, f"refused={r.refused} (Expected: reason correctly describes uniqueCount as a distinct-value count, not framed as 'asks for at least that many failures')")

@block("CTR-036")
def _():
    schema_props = []
    for i in range(4):
        schema_props.append({"name":f"c{i}", "quality":[{"rule":"nullCount"}]})
    for i in range(4,11):
        schema_props.append({"name":f"c{i}", "quality":[{"rule":"notARule"}]})
    c = {"schema":[{"name":"t","properties":schema_props}]}
    r = controls_from(c)
    d = r.describe()
    ok = '4 of 11' in d and all(f"t.c{i}" in d for i in range(4,11))
    R("CTR-036", ok, f"{d[:200]}")

print("=== CTR quality 017-036 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

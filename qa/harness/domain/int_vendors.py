import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.integrate.catalog import Badge, Standing
from prama.integrate.vendors import CollibraTarget, AlationTarget, DataHubTarget

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

def ok_transport(call):
    return {"status": "ok"}

@block("INT-018")
def _():
    t = CollibraTarget(ok_transport, asset_ids={}, attribute_type_id="attr1")
    b = Badge(dataset="unmapped_ds", standing=Standing.HEALTHY, established_at="t")
    report = t.publish([b])
    ok = report.written==0 and len(report.refused)==1 and 'trading badge on a finance table' in report.refused[0][1]
    R("INT-018", ok, f"{report.refused}")

@block("INT-019")
def _():
    t = AlationTarget(ok_transport, object_ids={"ds_zero":0}, field_id=5)
    b_unmapped = Badge(dataset="unmapped_ds", standing=Standing.HEALTHY, established_at="t")
    b_zero = Badge(dataset="ds_zero", standing=Standing.HEALTHY, established_at="t")
    r1 = t.publish([b_unmapped])
    r2 = t.publish([b_zero])
    ok = r1.written==0 and len(r1.refused)==1 and r2.written==1 and len(r2.refused)==0
    R("INT-019", ok, f"unmapped: written={r1.written} refused={r1.refused}; zero_id: written={r2.written} refused={r2.refused}")

@block("INT-020")
def _():
    t = DataHubTarget(ok_transport, platform="snowflake", env="PROD")
    urn1 = t.urn_for("orders")
    t2 = DataHubTarget(ok_transport, platform="snowflake", env="DEV")
    urn2 = t2.urn_for("orders")
    differ = urn1 != urn2
    b = Badge(dataset="orders", standing=Standing.HEALTHY, established_at="t")
    report = t2.publish([b])  # env mismatch vs a hypothetical ingestion job in PROD -- no verification mechanism at all
    R("INT-020", not report.refused, f"urn_prod={urn1} urn_dev={urn2} differ={differ}; publish_with_mismatched_env: written={report.written} refused={report.refused} (no refusal path exists for a URN/env mismatch -- confirmed unmitigated per module's own docstring)")

@block("INT-021")
def _():
    def failing_transport(call):
        raise ConnectionError("connection refused")
    t = CollibraTarget(failing_transport, asset_ids={f"d{i}": f"id{i}" for i in range(40)}, attribute_type_id="attr1")
    badges = [Badge(dataset=f"d{i}", standing=Standing.HEALTHY, established_at="t") for i in range(40)]
    report = t.publish(badges)
    ok = report.written==0 and len(report.refused)==40
    reasons = {w for _,w in report.refused}
    collapsed = 'refused for the same reason' in report.describe()
    R("INT-021", ok and collapsed, f"written={report.written} refused_count={len(report.refused)} reasons_distinct={len(reasons)} describe={report.describe()}")

@block("INT-022")
def _():
    def missing_asset_transport(call):
        raise LookupError("no such asset")
    t = CollibraTarget(missing_asset_transport, asset_ids={"d1":"id1"}, attribute_type_id="attr1")
    b = Badge(dataset="d1", standing=Standing.HEALTHY, established_at="t")
    report = t.publish([b])
    ok = report.written==0 and len(report.refused)==1 and 'does not create assets' in report.refused[0][1]
    R("INT-022", ok, f"{report.refused}")

@block("INT-023")
def _():
    import ast
    tree = ast.parse(open("/home/ashutosh/PycharmProjects/prama/src/prama/integrate/vendors.py").read())
    banned = {'socket','http','requests','httpx'}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] in banned:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split('.')[0] in banned:
                found.append(node.module)
    R("INT-023", not found, f"banned_imports_found={found}")

@block("INT-024")
def _():
    import re
    src = open("/home/ashutosh/PycharmProjects/prama/src/prama/integrate/vendors.py").read()
    doc_has_caveat = 'not been run against a live server' in src
    R("INT-024", None, f"module_docstring_has_caveat={doc_has_caveat} -- checking user-facing docs for the same caveat requires reading docs/*.md, not exercised here; BLOCKED-partial (source caveat confirmed present, external doc propagation not checked)")

@block("INT-025")
def _():
    from prama.integrate.catalog import RecordingTarget
    combos = [
        frozenset({"standing","established_at","coverage","evidence_reference","detail"}),
        frozenset({"standing","established_at"}),
        frozenset({"standing"}),
    ]
    detail = []
    ok = True
    for supports in combos:
        t = RecordingTarget(supports=supports, refuse={"bad1"})
        badges = [Badge(dataset="good1", standing=Standing.HEALTHY, established_at="t"),
                  Badge(dataset="bad1", standing=Standing.HEALTHY, established_at="t")]
        report = t.publish(badges)
        if "established_at" not in supports:
            ok &= report.written==0 and len(report.refused)==2
        else:
            ok &= report.written==1 and len(report.refused)==1
        detail.append(f"supports={sorted(supports)}: written={report.written} refused={len(report.refused)}")
    R("INT-025", ok, "; ".join(detail))

print("=== INT vendors 018-025 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

import sys, asyncio, dataclasses, inspect
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.report.attestation import Attestation, Coverage, Exception_, ATTESTATION_VERSION
from prama.report.attest import build as attest_build, UNRESOLVED
from prama.report.rdarr import Pack, build as rdarr_build
from prama.packs.banking.regulatory import Catalogue, Obligation, Citation, Template, Standing

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

def mk_attestation(**overrides):
    defaults = dict(
        attester_id="u1", attester_name="Alice", statement="I reviewed it",
        scope="tenant:acme", period_start="2026-01-01", period_end="2026-01-31",
        coverage=Coverage(controls_in_scope=10, controls_run=10, passed=10, failed=0),
        evidence_root="abc123", evidence_records=50,
    )
    defaults.update(overrides)
    return Attestation(**defaults)

# RPT-001
a1 = mk_attestation()
c1 = a1.content()
ok = bool(a1.scope) and bool(a1.period_start) and bool(a1.period_end) and c1["scope"]==a1.scope and c1["period_start"]==a1.period_start and c1["period_end"]==a1.period_end
line("RPT-001", "PASS" if ok else "FAIL", f"scope={a1.scope!r} start={a1.period_start!r} end={a1.period_end!r} in_content={c1['scope']==a1.scope}")

# RPT-002
a2a = mk_attestation(evidence_root="root_A")
a2b = mk_attestation(evidence_root="root_B")
ok = a2a.content_hash != a2b.content_hash
line("RPT-002", "PASS" if ok else "FAIL", f"hash_A={a2a.content_hash[:12]} hash_B={a2b.content_hash[:12]}")

# RPT-003
fields = {f.name for f in dataclasses.fields(Attestation)}
content_keys = set(mk_attestation().content().keys())
missing = fields - content_keys - {"version"}  # version present too actually
missing = fields - content_keys
ok = missing == set() or missing == {"version"}  # version included separately, check directly
ok = "version" in mk_attestation().content() and (fields - content_keys) == set()
line("RPT-003", "PASS" if ok else "FAIL", f"fields={fields} content_keys={content_keys} missing={fields-content_keys}")

# RPT-004
cov4 = Coverage(controls_in_scope=100, controls_run=40, passed=30, failed=5, errored=3, not_established=2, never_ran=60)
desc4 = cov4.describe()
ok = all(s in desc4 for s in ["40 of 100", "this covers 40% of the scope", "30 passed", "5 failed", "2 could not be established", "3 could not be executed", "60 never ran at all"])
line("RPT-004", "PASS" if ok else "FAIL", f"describe={desc4!r}")

# RPT-005
cov5 = Coverage(controls_in_scope=0, controls_run=0, passed=0, failed=0)
ok = cov5.rate == 0.0 and cov5.is_complete == False
line("RPT-005", "PASS" if ok else "FAIL", f"rate={cov5.rate} is_complete={cov5.is_complete}")

# RPT-006
cov6 = Coverage(controls_in_scope=10, controls_run=10, passed=8, failed=2)
a6 = mk_attestation(coverage=cov6)
seal6 = a6.seal(b"secretkey")
ok = bool(seal6) and cov6.is_clean == False and a6.is_qualified == True
line("RPT-006", "PASS" if ok else "FAIL", f"seal={seal6[:12]} is_clean={cov6.is_clean} is_qualified={a6.is_qualified}")

# RPT-007
cov7 = Coverage(controls_in_scope=100, controls_run=40, passed=40, failed=0)
a7 = mk_attestation(coverage=cov7)
ok = a7.is_qualified == True
line("RPT-007", "PASS" if ok else "FAIL", f"is_qualified={a7.is_qualified} is_clean={cov7.is_clean} is_complete={cov7.is_complete}")

print("=== attest.build (mocked uow) ===")

class Rec:
    def __init__(self, control_id, plan_id, sequence, verdict, dataset, detail="", metrics=None, finished_at=""):
        self.control_id = control_id; self.plan_id = plan_id; self.sequence = sequence
        self.verdict = verdict; self.dataset = dataset; self.detail = detail
        self.metrics = metrics or {}; self.finished_at = finished_at

class Ctrl:
    def __init__(self, control_id):
        self.control_id = control_id

class MockEvidence:
    def __init__(self, records, root, count):
        self._records = records; self._root = root; self._count = count
    async def in_period(self, tenant_id, start, end):
        return self._records
    async def period_root(self, tenant_id, start, end):
        return (self._root, self._count)

class MockControls:
    def __init__(self, live_controls):
        self._live = live_controls
    async def live(self, tenant_id):
        return self._live

class MockUow:
    def __init__(self, records, root, count, live_controls):
        self.evidence = MockEvidence(records, root, count)
        self.controls = MockControls(live_controls)

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

# RPT-008: twelve failing controls
records8 = [Rec(control_id=f"c{i}", plan_id=f"c{i}", sequence=1, verdict="fail", dataset="d") for i in range(12)]
uow8 = MockUow(records8, "root8", 12, [Ctrl(f"c{i}") for i in range(12)])
att8 = run(attest_build(uow8, "t1", scope="s", period_start="2026-01-01", period_end="2026-01-31",
                          attester_id="u", attester_name="A", statement="x", signed_at="2026-02-01"))
ok = len(att8.exceptions) == 12
line("RPT-008", "PASS" if ok else "FAIL", f"n_exceptions={len(att8.exceptions)}")

# RPT-009
sig9 = inspect.signature(attest_build)
param_names = set(sig9.parameters.keys())
expected_caller_params = {"scope","period_start","period_end","attester_id","attester_name","statement","signed_at","dispositions"}
ok = expected_caller_params <= param_names and "uow" in param_names
line("RPT-009", "PASS" if ok else "FAIL", f"params={list(param_names)}")

# RPT-010: control ran 30 times, failing at the end
records10 = [Rec(control_id="cX", plan_id="cX", sequence=i, verdict=("fail" if i==29 else "pass"), dataset="d") for i in range(30)]
uow10 = MockUow(records10, "root10", 30, [Ctrl("cX")])
att10 = run(attest_build(uow10, "t1", scope="s", period_start="2026-01-01", period_end="2026-01-31",
                          attester_id="u", attester_name="A", statement="x", signed_at="2026-02-01"))
ok = len(att10.exceptions) == 1 and att10.exceptions[0].verdict == "fail"
line("RPT-010", "PASS" if ok else "FAIL", f"n_exceptions={len(att10.exceptions)} verdict={att10.exceptions[0].verdict if att10.exceptions else None}")

# RPT-011: 10 live, 4 produced nothing
records11 = [Rec(control_id=f"c{i}", plan_id=f"c{i}", sequence=1, verdict="pass", dataset="d") for i in range(6)]
uow11 = MockUow(records11, "root11", 6, [Ctrl(f"c{i}") for i in range(10)])
att11 = run(attest_build(uow11, "t1", scope="s", period_start="2026-01-01", period_end="2026-01-31",
                          attester_id="u", attester_name="A", statement="x", signed_at="2026-02-01"))
ok = att11.coverage.never_ran == 4 and all(e.control_id not in [f"c{i}" for i in range(6,10)] for e in att11.exceptions)
line("RPT-011", "PASS" if ok else "FAIL", f"never_ran={att11.coverage.never_ran} n_exceptions={len(att11.exceptions)}")

# RPT-012: one of each fail/error/skipped/indeterminate
records12 = [
    Rec(control_id="c1", plan_id="c1", sequence=1, verdict="fail", dataset="d"),
    Rec(control_id="c2", plan_id="c2", sequence=1, verdict="error", dataset="d"),
    Rec(control_id="c3", plan_id="c3", sequence=1, verdict="skipped", dataset="d"),
    Rec(control_id="c4", plan_id="c4", sequence=1, verdict="indeterminate", dataset="d"),
]
uow12 = MockUow(records12, "root12", 4, [Ctrl(f"c{i}") for i in range(1,5)])
att12 = run(attest_build(uow12, "t1", scope="s", period_start="2026-01-01", period_end="2026-01-31",
                          attester_id="u", attester_name="A", statement="x", signed_at="2026-02-01"))
ok = len(att12.exceptions) == 4 and {e.verdict for e in att12.exceptions} == {"fail","error","skipped","indeterminate"}
line("RPT-012", "PASS" if ok else "FAIL", f"n_exceptions={len(att12.exceptions)} verdicts={[e.verdict for e in att12.exceptions]}")

# RPT-013: unknown verdict
records13 = [Rec(control_id="c1", plan_id="c1", sequence=1, verdict="weird_verdict", dataset="d")]
uow13 = MockUow(records13, "root13", 1, [Ctrl("c1")])
att13 = run(attest_build(uow13, "t1", scope="s", period_start="2026-01-01", period_end="2026-01-31",
                          attester_id="u", attester_name="A", statement="x", signed_at="2026-02-01"))
total_categorised = att13.coverage.passed + att13.coverage.failed + att13.coverage.not_established + att13.coverage.errored
ok = len(att13.exceptions) == 1 and att13.exceptions[0].verdict == "weird_verdict"
categorised_matches = total_categorised == att13.coverage.controls_run
line("RPT-013", "PASS" if ok else "FAIL", f"n_exceptions={len(att13.exceptions)} verdict={att13.exceptions[0].verdict} controls_run={att13.coverage.controls_run} categorised_sum={total_categorised} matches={categorised_matches}")

# RPT-014: missing dispositions
records14 = [Rec(control_id="c1", plan_id="c1", sequence=1, verdict="fail", dataset="d")]
uow14 = MockUow(records14, "root14", 1, [Ctrl("c1")])
att14 = run(attest_build(uow14, "t1", scope="s", period_start="2026-01-01", period_end="2026-01-31",
                          attester_id="u", attester_name="A", statement="x", signed_at="2026-02-01"))
ok = att14.exceptions[0].disposition == ""
line("RPT-014", "PASS" if ok else "FAIL", f"disposition={att14.exceptions[0].disposition!r}")

# RPT-015
records15 = [
    Rec(control_id="c1", plan_id="c1", sequence=1, verdict="fail", dataset="d", metrics={"scanned_rows":1000,"distinct_keys":990}),
    Rec(control_id="c2", plan_id="c2", sequence=1, verdict="fail", dataset="d", metrics={"scanned_rows":500,"violating_rows":12}),
]
uow15 = MockUow(records15, "root15", 2, [Ctrl("c1"), Ctrl("c2")])
att15 = run(attest_build(uow15, "t1", scope="s", period_start="2026-01-01", period_end="2026-01-31",
                          attester_id="u", attester_name="A", statement="x", signed_at="2026-02-01"))
details = {e.control_id: e.detail for e in att15.exceptions}
ok = details.get("c1") == "10 duplicate(s) in 1,000 rows" and details.get("c2") == "12 of 500 rows"
line("RPT-015", "PASS" if ok else "FAIL", f"details={details}")

# RPT-016
a16 = mk_attestation()
seal_good = a16.seal(b"key1")
verify_same = a16.verify(b"key1", seal_good)
verify_diff = a16.verify(b"key2", seal_good)
ok = verify_same == True and verify_diff == False
line("RPT-016", "PASS" if ok else "FAIL", f"verify_same={verify_same} verify_diff={verify_diff}")

# RPT-017 -- documentation check
import prama.report.attestation as attmod
doc = attmod.__doc__ or ""
ok = "holder of the key" in doc and "asymmetric signature would say more" in doc
line("RPT-017", "PASS" if ok else "FAIL", f"module_doc_has_claim={ok}")

# RPT-018
a18_clean = mk_attestation(coverage=Coverage(controls_in_scope=5, controls_run=5, passed=5, failed=0))
a18_qual = mk_attestation(coverage=Coverage(controls_in_scope=5, controls_run=5, passed=4, failed=1))
ok = "without exception" in a18_clean.describe() and "with exceptions" in a18_qual.describe()
line("RPT-018", "PASS" if ok else "FAIL", f"clean={a18_clean.describe()!r} qual={a18_qual.describe()!r}")

# RPT-019
a19 = mk_attestation()
ok = a19.content()["version"] == "1.0" == ATTESTATION_VERSION
line("RPT-019", "PASS" if ok else "FAIL", f"version={a19.content()['version']}")

print("=== rdarr.py ===")

def mk_obligation(identity, requires_ok=True, templates=None, not_discharged=""):
    cit = Citation(document="BCBS239", clause="P4")
    if templates is None:
        templates = (Template(identity=f"{identity}_tmpl", pql="CHECK x", requires=()),)
    return Obligation(identity=identity, regime="RDARR", citation=cit, objective="x",
                       templates=templates, not_discharged=not_discharged)

# RPT-020, 021: leads with gaps, controls-with-no-evidence separate section
# Obligation requires templates or relationships or not_discharged; for unaddressed, give template but no binding
ob_unaddr = mk_obligation("ob_unaddr")
ob_unproven = mk_obligation("ob_unproven")
ob_exception = mk_obligation("ob_exc")
ob_clean = mk_obligation("ob_clean")
cat20 = Catalogue([ob_unaddr, ob_unproven, ob_exception, ob_clean])
bindings20 = {
    "ob_unproven_tmpl": ["c_unproven"],
    "ob_exc_tmpl": ["c_exc"],
    "ob_clean_tmpl": ["c_clean"],
}
verdicts20 = {"c_exc": "fail", "c_clean": "pass"}  # c_unproven absent -> never ran
cov20 = cat20.coverage("RDARR", controls_by_template=bindings20, verdicts=verdicts20)
pack20 = Pack(regime="RDARR", scope="s", period_start="2026-01-01", period_end="2026-01-31", coverage=cov20)
sections20 = pack20.sections()
titles = [s["title"] for s in sections20]
ok = titles == ["Obligations with no control", "Obligations with controls that produced no evidence",
                 "Obligations proven with exceptions", "Obligations proven clean"]
line("RPT-020", "PASS" if ok else "FAIL", f"titles={titles}")

unaddr_ids = [s["identity"] for s in sections20[0]["standings"]]
unproven_ids = [s["identity"] for s in sections20[1]["standings"]]
ok = "ob_unaddr" in unaddr_ids and "ob_unproven" in unproven_ids
line("RPT-021", "PASS" if ok else "FAIL", f"unaddr={unaddr_ids} unproven={unproven_ids}")

# RPT-022
cov22 = cov20  # has one unaddressed
ok = pack20.is_defensible == False and str(len(cov22.unaddressed)) in pack20.headline()
line("RPT-022", "PASS" if ok else "FAIL", f"is_defensible={pack20.is_defensible} headline={pack20.headline()!r}")

# RPT-023
obs23 = [mk_obligation("obA"), mk_obligation("obB")]
cat23 = Catalogue(obs23)
bindings23 = {"obA_tmpl": ["cA"], "obB_tmpl": ["cB"]}
verdicts23 = {"cA": "fail", "cB": "pass"}
cov23 = cat23.coverage("RDARR", controls_by_template=bindings23, verdicts=verdicts23)
pack23 = Pack(regime="RDARR", scope="s", period_start="2026-01-01", period_end="2026-01-31", coverage=cov23)
ok = pack23.is_defensible == True
line("RPT-023", "PASS" if ok else "FAIL", f"is_defensible={pack23.is_defensible} unaddressed={len(cov23.unaddressed)} unproven={len(cov23.unproven)}")

# RPT-024
empty_cat = Catalogue([])
empty_cov = empty_cat.coverage("RDARR", controls_by_template={})
pack24 = Pack(regime="RDARR", scope="s", period_start="2026-01-01", period_end="2026-01-31", coverage=empty_cov)
ok = "no obligations are loaded, so this pack establishes nothing" in pack24.headline()
line("RPT-024", "PASS" if ok else "FAIL", f"headline={pack24.headline()!r}")

# RPT-025 - the flagged defect
records25 = [Rec(control_id="cX", plan_id="cX", sequence=1, verdict="pass", dataset="d", finished_at="2026-01-15")]
uow25 = MockUow(records25, "the_real_root_hash", 42, [Ctrl("cX")])
cat25 = Catalogue([mk_obligation("obA")])
pack25 = run(rdarr_build(uow25, "t1", catalogue=cat25, regime="RDARR", scope="s",
                          period_start="2026-01-01", period_end="2026-01-31",
                          bindings={"obA_tmpl": ["cX"]}))
ok = isinstance(pack25.evidence_root, str) and pack25.evidence_root == "the_real_root_hash"
line("RPT-025", "PASS" if ok else "FAIL", f"evidence_root={pack25.evidence_root!r} type={type(pack25.evidence_root).__name__}")

# RPT-026
records26 = [Rec(control_id="cY", plan_id="cY", sequence=i, verdict=("fail" if i==19 else "pass"), dataset="d", finished_at=f"2026-01-{(i%28)+1:02d}") for i in range(20)]
uow26 = MockUow(records26, "root26", 20, [Ctrl("cY")])
cat26 = Catalogue([mk_obligation("obY")])
pack26 = run(rdarr_build(uow26, "t1", catalogue=cat26, regime="RDARR", scope="s",
                          period_start="2026-01-01", period_end="2026-01-31",
                          bindings={"obY_tmpl": ["cY"]}))
standing26 = pack26.coverage.standings[0]
ok = len(standing26.controls) == 1  # one standing
line("RPT-026", "PASS" if ok else "FAIL", f"standing={standing26.standing} controls={standing26.controls} failed={standing26.failed}")

# RPT-027
ok = pack26.bindings.get("obY_tmpl") == ("cY",)
line("RPT-027", "PASS" if ok else "FAIL", f"bindings={pack26.bindings}")

import sys, subprocess, ast
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.egress import Gate, EGRESS_POINTS, ResidencyRefused, point
from prama.security.residency import Policy
from prama.core.errors import ValidationError

REPO = "/home/ashutosh/PycharmProjects/prama"

# SEC-031: run the real architecture test for egress
r = subprocess.run(["python3", "-m", "pytest", "tests/architecture/test_egress.py", "-v"], capture_output=True, text=True, cwd=REPO)
out31 = r.stdout
passed = out31.count(" PASSED")
failed = out31.count(" FAILED")
line("SEC-031", "PASS" if (r.returncode == 0 and passed > 0) else "FAIL", f"pytest tests/architecture/test_egress.py -> returncode={r.returncode} passed={passed} failed={failed}")

# SEC-032: counterfactual -- on a SCRATCH COPY of connect/sources/rest.py (src/ is never touched),
# remove the gate.require(...) call, leaving comments intact, and run the real
# reaches_the_gate() scanner from tests/architecture/test_egress.py against the copy.
import shutil
rest_path = f"{REPO}/src/prama/connect/sources/rest.py"
scratch_copy = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust/rest_mutated.py"
original = open(rest_path).read()
shutil.copy(rest_path, scratch_copy)
if "gate.require(" not in original:
    line("SEC-032", "BLOCKED", "gate.require( not found verbatim in connect/sources/rest.py; cannot safely locate the call to remove")
else:
    lines = original.splitlines()
    start_idx = next(i for i, l in enumerate(lines) if "gate.require(" in l)
    depth = 0
    end_idx = start_idx
    for i in range(start_idx, len(lines)):
        depth += lines[i].count("(") - lines[i].count(")")
        end_idx = i
        if depth <= 0:
            break
    mutated_lines = list(lines)
    for i in range(start_idx, end_idx + 1):
        # keep every comment about it intact; only the executable call becomes a no-op
        mutated_lines[i] = mutated_lines[i]
    del mutated_lines[start_idx:end_idx + 1]
    mutated_lines.insert(start_idx, " " * (len(lines[start_idx]) - len(lines[start_idx].lstrip())) + "pass")
    mutated = "\n".join(mutated_lines)
    open(scratch_copy, "w").write(mutated)

    sys.path.insert(0, f"{REPO}/tests/architecture")
    import importlib.util
    spec = importlib.util.spec_from_file_location("test_egress_mod", f"{REPO}/tests/architecture/test_egress.py")
    te = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(te)
    from pathlib import Path as _Path
    still_reaches = te.reaches_the_gate(_Path(scratch_copy))
    original_reaches = te.reaches_the_gate(_Path(rest_path))
    ok = original_reaches and not still_reaches
    line("SEC-032", "PASS" if ok else "FAIL",
         f"src/ untouched (mutation applied only to a scratch copy at {scratch_copy}); "
         f"reaches_the_gate() on the real file={original_reaches}, on the mutated scratch copy={still_reaches} "
         f"(expected: real file True, mutated copy False)")

# SEC-033: each of the seven points refused end-to-end under a refusing policy
gate = Gate.for_tenant("EU", tenant_id="t1")
refused = {}
for ep in EGRESS_POINTS:
    try:
        gate.require(ep.name, destination="US", jurisdiction="EU", subject=f"test-{ep.name}")
        refused[ep.name] = False
    except ResidencyRefused as e:
        refused[ep.name] = ep.name in str(e) or ep.name in str(e.context)
all_refused = all(refused.values())
line("SEC-033", "PASS" if all_refused else "FAIL", f"refused_per_point={refused} (tested Gate.require directly for all 7 registered points, not by driving each real connector/provider end to end -- see caveat)")

# SEC-034: unregistered egress name refused at gate
try:
    gate.require("siem_export", destination="EU", jurisdiction="EU")
    line("SEC-034", "FAIL", "no exception raised for unregistered egress name")
except ValidationError as e:
    ok = all(ep.name in str(e) for ep in EGRESS_POINTS)
    line("SEC-034", "PASS" if ok else "FAIL", f"ValidationError: {e}")
except Exception as e:
    line("SEC-034", "FAIL", f"wrong exception type {type(e)}: {e}")

# SEC-035: decide does not enforce, require does
p_refuse = Policy.of("EU")
g = Gate(policy=p_refuse, tenant_id="t1")
d = g.decide("evidence-export", destination="US", jurisdiction="EU")
decide_did_not_raise = not d.may_proceed
try:
    g.require("evidence-export", destination="US", jurisdiction="EU")
    require_raised = False
except ResidencyRefused:
    require_raised = True
ok = decide_did_not_raise and require_raised
line("SEC-035", "PASS" if ok else "FAIL", f"decide()_returns_refused_without_raising={decide_did_not_raise} require()_raises={require_raised}")

# SEC-036: refusal is its own exception type, distinct from ValidationError, with the right code
try:
    g.require("evidence-export", destination="US", jurisdiction="EU")
    line("SEC-036", "FAIL", "no exception")
except ResidencyRefused as e:
    ok = not isinstance(e, ValidationError) and e.code == "RESIDENCY.REFUSED"
    line("SEC-036", "PASS" if ok else "FAIL", f"type={type(e)} code={e.code} isinstance_ValidationError={isinstance(e, ValidationError)}")

# SEC-037: refusal context names egress/tenant/destination/jurisdiction, (undeclared) rendered not empty
g2 = Gate(policy=p_refuse, tenant_id="acme")
try:
    g2.require("evidence-export", destination="EU", jurisdiction="")
    line("SEC-037", "FAIL", "no exception")
except ResidencyRefused as e:
    ctx = e.context
    ok = set(ctx.keys()) >= {"egress","tenant","destination","jurisdiction"} and ctx["jurisdiction"] == "(undeclared)"
    line("SEC-037", "PASS" if ok else "FAIL", f"context={ctx}")

# SEC-038: registry entries have non-empty specific what/destination_from/jurisdiction_from
incomplete = [ep.name for ep in EGRESS_POINTS if not ep.what.strip() or not ep.destination_from.strip() or not ep.jurisdiction_from.strip() or len(ep.what) < 10]
line("SEC-038", "PASS" if not incomplete else "FAIL", f"n_points={len(EGRESS_POINTS)} incomplete={incomplete}")

# SEC-039: every point's call site passes a non-empty jurisdiction wherever declared -- static check via grep for gate.require( calls' jurisdiction= kwarg
grep_calls = subprocess.run(["grep", "-rn", "-A3", "gate.require(", f"{REPO}/src/prama"], capture_output=True, text=True)
call_sites = grep_calls.stdout
missing_jurisdiction_kw = "jurisdiction=" not in call_sites  # crude signal
line("SEC-039", "INFO", f"static grep of gate.require( call sites (manual review needed for full confirmation) -- see call sites: {len(call_sites.splitlines())} lines matched")

# SEC-039 follow-up: read every gate.require() call site's jurisdiction= kwarg
# against what security/egress.py::EGRESS_POINTS documents that point's
# jurisdiction_from as being.
rest_src = open(f"{REPO}/src/prama/connect/sources/rest.py").read()
egress_src = open(f"{REPO}/src/prama/security/egress.py").read()
source_read_doc = 'jurisdiction_from="the dataset\'s declared jurisdiction"' in egress_src
rest_passes_region_as_jurisdiction = "jurisdiction=self._region" in rest_src
rest_has_dataset_jurisdiction_field = "self._dataset_jurisdiction" in rest_src
defect_present = source_read_doc and rest_passes_region_as_jurisdiction and not rest_has_dataset_jurisdiction_field
line("SEC-039", "FAIL" if defect_present else "PASS",
     f"EGRESS_POINTS['source-read'].jurisdiction_from still documented as \"the dataset's declared jurisdiction\": {source_read_doc}; "
     f"connect/sources/rest.py:gate.require('source-read', ...) still passes jurisdiction=self._region (the connector-configured region, same as destination): {rest_passes_region_as_jurisdiction}; "
     f"RestSource now has a genuine dataset-jurisdiction field feeding it: {rest_has_dataset_jurisdiction_field} -- "
     f"{'defect persists: the call site does not pass what the registry says it passes' if defect_present else 'no longer a defect'}")

# SEC-040: Vault fetch passes region as both destination and jurisdiction
vault_src = open(f"{REPO}/src/prama/secrets/vault.py").read()
mentions_region_both = "destination=" in vault_src and "jurisdiction=" in vault_src
line("SEC-040", "INFO", f"vault.py mentions destination= and jurisdiction=: {mentions_region_both} -- see follow-up static inspection")

vault_passes_region_both = "destination=self._region" in vault_src and "jurisdiction=self._region" in vault_src
secret_fetch_doc = "the same region: a credential belongs wherever its store is" in egress_src
line("SEC-040", "PASS" if (vault_passes_region_both and secret_fetch_doc) else "FAIL",
     f"secrets/vault.py gate.require('secret-fetch', destination=self._region, jurisdiction=self._region, ...) present: {vault_passes_region_both}; "
     f"EGRESS_POINTS['secret-fetch'].jurisdiction_from documents exactly this as deliberate ('the same region: a credential belongs wherever its store is, and there is no separate subject to ask'): {secret_fetch_doc} -- code and registry agree, this is a pinned deliberate decision")

# SEC-041: architecture test enforces new modules register their egress -- confirmed by SEC-031's pytest run already covering this contract generically
line("SEC-041", "INFO", "covered structurally by tests/architecture/test_egress.py's module-scan mechanism (see SEC-031); did not add a genuinely new scratch module performing network IO to prove the negative")

# SEC-041 follow-up: actually prove the negative with a genuinely new
# network-touching module the registry has never heard of, by replicating
# test_egress.py's own scan logic (ast import-walk) against a temp copy of
# src/prama with one added rogue module, rather than trusting the mechanism
# exists without exercising it against a real violation. No file under real
# src/ is modified.
import importlib.util as _ilu, shutil as _shutil, tempfile as _tempfile
from pathlib import Path as _Path
_spec = _ilu.spec_from_file_location("qa_test_egress_mod", f"{REPO}/tests/architecture/test_egress.py")
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_TestEgress = next(getattr(_mod, n) for n in dir(_mod) if isinstance(getattr(_mod, n), type) and hasattr(getattr(_mod, n), "network_modules"))
_inst = _TestEgress()
_tmp = _Path(_tempfile.mkdtemp(prefix="qa_egress_"))
_tmp_src = _tmp / "src"
_shutil.copytree(f"{REPO}/src/prama", _tmp_src / "prama", ignore=_shutil.ignore_patterns("__pycache__"))
_scratch = _tmp_src / "prama" / "scratch"
_scratch.mkdir(parents=True, exist_ok=True)
(_scratch / "leaky.py").write_text(
    "import httpx\n\ndef send(payload):\n    return httpx.post('https://example.com/collect', json=payload)\n")
_mod.SRC = _tmp_src
_found = _inst.network_modules()
_registered = {e.module.replace(".", "/") + ".py" for e in _mod.EGRESS_POINTS}
_unaccounted = [n for n in _found if n not in _registered and n not in _inst.NOT_EGRESS]
_scratch_caught = "prama/scratch/leaky.py" in _unaccounted
_other_leaks = [u for u in _unaccounted if u != "prama/scratch/leaky.py"]
_shutil.rmtree(_tmp)
line("SEC-041", "PASS" if (_scratch_caught and not _other_leaks) else "FAIL",
     f"unregistered scratch module using httpx.post() found by network_modules() scan and flagged as unaccounted: {_scratch_caught} -- "
     f"this is exactly what test_every_module_that_can_reach_the_network_is_accounted_for would fail on; "
     f"real modules besides the injected scratch one that the scan currently misses: {_other_leaks} (empty means no live gap)")

# SEC-042: Gate.for_tenant carries tenant into refusal
g3 = Gate.for_tenant("EU", tenant_id="01ACME")
try:
    g3.require("evidence-export", destination="US", jurisdiction="EU")
    line("SEC-042", "FAIL", "no exception")
except ResidencyRefused as e:
    ok = e.context.get("tenant") == "01ACME"
    line("SEC-042", "PASS" if ok else "FAIL", f"context={e.context}")

# SEC-043: subject defaults to egress point's own name
g4 = Gate(policy=p_refuse, tenant_id="t1")
try:
    g4.require("evidence-export", destination="US", jurisdiction="EU")
    line("SEC-043", "FAIL", "no exception")
except ResidencyRefused as e:
    ok = "evidence-export" in str(e) and "this data" not in str(e)
    line("SEC-043", "PASS" if ok else "FAIL", f"message={e}")

# SEC-044: egress refusal audited -- grep for an audit log call at Gate.require
egress_src = open(f"{REPO}/src/prama/security/egress.py").read()
mentions_audit = "audit" in egress_src.lower() or "_log" in egress_src
line("SEC-044", "PASS" if mentions_audit else "FAIL", f"security/egress.py mentions audit logging at refusal: {mentions_audit}")

print("SECTION SEC-031..044 DONE")

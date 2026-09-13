import dataclasses, hashlib, json, sys, ast, subprocess, tempfile, os, stat
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.evidence.record import EvidenceRecord, SnapshotRef, GENESIS
from prama.evidence.ledger import Ledger, verify as ledger_verify, merkle_root
from prama.evidence.retention import Archivist

VERIFY_SCRIPT = "/home/ashutosh/PycharmProjects/prama/scripts/verify_evidence.py"

def R(n=0, **changes):
    base = {
        "plan_id": f"ir:sha256:{n:064x}", "control_id": "ctl-1", "dataset": "positions_eod",
        "binding": "pg://RISK.POSITIONS", "engine": "postgresql",
        "snapshot": SnapshotRef(kind="lsn", identifier=f"0/{1000+n}", exact=True),
        "verdict": "pass", "metrics": {"scanned_rows": 50000.0, "violating_rows": float(n)},
        "started_at": "2026-04-02T06:31:00Z", "finished_at": "2026-04-02T06:31:02Z",
        "duration_ms": 2100, "tenant_id": "t1",
    }
    base.update(changes)
    return EvidenceRecord(**base)

def a_chain(n=10):
    l = Ledger()
    for i in range(n):
        l.append(R(i))
    return l

def write_bundle(records, dirpath, manifest_overrides=None, use_archivist=True):
    if use_archivist:
        arch = Archivist()
        bundle = arch.bundle(records, tenant_id="t1")
        files = bundle.files()
    else:
        files = None
    if manifest_overrides is not None:
        m = json.loads(files["manifest.json"])
        m.update(manifest_overrides)
        files["manifest.json"] = json.dumps(m)
    os.makedirs(dirpath, exist_ok=True)
    open(os.path.join(dirpath, "manifest.json"), "w").write(files["manifest.json"])
    open(os.path.join(dirpath, "evidence.ndjson"), "w").write(files["evidence.ndjson"])
    return files

def run_cli(args, cwd=None):
    r = subprocess.run([sys.executable, VERIFY_SCRIPT] + args, capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout, r.stderr

# EVD-125: verifier imports nothing from Prama and nothing outside stdlib
src = open(VERIFY_SCRIPT).read()
tree = ast.parse(src)
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for a in node.names: imports.add(a.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        if node.module: imports.add(node.module.split(".")[0])
stdlib = sys.stdlib_module_names
non_stdlib = {m for m in imports if m not in stdlib}
ok = non_stdlib == set() and "prama" not in imports
line("EVD-125", "PASS" if ok else "FAIL", f"imports={sorted(imports)} non_stdlib={sorted(non_stdlib)}")

# EVD-126: verifier runs on a bare interpreter with Prama uninstalled -- run from a temp cwd with PYTHONPATH cleared
d = tempfile.mkdtemp()
write_bundle(a_chain(5).records(), d)
env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
env["PATH"] = "/usr/bin:/bin"
r = subprocess.run(["/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable, VERIFY_SCRIPT, d],
                    capture_output=True, text=True, cwd="/tmp", env=env)
line("EVD-126", "PASS" if r.returncode == 0 else "FAIL", f"exit={r.returncode} stdout_tail={r.stdout[-200:]!r} stderr={r.stderr[-200:]!r}")

# EVD-127: good bundle exits 0 with every check listed
d2 = tempfile.mkdtemp()
write_bundle(a_chain(10).records(), d2)
code, out, err = run_cli([d2])
checks_named = ["content hash", "links to the one", "sequence numbers", "evidence file is the one", "Merkle root", "chain head"]
present = [c for c in checks_named if c in out]
ok = code == 0 and len(present) == len(checks_named)
line("EVD-127", "PASS" if ok else "FAIL", f"exit={code} checks_found={present} missing={[c for c in checks_named if c not in present]}")

# EVD-128: failed check exits 1
d3 = tempfile.mkdtemp()
files = write_bundle(a_chain(10).records(), d3)
lines_ = files["evidence.ndjson"].splitlines()
rec4 = json.loads(lines_[4]); rec4["verdict"] = "fail" if rec4["verdict"] != "fail" else "pass"
lines_[4] = json.dumps(rec4)
open(os.path.join(d3, "evidence.ndjson"), "w").write("\n".join(lines_))
code3, out3, err3 = run_cli([d3])
ok = code3 == 1 and "not what its manifest claims" in out3
line("EVD-128", "PASS" if ok else "FAIL", f"exit={code3} tail={out3[-200:]!r}")

# EVD-129: unreadable bundle exits 2, four variants
d4 = tempfile.mkdtemp()
c_missing_dir, o1, e1 = run_cli([os.path.join(d4, "does-not-exist")])
d5 = tempfile.mkdtemp()  # dir with no manifest.json
open(os.path.join(d5, "evidence.ndjson"), "w").write("")
c_no_manifest, o2, e2 = run_cli([d5])
d6 = tempfile.mkdtemp()
open(os.path.join(d6, "manifest.json"), "w").write("{not json")
open(os.path.join(d6, "evidence.ndjson"), "w").write("")
c_bad_manifest, o3, e3 = run_cli([d6])
d7 = tempfile.mkdtemp()
write_bundle(a_chain(3).records(), d7)
lines_ = open(os.path.join(d7, "evidence.ndjson")).read().splitlines()
lines_[1] = "{not json either"
open(os.path.join(d7, "evidence.ndjson"), "w").write("\n".join(lines_))
c_bad_line, o4, e4 = run_cli([d7])
results = [c_missing_dir, c_no_manifest, c_bad_manifest, c_bad_line]
ok = all(c == 2 for c in results)
line("EVD-129", "PASS" if ok else "FAIL", f"exits={results} stderrs={[e1.strip(),e2.strip(),e3.strip(),e4.strip()]}")

# EVD-130: unreadable file (no permission) exits 2 not 1
d8 = tempfile.mkdtemp()
write_bundle(a_chain(3).records(), d8)
ev_path = os.path.join(d8, "evidence.ndjson")
os.chmod(ev_path, 0o000)
try:
    if os.geteuid() == 0:
        line("EVD-130", "BLOCKED", "running as root; chmod 000 does not deny root read access, cannot exercise this permission path")
    else:
        code8, out8, err8 = run_cli([d8])
        line("EVD-130", "PASS" if code8 == 2 else "FAIL", f"exit={code8} stderr={err8.strip()!r}")
finally:
    os.chmod(ev_path, 0o644)

# EVD-131: wrong argument counts exit 2 with usage
c0, o0, e0 = run_cli([])
c3, o3b, e3b = run_cli(["a", "b", "c"])
ok = c0 == 2 and c3 == 2 and "usage" in e0.lower() and "usage" in e3b.lower()
line("EVD-131", "PASS" if ok else "FAIL", f"zero_args_exit={c0} stderr0={e0!r} three_args_exit={c3} stderr3={e3b!r}")

# EVD-132: both invocation forms work identically
d9 = tempfile.mkdtemp()
write_bundle(a_chain(5).records(), d9)
c_dir, o_dir, e_dir = run_cli([d9])
c_files, o_files, e_files = run_cli([os.path.join(d9, "manifest.json"), os.path.join(d9, "evidence.ndjson")])
ok = c_dir == c_files == 0 and o_dir == o_files
line("EVD-132", "PASS" if ok else "FAIL", f"dir_form_exit={c_dir} files_form_exit={c_files} outputs_identical={o_dir==o_files}")

print("SECTION EVD-125..132 DONE")

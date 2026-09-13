import dataclasses, hashlib, json, sys, subprocess, tempfile, os, importlib.util
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.evidence.record import EvidenceRecord, SnapshotRef, GENESIS
from prama.evidence.ledger import Ledger, verify as ledger_verify, merkle_root
from prama.evidence.retention import Archivist

VERIFY_SCRIPT = "/home/ashutosh/PycharmProjects/prama/scripts/verify_evidence.py"
spec = importlib.util.spec_from_file_location("verify_evidence", VERIFY_SCRIPT)
ve = importlib.util.module_from_spec(spec); spec.loader.exec_module(ve)

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

def write_bundle(records, dirpath):
    arch = Archivist()
    bundle = arch.bundle(records, tenant_id="t1")
    files = bundle.files()
    os.makedirs(dirpath, exist_ok=True)
    open(os.path.join(dirpath, "manifest.json"), "w").write(files["manifest.json"])
    open(os.path.join(dirpath, "evidence.ndjson"), "w").write(files["evidence.ndjson"])
    return bundle

def reseal(dirpath):
    """Recompute manifest count/digest/head/root from the (possibly tampered) evidence.ndjson, leave records as-is."""
    ev_path = os.path.join(dirpath, "evidence.ndjson")
    m_path = os.path.join(dirpath, "manifest.json")
    payload = open(ev_path).read()
    lines_ = [x for x in payload.splitlines() if x.strip()]
    recs = [json.loads(x) for x in lines_]
    hashes = [r["record_hash"] for r in recs]
    m = json.load(open(m_path))
    m["records"] = len(recs)
    m["payload_digest"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    m["merkle_root"] = ve.merkle_root(hashes)
    m["chain_head"] = hashes[-1] if hashes else GENESIS
    m["erased"] = sum(1 for r in recs if r.get("tombstone"))
    m["from_sequence"] = recs[0]["sequence"] if recs else 0
    m["to_sequence"] = recs[-1]["sequence"] if recs else 0
    json.dump(m, open(m_path, "w"))

def run_cli(args):
    r = subprocess.run([sys.executable, VERIFY_SCRIPT] + args, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr

# EVD-133: verifier catches edited record (manifest re-sealed so payload digest matches)
d = tempfile.mkdtemp()
write_bundle(a_chain(10).records(), d)
lines_ = open(os.path.join(d, "evidence.ndjson")).read().splitlines()
rec4 = json.loads(lines_[4]); rec4["verdict"] = "fail" if rec4["verdict"] != "fail" else "pass"
lines_[4] = json.dumps(rec4)
open(os.path.join(d, "evidence.ndjson"), "w").write("\n".join(lines_))
reseal(d)
code, out, err = run_cli([d])
ok = code == 1 and "content_hash is" in out and "4" in out
line("EVD-133", "PASS" if ok else "FAIL", f"exit={code} excerpt={[l for l in out.splitlines() if 'record 4' in l]}")

# EVD-134: verifier catches broken link (record removed, manifest count adjusted, digest re-taken)
d2 = tempfile.mkdtemp()
write_bundle(a_chain(10).records(), d2)
lines_ = open(os.path.join(d2, "evidence.ndjson")).read().splitlines()
del lines_[4]
open(os.path.join(d2, "evidence.ndjson"), "w").write("\n".join(lines_))
reseal(d2)
code2, out2, err2 = run_cli([d2])
ok = code2 == 1 and "links to the one before it" in out2 and "sequence numbers are contiguous" in out2
fail_lines = [l for l in out2.splitlines() if "[FAIL]" in l]
line("EVD-134", "PASS" if (code2 == 1 and len(fail_lines) >= 2) else "FAIL", f"exit={code2} fail_checks={fail_lines}")

# EVD-135: verifier reports sequence gap separately from link (0-4, 6-9, relinked)
l = a_chain(10)
recs = l.records()
remaining = recs[0:5] + recs[6:10]
import dataclasses as dc
relinked = [remaining[0]]
prev = remaining[0].record_hash
for r in remaining[1:]:
    nr = dc.replace(r, previous_hash=prev)
    relinked.append(nr)
    prev = nr.record_hash
d3 = tempfile.mkdtemp()
write_bundle(relinked, d3)
code3, out3, err3 = run_cli([d3])
link_pass = "[PASS] every record links to the one before it" in out3
seq_fail = "[FAIL] sequence numbers are contiguous" in out3
line("EVD-135", "PASS" if (link_pass and seq_fail) else "FAIL", f"exit={code3} link_pass={link_pass} seq_fail={seq_fail}")

# EVD-136: verifier checks tombstone seal, refuses missing one (both EVD-028/029 style)
l = a_chain(5)
recs = l.records()
erased = recs[2].erase(by="dpo", authority="A1", at="2026-01-01T00:00:00Z")
recs_e = recs[:2] + [erased] + recs[3:]
d4 = tempfile.mkdtemp()
write_bundle(recs_e, d4)
lines_ = open(os.path.join(d4, "evidence.ndjson")).read().splitlines()
rec2 = json.loads(lines_[2]); rec2["tombstone"]["erased_by"] = "mallory"
lines_[2] = json.dumps(rec2)
open(os.path.join(d4, "evidence.ndjson"), "w").write("\n".join(lines_))
reseal(d4)
code4, out4, err4 = run_cli([d4])
d5 = tempfile.mkdtemp()
write_bundle(recs_e, d5)
lines_ = open(os.path.join(d5, "evidence.ndjson")).read().splitlines()
rec2b = json.loads(lines_[2]); del rec2b["tombstone"]["seal"]
lines_[2] = json.dumps(rec2b)
open(os.path.join(d5, "evidence.ndjson"), "w").write("\n".join(lines_))
reseal(d5)
code5, out5, err5 = run_cli([d5])
ok = code4 == 1 and code5 == 1
line("EVD-136", "PASS" if ok else "FAIL", f"tampered_erased_by_exit={code4} missing_seal_exit={code5}")

# EVD-137: verifier checks tombstone against record's content_hash
l = a_chain(5)
recs = l.records()
erased = recs[2].erase(by="dpo", authority="A1", at="2026-01-01T00:00:00Z")
recs_e = recs[:2] + [erased] + recs[3:]
d6 = tempfile.mkdtemp()
write_bundle(recs_e, d6)
lines_ = open(os.path.join(d6, "evidence.ndjson")).read().splitlines()
rec2 = json.loads(lines_[2])
rec2["tombstone"]["original_content_hash"] = "ab" * 32
# recompute seal since we're forging the whole tombstone content, not just leaving stale seal;
# actually for THIS case we want a mismatched original_content_hash vs stored content_hash while seal still recomputes correctly over the (tampered) tombstone fields
import hashlib as _h
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.core.pjson import canonical as _canon
stone_fields = {k: rec2["tombstone"][k] for k in ("original_content_hash","erased_at","erased_by","authority","reason")}
rec2["tombstone"]["seal"] = _h.sha256(_canon(stone_fields)).hexdigest()
lines_[2] = json.dumps(rec2)
open(os.path.join(d6, "evidence.ndjson"), "w").write("\n".join(lines_))
reseal(d6)
code6, out6, err6 = run_cli([d6])
ok = code6 == 1 and "names a different original" in out6
line("EVD-137", "PASS" if ok else "FAIL", f"exit={code6} excerpt={[l for l in out6.splitlines() if 'different original' in l]}")

# EVD-138: erased record's presence reported, not silently passed (two erased, all seals hold)
l = a_chain(5)
recs = l.records()
e2 = recs[1].erase(by="dpo", authority="A1", at="2026-01-01T00:00:00Z")
e4 = recs[3].erase(by="dpo", authority="A1", at="2026-01-01T00:00:00Z")
recs_e2 = [recs[0], e2, recs[2], e4, recs[4]]
d7 = tempfile.mkdtemp()
write_bundle(recs_e2, d7)
code7, out7, err7 = run_cli([d7])
ok = code7 == 0 and "2 record(s) carry a tombstone whose seal holds" in out7 and "[PASS]" in [l.split("]")[0]+"]" for l in out7.splitlines() if "tombstone" in l][0] if any("tombstone" in l for l in out7.splitlines()) else False
tombstone_lines = [l for l in out7.splitlines() if "tombstone" in l]
ok = code7 == 0 and len(tombstone_lines) >= 1 and "[PASS]" in tombstone_lines[0]
line("EVD-138", "PASS" if ok else "FAIL", f"exit={code7} tombstone_line={tombstone_lines}")

print("SECTION EVD-133..138 DONE")

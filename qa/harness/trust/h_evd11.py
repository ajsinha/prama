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

def run_cli(args):
    r = subprocess.run([sys.executable, VERIFY_SCRIPT] + args, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr

# EVD-139: manifest count check catches truncation (last three lines removed, manifest untouched)
d = tempfile.mkdtemp()
write_bundle(a_chain(10).records(), d)
lines_ = open(os.path.join(d, "evidence.ndjson")).read().splitlines()
open(os.path.join(d, "evidence.ndjson"), "w").write("\n".join(lines_[:-3]))
code, out, err = run_cli([d])
ok = code == 1 and "manifest's record count" in out and "perfectly valid" in out
line("EVD-139", "PASS" if ok else "FAIL", f"exit={code} excerpt={[l for l in out.splitlines() if 'record count' in l or 'perfectly valid' in l]}")

# EVD-140: payload digest check catches whitespace addition
d2 = tempfile.mkdtemp()
write_bundle(a_chain(10).records(), d2)
payload = open(os.path.join(d2, "evidence.ndjson")).read()
open(os.path.join(d2, "evidence.ndjson"), "w").write(payload + " ")
code2, out2, err2 = run_cli([d2])
ok = code2 == 1 and "evidence file is the one the manifest describes" in out2
line("EVD-140", "PASS" if ok else "FAIL", f"exit={code2} fail_lines={[l for l in out2.splitlines() if '[FAIL]' in l]}")

# EVD-141: Merkle root check catches substituted record set (internally consistent, count+digest updated, manifest root/head untouched)
d3 = tempfile.mkdtemp()
orig_bundle = write_bundle(a_chain(10).records(), d3)
orig_manifest = json.load(open(os.path.join(d3, "manifest.json")))
new_chain = Ledger()
for i in range(10):
    new_chain.append(R(i, dataset="COMPLETELY_DIFFERENT_DATASET"))  # a genuinely different, internally-consistent chain of the same length
new_payload = "\n".join(r.to_json() for r in new_chain.records())
open(os.path.join(d3, "evidence.ndjson"), "w").write(new_payload)
m = dict(orig_manifest)
m["records"] = 10
m["payload_digest"] = hashlib.sha256(new_payload.encode("utf-8")).hexdigest()
# deliberately leave merkle_root and chain_head as the ORIGINAL manifest's values
json.dump(m, open(os.path.join(d3, "manifest.json"), "w"))
code3, out3, err3 = run_cli([d3])
merkle_fail = "[FAIL] the Merkle root matches the records" in out3
head_fail = "[FAIL] the chain head matches the last record" in out3
line("EVD-141", "PASS" if (code3 == 1 and merkle_fail and head_fail) else "FAIL", f"exit={code3} merkle_fail={merkle_fail} head_fail={head_fail}")

# EVD-142: empty bundle hand-made (0 records, matching digest, merkle_root=genesis, chain_head=genesis) -- stated outcome, not "every check passed"
d4 = tempfile.mkdtemp()
os.makedirs(d4, exist_ok=True)
open(os.path.join(d4, "evidence.ndjson"), "w").write("")
m4 = {
    "bundle_version": "1.0", "evidence_version": "1.1", "tenant_id": "t1",
    "from_sequence": 0, "to_sequence": 0, "records": 0, "erased": 0,
    "chain_head": GENESIS, "merkle_root": GENESIS,
    "payload_digest": hashlib.sha256(b"").hexdigest(), "written_at": "2026-01-01T00:00:00Z",
}
json.dump(m4, open(os.path.join(d4, "manifest.json"), "w"))
code4, out4, err4 = run_cli([d4])
every_check_passed = "Every check passed." in out4
line("EVD-142", "FAIL" if (code4 == 0 and every_check_passed) else "PASS",
     f"exit={code4} says_every_check_passed={every_check_passed} -- an empty bundle (0 records) verifies green with no distinguishing statement that there was nothing to check")

# EVD-143: success text states what green does not mean (four lines)
d5 = tempfile.mkdtemp()
write_bundle(a_chain(3).records(), d5)
code5, out5, err5 = run_cli([d5])
required_phrases = ["does not establish", "have not been altered", "does not say", "honestly written and correctly"]
# actual wording check: look for the substance
sentences_present = ("not say" in out5 and "true" in out5 and "honestly written and correctly" in out5 and "chained" in out5)
line("EVD-143", "PASS" if sentences_present else "FAIL", f"exit={code5} tail={out5[out5.find('Every check passed'):][:400]!r}")

# EVD-144: two implementations agree on adversarial corpus
def content_edit(recs):
    p = [r.to_dict() for r in recs]; p[2] = dict(p[2]); p[2]["verdict"] = "fail" if p[2]["verdict"]!="fail" else "pass"; return p
def truncated(recs):
    return [r.to_dict() for r in recs][:-2]
def reordered(recs):
    p = [r.to_dict() for r in recs]; p[3], p[4] = p[4], p[3]; return p
def gapped(recs):
    p = [r.to_dict() for r in recs]; del p[3]; return p
import dataclasses as dc
def rechained(recs):
    new = list(recs); new[2] = dc.replace(recs[2], dataset="X")
    prev = recs[1].record_hash
    out = list(new[:2])
    for r in new[2:]:
        nr = dc.replace(r, previous_hash=prev); out.append(nr); prev = nr.record_hash
    return [r.to_dict() for r in out]
def erased_sealed(recs):
    new = list(recs); new[2] = recs[2].erase(by="dpo", authority="A1", at="2026-01-01T00:00:00Z")
    return [r.to_dict() for r in new]
def erased_tampered(recs):
    p = erased_sealed(recs); p[2] = dict(p[2]); p[2]["tombstone"] = dict(p[2]["tombstone"]); p[2]["tombstone"]["erased_by"] = "mallory"; return p
def extra_key(recs):
    p = [r.to_dict() for r in recs]; p[2] = dict(p[2]); p[2]["note"] = "x"; return p
def non_ascii(recs):
    new = list(recs); new[2] = dc.replace(recs[2], dataset="münchen"); return [r.to_dict() for r in new]
def window(recs):
    return [r.to_dict() for r in recs[3:]]

corpus = {"intact": lambda r: [x.to_dict() for x in r], "content_edit": content_edit, "truncated": truncated,
          "reordered": reordered, "gapped": gapped, "rechained": rechained, "erased_sealed": erased_sealed,
          "erased_tampered": erased_tampered, "extra_key": extra_key, "non_ascii": non_ascii, "window": window}

disagreements = []
for name, fn in corpus.items():
    recs = a_chain(10).records()
    payloads = fn(recs)
    prama_intact = ledger_verify(payloads).is_intact
    dd = tempfile.mkdtemp()
    payload_text = "\n".join(json.dumps(p) for p in payloads)
    hashes = [p["record_hash"] for p in payloads]
    m = {
        "bundle_version": "1.0", "evidence_version": "1.1", "tenant_id": "t1",
        "from_sequence": payloads[0]["sequence"] if payloads else 0,
        "to_sequence": payloads[-1]["sequence"] if payloads else 0,
        "records": len(payloads), "erased": sum(1 for p in payloads if p.get("tombstone")),
        "chain_head": hashes[-1] if hashes else GENESIS, "merkle_root": ve.merkle_root(hashes),
        "payload_digest": hashlib.sha256(payload_text.encode("utf-8")).hexdigest(),
        "written_at": "2026-01-01T00:00:00Z",
    }
    open(os.path.join(dd, "manifest.json"), "w").write(json.dumps(m))
    open(os.path.join(dd, "evidence.ndjson"), "w").write(payload_text)
    code, out, err = run_cli([dd])
    indep_intact = code == 0
    if prama_intact != indep_intact:
        disagreements.append((name, prama_intact, indep_intact))
line("EVD-144", "FAIL" if disagreements else "PASS", f"disagreements(name,prama_intact,independent_ok)={disagreements} -- predicted by EVD-006(non_ascii, not in this corpus fn but same canonical bug applies to any record if dataset made non-ascii and prama also passes it through differently -- see EVD-006), EVD-014(extra_key), EVD-031(erased_tampered), EVD-049(window)")

# EVD-145: verifier's canonical (NOT_CONTENT) excludes exactly previous_hash/content_hash/record_hash
ok = ve.NOT_CONTENT == ("previous_hash", "content_hash", "record_hash")
line("EVD-145", "PASS" if ok else "FAIL", f"NOT_CONTENT={ve.NOT_CONTENT} (tombstone is popped separately in verify_chain, not via NOT_CONTENT -- confirmed correct by inspection)")

# EVD-146: verifier caps output at 5 per check
d6 = tempfile.mkdtemp()
recs = a_chain(20).records()
payloads = [r.to_dict() for r in recs]
for i in range(len(payloads)):
    payloads[i] = dict(payloads[i]); payloads[i]["verdict"] = "fail" if payloads[i]["verdict"] != "fail" else "pass"
payload_text = "\n".join(json.dumps(p) for p in payloads)
hashes = [p["record_hash"] for p in payloads]
m = {"bundle_version":"1.0","evidence_version":"1.1","tenant_id":"t1","from_sequence":0,"to_sequence":19,
     "records":20,"erased":0,"chain_head":hashes[-1],"merkle_root":ve.merkle_root(hashes),
     "payload_digest":hashlib.sha256(payload_text.encode()).hexdigest(),"written_at":"2026-01-01T00:00:00Z"}
open(os.path.join(d6,"manifest.json"),"w").write(json.dumps(m))
open(os.path.join(d6,"evidence.ndjson"),"w").write(payload_text)
code6, out6, err6 = run_cli([d6])
content_hash_lines = [l for l in out6.splitlines() if "content_hash is" in l]
ok = len(content_hash_lines) == 5
line("EVD-146", "PASS" if ok else "FAIL", f"lines_shown={len(content_hash_lines)} (expected 5, out of 20 failing records)")

# EVD-147: a record with no sequence key does not crash the verifier
d7 = tempfile.mkdtemp()
recs = a_chain(3).records()
payloads = [r.to_dict() for r in recs]
del payloads[0]["sequence"]
payload_text = "\n".join(json.dumps(p) for p in payloads)
hashes = [p["record_hash"] for p in payloads]
m = {"bundle_version":"1.0","evidence_version":"1.1","tenant_id":"t1","from_sequence":0,"to_sequence":2,
     "records":3,"erased":0,"chain_head":hashes[-1],"merkle_root":ve.merkle_root(hashes),
     "payload_digest":hashlib.sha256(payload_text.encode()).hexdigest(),"written_at":"2026-01-01T00:00:00Z"}
open(os.path.join(d7,"manifest.json"),"w").write(json.dumps(m))
open(os.path.join(d7,"evidence.ndjson"),"w").write(payload_text)
code7, out7, err7 = run_cli([d7])
ok = code7 in (0, 1) and "Traceback" not in out7 and "Traceback" not in err7
reported_failure = code7 == 1
line("EVD-147", "PASS" if (ok and reported_failure) else "FAIL", f"exit={code7} no_crash={ok} reported_as_failure={reported_failure} stderr={err7[:200]!r}")

# EVD-148: report distinguishes a check that failed from one that did not run (tombstone check absent when no erasures)
d8 = tempfile.mkdtemp()
write_bundle(a_chain(5).records(), d8)
code8, out8, err8 = run_cli([d8])
tombstone_mentioned = "tombstone" in out8.lower()
line("EVD-148", "PASS" if not tombstone_mentioned else "FAIL", f"tombstone_check_shown_when_no_erasures={tombstone_mentioned} (expected: absent, not shown as passing)")

print("SECTION EVD-139..148 DONE")

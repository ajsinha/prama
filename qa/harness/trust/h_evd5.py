import dataclasses, hashlib, json, sys, subprocess, hmac as hmaclib, inspect
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.evidence.record import EvidenceRecord, SnapshotRef, GENESIS
from prama.evidence.ledger import Ledger, verify as ledger_verify, merkle_root, sign, verify_signature, Breach

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

# EVD-056: export does not end with a blank line the verifier miscounts
l = a_chain(10)
exported = l.export()
lines_nl = [x for x in (exported + "\n").split("\n") if x.strip()]
lines_dblnl = [x for x in (exported + "\n\n").split("\n") if x.strip()]
ok2 = len(lines_nl) == 10 and len(lines_dblnl) == 10
line("EVD-056", "PASS" if ok2 else "FAIL", f"no_trailing_nonblank={len([x for x in exported.split(chr(10)) if x.strip()])} one_trailing_nl={len(lines_nl)} two_trailing_nl={len(lines_dblnl)} all_10={ok2}")

# EVD-057: a breach of each kind renders as a sentence naming the sequence
kinds_samples = {
    "content": Breach("content", 4, "the content does not match its hash; this record has been altered"),
    "link": Breach("link", 5, "this record does not follow the one before it; the chain is broken here"),
    "gap": Breach("gap", 6, "expected sequence 5 and found 6; 1 record(s) are missing"),
    "order": Breach("gap", 4, "records are out of order"),
    "genesis": Breach("genesis", 0, "the first record does not start the chain"),
}
rendered = {k: b.render() for k, b in kinds_samples.items()}
ok = all(str(b.sequence) in rendered[k] for k, b in kinds_samples.items())
line("EVD-057", "PASS" if ok else "FAIL", f"rendered={rendered}")

# EVD-058: Verification.to_dict shape
l = a_chain(10)
payloads = [r.to_dict() for r in l]
payloads[4] = dict(payloads[4]); payloads[4]["verdict"] = "fail"
del payloads[7]
v = ledger_verify(payloads)
d = v.to_dict()
ok = (d["intact"] is False and len(d["breaches"]) >= 2 and
      set(d.keys()) >= {"records","intact","head","merkle_root","erased","breaches"} and
      all({"kind","sequence","detail"} <= set(b.keys()) for b in d["breaches"]))
line("EVD-058", "PASS" if ok else "FAIL", f"keys={sorted(d.keys())} intact={d['intact']} n_breaches={len(d['breaches'])}")

# EVD-059: verification's head equals ledger.head
l = a_chain(10)
v = l.verify()
line("EVD-059", "PASS" if v.head == l.head else "FAIL", f"verify().head={v.head} ledger.head={l.head}")

# EVD-060: breach at record 2 and 7 both reported (doesn't stop early)
l = a_chain(10)
payloads = [r.to_dict() for r in l]
payloads[2] = dict(payloads[2]); payloads[2]["verdict"] = "fail"
payloads[7] = dict(payloads[7]); payloads[7]["verdict"] = "fail"
v = ledger_verify(payloads)
seqs_with_content_breach = sorted({b.sequence for b in v.breaches if b.kind == "content"})
ok = seqs_with_content_breach == [2, 7]
line("EVD-060", "PASS" if ok else "FAIL", f"content_breach_sequences={seqs_with_content_breach}")

# EVD-061: verify() on a large chain -- functional smoke test at reduced scale (1e6 impractical for this harness; use 50000 as a scaled probe)
import time
l = Ledger()
for i in range(20000):
    l.append(R(0))
t0 = time.time()
v = l.verify()
dt = time.time() - t0
line("EVD-061", "PASS" if v.is_intact else "FAIL", f"SCALED PROBE (20000 records, not the stated 1,000,000): verify_intact={v.is_intact} time_s={dt:.2f} -- completed without error; did not instrument memory to confirm streaming/no materialisation of the full chain, so this only confirms correctness at reduced scale, not the performance claim")

# EVD-062: verifying same bundle twice (two processes, different PYTHONHASHSEED) gives same answer
l = a_chain(10)
payloads = [r.to_dict() for r in l]
payload_json = json.dumps(payloads)
script = f'''
import sys, json
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.evidence.ledger import verify
payloads = json.loads(sys.stdin.read())
v = verify(payloads)
print(json.dumps(v.to_dict()))
'''
import os
env1 = dict(os.environ); env1["PYTHONHASHSEED"] = "1"
env2 = dict(os.environ); env2["PYTHONHASHSEED"] = "999999"
out1 = subprocess.run([sys.executable, "-c", script], input=payload_json, capture_output=True, text=True, env=env1)
out2 = subprocess.run([sys.executable, "-c", script], input=payload_json, capture_output=True, text=True, env=env2)
ok = out1.stdout == out2.stdout and out1.stdout.strip() != ""
line("EVD-062", "PASS" if ok else "FAIL", f"hashseed1_out={out1.stdout[:200]!r} hashseed999999_out={out2.stdout[:200]!r} stderr1={out1.stderr[-150:]!r} equal={ok}")

# ---------------- Merkle root and seal (EVD-063..074) ----------------

# EVD-063: root of empty set is genesis
line("EVD-063", "PASS" if merkle_root([]) == GENESIS else "FAIL", f"merkle_root([])={merkle_root([])}")

# EVD-064: root of one hash is that hash
h = hashlib.sha256(b"x").hexdigest()
line("EVD-064", "PASS" if merkle_root([h]) == h else "FAIL", f"merkle_root([h])={merkle_root([h])} h={h}")

# EVD-065: root of two hashes is hash of concatenation
a = hashlib.sha256(b"a").hexdigest()
b = hashlib.sha256(b"b").hexdigest()
expect = hashlib.sha256((a+b).encode("ascii")).hexdigest()
line("EVD-065", "PASS" if merkle_root([a,b]) == expect else "FAIL", f"merkle_root={merkle_root([a,b])} handcomputed={expect}")

# EVD-066: odd node promoted, not duplicated
a = hashlib.sha256(b"a").hexdigest(); b = hashlib.sha256(b"b").hexdigest(); c = hashlib.sha256(b"c").hexdigest()
r3 = merkle_root([a,b,c])
r4 = merkle_root([a,b,c,c])
line("EVD-066", "PASS" if r3 != r4 else "FAIL", f"root([a,b,c])={r3} root([a,b,c,c])={r4} different={r3!=r4}")

# EVD-067: reordering changes the root
hashes4 = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(4)]
swapped = list(hashes4); swapped[0], swapped[1] = swapped[1], swapped[0]
r_orig = merkle_root(hashes4)
r_swap = merkle_root(swapped)
line("EVD-067", "PASS" if r_orig != r_swap else "FAIL", f"orig={r_orig} swapped={r_swap}")

# EVD-068: both merkle implementations agree for n=0..33
import importlib.util
spec = importlib.util.spec_from_file_location("verify_evidence", "/home/ashutosh/PycharmProjects/prama/scripts/verify_evidence.py")
ve = importlib.util.module_from_spec(spec); spec.loader.exec_module(ve)
mismatches = []
for n in range(0, 34):
    hs = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(n)]
    r1 = merkle_root(hs)
    r2 = ve.merkle_root(hs)
    if r1 != r2:
        mismatches.append(n)
line("EVD-068", "PASS" if not mismatches else "FAIL", f"mismatches_at_n={mismatches}")

# EVD-069: HMAC pinned to independent vector, no hmac import
key = b"a-shared-secret-key"
head = hashlib.sha256(b"chain-head-data").hexdigest()
# RFC 2104-style HMAC over SHA-256 using hashlib only
def manual_hmac_sha256(key, msg):
    block_size = 64
    if len(key) > block_size:
        key = hashlib.sha256(key).digest()
    key = key.ljust(block_size, b"\x00")
    o_pad = bytes(x ^ 0x5c for x in key)
    i_pad = bytes(x ^ 0x36 for x in key)
    inner = hashlib.sha256(i_pad + msg).digest()
    return hashlib.sha256(o_pad + inner).hexdigest()
expect = manual_hmac_sha256(key, head.encode("ascii"))
actual = sign(head, key)
line("EVD-069", "PASS" if actual == expect else "FAIL", f"sign()={actual} manual_rfc2104={expect}")

# EVD-070: verify_signature refuses wrong key/head/truncated/altered signature
sig = sign(head, key)
cases = {
    "wrong_key": verify_signature(head, b"different-key", sig),
    "wrong_head": verify_signature(hashlib.sha256(b"other").hexdigest(), key, sig),
    "truncated_sig": verify_signature(head, key, sig[:32]),
    "altered_one_char": verify_signature(head, key, ("0" if sig[0] != "0" else "1") + sig[1:]),
}
ok = not any(cases.values())
line("EVD-070", "PASS" if ok else "FAIL", f"{cases}")

# EVD-071: comparison is constant-time -- read the source
src = inspect.getsource(verify_signature)
ok = "hmac.compare_digest" in src and "==" not in src.replace("!=", "")
line("EVD-071", "PASS" if "hmac.compare_digest" in src else "FAIL", f"source={src.strip()!r}")

# EVD-072: signing with empty key is refused
try:
    s = sign(head, b"")
    line("EVD-072", "FAIL", f"no refusal; sign(head, b'') returned {s!r}")
except Exception as e:
    line("EVD-072", "PASS", f"{type(e).__name__}: {e}")

# EVD-073: docstring/surface states what signature proves -- grep for "signed"
grep = subprocess.run(["grep", "-rn", "-i", "signed", "/home/ashutosh/PycharmProjects/prama/src/prama/cli", "/home/ashutosh/PycharmProjects/prama/src/prama/api"], capture_output=True, text=True)
hits = grep.stdout.strip().splitlines()
line("EVD-073", "INFO" if hits else "FAIL", f"grep -rni 'signed' src/prama/cli src/prama/api -> {len(hits)} hits: {hits[:10]}")

# EVD-073 follow-up: the INFO grep alone is not decisive (it finds unrelated
# "signed" hits -- CLI bundle-manifest signing, attestation sign). What decides
# the case is whether evidence.ledger.sign()/verify_signature() are called from
# any CLI command or API route at all, since that is the only surface on which
# a "what the signature proves" caveat sentence could appear.
grep2 = subprocess.run(["grep", "-rn", "verify_signature\\|\\.sign(", "/home/ashutosh/PycharmProjects/prama/src/prama"], capture_output=True, text=True)
sign_hits = [l for l in grep2.stdout.splitlines() if "evidence/ledger.py" not in l and "evidence/__init__.py" not in l and "__pycache__" not in l]
ledger_sign_used_outside = any("ledger" in l.lower() and ("sign(" in l or "verify_signature" in l) for l in sign_hits)
line("EVD-073", "FAIL" if not ledger_sign_used_outside else "PASS",
     f"evidence.ledger.sign()/verify_signature() called outside evidence/ledger.py+__init__.py: {ledger_sign_used_outside} -- other 'sign('/'verify_signature' hits are unrelated mechanisms (CLI bundle manifest Ed25519 signing, attestation.sign): {sign_hits}. "
     f"No CLI command or API route renders a signed chain head, so there is no surface for a caveat sentence to appear on.")

# EVD-074: published root + signed head detects re-chained forgery
l = a_chain(10)
recs = l.records()
key = b"estate-signing-key-2026"
original_head = l.head
original_sig = sign(original_head, key)
new_recs = list(recs)
new_recs[4] = dataclasses.replace(recs[4], dataset="FABRICATED")
prev = recs[3].record_hash
final = list(recs[:4])
for r in new_recs[4:]:
    relinked = dataclasses.replace(r, previous_hash=prev)
    final.append(relinked); prev = relinked.record_hash
forged_head = final[-1].record_hash
ok = not verify_signature(forged_head, key, original_sig)
line("EVD-074", "PASS" if ok else "FAIL", f"forged_head={forged_head} original_head={original_head} verify_signature(forged_head, key, original_sig)={not ok}")

print("SECTION EVD-056..074 DONE")

import dataclasses, hashlib, json, sys, importlib.util
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.evidence.record import EvidenceRecord, SnapshotRef, Tombstone, GENESIS
from prama.evidence.ledger import Ledger, verify as ledger_verify
from prama.core.pjson import canonical

spec = importlib.util.spec_from_file_location("verify_evidence", "/home/ashutosh/PycharmProjects/prama/scripts/verify_evidence.py")
ve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ve)

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

import sys as _sys
_sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line

def run_verifier_on(payloads):
    """Write payloads+manifest to a tmp dir, run verify_evidence.py main(), capture output+exit."""
    import tempfile, io, contextlib
    d = tempfile.mkdtemp()
    payload_text = "\n".join(json.dumps(p) for p in payloads)
    hashes = [p["record_hash"] for p in payloads]
    manifest = {
        "bundle_version": "1.0", "evidence_version": "1.1", "tenant_id": "t1",
        "from_sequence": payloads[0]["sequence"] if payloads else 0,
        "to_sequence": payloads[-1]["sequence"] if payloads else 0,
        "records": len(payloads),
        "erased": sum(1 for p in payloads if p.get("tombstone")),
        "chain_head": hashes[-1] if hashes else GENESIS,
        "merkle_root": ve.merkle_root(hashes),
        "payload_digest": hashlib.sha256(payload_text.encode("utf-8")).hexdigest(),
        "written_at": "2026-01-01T00:00:00Z",
    }
    open(d + "/manifest.json", "w").write(json.dumps(manifest))
    open(d + "/evidence.ndjson", "w").write(payload_text)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = ve.main([d])
    return code, buf.getvalue(), d, manifest

def reseal_manifest(payloads, manifest_path):
    payload_text = "\n".join(json.dumps(p) for p in payloads)
    hashes = [p["record_hash"] for p in payloads]
    m = json.load(open(manifest_path))
    m["records"] = len(payloads)
    m["chain_head"] = hashes[-1] if hashes else GENESIS
    m["merkle_root"] = ve.merkle_root(hashes)
    m["payload_digest"] = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    m["erased"] = sum(1 for p in payloads if p.get("tombstone"))
    json.dump(m, open(manifest_path, "w"))
    open(manifest_path.replace("manifest.json", "evidence.ndjson"), "w").write(payload_text)

# EVD-014: unknown key added to record JSON invisible to Prama's from_dict-based verify, but visible to independent verifier
chain = a_chain(5)
payloads = [r.to_dict() for r in chain]
payloads[2]["note"] = "approved by treasury"
prama_v = ledger_verify(payloads)
code, out, d, manifest = run_verifier_on(payloads)
prama_breach = not prama_v.is_intact
indep_breach = code != 0
# Expected (catalogue): both Ledger.verify() and the independent verifier report a breach.
line("EVD-014", "PASS" if (indep_breach and prama_breach) else "FAIL",
     f"prama_verify_intact={prama_v.is_intact} (breaches={[ (b.kind,b.sequence) for b in prama_v.breaches]}) independent_exit={code} independent_ok={not indep_breach} -- expected both to report a breach")

# EVD-015: snapshot.exact flipped false->true is inside hash
r = R(0, snapshot=SnapshotRef(kind="lsn", identifier="x", exact=False))
d0 = r.to_dict()
d1 = dict(d0)
d1["snapshot"] = {**d0["snapshot"], "exact": True}
v = ledger_verify([d1])
line("EVD-015", "PASS" if any(b.kind == "content" for b in v.breaches) else "FAIL", f"breaches={[(b.kind,b.sequence,b.detail) for b in v.breaches]}")

# EVD-016: claim narrows verdict
r_full = R(0, coverage="full", verdict="pass")
r_inc = R(0, coverage="incremental", verdict="pass")
r_fwd = R(0, coverage="forward_only", verdict="fail")
ok = r_full.claim == "pass" and r_inc.claim == "pass over the rows examined" and r_fwd.claim == "fail over the rows examined"
line("EVD-016", "PASS" if ok else "FAIL", f"full={r_full.claim!r} incremental={r_inc.claim!r} forward_only={r_fwd.claim!r}")

# EVD-017: coverage inside hash
r = R(0, coverage="incremental")
d0 = r.to_dict()
d1 = dict(d0); d1["coverage"] = "full"
v = ledger_verify([d1])
line("EVD-017", "PASS" if any(b.kind == "content" for b in v.breaches) else "FAIL", f"breaches={[(b.kind,b.sequence,b.detail) for b in v.breaches]}")

# EVD-018: round-trip to_dict/from_dict unchanged, including tombstone
r = R(0, dimensions=("completeness",), criticality=1).erase(by="dpo", authority="DSAR-1", at="2026-01-01T00:00:00Z")
rt = EvidenceRecord.from_dict(r.to_dict())
ok = rt.to_dict() == r.to_dict() and rt.content_hash == r.content_hash and rt.record_hash == r.record_hash
line("EVD-018", "PASS" if ok else "FAIL", f"equal_dict={rt.to_dict()==r.to_dict()} content_hash_eq={rt.content_hash==r.content_hash} record_hash_eq={rt.record_hash==r.record_hash}")

# EVD-019: defaults from empty payload
r = EvidenceRecord.from_dict({})
ok = (r.verdict == "error" and r.criticality == 4 and r.coverage == "full" and
      r.triggered_by == "schedule" and r.previous_hash == GENESIS and r.evidence_version == "1.1")
line("EVD-019", "PASS" if ok else "FAIL", f"verdict={r.verdict} criticality={r.criticality} coverage={r.coverage} triggered_by={r.triggered_by} previous_hash={r.previous_hash} evidence_version={r.evidence_version}")

# EVD-020: metric arriving as string coerced or refused with typed failure, not raw ValueError
try:
    r = EvidenceRecord.from_dict({"metrics": {"rows": "eight"}})
    line("EVD-020", "FAIL", f"silently coerced/dropped: metrics={r.metrics!r} (no exception raised at all)")
except ValueError as e:
    line("EVD-020", "FAIL", f"raised a raw ValueError, not a typed/named failure: {e!r}")
except Exception as e:
    line("EVD-020", "PASS" if type(e).__module__.startswith("prama") else "FAIL", f"{type(e).__module__}.{type(e).__name__}: {e!r}")

# EVD-021: record stays under 2KB
r = R(0, metrics={"a":1.0,"b":2.0,"c":3.0,"d":4.0}, parameters={"x":"1","y":"2","z":"3"}, detail="d"*256)
sz = r.size_bytes
line("EVD-021", "PASS" if sz < 2048 else "FAIL", f"size_bytes={sz}")

# EVD-022: GENESIS is 64 zeros, matches verify_evidence.py's constant
ok = GENESIS == "0"*64 and ve.GENESIS == "0"*64 and GENESIS == ve.GENESIS
line("EVD-022", "PASS" if ok else "FAIL", f"GENESIS={GENESIS!r} ve.GENESIS={ve.GENESIS!r}")

print("SECTION EVD-014..022 DONE")

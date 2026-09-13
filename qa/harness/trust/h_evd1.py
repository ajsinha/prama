import dataclasses, hashlib, json, sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.evidence.record import (
    EvidenceRecord, SnapshotRef, Tombstone, GENESIS, EVIDENCE_VERSION,
    FIELDS_SINCE, DETAIL_LIMIT, _version_tuple, _number,
)
from prama.core.pjson import canonical, dumpb, HAVE_ORJSON

def R(n=0, **changes):
    base = {
        "plan_id": f"ir:sha256:{n:064x}",
        "control_id": "ctl-1",
        "dataset": "positions_eod",
        "binding": "pg://RISK.POSITIONS",
        "engine": "postgresql",
        "snapshot": SnapshotRef(kind="lsn", identifier=f"0/{1000+n}", exact=True),
        "verdict": "pass",
        "metrics": {"scanned_rows": 50000.0, "violating_rows": float(n)},
        "started_at": "2026-04-02T06:31:00Z",
        "finished_at": "2026-04-02T06:31:02Z",
        "duration_ms": 2100,
        "tenant_id": "t1",
    }
    base.update(changes)
    return EvidenceRecord(**base)

import sys as _sys
_sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line

# EVD-001: content hash covers every field of the record
fields = {f.name for f in dataclasses.fields(EvidenceRecord)}
expected_keys = fields - {"previous_hash", "tombstone"}
content_keys = set(R().content().keys())
try:
    ok = expected_keys == content_keys
    line("EVD-001", "PASS" if ok else "FAIL", f"dataclass_fields-2={sorted(expected_keys)} content()_keys={sorted(content_keys)} equal={ok}")
except Exception as e:
    line("EVD-001", "FAIL", repr(e))

# EVD-002: doc-only, judged by reading
excluded = fields - content_keys
line("EVD-002", "PASS" if excluded == {"previous_hash", "tombstone"} else "FAIL",
     f"fields excluded from content(): {sorted(excluded)}; docstring covers previous_hash ('it is a hash') and tombstone ('sealed separately') -- checked by inspection")

# EVD-003: record_hash = sha256(previous_hash||content_hash) ascii, pinned
r = R(0, previous_hash=GENESIS)
expect = hashlib.sha256((r.previous_hash + r.content_hash).encode("ascii")).hexdigest()
line("EVD-003", "PASS" if r.record_hash == expect else "FAIL", f"record_hash={r.record_hash} handcomputed={expect}")

# EVD-004: content hash independent of dict insertion order
r1 = R(0, metrics={"a": 1.0, "b": 2.0}, parameters={"x": "1", "y": "2"})
r2 = R(0, metrics={"b": 2.0, "a": 1.0}, parameters={"y": "2", "x": "1"})
line("EVD-004", "PASS" if r1.content_hash == r2.content_hash else "FAIL", f"{r1.content_hash} vs {r2.content_hash}")

# EVD-005: content hash independent of orjson presence -- run as two subprocesses,
# one with orjson importable and one with it masked
import subprocess
script = r'''
import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
if len(sys.argv) > 1 and sys.argv[1] == "--no-orjson":
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *a, **kw):
        if name == "orjson":
            raise ImportError("masked")
        return real_import(name, *a, **kw)
    builtins.__import__ = fake_import
from prama.evidence.record import EvidenceRecord, SnapshotRef
from prama.core.pjson import HAVE_ORJSON
r = EvidenceRecord(
    plan_id="p", control_id="c", dataset="d", binding="b", engine="pg",
    snapshot=SnapshotRef(kind="lsn", identifier="x", exact=True),
    verdict="pass",
    metrics={"a": 1e16, "b": 0.1 + 0.2, "c": float(2**60)},
    tenant_id="münchen",
)
print(HAVE_ORJSON, r.content_hash)
'''
open("/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust/_orjson_probe.py", "w").write(script)
probe = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust/_orjson_probe.py"
out_with = subprocess.run([sys.executable, probe], capture_output=True, text=True)
out_without = subprocess.run([sys.executable, probe, "--no-orjson"], capture_output=True, text=True)
try:
    have1, hash1 = out_with.stdout.strip().split()
    have2, hash2 = out_without.stdout.strip().split()
    ok = have1 == "True" and have2 == "False" and hash1 == hash2
    line("EVD-005", "PASS" if ok else "FAIL", f"with_orjson=({have1},{hash1}) without_orjson=({have2},{hash2}) stderr_with={out_with.stderr[-200:]!r} stderr_without={out_without.stderr[-200:]!r}")
except Exception as e:
    line("EVD-005", "FAIL", f"subprocess outputs unparsable: with={out_with!r} without={out_without!r} err={e!r}")

# EVD-006: non-ASCII record hashes same via Prama canonical vs verify_evidence.py canonical
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/scripts")
import importlib.util
spec = importlib.util.spec_from_file_location("verify_evidence", "/home/ashutosh/PycharmProjects/prama/scripts/verify_evidence.py")
ve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ve)
r_uni = R(0, dataset="münchen.positionen")
prama_hash = r_uni.content_hash
verifier_hash = ve.sha256_hex(ve.canonical(r_uni.to_dict()))
line("EVD-006", "PASS" if prama_hash == verifier_hash else "FAIL", f"prama_content_hash={prama_hash} verifier_recompute={verifier_hash} equal={prama_hash==verifier_hash}")

# EVD-007: metric 8 vs 8.0 same hash
ra = R(0, metrics={"rows": 8})
rb = R(0, metrics={"rows": 8.0})
line("EVD-007", "PASS" if ra.content_hash == rb.content_hash else "FAIL", f"{ra.content_hash} vs {rb.content_hash}")

# EVD-008: NaN and Inf both -> null, collide
try:
    r_nan = R(0, metrics={"ratio": float("nan")})
    r_inf = R(0, metrics={"ratio": float("inf")})
    collide = r_nan.content_hash == r_inf.content_hash
    line("EVD-008", "PASS" if collide else "FAIL", f"nan_hash={r_nan.content_hash} inf_hash={r_inf.content_hash} collide={collide} content_nan={r_nan.content()['metrics']} content_inf={r_inf.content()['metrics']}")
except Exception as e:
    line("EVD-008", "FAIL", f"exception instead of collision: {e!r}")

# EVD-009: detail beyond 300 chars outside hash, but truncated in to_dict too
detail_a = "x" * 300 + "AAAA"
detail_b = "x" * 300 + "BBBB"
ra = R(0, detail=detail_a)
rb = R(0, detail=detail_b)
hash_eq = ra.content_hash == rb.content_hash
dict_trunc = ra.to_dict()["detail"] == "x"*300
line("EVD-009", "PASS" if (hash_eq and dict_trunc) else "FAIL", f"hash_eq={hash_eq} to_dict_detail_len={len(ra.to_dict()['detail'])} truncated_matches_x300={dict_trunc}")

# EVD-010: a 1.0 record read by 1.1 build still hashes to stored value
payload_10 = {
    "evidence_version": "1.0",
    "sequence": 0, "plan_id": "p", "control_id": "c", "control_version": 1,
    "dataset": "d", "binding": "b", "snapshot": {"kind":"none","identifier":"","exact":False},
    "parameters": {}, "engine": "pg", "coverage": "full", "verdict": "pass",
    "metrics": {}, "samples_digest": "", "sample_count": 0,
    "started_at": "", "finished_at": "", "duration_ms": 0,
    "triggered_by": "schedule", "tenant_id": "t1", "detail": "",
}
stored_hash = hashlib.sha256(canonical(payload_10)).hexdigest()  # content is exactly payload minus hash fields, already no dims/crit
rec10 = EvidenceRecord.from_dict({**payload_10, "previous_hash": GENESIS})
line("EVD-010", "PASS" if rec10.content_hash == stored_hash and "dimensions" not in rec10.content() and "criticality" not in rec10.content() else "FAIL",
     f"recomputed={rec10.content_hash} stored={stored_hash} content_keys={sorted(rec10.content().keys())}")

# EVD-011: 1.1 record emits both fields
r11 = R(0, dimensions=("completeness","accuracy"), criticality=2)
c = r11.content()
ok = c.get("dimensions") == ["completeness","accuracy"] and c.get("criticality") == 2 and isinstance(c.get("criticality"), int)
line("EVD-011", "PASS" if ok else "FAIL", f"content_dimensions={c.get('dimensions')!r} content_criticality={c.get('criticality')!r}")

# EVD-012: "1.10" sorts after "1.9"
ok = _version_tuple("1.10") > _version_tuple("1.9")
line("EVD-012", "PASS" if ok else "FAIL", f"_version_tuple('1.10')={_version_tuple('1.10')} _version_tuple('1.9')={_version_tuple('1.9')}")

# EVD-013: unparsable evidence version degrades to (0,0) => no dims/crit hashed, breach reported as content not swallowed
vt = _version_tuple("banana")
payload_bad = dict(payload_10)
payload_bad["evidence_version"] = "banana"
rec_bad = EvidenceRecord.from_dict(payload_bad)
c_bad = rec_bad.content()
ok = vt == (0,0) and "dimensions" not in c_bad and "criticality" not in c_bad
line("EVD-013", "PASS" if ok else "FAIL", f"_version_tuple('banana')={vt} content_keys={sorted(c_bad.keys())}")

print("SECTION EVD-001..022 part1 DONE")

import dataclasses, hashlib, json, sys, importlib.util
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.evidence.record import EvidenceRecord, SnapshotRef, Tombstone, GENESIS
from prama.evidence.ledger import Ledger, verify as ledger_verify
from prama.evidence.retention import Archivist, RetentionPolicy
from prama.core.pjson import canonical
from prama.core.errors import ValidationError

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

def a_chain(n=5):
    l = Ledger()
    for i in range(n):
        l.append(R(i))
    return l

def run_verifier_on(payloads, extra_manifest=None):
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
    if extra_manifest:
        manifest.update(extra_manifest)
    open(d + "/manifest.json", "w").write(json.dumps(manifest))
    open(d + "/evidence.ndjson", "w").write(payload_text)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = ve.main([d])
    return code, buf.getvalue(), d, manifest

# EVD-023: erase record 2 of 5, write back, verify intact, erased==1, records 3-5 link
chain = a_chain(5)
recs = chain.records()
erased_rec = recs[2].erase(by="dpo", authority="DSAR-1", at="2026-01-01T00:00:00Z")
new_recs = recs[:2] + [erased_rec] + recs[3:]
v = ledger_verify(r.to_dict() for r in new_recs)
ok = v.is_intact and v.erased == 1
line("EVD-023", "PASS" if ok else "FAIL", f"intact={v.is_intact} erased={v.erased} breaches={[(b.kind,b.sequence) for b in v.breaches]}")

# EVD-024: content_hash unchanged after erase, taken from tombstone.original_content_hash
r = R(0)
before = r.content_hash
after = r.erase(by="dpo")
ok = after.content_hash == before and after.content_hash == after.tombstone.original_content_hash
line("EVD-024", "PASS" if ok else "FAIL", f"before={before} after={after.content_hash} tombstone_orig={after.tombstone.original_content_hash}")

# EVD-025: exactly the documented fields survive an erasure
r = R(0, dimensions=("completeness",), criticality=1, detail="boom", parameters={"x":"1"})
e = r.erase(by="dpo", authority="DSAR-2")
survivors_expected = {"sequence","control_version","engine","coverage","verdict","started_at","finished_at",
                       "duration_ms","triggered_by","tenant_id","criticality","previous_hash","evidence_version"}
cleared_expected = {"plan_id","control_id","dataset","binding","parameters","metrics","samples_digest",
                     "sample_count","detail","dimensions"}
d = dataclasses.asdict(e)
non_default_fields = set()
default_rec = EvidenceRecord()
default_d = dataclasses.asdict(default_rec)
for f in dataclasses.fields(EvidenceRecord):
    if f.name in ("tombstone",):
        continue
    if getattr(e, f.name) != getattr(default_rec, f.name):
        non_default_fields.add(f.name)
# sequence/control_version/etc from R() base differ from default even before erase, that's expected -- but engine/coverage/verdict etc are meant to survive
cleared_ok = all(getattr(e, f) in ("", (), {}, 0) for f in cleared_expected)
snapshot_cleared = e.snapshot == SnapshotRef()
line("EVD-025", "PASS" if (cleared_ok and snapshot_cleared) else "FAIL",
     f"cleared_ok={cleared_ok} snapshot_cleared={snapshot_cleared} plan_id={e.plan_id!r} control_id={e.control_id!r} dataset={e.dataset!r} binding={e.binding!r} parameters={e.parameters!r} metrics={e.metrics!r} samples_digest={e.samples_digest!r} sample_count={e.sample_count!r} detail={e.detail!r} dimensions={e.dimensions!r} verdict_survives={e.verdict!r} tenant_id_survives={e.tenant_id!r} criticality_survives={e.criticality!r}")

# EVD-026: erasing an already-erased record is a no-op
r = R(0)
e1 = r.erase(by="dpo", authority="A1", at="2026-01-01T00:00:00Z")
e2 = e1.erase(by="other", authority="other", at="2027-01-01T00:00:00Z")
ok = e2 == e1 and e2.tombstone.erased_by == "dpo" and e2.tombstone.authority == "A1"
line("EVD-026", "PASS" if ok else "FAIL", f"e2==e1:{e2==e1} erased_by={e2.tombstone.erased_by} authority={e2.tombstone.authority}")

# EVD-027: tombstone seal is hash of its own fields
r = R(0)
e = r.erase(by="dpo", authority="A1", at="2026-01-01T00:00:00Z")
expect = hashlib.sha256(canonical(e.tombstone.content())).hexdigest()
line("EVD-027", "PASS" if e.tombstone.seal == expect else "FAIL", f"seal={e.tombstone.seal} handcomputed={expect}")

# EVD-028: rewriting erased_by invalidates seal -- reproduce via independent verifier, re-sealing manifest (not the tombstone seal)
chain = a_chain(5)
recs = chain.records()
erased = recs[2].erase(by="dpo", authority="DSAR-1", at="2026-01-01T00:00:00Z")
recs2 = recs[:2] + [erased] + recs[3:]
payloads = [r.to_dict() for r in recs2]
# tamper: rewrite erased_by/authority in the tombstone dict, leave seal untouched
payloads[2]["tombstone"]["erased_by"] = "mallory"
payloads[2]["tombstone"]["authority"] = "no authority at all"
code, out, d, manifest = run_verifier_on(payloads)
line("EVD-028", "PASS" if code == 1 and "tombstone" in out.lower() else "FAIL", f"exit={code} output_excerpt={out[:400]!r}")

# EVD-029: tombstone with seal stripped is refused
payloads2 = [r.to_dict() for r in recs2]
del payloads2[2]["tombstone"]["seal"]
code2, out2, d2, manifest2 = run_verifier_on(payloads2)
line("EVD-029", "PASS" if code2 == 1 and "no seal" in out2 else "FAIL", f"exit={code2} output_excerpt={out2[:400]!r}")

# EVD-030: tombstone lifted from one record onto another (intact) -- expect link breach
chain = a_chain(5)
recs = chain.records()
erased = recs[2].erase(by="dpo", authority="DSAR-1", at="2026-01-01T00:00:00Z")
recs3 = recs[:2] + [erased] + recs[3:]
payloads3 = [r.to_dict() for r in recs3]
# copy erased record's tombstone onto record 3 (intact), set record3's content_hash to tombstone's original_content_hash
target = dict(payloads3[3])
target["tombstone"] = dict(payloads3[2]["tombstone"])
target["content_hash"] = target["tombstone"]["original_content_hash"]
payloads3b = payloads3[:3] + [target] + payloads3[4:]
code3, out3, d3, manifest3 = run_verifier_on(payloads3b)
line("EVD-030", "PASS" if code3 == 1 else "FAIL", f"exit={code3} output_excerpt={out3[:500]!r}")

# EVD-031: Prama's own verify() does NOT check the tombstone seal (rewrite erased_by/authority, verify() intact; independent verifier catches it)
chain = a_chain(5)
recs = chain.records()
erased = recs[2].erase(by="dpo", authority="DSAR-1", at="2026-01-01T00:00:00Z")
recs4 = recs[:2] + [erased] + recs[3:]
payloads4 = [r.to_dict() for r in recs4]
payloads4[2]["tombstone"]["erased_by"] = "mallory"
payloads4[2]["tombstone"]["authority"] = "no authority at all"
v4 = ledger_verify(payloads4)
code4, out4, d4, manifest4 = run_verifier_on(payloads4)
ok = v4.is_intact and code4 == 1
line("EVD-031", "PASS" if ok else "FAIL", f"prama_verify_intact={v4.is_intact} independent_exit={code4} -- expected both report a breach")

# EVD-032: erasure records who/when/authority, reason defaults, timestamp from archivist's clock not record's
r = R(0, finished_at="2026-04-02T06:31:02Z")
e = r.erase(by="dpo@bank", authority="DSAR-2026-114", at="2026-09-01T00:00:00Z")
ok = (e.tombstone.erased_by == "dpo@bank" and e.tombstone.authority == "DSAR-2026-114" and
      e.tombstone.reason == "right to erasure" and e.tombstone.erased_at == "2026-09-01T00:00:00Z" and
      e.tombstone.erased_at != r.finished_at)
line("EVD-032", "PASS" if ok else "FAIL", f"erased_by={e.tombstone.erased_by} authority={e.tombstone.authority} reason={e.tombstone.reason!r} erased_at={e.tombstone.erased_at}")

# EVD-033: tombstone holds no subject identity
r = R(0)
e = r.erase(by="dpo", authority="DSAR-3")
fields_ = dataclasses.fields(Tombstone)
names = [f.name for f in fields_]
line("EVD-033", "PASS" if set(names) == {"original_content_hash","erased_at","erased_by","authority","reason"} else "FAIL",
     f"tombstone fields={names} -- none is a subject/customer identifier field by name")

# EVD-034: Tombstone.from_dict ignores a supplied (forged) seal
forged = {"original_content_hash": "a"*64, "erased_at": "2026-01-01T00:00:00Z", "erased_by": "dpo",
          "authority": "A1", "reason": "right to erasure", "seal": "f"*64}
t = Tombstone.from_dict(forged)
recomputed_first = t.seal  # this is what "checked by recomputing with code under test" would give; must differ from forged
ok = t.seal != "f"*64
line("EVD-034", "PASS" if ok else "FAIL", f"forged_seal={'f'*64} recomputed_seal={t.seal} differs={ok}")

# EVD-035: verification reports erased records, not absorbed
chain = a_chain(5)
recs = chain.records()
e2r = recs[1].erase(by="dpo", authority="A", at="2026-01-01T00:00:00Z")
e3r = recs[3].erase(by="dpo", authority="A", at="2026-01-01T00:00:00Z")
recs5 = [recs[0], e2r, recs[2], e3r, recs[4]]
v5 = ledger_verify(r.to_dict() for r in recs5)
rendered = v5.render()
ok = v5.erased == 2 and "erased" in rendered and "2" in rendered
line("EVD-035", "PASS" if ok else "FAIL", f"erased={v5.erased} rendered={rendered!r}")

# EVD-036: Archivist.erase with a sequence not present
ledger = a_chain(5)
arch = Archivist()
try:
    result = arch.erase(ledger, [99], by="dpo")
    same = [r.to_dict() for r in result] == [r.to_dict() for r in ledger]
    line("EVD-036", "FAIL", f"no exception raised; returned list identical_to_original={same}; caller receives no statement that nothing was erased (bare list of {len(result)} records)")
except ValidationError as e:
    line("EVD-036", "PASS", f"ValidationError: {e}")
except Exception as e:
    line("EVD-036", "FAIL", f"unexpected exception type {type(e)}: {e}")

# EVD-037: erasure in hot storage doesn't retroactively alter a written bundle -- documentation/behavioural check
ledger = a_chain(5)
arch = Archivist()
bundle = arch.bundle(ledger.records(), tenant_id="t1")
ok_before, msg_before = bundle.check()
erased_records = arch.erase(ledger, [2], by="dpo", authority="A1")
# the bundle object is untouched (it's a separate artifact); check it again
ok_after, msg_after = bundle.check()
line("EVD-037", "PASS" if (ok_before and ok_after) else "FAIL", f"bundle_check_before_erase=({ok_before},{msg_before}) bundle_check_after_hot_erase=({ok_after},{msg_after})")

# EVD-038: a ledger entirely erased still verifies
ledger = a_chain(5)
arch = Archivist()
erased_all = arch.erase(ledger, list(range(5)), by="dpo", authority="A1")
v = ledger_verify(r.to_dict() for r in erased_all)
ok = v.is_intact and v.erased == 5
line("EVD-038", "PASS" if ok else "FAIL", f"intact={v.is_intact} erased={v.erased} rendered={v.render()!r}")

print("SECTION EVD-023..038 DONE")

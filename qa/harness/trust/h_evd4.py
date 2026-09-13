import dataclasses, hashlib, json, sys, copy, threading
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.evidence.record import EvidenceRecord, SnapshotRef, GENESIS
from prama.evidence.ledger import Ledger, verify as ledger_verify, merkle_root

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

# EVD-039: first record starts from genesis
l = Ledger()
r = l.append(R(0))
ok = r.sequence == 0 and r.previous_hash == GENESIS and l.head == r.record_hash
line("EVD-039", "PASS" if ok else "FAIL", f"sequence={r.sequence} previous_hash==GENESIS:{r.previous_hash==GENESIS} head==record_hash:{l.head==r.record_hash}")

# EVD-040: ledger sets sequence/previous_hash, caller's values overwritten
l = a_chain(3)
r = l.append(R(0, sequence=0, previous_hash="ff"*32))
ok = r.sequence == 3 and r.previous_hash == l.records()[2].record_hash
line("EVD-040", "PASS" if ok else "FAIL", f"caller_supplied sequence=0 previous_hash=ff*32; actual sequence={r.sequence} previous_hash={r.previous_hash}")

# EVD-041: sequence numbers contiguous across 1000 appends
l = Ledger()
for i in range(1000):
    l.append(R(0))
seqs = [r.sequence for r in l]
ok = seqs == list(range(1000))
line("EVD-041", "PASS" if ok else "FAIL", f"len={len(seqs)} first5={seqs[:5]} last5={seqs[-5:]} contiguous={ok}")

# EVD-042: head on empty ledger is genesis
l = Ledger()
v = l.verify()
ok = l.head == GENESIS and l.next_sequence == 0 and v.is_intact and v.records == 0 and l.merkle_root() == GENESIS
line("EVD-042", "PASS" if ok else "FAIL", f"head={l.head} next_sequence={l.next_sequence} verify_intact={v.is_intact} verify_records={v.records} merkle_root={l.merkle_root()}")

# EVD-043: edited record reported as content breach (and link)
l = a_chain(10)
payloads = [r.to_dict() for r in l]
payloads[4] = dict(payloads[4]); payloads[4]["verdict"] = "pass" if payloads[4]["verdict"] != "pass" else "fail"
# ensure the flip is actually different from original -- record4 verdict was 'pass' (constant in R()), so change to 'fail'
payloads[4]["verdict"] = "fail"
v = ledger_verify(payloads)
kinds4 = sorted(b.kind for b in v.breaches if b.sequence == 4)
ok = "content" in kinds4 and "link" in kinds4
line("EVD-043", "PASS" if ok else "FAIL", f"breaches_at_4={kinds4} all_breaches={[(b.kind,b.sequence) for b in v.breaches]}")

# EVD-044: record replaced wholesale with self-consistent fabrication -> no content breach at 4, but link breach at 5
l = a_chain(10)
recs = l.records()
fab = R(999, dataset="FABRICATED", verdict="fail")
fab = dataclasses.replace(fab, sequence=4, previous_hash=recs[3].record_hash)  # self-consistent but not the real record 4
payloads = [r.to_dict() for r in recs]
payloads[4] = fab.to_dict()
v = ledger_verify(payloads)
kinds4 = sorted(b.kind for b in v.breaches if b.sequence == 4)
kinds5 = sorted(b.kind for b in v.breaches if b.sequence == 5)
ok = "content" not in kinds4 and "link" in kinds5
line("EVD-044", "PASS" if ok else "FAIL", f"breaches_at_4={kinds4} breaches_at_5={kinds5}")

# EVD-045: fully re-chained forgery verifies as intact; only root/head differ from published
l = a_chain(10)
recs = l.records()
published_root = l.merkle_root()
published_head = l.head
new_recs = list(recs)
new_recs[4] = dataclasses.replace(recs[4], dataset="FABRICATED", verdict="fail")
# re-chain from 4 onward
rebuilt = Ledger()
for r in new_recs[:4]:
    rebuilt._records.append(r)
prev = new_recs[3].record_hash
final = []
final.extend(new_recs[:4])
for r in new_recs[4:]:
    relinked = dataclasses.replace(r, previous_hash=prev)
    final.append(relinked)
    prev = relinked.record_hash
v = ledger_verify(r.to_dict() for r in final)
new_root = merkle_root([r.record_hash for r in final])
new_head = final[-1].record_hash
ok = v.is_intact and new_root != published_root and new_head != published_head
line("EVD-045", "PASS" if ok else "FAIL", f"intact={v.is_intact} root_changed={new_root!=published_root} head_changed={new_head!=published_head}")

# EVD-046: record removed from middle -> gap breach naming seq 5, plus link
l = a_chain(10)
payloads = [r.to_dict() for r in l]
del payloads[4]
v = ledger_verify(payloads)
gap = [b for b in v.breaches if b.kind == "gap"]
ok = len(gap) >= 1 and gap[0].sequence == 5 and "missing" in gap[0].detail
line("EVD-046", "PASS" if ok else "FAIL", f"breaches={[(b.kind,b.sequence,b.detail) for b in v.breaches]}")

# EVD-047: two records swapped -> gap breach "out of order" + link breaches
l = a_chain(10)
payloads = [r.to_dict() for r in l]
payloads[4], payloads[5] = payloads[5], payloads[4]
v = ledger_verify(payloads)
gap = [b for b in v.breaches if b.kind == "gap"]
ok = any("out of order" in b.detail for b in gap) and any(b.kind == "link" for b in v.breaches)
line("EVD-047", "PASS" if ok else "FAIL", f"breaches={[(b.kind,b.sequence,b.detail) for b in v.breaches]}")

# EVD-048: truncation at end invisible to verify() over the remaining lines, but Bundle.check() fails on manifest count
from prama.evidence.retention import Archivist
l = a_chain(10)
arch = Archivist()
bundle = arch.bundle(l.records(), tenant_id="t1")
lines = bundle.payload.splitlines()
truncated_payload = "\n".join(lines[:-3])
truncated_records = [json.loads(x) for x in truncated_payload.splitlines()]
v = ledger_verify(truncated_records)
import dataclasses as dc
trunc_bundle = dc.replace(bundle, payload=truncated_payload)
ok_check, msg_check = trunc_bundle.check()
ok = v.is_intact and not ok_check
line("EVD-048", "PASS" if ok else "FAIL", f"verify_over_truncated_lines_intact={v.is_intact} bundle_check_ok={ok_check} bundle_check_msg={msg_check!r}")

# EVD-049: a window not starting at sequence 0 (e.g. 100..109) is verified with no breach (per catalogue's expectation)
l = a_chain(110)
window = l.records()[100:110]
v = ledger_verify(r.to_dict() for r in window)
ok = v.is_intact
line("EVD-049", "PASS" if ok else "FAIL",
     f"window seq {window[0].sequence}..{window[-1].sequence}; verify intact={v.is_intact} breaches={[(b.kind,b.sequence,b.detail) for b in v.breaches]}")

# EVD-050: genesis check fires only for a record claiming to be first (sequence==0, previous_hash != GENESIS)
r_bad = R(0, previous_hash="ab"*32)
v = ledger_verify([r_bad.to_dict()])
gen = [b for b in v.breaches if b.kind == "genesis"]
ok = len(gen) == 1
line("EVD-050", "PASS" if ok else "FAIL", f"breaches={[(b.kind,b.sequence,b.detail) for b in v.breaches]}")

# EVD-051: a single record on its own verifies only against itself (T11 shape) -- any content passes since both sides are supplied by the record
r_any = R(0, dataset="ANYTHING AT ALL", verdict="fail", previous_hash=GENESIS)
v = ledger_verify([r_any.to_dict()])
ok = v.is_intact  # this IS the documented limit -- pass if code behaves as T11 described (a lone record proves only itself)
line("EVD-051", "PASS" if ok else "FAIL", f"lone record of arbitrary content verifies intact={v.is_intact} (T11: proves its own content hash and nothing about position) breaches={[(b.kind) for b in v.breaches]}")

# EVD-052: concurrent appends -- is append thread-safe? No lock visible in source.
l = Ledger()
errors = []
def worker():
    try:
        for _ in range(500):
            l.append(R(0))
    except Exception as e:
        errors.append(e)
threads = [threading.Thread(target=worker) for _ in range(8)]
for t in threads: t.start()
for t in threads: t.join()
seqs = sorted(r.sequence for r in l)
n = len(seqs)
duplicates = n - len(set(seqs))
contiguous = seqs == list(range(n))
ok = (n == 4000 and duplicates == 0 and contiguous)
v = l.verify()
line("EVD-052", "PASS" if ok else "FAIL", f"total_records={n} expected=4000 duplicate_sequences={duplicates} contiguous={contiguous} chain_intact={v.is_intact} errors={errors[:2]}")

# EVD-053: storage seam -- public surface of Ledger
public = [m for m in dir(Ledger) if not m.startswith("_")]
ok = set(public) <= {"head","next_sequence","append","extend","records","since","find","verify","merkle_root","export"}
line("EVD-053", "PASS" if ok else "FAIL", f"public_surface={sorted(public)}")

# EVD-054: since/find do not renumber or relink
l = Ledger()
pids = []
for i in range(20):
    pid = f"plan-{i%3}"
    pids.append(pid)
    l.append(R(i, plan_id=pid))
since10 = l.since(10)
find0 = l.find("plan-0")
ok = all(r.sequence >= 10 for r in since10) and len(since10) == 10 and all(r.plan_id == "plan-0" for r in find0)
seqs_preserved = [r.sequence for r in since10][:3]
line("EVD-054", "PASS" if ok else "FAIL", f"since(10)_len={len(since10)} since(10)_first_seqs={seqs_preserved} find('plan-0')_count={len(find0)} find_seqs={[r.sequence for r in find0]}")

# EVD-055: export is ndjson, one record per line, even with embedded newline/unicode in detail
l = Ledger()
l.append(R(0, detail="line one\nline two üñî"))
l.append(R(1))
exported = l.export()
lines_ = exported.split("\n")
try:
    parsed = [json.loads(x) for x in lines_]
    ok = len(parsed) == 2
    err = None
except Exception as e:
    ok = False
    err = repr(e)
line("EVD-055", "PASS" if ok else "FAIL", f"num_lines_when_split_on_newline={len(lines_)} parse_each_as_json_ok={ok} error={err} detail_repr={l.records()[0].to_dict()['detail']!r}")

print("SECTION EVD-039..055 DONE")

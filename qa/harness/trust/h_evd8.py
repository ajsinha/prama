import dataclasses, hashlib, json, sys, datetime
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.evidence.record import EvidenceRecord, SnapshotRef, GENESIS
from prama.evidence.ledger import Ledger
from prama.evidence.retention import RetentionPolicy, Tier, Archivist, Manifest, Bundle, BUNDLE_VERSION
from prama.evidence.record import EVIDENCE_VERSION
from prama.core.errors import ValidationError
from prama.core.clock import Clock
from prama.security.egress import Gate

UTC = datetime.timezone.utc

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

class FixedClock(Clock):
    def __init__(self, t): self._t = t
    def now(self): return self._t
    def monotonic(self): return 0.0

# EVD-103: tiers out of order refused
try:
    RetentionPolicy(hot_days=400, warm_days=100)
    line("EVD-103", "FAIL", "no exception raised")
except ValidationError as e:
    ok = "hot" in str(e.context) and "400" in str(e.context) and "100" in str(e.context)
    line("EVD-103", "PASS" if ok else "FAIL", f"ValidationError: {e} context={e.context}")
except Exception as e:
    line("EVD-103", "FAIL", f"wrong exception type: {type(e)}: {e}")

# EVD-104: equal tier lengths allowed
try:
    p = RetentionPolicy(hot_days=90, warm_days=90, cold_days=90)
    line("EVD-104", "PASS", f"accepted: {p}")
except Exception as e:
    line("EVD-104", "FAIL", f"raised: {e}")

# EVD-105: boundary tier_at
p = RetentionPolicy()
r1 = p.tier_at(90.0); r2 = p.tier_at(90.0001); r3 = p.tier_at(365.0); r4 = p.tier_at(365.0001)
ok = r1 is Tier.HOT and r2 is Tier.WARM and r3 is Tier.WARM and r4 is Tier.COLD
line("EVD-105", "PASS" if ok else "FAIL", f"90.0->{r1} 90.0001->{r2} 365.0->{r3} 365.0001->{r4}")

# EVD-106: past cold window, expire=False -> stays COLD forever
p = RetentionPolicy(expire=False)
r = p.tier_at(10_000)
line("EVD-106", "PASS" if r is Tier.COLD else "FAIL", f"tier_at(10000)={r}")

# EVD-107: expiry happens only when asked
p = RetentionPolicy(expire=True)
r1 = p.tier_at(p.cold_days); r2 = p.tier_at(p.cold_days + 1)
ok = r1 is Tier.COLD and r2 is Tier.EXPIRED
line("EVD-107", "PASS" if ok else "FAIL", f"tier_at(cold_days)={r1} tier_at(cold_days+1)={r2}")

# EVD-108: record with no finish time stays hot
arch = Archivist()
r = R(0, finished_at="")
line("EVD-108", "PASS" if arch.tier_of(r) is Tier.HOT else "FAIL", f"tier_of={arch.tier_of(r)}")

# EVD-109: unparsable finish time stays hot, no exception
r = R(0, finished_at="yesterday")
try:
    t = arch.tier_of(r)
    line("EVD-109", "PASS" if t is Tier.HOT else "FAIL", f"tier_of={t}")
except Exception as e:
    line("EVD-109", "FAIL", f"raised {type(e).__name__}: {e}")

# EVD-110: naive timestamp does not crash archivist
r = R(0, finished_at="2026-01-01T00:00:00")  # no offset
try:
    t = arch.tier_of(r)
    line("EVD-110", "PASS", f"tier_of returned without crashing: {t}")
except TypeError as e:
    line("EVD-110", "FAIL", f"TypeError (naive vs aware datetime subtraction): {e}")
except Exception as e:
    line("EVD-110", "FAIL", f"unexpected {type(e).__name__}: {e}")

# EVD-111: tier plan accounts for every record exactly once
clock = FixedClock(datetime.datetime(2028, 1, 1, tzinfo=UTC))
arch2 = Archivist(clock=clock)
ledger = Ledger()
# hot: recent; warm: ~200 days old; cold: ~1000 days old; expired doesn't apply since default expire=False
ledger.append(R(0, finished_at="2027-12-20T00:00:00Z"))  # ~12 days -> hot
ledger.append(R(1, finished_at="2027-06-01T00:00:00Z"))  # ~214 days -> warm
ledger.append(R(2, finished_at="2020-01-01T00:00:00Z"))  # very old -> cold
plan = arch2.plan(ledger)
total = sum(len(v) for v in plan.values())
ok = total == len(ledger) and set(plan.keys()) == {"hot", "warm", "cold", "expired"}
line("EVD-111", "PASS" if ok else "FAIL", f"plan_counts={{k: len(v) for k,v in plan.items()}} total={total} len_ledger={len(ledger)}")

# EVD-112: retention report describes policy in words
p1 = RetentionPolicy(expire=True, cold_days=2555)
p2 = RetentionPolicy(expire=False, cold_days=2555)
d1 = p1.describe(); d2 = p2.describe()
ok = "deleted after" in d1 and "2,555" in d1 and "kept indefinitely" in d2 and "2,555" in d2
line("EVD-112", "PASS" if ok else "FAIL", f"expire=True: {d1!r} expire=False: {d2!r}")

# EVD-113: bundling nothing refused
try:
    Archivist().bundle([], tenant_id="t1")
    line("EVD-113", "FAIL", "no exception")
except ValidationError as e:
    line("EVD-113", "PASS", f"ValidationError: {e}")
except Exception as e:
    line("EVD-113", "FAIL", f"wrong type {type(e)}: {e}")

# EVD-114: residency gate consulted before bundling
from prama.security.residency import Policy
from prama.security.egress import ResidencyRefused
ledger = a_chain(3)
gate = Gate.for_tenant("EU", tenant_id="acme-eu")
try:
    Archivist().bundle(ledger.records(), tenant_id="acme-eu", gate=gate, archive_region="US", jurisdiction="EU")
    line("EVD-114", "FAIL", "no exception raised; bundle produced despite residency gate configured for EU-only with US destination")
except ResidencyRefused as e:
    ok = "US" in str(e.context) and "acme-eu" in str(e.context) and "EU" in str(e.context)
    line("EVD-114", "PASS" if ok else "FAIL", f"ResidencyRefused: {e} context={e.context}")
except Exception as e:
    line("EVD-114", "FAIL", f"wrong exception type {type(e)}: {e}")

# EVD-115: refused bundle refused wholesale (spanning two jurisdictions, one permitted)
ledger2 = a_chain(4)
gate2 = Gate.for_tenant("EU", tenant_id="acme-eu")
try:
    # even records span an allowed dest (EU), a batch call declares one jurisdiction for the whole bundle
    b = Archivist().bundle(ledger2.records(), tenant_id="acme-eu", gate=gate2, archive_region="US", jurisdiction="mixed-EU-US")
    line("EVD-115", "FAIL", f"bundle produced with {len(b.payload.splitlines())} records instead of failing wholesale")
except ResidencyRefused as e:
    line("EVD-115", "PASS", f"whole call refused (no partial bundle object exists): {e}")
except Exception as e:
    line("EVD-115", "FAIL", f"wrong exception type {type(e)}: {e}")

# EVD-116: manifest describes the payload it was built from
ledger3 = Ledger()
for i in range(10):
    ledger3.append(R(i))
recs = ledger3.records()
erased_recs = list(recs)
erased_recs[2] = recs[2].erase(by="dpo", authority="A1", at="2026-01-01T00:00:00Z")
erased_recs[5] = recs[5].erase(by="dpo", authority="A1", at="2026-01-01T00:00:00Z")
arch3 = Archivist()
bundle3 = arch3.bundle(erased_recs, tenant_id="t1")
m = bundle3.manifest
payload_bytes = bundle3.payload.encode("utf-8")
ok = (m.records == 10 and m.erased == 2 and m.from_sequence == erased_recs[0].sequence and
      m.to_sequence == erased_recs[-1].sequence and
      m.payload_digest == hashlib.sha256(payload_bytes).hexdigest() and
      m.chain_head == erased_recs[-1].record_hash and
      m.bundle_version == BUNDLE_VERSION and m.evidence_version == EVIDENCE_VERSION)
line("EVD-116", "PASS" if ok else "FAIL", f"records={m.records} erased={m.erased} from_seq={m.from_sequence} to_seq={m.to_sequence} digest_ok={m.payload_digest==hashlib.sha256(payload_bytes).hexdigest()} chain_head_ok={m.chain_head==erased_recs[-1].record_hash} bundle_version={m.bundle_version} evidence_version={m.evidence_version}")

# EVD-117: Bundle.check() passes on a bundle as built (window starting at sequence 0)
ok_check, msg_check = bundle3.check()
line("EVD-117", "PASS" if ok_check else "FAIL", f"check()={ok_check} msg={msg_check!r}")

# EVD-118: Bundle.check() fails on a truncated payload
lines_ = bundle3.payload.splitlines()
truncated = "\n".join(lines_[:-2])
trunc_bundle = dataclasses.replace(bundle3, payload=truncated)
ok2, msg2 = trunc_bundle.check()
line("EVD-118", "PASS" if (not ok2 and "incomplete" in msg2) else "FAIL", f"check()={ok2} msg={msg2!r}")

# EVD-119: Bundle.check() fails on payload not matching digest (one char changed, count preserved)
lines_ = bundle3.payload.splitlines()
lines_[0] = lines_[0][:-1] + ("0" if lines_[0][-1] != "0" else "1")  # corrupt trailing char of first line's JSON (still valid JSON overall length preserved? just corrupt digest)
corrupted_payload = "\n".join(lines_)
corrupt_bundle = dataclasses.replace(bundle3, payload=corrupted_payload)
ok3, msg3 = corrupt_bundle.check()
line("EVD-119", "PASS" if (not ok3 and "digest" in msg3) else "FAIL", f"check()={ok3} msg={msg3!r}")

# EVD-120: Bundle.check() fails when manifest head edited
bad_manifest = dataclasses.replace(bundle3.manifest, chain_head="ab"*32)
bad_head_bundle = dataclasses.replace(bundle3, manifest=bad_manifest)
ok4, msg4 = bad_head_bundle.check()
line("EVD-120", "PASS" if (not ok4 and "chain head" in msg4) else "FAIL", f"check()={ok4} msg={msg4!r}")

# EVD-121: bundle writes exactly two files
files = bundle3.files()
line("EVD-121", "PASS" if set(files.keys()) == {"manifest.json", "evidence.ndjson"} else "FAIL", f"files={sorted(files.keys())}")

# EVD-122: manifest's verification prose vs what the verifier does -- check it mentions tombstone seal, merkle root, payload digest
prose = bundle3.manifest.verification
mentions_tombstone_seal = "seal" in prose.lower()
mentions_merkle = "merkle" in prose.lower()
mentions_payload_digest = "payload_digest" in prose.lower() or "payload digest" in prose.lower()
all_present = mentions_tombstone_seal and mentions_merkle and mentions_payload_digest
line("EVD-122", "FAIL" if not all_present else "PASS",
     f"prose={prose!r} mentions_tombstone_seal={mentions_tombstone_seal} mentions_merkle_root={mentions_merkle} mentions_payload_digest={mentions_payload_digest}")

# EVD-123: bundle version recorded and read back
line("EVD-123", "PASS" if bundle3.manifest.bundle_version == "1.0" else "FAIL", f"bundle_version={bundle3.manifest.bundle_version}")

# EVD-124: nothing in the product actually exports an evidence bundle -- search cli/ and api/ for Archivist().bundle( calls
import subprocess
grep = subprocess.run(["grep", "-rn", "Archivist(", "/home/ashutosh/PycharmProjects/prama/src/prama/cli", "/home/ashutosh/PycharmProjects/prama/src/prama/api"], capture_output=True, text=True)
hits = grep.stdout.strip()
line("EVD-124", "FAIL" if not hits else "PASS", f"grep -rn 'Archivist(' src/prama/cli src/prama/api -> {hits or '(no hits: nothing in cli or api constructs an Archivist or calls .bundle())'}")

print("SECTION EVD-103..124 DONE")

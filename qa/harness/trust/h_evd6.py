import dataclasses, hashlib, json, sys, inspect, datetime
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.evidence.record import EvidenceRecord, SnapshotRef, GENESIS
from prama.evidence.ledger import Ledger
from prama.evidence.recorder import Recorder, SampleStore, SampleSet, _snapshot_ref
from prama.ir.model import ControlPlan, Scope, Provenance, Verdict
from prama.backend.execute import ControlResult
from prama.core.clock import Clock

def a_plan(**changes):
    base = dict(
        scope=Scope(dataset="positions_eod", binding="pg://RISK.POSITIONS"),
        dimensions=("completeness", "accuracy"),
        provenance=Provenance(pql_hash="deadbeef" * 8),
    )
    base.update(changes)
    return ControlPlan(**base)

def a_result(**changes):
    base = dict(plan_id="", verdict=Verdict.PASS, metrics={"scanned_rows": 100.0, "violating_rows": 0.0}, engine="postgresql")
    base.update(changes)
    return ControlResult(**base)

class FixedClock(Clock):
    def __init__(self, t):
        self._t = t
    def now(self):
        return self._t
    def monotonic(self):
        return 0.0

UTC = datetime.timezone.utc

# EVD-075: a recorded run lands in the ledger, linked
ledger = Ledger()
samples = SampleStore()
rec = Recorder(ledger, samples, engine="postgresql", tenant_id="t1")
plan = a_plan()
result = a_result(plan_id=plan.plan_id)
returned = rec.record(plan, result)
ok = returned.sequence == 0 and returned.previous_hash == GENESIS and ledger.verify().is_intact and len(ledger) == 1
line("EVD-075", "PASS" if ok else "FAIL", f"sequence={returned.sequence} previous_hash==GENESIS:{returned.previous_hash==GENESIS} verify_intact={ledger.verify().is_intact} len={len(ledger)}")

# EVD-076: control_id defaults to plan's pql_hash
plan2 = a_plan(provenance=Provenance(pql_hash="cafebabe" * 8))
result2 = a_result(plan_id=plan2.plan_id)
r2 = rec.record(plan2, result2)
ok = r2.control_id == plan2.provenance.pql_hash
line("EVD-076", "PASS" if ok else "FAIL", f"control_id={r2.control_id} pql_hash={plan2.provenance.pql_hash}")

# EVD-077: dimensions come from the plan, no caller parameter
sig = inspect.signature(rec.record)
has_dims_param = "dimensions" in sig.parameters
plan3 = a_plan(dimensions=("timeliness",))
result3 = a_result(plan_id=plan3.plan_id)
r3 = rec.record(plan3, result3)
ok = (not has_dims_param) and r3.dimensions == ("timeliness",)
line("EVD-077", "PASS" if ok else "FAIL", f"signature={sig} has_dimensions_param={has_dims_param} record_dimensions={r3.dimensions}")

# EVD-078: criticality supplied by caller, both accepted, visible
plan4 = a_plan()
result4 = a_result(plan_id=plan4.plan_id)
rA = rec.record(plan4, result4, criticality=1)
rB = rec.record(plan4, result4, criticality=4)
ok = rA.criticality == 1 and rB.criticality == 4
line("EVD-078", "PASS" if ok else "FAIL", f"criticality_1_record={rA.criticality} criticality_4_record={rB.criticality} -- caller CAN choose criticality; asymmetry with dimensions documented in recorder.py docstring")

# EVD-079: run with no snapshot -> kind=none, identifier='', exact=False
ref = _snapshot_ref(None)
ok = ref.kind == "none" and ref.identifier == "" and ref.exact is False
line("EVD-079", "PASS" if ok else "FAIL", f"kind={ref.kind} identifier={ref.identifier!r} exact={ref.exact}")

# EVD-080: source's own snapshot carried verbatim, enum unwrapped
class FakeSnap:
    class K:
        value = "file_digest"
    kind = K()
    identifier = "sha256:abcd"
    exact = True
ref2 = _snapshot_ref(FakeSnap())
ok = ref2.kind == "file_digest" and ref2.identifier == "sha256:abcd" and ref2.exact is True
line("EVD-080", "PASS" if ok else "FAIL", f"kind={ref2.kind} identifier={ref2.identifier} exact={ref2.exact}")

# EVD-081: negative duration clamped to 0
clock = FixedClock(datetime.datetime(2026, 1, 1, tzinfo=UTC))
rec_neg = Recorder(Ledger(), SampleStore(), clock=clock)
plan5 = a_plan()
result5 = a_result(plan_id=plan5.plan_id)
started_later = datetime.datetime(2026, 1, 2, tzinfo=UTC)  # started_at AFTER finished (clock.now())
r5 = rec_neg.record(plan5, result5, started_at=started_later)
ok = r5.duration_ms == 0
line("EVD-081", "PASS" if ok else "FAIL", f"duration_ms={r5.duration_ms}")

# EVD-082: metric engine did not return is absent, not zero
plan6 = a_plan()
result6 = a_result(plan_id=plan6.plan_id, metrics={"scanned_rows": 10.0})  # violating_rows omitted
r6 = rec.record(plan6, result6)
ok = "violating_rows" not in r6.metrics and "scanned_rows" in r6.metrics
line("EVD-082", "PASS" if ok else "FAIL", f"metrics={r6.metrics}")

# EVD-083: samples stored only when rows given
plan7 = a_plan()
result7 = a_result(plan_id=plan7.plan_id, verdict=Verdict.FAIL)
r7 = rec.record(plan7, result7, rows=None)
ok = r7.samples_digest == "" and r7.sample_count == 0 and len(samples) == 0
line("EVD-083", "PASS" if ok else "FAIL", f"samples_digest={r7.samples_digest!r} sample_count={r7.sample_count} store_len={len(samples)}")

# EVD-084: two identical sample sets share one digest; forgetting one forgets both
store2 = SampleStore()
rec8 = Recorder(Ledger(), store2)
plan8a = a_plan(provenance=Provenance(pql_hash="a"*64))
plan8b = a_plan(provenance=Provenance(pql_hash="b"*64))
rows = [{"id": 1, "reason": "x"}]
r8a = rec8.record(plan8a, a_result(plan_id=plan8a.plan_id, verdict=Verdict.FAIL), rows=list(rows))
r8b = rec8.record(plan8b, a_result(plan_id=plan8b.plan_id, verdict=Verdict.FAIL), rows=list(rows))
same_digest = r8a.samples_digest == r8b.samples_digest
store2.forget(r8a.samples_digest)
other_gone = store2.get(r8b.samples_digest) is None
# NOTE (round 3): the original assertion checked only the mechanics
# (same_digest, forgetting-one-forgets-both), which already held in round 2
# too -- round 2's own published verdict FAILED this case on a requirement
# the saved script never encoded: the catalogue also requires the sharing
# behaviour to be *stated*, not merely true, and SampleStore.put/forget carry
# no docstring sentence about shared digests or the retention consequence. A
# harness completeness gap, not a change in the underlying mechanics.
import inspect as _inspect6
store_src = _inspect6.getsource(SampleStore)
documented = ("shared" in store_src.lower() or "content-address" in store_src.lower()
              or "same digest" in store_src.lower() or "identical" in store_src.lower())
ok = same_digest and other_gone and documented
line("EVD-084", "PASS" if ok else "FAIL",
     f"same_digest={same_digest} digest={r8a.samples_digest} forgetting_one_also_forgets_other={other_gone} "
     f"(content-addressed sharing, not reference-counted) documented_in_SampleStore_docstrings={documented}")

# EVD-085: sample digest format sha256: + 32 hex chars (128 bits)
s = store2.put([{"a": 1}])
digest = s.digest
ok = digest.startswith("sha256:") and len(digest) == len("sha256:") + 32
line("EVD-085", "PASS" if ok else "FAIL", f"digest={digest} len_hex_part={len(digest)-7}")

# EVD-086: forgetting a sample leaves the record intact
ledger9 = Ledger()
store9 = SampleStore()
rec9 = Recorder(ledger9, store9)
plan9 = a_plan()
rows9 = [{"id": i} for i in range(50)]
r9 = rec9.record(plan9, a_result(plan_id=plan9.plan_id, verdict=Verdict.FAIL), rows=rows9)
store9.forget(r9.samples_digest)
v9 = ledger9.verify()
r9_reread = ledger9.records()[0]
ok = v9.is_intact and r9_reread.sample_count == 50 and store9.get(r9.samples_digest) is None
line("EVD-086", "PASS" if ok else "FAIL", f"verify_intact={v9.is_intact} sample_count={r9_reread.sample_count} rows_gone={store9.get(r9.samples_digest) is None}")

# EVD-087: masked columns lost when sample expires
store10 = SampleStore()
sset = store10.put([{"iban": "xxx", "name": "xxx", "amount": 5}], masked=("iban", "name"))
store10.forget(sset.digest)
# after forgetting, can we determine masked columns from anything the record carries? Recorder doesn't store masked info in EvidenceRecord at all
ledger10 = Ledger()
rec10 = Recorder(ledger10, store10)
plan10 = a_plan()
r10 = rec10.record(plan10, a_result(plan_id=plan10.plan_id, verdict=Verdict.FAIL), rows=[{"iban":"x"}], masked=("iban",))
fields_on_record = {f.name for f in dataclasses.fields(EvidenceRecord)}
ok = "masked" not in fields_on_record and "masked_columns" not in fields_on_record
line("EVD-087", "FAIL" if ok else "PASS", f"EvidenceRecord fields do not include which columns were masked ({sorted(fields_on_record)}); once SampleStore.forget() is called the masked tuple is gone with the SampleSet and nothing on the EvidenceRecord records it -- undocumented absence")

# EVD-088: empty ledger/samplestore passed in are used, not replaced (falsy __len__ pitfall)
ledger11 = Ledger()
store11 = SampleStore()
rec11 = Recorder(ledger11, store11)
plan11 = a_plan()
rec11.record(plan11, a_result(plan_id=plan11.plan_id))
ok = len(ledger11) == 1 and rec11.ledger is ledger11
line("EVD-088", "PASS" if ok else "FAIL", f"caller_ledger_len={len(ledger11)} recorder.ledger_is_callers_object={rec11.ledger is ledger11}")

print("SECTION EVD-075..088 DONE")

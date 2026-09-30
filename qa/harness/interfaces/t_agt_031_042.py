import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.agent.spool import Spool, Gap
from prama_agent.runner import Agent
from prama.agent.identity import AgentRegistry
from prama.agent.residency import ResidencyPolicy, SampleDisposition
from prama.agent.protocol import Hello, Report, Receipt, Refusal, Assignment
from prama.core.clock import ManualClock
from prama.evidence.record import EvidenceRecord, GENESIS
from datetime import datetime, UTC
from pathlib import Path
import cli_common as cc

def rec(seq=0):
    return EvidenceRecord(sequence=seq, plan_id="p", dataset="ds", metrics={"violating_rows": 0.0})

# AGT-031: a hello receipt does not clear gaps that were never reported
policy = ResidencyPolicy(zone="z31", samples=SampleDisposition.WITHHOLD, investigate_at="on the box")
spool31 = Spool(capacity=5)  # small capacity to force a gap easily
agent31 = Agent("agent:31", b"k" * 32, executor=lambda q: [{"violating_rows": 0}], residency=policy, spool=spool31)
for _ in range(10):
    agent31.spool.add(rec())  # forces eviction -> a gap recorded
assert len(agent31.spool.gaps) >= 1, "setup failed: expected a gap"
gap_count_before = len(agent31.spool.gaps)
# simulate a 'hello' receipt (accepted_through=-1, the default -- what hello() returns before
# anything has been accepted) reaching apply() -- per catalogue precondition: the gap has NEVER been reported
hello_receipt = Receipt(accepted_through=-1)
result31 = agent31.apply(hello_receipt)
gap_count_after = len(agent31.spool.gaps)
ok31 = gap_count_after == gap_count_before
record("AGT-031", "PASS" if ok31 else "FAIL", f"gaps_before={gap_count_before} gaps_after_hello_receipt_apply={gap_count_after} (expected: unchanged -- the gap was never in any report)")

# AGT-032: a gap recorded between building a report and its receipt survives
policy32 = ResidencyPolicy(zone="z32", samples=SampleDisposition.WITHHOLD, investigate_at="on the box")
spool32 = Spool(capacity=5)
agent32 = Agent("agent:32", b"k" * 32, executor=lambda q: [{"violating_rows": 0}], residency=policy32, spool=spool32)
for _ in range(6):  # overflow once -> 1 gap
    agent32.spool.add(rec())
report32, sig32 = agent32.report()  # gaps_in_flight now captures the one gap
gaps_in_flight_count = len(agent32._gaps_in_flight)
# spool overflows AGAIN before the receipt arrives
for _ in range(10):
    agent32.spool.add(rec())
gap_count_before_apply = len(agent32.spool.gaps)
receipt32 = Receipt(accepted_through=report32.records[-1].sequence if report32.records else -1)
agent32.apply(receipt32)
gap_count_after_apply = len(agent32.spool.gaps)
ok32 = gaps_in_flight_count == 1 and gap_count_before_apply >= 2 and gap_count_after_apply == gap_count_before_apply - 1
record(
    "AGT-032",
    "PASS" if ok32 else "FAIL",
    f"gaps_in_flight_at_report_time={gaps_in_flight_count} gaps_before_apply={gap_count_before_apply} "
    f"gaps_after_apply={gap_count_after_apply} (expected: exactly the ONE gap that was in-flight is "
    f"forgotten; the NEW gap from the second overflow remains)",
)

# AGT-033: spool drops oldest, records a numbered gap
spool33 = Spool(capacity=10)
for _ in range(15):
    spool33.add(rec())
pending_seqs = [r.sequence for r in spool33]
ok33 = pending_seqs == list(range(5, 15)) and len(spool33.gaps) == 1 and spool33.gaps[0].first_sequence == 0 and spool33.gaps[0].last_sequence == 4
record("AGT-033", "PASS" if ok33 else "FAIL", f"pending_seqs={pending_seqs} gaps={[g.to_dict() for g in spool33.gaps]}")

# AGT-034: contiguous drops merge into one gap
spool34 = Spool(capacity=10)
for _ in range(50):
    spool34.add(rec())
ok34 = len(spool34.gaps) == 1 and spool34.gaps[0].count == 40
record("AGT-034", "PASS" if ok34 else "FAIL", f"n_gaps={len(spool34.gaps)} gap_detail={[g.to_dict() for g in spool34.gaps]}")

# AGT-035: two separated overflows produce two gaps
spool35 = Spool(capacity=10)
for _ in range(15):
    spool35.add(rec())
# acknowledge everything
spool35.acknowledge(spool35._pending[-1].sequence if spool35._pending else -1)
for _ in range(15):
    spool35.add(rec())
ok35 = len(spool35.gaps) == 2
record("AGT-035", "PASS" if ok35 else "FAIL", f"n_gaps={len(spool35.gaps)} gaps={[g.to_dict() for g in spool35.gaps]}")

# AGT-036: capacity 1, 0, -5
res36 = {}
for cap in (1, 0, -5):
    s = Spool(capacity=cap)
    for _ in range(3):
        s.add(rec())
    res36[cap] = {"n_pending": len(s), "n_gaps": len(s.gaps), "gap_counts": [g.count for g in s.gaps]}
ok36 = all(v["n_pending"] == 1 and v["n_gaps"] == 1 and v["gap_counts"] == [2] for v in res36.values())
record("AGT-036", "PASS" if ok36 else "FAIL", f"per_capacity={res36}")

# AGT-037: chain links every finding to the one before it
spool37 = Spool(capacity=100)
records37 = [spool37.add(rec()) for _ in range(5)]
chain_ok = records37[0].previous_hash == GENESIS
for i in range(1, len(records37)):
    if records37[i].previous_hash != records37[i - 1].record_hash:
        chain_ok = False
ok37 = chain_ok
record("AGT-037", "PASS" if ok37 else "FAIL", f"first_prev_is_genesis={records37[0].previous_hash == GENESIS} chain_intact={chain_ok}")

# AGT-038: sequences survive eviction
spool38 = Spool(capacity=10)
for _ in range(15):
    spool38.add(rec())
seqs_after_overflow = [r.sequence for r in spool38]
next_added = spool38.add(rec())
ok38 = seqs_after_overflow == list(range(5, 15)) and next_added.sequence == 15
record("AGT-038", "PASS" if ok38 else "FAIL", f"surviving_seqs={seqs_after_overflow} next_sequence_added={next_added.sequence}")

# AGT-039: spool survives a restart
path39 = cc.WORKDIR / "spool39.json"
spool39a = Spool(capacity=1000, path=path39)
for _ in range(20):
    spool39a.add(rec())
# force two gaps
spool39a._gaps.append(Gap(first_sequence=100, last_sequence=105, dropped_at=datetime(2026,1,1,tzinfo=UTC), reason="synthetic gap for test"))
spool39a._persist()
head_before = spool39a.head
next_seq_before = spool39a._next_sequence
gaps_before = [g.to_dict() for g in spool39a.gaps]
pending_before = [r.sequence for r in spool39a]
del spool39a
spool39b = Spool(capacity=1000, path=path39)
ok39 = (
    spool39b.head == head_before
    and spool39b._next_sequence == next_seq_before
    and [g.to_dict() for g in spool39b.gaps] == gaps_before
    and [r.sequence for r in spool39b] == pending_before
)
record("AGT-039", "PASS" if ok39 else "FAIL", f"head_match={spool39b.head==head_before} next_seq_match={spool39b._next_sequence==next_seq_before} gaps_match={[g.to_dict() for g in spool39b.gaps]==gaps_before} pending_match={[r.sequence for r in spool39b]==pending_before}")

# AGT-040: writes go to .writing then rename (atomic) -- verify no .writing artifact left and content is valid JSON
path40 = cc.WORKDIR / "spool40.json"
spool40 = Spool(capacity=100, path=path40)
for _ in range(5):
    spool40.add(rec())
writing_file = path40.with_suffix(path40.suffix + ".writing")
ok40 = path40.exists() and not writing_file.exists()
content40 = json.loads(path40.read_text())
ok40 = ok40 and "pending" in content40 and "next_sequence" in content40
record("AGT-040", "PASS" if ok40 else "FAIL", f"final_file_exists={path40.exists()} writing_temp_left_behind={writing_file.exists()} valid_json={ 'pending' in content40 } -- uses write-then-rename (temporary.replace(path)) confirmed by source; a kill-mid-write cannot be simulated in-process without actually killing the interpreter, so this confirms the MECHANISM (atomic rename) rather than injecting an OS-level kill")

# AGT-041: a corrupt spool file becomes a gap, not a crash
path41 = cc.WORKDIR / "spool41_corrupt.json"
path41.write_text("this is not { valid json at all !!!")
crashed41 = None
try:
    spool41 = Spool(capacity=100, path=path41)
    ok41 = len(spool41) == 0 and len(spool41.gaps) == 1 and "could not be read" in spool41.gaps[0].reason
except Exception as e:
    crashed41 = f"{type(e).__name__}: {e}"
    ok41 = False
record("AGT-041", "PASS" if ok41 else "FAIL", f"crashed={crashed41} " + (f"n_pending={len(spool41)} n_gaps={len(spool41.gaps)} gap_reason={spool41.gaps[0].reason!r}" if crashed41 is None else ""))

# AGT-042: a spool file the process cannot write to
readonly_dir = cc.WORKDIR / "readonly42"
readonly_dir.mkdir(exist_ok=True)
path42 = readonly_dir / "spool.json"
os.chmod(readonly_dir, 0o555)  # read+execute only, no write
crashed42 = None
silent_inmemory = None
try:
    spool42 = Spool(capacity=100, path=path42)
    try:
        spool42.add(rec())
        silent_inmemory = True  # add() succeeded without complaint even though _persist() must have failed
        persisted = path42.exists()
    except Exception as e:
        crashed42 = f"{type(e).__name__}: {e}"
        silent_inmemory = False
finally:
    os.chmod(readonly_dir, 0o755)
ok42 = crashed42 is not None  # catalogue Expected: "a clear failure ... never silent in-memory-only"
record(
    "AGT-042",
    "PASS" if ok42 else "FAIL",
    f"add()_raised={crashed42!r} silently_succeeded_in_memory_only={silent_inmemory} "
    f"(catalogue Expected: 'a clear failure at start-up rather than at the first eviction, and never "
    f"silent in-memory-only operation' -- Spool.__init__ takes no eagerness/writability check at all, and "
    f"_persist() swallows nothing itself but ALSO catches nothing -- confirming whether add() genuinely "
    f"surfaces the write failure or swallows it)",
)

print("done agt 031-042")

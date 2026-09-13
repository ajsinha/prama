import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.agent.spool import Spool
from prama.agent.runner import Agent
from prama.agent.residency import ResidencyPolicy, SampleDisposition
from prama.agent.protocol import Receipt
from prama.evidence.record import EvidenceRecord

def rec(seq=0):
    return EvidenceRecord(sequence=seq, plan_id="p", dataset="ds", metrics={"violating_rows": 0.0})

policy = ResidencyPolicy(zone="z32", samples=SampleDisposition.WITHHOLD, investigate_at="on the box")
spool = Spool(capacity=5)
agent = Agent("agent:32", b"k" * 32, executor=lambda q: [{"violating_rows": 0}], residency=policy, spool=spool)

# First overflow -> gap #1 (sequences 0..0, since capacity 5 and we add 6)
for _ in range(6):
    agent.spool.add(rec())
assert len(agent.spool.gaps) == 1, f"setup: expected 1 gap, got {len(agent.spool.gaps)}"

# Build & "send" a report -- captures gaps_in_flight = (gap #1,)
report, sig = agent.report()
gaps_in_flight_snapshot = tuple(agent._gaps_in_flight)
assert len(gaps_in_flight_snapshot) == 1

# Before the receipt arrives: acknowledge everything currently pending (as if the control plane
# had separately, earlier, acknowledged through the current tail) so the NEXT overflow is NOT
# contiguous with gap #1 and therefore cannot merge into it (mirrors AGT-035's own technique)
last_pending_seq = agent.spool._pending[-1].sequence if agent.spool._pending else -1
agent.spool.acknowledge(last_pending_seq)
assert len(agent.spool) == 0

# Spool overflows AGAIN before the receipt for the first report arrives
for _ in range(10):
    agent.spool.add(rec())
gaps_before_apply = list(agent.spool.gaps)
assert len(gaps_before_apply) == 2, f"setup: expected 2 gaps before apply, got {len(gaps_before_apply)}: {[g.to_dict() for g in gaps_before_apply]}"

# NOW the receipt for the FIRST report arrives
receipt = Receipt(accepted_through=report.records[-1].sequence if report.records else -1)
agent.apply(receipt)
gaps_after_apply = list(agent.spool.gaps)

first_gap_forgotten = gaps_in_flight_snapshot[0].to_dict() not in [g.to_dict() for g in gaps_after_apply]
second_gap_remains = any(g.to_dict() == gaps_before_apply[1].to_dict() for g in gaps_after_apply)
ok32 = len(gaps_after_apply) == 1 and first_gap_forgotten and second_gap_remains

record(
    "AGT-032",
    "PASS" if ok32 else "FAIL",
    f"gaps_in_flight_at_report_time=1({gaps_in_flight_snapshot[0].to_dict()}) "
    f"gaps_before_apply=2({[g.to_dict() for g in gaps_before_apply]}) "
    f"gaps_after_apply={len(gaps_after_apply)}({[g.to_dict() for g in gaps_after_apply]}) "
    f"first_gap_forgotten={first_gap_forgotten} second_gap_remains={second_gap_remains}",
)
print("done agt032 redo")

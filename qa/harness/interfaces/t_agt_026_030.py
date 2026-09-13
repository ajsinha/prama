import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.agent.identity import AgentRegistry
from prama.agent.coordinator import Coordinator
from prama.agent.protocol import Report, Receipt
from prama.core.clock import ManualClock
from prama.evidence.record import EvidenceRecord
from prama.evidence.ledger import Ledger
from prama.agent.spool import Spool
from datetime import datetime, UTC

def mk_agent(zone, clock=None):
    clock = clock or ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
    reg = AgentRegistry(clock=clock)
    token, secret = reg.issue_token(zone)
    agent, key = reg.enrol(secret.reveal())
    return reg, agent, clock

def mk_report(agent_id, records):
    return Report(agent_id=agent_id, records=tuple(records))

def sign(reg, agent_id, msg):
    return reg.sign_as(agent_id, msg.signable())

def rec(seq):
    return EvidenceRecord(sequence=seq, plan_id=f"p{seq}", dataset="ds", metrics={"violating_rows": 0.0})

# AGT-026: duplicate delivery recognised and counted
reg26, agent26, clock26 = mk_agent("z26")
ledger26 = Ledger()
coord26 = Coordinator(reg26, ledger=ledger26, clock=clock26)
records1 = [rec(i) for i in range(11)]  # 0..10
report1 = mk_report(agent26.agent_id, records1)
sig1 = sign(reg26, agent26.agent_id, report1)
resp1 = coord26.report(report1, sig1)
n_ledger_after_first = len(ledger26)
report2 = mk_report(agent26.agent_id, records1)  # SAME records again
sig2 = sign(reg26, agent26.agent_id, report2)
resp2 = coord26.report(report2, sig2)
n_ledger_after_second = len(ledger26)
ok26 = resp2.duplicates == len(records1) and n_ledger_after_second == n_ledger_after_first
record("AGT-026", "PASS" if ok26 else "FAIL", f"first_accepted_through={resp1.accepted_through} ledger_after_first={n_ledger_after_first} second_duplicates={resp2.duplicates} ledger_after_second={n_ledger_after_second}")

# AGT-027: gap in sequence recorded, records still kept
reg27, agent27, clock27 = mk_agent("z27")
ledger27 = Ledger()
coord27 = Coordinator(reg27, ledger=ledger27, clock=clock27)
r1 = mk_report(agent27.agent_id, [rec(i) for i in range(11)])  # 0..10
coord27.report(r1, sign(reg27, agent27.agent_id, r1))
r2 = mk_report(agent27.agent_id, [rec(15)])  # gap: expected 11, missing 4
resp27 = coord27.report(r2, sign(reg27, agent27.agent_id, r2))
ok27 = len(resp27.rejected) == 1 and resp27.rejected[0][0] == 15 and "4" in resp27.rejected[0][1] and len(ledger27) == 12
record("AGT-027", "PASS" if ok27 else "FAIL", f"rejected={resp27.rejected} ledger_len={len(ledger27)} (expect 12: 11 from first report + the sequence-15 record kept despite the gap)")

# AGT-028: first report from a fresh agent (starting at 0) not treated as a gap
reg28, agent28, clock28 = mk_agent("z28")
ledger28 = Ledger()
coord28 = Coordinator(reg28, ledger=ledger28, clock=clock28)
r28 = mk_report(agent28.agent_id, [rec(0)])
resp28 = coord28.report(r28, sign(reg28, agent28.agent_id, r28))
ok28 = len(resp28.rejected) == 0 and resp28.accepted_through == 0
record("AGT-028", "PASS" if ok28 else "FAIL", f"rejected={resp28.rejected} accepted_through={resp28.accepted_through}")

# AGT-029: out-of-order records within one report (12, 11, 13)
reg29, agent29, clock29 = mk_agent("z29")
ledger29 = Ledger()
coord29 = Coordinator(reg29, ledger=ledger29, clock=clock29)
r29a = mk_report(agent29.agent_id, [rec(i) for i in range(11)])  # 0..10, highest=10
coord29.report(r29a, sign(reg29, agent29.agent_id, r29a))
r29b = mk_report(agent29.agent_id, [rec(12), rec(11), rec(13)])
resp29 = coord29.report(r29b, sign(reg29, agent29.agent_id, r29b))
# per catalogue Why: loop advances 'highest' as it goes -- 12 (gap, highest->12), then 11
# (11 <= highest=12 -> treated as DUPLICATE and dropped), then 13 (13==highest+1==13, clean, highest->13)
ok29 = (
    len(resp29.rejected) == 1 and resp29.rejected[0][0] == 12
    and resp29.duplicates == 1
    and resp29.accepted_through == 13
)
record(
    "AGT-029",
    "PASS" if ok29 else "FAIL",
    f"rejected={resp29.rejected} duplicates={resp29.duplicates} accepted_through={resp29.accepted_through} -- "
    f"confirms the catalogue's own predicted mechanism: 11-after-12 is silently treated as a duplicate and "
    f"dropped rather than accepted, which the catalogue itself flags as the (documented, deterministic but "
    f"transport-order-dependent) outcome to confirm, not a surprise",
)

# AGT-030: receipt acknowledges by sequence, not by count -- a receipt for seq 5 arriving after 2 more spooled
spool30 = Spool(capacity=1000)
for i in range(10):
    spool30.add(rec(0))  # sequence is assigned internally by Spool, ignore rec()'s own .sequence
# after adding 10, sequences 0..9 pending
# simulate: report sent covering through seq 5 conceptually, but meanwhile 2 MORE were spooled (10, 11)
spool30.add(rec(0))
spool30.add(rec(0))
before_ack = len(spool30)
removed = spool30.acknowledge(5)
after_ack = len(spool30)
remaining_sequences = [r.sequence for r in spool30]
ok30 = removed == 6 and all(s > 5 for s in remaining_sequences) and 6 in remaining_sequences and 11 in remaining_sequences
record("AGT-030", "PASS" if ok30 else "FAIL", f"before={before_ack} removed={removed} after={after_ack} remaining_sequences={remaining_sequences}")

print("done agt 026-030")

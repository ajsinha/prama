import sys, os, inspect
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama_agent.runner import Agent
from prama.agent.identity import AgentRegistry, AgentState
from prama.agent.coordinator import Coordinator, fleet_health
from prama.agent.residency import ResidencyPolicy, SampleDisposition
from prama.agent.protocol import Receipt, Refusal
from prama.agent.spool import Spool
from prama.core.clock import ManualClock
from prama.evidence.ledger import Ledger
from datetime import datetime, timedelta, UTC

def mk_agent_runner(spool=None):
    return Agent("agent:x", b"k"*32, executor=lambda q: [{"violating_rows": 0.0}], residency=ResidencyPolicy(zone="z", samples=SampleDisposition.WITHHOLD, investigate_at="x"), spool=spool)

# AGT-065: a permanent refusal stops the agent
agent65 = mk_agent_runner()
result65 = agent65.apply(Refusal(reason="revoked", permanent=True))
ok65 = result65 is False
record("AGT-065", "PASS" if ok65 else "FAIL", f"apply_returned={result65}")

# AGT-066: a non-permanent refusal does not stop the agent; spool untouched
spool66 = Spool(capacity=1000)
agent66 = mk_agent_runner(spool=spool66)
for _ in range(5):
    agent66.spool.add(agent66._error_record(agent66.hello()[0].__class__ and __import__("prama.agent.protocol", fromlist=["Assignment"]).Assignment(plan_id="p", dataset="d", binding="b", engine="e", metric_query="q"), agent66._clock.now(), "x"))
n_pending_before = len(agent66.spool)
result66 = agent66.apply(Refusal(reason="busy", permanent=False))
n_pending_after = len(agent66.spool)
ok66 = result66 is True and n_pending_after == n_pending_before
record("AGT-066", "PASS" if ok66 else "FAIL", f"apply_returned={result66} pending_before={n_pending_before} pending_after={n_pending_after}")

# AGT-067: a receipt for work never sent (accepted_through way beyond highest sequence) does not
# remove more than exists, and the discrepancy is at least observable (no upper bound check exists,
# per code review of Spool.acknowledge -- confirming this by direct execution as flagged by the orchestrator)
spool67 = Spool(capacity=1000)
agent67 = mk_agent_runner(spool=spool67)
from prama.agent.protocol import Assignment as Asg67
for _ in range(6):
    agent67.spool.add(agent67._error_record(Asg67(plan_id="p", dataset="d", binding="b", engine="e", metric_query="q"), agent67._clock.now(), "x"))
# highest sequence spooled is 5 (0..5)
highest67 = max(r.sequence for r in agent67.spool)
receipt67 = Receipt(accepted_through=500)  # forged/bogus: far beyond anything ever sent
before67 = len(agent67.spool)
agent67.apply(receipt67)
after67 = len(agent67.spool)
ok67 = after67 == 0  # this is what ACTUALLY happens: acknowledge(500) drops every record whose sequence<=500, i.e. everything
record(
    "AGT-067",
    "PASS" if not (after67 == 0 and before67 > 0) else "FAIL",
    f"highest_sequence_ever_spooled={highest67} spool_len_before={before67} spool_len_after_bogus_receipt(500)={after67} -- "
    f"Spool.acknowledge(through_sequence) is `[r for r in self._pending if r.sequence > through_sequence]` "
    f"with NO upper-bound check against the highest sequence actually spooled/sent. A receipt claiming "
    f"accepted_through=500 when only sequences 0..{highest67} were ever spooled empties the ENTIRE spool "
    f"silently, with no error, no log warning, nothing noticed anywhere in Agent.apply or Spool.acknowledge. "
    f"This is ONE of the two items the orchestrator explicitly flagged as still needing confirmation by "
    f"execution (Spool.acknowledge being unbounded) -- confirmed: a single forged/bogus receipt erases an "
    f"agent's entire backlog with no detection, exactly as the catalogue's Why predicts.",
)

# AGT-068: a receipt with accepted_through=-1 (the default) clears nothing and forgets no gaps
spool68 = Spool(capacity=5)
agent68 = mk_agent_runner(spool=spool68)
for _ in range(10):  # force overflow -> a gap
    agent68.spool.add(agent68._error_record(Asg67(plan_id="p", dataset="d", binding="b", engine="e", metric_query="q"), agent68._clock.now(), "x"))
gaps_before68 = len(agent68.spool.gaps)
pending_before68 = len(agent68.spool)
default_receipt = Receipt()  # accepted_through=-1 by default
agent68.apply(default_receipt)
ok68 = len(agent68.spool) == pending_before68 and len(agent68.spool.gaps) == gaps_before68
record("AGT-068", "PASS" if ok68 else "FAIL", f"pending_before={pending_before68} pending_after={len(agent68.spool)} gaps_before={gaps_before68} gaps_after={len(agent68.spool.gaps)}")

# AGT-069: an agent whose clock is wrong -- duration_ms never negative; enrolment judged on control plane's clock
clock_control_plane = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg69 = AgentRegistry(clock=clock_control_plane)
token69, secret69 = reg69.issue_token("z69")
# the AGENT's own clock is a day AHEAD -- but enrol() takes no clock argument from the agent at all;
# the registry's own clock decides validity, so the agent cannot influence it regardless
agent_ahead = Agent("agent:ahead", b"k"*32, executor=lambda q: [{"violating_rows": 0.0}], residency=ResidencyPolicy(zone="z", samples=SampleDisposition.WITHHOLD, investigate_at="x"), clock=ManualClock(datetime(2026, 1, 2, tzinfo=UTC)))
agent_behind = Agent("agent:behind", b"k"*32, executor=lambda q: [{"violating_rows": 0.0}], residency=ResidencyPolicy(zone="z", samples=SampleDisposition.WITHHOLD, investigate_at="x"), clock=ManualClock(datetime(2025, 12, 31, tzinfo=UTC)))
from prama.agent.protocol import Assignment as Asg69
outcome_ahead = agent_ahead.run(Asg69(plan_id="p", dataset="d", binding="b", engine="e", metric_query="q", plan={"threshold": {"metric": "violating_rows", "value": 0.0}}, metric_names=("violating_rows",)))
outcome_behind = agent_behind.run(Asg69(plan_id="p", dataset="d", binding="b", engine="e", metric_query="q", plan={"threshold": {"metric": "violating_rows", "value": 0.0}}, metric_names=("violating_rows",)))
duration_ahead = outcome_ahead.record.duration_ms
duration_behind = outcome_behind.record.duration_ms
# enrolment: the token issued by the control plane's clock; agent's clock plays no role in enrol() at all
enrol_sig = inspect.signature(AgentRegistry.enrol)
ok69 = duration_ahead >= 0 and duration_behind >= 0 and "clock" not in enrol_sig.parameters
record("AGT-069", "PASS" if ok69 else "FAIL", f"duration_ahead_ms={duration_ahead} duration_behind_ms={duration_behind} enrol_signature_params={list(enrol_sig.parameters)} (agent's own clock cannot enter enrol() at all, since it is called on the AgentRegistry with only token_secret/name/version -- confirming the guarantee holds structurally, not just by convention)")

# AGT-070: fleet_health reports silence rather than inferring it
clock70 = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg70 = AgentRegistry(clock=clock70)
agents70 = []
for i in range(3):
    t, s = reg70.issue_token(f"zone{i}")
    a, k = reg70.enrol(s.reveal(), name=f"agent{i}")
    agents70.append(a)
# advance the clock so agent 0 hasn't been "seen" in 20 minutes (last_seen_at was set at enrol time)
clock70.advance(20 * 60)
# "touch" agents 1 and 2 so they look recently active
reg70.seen(agents70[1].agent_id)
reg70.seen(agents70[2].agent_id)
health70 = fleet_health(reg70, after_minutes=15)
silent_ids = [a["agent_id"] for a in health70["silent"]]
ok70 = health70["agents"] == 3 and agents70[0].agent_id in silent_ids and agents70[1].agent_id not in silent_ids and agents70[2].agent_id not in silent_ids and "last_seen_at" in health70["silent"][0]
record("AGT-070", "PASS" if ok70 else "FAIL", f"health={health70}")

# AGT-071: an agent never seen counts as stale
clock71 = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg71 = AgentRegistry(clock=clock71)
from prama.agent.identity import AgentIdentity
never_seen = AgentIdentity(agent_id="agent:never", zone="z", key_digest="x"*64, last_seen_at=None)
ok71 = never_seen.is_stale(clock71.now()) is True
record("AGT-071", "PASS" if ok71 else "FAIL", f"is_stale={never_seen.is_stale(clock71.now())}")

# AGT-072: a suspended or revoked agent is not reported as silent
clock72 = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg72 = AgentRegistry(clock=clock72)
t72, s72 = reg72.issue_token("z72")
agent72, k72 = reg72.enrol(s72.reveal())
reg72.revoke(agent72.agent_id)
clock72.advance(24 * 60 * 60)  # a day of silence
health72 = fleet_health(reg72, after_minutes=15)
silent_ids72 = [a["agent_id"] for a in health72["silent"]]
ok72 = agent72.agent_id not in silent_ids72 and health72["revoked"] == 1
record("AGT-072", "PASS" if ok72 else "FAIL", f"silent_ids={silent_ids72} revoked_count={health72['revoked']}")

# AGT-073: the coordinator's ledger is NOT replaced when it is empty
empty_ledger = Ledger()
coord73 = Coordinator(AgentRegistry(clock=ManualClock(datetime(2026,1,1,tzinfo=UTC))), ledger=empty_ledger)
ok73 = coord73.ledger is empty_ledger
record("AGT-073", "PASS" if ok73 else "FAIL", f"same_instance={coord73.ledger is empty_ledger}")

# AGT-074: the agent's spool is NOT replaced when it is empty
empty_spool = Spool(capacity=100)
agent74 = Agent("agent:74", b"k"*32, executor=lambda q: [{"violating_rows": 0.0}], residency=ResidencyPolicy(zone="z", samples=SampleDisposition.WITHHOLD, investigate_at="x"), spool=empty_spool)
ok74 = agent74.spool is empty_spool
record("AGT-074", "PASS" if ok74 else "FAIL", f"same_instance={agent74.spool is empty_spool}")

# AGT-075: the control plane never initiates -- only hello and report on Coordinator; protocol is agent-initiated
import prama.agent.protocol as proto_mod
coord_public_methods = [m for m in dir(Coordinator) if not m.startswith("_") and callable(getattr(Coordinator, m))]
coord_public_methods = [m for m in coord_public_methods if m not in ("enqueue", "unassignable", "ledger")]  # these are the control plane's OWN admin surface (loading work in, reading state), not messages TO an agent
ok75 = set(coord_public_methods) == {"hello", "report"}
record("AGT-075", "PASS" if ok75 else "FAIL", f"coordinator_conversation_methods={coord_public_methods} (excluding enqueue/unassignable/ledger which are the control plane's own admin surface for loading work in and reading state, not messages sent TO an agent)")

# AGT-076: poll interval declared and honoured
reg76 = AgentRegistry(clock=ManualClock(datetime(2026,1,1,tzinfo=UTC)))
coord76 = Coordinator(reg76, poll_seconds=60)
t76, s76 = reg76.issue_token("z76")
agent76, k76 = reg76.enrol(s76.reveal())
from prama.agent.protocol import Hello
from prama.agent.capability import AgentCapabilities
hello76 = Hello(agent_id=agent76.agent_id, capabilities=AgentCapabilities())
sig76 = reg76.sign_as(agent76.agent_id, hello76.signable())
resp76 = coord76.hello(hello76, sig76)
ok76 = isinstance(resp76, Receipt) and resp76.poll_after_seconds == 60
record("AGT-076", "PASS" if ok76 else "FAIL", f"poll_after_seconds={resp76.poll_after_seconds if isinstance(resp76, Receipt) else resp76}")

print("done agt 065-076")

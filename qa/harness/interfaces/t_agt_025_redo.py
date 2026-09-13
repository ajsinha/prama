import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.agent.identity import AgentRegistry
from prama.agent.coordinator import Coordinator
from prama.agent.protocol import Hello, Assignment, Receipt
from prama.agent.capability import AgentCapabilities
from prama.core.clock import ManualClock
from prama.ir.model import ControlPlan, Scope, Metric, Threshold, MetricAggregate, Expr
from datetime import datetime, UTC

clock = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg = AgentRegistry(clock=clock)
token, secret = reg.issue_token("zH")
agent, key = reg.enrol(secret.reveal())
coord = Coordinator(reg, clock=clock)

filt = Expr.operation("=", Expr.column("a"), Expr.literal(1))
plan = ControlPlan(
    scope=Scope(dataset="dsH", binding="b1", filter=filt),
    metrics=(Metric(name="violating_rows", aggregate=MetricAggregate.COUNT),),
    threshold=Threshold(metric="violating_rows", value=0.0),
)
asg = Assignment(plan_id=plan.plan_id, dataset="dsH", binding="b1", engine="sqlite", metric_query="SELECT 1", plan={"threshold": {"metric": "violating_rows", "value": 0.0}})
coord.enqueue("zH", plan, asg)

hello = Hello(agent_id=agent.agent_id, capabilities=AgentCapabilities(pushdown=("nope",)), free_slots=5)
sig = reg.sign_as(agent.agent_id, hello.signable())

receipt_lengths = []
persistent_lengths = []
for i in range(1000):
    resp = coord.hello(hello, sig)
    receipt_lengths.append(len(resp.unassignable) if isinstance(resp, Receipt) else -1)
    persistent_lengths.append(len(coord.unassignable("zH")))

ok25 = receipt_lengths[0] == 1 and all(x == 1 for x in receipt_lengths[1:]) if False else None
# What actually happens, documented plainly:
record(
    "AGT-025",
    "FAIL",
    f"receipt.unassignable length across 1000 polls: poll1={receipt_lengths[0]} poll2={receipt_lengths[1]} "
    f"poll1000={receipt_lengths[-1]}. coordinator.unassignable('zH') (the PERSISTENT, accumulated list held "
    f"on ZoneWork) across the same polls: poll1={persistent_lengths[0]} poll1000={persistent_lengths[-1]}. "
    f"Actual behavior: because _assign() removes an unassignable plan from work.queue on the poll that "
    f"discovers it (see AGT-021/024) and then short-circuits with 'if work is None or not work.queue: "
    f"return [], []' on every SUBSEQUENT poll once the queue is empty, the Receipt's own 'unassignable' "
    f"field reports the hole exactly ONCE (poll 1) and then reports NOTHING (empty tuple) forever after -- "
    f"the operator sees the coverage hole on the first poll and then it silently vanishes from every "
    f"receipt, even though coord.unassignable('zH') still holds it internally and forever. This is a "
    f"DIFFERENT defect shape than the catalogue's own Why anticipates ('work.unassignable.append runs on "
    f"every poll and the whole list is returned each time', implying UNBOUNDED GROWTH) -- that growth "
    f"does not occur here because AGT-024's queue-draining bug empties the queue after one poll, which "
    f"masks the growth but replaces it with a worse failure: the coverage hole silently disappears from "
    f"what the agent's operator actually sees (the Receipt) after the very first poll, while the internal "
    f"state (coord.unassignable()) never reflects that anything changed on the queue side either. Neither "
    f"the catalogue's literal Expected ('reported once, not returned in every receipt') nor its literal "
    f"mechanism (Why) holds: what actually happens is reported once and then never again, which satisfies "
    f"'not returned in every receipt' by accident of a different bug rather than by design.",
)
print("done agt025 redo", receipt_lengths[:3], persistent_lengths[:3], receipt_lengths[-1], persistent_lengths[-1])

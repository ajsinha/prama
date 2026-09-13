import sys, os, json, dataclasses as dc
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.agent.identity import AgentRegistry
from prama.agent.coordinator import Coordinator
from prama.agent.protocol import Hello, Report, Assignment, Receipt
from prama.agent.capability import AgentCapabilities, fits
from prama.core.clock import ManualClock
from prama.evidence.record import EvidenceRecord
from prama.evidence.ledger import Ledger
from prama.ir.model import ControlPlan, Scope, Metric, Threshold, MetricAggregate, Expr
from datetime import datetime, UTC

def mk_registry_agent(zone, clock=None):
    clock = clock or ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
    reg = AgentRegistry(clock=clock)
    token, secret = reg.issue_token(zone)
    agent, key = reg.enrol(secret.reveal())
    return reg, agent, clock

def mk_hello(agent_id, capabilities=None, pending=0, free_slots=1, version=""):
    return Hello(agent_id=agent_id, version=version, capabilities=capabilities or AgentCapabilities(), pending_findings=pending, free_slots=free_slots)

def sign_reg(reg, agent_id, message):
    return reg.sign_as(agent_id, message.signable())

def mk_plan(dataset="ds1", salt="", pushdown_req=None):
    detail = {}
    return ControlPlan(
        scope=Scope(dataset=dataset, binding="b1"),
        metrics=(Metric(name="violating_rows", aggregate=MetricAggregate.COUNT),),
        threshold=Threshold(metric="violating_rows", value=0.0),
        because=salt,
    )

def mk_assignment(plan, engine="sqlite"):
    return Assignment(plan_id=plan.plan_id, dataset=plan.scope.dataset, binding=plan.scope.binding, engine=engine, metric_query="SELECT 1", plan={"threshold": {"metric": "violating_rows", "value": 0.0}})

# AGT-021: work an agent cannot run is reported in unassignable, not silently skipped
reg21, agent21, clock21 = mk_registry_agent("zF")
coord21 = Coordinator(reg21, clock=clock21)
plan21 = mk_plan("dsF", salt="needs-pushdown")
asg21 = mk_assignment(plan21)
# force a plan that requires a pushdown capability the agent lacks: give the agent SOME pushdown
# (non-empty) so the 'declares nothing = can do anything' default doesn't mask this check (see AGT-023)
def mk_filter():
    return Expr.operation("=", Expr.column("a"), Expr.literal(1))

plan21b = ControlPlan(
    scope=Scope(dataset="dsF", binding="b1", filter=mk_filter()),
    metrics=(Metric(name="violating_rows", aggregate=MetricAggregate.COUNT),),
    threshold=Threshold(metric="violating_rows", value=0.0),
)
asg21b = mk_assignment(plan21b)
coord21.enqueue("zF", plan21b, asg21b)
hello21 = mk_hello(agent21.agent_id, capabilities=AgentCapabilities(pushdown=("something-else",)), free_slots=5)
sig21 = sign_reg(reg21, agent21.agent_id, hello21)
resp21 = coord21.hello(hello21, sig21)
ok21 = isinstance(resp21, Receipt) and len(resp21.assignments) == 0 and len(resp21.unassignable) == 1 and "reasons" in resp21.unassignable[0]
record("AGT-021", "PASS" if ok21 else "FAIL", f"assignments={resp21.assignments if isinstance(resp21,Receipt) else resp21} unassignable={resp21.unassignable if isinstance(resp21,Receipt) else 'N/A'}")

# AGT-022: fits collects every reason, not the first
plan22 = mk_plan("ds22")
caps22 = AgentCapabilities(ir_versions=("0.1",), engines=("bigquery",), pushdown=("something",), datasets=("other-dataset",))
fitness22 = fits(plan22, caps22, engine="sqlite")
ok22 = len(fitness22.reasons) >= 2  # ir_version mismatch + engine mismatch + (dataset confinement); pushdown only checked if plan requires something
record("AGT-022", "PASS" if ok22 else "FAIL", f"assignable={fitness22.assignable} reasons={fitness22.reasons} remedy={fitness22.remedy!r}")

# AGT-023: default AgentCapabilities (declares nothing) is NOT refused for any plan
default_caps = AgentCapabilities()
plan23 = mk_plan("ds23")
fitness23 = fits(plan23, default_caps, engine="postgres")
ok23 = fitness23.assignable is True
record(
    "AGT-023",
    "PASS" if ok23 else "FAIL",
    f"assignable={fitness23.assignable} reasons={fitness23.reasons} -- confirms the catalogue's own stated "
    f"Expected/Why: AgentCapabilities.from_dict({{}}) (the default) means 'can do anything' because the "
    f"engines/pushdown checks are guarded by 'if capabilities.engines/pushdown is non-empty' -- confirmed "
    f"exactly as the catalogue states: 'the permissive default is the opposite of the safe direction'. "
    f"This is one of the two items the orchestrator flagged as still needing execution-based confirmation.",
)

# AGT-024: an unassignable plan leaves the queue and is not lost when a capable agent later asks
reg24, incapable_agent, clock24 = mk_registry_agent("zG")
capable_reg_token, capable_secret = reg24.issue_token("zG")
capable_agent, capable_key = reg24.enrol(capable_secret.reveal(), name="capable")
coord24 = Coordinator(reg24, clock=clock24)
plan24 = mk_plan("dsG", salt="needs-x")
plan24_filtered = ControlPlan(
    scope=Scope(dataset="dsG", binding="b1", filter=mk_filter()),
    metrics=(Metric(name="violating_rows", aggregate=MetricAggregate.COUNT),),
    threshold=Threshold(metric="violating_rows", value=0.0),
)
asg24 = mk_assignment(plan24_filtered)
coord24.enqueue("zG", plan24_filtered, asg24)
hello_incapable = mk_hello(incapable_agent.agent_id, capabilities=AgentCapabilities(pushdown=("nope",)), free_slots=5)
sig_incapable = sign_reg(reg24, incapable_agent.agent_id, hello_incapable)
resp_incapable = coord24.hello(hello_incapable, sig_incapable)
hello_capable = mk_hello(capable_agent.agent_id, capabilities=AgentCapabilities(pushdown=("pushdown.filter",)), free_slots=5)
sig_capable = sign_reg(reg24, capable_agent.agent_id, hello_capable)
resp_capable = coord24.hello(hello_capable, sig_capable)
capable_got_it = isinstance(resp_capable, Receipt) and len(resp_capable.assignments) == 1
ok24 = capable_got_it
record(
    "AGT-024",
    "PASS" if ok24 else "FAIL",
    f"incapable_hello_assignments={resp_incapable.assignments if isinstance(resp_incapable,Receipt) else resp_incapable} "
    f"unassignable_after_incapable={resp_incapable.unassignable if isinstance(resp_incapable,Receipt) else 'N/A'} "
    f"capable_hello_assignments={resp_capable.assignments if isinstance(resp_capable,Receipt) else resp_capable} "
    f"(expected per catalogue: capable agent SHOULD receive it, but code review shows work.queue = remaining "
    f"in _assign drops the plan into ONLY the unassignable list and never back into queue -- confirming "
    f"whether the capable agent actually still gets it)",
)

# AGT-025: unassignable accumulates without bound across polls
reg25, agent25, clock25 = mk_registry_agent("zH")
coord25 = Coordinator(reg25, clock=clock25)
plan25_filtered = ControlPlan(
    scope=Scope(dataset="dsH", binding="b1", filter=mk_filter()),
    metrics=(Metric(name="violating_rows", aggregate=MetricAggregate.COUNT),),
    threshold=Threshold(metric="violating_rows", value=0.0),
)
asg25 = mk_assignment(plan25_filtered)
coord25.enqueue("zH", plan25_filtered, asg25)
hello25 = mk_hello(agent25.agent_id, capabilities=AgentCapabilities(pushdown=("nope",)), free_slots=5)
sig25 = sign_reg(reg25, agent25.agent_id, hello25)
lengths = []
for _ in range(1000):
    resp25 = coord25.hello(hello25, sig25)
    lengths.append(len(resp25.unassignable) if isinstance(resp25, Receipt) else -1)
ok25 = lengths[-1] == 1  # per catalogue Expected: "reported once, not a thousand entries" -- but Why says work.unassignable.append runs on EVERY poll
record(
    "AGT-025",
    "PASS" if ok25 else "FAIL",
    f"length_after_1_poll={lengths[0]} length_after_1000_polls={lengths[-1]} (Expected per catalogue: same "
    f"hole reported ONCE; Why states plainly 'work.unassignable.append runs on every poll and the whole "
    f"list is returned each time' -- confirming which actually happens)",
)

print("done agt 021-025")

import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.agent.identity import AgentRegistry, AgentState, sign_payload
from prama.agent.coordinator import Coordinator
from prama.agent.protocol import Hello, Report, Assignment, Refusal, Receipt
from prama.agent.capability import AgentCapabilities
from prama.core.clock import ManualClock
from prama.evidence.record import EvidenceRecord, GENESIS
from prama.evidence.ledger import Ledger
from prama.ir.model import ControlPlan, Scope, Metric, Threshold
from datetime import datetime, UTC

def mk_registry_agent(zone="reporting", clock=None):
    clock = clock or ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
    reg = AgentRegistry(clock=clock)
    token, secret = reg.issue_token(zone)
    agent, key = reg.enrol(secret.reveal())
    return reg, agent, clock

def mk_hello(agent_id, capabilities=None, pending=0, free_slots=1, version=""):
    return Hello(agent_id=agent_id, version=version, capabilities=capabilities or AgentCapabilities(), pending_findings=pending, free_slots=free_slots)

def sign_reg(reg, agent_id, message):
    return reg.sign_as(agent_id, message.signable())

def mk_plan(dataset="ds1", plan_id_salt=""):
    return ControlPlan(
        scope=Scope(dataset=dataset, binding="b1"),
        metrics=(Metric(name="violating_rows", aggregate=__import__("prama.ir.model", fromlist=["MetricAggregate"]).MetricAggregate.COUNT),),
        threshold=Threshold(metric="violating_rows", value=0.0),
        because=plan_id_salt,
    )

def mk_assignment(plan, engine="sqlite"):
    return Assignment(plan_id=plan.plan_id, dataset=plan.scope.dataset, binding=plan.scope.binding, engine=engine, metric_query="SELECT 1", plan={"threshold": {"metric": "violating_rows", "value": 0.0}})

# AGT-013: suspended agent's findings are held, not rejected (non-permanent refusal)
reg13, agent13, clock13 = mk_registry_agent("zA")
coord13 = Coordinator(reg13, clock=clock13)
reg13.suspend(agent13.agent_id)
report13 = Report(agent_id=agent13.agent_id, records=(EvidenceRecord(sequence=0, plan_id="p1", dataset="ds1"),))
sig13 = sign_reg(reg13, agent13.agent_id, report13)  # will be "no key" essentially since verify() checks state first
resp13 = coord13.report(report13, sig13)
ok13 = isinstance(resp13, Refusal) and resp13.permanent is False and "suspended" in resp13.reason
record("AGT-013", "PASS" if ok13 else "FAIL", f"response={resp13}")

# AGT-014: suspended agent refused before signature check (correct AND wrong sig both refused identically)
reg14, agent14, clock14 = mk_registry_agent("zB")
coord14 = Coordinator(reg14, clock=clock14)
report14 = Report(agent_id=agent14.agent_id, records=())
correct_sig = sign_reg(reg14, agent14.agent_id, report14)
reg14.suspend(agent14.agent_id)
resp14_correct = coord14.report(report14, correct_sig)
resp14_wrong = coord14.report(report14, "totally-wrong-signature")
ok14 = (isinstance(resp14_correct, Refusal) and isinstance(resp14_wrong, Refusal)
        and resp14_correct.reason == resp14_wrong.reason == "this agent is suspended")
record("AGT-014", "PASS" if ok14 else "FAIL", f"correct_sig_resp={resp14_correct} wrong_sig_resp={resp14_wrong}")

# AGT-015: unknown agent refused with enrolment remedy
reg15 = AgentRegistry(clock=ManualClock(datetime(2026,1,1,tzinfo=UTC)))
coord15 = Coordinator(reg15)
hello15 = mk_hello("agent:invented-nonexistent")
resp15 = coord15.hello(hello15, "whatever-signature")
ok15 = isinstance(resp15, Refusal) and resp15.permanent is True and "does not know" in resp15.reason and "Enrol" in resp15.remedy
record("AGT-015", "PASS" if ok15 else "FAIL", f"response={resp15}")

# AGT-016: tampered payload fails verification, nothing appended to ledger
reg16, agent16, clock16 = mk_registry_agent("zC")
ledger16 = Ledger()
coord16 = Coordinator(reg16, ledger=ledger16, clock=clock16)
rec16 = EvidenceRecord(sequence=0, plan_id="p16", dataset="ds16", metrics={"violating_rows": 5.0})
report16 = Report(agent_id=agent16.agent_id, records=(rec16,))
sig16 = sign_reg(reg16, agent16.agent_id, report16)
tampered_rec = __import__("dataclasses").replace(rec16, metrics={"violating_rows": 0.0})  # altered metric, same signature
tampered_report = Report(agent_id=agent16.agent_id, records=(tampered_rec,))
resp16 = coord16.report(tampered_report, sig16)  # signature was computed over the ORIGINAL, now sent with tampered body
ok16 = isinstance(resp16, Refusal) and "not signed by that agent" in resp16.reason and len(ledger16) == 0
record("AGT-016", "PASS" if ok16 else "FAIL", f"response={resp16} ledger_len={len(ledger16)}")

# AGT-017: every field in signable() matters -- change one field at a time on Hello and Report
import dataclasses as dc
hello_base = mk_hello(agent16.agent_id, capabilities=AgentCapabilities(engines=("sqlite",)), pending=3, free_slots=2, version="1.0")
sig_hello_base = sign_reg(reg16, agent16.agent_id, hello_base)
field_changes_hello = {
    "version": dc.replace(hello_base, version="9.9"),
    "pending_findings": dc.replace(hello_base, pending_findings=999),
    "free_slots": dc.replace(hello_base, free_slots=999),
    "capabilities": dc.replace(hello_base, capabilities=AgentCapabilities(engines=("postgres",))),
}
bad17 = {}
for label, altered in field_changes_hello.items():
    if reg16.verify(agent16.agent_id, altered.signable(), sig_hello_base):
        bad17[f"hello.{label}"] = "signature STILL verified after altering this field"

report_base = Report(agent_id=agent16.agent_id, records=(rec16,), gaps=(), residency={"zone": "zC", "samples": "withhold"})
sig_report_base = sign_reg(reg16, agent16.agent_id, report_base)
field_changes_report = {
    "records": dc.replace(report_base, records=(dc.replace(rec16, metrics={"violating_rows": 1.0}),)),
    "residency": dc.replace(report_base, residency={"zone": "zC", "samples": "send"}),
}
for label, altered in field_changes_report.items():
    if reg16.verify(agent16.agent_id, altered.signable(), sig_report_base):
        bad17[f"report.{label}"] = "signature STILL verified after altering this field"
ok17 = not bad17
record("AGT-017", "PASS" if ok17 else "FAIL", f"bad={bad17}")

# AGT-019: work assigned from enrolled zone, never from the request
reg19, agent19, clock19 = mk_registry_agent("reporting")
coord19 = Coordinator(reg19, clock=clock19)
plan_trading = mk_plan("trading_positions")
asg_trading = mk_assignment(plan_trading)
coord19.enqueue("trading", plan_trading, asg_trading)
hello19 = mk_hello(agent19.agent_id, capabilities=AgentCapabilities(datasets=("trading_positions",)), free_slots=5)
sig19 = sign_reg(reg19, agent19.agent_id, hello19)
resp19 = coord19.hello(hello19, sig19)
ok19 = isinstance(resp19, Receipt) and len(resp19.assignments) == 0
record("AGT-019", "PASS" if ok19 else "FAIL", f"assignments={resp19.assignments if isinstance(resp19, Receipt) else resp19}")

# AGT-020: free_slots bounded by declared concurrency
reg20, agent20, clock20 = mk_registry_agent("zD")
coord20 = Coordinator(reg20, clock=clock20)
plans20 = []
for i in range(10):
    p = mk_plan("dsD", plan_id_salt=f"salt{i}")
    a = mk_assignment(p)
    coord20.enqueue("zD", p, a)
    plans20.append(p)
hello20_over = mk_hello(agent20.agent_id, capabilities=AgentCapabilities(max_concurrency=2), free_slots=1000)
sig20a = sign_reg(reg20, agent20.agent_id, hello20_over)
resp20a = coord20.hello(hello20_over, sig20a)
n_assigned_over = len(resp20a.assignments) if isinstance(resp20a, Receipt) else -1

reg20b, agent20b, clock20b = mk_registry_agent("zE", clock=ManualClock(datetime(2026,1,1,tzinfo=UTC)))
coord20b = Coordinator(reg20b, clock=clock20b)
for i in range(10):
    p = mk_plan("dsE", plan_id_salt=f"salt2-{i}")
    a = mk_assignment(p)
    coord20b.enqueue("zE", p, a)
hello20_neg = mk_hello(agent20b.agent_id, capabilities=AgentCapabilities(max_concurrency=2), free_slots=-5)
sig20b = sign_reg(reg20b, agent20b.agent_id, hello20_neg)
resp20b = coord20b.hello(hello20_neg, sig20b)
n_assigned_neg = len(resp20b.assignments) if isinstance(resp20b, Receipt) else -1
ok20 = n_assigned_over == 2 and n_assigned_neg == 0
record("AGT-020", "PASS" if ok20 else "FAIL", f"free_slots=1000,max_concurrency=2 -> assigned={n_assigned_over} (expect 2); free_slots=-5,max_concurrency=2 -> assigned={n_assigned_neg} (expect 0)")

print("done agt 013-020")

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.agent.runner import Agent
from prama.agent.residency import ResidencyPolicy, SampleDisposition
from prama.agent.protocol import Assignment
from prama.backend.execute import judge as backend_judge
from prama.ir.model import ControlPlan, Scope, Metric, Threshold, MetricAggregate

plan58 = ControlPlan(scope=Scope(dataset="ds58", binding="b1"), metrics=(Metric(name="violating_rows", aggregate=MetricAggregate.COUNT),), threshold=Threshold(metric="violating_rows", value=2.0))
metrics58 = {"violating_rows": 5.0, "scanned_rows": 100.0}
direct_verdict = backend_judge(plan58, metrics58).verdict

agent58 = Agent("agent:58", b"k"*32, executor=lambda q: [metrics58], residency=ResidencyPolicy(zone="z58", samples=SampleDisposition.WITHHOLD, investigate_at="x"))
asg58 = Assignment(
    plan_id="p58", dataset="ds58", binding="b1", engine="sqlite", metric_query="Q",
    metric_names=("violating_rows", "scanned_rows"),  # explicitly naming the metrics to extract
    plan={"threshold": {"metric": "violating_rows", "value": 2.0}},
)
outcome58 = agent58.run(asg58)
ok58 = outcome58.record.verdict == direct_verdict.value
record("AGT-058", "PASS" if ok58 else "FAIL", f"direct_judge_verdict={direct_verdict.value} agent_verdict={outcome58.record.verdict} agent_metrics={outcome58.record.metrics}")
print("done agt058 redo")

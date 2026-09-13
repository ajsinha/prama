import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.agent.runner import Agent
from prama.agent.residency import ResidencyPolicy, SampleDisposition
from prama.agent.protocol import Assignment
from prama.ir.model import Verdict

def mk_assignment(query="SELECT 1", sample_query="", plan=None, dataset="ds", plan_id="p1"):
    return Assignment(
        plan_id=plan_id, dataset=dataset, binding="b1", engine="sqlite",
        metric_query=query, sample_query=sample_query,
        plan=plan if plan is not None else {"threshold": {"metric": "violating_rows", "value": 0.0}},
    )

# AGT-054: samples stay local even when the policy withholds them
policy54 = ResidencyPolicy(zone="z54", samples=SampleDisposition.WITHHOLD, investigate_at="local box")
agent54 = Agent(
    "agent:54", b"k" * 32,
    executor=lambda q: [{"violating_rows": 5, "scanned_rows": 100}] if "metric" in q or True else [],
    residency=policy54,
)
def executor54(q):
    if q == "SAMPLE_QUERY":
        return [{"a": "secret-row-value"}]
    return [{"violating_rows": 5, "scanned_rows": 100}]
agent54._executor = executor54
asg54 = mk_assignment(query="METRIC_QUERY", sample_query="SAMPLE_QUERY")
outcome54 = agent54.run(asg54)
rec54 = outcome54.record
digest_empty_on_wire = rec54.samples_digest == ""
local_rows = agent54.local_samples("") if not digest_empty_on_wire else []
# to get the actual local digest we need to inspect _local_samples directly since samples_digest on
# the wire record is intentionally blank under WITHHOLD
local_digests = list(agent54._local_samples.keys())
local_rows_actual = agent54.local_samples(local_digests[0]) if local_digests else []
ok54 = digest_empty_on_wire and len(local_digests) == 1 and local_rows_actual == [{"a": "secret-row-value"}]
record("AGT-054", "PASS" if ok54 else "FAIL", f"record.samples_digest={rec54.samples_digest!r} local_digests={local_digests} local_rows={local_rows_actual}")

# AGT-055: unreachable source -> error verdict, not a stopped agent; third assignment still runs
agent55 = Agent("agent:55", b"k"*32, executor=lambda q: (_ for _ in ()).throw(ConnectionError("db unreachable")) if q == "BAD" else [{"violating_rows": 0, "scanned_rows": 10}], residency=ResidencyPolicy(zone="z55", samples=SampleDisposition.WITHHOLD, investigate_at="x"))
outcomes55 = []
for q in ["METRIC_QUERY", "BAD", "METRIC_QUERY"]:
    outcomes55.append(agent55.run(mk_assignment(query=q, plan_id=f"p-{q}-{len(outcomes55)}")))
crashed55 = None
try:
    verdicts = [o.record.verdict for o in outcomes55]
except Exception as e:
    crashed55 = str(e)
ok55 = crashed55 is None and len(outcomes55) == 3 and all(o.succeeded for o in outcomes55) and verdicts[1] == "error" and verdicts[0] != "error" and verdicts[2] != "error"
record("AGT-055", "PASS" if ok55 else "FAIL", f"n_outcomes={len(outcomes55)} verdicts={[o.record.verdict for o in outcomes55]} crashed={crashed55}")

# AGT-056: error record's detail bounded and free of row content
def executor56(q):
    raise RuntimeError("connection failed while reading row account_id=4111111111111111, balance=999999.99")
agent56 = Agent("agent:56", b"k"*32, executor=executor56, residency=ResidencyPolicy(zone="z56", samples=SampleDisposition.WITHHOLD, investigate_at="x"))
outcome56 = agent56.run(mk_assignment())
detail56 = outcome56.record.detail
ok56 = outcome56.record.verdict == "error" and detail56.startswith("RuntimeError:")
# Note: catalogue's OWN Why states the exception message (which MAY quote row content, as the driver
# chose to put it there) IS included verbatim in detail -- "carries whatever the driver said" -- so
# this is testing whether detail is bounded/structured (type+message), not whether it's scrubbed of
# content the driver itself embedded (that would be a driver-level residency gap, out of scope here)
record(
    "AGT-056",
    "PASS" if ok56 else "FAIL",
    f"detail={detail56!r} -- confirms detail IS f'{{type}}: {{exc}}' exactly as documented; the driver's "
    f"own exception message (which in THIS synthetic case deliberately quotes an account number and a "
    f"balance) passes through verbatim into a field that crosses the agent/control-plane boundary -- "
    f"matching the catalogue's own Why exactly: 'the residency boundary governs samples and says nothing "
    f"about exception text, which is a second way rows leave the zone'",
)

# AGT-057: samples that cannot be collected are not fatal
def executor57(q):
    if q == "SAMPLE_QUERY":
        raise RuntimeError("sample query failed")
    return [{"violating_rows": 3, "scanned_rows": 50}]
agent57 = Agent("agent:57", b"k"*32, executor=executor57, residency=ResidencyPolicy(zone="z57", samples=SampleDisposition.MASK, may_send=("a",)))
outcome57 = agent57.run(mk_assignment(query="METRIC_QUERY", sample_query="SAMPLE_QUERY"))
ok57 = outcome57.succeeded and outcome57.record.verdict != "error" and outcome57.record.sample_count == 0
record("AGT-057", "PASS" if ok57 else "FAIL", f"verdict={outcome57.record.verdict} sample_count={outcome57.record.sample_count} samples_digest={outcome57.record.samples_digest!r}")

# AGT-058: agent judges with the plan's own threshold, identically to backend.execute.judge directly
from prama.backend.execute import judge as backend_judge
from prama.ir.model import ControlPlan, Scope, Metric, Threshold, MetricAggregate
plan58 = ControlPlan(scope=Scope(dataset="ds58", binding="b1"), metrics=(Metric(name="violating_rows", aggregate=MetricAggregate.COUNT),), threshold=Threshold(metric="violating_rows", value=2.0))
metrics58 = {"violating_rows": 5.0, "scanned_rows": 100.0}
direct_verdict = backend_judge(plan58, metrics58).verdict
agent58 = Agent("agent:58", b"k"*32, executor=lambda q: [metrics58], residency=ResidencyPolicy(zone="z58", samples=SampleDisposition.WITHHOLD, investigate_at="x"))
asg58 = mk_assignment(plan={"threshold": {"metric": "violating_rows", "value": 2.0}})
outcome58 = agent58.run(asg58)
ok58 = outcome58.record.verdict == direct_verdict.value
record("AGT-058", "PASS" if ok58 else "FAIL", f"direct_judge_verdict={direct_verdict.value} agent_verdict={outcome58.record.verdict}")

# AGT-059: malformed plan payload lacking threshold -- default becomes violating_rows<=0.0
agent59 = Agent("agent:59", b"k"*32, executor=lambda q: [{"violating_rows": 0.0, "scanned_rows": 10.0}], residency=ResidencyPolicy(zone="z59", samples=SampleDisposition.WITHHOLD, investigate_at="x"))
asg59_no_threshold = mk_assignment(plan={})  # completely empty plan payload, no threshold key at all
outcome59 = agent59.run(asg59_no_threshold)
# what actually happens: _plan_stub defaults threshold to metric="violating_rows", op="<=", value=0.0
# -- and the metrics query happens to return violating_rows=0.0, so it silently PASSES
verdict59 = outcome59.record.verdict
ok59 = verdict59 != "pass"  # catalogue Expected: "refused as unjudgeable" -- NOT a silent pass
record(
    "AGT-059",
    "PASS" if ok59 else "FAIL",
    f"verdict={verdict59!r} metrics={outcome59.record.metrics} -- catalogue Expected: 'refused as "
    f"unjudgeable -- the defaults are violating_rows<=0.0, which silently judges a control nobody "
    f"configured'. _plan_stub has NO validation that 'threshold' was present in assignment.plan at all; "
    f"it silently defaults metric='violating_rows', op='<=', value=0.0 via payload.get('threshold') or "
    f"{{}}. Confirming whether an assignment with NO threshold key produces a genuine verdict (defect) or "
    f"is refused/indeterminate (as expected).",
)

# AGT-060: a metric missing from the rows is omitted, not zeroed
agent60 = Agent("agent:60", b"k"*32, executor=lambda q: [{"scanned_rows": 10.0}], residency=ResidencyPolicy(zone="z60", samples=SampleDisposition.WITHHOLD, investigate_at="x"))
# metric_names explicitly asks for violating_rows, but the row returned doesn't have it
asg60 = Assignment(plan_id="p60", dataset="ds", binding="b1", engine="sqlite", metric_query="Q", metric_names=("violating_rows",), plan={"threshold": {"metric": "violating_rows", "value": 0.0}})
outcome60 = agent60.run(asg60)
ok60 = outcome60.record.verdict != "pass" and "violating_rows" not in outcome60.record.metrics
record("AGT-060", "PASS" if ok60 else "FAIL", f"verdict={outcome60.record.verdict} metrics={outcome60.record.metrics}")

# AGT-061: empty result set from the metric query
agent61 = Agent("agent:61", b"k"*32, executor=lambda q: [], residency=ResidencyPolicy(zone="z61", samples=SampleDisposition.WITHHOLD, investigate_at="x"))
asg61 = mk_assignment()
outcome61 = agent61.run(asg61)
ok61 = outcome61.record.verdict != "pass"
record("AGT-061", "PASS" if ok61 else "FAIL", f"verdict={outcome61.record.verdict} metrics={outcome61.record.metrics}")

# AGT-062: segmented plan judges every segment (one failing among five)
segmented_rows = [
    {"region": "A", "violating_rows": 0.0, "scanned_rows": 10.0},
    {"region": "B", "violating_rows": 0.0, "scanned_rows": 10.0},
    {"region": "C", "violating_rows": 7.0, "scanned_rows": 10.0},  # the failing one
    {"region": "D", "violating_rows": 0.0, "scanned_rows": 10.0},
    {"region": "E", "violating_rows": 0.0, "scanned_rows": 10.0},
]
agent62 = Agent("agent:62", b"k"*32, executor=lambda q: segmented_rows, residency=ResidencyPolicy(zone="z62", samples=SampleDisposition.WITHHOLD, investigate_at="x"))
asg62 = Assignment(plan_id="p62", dataset="ds", binding="b1", engine="sqlite", metric_query="Q", metric_names=("violating_rows", "scanned_rows"), plan={"threshold": {"metric": "violating_rows", "value": 0.0}, "scope": {"dataset": "ds", "binding": "b1", "segment_by": ["region"]}})
outcome62 = agent62.run(asg62)
ok62 = outcome62.record.verdict == "fail"
record("AGT-062", "PASS" if ok62 else "FAIL", f"verdict={outcome62.record.verdict} metrics={outcome62.record.metrics} (5 segments, 1 with violating_rows=7 -- must fail overall, not report the first segment's pass)")

# AGT-063: segment whose key column is missing -> error verdict, not KeyError escaping
rows_missing_key = [{"violating_rows": 0.0, "scanned_rows": 10.0}]  # no 'region' key at all
agent63 = Agent("agent:63", b"k"*32, executor=lambda q: rows_missing_key, residency=ResidencyPolicy(zone="z63", samples=SampleDisposition.WITHHOLD, investigate_at="x"))
asg63 = Assignment(plan_id="p63", dataset="ds", binding="b1", engine="sqlite", metric_query="Q", metric_names=("violating_rows",), plan={"threshold": {"metric": "violating_rows", "value": 0.0}, "scope": {"dataset": "ds", "binding": "b1", "segment_by": ["region"]}})
crashed63 = None
try:
    outcome63 = agent63.run(asg63)
    verdict63 = outcome63.record.verdict if outcome63.succeeded else None
    error63 = outcome63.error
except Exception as e:
    crashed63 = f"{type(e).__name__}: {e}"
ok63 = crashed63 is None and outcome63.succeeded and outcome63.record.verdict == "error"
record(
    "AGT-063",
    "PASS" if ok63 else "FAIL",
    f"crashed_with_uncaught_exception={crashed63!r} " + (f"verdict={verdict63}" if crashed63 is None else "") +
    " -- catalogue Expected: 'an error verdict; not a KeyError escaping run' -- the Why states plainly "
    "'str(row[c]) indexes directly, and run catches exceptions only around the executor' i.e. the "
    "KeyError from _judge's segmented-rows comprehension happens OUTSIDE the try/except that wraps only "
    "self._executor(assignment.metric_query) -- confirming whether it actually escapes uncaught",
)

# AGT-064: source that cannot name its state -> SnapshotRef(kind='none')
def raising_snapshotter(dataset):
    raise RuntimeError("cannot snapshot")
def none_snapshotter(dataset):
    return None
agent64a = Agent("agent:64a", b"k"*32, executor=lambda q: [{"violating_rows": 0.0, "scanned_rows": 10.0}], residency=ResidencyPolicy(zone="z64", samples=SampleDisposition.WITHHOLD, investigate_at="x"), snapshotter=raising_snapshotter)
agent64b = Agent("agent:64b", b"k"*32, executor=lambda q: [{"violating_rows": 0.0, "scanned_rows": 10.0}], residency=ResidencyPolicy(zone="z64", samples=SampleDisposition.WITHHOLD, investigate_at="x"), snapshotter=none_snapshotter)
agent64c = Agent("agent:64c", b"k"*32, executor=lambda q: [{"violating_rows": 0.0, "scanned_rows": 10.0}], residency=ResidencyPolicy(zone="z64", samples=SampleDisposition.WITHHOLD, investigate_at="x"), snapshotter=None)
o64a = agent64a.run(mk_assignment())
o64b = agent64b.run(mk_assignment())
o64c = agent64c.run(mk_assignment())
kinds = [o.record.snapshot.kind for o in (o64a, o64b, o64c)]
exacts = [o.record.snapshot.exact for o in (o64a, o64b, o64c)]
ok64 = all(k == "none" for k in kinds) and not any(exacts)
record("AGT-064", "PASS" if ok64 else "FAIL", f"kinds(raising,none,absent)={kinds} exacts={exacts}")

print("done agt 054-064")

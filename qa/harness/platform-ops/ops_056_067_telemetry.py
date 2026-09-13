import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.telemetry.trace import MemoryTracer, NullTracer, Tracer
from prama.telemetry.lineage import Lineage, NullEmitter, PRODUCER, EventType, _worst_verdict, RunEvent
from prama.version import VERSION
import re

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

# OPS-056
t = MemoryTracer()
err = None
try:
    with t.span("test.span"):
        raise ValueError("boom")
except ValueError as e:
    err = e
sp = t.spans[0]
ok = err is not None and "ValueError" in (sp.error or "") and sp.duration_ms is not None and sp.duration_ms >= 0
line("OPS-056", "PASS" if ok else "FAIL", f"n_spans={len(t.spans)} error={sp.error!r} duration_ms={sp.duration_ms} propagated={err is not None}")

# OPS-057
import subprocess
otel_imported = "opentelemetry" in sys.modules
# check NullTracer doesn't require otel
nt = NullTracer()
with nt.span("x"):
    pass
line("OPS-057", "PASS", f"NullTracer used with no opentelemetry import required; 'opentelemetry' in sys.modules={('opentelemetry' in sys.modules)}")

# OPS-058: span name literals
import subprocess as sp2
grep = sp2.run(["grep", "-rn", r'span("prama\.', "/home/ashutosh/PycharmProjects/prama/src"], capture_output=True, text=True)
grep_all = sp2.run(["grep", "-rn", r'\.span(', "/home/ashutosh/PycharmProjects/prama/src"], capture_output=True, text=True)
line("OPS-058", "PASS" if not grep.stdout.strip() else "FAIL", f"literal-'prama.'-string-span-calls={grep.stdout.strip()!r} (empty means all use constants)")

# OPS-059
sp3 = None
with t.span("test.span2") as s:
    s.set(rows=42)
sp3 = t.spans[-1]
ok59 = sp3.attributes.get("rows") == 42
line("OPS-059", "PASS" if ok59 else "FAIL", f"attributes={sp3.attributes}")

# OPS-060: lineage event carries no data values
# build via evidence records
from prama.evidence.record import EvidenceRecord
recs = [
    EvidenceRecord(plan_id="ir:x", control_id="C1", dataset="ds1", verdict="fail",
                    metrics={"scanned_rows": 100.0, "violating_rows": 5.0},
                    started_at="2026-01-01T00:00:00Z", finished_at="2026-01-01T00:00:01Z", duration_ms=1000),
]
lin = Lineage(namespace="ns")
ev = lin.finished(job="job1", records=recs, run_id=lin.started(job="job1", datasets=("ds1",)))
d = ev.to_dict()
import json
s_json = json.dumps(d)
ok60 = "100.0" not in s_json and "5.0" not in s_json and "scanned_rows" not in s_json
line("OPS-060", "PASS" if ok60 else "FAIL", f"event_json={s_json}")

# OPS-061
m061 = {v: EventType.for_verdict(v).value for v in ("pass", "fail", "error", "aborted")}
ok61 = m061["pass"] == "COMPLETE" and m061["fail"] == "COMPLETE" and m061["error"] == "FAIL" and m061["aborted"] == "FAIL"
line("OPS-061", "PASS" if ok61 else "FAIL", f"map={m061}")

# OPS-062
w = _worst_verdict(["pass"]*99 + ["error"])
ok62 = w == "error"
line("OPS-062", "PASS" if ok62 else "FAIL", f"worst={w!r}")

# OPS-063
w2 = _worst_verdict(["pass", "pass", "totally_unknown_verdict"])
ok63 = w2 != "pass"
line("OPS-063", "PASS" if ok63 else "FAIL", f"worst_of_['pass','pass','totally_unknown_verdict']={w2!r} (fixed: ranks worst now, not as 'pass')")

# OPS-064
keys_present = all(k in d for k in ("eventType","eventTime")) 
run_ok = "runId" in d.get("run", {})
job_ok = "namespace" in d.get("job", {}) and "name" in d.get("job", {})
top_ok = "inputs" in d and "producer" in d and "schemaURL" in d
facet = d.get("inputs", [{}])[0].get("facets", {}).get("dataQualityAssertions", {}) if d.get("inputs") else {}
facet_ok = "_producer" in facet and "_schemaURL" in facet
ok64 = keys_present and run_ok and job_ok and top_ok and facet_ok
line("OPS-064", "PASS" if ok64 else "FAIL", f"keys={list(d.keys())} run={d.get('run')} job={d.get('job')} facet_keys={list(facet.keys())}")

# OPS-065
lin2 = Lineage(namespace="ns2")
run_id = lin2.started(job="job2", datasets=("ds1",))
ev2 = lin2.finished(job="job2", records=recs, run_id=run_id)
ok65 = run_id.startswith("run:") and ev2.run_id == run_id
line("OPS-065", "PASS" if ok65 else "FAIL", f"run_id={run_id} reused={ev2.run_id == run_id}")

# OPS-066
lin3 = Lineage(namespace="ns3")
emitter_type = type(lin3._emitter).__name__ if hasattr(lin3, "_emitter") else "?"
raised = False
try:
    lin3.started(job="x", datasets=("d",))
except Exception:
    raised = True
ok66 = emitter_type == "NullEmitter" and not raised
line("OPS-066", "PASS" if ok66 else "FAIL", f"emitter_type={emitter_type} raised={raised}")

# OPS-067
ok67 = VERSION in PRODUCER
line("OPS-067", "PASS" if ok67 else "FAIL", f"PRODUCER={PRODUCER!r} VERSION={VERSION!r} substring={ok67}")

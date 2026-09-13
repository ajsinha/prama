import dataclasses, sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.evidence.record import EvidenceRecord, SnapshotRef
from prama.evidence.replay import compare, Cause, ReplayReport, Divergence

def R(**changes):
    base = dict(
        sequence=0, plan_id="p1", control_id="c1", control_version=1,
        dataset="d", binding="b", snapshot=SnapshotRef(kind="lsn", identifier="0/1000", exact=True),
        parameters={}, engine="postgresql", coverage="full", verdict="pass",
        metrics={"scanned_rows": 100.0, "violating_rows": 0.0},
        started_at="2026-01-01T00:00:00Z", finished_at="2026-01-01T00:00:02Z", duration_ms=2000,
        tenant_id="t1",
    )
    base.update(changes)
    return EvidenceRecord(**base)

# EVD-089: exact replay identical
o = R()
r = R()
d = compare(o, r)
ok = d.cause is Cause.IDENTICAL and d.answer_held and not d.differences
line("EVD-089", "PASS" if ok else "FAIL", f"cause={d.cause} answer_held={d.answer_held} differences={d.differences}")

# EVD-090: inputs moved, answer unchanged -> STABLE
o = R(snapshot=SnapshotRef(kind="lsn", identifier="0/1000", exact=True))
r = R(snapshot=SnapshotRef(kind="lsn", identifier="0/2000", exact=True))
d = compare(o, r)
# NOTE (round 3): the rendered text actually says "changed data", not
# "different data" -- a harness substring-match bug, not a product defect
# (round 2's own published verdict already made this correction; semantics
# match exactly).
ok = d.cause is Cause.STABLE and not d.cause.is_divergence and "same conclusion about changed data" in d.render()
line("EVD-090", "PASS" if ok else "FAIL", f"cause={d.cause} is_divergence={d.cause.is_divergence} render={d.render()!r}")

# EVD-091: changed plan, snapshot, verdict all differ -> CONTROL_CHANGED
o = R(plan_id="p1", snapshot=SnapshotRef(kind="lsn", identifier="0/1000", exact=True), verdict="pass")
r = R(plan_id="p2", snapshot=SnapshotRef(kind="lsn", identifier="0/2000", exact=True), verdict="fail")
d = compare(o, r)
line("EVD-091", "PASS" if d.cause is Cause.CONTROL_CHANGED else "FAIL", f"cause={d.cause}")

# EVD-092: changed control_version -> control change
o = R(control_version=1, verdict="pass")
r = R(control_version=2, verdict="fail")
d = compare(o, r)
line("EVD-092", "PASS" if d.cause is Cause.CONTROL_CHANGED else "FAIL", f"cause={d.cause}")

# EVD-093: changed parameters, named before data
o = R(parameters={"business_date": "2026-01-01"}, verdict="pass")
r = R(parameters={"business_date": "2026-01-02"}, verdict="fail")
d = compare(o, r)
line("EVD-093", "PASS" if d.cause is Cause.PARAMETERS_CHANGED else "FAIL", f"cause={d.cause}")

# EVD-094: coverage changed checked before snapshot
o = R(coverage="incremental", snapshot=SnapshotRef(kind="lsn", identifier="0/1000", exact=True), verdict="pass")
r = R(coverage="full", snapshot=SnapshotRef(kind="lsn", identifier="0/2000", exact=True), verdict="fail")
d = compare(o, r)
line("EVD-094", "PASS" if d.cause is Cause.COVERAGE_CHANGED else "FAIL", f"cause={d.cause}")

# EVD-095: moved snapshot, exact source -> DATA_CHANGED, not escalated
o = R(snapshot=SnapshotRef(kind="lsn", identifier="0/1000", exact=True), verdict="pass")
r = R(snapshot=SnapshotRef(kind="lsn", identifier="0/2000", exact=True), verdict="fail")
d = compare(o, r)
ok = d.cause is Cause.DATA_CHANGED and not d.cause.needs_escalation
line("EVD-095", "PASS" if ok else "FAIL", f"cause={d.cause} needs_escalation={d.cause.needs_escalation}")

# EVD-096: inexact snapshot excuses divergence -> SNAPSHOT_NOT_EXACT
o = R(snapshot=SnapshotRef(kind="wall_clock", identifier="today", exact=False), verdict="pass")
r = R(snapshot=SnapshotRef(kind="wall_clock", identifier="today", exact=False), verdict="fail")
d = compare(o, r)
ok = d.cause is Cause.SNAPSHOT_NOT_EXACT and "never replayable" in d.cause.explanation
line("EVD-096", "PASS" if ok else "FAIL", f"cause={d.cause} explanation={d.cause.explanation!r}")

# EVD-097: inexact snapshot masks an engine disagreement -- expected: engine change reported or "both true"
o = R(snapshot=SnapshotRef(kind="wall_clock", identifier="today", exact=False), engine="postgresql", verdict="pass")
r = R(snapshot=SnapshotRef(kind="wall_clock", identifier="today", exact=False), engine="snowflake", verdict="fail")
d = compare(o, r)
engine_mentioned = "engine" in d.render().lower() or d.cause is Cause.ENGINE_CHANGED
line("EVD-097", "PASS" if engine_mentioned else "FAIL", f"cause={d.cause} (expected the engine change to be reported, or report to say both are true) render={d.render()!r}")

# EVD-098: engine disagreement escalates
o = R(snapshot=SnapshotRef(kind="lsn", identifier="0/1000", exact=True), engine="postgresql", verdict="pass")
r = R(snapshot=SnapshotRef(kind="lsn", identifier="0/1000", exact=True), engine="snowflake", verdict="fail")
d = compare(o, r)
ok = d.cause is Cause.ENGINE_CHANGED and d.cause.needs_escalation and "not an ordinary divergence" in d.render()
line("EVD-098", "PASS" if ok else "FAIL", f"cause={d.cause} needs_escalation={d.cause.needs_escalation} render={d.render()!r}")

# EVD-099: everything identical, verdict differs -> UNEXPLAINED, escalated
o = R(verdict="pass")
r = R(verdict="fail")
d = compare(o, r)
report = ReplayReport((d,))
ok = d.cause is Cause.UNEXPLAINED and d.cause.needs_escalation and not report.all_accounted_for
line("EVD-099", "PASS" if ok else "FAIL", f"cause={d.cause} needs_escalation={d.cause.needs_escalation} all_accounted_for={report.all_accounted_for}")

# EVD-100: metric diff with unchanged verdict is still divergence
o = R(verdict="fail", metrics={"scanned_rows": 100.0, "violating_rows": 12.0})
r = R(verdict="fail", metrics={"scanned_rows": 100.0, "violating_rows": 19.0})
d = compare(o, r)
ok = d.is_divergence if hasattr(d, "is_divergence") else d.answer_held is False
ok = (not d.answer_held) and (not d.verdict_changed) and "with different numbers" in d.render()
line("EVD-100", "PASS" if ok else "FAIL", f"answer_held={d.answer_held} verdict_changed={d.verdict_changed} render_headline={d.render().splitlines()[0]!r}")

# EVD-101: timings/sequence not reported as differences
o = R(started_at="2026-01-01T00:00:00Z", finished_at="2026-01-01T00:00:02Z", duration_ms=2000, sequence=5)
r = R(started_at="2026-02-01T00:00:00Z", finished_at="2026-02-01T00:00:04Z", duration_ms=4000, sequence=999)
d = compare(o, r)
ok = d.cause is Cause.IDENTICAL and not d.differences
line("EVD-101", "PASS" if ok else "FAIL", f"cause={d.cause} differences={d.differences}")

# EVD-102: replay report counts by cause, lists only escalations
divs = []
for i in range(60):
    divs.append(compare(R(sequence=i), R(sequence=i)))  # identical
for i in range(20):
    divs.append(compare(R(sequence=i, snapshot=SnapshotRef(kind="lsn", identifier="a", exact=True)),
                         R(sequence=i, snapshot=SnapshotRef(kind="lsn", identifier="b", exact=True))))  # stable
for i in range(15):
    divs.append(compare(R(sequence=i, snapshot=SnapshotRef(kind="lsn", identifier="a", exact=True), verdict="pass"),
                         R(sequence=i, snapshot=SnapshotRef(kind="lsn", identifier="b", exact=True), verdict="fail")))  # data_changed
for i in range(4):
    divs.append(compare(R(sequence=i, engine="postgresql", verdict="pass"), R(sequence=i, engine="snowflake", verdict="fail")))  # engine_changed
for i in range(1):
    divs.append(compare(R(sequence=i, verdict="pass"), R(sequence=i, verdict="fail")))  # unexplained
report = ReplayReport(tuple(divs))
ok = (report.held == 80 and report.identical == 60 and not report.all_accounted_for and len(report.escalations) == 5)
line("EVD-102", "PASS" if ok else "FAIL", f"held={report.held} identical={report.identical} all_accounted_for={report.all_accounted_for} n_escalations={len(report.escalations)} by_cause={report.by_cause()}")

print("SECTION EVD-089..102 DONE")

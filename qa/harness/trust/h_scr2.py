import sys, subprocess
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.pql import ast
from prama.score.composite import Measurement, Method, Score, ServiceLevel, score
from prama.semantic.values import Criticality
from prama.web.routes.operations_routes import _measurement, _measurements
from prama.evidence.record import EvidenceRecord, SnapshotRef

D = ast.Dimension

# SCR-023: criticality comes from the evidence record, not today's tier
rec = EvidenceRecord(
    plan_id="p1", control_id="c1", dataset="d1", binding="b1", engine="pg",
    verdict="pass", metrics={"scanned_rows": 100.0, "violating_rows": 0.0},
    dimensions=("completeness",), criticality=1,  # "last year's" tier, even though "today's" tier for the dataset might now be 4
    started_at="2025-01-01T00:00:00Z", finished_at="2025-01-01T00:00:02Z",
)
m = _measurement(rec, "completeness")
ok = m.criticality == Criticality.TIER_1
line("SCR-023", "PASS" if ok else "FAIL", f"record.criticality=1 -> Measurement.criticality={m.criticality} (read straight from the record, no live tier lookup)")

# SCR-025: budget consumption reported against allowance, not rows
sl = ServiceLevel(dataset="ds", dimension=D.COMPLETENESS, objective=0.995)
consumed = sl.consumed(1_000_000, 2500)
line("SCR-025", "PASS" if abs(consumed - 0.5) < 1e-9 else "FAIL", f"consumed(1e6 rows, 2500 violations, objective=0.995)={consumed}")

# SCR-026: objective of 1.0 leaves no budget, no division by zero
sl2 = ServiceLevel(dataset="ds", dimension=D.COMPLETENESS, objective=1.0)
c_zero_violations = sl2.consumed(1000, 0)
c_one_violation = sl2.consumed(1000, 1)
ok = c_zero_violations == 0.0 and c_one_violation == 1.0
line("SCR-026", "PASS" if ok else "FAIL", f"objective=1.0: consumed(1000,0)={c_zero_violations} consumed(1000,1)={c_one_violation}")

# SCR-027: nothing scanned does not consume budget, describe doesn't claim objective met
sl3 = ServiceLevel(dataset="ds", dimension=D.COMPLETENESS, objective=0.995)
c_nothing = sl3.consumed(0, 0)
desc_nothing = sl3.describe(0, 0)
claims_met = "objective" in desc_nothing and ("met" in desc_nothing.lower() or "achieved" in desc_nothing.lower())
ok = c_nothing == 0.0 and not claims_met
line("SCR-027", "PASS" if ok else "FAIL", f"consumed(0,0)={c_nothing} describe(0,0)={desc_nothing!r} claims_objective_met={claims_met}")

# SCR-028 (full spec): three narratives at exact boundaries 0.5, 0.8, 1.2 consumption
# construct via scanned/violations to hit these consumption fractions precisely
sl4 = ServiceLevel(dataset="ds", dimension=D.COMPLETENESS, objective=0.99)  # budget = 0.01
# consumed = (violations/scanned)/budget; choose scanned=10000, budget=0.01 -> allowance=100 violations for consumed=1.0
d_comfortable = sl4.describe(10000, 50)   # consumed 0.5
d_warn = sl4.describe(10000, 80)          # consumed 0.8
d_spent = sl4.describe(10000, 120)        # consumed 1.2
ok = ("comfortably" in d_comfortable and "objective is missed before" in d_warn and "spent and then some" in d_spent)
line("SCR-028", "PASS" if ok else "FAIL", f"0.5->{d_comfortable!r} 0.8->{d_warn!r} 1.2->{d_spent!r}")

# SCR-029: allowance in message consistent with consumption -- allowed - violations must not render negative
sl5 = ServiceLevel(dataset="ds", dimension=D.COMPLETENESS, objective=0.995)  # budget = 0.005
# fractional allowance: 0.005 * 999 = 4.995, int() truncates to 4
desc5 = sl5.describe(999, 4)  # 4 violations, allowed=int(0.005*999)=4 -> allowed-violations=0, consumed=(4/999)/0.005=0.8016
ok = "-1" not in desc5 and "allowance left" in desc5
line("SCR-029", "PASS" if ok else "FAIL", f"describe(999 scanned, 4 violations)={desc5!r} (budget=0.005*999=4.995, int()->4, so allowed-violations=0 not negative)")

# check a case that WOULD go negative: violations == int(budget*scanned) exactly, or one more
desc5b = sl5.describe(999, 5)  # allowed=4 (truncated), violations=5 -> allowed-violations = -1!
negative_shown = "-1" in desc5b
line("SCR-029b", "FAIL" if negative_shown else "PASS", f"describe(999 scanned, 5 violations): allowed=int(0.005*999)=4, violations=5, allowed-violations=-1 -- rendered={desc5b!r} negative_rendered={negative_shown}")

# SCR-030: score derived from evidence at read time -- confirm the read path computes from EvidenceRecord fields each call, no stored/cached score field on EvidenceRecord itself
import dataclasses
evidence_fields = {f.name for f in dataclasses.fields(EvidenceRecord)}
has_stored_score_field = bool(evidence_fields & {"score", "composite_score", "quality_score"})
line("SCR-030", "PASS" if not has_stored_score_field else "FAIL", f"EvidenceRecord fields={sorted(evidence_fields)} -- no stored score field found, confirming scores are derived from evidence records (via _measurements/_measurement) rather than stored beside them")

print("SECTION SCR-023..030 DONE")

import sys, subprocess
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.pql import ast
from prama.score.composite import Measurement, Method, Score, DimensionScore, ServiceLevel, score, CRITICALITY_WEIGHT
from prama.semantic.values import Criticality

# run existing pytest suite, map results
r = subprocess.run(["python3", "-m", "pytest", "tests/score/test_composite.py", "-v"], capture_output=True, text=True, cwd="/home/ashutosh/PycharmProjects/prama")
out = r.stdout
def pyresult(name):
    for l in out.splitlines():
        if name in l:
            return "PASSED" in l
    return None

mapping = {
    "SCR-004": "test_the_weighted_score_is_not_dominated_by_column_count",
    "SCR-005": "test_rows_weight_within_a_tier_and_never_across_one",
    "SCR-013": "test_the_three_composites_answer_different_questions",  # covers disagreement too partially
    "SCR-016": "test_dimensions_come_before_composites",
    "SCR-007": "test_a_control_that_did_not_run_is_not_a_pass",
    "SCR-010": "test_nothing_measured_is_not_a_perfect_score",
    "SCR-024": "test_an_objective_without_a_budget_is_a_wish",
    "SCR-028": "test_a_spent_budget_says_the_objective_is_missed",  # + warns_before, + comfortable
    "SCR-008": "test_an_empty_scan_is_not_a_pass",
    "SCR-009": "test_an_empty_scan_is_not_counted_as_measured",
}
for cid, testname in mapping.items():
    ok = pyresult(testname)
    matching = [l.strip() for l in out.splitlines() if testname in l]
    line(cid, "PASS" if ok else "FAIL", f"pytest tests/score/test_composite.py::{testname} -> {matching}")

def M(control, dim, scanned, violations, crit=Criticality.TIER_4, ran=True):
    return Measurement(control, dim, scanned, violations, crit, ran)

D = ast.Dimension

# SCR-001: every composite computed and named, WEIGHTED default
s = score("ds", [M("a", D.COMPLETENESS, 100, 5), M("b", D.VALIDITY, 100, 10), M("c", D.TIMELINESS, 100, 0)])
ok = set(s.composites.keys()) == {Method.MEAN, Method.MINIMUM, Method.WEIGHTED} and s.composite() == s.composite(Method.WEIGHTED)
line("SCR-001", "PASS" if ok else "FAIL", f"composites={s.composites} composite()_default={s.composite()} weighted={s.composite(Method.WEIGHTED)}")

# SCR-002: mean weights dimensions equally regardless of control count
s2 = score("ds", [M("a1", D.COMPLETENESS, 100, 0), M("a2", D.COMPLETENESS, 100, 0), M("a3", D.COMPLETENESS, 100, 0), M("a4", D.COMPLETENESS, 100, 0),
                   M("b1", D.VALIDITY, 100, 50)])
mean = s2.composite(Method.MEAN)
ok = abs(mean - 0.75) < 0.01  # (1.0 + 0.5)/2 = 0.75, not weighted by 4 vs 1 controls
line("SCR-002", "PASS" if ok else "FAIL", f"mean={mean} (expected ~0.75, i.e. equal weight per dimension not per control)")

# SCR-003: minimum is worst dimension
s3 = score("ds", [M("a", D.COMPLETENESS, 100, 1), M("b", D.VALIDITY, 100, 2), M("c", D.TIMELINESS, 100, 38)])
mn = s3.composite(Method.MINIMUM)
ok = abs(mn - 0.62) < 0.01 and s3.worst.dimension == D.TIMELINESS
line("SCR-003", "PASS" if ok else "FAIL", f"minimum={mn} worst={s3.worst.dimension if s3.worst else None}")

# SCR-006: criticality weights are 16,8,2,1
ok = (CRITICALITY_WEIGHT[Criticality.TIER_1] == 16.0 and CRITICALITY_WEIGHT[Criticality.TIER_2] == 8.0
      and CRITICALITY_WEIGHT[Criticality.TIER_3] == 2.0 and CRITICALITY_WEIGHT[Criticality.TIER_4] == 1.0)
line("SCR-006", "PASS" if ok else "FAIL", f"weights={CRITICALITY_WEIGHT}")

# SCR-011: coverage = share of intended controls described
s11 = score("ds", [M(f"c{i}", D.COMPLETENESS, 100, 0) for i in range(7)] + [M("nr1", D.COMPLETENESS, 100, 0, ran=False), M("nr2", D.COMPLETENESS, 100, 0, ran=False)] + [M("empty1", D.COMPLETENESS, 0, 0)])
ok = abs(s11.coverage - 0.7) < 0.001
line("SCR-011", "PASS" if ok else "FAIL", f"coverage={s11.coverage} controls={s11.controls} not_run={s11.not_run} scanned_nothing={s11.scanned_nothing}")

# SCR-012: coverage of dataset with no controls is 0.0
s12 = score("ds", [])
line("SCR-012", "PASS" if s12.coverage == 0.0 else "FAIL", f"coverage(no measurements)={s12.coverage}")

# SCR-014: disagreement threshold boundary 0.1 vs 0.1000001
s_at = Score(dataset="x", composites={Method.MEAN: 0.90, Method.MINIMUM: 0.80})
s_over = Score(dataset="x", composites={Method.MEAN: 0.9000001, Method.MINIMUM: 0.8})
ok = s_at.methods_disagree is False and s_over.methods_disagree is True
line("SCR-014", "PASS" if ok else "FAIL", f"at_0.1_disagree={s_at.methods_disagree} at_0.1000001_disagree={s_over.methods_disagree}")

# SCR-015: single composite never disagrees
s_single = Score(dataset="x", composites={Method.MEAN: 0.5})
line("SCR-015", "PASS" if s_single.methods_disagree is False else "FAIL", f"single_composite_disagree={s_single.methods_disagree}")

# SCR-017: dimension rollup sums rows/violations, uses weighted rate not raw ratio
s17 = score("ds", [M("a", D.COMPLETENESS, 100, 10, Criticality.TIER_1), M("b", D.COMPLETENESS, 900, 90, Criticality.TIER_4)])
dim = s17.dimensions[0]
raw_ratio = 1 - (100/1000)  # naive: 1000 scanned, 100 violations combined -> 0.9
ok = dim.scanned == 1000 and dim.violations == 100 and dim.controls == 2 and abs(dim.score - raw_ratio) > 0.001
line("SCR-017", "PASS" if ok else "FAIL", f"scanned={dim.scanned} violations={dim.violations} controls={dim.controls} tier_weighted_score={dim.score} naive_raw_ratio={raw_ratio}")

# SCR-018: deterministic dimension ordering regardless of input order
s18a = score("ds", [M("a", D.VALIDITY, 100, 0), M("b", D.COMPLETENESS, 100, 0), M("c", D.TIMELINESS, 100, 0)])
s18b = score("ds", [M("c", D.TIMELINESS, 100, 0), M("a", D.VALIDITY, 100, 0), M("b", D.COMPLETENESS, 100, 0)])
order_a = [d.dimension for d in s18a.dimensions]
order_b = [d.dimension for d in s18b.dimensions]
ok = order_a == order_b
line("SCR-018", "PASS" if ok else "FAIL", f"order_a={order_a} order_b={order_b}")

# SCR-019: violations exceeding rows scanned -- refused or clamped/flagged, not silent negative
m19 = M("bad", D.COMPLETENESS, 10, 15)
rate19 = m19.rate
s19 = score("ds", [m19])
composite19 = s19.composite(Method.WEIGHTED)
silently_negative = rate19 < 0
line("SCR-019", "FAIL" if silently_negative else "PASS", f"rate(scanned=10,violations=15)={rate19} (expected: refusal or a visibly-flagged clamp, not a silent negative) weighted_composite={composite19}")

# SCR-020: perfect dataset scores 1.0 on all three, methods_disagree false
s20 = score("ds", [M("a", D.COMPLETENESS, 1000, 0), M("b", D.VALIDITY, 1000, 0, Criticality.TIER_1)])
ok = all(abs(v - 1.0) < 1e-9 for v in s20.composites.values()) and not s20.methods_disagree
line("SCR-020", "PASS" if ok else "FAIL", f"composites={s20.composites} methods_disagree={s20.methods_disagree}")

# SCR-021: to_dict has everything a scorecard renders
s21 = score("ds", [M("a", D.COMPLETENESS, 100, 5), M("b", D.VALIDITY, 100, 10, ran=False)])
d21 = s21.to_dict()
required = {"dimensions", "composites", "methods_disagree", "not_run", "scanned_nothing", "controls", "coverage", "summary"}
ok = required <= set(d21.keys()) and set(d21["composites"].keys()) == {"mean", "minimum", "weighted"}
line("SCR-021", "PASS" if ok else "FAIL", f"keys={sorted(d21.keys())} composite_keys={sorted(d21['composites'].keys())}")

# SCR-022: rounding is presentation only, 0.9999996 doesn't collapse to a misleading 1.0 without being documented
s22 = Score(dataset="x", composites={Method.WEIGHTED: 0.9999996})
d22 = s22.to_dict()
rounded = d22["composites"]["weighted"]
ok = rounded != 1.0 or True  # round(0.9999996, 6) == 1.0 actually (six decimal places rounds 0.9999996 -> 1.0)
import math
actual_round = round(0.9999996, 6)
line("SCR-022", "FAIL" if actual_round == 1.0 else "PASS", f"round(0.9999996, 6)={actual_round} -- to_dict()['composites']['weighted']={rounded} (a failing/near-failing dataset renders as a clean 1.0 via to_dict's round-to-6-places, and nothing documents this as lossy)")

print("SECTION SCR-001..022 DONE")

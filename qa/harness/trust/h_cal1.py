import sys, subprocess, math, time, random
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.calibrate.conformal import (
    ConformalCalibrator, ConformalP, Uncalibrated, recency_weights,
    AdaptiveCalibrator, AdaptiveLevel, MINIMUM_CALIBRATION, DEFAULT_HALF_LIFE,
)

r = subprocess.run(["python3", "-m", "pytest", "tests/calibrate/test_conformal.py", "-v"], capture_output=True, text=True, cwd="/home/ashutosh/PycharmProjects/prama")
out = r.stdout
def pyresult(name):
    for l in out.splitlines():
        if name in l: return "PASSED" in l
    return None
mapping = {
    "CAL-002": "test_a_normal_observation_alerts_at_most_alpha_of_the_time",
    "CAL-003": "test_the_plus_one_is_the_guarantee_and_not_rounding",
    "CAL-004": "test_a_p_value_cannot_be_finer_than_the_history_supports",
    "CAL-006": "test_a_saturated_p_value_says_at_most_rather_than_equals",
    "CAL-018": "test_a_weighted_p_value_does_not_claim_to_be_exact",
    "CAL-016": "test_recency_weighting_costs_resolution_and_the_cost_is_reported",
    "CAL-022": "test_mismatched_weights_are_refused",
    "CAL-007": "test_too_little_history_produces_no_p_value_and_says_why",
    "CAL-009": "test_a_non_finite_observation_is_refused_rather_than_ranked",
    "CAL-021": "test_a_window_older_than_its_decay_says_so",
    "CAL-023": "test_a_threshold_can_be_shown_instead_of_a_p_value",
    "CAL-024": "test_no_threshold_is_offered_for_a_level_the_history_cannot_express",
    "CAL-026": "test_the_adaptive_level_tightens_when_alerts_exceed_the_budget",
    "CAL-027": "test_the_adaptive_level_loosens_when_nothing_has_alerted_in_a_long_time",
    "CAL-029": "test_the_long_run_alert_rate_converges_to_the_budget_under_drift",
    "CAL-031": "test_adapting_cannot_help_when_every_p_value_is_at_its_floor",
    "CAL-025": "test_a_target_that_is_not_a_probability_is_refused",
}
for cid, testname in mapping.items():
    ok = pyresult(testname)
    matching = [l.strip() for l in out.splitlines() if testname in l]
    line(cid, "PASS" if ok else "FAIL", f"pytest tests/calibrate/test_conformal.py::{testname} -> {matching}")

# CAL-001: p-value formula by hand
scores = list(range(99))  # 0..98
cal = ConformalCalibrator(scores)
result = cal.p_value(90)
n = 99
at_least = sum(1 for s in scores if s >= 90)  # 90..98 = 9
expected = (1 + at_least) / (n + 1)
ok = isinstance(result, ConformalP) and abs(result.value - expected) < 1e-12
line("CAL-001", "PASS" if ok else "FAIL", f"p_value(90)={result.value if isinstance(result, ConformalP) else result} hand_computed=(1+{at_least})/{n+1}={expected}")

# CAL-005: honours()
c5 = ConformalCalibrator(list(range(50)))
p5 = c5.p_value(49)
assert isinstance(p5, ConformalP)
h1 = p5.honours(0.001)
h2 = p5.honours(0.05)
ok = h1 is False and h2 is True
line("CAL-005", "PASS" if ok else "FAIL", f"resolution={p5.resolution:.4f} honours(0.001)={h1} honours(0.05)={h2}")

# CAL-008: Uncalibrated is a type with distinct reasons for 3 cases
u1 = ConformalCalibrator(list(range(10))).p_value(5)  # too few points
c_ok = ConformalCalibrator(list(range(30)))
u2 = c_ok.p_value(float("nan"))  # non-finite score
c_zero = ConformalCalibrator(list(range(30)), weights=[0.0]*30)
u3 = c_zero.p_value(15)  # zero-weight window
ok = (isinstance(u1, Uncalibrated) and isinstance(u2, Uncalibrated) and isinstance(u3, Uncalibrated)
      and len({u1.reason, u2.reason, u3.reason}) == 3)
line("CAL-008", "PASS" if ok else "FAIL", f"u1={u1.reason!r} u2={u2.reason!r} u3={u3.reason!r} all_distinct_types={ok}")

# CAL-010: non-finite calibration points dropped, n reflects it
scores10 = [float(i) for i in range(25)] + [float("nan")] * 5
c10 = ConformalCalibrator(scores10)
ok = c10.n == 25
line("CAL-010", "PASS" if ok else "FAIL", f"n={c10.n} (25 finite + 5 nan dropped)")

# CAL-011: performance -- 100k calibration points, 10k p-values within budget, uses bisect
big_scores = list(range(100_000))
c11 = ConformalCalibrator(big_scores)
t0 = time.time()
for i in range(10_000):
    c11.p_value(i * 10)
elapsed = time.time() - t0
BUDGET = 10.0
ok = elapsed < BUDGET
line("CAL-011", "PASS" if ok else "FAIL", f"100k calib points, 10k p_value() calls: elapsed={elapsed:.3f}s budget={BUDGET}s")

# CAL-012: ties counted as at-least-as-extreme
scores12 = [10, 20, 30, 40] + [50]*10 + [60, 70, 80, 90, 100, 110, 120, 130, 140, 150]
c12 = ConformalCalibrator(scores12)
p12 = c12.p_value(50)
n12 = len(scores12)
at_least12 = sum(1 for s in scores12 if s >= 50)  # all 10 fifties + everything above
expected12 = (1 + at_least12) / (n12 + 1)
ok = isinstance(p12, ConformalP) and abs(p12.value - expected12) < 1e-9
line("CAL-012", "PASS" if ok else "FAIL", f"p_value(50)={p12.value if isinstance(p12,ConformalP) else p12} at_least={at_least12} expected={expected12}")

# CAL-013: observation below everything gives p-value of 1.0
scores13 = list(range(1, 51))  # 1..50
c13 = ConformalCalibrator(scores13)
p13 = c13.p_value(0)  # below everything
ok = isinstance(p13, ConformalP) and abs(p13.value - 1.0) < 1e-12
line("CAL-013", "PASS" if ok else "FAIL", f"p_value(below_all)={p13.value if isinstance(p13,ConformalP) else p13}")

# CAL-014: recency weights ascending, last=1.0, 50th from end=0.5
# NOTE (round 3): w[-1] is age 0 (the most recent); w[-k] is age k-1. Fifty
# half-lives back is age 50, i.e. w[-51], not w[-50] (age 49) -- the original
# check was off by one position under a 1-indexed-from-the-end reading. A
# harness bug, not a product defect (round 2's own published verdict already
# made this correction: w[-51] == 0.5 exactly).
w = recency_weights(100, half_life=50)
ok = (w[-1] == 1.0 and abs(w[-51] - 0.5) < 1e-9 and all(w[i] <= w[i+1] for i in range(len(w)-1)))
line("CAL-014", "PASS" if ok else "FAIL", f"w[-1]={w[-1]} w[-51]={w[-51]:.6f} (age 50 == half_life) ascending={all(w[i]<=w[i+1] for i in range(len(w)-1))}")

# CAL-015: recency_weights(0) empty, half_life=0 doesn't divide by zero
w0 = recency_weights(0)
try:
    w_zero_hl = recency_weights(10, half_life=0)
    finite = all(math.isfinite(x) for x in w_zero_hl)
except ZeroDivisionError:
    finite = False
ok = w0 == () and finite
line("CAL-015", "PASS" if ok else "FAIL", f"recency_weights(0)={w0} recency_weights(10, half_life=0)_all_finite={finite}")

print("SECTION CAL-001..015 DONE")

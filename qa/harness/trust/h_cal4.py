import sys, subprocess, math
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.calibrate.select import (
    Method, Level, Hypothesis, Finding, Selection, benjamini_hochberg, simes,
    _harmonic, HierarchicalSelector, ROLLUP_FRACTION, ROLLUP_MINIMUM, _parent_level,
    Budget, power_at, _normal_cdf, _normal_quantile,
)

r = subprocess.run(["python3", "-m", "pytest", "tests/calibrate/test_select.py", "-v"], capture_output=True, text=True, cwd="/home/ashutosh/PycharmProjects/prama")
out = r.stdout
def pyresult(name):
    for l in out.splitlines():
        if name in l: return "PASSED" in l
    return None
mapping = {
    "CAL-055": "test_bh_takes_the_largest_k_and_not_the_first_failure",
    "CAL-056": "test_bh_controls_the_false_discovery_rate",
    "CAL-057": "test_by_is_strictly_more_conservative_than_bh",
    "CAL-060": "test_simes_summarises_a_family_without_testing_each_member",
    "CAL-062": "test_a_quiet_family_is_never_opened",
    "CAL-064": "test_a_wholesale_failure_becomes_one_finding_rather_than_four_hundred",
    "CAL-065": "test_roll_up_is_decided_on_the_shape_of_the_failure_not_the_correction",
    "CAL-066": "test_a_partial_failure_is_not_rolled_up",
    "CAL-067": "test_a_small_family_is_never_rolled_up",
    "CAL-068": "test_the_roll_up_carries_the_family_p_value_not_the_worst_child",
    "CAL-072": "test_which_procedure_ran_and_what_it_assumes_is_on_the_result",
    "CAL-073": "test_a_business_budget_becomes_a_statistical_level",
    "CAL-076": "test_a_budget_the_history_cannot_honour_is_refused_with_the_arithmetic",
    "CAL-077": "test_an_achievable_budget_reports_no_shortfall",
}
for cid, testname in mapping.items():
    ok = pyresult(testname)
    matching = [l.strip() for l in out.splitlines() if testname in l]
    line(cid, "PASS" if ok else "FAIL", f"pytest tests/calibrate/test_select.py::{testname} -> {matching}")

# CAL-058: harmonic approximation agrees with exact sum at crossover (999, 1000, 1001)
for count in (999, 1000, 1001):
    exact = sum(1.0/i for i in range(1, count+1))
    approx = _harmonic(count)
    diff = abs(exact - approx)
    if count == 999:
        r999 = (exact, approx, diff)
    elif count == 1000:
        r1000 = (exact, approx, diff)
    else:
        r1001 = (exact, approx, diff)
ok = all(d < 1e-6 for _, _, d in (r999, r1000, r1001))
line("CAL-058", "PASS" if ok else "FAIL", f"999: exact={r999[0]:.8f} approx={r999[1]:.8f} diff={r999[2]:.2e}; 1000: diff={r1000[2]:.2e}; 1001: diff={r1001[2]:.2e}")

# CAL-059: _harmonic(0) and _harmonic(1) are safe, both 1.0
ok = _harmonic(0) == 1.0 and _harmonic(1) == 1.0
line("CAL-059", "PASS" if ok else "FAIL", f"_harmonic(0)={_harmonic(0)} _harmonic(1)={_harmonic(1)}")

# CAL-061: simes of empty family is 1.0
ok = simes([]) == 1.0
line("CAL-061", "PASS" if ok else "FAIL", f"simes([])={simes([])}")

# CAL-063: within-family level scaled by families survived (20 families, 4 opened, alpha 0.05 -> 0.01)
leaves = []
for i in range(16):  # 16 quiet families -- high p-values, family Simes p-value will be high, family not opened
    leaves.extend([Hypothesis(f"q{i}.c{j}", 0.9, Level.CHECK, parent=f"dataset{i}") for j in range(5)])
for i in range(16, 20):  # 4 failing families -- low p-values everywhere, family opens
    leaves.extend([Hypothesis(f"f{i}.c{j}", 0.0005, Level.CHECK, parent=f"dataset{i}") for j in range(5)])
sel = HierarchicalSelector(method=Method.BH)
result = sel.select(leaves, alpha=0.05)
ok_families = result.families_unopened == 16
thresholds = {f.threshold for f in result.findings}
scaled_expected = 0.05 * (4/20)  # 0.01
matches_scaled = any(abs(t - scaled_expected) < 1e-9 for t in thresholds)
line("CAL-063", "PASS" if (ok_families and matches_scaled) else "FAIL",
     f"families_unopened={result.families_unopened} (expected 16 of 20) thresholds_seen={thresholds} expected_scaled_level={scaled_expected} matches={matches_scaled}")

# CAL-069: rolled-up finding reported one level up; DOMAIN clamps to DOMAIN
ok = _parent_level(Level.CHECK) == Level.ATTRIBUTE and _parent_level(Level.DOMAIN) == Level.DOMAIN
line("CAL-069", "PASS" if ok else "FAIL", f"_parent_level(CHECK)={_parent_level(Level.CHECK)} _parent_level(DOMAIN)={_parent_level(Level.DOMAIN)}")

# CAL-070: findings ordered by p-value then identity, deterministic across shuffles
import random
hyps = [Hypothesis(f"h{i}", 0.001, Level.CHECK, parent="") for i in range(10)]
random.seed(1); shuffled1 = list(hyps); random.shuffle(shuffled1)
random.seed(99); shuffled2 = list(hyps); random.shuffle(shuffled2)
sel2 = HierarchicalSelector()
r1 = sel2.select(shuffled1, alpha=0.5)
r2 = sel2.select(shuffled2, alpha=0.5)
order1 = [f.test.identity for f in r1.findings]
order2 = [f.test.identity for f in r2.findings]
ok = order1 == order2
line("CAL-070", "PASS" if ok else "FAIL", f"order1={order1} order2={order2} identical={ok}")

# CAL-071: selecting nothing returns empty Selection with a proper summary
sel3 = HierarchicalSelector()
r_empty = sel3.select([], alpha=0.05)
r_none_reject = sel3.select([Hypothesis("a", 0.99, Level.CHECK, parent="")], alpha=0.01)
ok = (len(r_empty.findings) == 0 and r_empty.method is not None and "0" in r_empty.describe()
      and len(r_none_reject.findings) == 0)
line("CAL-071", "PASS" if ok else "FAIL", f"empty_findings={len(r_empty.findings)} describe={r_empty.describe()!r} non_rejecting_findings={len(r_none_reject.findings)}")

# CAL-074: budget over zero tests is 0.0
b74 = Budget(false_alarms=2, tests_per_period=0)
ok = b74.alpha == 0.0
line("CAL-074", "PASS" if ok else "FAIL", f"Budget(false_alarms=2, tests_per_period=0).alpha={b74.alpha}")

# CAL-075: budget more generous than one alarm per test is capped at 1.0
b75 = Budget(false_alarms=100, tests_per_period=10)
ok = b75.alpha == 1.0
line("CAL-075", "PASS" if ok else "FAIL", f"Budget(false_alarms=100, tests_per_period=10).alpha={b75.alpha}")

# CAL-078: power labelled approximate wherever it appears
import inspect
power_doc = power_at.__doc__ or ""
ok = "approxim" in power_doc.lower()
line("CAL-078", "PASS" if ok else "FAIL", f"power_at docstring mentions approximation: {ok} docstring={power_doc[:150]!r}")

# CAL-079: power monotone in effect size and alpha, bounded [0,1], zero effect ~ alpha
vals_effect = [power_at(0.05, e, 1000) for e in (0, 1, 2, 3)]
vals_alpha = [power_at(a, 2.0, 1000) for a in (0.01, 0.05)]
monotone_effect = all(vals_effect[i] <= vals_effect[i+1] for i in range(len(vals_effect)-1))
monotone_alpha = vals_alpha[0] <= vals_alpha[1]
bounded = all(0.0 <= v <= 1.0 for v in vals_effect + vals_alpha)
zero_effect_approx_alpha = abs(vals_effect[0] - 0.05) < 0.01
ok = monotone_effect and monotone_alpha and bounded and zero_effect_approx_alpha
line("CAL-079", "PASS" if ok else "FAIL", f"power_by_effect(0,1,2,3)={vals_effect} power_by_alpha(0.01,0.05)={vals_alpha} monotone_effect={monotone_effect} monotone_alpha={monotone_alpha} bounded={bounded} zero_effect~alpha={zero_effect_approx_alpha}")

# CAL-080: degenerate power inputs return 0.0, no infinity
p_n0 = power_at(0.05, 2.0, 0)
p_alpha0 = power_at(0.0, 2.0, 1000)
ok = p_n0 == 0.0 and p_alpha0 == 0.0 and math.isfinite(p_n0) and math.isfinite(p_alpha0)
line("CAL-080", "PASS" if ok else "FAIL", f"power_at(alpha=0.05, effect=2, n=0)={p_n0} power_at(alpha=0, effect=2, n=1000)={p_alpha0}")

print("SECTION CAL-055..080 DONE")

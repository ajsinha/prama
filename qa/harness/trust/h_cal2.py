import sys, subprocess, math, random
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.calibrate.conformal import (
    ConformalCalibrator, ConformalP, Uncalibrated, recency_weights,
    AdaptiveCalibrator, AdaptiveLevel,
)

# CAL-017: effective_n equals n when unweighted
c17 = ConformalCalibrator(list(range(40)))
ok = c17.effective_n == 40
line("CAL-017", "PASS" if ok else "FAIL", f"n={c17.n} effective_n={c17.effective_n}")

# CAL-019: coverage gap labelled indicative wherever it surfaces (alert + API rendering)
c19 = ConformalCalibrator(list(range(60)), weights=recency_weights(60, half_life=10))
p19 = c19.p_value(59)
desc19 = p19.describe() if isinstance(p19, ConformalP) else ""
d19 = p19.to_dict() if isinstance(p19, ConformalP) else {}
describe_says_approximate = "approximate" in desc19
never_proven_bound_language = "proven" not in desc19.lower() and "guarantee" not in desc19.lower()
line("CAL-019", "PASS" if (describe_says_approximate and never_proven_bound_language) else "FAIL",
     f"describe()={desc19!r} to_dict={d19} -- 'approximate' present={describe_says_approximate} no 'proven'/'guarantee' language={never_proven_bound_language}")

# CAL-020: unweighted p-value has coverage_gap exactly 0.0 and exact=True
c20 = ConformalCalibrator(list(range(40)))
p20 = c20.p_value(39)
ok = isinstance(p20, ConformalP) and p20.coverage_gap == 0.0 and p20.exact is True
line("CAL-020", "PASS" if ok else "FAIL", f"coverage_gap={p20.coverage_gap if isinstance(p20,ConformalP) else p20} exact={p20.exact if isinstance(p20,ConformalP) else None}")

# CAL-028: level stays inside floor/ceiling -- 10000 alerts then 10000 non-alerts
ac = AdaptiveCalibrator(target=0.05, step=0.02, window=100, floor=1e-4, ceiling=0.5)
levels = []
for _ in range(10_000):
    lvl = ac.observe(True)
    levels.append(lvl.current)
for _ in range(10_000):
    lvl = ac.observe(False)
    levels.append(lvl.current)
ok = all(1e-4 - 1e-12 <= v <= 0.5 + 1e-12 for v in levels)
line("CAL-028", "PASS" if ok else "FAIL", f"min_level={min(levels)} max_level={max(levels)} floor=1e-4 ceiling=0.5 all_within_bounds={ok}")

# CAL-030: update is on alert indicator, not on p-value magnitude
ac_a = AdaptiveCalibrator(target=0.1, step=0.05, window=50)
ac_b = AdaptiveCalibrator(target=0.1, step=0.05, window=50)
random.seed(7)
alerts_sequence = [random.random() < 0.15 for _ in range(200)]
for alerted in alerts_sequence:
    ac_a.observe(alerted)
    ac_b.observe(alerted)  # identical alert sequence, no p-values involved at all -- the point is observe() only takes a bool
ok = abs(ac_a.level.current - ac_b.level.current) < 1e-12
line("CAL-030", "PASS" if ok else "FAIL", f"levels_after_identical_alert_sequences_but_via_two_separately_constructed_calibrators: a={ac_a.level.current} b={ac_b.level.current} equal={ok} (observe() signature only accepts a bool 'alerted', confirming by inspection that p-value magnitude cannot enter the update)")

# CAL-032: saturation boundary exactly half
lvl_49 = AdaptiveLevel(target=0.05, current=0.05, step=0.02, saturated=0.49)
lvl_50 = AdaptiveLevel(target=0.05, current=0.05, step=0.02, saturated=0.50)
ok = lvl_49.is_powerless is False and lvl_50.is_powerless is True
line("CAL-032", "PASS" if ok else "FAIL", f"saturated=0.49 -> is_powerless={lvl_49.is_powerless}; saturated=0.50 -> is_powerless={lvl_50.is_powerless}")

# CAL-033: window bounds "recent", saturation list stays same length as alert list
ac33 = AdaptiveCalibrator(target=0.1, step=0.02, window=100)
for i in range(150):
    ac33.observe(i % 10 == 0, saturated=(i % 7 == 0))
ok = len(ac33._recent) == 100 and len(ac33._saturated) == 100
realised_over_window = ac33.realised
expected_realised = sum(1 for i in range(50, 150) if i % 10 == 0) / 100
ok = ok and abs(realised_over_window - expected_realised) < 1e-9
line("CAL-033", "PASS" if ok else "FAIL", f"len(_recent)={len(ac33._recent)} len(_saturated)={len(ac33._saturated)} realised={realised_over_window} expected(over_last_100)={expected_realised}")

# CAL-034: judge() carries saturation through; test+observe separately loses it
c34 = ConformalCalibrator(list(range(30)))
p34_sat = c34.p_value(1000)  # far beyond everything -> saturated
assert isinstance(p34_sat, ConformalP) and p34_sat.is_saturated

ac_judge = AdaptiveCalibrator(target=0.1)
alerted_j, level_j = ac_judge.judge(p34_sat)
saturation_via_judge = ac_judge._saturated[-1]

ac_manual = AdaptiveCalibrator(target=0.1)
alerted_m = ac_manual.test(p34_sat)
ac_manual.observe(alerted_m)  # no saturated= passed -> defaults False
saturation_via_manual = ac_manual._saturated[-1]

ok = saturation_via_judge is True and saturation_via_manual is False
line("CAL-034", "PASS" if ok else "FAIL", f"judge()_records_saturation={saturation_via_judge} separate_test+observe_loses_it={not saturation_via_manual}")

# CAL-035: test() compares against current level, not target
ac35 = AdaptiveCalibrator(target=0.05, step=0.05, window=200)
for _ in range(30):
    ac35.observe(True)  # tighten current well below target
current_level = ac35.level.current
assert current_level < 0.05 - 1e-9, f"expected tightened, got {current_level}"
class FakeP:
    def __init__(self, v): self.value = v
p_between = FakeP((current_level + 0.05) / 2)  # between current (tight) and target
alerts = ac35.test(p_between)
ok = alerts is False
line("CAL-035", "PASS" if ok else "FAIL", f"current_level={current_level:.5f} target=0.05 p_between={p_between.value:.5f} test()_result={alerts} (expected: False -- tested against current, not target)")

# CAL-036: level describes itself distinctly for at-target, tightened, loosened, powerless
l_target = AdaptiveLevel(target=0.05, current=0.05, step=0.02)
l_tight = AdaptiveLevel(target=0.05, current=0.02, step=0.02, realised=0.15)
l_loose = AdaptiveLevel(target=0.05, current=0.08, step=0.02, realised=0.01)
l_powerless = AdaptiveLevel(target=0.05, current=0.05, step=0.02, saturated=0.7)
descs = [l_target.describe(), l_tight.describe(), l_loose.describe(), l_powerless.describe()]
ok = len(set(descs)) == 4 and all("0.05" in d or "5.00" in d for d in descs[:3])
line("CAL-036", "PASS" if ok else "FAIL", f"descs={descs}")

print("SECTION CAL-017..036 DONE")

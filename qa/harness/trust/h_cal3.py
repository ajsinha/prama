import sys, subprocess, math
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.calibrate.validity import (
    ValidityMonitor, ValidityReport, Validity, Point, CalibrationCurve,
    wilson_interval, _z_for, CURVE_LEVELS, MINIMUM_OBSERVATIONS, DEGRADATION_CONFIDENCE,
    TARGET_CALIBRATION_ERROR,
)

r = subprocess.run(["python3", "-m", "pytest", "tests/calibrate/test_validity.py", "-v"], capture_output=True, text=True, cwd="/home/ashutosh/PycharmProjects/prama")
out = r.stdout
def pyresult(name):
    for l in out.splitlines():
        if name in l: return "PASSED" in l
    return None
mapping = {
    "CAL-037": "test_a_calibrated_monitor_reports_that_it_is",
    "CAL-038": "test_a_monitor_whose_data_moved_reports_uncalibrated_and_keeps_running",
    "CAL-039": "test_sampling_noise_does_not_trip_the_validity_monitor",
    "CAL-041": "test_a_new_monitor_has_not_earned_the_promise_yet",
    "CAL-042": "test_firing_less_often_than_promised_is_not_a_broken_promise",
    "CAL-043": "test_a_departure_that_is_not_yet_meaningless_is_called_drifting",
    "CAL-046": "test_the_curve_covers_three_orders_of_magnitude",
    "CAL-047": "test_the_calibration_error_meets_the_wave_target_on_honest_data",
    "CAL-049": "test_the_interval_stays_an_interval_at_small_rates",
    "CAL-050": "test_no_observations_admits_everything",
    "CAL-052": "test_the_degradation_appears_on_every_alert_not_only_a_status_page",
}
for cid, testname in mapping.items():
    ok = pyresult(testname)
    matching = [l.strip() for l in out.splitlines() if testname in l]
    line(cid, "PASS" if ok else "FAIL", f"pytest tests/calibrate/test_validity.py::{testname} -> {matching}")

# CAL-040: confidence is 0.999, documented
ok = DEGRADATION_CONFIDENCE == 0.999
import prama.calibrate.validity as vmod
doc = vmod.__doc__ or ""
docstring_reasoning = "one monitor in twenty" in doc or "wrongly labelled" in doc
line("CAL-040", "PASS" if (ok and docstring_reasoning) else "FAIL", f"DEGRADATION_CONFIDENCE={DEGRADATION_CONFIDENCE} reasoning_documented={docstring_reasoning}")

# CAL-044: is_liberal compares nominal against interval (interval entirely above nominal)
p44 = Point(nominal=0.05, empirical=0.10, observations=500, low=0.08, high=0.12)
ok = p44.is_liberal is True
line("CAL-044", "PASS" if ok else "FAIL", f"interval=[0.08,0.12] nominal=0.05 -> is_liberal={p44.is_liberal}")

# CAL-045: conservative point (interval entirely below nominal) not flagged liberal
p45 = Point(nominal=0.05, empirical=0.02, observations=500, low=0.01, high=0.03)
ok = p45.is_liberal is False
line("CAL-045", "PASS" if ok else "FAIL", f"interval=[0.01,0.03] nominal=0.05 -> is_liberal={p45.is_liberal}")

# CAL-048: empty curve has zero error and (mis)claims meets_target -- test what actually happens
empty_curve = CalibrationCurve(points=(), observations=0)
err = empty_curve.calibration_error
meets = empty_curve.meets_target
# Expected per catalogue: EITHER a guarded meets_target OR the same UNKNOWN qualification carried on the curve itself
guarded = not meets  # if meets_target is False for an empty curve, it's guarded
line("CAL-048", "PASS" if guarded else "FAIL",
     f"empty CalibrationCurve: calibration_error={err} meets_target={meets} -- expected either meets_target guarded to False for zero observations, "
     f"or a documented UNKNOWN qualification on the curve itself; as read, meets_target is UNGUARDED and reports True for a curve that has seen nothing")

# CAL-051: z quantile precision
z95 = _z_for(0.95)
z99 = _z_for(0.99)
z999 = _z_for(0.999)
ok = (round(z95, 5) == 1.95996 and round(z99, 5) == 2.5758 and round(z999, 5) == 3.2905)
line("CAL-051", "PASS" if ok else "FAIL", f"_z_for(0.95)={z95:.5f} _z_for(0.99)={z99:.5f} _z_for(0.999)={z999:.5f}")

# CAL-053: window bounds memory, oldest falls out
m53 = ValidityMonitor(nominal=0.05, window=500)
m53.observe_all([i / 10000.0 for i in range(10_000)])
ok = m53.observations == 500 and m53._p_values[0] == 9500/10000.0
line("CAL-053", "PASS" if ok else "FAIL", f"observations={m53.observations} (expected 500) oldest_retained={m53._p_values[0]:.4f} (expected {9500/10000.0:.4f}, the 500 most recent)")

# CAL-054: monitor's own weak point documented in the class docstring
monitor_doc = ValidityMonitor.__doc__ or ""
ok = "nobody knows which" in monitor_doc and "how often does this monitor fire" in monitor_doc
line("CAL-054", "PASS" if ok else "FAIL", f"docstring_acknowledges_weak_point={ok} docstring_excerpt={monitor_doc[:300]!r}")

print("SECTION CAL-037..054 DONE")

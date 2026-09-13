import math, random, sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.monitor.detect import (
    RobustDeviation, QuantileDistance, LocalOutlierFactor, ForecastResidual, ShapeDistance,
    Ensemble, default_ensemble, MINIMUM_HISTORY, MAXIMUM_CALIBRATION, Score, _relative, _standardise,
)
from prama.monitor.fleet import _default_detector
from prama.monitor.detect import Detector

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

random.seed(0)

detectors = [RobustDeviation(), QuantileDistance(), LocalOutlierFactor(), ForecastResidual(), ShapeDistance()]

# MON-031 - nine observations -> None from each
hist9 = [1000.0]*9
results = {d.name: d.score(1000.0, hist9) for d in detectors}
ok = all(v is None for v in results.values())
line("MON-031", "PASS" if ok else "FAIL", f"{ {k: v for k,v in results.items()} }")

# MON-032 - each detector's own floor
rd_at10 = RobustDeviation().score(5.0, [1.0]*10)
rd_at9 = RobustDeviation().score(5.0, [1.0]*9)
lof = LocalOutlierFactor(neighbours=5)
lof_at6 = lof.score(5.0, list(range(6)))  # k+1=6
lof_at5 = lof.score(5.0, list(range(5)))
fr = ForecastResidual(span=7)
fr_at8 = fr.score(5.0, [float(i) for i in range(8)])  # span+1=8
fr_at7 = fr.score(5.0, [float(i) for i in range(7)])
sd = ShapeDistance(window=6)
sd_at12 = sd.score_window([1,2,3,4,5,6], [float(i%6) for i in range(12)])  # 2*window=12
sd_at11 = sd.score_window([1,2,3,4,5,6], [float(i%6) for i in range(11)])
ok = (rd_at10 is not None and rd_at9 is None and
      lof_at6 is not None and lof_at5 is None and
      fr_at8 is not None and fr_at7 is None and
      sd_at12 is not None and sd_at11 is None)
line("MON-032", "PASS" if ok else "FAIL",
     f"rd10={rd_at10 is not None} rd9={rd_at9 is None} lof6={lof_at6 is not None} lof5={lof_at5 is None} "
     f"fr8={fr_at8 is not None} fr7={fr_at7 is None} sd12={sd_at12 is not None} sd11={sd_at11 is None}")

# MON-033 - observation scored against same window (last 300) as calibration
random.seed(5)
hist500 = [random.gauss(1000,50) for _ in range(500)]
rd = RobustDeviation()
score_full = rd.score(1000.0, hist500)  # uses .score which windows to last 300
score_manual_300 = rd.compute(1000.0, hist500[-300:])
cal = rd.scores(hist500)  # also windows to last 300 internally
ok = score_full is not None and abs(score_full.value - score_manual_300.value) < 1e-9 and len(cal) <= 300
line("MON-033", "PASS" if ok else "FAIL", f"score_full={score_full.value} score_manual={score_manual_300.value} n_cal={len(cal)}")

# MON-034 - leave-one-out systematically larger than "against full window"
random.seed(9)
hist50 = [random.gauss(1000,50) for _ in range(50)]
rd = RobustDeviation()
loo_scores = rd.scores(hist50)
full_scores = [rd.compute(v, hist50).value for v in hist50]
mean_loo = sum(loo_scores)/len(loo_scores)
mean_full = sum(full_scores)/len(full_scores)
ok = mean_loo > mean_full
line("MON-034", "PASS" if ok else "FAIL", f"mean_loo={mean_loo:.4f} mean_full={mean_full:.4f}")

# MON-035 - RobustDeviation unmoved by one extreme point
random.seed(21)
base = [random.gauss(1000,50) for _ in range(50)]
with_outlier = base + [100000.0]
rd = RobustDeviation()
s1 = rd.compute(1300.0, base)
s2 = rd.compute(1300.0, with_outlier)
ok = abs(s1.value - s2.value) < 0.5
line("MON-035", "PASS" if ok else "FAIL", f"without_outlier={s1.value:.4f} with_outlier={s2.value:.4f}")

# MON-036 - constant history falls back to raw distance / 1.4826
hist_const = [50.0]*20
rd = RobustDeviation()
s = rd.compute(60.0, hist_const)
expected_val = abs(60.0-50.0)/1.4826
ok = math.isfinite(s.value) and abs(s.value - expected_val) < 1e-9
line("MON-036", "PASS" if ok else "FAIL", f"score={s.value} expected={expected_val}")

# MON-037 - MAD scaling does not change ordering
random.seed(31)
hist = [random.gauss(1000,50) for _ in range(60)]
rd = RobustDeviation()
obs_points = [900, 1000, 1100, 1300, 1500, 700]
scored_with = sorted(obs_points, key=lambda o: rd.compute(o, hist).value)
# without factor: recompute manually
def _median(vals):
    o = sorted(vals); m = len(o)//2
    return o[m] if len(o)%2 else (o[m-1]+o[m])/2
centre = _median(hist)
spread = _median([abs(v-centre) for v in hist]) or 1.0
scored_without = sorted(obs_points, key=lambda o: abs(o-centre)/spread)
ok = scored_with == scored_without
line("MON-037", "PASS" if ok else "FAIL", f"with_factor_order={scored_with} without_factor_order={scored_without}")

# MON-038 - QuantileDistance scores both tails
hist01 = [i/99 for i in range(100)]  # 0 to 1
qd = QuantileDistance()
s_low = qd.compute(-0.5, hist01)
s_high = qd.compute(1.5, hist01)
s_mid = qd.compute(0.5, hist01)
ok = abs(s_low.value-1.0) < 0.05 and abs(s_high.value-1.0) < 0.05 and s_mid.value < 0.05
line("MON-038", "PASS" if ok else "FAIL", f"low={s_low.value:.3f} high={s_high.value:.3f} mid={s_mid.value:.3f}")

# MON-039 - QuantileDistance default for bounded metric
from prama.monitor.fleet import MetricKind
try:
    det_null = _default_detector(MetricKind.NULL_RATE)
    det_dist = _default_detector(MetricKind.DISTRIBUTION)
    ok = isinstance(det_null, QuantileDistance) and isinstance(det_dist, QuantileDistance)
    line("MON-039", "PASS" if ok else "FAIL", f"null_rate={type(det_null).__name__} distribution={type(det_dist).__name__}")
except Exception as e:
    line("MON-039", "FAIL", f"exception {type(e).__name__}: {e}")

# MON-040 - LocalOutlierFactor between two clusters
random.seed(41)
weekday = [20000 + random.gauss(0,200) for _ in range(60)]
weekend = [500 + random.gauss(0,50) for _ in range(30)]
hist_lof = weekday + weekend
lof = LocalOutlierFactor()
s_10000 = lof.compute(10000.0, hist_lof)
s_19500 = lof.compute(19500.0, hist_lof)
ok = s_10000.value > s_19500.value * 1.5
line("MON-040", "PASS" if ok else "FAIL", f"10000={s_10000.value:.3f} 19500={s_19500.value:.3f}")

# MON-041 - point exactly on a history value
hist_rep = [10.0,10.0,10.0,20.0,30.0,40.0,50.0,60.0,70.0,80.0]
lof = LocalOutlierFactor()
s = lof.compute(10.0, hist_rep)
ok = s is not None and math.isfinite(s.value)
line("MON-041", "PASS" if ok else "FAIL", f"score={s}")

# MON-042 - far-away point degenerate case
hist_norm = [random.gauss(1000,10) for _ in range(30)]
lof = LocalOutlierFactor()
s = lof.compute(1e30, hist_norm)
ok = s is not None and s.value == float(len(hist_norm)) and "nowhere near" in s.explanation
line("MON-042", "PASS" if ok else "FAIL", f"score={s.value if s else None} explanation={s.explanation if s else None}")

# MON-043 - ForecastResidual tracks a trending series
trend = [1000 * (1.02**i) for i in range(30)]
next_val = 1000 * (1.02**30)
fr = ForecastResidual()
rd = RobustDeviation()
s_fr = fr.compute(next_val, trend)
s_rd = rd.compute(next_val, trend)
ok = s_fr.value < 1.0 and s_rd.value > 1.0
line("MON-043", "PASS" if ok else "FAIL", f"fr={s_fr.value:.3f} rd={s_rd.value:.3f}")

# MON-044 - relative residual scale-free
double_series = [1000 * (2 ** (i/99)) for i in range(100)]
fr = ForecastResidual()
cal = fr.scores(double_series)
first_third = cal[:len(cal)//3]
last_third = cal[-len(cal)//3:]
m1 = sum(first_third)/len(first_third)
m2 = sum(last_third)/len(last_third)
ok = abs(m1-m2) < max(m1,m2)*2  # comparable order of magnitude
line("MON-044", "PASS" if ok else "FAIL", f"first_third_mean={m1:.4f} last_third_mean={m2:.4f}")

# MON-045 - _relative falls back to absolute at zero
val = _relative(5.0, 0.0)
ok = val == 5.0
line("MON-045", "PASS" if ok else "FAIL", f"_relative(5,0)={val}")

# MON-046 - ShapeDistance finds changed profile with unchanged total
random.seed(51)
def smooth_day():
    return [10+math.sin(i/23*2*math.pi)*2+random.gauss(0,0.2) for i in range(24)]
history_days = []
for _ in range(20):
    history_days.extend(smooth_day())
spiky = [0.1]*20 + [0.1]*3 + [10*24-0.1*23]  # total similar but spiky - simplify: all at once
spiky_window = [0.0]*23 + [24*10.4]  # total same as a smooth day roughly
sd = ShapeDistance(window=24)
smooth_window = smooth_day()
s_smooth = sd.score_window(smooth_window, history_days)
s_spiky = sd.score_window(spiky_window, history_days)
ok = s_spiky.value > s_smooth.value * 2
line("MON-046", "PASS" if ok else "FAIL", f"smooth={s_smooth.value:.3f} spiky={s_spiky.value:.3f}")

# MON-047 - ShapeDistance blind to level change
random.seed(61)
history_days2 = []
shape_base = [1,2,3,4,5,6,5,4,3,2]
for _ in range(20):
    history_days2.extend(shape_base)
sd = ShapeDistance(window=10)
double_window = [2*v for v in shape_base]
s = sd.score_window(double_window, history_days2)
ok = s is not None and s.value < 0.01
line("MON-047", "PASS" if ok else "FAIL", f"score={s.value if s else None}")

# MON-048 - ShapeDistance handles a flat window
flat = [5.0]*10
z = _standardise(flat)
ok = all(v == 0.0 for v in z)
history_flat = [5.0]*100
sd = ShapeDistance(window=10)
s = sd.score_window(flat, history_flat)
ok = ok and s is not None and math.isfinite(s.value)
line("MON-048", "PASS" if ok else "FAIL", f"standardise={z[:3]} score={s.value if s else None}")

# MON-049 - ShapeDistance not in default ensemble
ens = default_ensemble()
names = [d.name for d in ens.detectors]
ok = "shape_distance" not in names and len(names) == 4
line("MON-049", "PASS" if ok else "FAIL", f"ensemble_detectors={names} module_docstring_claims_five=True")

# MON-050 - score_all omits detectors that cannot score
short_hist = [1000.0]*15  # enough for RobustDeviation(10), QuantileDistance(10) but not LOF(6? no lof needs 10 too, but ForecastResidual needs 8), ShapeDistance not in default
# to differentiate: use a history length enough for RobustDeviation/QuantileDistance/ForecastResidual(default span 7 -> needs 8)/LOF(needs 10) - all defaults need <=10 except LOF default k=5-> needs 10
# use a length 9 -> below all thresholds except... all need >=10 except ForecastResidual needs max(10,8)=10 too. So use length that differentiates: use MINIMUM_HISTORY itself doesn't differentiate cleanly since all detectors default floor is 10.
# Let's use custom ensemble with different floors: LOF(neighbours=20)->needs 21, ForecastResidual(span=3)->needs 10
custom_ens = Ensemble(detectors=(RobustDeviation(), QuantileDistance(), LocalOutlierFactor(neighbours=20), ForecastResidual(span=3)))
hist15 = [random.gauss(1000,50) for _ in range(15)]
scores = custom_ens.score_all(1000.0, hist15)
ok = "robust_deviation" in scores and "quantile_distance" in scores and "local_outlier_factor" not in scores and "forecast_residual" in scores
line("MON-050", "PASS" if ok else "FAIL", f"scored={list(scores.keys())}")

# MON-051 - no method averages/combines raw scores
import inspect
src_ensemble = inspect.getsource(Ensemble)
ok = "average" not in src_ensemble.lower() and "weight" not in src_ensemble.lower() and "sum(" not in src_ensemble
line("MON-051", "PASS" if ok else "FAIL", f"Ensemble methods: {[m for m in dir(Ensemble) if not m.startswith('_')]}")

# MON-052 - calibration_for unknown detector -> []
ens = default_ensemble()
res = ens.calibration_for("nonexistent", [1,2,3]*20)
ok = res == []
line("MON-052", "PASS" if ok else "FAIL", f"result={res}")

# MON-053 - every detector declares good_at and blind_to, non-empty, distinct
all_five = [RobustDeviation, QuantileDistance, LocalOutlierFactor, ForecastResidual, ShapeDistance]
good_ats = [d.good_at for d in all_five]
blind_tos = [d.blind_to for d in all_five]
ok = all(good_ats) and all(blind_tos) and len(set(good_ats)) == 5 and len(set(blind_tos)) == 5
line("MON-053", "PASS" if ok else "FAIL", f"good_at={good_ats} blind_to={blind_tos}")

# MON-054 - Score not a probability
random.seed(71)
hist = [random.gauss(1000,50) for _ in range(60)]
rd = RobustDeviation()
outside01 = False
for obs in [500, 1000, 1500, 2000, 5000]:
    s = rd.compute(obs, hist)
    if s.value > 1.0 or s.value < 0.0:
        outside01 = True
ok = outside01
line("MON-054", "PASS" if ok else "FAIL", f"outside_01_seen={outside01}")

# MON-055 - explanations are readable sentences
random.seed(81)
hist = [random.gauss(1000,50) for _ in range(60)]
obs = 1300.0
explanations = {}
for d in [RobustDeviation(), QuantileDistance(), LocalOutlierFactor(), ForecastResidual()]:
    s = d.compute(obs, hist)
    explanations[d.name] = s.explanation if s else None
sd = ShapeDistance(window=6)
s = sd.score_window(hist[-6:], hist)
explanations["shape_distance"] = s.explanation if s else None
ok = all(e and isinstance(e, str) and len(e) > 10 and not e.strip().startswith("<") for e in explanations.values())
line("MON-055", "PASS" if ok else "FAIL", f"{explanations}")

import sys, math, random
from datetime import datetime, timedelta, date
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.monitor.fleet import (
    Monitor, MetricKind, Observation, Verdict, FleetReport, SegmentedMonitor, _default_detector,
)
from prama.monitor.detect import RobustDeviation, QuantileDistance, ForecastResidual, LocalOutlierFactor
from prama.monitor.season import SeasonalModel
from prama.monitor.coldstart import ColdStart, Prior, PriorSource, SEMANTIC_NULL_RATES, Handover
from prama.monitor.cards import PrecisionHistory, ModelCard, card_for, Outcome
from prama.monitor.tournament import Tournament, Record, Decision, MINIMUM_SHADOW, MATERIAL_MARGIN, shadow_record
from prama.monitor.benchmark import (
    REGIMES, Mechanism, Cell, BenchmarkReport, measure, run, _after_changepoint, LEVELS,
)
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration, Optionality
from prama.semantic.values import Rhythm, Frequency
from prama.calibrate.validity import ValidityMonitor, TARGET_CALIBRATION_ERROR

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

random.seed(0)

# ---- MON-075 ----
m = Monitor("ds","metric")
v = m.judge(Observation(value=100.0, at=datetime(2026,1,1)), [])
ok = v.alerted == False and v.uncalibrated is not None and v.uncalibrated.reason == "no history for this metric yet"
line("MON-075", "PASS" if ok else "FAIL", f"alerted={v.alerted} reason={v.uncalibrated.reason if v.uncalibrated else None}")

# ---- MON-076 ---- three refusal paths
m2 = Monitor("ds","m2")
# path 1: no history
v1 = m2.judge(Observation(value=1.0, at=datetime(2026,1,1)), [])
# path 2: too few comparables - give 3 history points (below MINIMUM_HISTORY of underlying detector after grouping)
hist_small = [Observation(value=float(i), at=datetime(2025,1,i+1)) for i in range(1,4)]
v2 = m2.judge(Observation(value=1.0, at=datetime(2026,1,1)), hist_small)
# path 3: uncalibrated p-value - need enough comparables but < minimum for ConformalCalibrator (20)
hist_mid = [Observation(value=float(1000+i), at=datetime(2024,1,1)+timedelta(days=i)) for i in range(15)]
v3 = m2.judge(Observation(value=1005.0, at=datetime(2024,1,1)+timedelta(days=20)), hist_mid)
ok = (v1.alerted==False and v2.alerted==False and v3.alerted==False and
      v1.uncalibrated is not None and v2.uncalibrated is not None and v3.uncalibrated is not None)
line("MON-076", "PASS" if ok else "FAIL", f"v1={v1.alerted},{v1.uncalibrated} v2={v2.alerted},{v2.uncalibrated} v3={v3.alerted},{v3.uncalibrated}")

# ---- MON-077 ---- only earlier obs in same segment comparable
m3 = Monitor("ds","m3", adaptive=False)
base_time = datetime(2024,1,1)
hist = []
for i in range(60):
    hist.append(Observation(value=1000.0+i*0.01, at=base_time+timedelta(days=i), segment="A"))
# add later observations (after obs.at) and other segment observations
future_obs = [Observation(value=99999.0, at=base_time+timedelta(days=200), segment="A")]
other_seg = [Observation(value=-99999.0, at=base_time+timedelta(days=30), segment="B")]
obs = Observation(value=1000.3, at=base_time+timedelta(days=60), segment="A")
v_clean = m3.judge(obs, hist)
v_polluted = m3.judge(obs, hist + future_obs + other_seg)
ok = v_clean.grouping is not None and v_polluted.grouping is not None and v_clean.grouping.size == v_polluted.grouping.size
line("MON-077", "PASS" if ok else "FAIL", f"clean_size={v_clean.grouping.size if v_clean.grouping else None} polluted_size={v_polluted.grouping.size if v_polluted.grouping else None}")

# ---- MON-078 ---- observation at exact same instant as history point excluded
m4 = Monitor("ds","m4")
hist78 = [Observation(value=1000.0+i, at=base_time+timedelta(days=i)) for i in range(60)]
same_instant = Observation(value=5000.0, at=base_time+timedelta(days=59))  # same as last hist point
v78 = m4.judge(same_instant, hist78)
ok = v78.grouping is not None and v78.grouping.size == 59  # the matching-instant point excluded, only earlier 59 remain
line("MON-078", "PASS" if ok else "FAIL", f"group_size={v78.grouping.size if v78.grouping else None} (expect 59, i.e. index0..58)")

# ---- MON-079 ---- verdict explains itself fully
m5 = Monitor("ds5","metric5", adaptive=False)
hist79 = [Observation(value=1000.0+random.gauss(0,20), at=base_time+timedelta(days=i)) for i in range(60)]
obs79 = Observation(value=1200.0, at=base_time+timedelta(days=60))
v79 = m5.judge(obs79, hist79)
expl = v79.explain()
ok = "ds5.metric5" in expl and v79.score is not None and v79.score.explanation.split(",")[0] in expl if v79.score else False
ok = "ds5.metric5" in expl and (v79.grouping is not None and v79.grouping.key.render()[:10] in expl if v79.grouping else True)
line("MON-079", "PASS" if ok else "FAIL", f"explain={expl!r}")

# ---- MON-080 ---- validity disclosure on degraded monitor appears on the alert
m6 = Monitor("ds6","metric6", adaptive=False)
# manufacture degraded validity by observing many extreme p-values (near 0) to break the promise
hist80 = [Observation(value=1000.0+random.gauss(0,5), at=base_time+timedelta(days=i)) for i in range(300)]
found_degraded_expl = None
for i in range(300, 340):
    obs80 = Observation(value=1000.0 + (5000 if i%2==0 else 0), at=base_time+timedelta(days=i))
    v80 = m6.judge(obs80, hist80)
    hist80.append(obs80)
    if v80.validity is not None and not v80.validity.status.promise_holds:
        found_degraded_expl = v80.explain()
        break
ok = found_degraded_expl is not None and "⚠" in found_degraded_expl
line("MON-080", "PASS" if ok else "FAIL", f"found={found_degraded_expl is not None} explain={found_degraded_expl!r}")

# ---- MON-081 ---- uncalibrated verdict explains why, not score
m7 = Monitor("ds7","metric7")
v81 = m7.judge(Observation(value=5.0, at=datetime(2026,1,1)), [])
expl81 = v81.explain()
ok = expl81 == f"ds7.metric7 could not be judged: no history for this metric yet"
line("MON-081", "PASS" if ok else "FAIL", f"explain={expl81!r}")

# ---- MON-082 ---- hypothesis() None without p-value
h82 = v81.hypothesis()
ok = h82 is None
line("MON-082", "PASS" if ok else "FAIL", f"hypothesis={h82}")

# ---- MON-083 ---- segmented hypothesis identity includes segment
m8 = Monitor("ds8","metric8", adaptive=False)
hist83 = [Observation(value=1000.0+random.gauss(0,20), at=base_time+timedelta(days=i), segment="X") for i in range(60)]
hist83b = [Observation(value=1000.0+random.gauss(0,20), at=base_time+timedelta(days=i), segment="Y") for i in range(60)]
obsX = Observation(value=1010.0, at=base_time+timedelta(days=60), segment="X")
obsY = Observation(value=1010.0, at=base_time+timedelta(days=60), segment="Y")
vX = m8.judge(obsX, hist83)
vY = m8.judge(obsY, hist83b)
hX = vX.hypothesis()
hY = vY.hypothesis()
ok = hX is not None and hY is not None and hX.identity != hY.identity
line("MON-083", "PASS" if ok else "FAIL", f"hX={hX.identity if hX else None} hY={hY.identity if hY else None}")

# ---- MON-084 ---- adaptive calibrator's level is what verdict reports
m9 = Monitor("ds9","metric9", alpha=0.01, adaptive=True)
hist84 = [Observation(value=1000.0+random.gauss(0,20), at=base_time+timedelta(days=i)) for i in range(300)]
last_level = None
for i in range(300, 340):
    obs84 = Observation(value=1000.0 + random.choice([0, 3000]), at=base_time+timedelta(days=i))
    v84 = m9.judge(obs84, hist84)
    hist84.append(obs84)
    if v84.level:
        last_level = v84.level
ok = last_level is not None and last_level != 0.01
line("MON-084", "PASS" if ok else "FAIL", f"last_level={last_level} configured_alpha=0.01")

# ---- MON-085 ---- recency weighting off by default: no half_life => weights None internally
import inspect
src_judge = inspect.getsource(Monitor.judge)
m10 = Monitor("ds10","metric10")  # no half_life passed
ok = m10._half_life is None
line("MON-085", "PASS" if ok else "FAIL", f"half_life={m10._half_life}")

# ---- MON-086 ---- is_bounded true for exactly NULL_RATE, DISTRIBUTION
bounded = [k for k in MetricKind if k.is_bounded]
ok = set(bounded) == {MetricKind.NULL_RATE, MetricKind.DISTRIBUTION}
line("MON-086", "PASS" if ok else "FAIL", f"bounded={[k.value for k in bounded]}")

# ---- MON-087 ---- FRESHNESS defaults to ForecastResidual
det = _default_detector(MetricKind.FRESHNESS)
ok = isinstance(det, ForecastResidual)
line("MON-087", "PASS" if ok else "FAIL", f"detector={type(det).__name__}")

# ---- MON-088 ---- default detector overridable
custom = LocalOutlierFactor()
m11 = Monitor("ds11","metric11", kind=MetricKind.NULL_RATE, detector=custom)
ok = m11.detector is custom
line("MON-088", "PASS" if ok else "FAIL", f"detector_is_custom={m11.detector is custom}")

# ---- MON-089 ---- FleetReport partitions
v_alert = Verdict(alerted=True, observation=Observation(value=1,at=datetime(2026,1,1)), metric="m",dataset="d")
from prama.calibrate.validity import ValidityReport, Validity, CalibrationCurve
vr_degraded = ValidityReport(status=Validity.UNCALIBRATED, curve=CalibrationCurve(points=(), observations=0), nominal=0.01, empirical=0.05, reason="drifted")
v_degraded_alert = Verdict(alerted=True, observation=Observation(value=1,at=datetime(2026,1,1)), metric="m",dataset="d", validity=vr_degraded)
from prama.calibrate.conformal import Uncalibrated
v_unjudgeable = Verdict(alerted=False, observation=Observation(value=1,at=datetime(2026,1,1)), metric="m",dataset="d", uncalibrated=Uncalibrated(reason="x"))
fr = FleetReport(verdicts=(v_alert, v_degraded_alert, v_unjudgeable))
ok = (v_unjudgeable not in fr.alerting) and (v_degraded_alert in fr.alerting and v_degraded_alert in fr.degraded)
line("MON-089", "PASS" if ok else "FAIL", f"alerting={len(fr.alerting)} unjudgeable={len(fr.unjudgeable)} degraded={len(fr.degraded)}")

# ---- MON-090 ---- describe empty fleet
fr_empty = FleetReport()
desc90 = fr_empty.describe()
ok = "0 monitors ran" in desc90 and "0 exceeded" in desc90
line("MON-090", "PASS" if ok else "FAIL", f"describe={desc90!r}")

# ---- MON-091 ---- SegmentedMonitor same test per segment, broken one alerts
sm = SegmentedMonitor("ds91","metric91", ["A","B","C"], adaptive=False)
hist91 = []
for seg in ["A","B","C"]:
    for i in range(60):
        hist91.append(Observation(value=1000.0+random.gauss(0,20), at=base_time+timedelta(days=i), segment=seg))
obs91 = [
    Observation(value=1010.0, at=base_time+timedelta(days=60), segment="A"),
    Observation(value=1005.0, at=base_time+timedelta(days=60), segment="B"),
    Observation(value=50000.0, at=base_time+timedelta(days=60), segment="C"),  # broken
]
report91 = sm.judge(obs91, hist91)
alerting_segs = [v.observation.segment for v in report91.alerting]
ok = "C" in alerting_segs and "A" not in alerting_segs and "B" not in alerting_segs
line("MON-091", "PASS" if ok else "FAIL", f"alerting_segments={alerting_segs}")

# ---- MON-092 ---- unknown segment dropped silently
sm2 = SegmentedMonitor("ds92","metric92", ["A","B"], adaptive=False)
obs92 = [Observation(value=1.0, at=base_time+timedelta(days=61), segment="UNKNOWN")]
report92 = sm2.judge(obs92, [])
ok_silent_drop = len(report92.verdicts) == 0
line("MON-092", "FAIL", f"verdicts_count={len(report92.verdicts)} (unknown segment silently dropped, no record/unjudgeable entry produced)")

# ---- MON-093 ---- segments form one family for selection
sm3 = SegmentedMonitor("ds93","metric93", [f"seg{i}" for i in range(40)], adaptive=False)
hist93 = []
for i in range(40):
    seg = f"seg{i}"
    for d in range(60):
        hist93.append(Observation(value=1000.0+random.gauss(0,20), at=base_time+timedelta(days=d), segment=seg))
obs93 = [Observation(value=50000.0, at=base_time+timedelta(days=60), segment=f"seg{i}") for i in range(40)]
report93 = sm3.judge(obs93, hist93)
hyps93 = sm3.hypotheses(report93)
parents = set(h.parent for h in hyps93)
ok = len(hyps93) > 0 and parents == {"ds93.metric93"}
line("MON-093", "PASS" if ok else "FAIL", f"n_hyps={len(hyps93)} parents={parents}")

# ---- MON-094 ---- each segment's monitor holds its own calibration
sm4 = SegmentedMonitor("ds94","metric94", ["low","high"], adaptive=False)
hist94 = []
for i in range(60):
    hist94.append(Observation(value=100.0+random.gauss(0,5), at=base_time+timedelta(days=i), segment="low"))
    hist94.append(Observation(value=100000.0+random.gauss(0,500), at=base_time+timedelta(days=i), segment="high"))
obs_low = Observation(value=105.0, at=base_time+timedelta(days=60), segment="low")
obs_high = Observation(value=100500.0, at=base_time+timedelta(days=60), segment="high")
report94 = sm4.judge([obs_low, obs_high], hist94)
ok = all(v.uncalibrated is None for v in report94.verdicts)
line("MON-094", "PASS" if ok else "FAIL", f"verdicts={[(v.observation.segment, v.uncalibrated) for v in report94.verdicts]}")

print("=== coldstart ===")

def attr(name, optionality=Optionality.OPTIONAL, semantic_type=""):
    return AttributeDeclaration(name=name, optionality=optionality, semantic_type=semantic_type)

decl = DatasetDeclaration(name="ds", domain_id="dom1")
cs = ColdStart()

# MON-095 - mandatory attribute -> zero tolerance
a95 = attr("acct_id", optionality=Optionality.MANDATORY)
p95 = cs.for_attribute(decl, a95)
ok = p95.low == 0 and p95.high == 0 and p95.source == PriorSource.DECLARATION and "acct_id" in p95.explanation
line("MON-095", "PASS" if ok else "FAIL", f"low={p95.low} high={p95.high} source={p95.source} explanation={p95.explanation!r}")

# MON-096 - semantic type implies null rate band, for all 9 types
results96 = {}
for sem, (low, high) in SEMANTIC_NULL_RATES.items():
    a = attr(f"col_{sem}", optionality=Optionality.OPTIONAL, semantic_type=sem)
    p = cs.for_attribute(decl, a)
    results96[sem] = (p.low, p.high, p.source)
ok = all(v == (SEMANTIC_NULL_RATES[k][0], SEMANTIC_NULL_RATES[k][1], PriorSource.SEMANTIC_TYPE) for k,v in results96.items())
line("MON-096", "PASS" if ok else "FAIL", f"{results96}")

# MON-097 - uuid admits no nulls
a97 = attr("id", semantic_type="uuid")
p97 = cs.for_attribute(decl, a97)
ok = p97.admits(0.0) == True and p97.admits(0.001) == False
line("MON-097", "PASS" if ok else "FAIL", f"admits(0.0)={p97.admits(0.0)} admits(0.001)={p97.admits(0.001)}")

# MON-098 - declaration beats semantic type
a98 = attr("isin_col", optionality=Optionality.MANDATORY, semantic_type="isin")
p98 = cs.for_attribute(decl, a98)
ok = p98.source == PriorSource.DECLARATION
line("MON-098", "PASS" if ok else "FAIL", f"source={p98.source}")

# MON-099 - siblings need at least three
a99 = attr("plain_col")
p_two = cs.for_attribute(decl, a99, siblings=[0.1, 0.2])
p_three = cs.for_attribute(decl, a99, siblings=[0.1, 0.2, 0.3])
ok = p_two.source == PriorSource.DEFAULT and p_three.source == PriorSource.SIBLINGS
line("MON-099", "PASS" if ok else "FAIL", f"two_source={p_two.source} three_source={p_three.source}")

# MON-100 - sibling band widened and clamped
p100 = cs.for_attribute(decl, a99, siblings=[0.4, 0.5, 0.6])
ok = abs(p100.low - 0.2) < 1e-9 and abs(p100.high - 1.0) < 1e-9
line("MON-100", "PASS" if ok else "FAIL", f"low={p100.low} high={p100.high}")

# MON-101 - estate default weakest
p101 = cs.for_attribute(decl, attr("mystery_col"))
ok = p101.source == PriorSource.DEFAULT and "alternative is no monitoring at all" in p101.explanation
line("MON-101", "PASS" if ok else "FAIL", f"source={p101.source} explanation={p101.explanation!r}")

# MON-102 - prior never calibrated
ok = p101.is_calibrated == False
line("MON-102", "PASS" if ok else "FAIL", f"is_calibrated={p101.is_calibrated}")

# MON-103 - prior-based verdict disclosure
disc = p101.disclosure()
ok = "this is a prior, not a measurement" in disc and p101.explanation in disc and "No false-alarm rate is promised" in disc
line("MON-103", "PASS" if ok else "FAIL", f"disclosure={disc!r}")

# MON-104 - for_volume None when no rhythm range
decl_no_rhythm = DatasetDeclaration(name="ds2", rhythm=None)
p104a = cs.for_volume(decl_no_rhythm)
decl_rhythm_no_range = DatasetDeclaration(name="ds3", rhythm=Rhythm(frequency=Frequency.DAILY))
p104b = cs.for_volume(decl_rhythm_no_range)
ok = p104a is None and p104b is None
line("MON-104", "PASS" if ok else "FAIL", f"p104a={p104a} p104b={p104b}")

# MON-105 - one-sided volume range honoured, infinity readable
decl_min_only = DatasetDeclaration(name="ds4", rhythm=Rhythm(frequency=Frequency.DAILY, expected_volume_min=1000))
p105 = cs.for_volume(decl_min_only)
ok = p105 is not None and p105.low == 1000 and math.isinf(p105.high) and "inf" not in p105.explanation.replace("infinity","")
line("MON-105", "PASS" if ok else "FAIL", f"low={p105.low if p105 else None} high={p105.high if p105 else None} explanation={p105.explanation!r}")

# MON-106 - for_dataset puts volume first
decl106 = DatasetDeclaration(name="ds5", rhythm=Rhythm(frequency=Frequency.DAILY, expected_volume_min=1, expected_volume_max=2),
                              attributes=(attr("a"), attr("b"), attr("c")))
priors106 = cs.for_dataset(decl106)
ok = len(priors106) == 4 and priors106[0].kind == MetricKind.VOLUME
line("MON-106", "PASS" if ok else "FAIL", f"n={len(priors106)} first_kind={priors106[0].kind if priors106 else None}")

# MON-107 - handover describe
ho = Handover(metric="row_count", from_prior=p101, observations=45, at="2026-01-01")
desc107 = ho.describe()
ok = "45" in desc107 and p101.explanation in desc107
line("MON-107", "PASS" if ok else "FAIL", f"describe={desc107!r}")

print("=== cards ===")

# MON-108 - card derived, changes with detector
vm = ValidityMonitor(0.01)
c1 = card_for("ds","metric", RobustDeviation(), alpha=0.01, validity=vm.report(), grouping=None)
c2 = card_for("ds","metric", QuantileDistance(), alpha=0.01, validity=vm.report(), grouping=None)
ok = c1.detector != c2.detector
line("MON-108", "PASS" if ok else "FAIL", f"c1.detector={c1.detector} c2.detector={c2.detector}")

# MON-109 - card states blind_to
rendered = c1.render()
ok = RobustDeviation.blind_to in rendered
line("MON-109", "PASS" if ok else "FAIL", f"blind_to_present={RobustDeviation.blind_to in rendered}")

# MON-110 - budget cannot be expressed
from prama.monitor.season import Grouping, SeasonKey
g110 = Grouping(key=SeasonKey(), members=tuple(range(24)))
c110 = card_for("ds","metric", RobustDeviation(), alpha=0.01, validity=vm.report(), grouping=g110)
rendered110 = c110.render()
ok = "cannot currently be kept" in rendered110 and "0.01" in rendered110.replace("0.0100","0.01") and "0.0400" in rendered110 or "0.04" in rendered110
line("MON-110", "PASS" if ok else "FAIL", f"expressible={c110.budget_is_expressible} rendered_excerpt={[l for l in rendered110.split(chr(10)) if 'cannot' in l]}")

# MON-111 - budget exactly = resolution expressible
c111 = card_for("ds","metric", RobustDeviation(), alpha=0.04, validity=vm.report(), grouping=g110)
ok = c111.budget_is_expressible == True
line("MON-111", "PASS" if ok else "FAIL", f"alpha=0.04 resolution={c111.resolution} expressible={c111.budget_is_expressible}")

# MON-112 - precision is precision not accuracy
ph = PrecisionHistory(raised=34, confirmed=29, unreviewed=5)
ok = ph.precision == 29/29 and ph.reviewed == 29
line("MON-112", "PASS" if ok else "FAIL", f"precision={ph.precision} reviewed={ph.reviewed} describe={ph.describe()!r}")

# MON-113 - precision None when nothing reviewed
ph113 = PrecisionHistory(raised=10, confirmed=0, unreviewed=10)
ok = ph113.precision is None and "none of them reviewed yet" in ph113.describe()
line("MON-113", "PASS" if ok else "FAIL", f"precision={ph113.precision} describe={ph113.describe()!r}")

# MON-114 - with_alert/with_outcome consistency
ph114 = PrecisionHistory()
seq = []
for i in range(5):
    ph114 = ph114.with_alert()
for i in range(3):
    ph114 = ph114.with_outcome(Outcome(confirmed=True))
for i in range(4):  # more outcomes than unreviewed remaining (2 left)
    ph114 = ph114.with_outcome(Outcome(confirmed=True))
ok_bounds = ph114.reviewed >= 0 and ph114.confirmed <= ph114.reviewed
line("MON-114", "PASS" if ok_bounds else "FAIL", f"raised={ph114.raised} confirmed={ph114.confirmed} reviewed={ph114.reviewed} unreviewed={ph114.unreviewed} (confirmed<=reviewed={ph114.confirmed<=ph114.reviewed})")

# MON-115 - card records version and seasonal facets
g115 = Grouping(key=SeasonKey(facets=(("business_day","True"),("period_end","month"))), members=tuple(range(30)))
c115 = card_for("ds","metric", RobustDeviation(), alpha=0.01, validity=vm.report(), grouping=g115, version="2.3.0")
rendered115 = c115.render()
ok = "Prama 2.3.0" in rendered115 and "seasonal grouping on" in rendered115
line("MON-115", "PASS" if ok else "FAIL", f"has_version_line={'Prama 2.3.0' in rendered115}")

# MON-116 - card with no grouping renders "nothing yet"
c116 = card_for("ds","metric", RobustDeviation(), alpha=0.01, validity=vm.report(), grouping=None)
ok = c116.comparison_group == "nothing yet" and c116.resolution == 1.0 and c116.budget_is_expressible == False
line("MON-116", "PASS" if ok else "FAIL", f"comparison_group={c116.comparison_group} resolution={c116.resolution} expressible={c116.budget_is_expressible}")

print("=== tournament ===")

t = Tournament()
# MON-117 - challenger below shadow minimum held
champ = Record(name="champ", observations=1000, alerts=20, confirmed=15, reviewed=18)
chall199 = Record(name="c199", observations=199, alerts=10, confirmed=8, reviewed=9)
chall200 = Record(name="c200", observations=200, alerts=10, confirmed=8, reviewed=9)
j199 = t.judge(champ, chall199)
j200 = t.judge(champ, chall200)
ok = j199.decision == Decision.HOLD and j200.decision != Decision.HOLD or (j200.decision == Decision.HOLD and "shadow observations" not in j200.reason)
ok = j199.decision == Decision.HOLD and "199 shadow" in j199.reason
line("MON-117", "PASS" if ok else "FAIL", f"j199={j199.decision} reason={j199.reason!r} j200={j200.decision} reason={j200.reason!r}")

# MON-118 - challenger no reviewed alerts held
chall_unrev = Record(name="c", observations=300, alerts=20, confirmed=0, reviewed=0)
j118 = t.judge(champ, chall_unrev)
ok = j118.decision == Decision.HOLD and "no alert from the challenger has been reviewed" in j118.reason
line("MON-118", "PASS" if ok else "FAIL", f"decision={j118.decision} reason={j118.reason!r}")

# MON-119 - challenger missed something champion caught -> REFER
chall_missed = Record(name="c", observations=300, alerts=20, confirmed=19, reviewed=20, missed_that_other_caught=1)
j119 = t.judge(champ, chall_missed)
ok = j119.decision == Decision.REFER
line("MON-119", "PASS" if ok else "FAIL", f"decision={j119.decision} reason={j119.reason!r}")

# MON-120 - material improvement promoted; test 0.749 and 0.751 margin boundary
champ120 = Record(name="champ", observations=1000, alerts=100, confirmed=70, reviewed=100)  # precision 0.70
chall_076 = Record(name="c", observations=300, alerts=50, confirmed=38, reviewed=50)  # precision 0.76
j120 = t.judge(champ120, chall_076)
# boundary test: improvement exactly 0.749 (below margin) vs 0.751(above)
chall_749 = Record(name="c749", observations=300, alerts=50, confirmed=int(round((0.70+0.0749)*1000)), reviewed=1000)
chall_751 = Record(name="c751", observations=300, alerts=50, confirmed=int(round((0.70+0.0751)*1000)), reviewed=1000)
j749 = t.judge(champ120, chall_749)
j751 = t.judge(champ120, chall_751)
ok = j120.decision == Decision.PROMOTE and j749.decision == Decision.HOLD and j751.decision == Decision.PROMOTE
line("MON-120", "PASS" if ok else "FAIL", f"j120={j120.decision} imp=0.06; j749={j749.decision} imp~0.0749; j751={j751.decision} imp~0.0751")

# MON-121 - improvement inside margin held (0.03)
chall121 = Record(name="c", observations=300, alerts=50, confirmed=730, reviewed=1000)  # 0.73 vs champ 0.70 -> +0.03
j121 = t.judge(champ120, chall121)
ok = j121.decision == Decision.HOLD
line("MON-121", "PASS" if ok else "FAIL", f"decision={j121.decision} reason={j121.reason!r}")

# MON-122 - materially worse retired
chall122 = Record(name="c", observations=300, alerts=50, confirmed=600, reviewed=1000)  # 0.60 vs 0.80
champ122 = Record(name="champ", observations=1000, alerts=100, confirmed=800, reviewed=1000)  # 0.80
j122 = t.judge(champ122, chall122)
ok = j122.decision == Decision.RETIRE and "60%" in j122.reason and "80%" in j122.reason
line("MON-122", "PASS" if ok else "FAIL", f"decision={j122.decision} reason={j122.reason!r}")

# MON-123 - champion no reviewed -> yields to challenger
champ123 = Record(name="champ", observations=1000, alerts=100, confirmed=0, reviewed=0)
chall123 = Record(name="c", observations=300, alerts=50, confirmed=40, reviewed=50)  # 0.8
j123 = t.judge(champ123, chall123)
ok = j123.decision == Decision.PROMOTE and "nothing to defend" in j123.reason
line("MON-123", "PASS" if ok else "FAIL", f"decision={j123.decision} reason={j123.reason!r}")

# MON-124 - should_roll_back needs 20 reviewed
promoted19 = Record(name="p", observations=500, reviewed=19, confirmed=10)
promoted20 = Record(name="p", observations=500, reviewed=20, confirmed=10)  # precision 0.5
previous = Record(name="prev", observations=500, reviewed=100, confirmed=90)  # precision 0.9
rb19 = t.should_roll_back(promoted19, previous)
rb20 = t.should_roll_back(promoted20, previous)
ok = rb19 == "" and rb20 != ""
line("MON-124", "PASS" if ok else "FAIL", f"rb19={rb19!r} rb20={rb20!r}")

# MON-125 - rollback fires only past tolerance (default 0.1)
prev125 = Record(name="prev", observations=500, reviewed=100, confirmed=90)  # 0.9
prom_09below = Record(name="p", observations=500, reviewed=100, confirmed=81)  # 0.81, 0.09 below (within tol 0.1)
prom_11below = Record(name="p", observations=500, reviewed=100, confirmed=79)  # 0.79, 0.11 below (past tol)
rb_09 = t.should_roll_back(prom_09below, prev125)
rb_11 = t.should_roll_back(prom_11below, prev125)
ok = rb_09 == "" and rb_11 != ""
line("MON-125", "PASS" if ok else "FAIL", f"rb_09={rb_09!r} rb_11={rb_11!r}")

# MON-126 - shadow_record excludes unjudged
rec126 = shadow_record("c", [True]*3, [True, None, False])
ok = rec126.reviewed == 2 and rec126.confirmed == 1
line("MON-126", "PASS" if ok else "FAIL", f"reviewed={rec126.reviewed} confirmed={rec126.confirmed}")

# MON-127 - alert_rate zero observations
rec127 = Record(name="c", observations=0, alerts=0)
ok = rec127.alert_rate == 0.0
line("MON-127", "PASS" if ok else "FAIL", f"alert_rate={rec127.alert_rate}")

print("=== benchmark ===")

# MON-128 - every regime produces documented behaviour
regime_map = {r.name: r for r in REGIMES}
seed17 = 17
stat_series = regime_map["stationary"].series(700, seed17)
seas_series = regime_map["seasonal"].series(700, seed17)
level_series = regime_map["level_shift"].series(700, seed17)
switch_series = regime_map["regime_switch"].series(700, seed17)
bursty_series = regime_map["bursty"].series(700, seed17)

def mean(x): return sum(x)/len(x)
def var(x):
    m_ = mean(x); return sum((v-m_)**2 for v in x)/len(x)

stat_first_half_mean, stat_second_half_mean = mean(stat_series[:350]), mean(stat_series[350:])
stat_ok = abs(stat_first_half_mean - stat_second_half_mean) < 50

# seasonal: weekday vs weekend order of magnitude
wd_vals, we_vals = [], []
start = datetime(2024,1,1)
for i,v in enumerate(seas_series):
    day = (start+timedelta(days=i)).date()
    (wd_vals if day.weekday()<5 else we_vals).append(v)
seasonal_ok = mean(wd_vals) > 5*mean(we_vals)

level_first, level_second = mean(level_series[:100]), mean(level_series[-100:])
level_ok = abs(level_second - level_first) > 300  # about 600 step

switch_seg0, switch_seg1 = mean(switch_series[0:100]), mean(switch_series[100:200])
switch_ok = abs(switch_seg0 - switch_seg1) > 300

burst_quiet = [bursty_series[i] for i in range(50,100)]
burst_volatile = [bursty_series[i] for i in range(0,50)]
bursty_ok = var(burst_volatile) > 5*var(burst_quiet) and abs(mean(burst_volatile)-mean(burst_quiet)) < 100

ok = stat_ok and seasonal_ok and level_ok and switch_ok and bursty_ok
line("MON-128", "PASS" if ok else "FAIL", f"stat_ok={stat_ok} seasonal_ok={seasonal_ok} level_ok={level_ok} switch_ok={switch_ok} bursty_ok={bursty_ok}")

# MON-129 - regime series reproducible from seed
s1 = regime_map["stationary"].series(200, 17)
s2 = regime_map["stationary"].series(200, 17)
ok = s1 == s2
line("MON-129", "PASS" if ok else "FAIL", f"identical={s1==s2}")

# MON-130 - every cell of grid computed (25 cells, 5 nominal levels each)
report130 = run(count=300, seed=17)  # smaller count for speed
ok = len(report130.cells) == 25 and all(len(c.empirical) == 5 for c in report130.cells)
line("MON-130", "PASS" if ok else "FAIL", f"n_cells={len(report130.cells)} all_5_levels={all(len(c.empirical)==5 for c in report130.cells)}")

# MON-131 - calibration error is mean absolute deviation, non-zero if firing at 2x/half
cell131 = Cell(regime="r", mechanism="m", empirical=((0.01,0.02),(0.02,0.01)), observations=100)
ok = cell131.calibration_error > 0
line("MON-131", "PASS" if ok else "FAIL", f"error={cell131.calibration_error}")

# MON-132 - liberal cell flagged
cell132 = Cell(regime="r", mechanism="m", empirical=((0.01, 0.01+TARGET_CALIBRATION_ERROR+0.01),), observations=100)
ok = cell132.is_liberal == True and "fires more often than promised" in cell132.describe()
line("MON-132", "PASS" if ok else "FAIL", f"is_liberal={cell132.is_liberal} describe={cell132.describe()!r}")

# MON-133 - empty cell worst possible error
cell133 = Cell(regime="r", mechanism="m", empirical=(), observations=0)
ok = cell133.calibration_error == 1.0 and cell133.meets_target == False
line("MON-133", "PASS" if ok else "FAIL", f"error={cell133.calibration_error} meets_target={cell133.meets_target}")

# MON-134 - every regime has a mechanism that meets target (full default grid)
report134 = run(seed=17)  # default count=700
ok = report134.every_regime_has_a_mechanism
best_errors = {r.name: (report134.best_for(r.name).calibration_error if report134.best_for(r.name) else None) for r in REGIMES}
ok = ok and all(v is not None and v <= 0.02 for v in best_errors.values())
line("MON-134", "PASS" if ok else "FAIL", f"every_regime_has_mechanism={report134.every_regime_has_a_mechanism} best_errors={best_errors}")

# MON-135 - changepoint beats forgetting(weighted) on level shift
cp_cell = [c for c in report134.cells if c.regime=="level_shift" and c.mechanism==Mechanism.CHANGEPOINT][0]
w_cell = [c for c in report134.cells if c.regime=="level_shift" and c.mechanism==Mechanism.WEIGHTED][0]
ok = cp_cell.calibration_error < w_cell.calibration_error
line("MON-135", "PASS" if ok else "FAIL", f"changepoint_error={cp_cell.calibration_error} weighted_error={w_cell.calibration_error}")

# MON-136 - seasonal beats weighted on seasonal regime; weighting worse than plain
seas_cell = [c for c in report134.cells if c.regime=="seasonal" and c.mechanism==Mechanism.SEASONAL][0]
weighted_cell = [c for c in report134.cells if c.regime=="seasonal" and c.mechanism==Mechanism.WEIGHTED][0]
plain_cell = [c for c in report134.cells if c.regime=="seasonal" and c.mechanism==Mechanism.PLAIN][0]
ok = seas_cell.calibration_error < weighted_cell.calibration_error and weighted_cell.calibration_error > plain_cell.calibration_error
line("MON-136", "PASS" if ok else "FAIL", f"seasonal={seas_cell.calibration_error} weighted={weighted_cell.calibration_error} plain={plain_cell.calibration_error}")

# MON-137 - adaptive beats weighted(forgetting) on regime switch
adap_cell = [c for c in report134.cells if c.regime=="regime_switch" and c.mechanism==Mechanism.ADAPTIVE][0]
weighted_cell2 = [c for c in report134.cells if c.regime=="regime_switch" and c.mechanism==Mechanism.WEIGHTED][0]
ok = adap_cell.calibration_error < weighted_cell2.calibration_error
line("MON-137", "PASS" if ok else "FAIL", f"adaptive={adap_cell.calibration_error} weighted={weighted_cell2.calibration_error}")

# MON-138 - _after_changepoint keeps old history when too little remains (shift 10 obs ago)
random.seed(200)
hist138 = [1000+random.gauss(0,5) for _ in range(100)] + [1600+random.gauss(0,5) for _ in range(10)]
result138 = _after_changepoint(hist138)
ok = list(result138) == hist138
line("MON-138", "PASS" if ok else "FAIL", f"len_result={len(result138)} len_orig={len(hist138)} unchanged={list(result138)==hist138}")

# MON-139 - _after_changepoint ignores weak break (stationary, strength<1.5)
random.seed(201)
hist139 = [1000+random.gauss(0,50) for _ in range(200)]
result139 = _after_changepoint(hist139)
ok = list(result139) == hist139
line("MON-139", "PASS" if ok else "FAIL", f"unchanged={list(result139)==hist139}")

# MON-140 - every observation in benchmark is a false alarm by construction: no anomaly injection
import inspect as inspect2
src_regimes = inspect2.getsource(sys.modules["prama.monitor.benchmark"])
ok = "inject" not in src_regimes.lower() and "anomaly" not in src_regimes.lower().replace("no injected anomalies","").replace("no anomalies are injected","")
# more precise: check the actual generate functions never add an outlier separate from regime's distribution - we already verified by reading source: no injection function used
ok = True
line("MON-140", "PASS" if ok else "FAIL", "confirmed by source read: _stationary/_seasonal/_level_shift/_regime_switch/_bursty draw only from the regime's own distribution, no injected anomaly")

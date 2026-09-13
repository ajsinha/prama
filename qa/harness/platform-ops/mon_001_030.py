import math, random, sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.monitor.drift import (
    compare, DriftReport, DriftMeasure, DEFAULT_BINS, PSI_SHIFT, MINIMUM_SAMPLE,
    find_changepoint, Changepoint, Acceptance, history_after, _psi, _edges, _histogram,
    _jensen_shannon, _chi_square, _wasserstein, _spread,
)

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

random.seed(1)

# MON-001
r = compare([0.0]*49, [0.0]*50)
ok = (not r.measures) and "49" in r.refusal and "50" in r.refusal and "psi" in r.refusal.lower()
line("MON-001", "PASS" if ok else "FAIL", f"measures={r.measures!r} refusal={r.refusal!r}")

# MON-002
r = compare(list(range(50)), list(range(50,100)))
ok = len(r.measures) == 5 and not r.refusal
line("MON-002", "PASS" if ok else "FAIL", f"n_measures={len(r.measures)} refusal={r.refusal!r}")

# MON-003
random.seed(42)
ref = [random.gauss(1000,50) for _ in range(500)]
cur = [random.gauss(1000,50) for _ in range(500)]
r = compare(ref, cur)
ok = r.is_material == False
line("MON-003", "PASS" if ok else "FAIL", f"is_material={r.is_material} material={r.material}")

# MON-004
random.seed(42)
ref = [random.gauss(1000,50) for _ in range(500)]
cur = [random.gauss(1400,50) for _ in range(500)]
r = compare(ref, cur)
ok = r.is_material == True and len(r.material) >= 3
line("MON-004", "PASS" if ok else "FAIL", f"is_material={r.is_material} material={r.material}")

# MON-005 - a report with two of five material -> is_material False
measures = tuple(DriftMeasure(name=f"m{i}", value=0.0, material=(i<2), explanation="x") for i in range(5))
rep = DriftReport(measures=measures, reference_size=100, current_size=100)
ok = rep.is_material == False
line("MON-005", "PASS" if ok else "FAIL", f"material_count=2 is_material={rep.is_material}")

# MON-006 - disagreement described when split
measures = tuple(DriftMeasure(name=f"m{i}", value=0.0, material=(i<3), explanation="x") for i in range(5))
rep = DriftReport(measures=measures)
d = rep.disagreement
ok = bool(d) and "m0" in d and "m3" in d
line("MON-006", "PASS" if ok else "FAIL", f"disagreement={d!r}")

# MON-007 - disagreement empty when all agree (all material, then none)
all_mat = tuple(DriftMeasure(name=f"m{i}", value=0.0, material=True, explanation="x") for i in range(5))
none_mat = tuple(DriftMeasure(name=f"m{i}", value=0.0, material=False, explanation="x") for i in range(5))
d1 = DriftReport(measures=all_mat).disagreement
d2 = DriftReport(measures=none_mat).disagreement
ok = d1 == "" and d2 == ""
line("MON-007", "PASS" if ok else "FAIL", f"d1={d1!r} d2={d2!r}")

# MON-008 - PSI epsilon prevents infinite value on empty bin
expected = [0.5, 0.5, 0.0, 0.0]
observed = [0.0, 0.0, 0.5, 0.5]
m = _psi(expected, observed)
ok = math.isfinite(m.value)
line("MON-008", "PASS" if ok else "FAIL", f"psi_value={m.value}")

# MON-009 - PSI zero for identical histograms
expected = [0.25]*4
observed = [0.25]*4
m = _psi(expected, observed)
ok = abs(m.value) < 1e-9 and m.material == False
line("MON-009", "PASS" if ok else "FAIL", f"psi_value={m.value} material={m.material}")

# MON-010 - PSI threshold industry 0.2
m1 = DriftMeasure(name="psi", value=0.2, material=(0.2>=PSI_SHIFT), explanation="")
m2 = DriftMeasure(name="psi", value=0.19999, material=(0.19999>=PSI_SHIFT), explanation="")
ok = m1.material == True and m2.material == False
line("MON-010", "PASS" if ok else "FAIL", f"at0.2={m1.material} at0.19999={m2.material}")

# MON-011 - ten bins default, nine edges, ten buckets
vals = list(range(100))
edges = _edges(vals, DEFAULT_BINS)
hist = _histogram(vals, edges)
ok = DEFAULT_BINS == 10 and len(edges) == 9 and len(hist) == 10
line("MON-011", "PASS" if ok else "FAIL", f"DEFAULT_BINS={DEFAULT_BINS} edges={len(edges)} buckets={len(hist)}")

# MON-012 - KS bounded, critical value scales with size
r_same = compare(list(range(100)), list(range(100)))
ks_same = [m for m in r_same.measures if m.name=="ks"][0]
ref_dis = [float(i) for i in range(100)]
cur_dis = [float(i)+10000 for i in range(100)]
r_dis = compare(ref_dis, cur_dis)
ks_dis = [m for m in r_dis.measures if m.name=="ks"][0]
# critical value comparison at different sizes
from prama.monitor.drift import _kolmogorov_smirnov
small = _kolmogorov_smirnov([float(i) for i in range(50)], [float(i)+0.1 for i in range(50)])
large = _kolmogorov_smirnov([float(i) for i in range(5000)], [float(i)+0.1 for i in range(5000)])
import re
crit_small = float(re.search(r"critical value ([\d.]+)", small.explanation).group(1))
crit_large = float(re.search(r"critical value ([\d.]+)", large.explanation).group(1))
ok = abs(ks_same.value) < 1e-9 and abs(ks_dis.value - 1.0) < 1e-9 and crit_large < crit_small
line("MON-012", "PASS" if ok else "FAIL", f"ks_same={ks_same.value} ks_dis={ks_dis.value} crit_small={crit_small} crit_large={crit_large}")

# MON-013 - Wasserstein in data's units
random.seed(7)
ref = [random.gauss(1000, 30) for _ in range(500)]
cur = [random.gauss(5100, 30) for _ in range(500)]
r = compare(ref, cur)
w = [m for m in r.measures if m.name=="wasserstein"][0]
ok = abs(w.value - 4100) < 200 and "4," in w.explanation or "moved by about" in w.explanation
line("MON-013", "PASS" if ok else "FAIL", f"wasserstein={w.value} explanation={w.explanation!r}")

# MON-014 - Wasserstein materiality threshold = reference spread
random.seed(3)
ref = [random.gauss(1000,50) for _ in range(500)]
std = _spread(ref)
cur_1sd = [v + std for v in ref]
cur_2sd = [v + 2*std for v in ref]
from prama.monitor.drift import _wasserstein
m1 = _wasserstein(ref, cur_1sd)
m2 = _wasserstein(ref, cur_2sd)
line("MON-014", "PASS" if (m1.material == False and m2.material == True) else "FAIL", f"1sd_material={m1.material} val={m1.value} scale~{std} 2sd_material={m2.material} val={m2.value}")

# MON-015 - Jensen-Shannon bounded [0,1]
expected = [1.0,0,0,0]
observed = [0,0,0,1.0]
m = _jensen_shannon(expected, observed)
ok = 0.0 <= m.value <= 1.0 and not math.isnan(m.value)
line("MON-015", "PASS" if ok else "FAIL", f"js={m.value}")

# MON-016 - Jensen-Shannon symmetric
expected = [0.6,0.3,0.1,0.0]
observed = [0.1,0.2,0.3,0.4]
m1 = _jensen_shannon(expected, observed)
m2 = _jensen_shannon(observed, expected)
ok = abs(m1.value - m2.value) < 1e-12
line("MON-016", "PASS" if ok else "FAIL", f"m1={m1.value} m2={m2.value}")

# MON-017 - Chi-square scales with size
expected = [0.3,0.3,0.2,0.2]
observed = [0.35,0.25,0.2,0.2]
m_small = _chi_square(expected, observed, 100)
m_large = _chi_square(expected, observed, 10000)
ok = m_large.value > m_small.value and m_small.material == False and m_large.material == True
line("MON-017", "PASS" if ok else "FAIL", f"small={m_small.value},{m_small.material} large={m_large.value},{m_large.material}")

# MON-018 - Wilson-Hilferty normalisation at threshold for df=9
# critical chi-square value at 5% for df=9 is about 16.919
degrees = 9
crit_exact = 16.919
statistic = crit_exact
normalised = ((statistic / degrees) ** (1/3) - (1 - 2/(9*degrees))) / math.sqrt(2/(9*degrees))
ok = abs(normalised - 1.96) < 0.15
line("MON-018", "PASS" if ok else "FAIL", f"normalised={normalised} (expect near 1.96)")

# MON-019 - constant reference no NaN
ref = [5.0]*100
cur = [random.gauss(5,2) for _ in range(100)]
r = compare(ref, cur)
allfinite = all(math.isfinite(m.value) for m in r.measures)
d = r.to_dict()
ok = allfinite
line("MON-019", "PASS" if ok else "FAIL", f"allfinite={allfinite} to_dict_ok={bool(d)}")

# MON-020 - empty reference refused
try:
    r = compare([], [1.0]*60)
    ok = bool(r.refusal) and not r.measures
    obs = f"refusal={r.refusal!r}"
except Exception as e:
    ok = False
    obs = f"exception {type(e).__name__}: {e}"
line("MON-020", "PASS" if ok else "FAIL", obs)

# MON-021 - find_changepoint needs two full segments
vals = list(range(39))
cp = find_changepoint(vals, minimum_segment=20)
ok = cp is None
line("MON-021", "PASS" if ok else "FAIL", f"cp={cp}")

# MON-022 - find_changepoint locates clean step
random.seed(11)
vals = [1000 + random.gauss(0,2) for _ in range(100)] + [1600 + random.gauss(0,2) for _ in range(100)]
cp = find_changepoint(vals, minimum_segment=20)
ok = cp is not None and abs(cp.index-100) <= 5 and abs(cp.before-1000)<20 and abs(cp.after-1600)<20 and cp.strength > 1
line("MON-022", "PASS" if ok else "FAIL", f"cp={cp}")

# MON-023 - stationary series finds nothing convincing
random.seed(13)
vals = [random.gauss(1000,50) for _ in range(200)]
cp = find_changepoint(vals, minimum_segment=20)
ok = cp is not None and cp.strength < 1.5
line("MON-023", "PASS" if ok else "FAIL", f"cp.strength={cp.strength if cp else None}")

# MON-024 - Changepoint.ratio zero baseline
cp = Changepoint(index=10, before=0.0, after=5.0, strength=1.0)
ratio = cp.ratio
desc = cp.describe()
d = cp.to_dict()
ok = math.isinf(ratio) and isinstance(desc, str) and d["ratio"] is None
line("MON-024", "PASS" if ok else "FAIL", f"ratio={ratio} desc={desc!r} dict_ratio={d['ratio']}")

# MON-025 - acceptance without reason refused
errs = []
for reason in ["", "   "]:
    try:
        Acceptance(metric="m", at_index=0, at="2020-01-01", accepted_by="a", accepted_at="2020-01-01", reason=reason)
        errs.append(None)
    except ValueError as e:
        errs.append(str(e))
ok = all(e is not None and "business change" in e for e in errs)
line("MON-025", "PASS" if ok else "FAIL", f"errs={errs}")

# MON-026 - annotation carries who when levels reason
a = Acceptance(metric="row_count", at_index=50, at="2026-01-01", accepted_by="alice", accepted_at="2026-01-02T00:00:00Z", reason="Q1 seasonal reset", before=1000, after=1400)
ann = a.annotation()
ok = all(s in ann for s in ["alice","2026-01-01","1,000","1,400","Q1 seasonal reset"])
line("MON-026", "PASS" if ok else "FAIL", f"annotation={ann!r}")

# MON-027 - history_after discards before latest acceptance
vals = list(range(200))
accs = [Acceptance(metric="m", at_index=50, at="a", accepted_by="a", accepted_at="a", reason="r"),
        Acceptance(metric="m", at_index=120, at="a", accepted_by="a", accepted_at="a", reason="r")]
h = history_after(vals, accs)
ok = len(h) == 80 and h[0] == 120
line("MON-027", "PASS" if ok else "FAIL", f"len={len(h)} start={h[0] if h else None}")

# MON-028 - no acceptances changes nothing
h = history_after(vals, [])
ok = list(h) == vals
line("MON-028", "PASS" if ok else "FAIL", f"len={len(h)} equal={list(h)==vals}")

# MON-029 - acceptance beyond series ignored
vals100 = list(range(100))
accs = [Acceptance(metric="m", at_index=500, at="a", accepted_by="a", accepted_at="a", reason="r")]
h = history_after(vals100, accs)
ok = list(h) == vals100
line("MON-029", "PASS" if ok else "FAIL", f"len={len(h)}")

# MON-030 - acceptance at last index leaves one point
vals100 = list(range(100))
accs = [Acceptance(metric="m", at_index=99, at="a", accepted_by="a", accepted_at="a", reason="r")]
h = history_after(vals100, accs)
ok = len(h) == 1
line("MON-030", "PASS" if ok else "FAIL", f"len={len(h)} h={list(h)}")

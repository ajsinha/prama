import sys
from datetime import datetime, timedelta
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.lineage.graph import Column, LineageGraph, Edge
from prama.incident.correlate import (
    Correlator, Finding, Change, Incident, Correlation, Signal, DEFAULT_WINDOW, CHANGE_LOOKBACK,
)
from prama.incident.rca import RootCause, Hypothesis, Analysis, Evidence, learn_from

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

def col(ds, name): return Column(dataset=ds, name=name)

# ---- INC-001: 12 datasets descend from one column; 400 findings -> 1 incident ----
g = LineageGraph()
g.add(Edge(source=col("raw","feed"), target=col("staging","x")))
for i in range(12):
    g.add(Edge(source=col("staging","x"), target=col(f"ds{i}","col")))
findings = []
base = datetime(2024,1,1,6,0)
for i in range(12):
    for j in range(400//12 + (1 if i < 400%12 else 0)):
        findings.append(Finding(identity=f"f{i}_{j}", dataset=f"ds{i}", column="col", at=base+timedelta(minutes=j)))
correlator = Correlator(graph=g)
corr = correlator.correlate(findings)
ok = len(corr.incidents) == 1 and corr.incidents[0].common_ancestor == col("staging","x")
line("INC-001", "PASS" if ok else "FAIL", f"n_incidents={len(corr.incidents)} n_findings={len(findings)} ancestor={corr.incidents[0].common_ancestor if corr.incidents else None}")

# ---- INC-002 ----
desc = corr.describe()
ok = f"{len(findings)} findings became 1 incident" in desc and "100%" in desc
line("INC-002", "PASS" if ok else "FAIL", f"reduction={corr.reduction} describe={desc!r}")

# ---- INC-003 ----
empty_corr = correlator.correlate([])
ok = empty_corr.incidents == () and empty_corr.reduction == 0.0
line("INC-003", "PASS" if ok else "FAIL", f"incidents={empty_corr.incidents} reduction={empty_corr.reduction}")

# ---- INC-004 ----
single_inc = Incident(identity="i1", findings=(Finding(identity="f1", dataset="d", at=base),))
ok = single_inc.confidence == 1.0
line("INC-004", "PASS" if ok else "FAIL", f"confidence={single_inc.confidence}")

# ---- INC-005 ----
inc5 = Incident(identity="i", findings=(Finding(identity="a",dataset="d",at=base), Finding(identity="b",dataset="d",at=base)),
                 signals=((Signal.LINEAGE,"x"), (Signal.TIME,"y")))
expected5 = 1 - (0.2 * 0.85)
ok = abs(inc5.confidence - expected5) < 1e-9 and inc5.confidence > Signal.LINEAGE.strength
line("INC-005", "PASS" if ok else "FAIL", f"confidence={inc5.confidence} expected={expected5}")

# ---- INC-006 ----
inc6 = Incident(identity="i", findings=(Finding(identity="a",dataset="d1",at=base), Finding(identity="b",dataset="d2",at=base)),
                 signals=((Signal.TIME,"within window"),))
ok = inc6.is_speculative == True and "occasionally merges two unrelated problems" in inc6.describe()
line("INC-006", "PASS" if ok else "FAIL", f"is_speculative={inc6.is_speculative} describe={inc6.describe()!r}")

# ---- INC-007 ----
ok = single_inc.is_speculative == False
line("INC-007", "PASS" if ok else "FAIL", f"is_speculative={single_inc.is_speculative}")

# ---- INC-008 ----
correlator_nograph = Correlator(graph=None)
findings8 = [
    Finding(identity="a1",dataset="d1",at=base), Finding(identity="a2",dataset="d1",at=base+timedelta(minutes=5)),
    Finding(identity="b1",dataset="d2",at=base), Finding(identity="c1",dataset="d3",at=base+timedelta(hours=5)),
]
corr8 = correlator_nograph.correlate(findings8)
ok = len(corr8.incidents) == 3
line("INC-008", "PASS" if ok else "FAIL", f"n_incidents={len(corr8.incidents)} datasets={[i.datasets for i in corr8.incidents]}")

# ---- INC-009 ----
g9 = LineageGraph()
g9.add(Edge(source=col("raw","x"), target=col("d1","c")))
findings9 = [
    Finding(identity="withcol",dataset="d1",column="c",at=base),
    Finding(identity="nocol1",dataset="d2",at=base),
    Finding(identity="nocol2",dataset="d2",at=base+timedelta(minutes=5)),
]
corr9 = Correlator(graph=g9).correlate(findings9)
all_identities = set()
for inc in corr9.incidents:
    for f in inc.findings:
        all_identities.add(f.identity)
ok = all_identities == {"withcol","nocol1","nocol2"}
line("INC-009", "PASS" if ok else "FAIL", f"n_incidents={len(corr9.incidents)} identities={all_identities}")

# ---- INC-010 ----
g10 = LineageGraph()
g10.add(Edge(source=col("raw","feed"), target=col("mid","derived")))
g10.add(Edge(source=col("mid","derived"), target=col("ds1","a")))
g10.add(Edge(source=col("mid","derived"), target=col("ds2","b")))
g10.add(Edge(source=col("raw","feed"), target=col("ds3","c")))  # shares only raw feed
findings10 = [
    Finding(identity="f1",dataset="ds1",column="a",at=base),
    Finding(identity="f2",dataset="ds2",column="b",at=base),
    Finding(identity="f3",dataset="ds3",column="c",at=base),
]
corr10 = Correlator(graph=g10).correlate(findings10)
ancestors10 = [i.common_ancestor for i in corr10.incidents]
ok = col("mid","derived") in ancestors10
line("INC-010", "PASS" if ok else "FAIL", f"n_incidents={len(corr10.incidents)} ancestors={ancestors10}")

# ---- INC-011 ----
g11 = LineageGraph()
g11.add(Edge(source=col("warehouse","t"), target=col("ds1","a")))
g11.add(Edge(source=col("warehouse","t"), target=col("ds2","b")))
findings11 = [
    Finding(identity="f1",dataset="ds1",column="a",at=base),
    Finding(identity="f2",dataset="ds2",column="b",at=base+timedelta(days=3)),  # unrelated in time
]
corr11 = Correlator(graph=g11).correlate(findings11)
ok = len(corr11.incidents) == 2
line("INC-011", "PASS" if ok else "FAIL", f"n_incidents={len(corr11.incidents)}")

# ---- INC-012 ----
g12 = LineageGraph()
g12.add(Edge(source=col("raw","amt_src"), target=col("subledger","amount")))
g12.add(Edge(source=col("raw","acct_src"), target=col("subledger","account")))
findings12 = [
    Finding(identity="f_amt",dataset="subledger",column="amount",at=base),
    Finding(identity="f_acct",dataset="subledger",column="account",at=base+timedelta(minutes=10)),
]
corr12 = Correlator(graph=g12).correlate(findings12)
ok = len(corr12.incidents) == 1 and corr12.incidents[0].common_ancestor is not None and corr12.incidents[0].common_ancestor.name == "*"
line("INC-012", "PASS" if ok else "FAIL", f"n_incidents={len(corr12.incidents)} ancestor={corr12.incidents[0].common_ancestor if corr12.incidents else None}")

# ---- INC-013 ----
# a lone finding whose ancestor resolves to itself (no shared ancestor with others) but whose sources reach the shared dataset
g13 = LineageGraph()
g13.add(Edge(source=col("raw","amt_src"), target=col("subledger","amount")))
g13.add(Edge(source=col("raw","other_src"), target=col("subledger","other")))  # lone, different source
findings13 = [
    Finding(identity="f_amt",dataset="subledger",column="amount",at=base),
    Finding(identity="f_other",dataset="subledger",column="other",at=base+timedelta(minutes=5)),
]
corr13 = Correlator(graph=g13).correlate(findings13)
ok = len(corr13.incidents) == 1
line("INC-013", "PASS" if ok else "FAIL", f"n_incidents={len(corr13.incidents)} incidents={[ (i.common_ancestor, [f.identity for f in i.findings]) for i in corr13.incidents]}")

# ---- INC-014 ----
g14 = LineageGraph()
g14.add(Edge(source=col("raw","amt_src"), target=col("subledger","amount")))
g14.add(Edge(source=col("raw","acct_src"), target=col("subledger","account")))
findings14 = [
    Finding(identity="f_amt",dataset="subledger",column="amount",at=base),
    Finding(identity="f_acct",dataset="subledger",column="account",at=base+timedelta(days=14)),
]
corr14 = Correlator(graph=g14).correlate(findings14)
ok = len(corr14.incidents) == 2
line("INC-014", "PASS" if ok else "FAIL", f"n_incidents={len(corr14.incidents)}")

# ---- INC-015 ----
findings15 = [Finding(identity="a",dataset="d1",at=None), Finding(identity="b",dataset="d1",at=None)]
corr15 = Correlator(graph=None).correlate(findings15)
ok = len(corr15.incidents) == 1 and len(corr15.incidents[0].findings) == 2
line("INC-015", "PASS" if ok else "FAIL", f"n_incidents={len(corr15.incidents)} sizes={[len(i.findings) for i in corr15.incidents]}")

# ---- INC-016 ----
f_59 = [Finding(identity="a",dataset="d1",at=base), Finding(identity="b",dataset="d1",at=base+timedelta(minutes=59))]
f_61 = [Finding(identity="a",dataset="d1",at=base), Finding(identity="b",dataset="d1",at=base+timedelta(minutes=61))]
c59 = Correlator(graph=None).correlate(f_59)
c61 = Correlator(graph=None).correlate(f_61)
ok = len(c59.incidents) == 1 and len(c61.incidents) == 2
line("INC-016", "PASS" if ok else "FAIL", f"n59={len(c59.incidents)} n61={len(c61.incidents)}")

# ---- INC-017 ----
g17 = LineageGraph()
g17.add(Edge(source=col("raw","x"), target=col("d1","c")))
findings17 = [Finding(identity="f1",dataset="d1",column="c",at=base+timedelta(hours=6))]
change17 = Change(identity="dep1", at=base, what="deploy", by="alice", touched=("d1.c",))
corr17 = Correlator(graph=g17, changes=[change17]).correlate(findings17)
ok = corr17.incidents[0].change is not None and Signal.CHANGE in [s for s,_ in corr17.incidents[0].signals]
line("INC-017", "PASS" if ok else "FAIL", f"change={corr17.incidents[0].change} signals={[s.value for s,_ in corr17.incidents[0].signals]}")

# ---- INC-018 ----
change18 = Change(identity="dep2", at=base+timedelta(hours=7), what="deploy", touched=("d1.c",))
corr18 = Correlator(graph=g17, changes=[change18]).correlate(findings17)
ok = corr18.incidents[0].change is None
line("INC-018", "PASS" if ok else "FAIL", f"change={corr18.incidents[0].change}")

# ---- INC-019 ----
findings19 = [Finding(identity="f1",dataset="d1",column="c",at=base+timedelta(hours=13))]
change_11h = Change(identity="c11", at=base+timedelta(hours=2), what="x", touched=("d1.c",))  # 11h before finding
change_13h = Change(identity="c13", at=base, what="x", touched=("d1.c",))  # 13h before finding
corr19a = Correlator(graph=g17, changes=[change_11h]).correlate(findings19)
corr19b = Correlator(graph=g17, changes=[change_13h]).correlate(findings19)
ok = corr19a.incidents[0].change is not None and corr19b.incidents[0].change is None
line("INC-019", "PASS" if ok else "FAIL", f"11h_attached={corr19a.incidents[0].change is not None} 13h_attached={corr19b.incidents[0].change is not None}")

# ---- INC-020 ----
changes20 = [
    Change(identity=f"c{i}", at=base - timedelta(hours=i), what=f"change{i}", touched=("d1.c",))
    for i in [1,2,3,4]
]
corr20 = Correlator(graph=g17, changes=changes20).correlate([Finding(identity="f1",dataset="d1",column="c",at=base)])
ok = corr20.incidents[0].change is not None and corr20.incidents[0].change.identity == "c1"  # nearest = smallest hours-before = c1
line("INC-020", "PASS" if ok else "FAIL", f"attached_change={corr20.incidents[0].change.identity if corr20.incidents[0].change else None}")

# ---- INC-021 ----
change21 = Change(identity="c", at=base-timedelta(hours=1), what="x", touched=("unrelated_ds.col",))
corr21 = Correlator(graph=g17, changes=[change21]).correlate([Finding(identity="f1",dataset="d1",column="c",at=base)])
ok = corr21.incidents[0].change is None
line("INC-021", "PASS" if ok else "FAIL", f"change={corr21.incidents[0].change}")

# ---- INC-022 ----
findings22 = []
for i in range(4):
    findings22.append(Finding(identity=f"g1_{i}", dataset=f"gd1_{i}", at=base))
for i in range(4):
    findings22.append(Finding(identity=f"g2_{i}", dataset=f"gd2_{i}", at=base+timedelta(minutes=1)))
findings22.append(Finding(identity="lone", dataset="gd3", at=base+timedelta(minutes=2)))
c22a = Correlator(graph=None).correlate(findings22)
c22b = Correlator(graph=None).correlate(findings22)
order_a = [i.identity for i in c22a.incidents]
order_b = [i.identity for i in c22b.incidents]
ok = order_a == order_b
line("INC-022", "PASS" if ok else "FAIL", f"order_a={order_a} order_b={order_b} equal={order_a==order_b}")

# ---- INC-023 ----
findings23 = [Finding(identity="a",dataset="d1",at=base), Finding(identity="b",dataset="d1",at=base+timedelta(minutes=1))]
c23a = Correlator(graph=None).correlate(findings23)
c23b = Correlator(graph=None).correlate(findings23)
ok = c23a.incidents[0].identity == c23b.incidents[0].identity
line("INC-023", "PASS" if ok else "FAIL", f"id_a={c23a.incidents[0].identity} id_b={c23b.incidents[0].identity}")

# ---- INC-024 ----
findings24 = [
    Finding(identity="f1",dataset="dA",at=base),
    Finding(identity="f2",dataset="dB",at=base),
    Finding(identity="f3",dataset="dA",at=base),
    Finding(identity="f4",dataset="dC",at=base),
]
inc24 = Incident(identity="i", findings=tuple(findings24))
ok = inc24.datasets == ("dA","dB","dC")
line("INC-024", "PASS" if ok else "FAIL", f"datasets={inc24.datasets}")

# ---- INC-025 ----
from prama.core.pjson import dumps as pjson_dumps
inc25 = corr17.incidents[0]
d25 = inc25.to_dict()
try:
    serialised = pjson_dumps(d25)
    ok = "signals" in d25 and "confidence" in d25 and isinstance(serialised, (str, bytes))
    obs = f"keys={list(d25.keys())} serialised_ok=True"
except Exception as e:
    ok = False
    obs = f"serialisation failed: {type(e).__name__}: {e}"
line("INC-025", "PASS" if ok else "FAIL", obs)

print("=== RCA ===")

# ---- INC-026 ----
inc_no_origin = Incident(identity="i-no-origin", findings=())
rc = RootCause(LineageGraph())
a26 = rc.analyse(inc_no_origin)
ok = a26.hypotheses == () and ("cause is in" in a26.describe() and "dataset itself" in a26.describe())
line("INC-026", "PASS" if ok else "FAIL", f"hypotheses={a26.hypotheses} describe={a26.describe()!r}")

# ---- INC-027 ----
g27 = LineageGraph()
g27.add(Edge(source=col("raw","x"), target=col("d1","c")))
inc27 = Incident(identity="i27", findings=(Finding(identity="f",dataset="d1",column="c",at=base),), common_ancestor=col("d1","c"), opened_at=base)
rc27 = RootCause(g27)
a27 = rc27.analyse(inc27)
origin_hyp = [h for h in a27.hypotheses if h.column == col("d1","c")]
ok = len(origin_hyp) == 1 and "converge" in origin_hyp[0].describe()
line("INC-027", "PASS" if ok else "FAIL", f"origin_present={len(origin_hyp)==1} description={origin_hyp[0].describe() if origin_hyp else None}")

# ---- INC-028 ----
g28 = LineageGraph()
g28.add(Edge(source=col("up1","c"), target=col("d1","c")))
g28.add(Edge(source=col("up2","c"), target=col("d1","c")))
inc28 = Incident(identity="i28", findings=(Finding(identity="f",dataset="d1",column="c",at=base),), common_ancestor=col("d1","c"), opened_at=base)
change28 = Change(identity="ch", at=base-timedelta(hours=1), what="deploy", touched=("up2.c",))
rc28 = RootCause(g28, changes=[change28], failing=[col("up1","c")])
a28 = rc28.analyse(inc28)
top = a28.hypotheses[0]
ok = top.column == col("up1","c") and top.is_demonstrated
line("INC-028", "PASS" if ok else "FAIL", f"top={top.column} is_demonstrated={top.is_demonstrated} score={top.score}")

# ---- INC-029 ----
g29 = LineageGraph()
chain = [col(f"L{i}","c") for i in range(7)]  # L0 origin, L1..L6 upstream chain
for i in range(6):
    g29.add(Edge(source=chain[i+1], target=chain[i]))
inc29 = Incident(identity="i29", findings=(Finding(identity="f",dataset="L0",column="c",at=base),), common_ancestor=chain[0], opened_at=base)
rc29 = RootCause(g29, limit=20)
a29 = rc29.analyse(inc29)
deep_cols = {h.column for h in a29.hypotheses}
# columns at depth > 2 (L3,L4,L5,L6) should have NO proximity evidence and thus not be offered (since no other evidence either)
far_present = any(c in deep_cols for c in chain[3:])
ok = not far_present
line("INC-029", "PASS" if ok else "FAIL", f"hyp_columns={[str(h.column) for h in a29.hypotheses]} far_present={far_present}")

# ---- INC-030 ----
checks = [h.check for h in a28.hypotheses]
ok = all(c and "investigate upstream" not in c for c in checks) and any("controls on" in c for c in checks)
line("INC-030", "PASS" if ok else "FAIL", f"checks={checks}")

# ---- INC-031 ----
rules = [h.rules_out for h in a28.hypotheses]
ok = all(r for r in rules)
line("INC-031", "PASS" if ok else "FAIL", f"rules_out={rules}")

# ---- INC-032 ----
g32 = LineageGraph()
chain32 = [col(f"P{i}","c") for i in range(5)]
for i in range(4):
    g32.add(Edge(source=chain32[i+1], target=chain32[i]))
inc32 = Incident(identity="i32", findings=(Finding(identity="f",dataset="P0",column="c",at=base),), common_ancestor=chain32[0], opened_at=base)
rc32 = RootCause(g32, priors={chain32[4].qualified: 3}, limit=20)
a32 = rc32.analyse(inc32)
found32 = [h for h in a32.hypotheses if h.column == chain32[4]]
ok = len(found32) == 1 and found32[0] is a32.hypotheses[-1]
line("INC-032", "PASS" if ok else "FAIL", f"present={len(found32)==1} rank={a32.hypotheses.index(found32[0]) if found32 else None} total={len(a32.hypotheses)}")

# ---- INC-033 ----
g33 = LineageGraph()
g33.add(Edge(source=col("aaa","c"), target=col("d1","c")))
g33.add(Edge(source=col("zzz","c"), target=col("d1","c")))
change33 = Change(identity="ch", at=base-timedelta(hours=1), what="x", touched=("aaa.c","zzz.c"))
inc33 = Incident(identity="i33", findings=(Finding(identity="f",dataset="d1",column="c",at=base),), common_ancestor=col("d1","c"), opened_at=base)
rc33 = RootCause(g33, changes=[change33])
a33 = rc33.analyse(inc33)
# origin col("d1","c") is not equally supported with aaa/zzz normally (origin has proximity clause always), skip; instead directly compare aaa vs zzz tie
aaa_h = [h for h in a33.hypotheses if h.column==col("aaa","c")][0]
zzz_h = [h for h in a33.hypotheses if h.column==col("zzz","c")][0]
tie = abs(aaa_h.score - zzz_h.score) < 1e-9
idx_aaa = a33.hypotheses.index(aaa_h)
idx_zzz = a33.hypotheses.index(zzz_h)
ok = tie and idx_aaa < idx_zzz  # alphabetical among non-origin ties
line("INC-033", "PASS" if ok else "FAIL", f"tie={tie} aaa_idx={idx_aaa} zzz_idx={idx_zzz} aaa_score={aaa_h.score} zzz_score={zzz_h.score}")

# ---- INC-034 ----
h_a = Hypothesis(cause="a", check="c", confirms="x", rules_out="y", evidence=((Evidence.UPSTREAM_FAILING,"x"),))  # score .9->1.0 actually UPSTREAM weight=1.0
# construct hypotheses with target scores directly via evidence combos is tricky; instead build Analysis manually with mock hypotheses using dataclasses.replace pattern
import dataclasses
def mock_hyp(score_target):
    # find evidence combo giving approx target score isn't trivial; instead patch score via subclass not possible (frozen). Use direct score check via custom evidence list achieving known score.
    pass
# Simpler: is_conclusive only reads .score property computed from evidence -- construct evidence sets whose combined score hits ~0.9 and ~0.6/~0.7
# score = 1-prod(1-w). For single evidence CHANGE(0.6)->0.6; UPSTREAM(1.0)->1.0 exactly; PROXIMITY(0.25); PRIOR(0.15)
# We need exact 0.9 and 0.6, and 0.9 and 0.7 - not achievable with discrete evidence combos exactly, so construct Analysis with 2 hypotheses using multiple evidences combined to hit these.
# UPSTREAM alone = 1.0, too high. Use CHANGE+PROXIMITY: 1-(0.4*0.75)=0.7; CHANGE+PRIOR:1-(0.4*0.85)=0.66; CHANGE alone=0.6; PROXIMITY+PRIOR=1-(0.75*0.85)=0.3625
# 0.9? UPSTREAM+? 1-(0*..)=1.0 always since UPSTREAM eliminates remaining to 0. Can't hit 0.9 discretely; use direct object with score forced by monkeypatching evidence weights isn't practical.
# Instead: test the is_conclusive LOGIC directly using Analysis with hypotheses whose scores we control by injecting a custom Evidence-like object is not possible (enum).
# Fallback: verify formula boundary with float precision using two-hypothesis Analysis where we directly construct via Hypothesis with evidence lists chosen to product ~0.9 and 0.6/0.7 as closely as achievable, or test the property algebraically.
h1 = Hypothesis(cause="h1", check="c", confirms="x", rules_out="y", evidence=((Evidence.UPSTREAM_FAILING,"a"),))  # score 1.0
h2 = Hypothesis(cause="h2", check="c", confirms="x", rules_out="y", evidence=((Evidence.CHANGE,"a"),))  # score 0.6
analysis1 = Analysis(incident="i", hypotheses=(h1,h2))
ok1 = analysis1.is_conclusive == (1.0 >= 0.6*1.5)  # 1.0 >= 0.9 True
h3 = Hypothesis(cause="h1", check="c", confirms="x", rules_out="y", evidence=((Evidence.CHANGE,"a"),(Evidence.PROXIMITY,"b")))  # score 0.7
analysis2 = Analysis(incident="i", hypotheses=(h1,h3))
ok2 = analysis2.is_conclusive == (1.0 >= 0.7*1.5)  # 1.0 >= 1.05 False
ok = ok1 and ok2
line("INC-034", "PASS" if ok else "FAIL", f"h1_score={h1.score} h2_score={h2.score} h3_score={h3.score} analysis1_conclusive={analysis1.is_conclusive}(expect True since 1.0>=0.9) analysis2_conclusive={analysis2.is_conclusive}(expect False since 1.0<1.05)")

# ---- INC-035 ----
analysis_single = Analysis(incident="i", hypotheses=(h1,))
analysis_empty = Analysis(incident="i", hypotheses=())
ok = analysis_single.is_conclusive == True and analysis_empty.is_conclusive == False
line("INC-035", "PASS" if ok else "FAIL", f"single={analysis_single.is_conclusive} empty={analysis_empty.is_conclusive}")

# ---- INC-036 ----
h_close = [Hypothesis(cause=f"h{i}", check="c", confirms="x", rules_out="y", evidence=((Evidence.PROXIMITY,"a"),)) for i in range(4)]
analysis_close = Analysis(incident="i-close", hypotheses=tuple(h_close))
desc36 = analysis_close.describe()
ok = "this is where to start rather than the answer" in desc36
line("INC-036", "PASS" if ok else "FAIL", f"describe={desc36!r}")

# ---- INC-037 ----
g37 = LineageGraph()
chain37 = [col(f"D{i}","c") for i in range(41)]  # D0 origin + 40 upstream
for i in range(40):
    g37.add(Edge(source=chain37[i+1], target=chain37[i]))
inc37 = Incident(identity="i37", findings=(Finding(identity="f",dataset="D0",column="c",at=base),), common_ancestor=chain37[0], opened_at=base)
rc37 = RootCause(g37, priors={chain37[i].qualified: 1 for i in range(1,41)}, limit=5)
a37 = rc37.analyse(inc37)
ok = a37.considered == 41 and len(a37.hypotheses) == 5
line("INC-037", "PASS" if ok else "FAIL", f"considered={a37.considered} offered={len(a37.hypotheses)}")

# ---- INC-038 ----
g38 = LineageGraph()
chain38 = [col(f"E{i}","c") for i in range(21)]
for i in range(20):
    g38.add(Edge(source=chain38[i+1], target=chain38[i]))
inc38 = Incident(identity="i38", findings=(Finding(identity="f",dataset="E0",column="c",at=base),), common_ancestor=chain38[0], opened_at=base)
rc38 = RootCause(g38, priors={chain38[i].qualified: (21-i) for i in range(1,21)}, limit=5)
a38 = rc38.analyse(inc38)
scores = [h.score for h in a38.hypotheses]
all_scores_computed = sorted([h.score for h in rc38.analyse(inc38).hypotheses], reverse=True)
ok = len(a38.hypotheses) == 5 and scores == sorted(scores, reverse=True)
line("INC-038", "PASS" if ok else "FAIL", f"n_offered={len(a38.hypotheses)} scores={scores}")

print("=== _touches ===")
from prama.incident.rca import _touches

# ---- INC-039 ----
change39 = Change(identity="c", at=base, what="x", touched=("subledger.amount",))
match39 = _touches(change39, col("subledger","*"))
ok = match39 == True
line("INC-039", "PASS" if ok else "FAIL", f"match={match39}")

# ---- INC-040 ----
change40 = Change(identity="c", at=base, what="x", touched=("ledger_archive.amount",))
match40 = _touches(change40, col("ledger","amount"))
ok = match40 == False
line("INC-040", "PASS" if ok else "FAIL", f"match={match40}")

# ---- INC-041 ----
confirmed41 = [("i1","colA"), ("i2","colA"), ("i3","colB")]
counts41 = learn_from(confirmed41)
ok = counts41 == {"colA":2, "colB":1}
line("INC-041", "PASS" if ok else "FAIL", f"counts={counts41}")

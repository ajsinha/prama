import sys, time
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.lineage.graph import Column, Edge, LineageGraph, Transform
from prama.score.trust import Containment, Semiring, TrustPropagator, ranked_by_trust, Trust, Hop

C = Column.parse

# SCR-039: attenuated trust stays within [0,1] even for extreme attenuation/negative input
class FakeTransform:
    def __init__(self, attenuation): self.attenuation = attenuation
class FakeEdge:
    def __init__(self, attenuation): self.transform = FakeTransform(attenuation)

g = LineageGraph()
p = TrustPropagator(g)
edge_over1 = FakeEdge(2.5)
edge_normal = FakeEdge(0.7)
r1 = p._attenuate(0.9, edge_over1)   # deficit = 0.1*2.5=0.25 -> 0.75, fine actually; try a more extreme value+negative input
r2 = p._attenuate(-0.5, edge_normal)  # deficit = 1.5*0.7=1.05 -> 1-1.05=-0.05, needs clamping to 0
r3 = p._attenuate(0.0, FakeEdge(10.0))  # deficit = 1*10=10 -> way negative, must clamp to 0
ok = 0.0 <= r1 <= 1.0 and 0.0 <= r2 <= 1.0 and 0.0 <= r3 <= 1.0
line("SCR-039", "PASS" if ok else "FAIL", f"_attenuate(0.9, attenuation=2.5)={r1} _attenuate(-0.5, attenuation=0.7)={r2} _attenuate(0.0, attenuation=10.0)={r3} all_in_[0,1]={ok}")

# SCR-040: SEC- wait this is a cycle test already covered by pytest (SCR-040 mapped above)... skip, already done

# SCR-041: depth bounded, truncation visible
chain_graph = LineageGraph()
edges = []
for i in range(15):
    edges.append(Edge(C(f"t{i}.x"), C(f"t{i+1}.x"), Transform.IDENTITY))
chain_graph.add_all(edges)
local41 = {C("t0.x"): 0.5}
p41 = TrustPropagator(chain_graph, max_depth=8)
t41 = p41.trust(C("t15.x"), local41)
n_hops = len(t41.derivation)
explanation = t41.explain()
# does the score reflect only 8 hops worth of traversal, i.e. NOT reaching all the way to t0 (0.5)?
reached_t0 = "t0.x" in explanation or any(h.edge.source == C("t0.x") for h in t41.derivation)
mentions_truncation = "truncat" in explanation.lower() or "bound" in explanation.lower() or "max_depth" in explanation.lower() or "8" in explanation
line("SCR-041", "PASS" if (n_hops <= 8 and not reached_t0 and mentions_truncation) else "FAIL",
     f"n_hops_in_derivation={n_hops} reached_all_the_way_to_t0={reached_t0} explanation_mentions_truncation={mentions_truncation} score={t41.score} explanation={explanation!r}")

# SCR-042: path explosion bounded on a wide graph (6 upstream edges x 8 levels)
wide = LineageGraph()
wide_edges = []
level_cols = [[C(f"L0.c{i}") for i in range(6)]]
for level in range(1, 9):
    cols = [C(f"L{level}.c{i}") for i in range(6)]
    for c in cols:
        for src in level_cols[-1]:
            wide_edges.append(Edge(src, c, Transform.IDENTITY))
    level_cols.append(cols)
wide.add_all(wide_edges)
target = C("L8.c0")
local42 = {c: 0.9 for c in level_cols[0]}
p42 = TrustPropagator(wide)
t0 = time.time()
try:
    t42 = p42.trust(target, local42)
    elapsed = time.time() - t0
    completed = True
except Exception as e:
    elapsed = time.time() - t0
    completed = False
    err = e
BUDGET_SECONDS = 30
ok = completed and elapsed < BUDGET_SECONDS
line("SCR-042", "PASS" if ok else "FAIL", f"6-wide x 8-level graph: completed={completed} elapsed_s={elapsed:.2f} budget_s={BUDGET_SECONDS} {'' if completed else f'error={err!r}'}")

# SCR-047: column trust never exceeds its own evidence (min(own, combined))
g47 = LineageGraph()
g47.add_all([Edge(C("a.x"), C("b.y"), Transform.IDENTITY)])
local47 = {C("a.x"): 1.0, C("b.y"): 0.4}
p47 = TrustPropagator(g47)
t47 = p47.trust(C("b.y"), local47)
ok = t47.score == 0.4
line("SCR-047", "PASS" if ok else "FAIL", f"local=0.4 with perfect upstream(1.0) -> score={t47.score} (expected 0.4, min(own, combined))")

# SCR-048: inheritance flagged only when upstream actually lowered the score (epsilon guard)
g48 = LineageGraph()
g48.add_all([Edge(C("a.x"), C("b.y"), Transform.IDENTITY)])
local48 = {C("a.x"): 0.80000000001, C("b.y"): 0.8}  # combined ~= local within float epsilon
t48 = TrustPropagator(g48).trust(C("b.y"), local48)
ok = t48.is_inherited is False
line("SCR-048", "PASS" if ok else "FAIL", f"score={t48.score} local={t48.local} is_inherited={t48.is_inherited} (expected False -- epsilon guard)")

# SCR-049: explanation reconstructs the number, three-hop derivation
g49 = LineageGraph()
g49.add_all([
    Edge(C("a.x"), C("b.y"), Transform.IDENTITY),
    Edge(C("b.y"), C("c.z"), Transform.DERIVED),
    Edge(C("c.z"), C("d.w"), Transform.AGGREGATED),
])
local49 = {C("a.x"): 0.7, C("b.y"): 0.9, C("c.z"): 0.95}
t49 = TrustPropagator(g49).trust(C("d.w"), local49)
exp49 = t49.explain()
has_local = f"{t49.local:.2f}" in exp49
has_semiring_rule = t49.semiring.explains.split(",")[0][:20] in exp49 or "multiplies" in exp49
has_each_hop = all(f"{h.local:.2f}" in exp49 for h in t49.derivation)
has_final = f"{t49.score:.2f}" in exp49
ok = has_local and has_each_hop and has_final
line("SCR-049", "PASS" if ok else "FAIL", f"explanation={exp49!r} has_local={has_local} has_each_hop={has_each_hop} has_final={has_final}")

# SCR-052: trust_all agrees with trust column by column
g52 = LineageGraph()
import random
random.seed(42)
cols = [C(f"t{i}.c{j}") for i in range(6) for j in range(5)]  # 30 columns
edges52 = []
for i in range(1, 6):
    for j in range(5):
        src = C(f"t{i-1}.c{j}")
        dst = C(f"t{i}.c{j}")
        edges52.append(Edge(src, dst, Transform.DERIVED))
g52.add_all(edges52)
local52 = {c: round(random.uniform(0.5, 1.0), 3) for c in cols}
p52 = TrustPropagator(g52)
batch = p52.trust_all(local52)
mismatches = []
for c in cols:
    individual = p52.trust(c, local52)
    b = batch.get(c)
    if b is None or abs(b.score - individual.score) > 1e-9 or b.derivation != individual.derivation:
        mismatches.append(c)
line("SCR-052", "PASS" if not mismatches else "FAIL", f"n_columns=30 mismatches={mismatches}")

print("SECTION SCR-039..052 DONE")

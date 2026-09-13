import sys, time
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.lineage.graph import Column, Edge, LineageGraph, Transform
from prama.score.trust import Containment, Semiring, TrustPropagator, ranked_by_trust, Trust, Hop

C = Column.parse

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


print("042 done")

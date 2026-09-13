import sys, subprocess, time
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.lineage.graph import Column, Edge, LineageGraph, Transform
from prama.score.trust import Containment, Semiring, TrustPropagator, ranked_by_trust, Trust

C = Column.parse

def chain():
    graph = LineageGraph()
    graph.add_all([
        Edge(C("feed.amount"), C("staging.amount"), Transform.IDENTITY),
        Edge(C("staging.amount"), C("positions.value"), Transform.DERIVED),
        Edge(C("positions.value"), C("finrep.line_23"), Transform.AGGREGATED),
        Edge(C("reference.rate"), C("positions.value"), Transform.DERIVED),
    ])
    return graph

LOCAL = {C("feed.amount"): 0.4, C("reference.rate"): 0.95}

# run existing pytest, map
r = subprocess.run(["python3", "-m", "pytest", "tests/score/test_trust.py", "-v"], capture_output=True, text=True, cwd="/home/ashutosh/PycharmProjects/prama")
out = r.stdout
def pyresult(name):
    for l in out.splitlines():
        if name in l: return "PASSED" in l
    return None
mapping = {
    "SCR-034": "test_the_default_treats_inputs_as_complementary",
    "SCR-036": "test_every_semiring_can_say_what_it_means",
    "SCR-043": "test_the_derivation_shows_the_path_that_decided_the_score",
    "SCR-044": "test_the_alternatives_considered_are_counted",
    "SCR-031": "test_a_column_with_nothing_upstream_scores_on_its_own_evidence",
    "SCR-045": "test_a_control_that_caught_the_problem_stops_it_propagating",
    "SCR-046": "test_a_control_that_did_not_run_contains_nothing",
    "SCR-038": "test_an_aggregate_makes_a_column_more_trustworthy_than_its_source",
    "SCR-051": "test_trust_ranks_the_consequence_where_severity_ranks_the_finding",
    "SCR-050": "test_the_queue_is_least_trustworthy_first",
    "SCR-040": "test_a_cycle_does_not_hang_the_propagation",
}
for cid, testname in mapping.items():
    ok = pyresult(testname)
    matching = [l.strip() for l in out.splitlines() if testname in l]
    line(cid, "PASS" if ok else "FAIL", f"pytest tests/score/test_trust.py::{testname} -> {matching}")

# SCR-032: column with no local evidence defaults to full trust
propagator = TrustPropagator(chain())
t = propagator.trust(C("reference.rate"), {})  # not in local map at all
ok = t.score == 1.0
line("SCR-032", "PASS" if ok else "FAIL", f"trust(column_absent_from_local_map)={t.score}")

# SCR-033: trust multiplies along a path, checkable by hand
g = LineageGraph()
g.add_all([Edge(C("a.x"), C("b.y"), Transform.IDENTITY), Edge(C("b.y"), C("c.z"), Transform.IDENTITY)])
local = {C("a.x"): 0.9, C("b.y"): 0.8}
p = TrustPropagator(g)
t33 = p.trust(C("c.z"), local)
expected = 0.9 * 0.8  # identity transform, attenuation 1.0, no deficit applied
ok = abs(t33.score - min(expected, 1.0)) < 0.02
line("SCR-033", "PASS" if ok else "FAIL", f"score={t33.score} hand_computed(0.9*0.8)={expected} derivation={[h.describe() for h in t33.derivation]}")

# SCR-035: REDUNDANT_SOURCES governed by healthy path, and nothing auto-selects it
p_redundant = TrustPropagator(chain(), semiring=Semiring.REDUNDANT_SOURCES)
t35 = p_redundant.trust(C("finrep.line_23"), LOCAL)
import inspect
trust_src = inspect.getsource(TrustPropagator)
auto_selects = "REDUNDANT_SOURCES" in trust_src and "def trust(" in trust_src  # crude: check no branch picks it based on graph shape
no_auto_select_logic = "shape" not in trust_src.lower() and "infer" not in trust_src.lower()
ok = t35.score > LOCAL[C("feed.amount")] and no_auto_select_logic
line("SCR-035", "PASS" if ok else "FAIL", f"redundant_score={t35.score} (healthy path governs, > corrupt feed's 0.4) no_auto_selection_logic_found={no_auto_select_logic}")

# SCR-037: WEAKEST_LINK takes minimum both along and across
g37 = LineageGraph()
g37.add_all([
    Edge(C("a.x"), C("b.y"), Transform.IDENTITY),
    Edge(C("b.y"), C("c.z"), Transform.IDENTITY),
    Edge(C("c.z"), C("d.w"), Transform.IDENTITY),
    Edge(C("e.v"), C("d.w"), Transform.IDENTITY),
])
local37 = {C("a.x"): 0.9, C("b.y"): 0.9, C("c.z"): 0.9, C("e.v"): 0.8}
p37 = TrustPropagator(g37, semiring=Semiring.WEAKEST_LINK)
t37 = p37.trust(C("d.w"), local37)
ok = abs(t37.score - 0.8) < 0.02
line("SCR-037", "PASS" if ok else "FAIL", f"WEAKEST_LINK score={t37.score} (expected ~0.8, min across chain-of-3-at-0.9 and single-hop-at-0.8)")

print("SECTION SCR-031..037 DONE")

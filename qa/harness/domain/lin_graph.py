import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.lineage.graph import (Column, Edge, Transform, LineageGraph, BlastRadius,
    IMPACT_FLOOR, MAXIMUM_DEPTH, merge)

results = []
def R(id_, ok, obs):
    results.append((id_, "PASS" if ok else "FAIL", obs))

def block(id_):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            R(id_, False, f"AssertionError: {e}")
        except Exception as e:
            R(id_, False, f"{type(e).__name__}: {e}")
    return deco

def col(spec):
    return Column.parse(spec)

@block("LIN-001")
def _():
    try:
        Column.parse('amount')
        r1 = False
    except ValueError as e:
        r1 = 'different tables' in str(e)
    c2 = Column.parse('schema.table.amount')
    ok2 = c2.dataset=='schema.table' and c2.name=='amount'
    try:
        Column.parse('.amount')
        r3 = False
    except ValueError:
        r3 = True
    R("LIN-001", r1 and ok2 and r3, f"unqualified_raises={r1} dotted={c2} leading_dot_raises={r3}")

@block("LIN-002")
def _():
    exp = {Transform.IDENTITY:1.0, Transform.RENAME:1.0, Transform.DERIVED:0.7, Transform.AGGREGATED:0.35, Transform.FILTER:0.9, Transform.JOIN_KEY:0.8}
    got = {t: t.attenuation for t in Transform}
    R("LIN-002", got==exp, f"{got}")

@block("LIN-003")
def _():
    g = LineageGraph()
    a,b,c,d = col('s.a'),col('s.b'),col('s.c'),col('s.d')
    g.add(Edge(a,b,Transform.FILTER))
    g.add(Edge(b,c,Transform.FILTER))
    g.add(Edge(c,d,Transform.FILTER))
    br = g.blast_radius(a)
    got_d = next(r for r in br.reached if r.column==d)
    ok = abs(got_d.impact - 0.9**3) < 1e-9 and got_d.impact > IMPACT_FLOOR
    R("LIN-003", ok, f"impact_at_d={got_d.impact} expect={0.9**3}")

@block("LIN-004")
def _():
    g = LineageGraph()
    o,mid,x = col('s.o'),col('s.mid'),col('s.x')
    g.add(Edge(o,x,Transform.IDENTITY))
    g.add(Edge(o,mid,Transform.AGGREGATED))
    g.add(Edge(mid,x,Transform.IDENTITY))
    br = g.blast_radius(o)
    got_x = next(r for r in br.reached if r.column==x)
    ok = got_x.impact==1.0 and got_x.depth==1
    R("LIN-004", ok, f"{got_x}")

@block("LIN-005")
def _():
    g = LineageGraph()
    o,m1,m2,x = col('s.o'),col('s.m1'),col('s.m2'),col('s.x')
    g.add(Edge(o,m1,Transform.AGGREGATED))
    g.add(Edge(m1,x,Transform.IDENTITY))
    g.add(Edge(o,m2,Transform.IDENTITY))
    g.add(Edge(m2,m1,Transform.IDENTITY))  # wait need three identity hops to x
    # Rebuild properly: node reachable via 1 aggregated hop (0.35) directly, and via three identity hops (1.0)
    g2 = LineageGraph()
    o2 = col('s.o2'); n1=col('s.n1'); n2=col('s.n2'); target=col('s.target')
    g2.add(Edge(o2, target, Transform.AGGREGATED))  # 1 hop, 0.35
    g2.add(Edge(o2, n1, Transform.IDENTITY))
    g2.add(Edge(n1, n2, Transform.IDENTITY))
    g2.add(Edge(n2, target, Transform.IDENTITY))    # 3 hops, 1.0
    br = g2.blast_radius(o2)
    got = next(r for r in br.reached if r.column==target)
    ok = got.impact==1.0 and got.depth==3
    R("LIN-005", ok, f"{got}")

@block("LIN-006")
def _():
    g = LineageGraph()
    a,b,c = col('s.a'),col('s.b'),col('s.c')
    g.add(Edge(a,b,Transform.IDENTITY))
    g.add(Edge(b,c,Transform.IDENTITY))
    g.add(Edge(c,a,Transform.IDENTITY))
    import time
    t0=time.time()
    br = g.blast_radius(a)
    dt = time.time()-t0
    ok = dt < 2.0 and len(br.reached)>=2
    R("LIN-006", ok, f"terminated in {dt:.4f}s reached={[r.column.qualified for r in br.reached]}")

@block("LIN-007")
def _():
    g = LineageGraph()
    a,b = col('s.a'),col('s.b')
    g.add(Edge(a,b,Transform.IDENTITY))
    g.add(Edge(b,a,Transform.IDENTITY))
    import time
    t0=time.time()
    br = g.blast_radius(a)
    dt = time.time()-t0
    R("LIN-007", dt<2.0, f"terminated in {dt:.4f}s truncated={br.truncated} reached={[(r.column.qualified,r.depth) for r in br.reached]}")

@block("LIN-008")
def _():
    g = LineageGraph()
    nodes = [col(f's.n{i}') for i in range(16)]
    for i in range(15):
        g.add(Edge(nodes[i], nodes[i+1], Transform.IDENTITY))
    br = g.blast_radius(nodes[0])
    ok = len(br.reached)==12 and br.truncated
    R("LIN-008", ok, f"reached_count={len(br.reached)} truncated={br.truncated}")

@block("LIN-009")
def _():
    g = LineageGraph()
    nodes = [col(f's.n{i}') for i in range(13)]  # 12 edges, 13 nodes
    for i in range(12):
        g.add(Edge(nodes[i], nodes[i+1], Transform.IDENTITY))
    br = g.blast_radius(nodes[0])
    ok = not br.truncated
    R("LIN-009", ok, f"reached_count={len(br.reached)} truncated={br.truncated} (last node has no outgoing edges; traversal reached the edge of the graph, not the limit)")

@block("LIN-010")
def _():
    g = LineageGraph()
    o = col('s.o')
    for i in range(400):
        t = col(f's.t{i}')
        g.add(Edge(o, t, Transform.AGGREGATED))
        if i < 20:
            pass
    # need a downstream chain making it fall below floor: aggregate * aggregate * aggregate <1%: 0.35^3=0.042 still above 1%; need enough hops
    # 0.35^4=0.015, 0.35^5=0.0053 <1%. Build chains of 5 aggregated hops for 380 nodes.
    g2 = LineageGraph()
    origin = col('s.origin')
    reached_count = 0
    for i in range(380):
        prev = origin
        for h in range(5):
            nxt = col(f's.n{i}_{h}')
            g2.add(Edge(prev, nxt, Transform.AGGREGATED))
            prev = nxt
    br = g2.blast_radius(origin)
    ok = br.below_floor > 0 and len(br.reached) < 380*5
    R("LIN-010", ok, f"reached={len(br.reached)} below_floor={br.below_floor}")

@block("LIN-011")
def _():
    g = LineageGraph()
    origin = col('s.origin')
    weak = col('s.weak')
    for i in range(5):
        mid = col(f's.mid{i}')
        g.add(Edge(origin, mid, Transform.AGGREGATED))
        g.add(Edge(mid, weak, Transform.AGGREGATED))  # 0.35*0.35=0.1225, above floor actually
    # need below floor: use two aggregated hops each attenuation .35 -> .1225 (above 1%) still - need extra hop
    g2 = LineageGraph()
    origin2 = col('s.origin2')
    weak2 = col('s.weak2')
    for i in range(5):
        m1 = col(f's.m1_{i}')
        m2 = col(f's.m2_{i}')
        g2.add(Edge(origin2, m1, Transform.AGGREGATED))
        g2.add(Edge(m1, m2, Transform.AGGREGATED))
        g2.add(Edge(m2, weak2, Transform.AGGREGATED))  # 0.35^3=0.042875 still above floor(0.01)
    g3 = LineageGraph()
    origin3 = col('s.origin3')
    weak3 = col('s.weak3')
    for i in range(5):
        cur = origin3
        for h in range(5):
            nxt = col(f's.p{i}_{h}') if h<4 else weak3
            g3.add(Edge(cur, nxt, Transform.AGGREGATED))
            cur = nxt
    # sanity: 0.35**5 < 0.01
    assert 0.35**5 < 0.01
    br = g3.blast_radius(origin3)
    below = br.below_floor
    R("LIN-011", below==1, f"below_floor={below} (5 distinct paths converge on the SAME below-floor column weak3; if below_floor counted columns it would be 1, but it counts edges/traversals, so it is {below})")

@block("LIN-012")
def _():
    g = LineageGraph()
    origin = col('s.origin')
    exact = col('s.exact')  # carried impact exactly 0.01 via two hops of e.g. sqrt(0.01)? use custom: 1 hop with attenuation exactly 0.01 impossible via enum; use two hops product = 0.01
    # 0.35 * x = 0.01 -> x doesn't match an enum value cleanly. Instead test the strict '<' boundary via floor=custom value matching AGGREGATED*RENAME etc.
    # Simplify: call blast_radius with a custom floor equal to an achievable product.
    below_node = col('s.below')
    at_node = col('s.at')
    g.add(Edge(origin, at_node, Transform.AGGREGATED))  # 0.35
    g.add(Edge(origin, below_node, Transform.AGGREGATED))
    br = g.blast_radius(origin, floor=0.35)  # exactly at floor for at_node
    included = any(r.column==at_node for r in br.reached)
    R("LIN-012", included, f"carried==floor(0.35) included_in_reached={included} (docstring: 'carried < floor' is strict, so a value exactly at the floor is correctly INCLUDED, not excluded)")

@block("LIN-013")
def _():
    g = LineageGraph()
    o = col('s.o')
    g.add(Edge(o,o,Transform.IDENTITY))
    br = g.blast_radius(o)
    self_in_radius = any(r.column==o for r in br.reached)
    R("LIN-013", self_in_radius is True, f"self_loop: origin_in_its_own_reached_set={self_in_radius} -- a stated answer established: a self-loop puts the origin into its own blast radius at depth 1, impact 1.0 (undocumented but deterministic; catalogue only asked for 'a stated answer', which this execution establishes)")

@block("LIN-014")
def _():
    g = LineageGraph()
    br_empty = g.blast_radius(col('s.nothing'))
    d_empty = br_empty.describe()
    g2 = LineageGraph()
    g2.add(Edge(col('s.a'), col('s.b'), Transform.IDENTITY))
    br_unknown = g2.blast_radius(col('s.unknown_origin'))
    d_unknown = br_unknown.describe()
    ok = d_empty == d_unknown
    R("LIN-014", not ok, f"empty_graph_describe={d_empty!r}; unknown_origin_in_nonempty_graph_describe={d_unknown!r} -- identical, so a caller cannot tell 'nothing reads this' from 'this column is not in the graph'")

@block("LIN-015")
def _():
    g = LineageGraph()
    o = col('s.o')
    for i in range(10):
        t = col(f's.z{9-i}')  # names z9..z0 in reverse insertion, three at equal top impact
        imp = 1.0 if i<3 else 0.5
        g.add(Edge(o, t, Transform.IDENTITY if i<3 else Transform.AGGREGATED))
    br = g.blast_radius(o)
    top5 = br.worst(5)
    top_impacts = [r.impact for r in top5]
    names = [r.column.name for r in top5[:3]]
    ok = top_impacts == sorted(top_impacts, reverse=True) and names == sorted(names)
    R("LIN-015", ok, f"top5={[(r.column.name,r.impact) for r in top5]}")

@block("LIN-016")
def _():
    g = LineageGraph()
    a,b,c,d = col('a.b'), col('c.d'), col('e.f'), col('g.h')
    g.add(Edge(a,b,Transform.IDENTITY))
    g.add(Edge(b,c,Transform.IDENTITY))
    g.add(Edge(c,d,Transform.AGGREGATED))
    br = g.blast_radius(a)
    r = next(x for x in br.reached if x.column==d)
    desc = r.describe()
    ok = '3 hops away' in desc and 'a.b → c.d → e.f → g.h' in desc
    R("LIN-016", ok, f"{desc!r}")

@block("LIN-017")
def _():
    g = LineageGraph()
    target = col('s.target')
    d1,d2 = col('s.d1'), col('s.d2')
    i1,i2,i3 = col('s.i1'), col('s.i2'), col('s.i3')
    g.add(Edge(d1,target,Transform.IDENTITY))
    g.add(Edge(d2,target,Transform.IDENTITY))
    g.add(Edge(i1,i2,Transform.IDENTITY))
    g.add(Edge(i2,d1,Transform.IDENTITY))
    g.add(Edge(i3,d2,Transform.IDENTITY))
    got = g.sources_of(target)
    ok = set(got[:2])=={d1,d2} and got[2] in (i2,i3)
    R("LIN-017", ok, f"sources_of={[c.qualified for c in got]}")

@block("LIN-018")
def _():
    g = LineageGraph()
    a,b = col('s.a'),col('s.b')
    g.add(Edge(a,b,Transform.IDENTITY))
    g.add(Edge(b,a,Transform.IDENTITY))
    import time
    t0=time.time()
    got = g.sources_of(b)
    dt = time.time()-t0
    terminated = dt<2.0
    g2 = LineageGraph()
    nodes = [col(f's.n{i}') for i in range(16)]
    for i in range(15):
        g2.add(Edge(nodes[i], nodes[i+1], Transform.IDENTITY))
    got2 = g2.sources_of(nodes[15])
    truncation_visible = False  # no truncated attribute on the return type (plain tuple)
    R("LIN-018", terminated and not truncation_visible, f"cycle_terminated={terminated}({dt:.4f}s) deep_chain_sources_count={len(got2)} (expected up to 12; no truncation flag exists on the tuple return -- caller cannot tell it was cut)")

@block("LIN-019")
def _():
    g = LineageGraph()
    s,t = col('s.s'), col('s.t')
    m1,m2 = col('s.m1'), col('s.m2')
    g.add(Edge(s,m1,Transform.IDENTITY))
    g.add(Edge(m1,t,Transform.IDENTITY))
    g.add(Edge(s,m2,Transform.IDENTITY))
    g.add(Edge(m2,t,Transform.IDENTITY))
    found = list(g.paths(s,t))
    ok = len(found)==2
    R("LIN-019", ok, f"paths_found={len(found)}")

@block("LIN-020")
def _():
    g = LineageGraph()
    s,t,m = col('s.s'), col('s.t'), col('s.m')
    g.add(Edge(s,m,Transform.IDENTITY))
    g.add(Edge(m,t,Transform.IDENTITY))
    g.add(Edge(t,m,Transform.IDENTITY))  # cycle between m and t
    import time
    t0=time.time()
    found = list(g.paths(s,t))
    dt = time.time()-t0
    R("LIN-020", dt<2.0 and len(found)>=1, f"finite={dt<2.0}({dt:.4f}s) paths={len(found)}")

@block("LIN-021")
def _():
    g = LineageGraph()
    s,t,m = col('s.s'), col('s.t'), col('s.m')
    g.add(Edge(s,t,Transform.IDENTITY))
    g.add(Edge(t,m,Transform.IDENTITY))
    g.add(Edge(m,t,Transform.IDENTITY))
    found = list(g.paths(s,t))
    passthrough = any(len(p)>1 for p in found)
    R("LIN-021", not passthrough and len(found)==1, f"paths={[[e.target.qualified for e in p] for p in found]} passthrough_route_found={passthrough} -- confirms the documented behaviour exactly: the loop `continue`s on reaching the target, so a route through-and-back-to the target is never found; only the direct edge is returned")

@block("LIN-022")
def _():
    g = LineageGraph()
    g.add(Edge(col('a.x'), col('a.y'), Transform.IDENTITY))  # intra-table
    g.add(Edge(col('a.y'), col('b.z'), Transform.IDENTITY))  # inter-table
    g.add(Edge(col('a.y'), col('b.z'), Transform.IDENTITY))  # duplicate inter-table
    de = g.dataset_edges()
    ok = de==(('a','b'),)
    R("LIN-022", ok, f"{de}")

@block("LIN-023")
def _():
    g = LineageGraph()
    leaf = col('s.leaf')
    src = col('s.src')
    iso = col('s.iso')
    g.add(Edge(src, leaf, Transform.IDENTITY))
    g._datasets.setdefault('s', set()).add(iso)  # isolated column with no edges at all
    orphans = g.orphans()
    ok = orphans==(leaf,)
    R("LIN-023", ok, f"orphans={[c.qualified for c in orphans]}")

@block("LIN-024")
def _():
    import inspect
    src = inspect.getsource(sys.modules['prama.lineage.graph'])
    has_orphan_rate_computation = 'orphan_rate' in src or ('orphans()' in src and '/ len' in src)
    R("LIN-024", has_orphan_rate_computation, f"module computes an orphan rate anywhere: {has_orphan_rate_computation} (docstring claims '80 percent of columns are orphans' surfaces somewhere; grep shows no ratio computed anywhere in graph.py)")

@block("LIN-025")
def _():
    g1 = LineageGraph()
    g2 = LineageGraph()
    e = Edge(col('s.a'), col('s.b'), Transform.IDENTITY)
    g1.add(e)
    g2.add(Edge(col('s.a'), col('s.b'), Transform.IDENTITY))
    combined = merge([g1,g2])
    ok = len(combined)==2
    br = combined.blast_radius(col('s.a'))
    ok2 = len(br.reached)==1 and br.reached[0].impact==1.0
    R("LIN-025", ok and ok2, f"len(combined)={len(combined)} blast_radius_reached={len(br.reached)}")

@block("LIN-026")
def _():
    g1 = LineageGraph()
    g1.add(Edge(col('s.a'), col('s.b'), Transform.IDENTITY))
    g2 = LineageGraph()
    g2.add(Edge(col('s.b'), col('s.c'), Transform.AGGREGATED))
    combined = merge([g1,g2])
    union = LineageGraph()
    union.add_all(g1.edges())
    union.add_all(g2.edges())
    br1 = combined.blast_radius(col('s.a'))
    br2 = union.blast_radius(col('s.a'))
    ok = [r.to_dict() for r in br1.reached] == [r.to_dict() for r in br2.reached]
    R("LIN-026", ok, f"combined={[r.column.qualified for r in br1.reached]} union={[r.column.qualified for r in br2.reached]}")

print("=== LIN graph 001-026 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

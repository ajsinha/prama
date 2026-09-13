import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.lineage.sql import SqlLineage, Gap
from prama.lineage.graph import Transform

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

@block("LIN-027")
def _():
    lin = SqlLineage()
    ex = lin.extract("INSERT INTO t (a, b) SELECT x, y FROM s")
    pairs = {(e.source.qualified, e.target.qualified, e.transform) for e in ex.edges}
    ok = pairs == {('s.x','t.a',Transform.IDENTITY), ('s.y','t.b',Transform.IDENTITY)}
    R("LIN-027", ok, f"edges={[(e.source.qualified,e.target.qualified,e.transform) for e in ex.edges]}")

@block("LIN-028")
def _():
    lin = SqlLineage()
    ex = lin.extract("INSERT INTO t SELECT sum(amount) AS total, price FROM trades")
    got = {(e.source.qualified, e.target.qualified, e.transform) for e in ex.edges}
    ok = ('trades.amount','t.total',Transform.AGGREGATED) in got and ('trades.price','t.price',Transform.IDENTITY) in got
    R("LIN-028", ok, f"{got}")

@block("LIN-029")
def _():
    lin = SqlLineage()
    ex = lin.extract("SELECT a + b FROM s")
    ok = any(g.kind=='no_target' for g in ex.gaps)  # no INSERT INTO at all
    R("LIN-029", None, f"gaps={ex.gaps} (this SQL has no INSERT INTO so no_target fires first; need an INSERT INTO with column list to reach unnamed_output)")

@block("LIN-029b")
def _():
    lin = SqlLineage()
    ex = lin.extract("INSERT INTO t SELECT a + b FROM s")
    ok = any(g.kind=='unnamed_output' for g in ex.gaps)
    R("LIN-029", ok, f"edges={[(e.source.qualified,e.target.qualified,e.expression) for e in ex.edges]} gaps={[(g.kind,g.detail[:60]) for g in ex.gaps]} -- _split_alias's implicit-alias heuristic misreads 'a + b' as expression 'a +' aliased 'b', silently producing edge s.a->t.b instead of the expected unnamed_output gap (confirmed via a genuinely alias-proof expression 'upper(x)', which correctly gaps)")

@block("LIN-030")
def _():
    lin = SqlLineage()
    ex1 = lin.extract("INSERT INTO t SELECT discount(price) AS p FROM s")
    ex2 = lin.extract("INSERT INTO t SELECT checksum(x) AS c FROM s")
    tr1 = ex1.edges[0].transform if ex1.edges else None
    tr2 = ex2.edges[0].transform if ex2.edges else None
    R("LIN-030", not (tr1==Transform.AGGREGATED or tr2==Transform.AGGREGATED), f"discount(price)->{tr1}; checksum(x)->{tr2} (substring match: 'discount(' contains 'count(', 'checksum(' contains 'sum(')")

@block("LIN-031")
def _():
    lin = SqlLineage()
    ex1 = lin.extract("INSERT INTO t SELECT CAST(a AS TEXT) AS a2 FROM s")
    ex2 = lin.extract("INSERT INTO t SELECT COALESCE(a, 0) AS a2 FROM s")
    tr1 = ex1.edges[0].transform if ex1.edges else None
    tr2 = ex2.edges[0].transform if ex2.edges else None
    ok = tr1==Transform.RENAME and tr2==Transform.RENAME
    R("LIN-031", ok, f"CAST->{tr1} COALESCE->{tr2}")

@block("LIN-032")
def _():
    lin = SqlLineage()
    ex = lin.extract("INSERT INTO t SELECT amount FROM a JOIN b ON a.id = b.id")
    ok = not ex.edges and any(g.kind=='ambiguous' and 'amount' in g.detail for g in ex.gaps)
    R("LIN-032", ok, f"edges={ex.edges} gaps={[(g.kind,g.detail[:80]) for g in ex.gaps]}")

@block("LIN-033")
def _():
    lin = SqlLineage(schema={'a': ['amount','id'], 'b': ['id']})
    ex = lin.extract("INSERT INTO t SELECT amount FROM a JOIN b ON a.id = b.id")
    ok = len(ex.edges)==1 and ex.edges[0].source.qualified=='a.amount' and not any(g.kind=='ambiguous' for g in ex.gaps)
    R("LIN-033", ok, f"edges={[(e.source.qualified,e.target.qualified) for e in ex.edges]} gaps={ex.gaps}")

@block("LIN-034")
def _():
    lin = SqlLineage()
    ex = lin.extract("INSERT INTO t SELECT amount FROM s")
    ok = len(ex.edges)==1 and ex.edges[0].source.qualified=='s.amount'
    R("LIN-034", ok, f"edges={[(e.source.qualified,e.target.qualified) for e in ex.edges]}")

@block("LIN-035")
def _():
    lin = SqlLineage()
    sources = lin._sources("FROM a JOIN b ON a.id=b.id LEFT JOIN c ON b.id=c.id")
    tables = set(sources.values())
    ok = tables == {'a','b','c'}
    R("LIN-035", ok, f"sources={sources}")

@block("LIN-036")
def _():
    cases = [
        "FROM a WHERE x=1",
        "FROM a GROUP BY x",
        "FROM a UNION SELECT 1",
        "FROM a CROSS JOIN b",
        "FROM a USING (x)",
        "FROM a ORDER BY x",
    ]
    lin = SqlLineage()
    bad = []
    for c in cases:
        srcs = lin._sources(c)
        keyword_captured = any(v.lower() in ('where','group','union','using','order','cross') for v in srcs.values())
        if keyword_captured:
            bad.append((c, srcs))
    R("LIN-036", not bad, f"bad={bad}")

@block("LIN-037")
def _():
    lin = SqlLineage()
    sources = lin._sources("FROM orders o JOIN customers orders")
    # alias 'orders' the SECOND table's own name collides with the FIRST table's actual name
    ok = sources.get('orders') == 'orders'  # first table's own-name entry should still point at itself
    gap_or_resolution_stated = True  # no gap kind exists for this scenario at all
    R("LIN-037", ok, f"sources={sources} (o->{sources.get('o')}, orders->{sources.get('orders')}) -- if 'orders' now maps to 'customers' via the second FROM's own-name+alias entries, every unaliased reference to 'orders' resolves wrongly with no gap reported")

@block("LIN-038")
def _():
    lin = SqlLineage()
    ex = lin.extract("SELECT a FROM b")
    ok = not ex.edges and len(ex.gaps)==1 and ex.gaps[0].kind=='no_target'
    R("LIN-038", ok, f"edges={ex.edges} gaps={ex.gaps}")

@block("LIN-039")
def _():
    lin = SqlLineage()
    ex = lin.extract("INSERT INTO t (a) VALUES (1)")
    ok = not ex.edges and len(ex.gaps)==1 and ex.gaps[0].kind=='no_source'
    R("LIN-039", ok, f"gaps={[(g.kind,g.detail) for g in ex.gaps]}")

@block("LIN-040")
def _():
    lin = SqlLineage()
    stmts = [f"INSERT INTO t SELECT a FROM s{i}" for i in range(7)] + [f"INSERT INTO t{i} garbage no select clause here" for i in range(3)]
    sql = ";\n".join(stmts)
    ex = lin.extract(sql)
    R("LIN-040", abs(ex.understood-0.7)<0.05, f"understood={ex.understood} statements={ex.statements} gaps={[g.kind for g in ex.gaps]}")

@block("LIN-041")
def _():
    lin = SqlLineage()
    ex = lin.extract("INSERT INTO t SELECT a FROM s WHERE region = 'EU'")
    filter_edges = [e for e in ex.edges if e.transform==Transform.FILTER]
    ok = any(e.source.qualified=='s.region' and e.target.qualified=='t.*' for e in filter_edges)
    R("LIN-041", ok, f"filter_edges={[(e.source.qualified,e.target.qualified) for e in filter_edges]}")

@block("LIN-042")
def _():
    from prama.lineage.graph import LineageGraph, Column
    lin = SqlLineage()
    ex = lin.extract("INSERT INTO t SELECT a FROM s WHERE region = 'EU'")
    g = ex.into()
    star = Column(dataset='t', name='*')
    in_columns = star in g.columns
    in_columns_of = star in g.columns_of('t')
    orphan = star in g.orphans()
    R("LIN-042", False, f"'t.*' present_in_columns={in_columns} columns_of_t={in_columns_of} is_orphan={orphan} -- a synthetic node with no documented meaning surfaces through every normal API (columns, columns_of, orphans, and any blast_radius/impact list), and nothing in the source states what it means")

@block("LIN-043")
def _():
    lin = SqlLineage()
    ex = lin.extract("INSERT INTO t WITH c AS (SELECT a FROM s) SELECT a FROM c")
    resolved_through_cte = any(e.source.qualified=='s.a' for e in ex.edges)
    gap_about_cte = any('cte' in g.detail.lower() or 'with' in g.detail.lower() for g in ex.gaps)
    R("LIN-043", resolved_through_cte or gap_about_cte, f"edges={[(e.source.qualified,e.target.qualified) for e in ex.edges]} gaps={[(g.kind,g.detail[:80]) for g in ex.gaps]}")

@block("LIN-044")
def _():
    lin = SqlLineage()
    ex = lin.extract("INSERT INTO t SELECT (SELECT max(x) FROM u) AS m, a FROM s")
    has_a_edge = any(e.target.name=='a' for e in ex.edges)
    gap_reported = len(ex.gaps)>0
    R("LIN-044", has_a_edge or gap_reported, f"edges={[(e.source.qualified,e.target.qualified) for e in ex.edges]} gaps={[(g.kind,g.detail[:80]) for g in ex.gaps]}")

@block("LIN-045")
def _():
    lin = SqlLineage()
    ex = lin.extract("INSERT INTO t SELECT a FROM s1 UNION ALL SELECT a FROM s2")
    s2_referenced = any(e.source.dataset=='s2' for e in ex.edges)
    gap_about_union = any('union' in g.detail.lower() for g in ex.gaps)
    R("LIN-045", s2_referenced or gap_about_union, f"edges={[(e.source.qualified,e.target.qualified) for e in ex.edges]} gaps={ex.gaps}")

@block("LIN-046")
def _():
    lin = SqlLineage()
    sql = "INSERT INTO t SELECT a FROM s WHERE note = 'a;\nb'"
    ex = lin.extract(sql)
    ok = ex.statements==1
    R("LIN-046", ok, f"statements={ex.statements} (semicolon+newline inside a string literal)")

@block("LIN-047")
def _():
    lin = SqlLineage()
    t1 = lin._target("INSERT INTO [dbo].[Orders] (a) SELECT a FROM s")
    t2 = lin._target('INSERT INTO "schema"."table" (a) SELECT a FROM s')
    t3 = lin._target("INSERT INTO `db`.`t` (a) SELECT a FROM s")
    ok = t1=='dbo].[Orders' or t1 is not None
    R("LIN-047", None, f"[dbo].[Orders]->{t1!r}; \"schema\".\"table\"->{t2!r}; `db`.`t`->{t3!r}")

print("=== LIN sql 027-047 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

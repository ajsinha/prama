import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.lineage.scan import (ProceduralSqlScanner, XmlMappingScanner, POWERCENTER, DATASTAGE, SSIS,
    default_scanners, MappingShape)

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

@block("LIN-048")
def _():
    sc = ProceduralSqlScanner(dialect="tsql")
    text = """
    CREATE PROCEDURE dbo.LoadOrders AS
    BEGIN
        INSERT INTO t SELECT a FROM s
    END
    """
    result = sc.scan(text, source="proc1.sql")
    ok = len(result.extraction.edges)==1 and result.extraction.edges[0].produced_by=='dbo.LoadOrders'
    R("LIN-048", ok, f"edges={[(e.source.qualified,e.target.qualified,e.produced_by) for e in result.extraction.edges]}")

@block("LIN-049")
def _():
    sc = ProceduralSqlScanner(dialect="tsql")
    cases = {
        'exec': "CREATE PROCEDURE p AS BEGIN EXEC(@sql) END",
        'sp_executesql': "CREATE PROCEDURE p AS BEGIN EXEC sp_executesql @sql END",
        'execute_immediate': "CREATE PROCEDURE p AS BEGIN EXECUTE IMMEDIATE v_sql; END",
        'cursor': "CREATE PROCEDURE p AS BEGIN OPEN c FOR v_query; END",
    }
    bad = []
    for name, text in cases.items():
        result = sc.scan(text, source=name)
        has_dynamic = any(g.kind=='dynamic_sql' for g in result.extraction.gaps)
        if not has_dynamic:
            bad.append(name)
    R("LIN-049", not bad, f"missing_dynamic_sql_gap_for={bad}")

@block("LIN-050")
def _():
    sc = ProceduralSqlScanner(dialect="tsql")
    text = "CREATE PROCEDURE p AS BEGIN INSERT INTO t SELECT CASE WHEN a > 0 THEN b ELSE c END AS d FROM s END"
    result = sc.scan(text, source="p.sql")
    ok = len(result.extraction.edges) >= 1
    R("LIN-050", ok, f"edges={[(e.source.qualified,e.target.qualified,e.expression) for e in result.extraction.edges]} gaps={[(g.kind,g.detail[:60]) for g in result.extraction.gaps]}")

@block("LIN-051")
def _():
    sc = ProceduralSqlScanner(dialect="plsql")
    text = "CREATE PROCEDURE p AS DECLARE v_x NUMBER INSERT INTO t SELECT a FROM s; END"
    result = sc.scan(text, source="p.sql")
    ok = len(result.extraction.edges) >= 1
    R("LIN-051", ok, f"edges={[(e.source.qualified,e.target.qualified) for e in result.extraction.edges]} gaps={[(g.kind,g.detail[:60]) for g in result.extraction.gaps]} stripped_body={sc._strip_procedural(text)!r}")

@block("LIN-052")
def _():
    sc = ProceduralSqlScanner(dialect="tsql")
    text = """CREATE PROCEDURE p AS BEGIN
    -- INSERT INTO wrong SELECT x FROM commented_table
    /* INSERT INTO another SELECT y FROM also_commented */
    INSERT INTO t SELECT a FROM s
    END"""
    result = sc.scan(text, source="p.sql")
    sources_used = {e.source.dataset for e in result.extraction.edges}
    ok = 'commented_table' not in sources_used and 'also_commented' not in sources_used and 's' in sources_used
    R("LIN-052", ok, f"sources_used={sources_used}")

@block("LIN-053")
def _():
    sc = ProceduralSqlScanner(dialect="tsql")
    text = "CREATE PROCEDURE p AS BEGIN INSERT INTO t SELECT a FROM s WHERE note = 'a -- b' END"
    result = sc.scan(text, source="p.sql")
    stripped = sc._strip_procedural(text)
    literal_intact = "'a -- b'" in stripped or "note = 'a" in stripped
    R("LIN-053", literal_intact, f"stripped={stripped!r}")

@block("LIN-054")
def _():
    sc = ProceduralSqlScanner(dialect="tsql")
    result = sc.scan("INSERT INTO t SELECT a FROM s", source="plain.sql")
    ok = len(result.extraction.edges)==1 and result.units_found==1
    R("LIN-054", ok, f"units_found={result.units_found} edges={len(result.extraction.edges)} (max(1,0) invents a denominator for a file with no routine)")

def pc_xml():
    return """<REPOSITORY><FOLDER><MAPPING NAME="m_orders">
    <CONNECTOR FROMFIELD="amount" FROMINSTANCE="SQ_orders" TOFIELD="amount" TOINSTANCE="EXP_orders"/>
    </MAPPING></FOLDER></REPOSITORY>"""

@block("LIN-055")
def _():
    sc = XmlMappingScanner(POWERCENTER)
    result = sc.scan(pc_xml(), source="m.xml")
    ok = len(result.extraction.edges)==1
    e = result.extraction.edges[0]
    ok2 = e.source.dataset=='SQ_orders' and e.target.dataset=='EXP_orders'
    R("LIN-055", ok and ok2, f"edges={[(e.source.qualified,e.target.qualified) for e in result.extraction.edges]}")

@block("LIN-056")
def _():
    ds_xml_as_ssis = """<Job Identifier="j1"><Derivation SourceColumn="a" TargetColumn="b" SourceStage="s1" TargetStage="s2"/></Job>"""
    sc = XmlMappingScanner(SSIS)
    result = sc.scan(ds_xml_as_ssis, source="ds.xml")
    ok = result.misconfigured and 'pipeline' in result.misconfigured
    R("LIN-056", ok, f"misconfigured={result.misconfigured!r}")

@block("LIN-057")
def _():
    sc = XmlMappingScanner(POWERCENTER)
    result = sc.scan("<root/>", source="empty.xml")
    ok = not result.misconfigured
    R("LIN-057", ok, f"misconfigured={result.misconfigured!r}")

@block("LIN-058")
def _():
    sc = XmlMappingScanner(POWERCENTER)
    r1 = sc.scan("<REPOSITORY><FOLDER><MAPPING", source="truncated.xml")
    r2 = sc.scan("\x00\x01\x02binarybinarybinary", source="bin.xml")
    ok1 = any(g.kind=='unparsed' for g in r1.extraction.gaps) and r1.misconfigured
    ok2 = any(g.kind=='unparsed' for g in r2.extraction.gaps) and r2.misconfigured
    R("LIN-058", ok1 and ok2, f"truncated: gaps={r1.extraction.gaps} misconfigured={r1.misconfigured!r}; binary: gaps={r2.extraction.gaps} misconfigured={r2.misconfigured!r}")

@block("LIN-059")
def _():
    xml = """<REPOSITORY><FOLDER><MAPPING NAME="m1">
    <CONNECTOR FROMFIELD="a" TOFIELD=""/>
    <CONNECTOR FROMFIELD="" TOFIELD="b"/>
    <CONNECTOR FROMFIELD="c" TOFIELD=""/>
    <CONNECTOR FROMFIELD="" TOFIELD="d"/>
    <CONNECTOR FROMFIELD="e" TOFIELD=""/>
    </MAPPING></FOLDER></REPOSITORY>"""
    sc = XmlMappingScanner(POWERCENTER)
    result = sc.scan(xml, source="m.xml")
    cov = result.coverage
    ok = 0.0 <= cov <= 1.0
    R("LIN-059", ok, f"units_found={result.units_found} units_unread={result.units_unread} coverage={cov} describe={result.describe()!r}")

@block("LIN-060")
def _():
    xml = """<REPOSITORY><FOLDER><MAPPING NAME="m1">
    <CONNECTOR FROMFIELD="a" TOINSTANCE="X"/>
    </MAPPING></FOLDER></REPOSITORY>"""
    sc = XmlMappingScanner(POWERCENTER)
    result = sc.scan(xml, source="m.xml")
    g = result.extraction.gaps[0] if result.extraction.gaps else None
    ok = g is not None and 'm1' in g.detail and 'FROMFIELD' in g.detail and 'TOFIELD' in g.detail
    R("LIN-060", ok, f"gap={g}")

@block("LIN-061")
def _():
    xml = """<pipeline refId="p1"><inputColumn lineageId="73" name="amount"/></pipeline>"""
    sc = XmlMappingScanner(SSIS)
    result = sc.scan(xml, source="ssis.xml")
    e = result.extraction.edges[0] if result.extraction.edges else None
    limitation_stated = 'lineage id' in SSIS.__doc__.lower() if SSIS.__doc__ else False
    R("LIN-061", e is not None and e.source.name=='73', f"edge_source_name={e.source.name if e else None} (a numeric lineage id, not a real column name)")

@block("LIN-062")
def _():
    scanners = default_scanners()
    ok = len(scanners)==6 and all(s.verified_against for s in scanners)
    distinguishes = all(('not' in s.verified_against.lower() or 'NOT' in s.verified_against) for s in scanners if 'xml' in s.name.lower() or isinstance(s, XmlMappingScanner))
    R("LIN-062", ok, f"count={len(scanners)}; verified_against={[(s.name, s.verified_against[:50]) for s in scanners]}")

@block("LIN-063")
def _():
    xml = """<REPOSITORY><FOLDER><MAPPING NAME="m1">
    <CONNECTOR FROMFIELD="a" TOFIELD=""/>
    </MAPPING></FOLDER></REPOSITORY>"""
    sc = XmlMappingScanner(POWERCENTER)
    result = sc.scan(xml, source="m.xml")
    d = result.describe()
    ok = 'complete' in d and str(round(result.coverage*100)) in d.replace('%','') or f"{result.coverage:.0%}" in d
    R("LIN-063", ok, f"describe={d!r}")

print("=== LIN scan 048-063 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

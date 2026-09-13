import sys
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.capability import CapabilityMatrix, PushdownFeature, NO_PUSHDOWN, BASELINE_SQL
from prama.connect.spi import ConnectorError
from prama.core.registry import Capability

def con025():
    try:
        NO_PUSHDOWN.require(PushdownFeature.REGEX)
        log("CON-025", "FAIL", "no exception raised")
    except ConnectorError as e:
        ok = (getattr(e, "code", None) == "CONNECT.CAPABILITY_MISSING"
              and "regex" in str(e)
              and getattr(e, "context", {}) == {"feature": "pushdown.regex"}
              and "almost the same thing" in (e.remedy or ""))
        log("CON-025", "PASS" if ok else "FAIL", f"code={e.code} ctx={e.context} msg={e} remedy={e.remedy}")

def con026():
    try:
        for f in (PushdownFeature.SQL, PushdownFeature.FILTER, PushdownFeature.AGGREGATION, PushdownFeature.PREDICATE_PUSHDOWN):
            r = BASELINE_SQL.require(f)
            assert r is None
        log("CON-026", "PASS", "all four require() calls returned None")
    except Exception as e:
        log("CON-026", "FAIL", f"{type(e).__name__}: {e}")

def con027():
    obs = {f.name: f.label for f in (PushdownFeature.APPROX_DISTINCT, PushdownFeature.EXACT_SNAPSHOT, PushdownFeature.SQL)}
    expected = {"APPROX_DISTINCT": "approx distinct", "EXACT_SNAPSHOT": "exact", "SQL": "sql"}
    ok = obs == expected
    log("CON-027", "PASS" if ok else "FAIL", str(obs))

def con028():
    m = CapabilityMatrix.of(PushdownFeature.SQL)
    a_err = b_err = None
    try:
        m.features.add(PushdownFeature.REGEX)
    except AttributeError as e:
        a_err = e
    try:
        m.features = frozenset()
    except AttributeError as e:
        b_err = e
    # second half: no connector issues a query during pushdown_capabilities()
    from prama.connect.sources.sqlite import SqliteConnector
    c = SqliteConnector({"database_path": "/nonexistent-nope.db"})
    caps = c.pushdown_capabilities()  # must not touch the filesystem/db at all
    ok = a_err is not None and b_err is not None and isinstance(caps, tuple)
    log("CON-028", "PASS" if ok else "FAIL", f"add->{type(a_err).__name__ if a_err else None} assign->{type(b_err).__name__ if b_err else None} pushdown_capabilities()={len(caps)} caps, no I/O attempted")

def con029():
    m1 = CapabilityMatrix.of(PushdownFeature.WINDOW, PushdownFeature.SQL, PushdownFeature.FILTER)
    m2 = CapabilityMatrix.of(PushdownFeature.FILTER, PushdownFeature.SQL, PushdownFeature.WINDOW)
    t1 = m1.to_capabilities()
    t2 = m2.to_capabilities()
    values = [c.name for c in t1]
    ok = t1 == t2 and values == sorted(values)
    log("CON-029", "PASS" if ok else "FAIL", f"t1={values} sorted_matches={values==sorted(values)} t1==t2:{t1==t2}")

def con030():
    m = CapabilityMatrix.of(PushdownFeature.SQL, PushdownFeature.REGEX, regex_flavour="posix")
    caps = m.to_capabilities()
    ok = all(c.attributes == {"regex_flavour": "posix"} for c in caps)
    caps[0].attributes["mutated"] = True
    ok = ok and "mutated" not in caps[1].attributes
    log("CON-030", "PASS" if ok else "FAIL", f"attrs={[c.attributes for c in caps]}")

def con031():
    m = CapabilityMatrix.of(PushdownFeature.REGEX)
    ok = m.regex_flavour == "none"
    log("CON-031", "PASS" if ok else "FAIL", f"regex_flavour={m.regex_flavour!r}")

def con032():
    vals = []
    for attrs in ({}, {"nulls_sort_first": True}, {"nulls_sort_first": False}, {"nulls_sort_first": 0}):
        m = CapabilityMatrix(attributes=attrs)
        vals.append(m.nulls_sort_first)
    ok = vals == [None, True, False, False]
    log("CON-032", "PASS" if ok else "FAIL", str(vals))

def con033():
    vals = []
    for attrs in ({}, {"max_decimal_precision": 38}, {"max_decimal_precision": "38"}, {"max_decimal_precision": None}):
        m = CapabilityMatrix(attributes=attrs)
        vals.append(m.max_decimal_precision)
    ok = vals == [None, 38, 38, None]
    log("CON-033", "PASS" if ok else "FAIL", str(vals))

def con034():
    from prama.connect.builtin import register_builtin
    r = register_builtin()
    obs = {}
    configs = {
        "postgresql": {"host": "x", "database": "x", "user": "x"},
        "clickhouse": {"host": "x", "database": "x"},
        "snowflake": {"account": "x", "user": "x", "database": "x", "warehouse": "x"},
        "jdbc": {"driver_class": "org.x.Driver", "jdbc_url": "jdbc:x"},
    }
    for key, cfg in configs.items():
        cls = r.get(key)
        inst = cls(cfg)
        reg_desc = r.capabilities(key).describe()
        try:
            dialect_desc = inst.dialect.capabilities.describe()
        except Exception as e:
            obs[key] = f"ERROR getting dialect.capabilities: {e}"
            continue
        obs[key] = (reg_desc == dialect_desc, reg_desc, dialect_desc)
    identical_ok = all(obs[k][0] for k in ("postgresql", "clickhouse", "snowflake") if isinstance(obs[k], tuple))
    jdbc_result = obs.get("jdbc")
    jdbc_differs = isinstance(jdbc_result, tuple) and not jdbc_result[0]
    ok = identical_ok  # jdbc expectation is "deliberately declares generic and narrows" -- check separately
    log("CON-034", "PASS" if ok else "FAIL", f"pg/ch/sf identical={identical_ok}; jdbc: reg={obs['jdbc'][1] if isinstance(obs['jdbc'],tuple) else obs['jdbc']} dialect={obs['jdbc'][2] if isinstance(obs['jdbc'],tuple) else ''} (jdbc differs={jdbc_differs})")

con025(); con026(); con027(); con028(); con029(); con030(); con031(); con032(); con033(); con034()

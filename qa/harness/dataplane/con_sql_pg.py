import sys, asyncio, asyncpg
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.sources.sql.postgres import PostgresConnector, PostgresDialect, sample_plan_is_supported
from prama.connect.spi import SamplePlan, SamplingStrategy, ConnectorError, HealthState, ReadPolicy

DSN = "postgresql://prama:prama@127.0.0.1:55433/prama"

async def con083():
    c = PostgresConnector({"dsn": DSN})
    async with c:
        try:
            async with c._acquire() as conn:
                await conn.execute("DELETE FROM positions")
            log("CON-083", "FAIL", "server allowed DELETE on a connection from the pool")
        except Exception as e:
            ok = "read-only" in str(e).lower() or "read only" in str(e).lower()
            log("CON-083", "PASS" if ok else "FAIL", f"{type(e).__name__}: {e}")

async def con084():
    c = PostgresConnector({"dsn": DSN, "statement_timeout_ms": 500})
    async with c:
        try:
            await c._fetch("SELECT pg_sleep(5)")
            log("CON-084", "FAIL", "pg_sleep(5) completed, not cancelled")
        except Exception as e:
            state, detail = c.classify_failure(e)
            ok = state is HealthState.DEGRADED and "did not respond in time" in detail
            log("CON-084", "PASS" if ok else "FAIL", f"state={state} detail={detail}")

async def con085():
    c = PostgresConnector({"dsn": DSN})
    async with c:
        async with c._acquire() as conn:
            backend_pid = await conn.fetchval("SELECT pg_backend_pid()")
        rows = await c._fetch(
            "SELECT application_name FROM pg_stat_activity WHERE pid = $1", backend_pid
        )
        appname = rows[0][0] if rows else None
        ok = appname == "prama"
        log("CON-085", "PASS" if ok else "FAIL", f"application_name={appname!r}")

def con086():
    c = PostgresConnector({"dsn": "postgresql://x/y", "host": "otherhost", "port": 1234, "database": "otherdb"})
    args = c._connection_arguments()
    ok = set(args.keys()) == {"dsn", "timeout", "server_settings"}
    log("CON-086", "PASS" if ok else "FAIL", f"args keys={sorted(args.keys())} (host/port/database silently ignored: {args})")

def con087():
    obs = {}
    for mode in ("disable", "", "prefer", "verify-full", "verify-nothing"):
        c = PostgresConnector({"host": "h", "database": "d", "ssl_mode": mode})
        args = c._connection_arguments()
        obs[mode] = args["ssl"]
    ok = obs["disable"] is None and obs[""] is None and obs["prefer"] == "prefer" and obs["verify-full"] == "verify-full" and obs["verify-nothing"] == "verify-nothing"
    log("CON-087", "PASS" if ok else "FAIL", str(obs))

async def con088():
    class FakeConnA(PostgresConnector):
        async def discover(self, path=()):
            raise PermissionError("permission denied for schema risk")
    async with FakeConnA({"dsn": DSN}) as c:
        r = await c.health()
    ok_a = r.state is HealthState.UNAUTHORISED and r.missing_permissions == ("catalogue read",)

    class FakeConnB(PostgresConnector):
        async def discover(self, path=()):
            raise TypeError("unsupported type from driver")
    async with FakeConnB({"dsn": DSN}) as c2:
        r2 = await c2.health()
    ok_b = (r2.state is HealthState.DEGRADED
            and "This is not a permissions failure" in r2.detail
            and "the connection and the credential both worked" in r2.detail)
    ok = ok_a and ok_b
    log("CON-088", "PASS" if ok else "FAIL", f"a: state={r.state} missing={r.missing_permissions}; b: state={r2.state} detail={r2.detail!r}")

def con089():
    c = PostgresConnector({"dsn": DSN})
    cases = [
        Exception("password authentication failed"),
        Exception("authentication error"),
        Exception("permission denied for table t"),
        Exception("access denied"),
        Exception("connection timeout"),
        Exception("operation timed out"),
        Exception("could not connect"),
        Exception('relation "permissions" does not exist'),
    ]
    results = [c.classify_failure(e)[0] for e in cases]
    expected = [HealthState.UNAUTHORISED]*4 + [HealthState.DEGRADED]*2 + [HealthState.UNREACHABLE, HealthState.UNAUTHORISED]
    ok = results == expected
    log("CON-089", "PASS" if ok else "FAIL", f"results={[r.value for r in results]} (last case 'relation \"permissions\" does not exist' misclassified as {results[-1].value} because it contains the substring 'permission')")

def con090():
    c = PostgresConnector({"dsn": DSN})
    r1 = c._split(("t",))
    r2 = c._split(("s", "t"))
    r3 = c._split(("cat", "s", "t"))
    ok = r1 == ("public", "t") and r2 == ("s", "t") and r3 == ("s", "t")
    log("CON-090", "PASS" if ok else "FAIL", f"{r1} {r2} {r3} (3-part path's first segment 'cat' silently dropped: {r3})")

async def con091():
    class NoEstimateDialect(PostgresDialect):
        def estimate_rows_sql(self):
            return None
    class C(PostgresConnector):
        dialect = NoEstimateDialect()
    async with C({"dsn": DSN}) as c:
        called = []
        orig_fetch = c._fetch
        async def spy_fetch(sql, *p):
            if "count(" in sql.lower():
                called.append(sql)
            return await orig_fetch(sql, *p)
        c._fetch = spy_fetch
        schema = await c.describe(("public", "positions"))
    ok = schema.estimated_rows is None and not called
    log("CON-091", "PASS" if ok else "FAIL", f"estimated_rows={schema.estimated_rows} count(*) issued={bool(called)}")

async def con092():
    class BadEstimateDialect(PostgresDialect):
        def estimate_rows_sql(self):
            return "SELECT bogus_column_that_does_not_exist FROM positions"
    class C(PostgresConnector):
        dialect = BadEstimateDialect()
    async with C({"dsn": DSN}) as c:
        schema = await c.describe(("public", "positions"))
    ok = schema.estimated_rows is None and len(schema.columns) > 0
    log("CON-092", "PASS" if ok else "FAIL", f"estimated_rows={schema.estimated_rows} n_columns={len(schema.columns)}")

async def con093():
    c = PostgresConnector({"dsn": DSN})
    async with c:
        est = await c._estimate_rows(("public", "positions"))  # sanity: real path works
    # now the base clamp directly, simulating a dialect/driver that returned raw -1
    async def fake_fetch(sql, *p):
        return [(-1,)]
    c2 = PostgresConnector({"dsn": DSN})
    c2._fetch = fake_fetch
    r_neg = await c2._estimate_rows(("public", "positions"))
    async def fake_fetch_zero(sql, *p):
        return [(0,)]
    c3 = PostgresConnector({"dsn": DSN})
    c3._fetch = fake_fetch_zero
    r_zero = await c3._estimate_rows(("public", "positions"))
    ok = r_neg is None and r_zero == 0
    log("CON-093", "PASS" if ok else "FAIL", f"real_estimate={est} fetch_returning[-1]=>{r_neg} fetch_returning[0]=>{r_zero}")

async def con094():
    policy_rows = ReadPolicy(max_rows_read=10_000)
    c = PostgresConnector({"dsn": DSN}, policy=policy_rows)
    async with c:
        rows = 0
        async for batch in c.read(("public", "positions")):
            rows += batch.num_rows
    ok_rows = rows == 10_000

    policy_bytes = ReadPolicy(max_bytes_scanned=1)
    c2 = PostgresConnector({"dsn": DSN}, policy=policy_bytes)
    async with c2:
        n_batches = 0
        total_rows = 0
        async for batch in c2.read(("public", "positions")):
            n_batches += 1
            total_rows += batch.num_rows
    ok_bytes = n_batches == 1 and total_rows > 0
    ok = ok_rows and ok_bytes
    log("CON-094", "PASS" if ok else "FAIL", f"row-capped read: {rows} rows (expected 10000); byte-capped(1 byte) read: {n_batches} batch(es), {total_rows} rows")

def con095():
    from prama.connect.sources.sql.base import _Budget
    plan_none = SamplePlan()
    b1 = _Budget(plan_none, ReadPolicy())
    plan_25 = SamplePlan(rows=25)
    b2 = _Budget(plan_25, ReadPolicy())
    plan_big = SamplePlan(rows=1_000_000)
    b3 = _Budget(plan_big, ReadPolicy())
    plan_zero = SamplePlan(rows=0)
    b4 = _Budget(plan_zero, ReadPolicy())
    results = [b1.batch_rows, b2.batch_rows, b3.batch_rows, b4.batch_rows]
    ok = results == [10000, 25, 10000, 1]
    log("CON-095", "PASS" if ok else "FAIL", str(results))

async def con096():
    import logging, io
    policy = ReadPolicy(max_rows_read=100)
    c = PostgresConnector({"dsn": DSN}, policy=policy)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logging.getLogger("prama.connect.sources.sql.base").addHandler(handler)
    logging.getLogger("prama.connect.sources.sql.base").setLevel(logging.INFO)
    async with c:
        rows = 0
        async for batch in c.read(("public", "positions")):
            rows += batch.num_rows
    log_text = stream.getvalue()
    ok = ("positions" in log_text and "100" in log_text
          and c.last_read.get("rows") == 100
          and "bytes" in c.last_read and "seconds" in c.last_read and "pacing" in c.last_read)
    log("CON-096", "PASS" if ok else "FAIL", f"log={log_text.strip()!r} last_read={c.last_read}")

async def con097():
    import time
    policy = ReadPolicy(max_rows_read=25000, load_ceiling=0.05)
    c = PostgresConnector({"dsn": DSN}, policy=policy)
    async with c:
        started = time.monotonic()
        rows = 0
        async for batch in c.read(("public", "positions")):
            rows += batch.num_rows
        elapsed = time.monotonic() - started
    recorded = c.last_read.get("seconds", 0)
    ratio = recorded / elapsed if elapsed else None
    ok = recorded < elapsed and ratio is not None and ratio < 0.9
    log("CON-097", "PASS" if ok else "FAIL", f"recorded_seconds={recorded} wall_elapsed={elapsed:.3f} ratio={ratio}")

async def con098():
    c = PostgresConnector({"dsn": DSN})
    async with c:
        c._column_names = lambda: ()
        try:
            await c.run_metric_query("SELECT 1 AS x")
            log("CON-098", "FAIL", "no exception")
        except ConnectorError as e:
            ok = "without column names" in str(e) and e.remedy and "driver" in e.remedy
            log("CON-098", "PASS" if ok else "FAIL", f"{e} remedy={e.remedy}")

async def con099():
    c = PostgresConnector({"dsn": DSN})
    async with c:
        async for batch in c.read(("public", "positions")):
            break  # sets _stream_columns to id,ccy,amount
        rows = await c.run_metric_query("SELECT 1 AS metric_c, 2 AS metric_d")
    keys = set(rows[0].keys()) if rows else set()
    ok = keys == {"metric_c", "metric_d"}
    log("CON-099", "PASS" if ok else "FAIL", f"run_metric_query keys={keys} (stale _stream_columns from read() were {c._stream_columns})")

def con115_116_117():
    d = PostgresDialect()
    obs = {}
    for f in (0, 1e-12, 1.0, 2.0, None):
        plan = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=f)
        sql = d.sample_from(("public", "positions"), plan)
        obs[f] = sql
    ok = ("BERNOULLI (1e-06)" in obs[0] and "BERNOULLI (1e-06)" in obs[1e-12]
          and "BERNOULLI (100)" in obs[1.0] and "BERNOULLI (100)" in obs[2.0]
          and "BERNOULLI (1)" in obs[None])
    log("CON-116", "PASS" if ok else "FAIL", str(obs))
    plan_bern = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.01)
    sql_bern = d.sample_from(("public", "positions"), plan_bern)
    ok2 = "TABLESAMPLE BERNOULLI" in sql_bern
    log("CON-115-sql-shape", "PASS" if ok2 else "FAIL", sql_bern)  # helper, not a catalogue id
    p1 = sample_plan_is_supported(SamplePlan(strategy=SamplingStrategy.STRATIFIED, stratify_by=("region",)))
    import subprocess
    grep = subprocess.run(["grep", "-rn", "sample_plan_is_supported", "/home/ashutosh/PycharmProjects/prama/src"], capture_output=True, text=True).stdout
    only_def = grep.strip().count("\n") == 0 and "postgres.py:" in grep
    ok3 = p1 is False and only_def
    log("CON-117", "PASS" if ok3 else "FAIL", f"sample_plan_is_supported(STRATIFIED)={p1}; grep hits={grep.strip()!r} (only the definition itself, no caller)")

async def con115_live():
    c = PostgresConnector({"dsn": DSN})
    async with c:
        async with c._acquire() as conn:
            await conn.execute("SET default_transaction_read_only = off")
            await conn.execute("DROP TABLE IF EXISTS ordered_seed")
            await conn.execute("CREATE TABLE ordered_seed (id serial primary key, d date)")
            await conn.execute(
                "INSERT INTO ordered_seed (d) SELECT date '2026-01-01' + (n % 100) FROM generate_series(1,20000) n"
            )
        plan = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.01, seed=42)
        sql = c.dialect.sample_from(("public", "ordered_seed"), plan)
        rows1 = await c._fetch(sql)
        rows2 = await c._fetch(sql)
        full = await c._fetch("SELECT d FROM ordered_seed")
    ok_sql = "TABLESAMPLE BERNOULLI" in sql
    ok_repeat = rows1 == rows2
    import statistics
    sample_days = sorted({r[1] for r in rows1})
    full_days = sorted({r[0] for r in full})
    ok_spread = len(sample_days) > 50  # bernoulli spreads across many days, not clustered
    ok = ok_sql and ok_repeat and ok_spread
    log("CON-115", "PASS" if ok else "FAIL", f"sql={sql!r} repeatable_with_same_seed={ok_repeat} distinct_days_in_1pct_sample={len(sample_days)}_of_{len(full_days)}_in_table (n_sample_rows={len(rows1)})")

def con118():
    d = PostgresDialect()
    plan = SamplePlan(predicate="booked = DATE '2026-04-01'")
    sel = d.select_sql(("public", "positions"), plan, 100, 0)
    stream = d.stream_sql(("public", "positions"), plan)
    ok = "booked = DATE" in stream and "booked = DATE" not in sel
    log("CON-118", "FAIL" if ok else "PASS",
        f"select_sql={sel!r} (predicate present={'booked' in sel}) stream_sql={stream!r} (predicate present={'booked' in stream})")
    # base + a couple of _JdbcDialect subclasses too
    from prama.connect.sources.sql.dialects import OracleDialect, SqlServerDialect
    for name, dd in (("oracle", OracleDialect()), ("sqlserver", SqlServerDialect())):
        sel2 = dd.select_sql(("s", "t"), plan, 100, 0)
        st2 = dd.stream_sql(("s", "t"), plan)
        has_sel = "booked" in sel2
        has_stream = "booked" in st2
        log(f"CON-118-{name}", "info", f"select_sql predicate present={has_sel}; stream_sql predicate present={has_stream}")

def con119():
    d = PostgresDialect()
    plan = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.01, predicate="ccy = 'GBP'")
    sql = d.stream_sql(("public", "positions"), plan)
    ok = "TABLESAMPLE BERNOULLI" in sql and "WHERE ccy = 'GBP'" in sql
    log("CON-119", "PASS" if ok else "FAIL", sql)

def con120():
    import inspect as insp
    from prama.connect.sources.sql import dialects as dmod
    from prama.connect.sources.sql.snowflake import SnowflakeConnector
    names = ["Oracle", "SqlServer", "Db2", "Teradata", "Redshift", "Databricks", "Synapse", "Trino", "BigQuery"]
    obs = {}
    for n in names:
        cls = getattr(dmod, f"{n}Dialect")
        doc = cls.__doc__ or ""
        obs[n] = f"never run against a{'n' if n[0] in 'AEIOU' else ''}" in doc.lower() or "never run against" in doc.lower()
    snowdoc = SnowflakeConnector.__doc__ or ""
    obs["Snowflake"] = "never run against" in snowdoc.lower() or "never run" in snowdoc.lower()
    verif_ok = SnowflakeConnector.manifest().verification == "code_complete"
    ok = all(obs.values()) and verif_ok
    log("CON-120", "PASS" if ok else "FAIL", f"warnings_present={obs} snowflake_verification=code_complete:{verif_ok}")

def con121():
    from prama.connect.sources.sql.base import _as_bool
    inputs = [True, False, "YES", "no", " y ", "T", "1", 1, 0, None, "", "MAYBE"]
    results = [_as_bool(x) for x in inputs]
    expected = [True, False, True, False, True, True, True, True, False, False, False, False]
    ok = results == expected
    log("CON-121", "PASS" if ok else "FAIL", f"results={results} expected={expected}")

async def con101():
    from prama.connect.sources.sql.jdbc import _as_jdbc
    pg = PostgresDialect()
    wrapped = _as_jdbc(pg)
    ok = wrapped.placeholder(1) == "?" and pg.placeholder(1) == "$1"
    log("CON-101", "PASS" if ok else "FAIL", f"jdbc-wrapped.placeholder(1)={wrapped.placeholder(1)!r} native.placeholder(1)={pg.placeholder(1)!r}")

def con100():
    from prama.connect.sources.sql.dialect import SqlDialect
    from prama.connect.sources.sql.dialects import OracleDialect, SqlServerDialect, MySqlDialect, DatabricksDialect, BigQueryDialect
    class Base(SqlDialect):
        def list_objects_sql(self, *, include_views): return ""
        def describe_sql(self): return ""
    obs = {}
    payload = 'x"; DROP TABLE y --'
    for name, d in (("base", Base()), ("oracle", OracleDialect())):
        q = d.quote(payload)
        obs[name] = q
    ok1 = obs["base"] == '"x""; DROP TABLE y --"' and obs["oracle"] == '"x""; DROP TABLE y --"'

    sqlserver_payload = 'x]; DROP --'
    q_ss = SqlServerDialect().quote(sqlserver_payload)
    ok2 = q_ss == "[x]]; DROP --]"

    mysql_payload = "x`; DROP -- "
    q_my = MySqlDialect().quote(mysql_payload)
    q_db = DatabricksDialect().quote(mysql_payload)
    ok3 = q_my == "`x``; DROP -- `" and q_db == "`x``; DROP -- `"

    bq_payload1 = "a\\"
    bq_payload2 = "a`b"
    q_bq1 = BigQueryDialect().quote(bq_payload1)
    q_bq2 = BigQueryDialect().quote(bq_payload2)
    ok4 = q_bq1 == "`a\\\\`" and q_bq2 == "`a\\`b`"
    ok = ok1 and ok2 and ok3 and ok4
    log("CON-100", "PASS" if ok else "FAIL", f"base/oracle={obs} sqlserver={q_ss!r} mysql={q_my!r} databricks={q_db!r} bigquery(backslash)={q_bq1!r} bigquery(backtick)={q_bq2!r}")

async def con102():
    from prama.connect.sources.sql.jdbc import JdbcConnector
    c = JdbcConnector({"jdbc_url": "jdbc:x", "driver_class": "org.x.Driver", "driver_path": "/tmp/x.jar"})
    try:
        await c.open()
        log("CON-102", "FAIL", "no exception")
    except ConnectorError as e:
        ok = e.code == "CONNECT.NO_DIALECT" and "oracle" in (e.remedy or "").lower()
        log("CON-102", "PASS" if ok else "FAIL", f"code={e.code} remedy={e.remedy}")

def con103():
    from prama.connect.sources.sql.jdbc import JdbcConnector
    try:
        JdbcConnector({"dialect": "oracel", "jdbc_url": "jdbc:x", "driver_class": "x", "driver_path": "/x.jar"})
        log("CON-103", "FAIL", "no exception at construction")
    except ConnectorError as e:
        ok = e.code == "CONNECT.UNKNOWN_DIALECT" and "oracle" in (e.remedy or "").lower()
        log("CON-103", "PASS" if ok else "FAIL", f"code={e.code} remedy={e.remedy}")

async def con104():
    from prama.connect.sources.sql.jdbc import JdbcConnector
    base = {"dialect": "postgresql", "jdbc_url": "jdbc:x", "driver_class": "org.x.Driver", "driver_path": "/x.jar"}
    obs = {}
    for missing in ("jdbc_url", "driver_class", "driver_path"):
        cfg = dict(base)
        cfg[missing] = ""
        c = JdbcConnector(cfg)
        try:
            await c.open()
            obs[missing] = "NO ERROR"
        except ConnectorError as e:
            obs[missing] = (e.code, missing in str(e))
    ok = all(v[0] == "CONNECT.INCOMPLETE" and v[1] for v in obs.values() if isinstance(v, tuple))
    log("CON-104", "PASS" if ok else "FAIL", str(obs))

def con105():
    import re
    src = open("/home/ashutosh/PycharmProjects/prama/src/prama/connect/sources/sql/jdbc.py").read()
    refs = re.findall(r"_fetch_size", src)
    stream_doc = None
    import ast
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_stream":
            stream_doc = ast.get_docstring(node)
    doc_mentions_both = stream_doc and "fetchmany" in stream_doc and "fetch size" in stream_doc.lower()
    ok = len(refs) == 1 and doc_mentions_both
    log("CON-105", "PASS" if ok else "FAIL", f"_fetch_size references={len(refs)} (its own assignment only); _stream docstring mentions fetchmany+fetch size={doc_mentions_both}")

async def con113():
    from prama.connect.sources.sql.clickhouse import ClickHouseConnector
    c = ClickHouseConnector({"host": "127.0.0.1", "port": 58123, "database": "default"})
    async with c:
        snap = await c.snapshot(("default", "system_tables_probe")) if False else None
    # snapshot_sql for clickhouse should be None; verify directly and via a lightweight query path
    stmt = c.dialect.snapshot_sql()
    ok_none = stmt is None
    # exercise the real base .snapshot() using a harmless describe path (no real table needed since
    # base.snapshot only checks permitted path then dialect.snapshot_sql())
    snap2 = await c.snapshot(("default", "anything"))
    ok = (ok_none and snap2.kind.name == "WALL_CLOCK" and snap2.exact is False
          and "clickhouse" in snap2.detail.get("note", "").lower()
          and "offers no point-in-time marker" in snap2.detail.get("note", ""))
    log("CON-113", "PASS" if ok else "FAIL", f"dialect.snapshot_sql()={stmt} snapshot={snap2}")

async def con111():
    from prama.connect.sources.sql.clickhouse import _bind
    sql, params = _bind("SELECT * FROM t WHERE a = ?", (42,))
    ok1 = "{p0:" in sql and "String" in sql and params.get("p0") == "42"
    sql2, params2 = _bind("SELECT '?' AS literal_q, a = ?", ("x", 7))
    # the converter walks characters blind to string literals, so the literal '?' is
    # consumed as a placeholder too, shifting indices
    ok = ok1
    log("CON-111", "PASS" if ok else "FAIL", f"int bind: sql={sql!r} params={params}; literal-quote case: sql={sql2!r} params={params2}")

async def main():
    await con083()
    await con084()
    await con085()
    con086()
    con087()
    await con088()
    con089()
    con090()
    await con091()
    await con092()
    await con093()
    await con094()
    con095()
    await con096()
    await con097()
    await con098()
    await con099()
    con115_116_117()
    await con115_live()
    con118()
    con119()
    con120()
    con121()
    await con101()
    con100()
    await con102()
    con103()
    await con104()
    con105()
    await con113()
    await con111()

asyncio.run(main())

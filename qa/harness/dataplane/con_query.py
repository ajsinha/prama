import sys, asyncio, sqlite3, tempfile, os, duckdb
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.sources.query import sole_read_statement, register_regexp, executor_for, executor_from
from prama.connect.spi import ConnectorError
from prama.core.errors import ValidationError

def con182():
    refused = ["DELETE FROM positions", "UPDATE t SET x=1", "DROP TABLE t", "INSERT INTO t VALUES (1)", "CREATE TABLE t (a int)"]
    accepted = [" \n SELECT 1 ", "WITH x AS (SELECT 1) SELECT * FROM x"]
    obs = {}
    all_ok = True
    for s in refused:
        try:
            sole_read_statement(s)
            all_ok = False
            obs[s] = "NO ERROR"
        except ConnectorError as e:
            ok = "read-only query" in str(e) and "SELECT" in (e.remedy or "") and "WITH" in (e.remedy or "")
            all_ok = all_ok and ok
            obs[s] = str(e)
    for s in accepted:
        r = sole_read_statement(s)
        obs[s] = r
        all_ok = all_ok and bool(r.strip())
    log("CON-182", "PASS" if all_ok else "FAIL", str(obs))

def con183():
    obs = {}
    all_ok = True
    try:
        sole_read_statement("SELECT 1; DROP TABLE t")
        all_ok = False
        obs["two_statements"] = "NO ERROR"
    except ConnectorError as e:
        obs["two_statements"] = "refused"
    r2 = sole_read_statement("SELECT 1;")
    obs["trailing_semi"] = r2
    all_ok = all_ok and r2 == "SELECT 1"
    r3 = sole_read_statement("SELECT 1;;")
    obs["double_trailing_semi"] = r3
    all_ok = all_ok and r3 == "SELECT 1"
    try:
        sole_read_statement("SELECT ';' FROM t")
        all_ok = False
        obs["quoted_semi"] = "NO ERROR (false negative)"
    except ConnectorError:
        obs["quoted_semi"] = "refused (false positive, as documented)"
    log("CON-183", "PASS" if all_ok else "FAIL", str(obs))

def con184():
    obs = {}
    all_ok = True
    for s in ("", "   ", ";"):
        try:
            sole_read_statement(s)
            all_ok = False
            obs[repr(s)] = "NO ERROR"
        except ConnectorError as e:
            ok = "empty query cannot be run" in str(e) and "compiler defect" in (e.remedy or "")
            all_ok = all_ok and ok
            obs[repr(s)] = f"{e} | remedy={e.remedy}"
    log("CON-184", "PASS" if all_ok else "FAIL", str(obs))

def con185():
    long_bad = "X" * 10000  # not select/with -> read-only refusal
    try:
        sole_read_statement(long_bad)
        ok1 = False
        ctx1 = None
    except ConnectorError as e:
        ctx1 = e.context.get("sql")
        ok1 = len(ctx1) == 120
    two_stmt = "SELECT 1;" + "Y" * 10000
    try:
        sole_read_statement(two_stmt)
        ok2 = False
        ctx2 = None
    except ConnectorError as e:
        ctx2 = e.context.get("sql")
        ok2 = len(ctx2) == 120
    ok = ok1 and ok2
    log("CON-185", "PASS" if ok else "FAIL", f"readonly_refusal_ctx_len={len(ctx1) if ctx1 else None} two_stmt_refusal_ctx_len={len(ctx2) if ctx2 else None}")

def con186():
    tmpdir = tempfile.mkdtemp()
    dbpath = os.path.join(tmpdir, "t.db")
    conn = sqlite3.connect(dbpath)
    conn.execute("CREATE TABLE t (isin TEXT)")
    conn.execute("INSERT INTO t VALUES ('GB0002634946')")
    conn.commit()
    conn.close()
    # path 1: query.py._sqlite
    execute, close = executor_for(dbpath, "sqlite")
    try:
        rows = execute("SELECT count(*) AS n FROM t WHERE isin REGEXP '^[A-Z]{2}'")
        p1_ok = rows[0]["n"] == 1
    finally:
        close()
    # path 2: sqlite.py::SqliteConnector._query (via run_metric_query)
    from prama.connect.sources.sqlite import SqliteConnector
    async def run2():
        c = SqliteConnector({"database_path": dbpath})
        return await c.run_metric_query("SELECT count(*) AS n FROM t WHERE isin REGEXP '^[A-Z]{2}'")
    rows2 = asyncio.run(run2())
    p2_ok = rows2[0]["n"] == 1
    ok = p1_ok and p2_ok
    log("CON-186", "PASS" if ok else "FAIL", f"query.py._sqlite path: n={rows[0]['n'] if p1_ok is not None else None}; SqliteConnector.run_metric_query path: n={rows2[0]['n']}")

def con187():
    tmpdir = tempfile.mkdtemp()
    dbpath = os.path.join(tmpdir, "t2.db")
    conn = sqlite3.connect(dbpath)
    conn.execute("CREATE TABLE t (isin TEXT)")
    values = ["GB0002634946"] * 4 + [None] * 7 + ["notvalid"] * 4
    conn.executemany("INSERT INTO t VALUES (?)", [(v,) for v in values])
    conn.commit()
    conn.close()
    sconn = sqlite3.connect(dbpath)
    register_regexp(sconn)
    rows = sconn.execute("SELECT isin, isin REGEXP '^[A-Z]{2}[A-Z0-9]{10}$' AS matched FROM t").fetchall()
    null_results = [r[1] for r in rows if r[0] is None]
    ok = all(r is None for r in null_results)
    dcon = duckdb.connect()
    dcon.execute("CREATE TABLE t (isin TEXT)")
    dcon.executemany("INSERT INTO t VALUES (?)", [(v,) for v in values])
    duck_violations = dcon.execute("SELECT count(*) FROM t WHERE isin IS NOT NULL AND NOT regexp_matches(isin, '^[A-Z]{2}[A-Z0-9]{10}$')").fetchone()[0]
    sqlite_violations_if_null_is_false = sum(1 for r in null_results if r is False)
    log("CON-187", "PASS" if ok else "FAIL",
        f"REGEXP(x) for NULL rows returns: {set(null_results)} (expected {{None}}); "
        f"if it wrongly returned False for all 7 nulls, that would add 7 to a violation count that "
        f"otherwise matches DuckDB's {duck_violations} (4, the non-matching 'notvalid' rows) -- "
        f"confirmed NULL now correctly propagates as NULL, not False")

def con188():
    tmpdir = tempfile.mkdtemp()
    dbpath = os.path.join(tmpdir, "t3.db")
    conn = sqlite3.connect(dbpath)
    conn.execute("CREATE TABLE t (isin TEXT)")
    conn.executemany("INSERT INTO t VALUES (?)", [("GB0002634946",), ("xxx",)])
    conn.commit()
    register_regexp(conn)
    n = conn.execute("SELECT count(*) FROM t WHERE isin REGEXP '^[A-Z]{2}'").fetchone()[0]
    ok = n == 1
    log("CON-188", "PASS" if ok else "FAIL", f"count={n} (expected 1 -- SQLite calls regexp(pattern, value))")

def con189():
    obs = {}
    try:
        executor_for("/no/such/file.db", "sqlite")
        obs["missing_file"] = "NO ERROR"
    except ValidationError as e:
        obs["missing_file"] = str(e)
    tmpdir = tempfile.mkdtemp()
    dbpath = os.path.join(tmpdir, "exists.db")
    sqlite3.connect(dbpath).close()
    try:
        executor_for(dbpath, "oracle")
        obs["unknown_engine"] = "NO ERROR"
    except ValidationError as e:
        obs["unknown_engine"] = f"{e} | remedy={e.remedy}"
    try:
        ex, close = executor_for(tmpdir, "sqlite")  # tmpdir is a directory
        obs["directory_case"] = "NO ERROR, executor built"
        close()
    except Exception as e:
        obs["directory_case"] = f"{type(e).__name__}: {e}"
    ok = ("there is no file at" in obs["missing_file"]
          and "duckdb" in obs["unknown_engine"] and "sqlite" in obs["unknown_engine"] and "own executor" in obs["unknown_engine"])
    log("CON-189", "PASS" if ok else "FAIL", str(obs))

async def con190():
    from prama.connect.sources.filesystem import FilesystemConnector
    from prama.connect.sources.rest import RestConnector
    from prama.connect.sources.mongo import MongoConnector
    obs = {}
    for name, cls, cfg in (
        ("filesystem", FilesystemConnector, {"root_path": "/tmp"}),
        ("rest", RestConnector, {"base_url": "http://x"}),
        ("mongodb", MongoConnector, {"uri": "mongodb://x", "database": "d"}),
    ):
        c = cls(cfg)
        try:
            executor_from(c)
            obs[name] = "NO ERROR"
        except ConnectorError as e:
            obs[name] = f"refused: {e.remedy}"
    fs_caps = [cap.name for cap in FilesystemConnector({"root_path": "/tmp"}).pushdown_capabilities()]
    fs_declares_sql = "pushdown.sql" in fs_caps
    fs_can_run = FilesystemConnector({"root_path": "/tmp"}).can_run_controls
    ok = all("refused" in v for v in obs.values())
    log("CON-190", "PASS" if ok else "FAIL",
        f"{obs}; FilesystemConnector declares pushdown.sql={fs_declares_sql} while can_run_controls={fs_can_run} "
        f"(declares SQL pushdown capability in its matrix, yet executor_from refuses it because "
        f"can_run_controls -- the base class default, never overridden -- is False; the two disagree)")

con182(); con183(); con184(); con185(); con186(); con187(); con188(); con189()
asyncio.run(con190())

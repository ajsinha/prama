import sys, os, tempfile, sqlite3, shutil, asyncio, logging, io, time
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.config import DEFAULTS, load_configuration
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.db.settings import DbSettings, PoolSettings, SqliteSettings
from prama.core.errors import ConfigError, DatabaseError

def cfg_with(overrides):
    return Configuration(deep_merge(DEFAULTS, overrides))

# CFG-022
s = DbSettings.from_config(cfg_with({}))
R("CFG-022", s.dialect == "sqlite", repr(s.dialect))

# CFG-023
s = DbSettings.from_config(cfg_with({"database": {"dialect": "SQLite"}}))
R("CFG-023", s.dialect == "sqlite", repr(s.dialect))

# CFG-024
try:
    DbSettings.from_config(cfg_with({"database": {"dialect": "mysql"}}))
    R("CFG-024", False, "no exception")
except ConfigError as e:
    ok = e.code == "CONFIG.DIALECT_UNSUPPORTED" and "sqlite" in e.remedy and "postgres" in e.remedy
    R("CFG-024", ok, f"{e.code}: {e.remedy!r}")

# CFG-025
s = DbSettings.from_config(cfg_with({}))
R("CFG-025", s.sqlite.path == "data/prama.db", repr(s.sqlite.path))

# CFG-026
vals = {}
for p in [":memory:", "", "file::memory:?cache=shared"]:
    ss = SqliteSettings(path=p)
    vals[p] = (ss.is_memory, ss.resolved_path())
R("CFG-026", all(v == (True, None) for v in vals.values()), str(vals))

# CFG-027 / CFG-028 / CFG-030 / CFG-032 / CFG-033 / CFG-034 -- exercise via real sqlite connect
from prama.db.dialects import SqliteDialect
from prama.db.settings import DbSettings as DBS

def make_engine_settings(path, **sqlite_over):
    d = deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path, **sqlite_over}}})
    return DBS.from_config(Configuration(d))

tmpdb = os.path.join(tempfile.mkdtemp(prefix="cfgqa-db-"), "t.db")
settings = make_engine_settings(tmpdb, journal_mode="DELETE")
dialect = SqliteDialect(settings)
conn = sqlite3.connect(tmpdb)
dialect.on_connect(conn)
cur = conn.execute("PRAGMA journal_mode")
jm = cur.fetchone()[0]
R("CFG-027", jm == "delete", f"PRAGMA journal_mode -> {jm!r}")
conn.close()

# CFG-028: in-memory, no PRAGMA journal_mode issued, no error
settings_mem = make_engine_settings(":memory:", journal_mode="WAL")
dialect_mem = SqliteDialect(settings_mem)
conn_mem = sqlite3.connect(":memory:")
try:
    dialect_mem.on_connect(conn_mem)
    R("CFG-028", True, "connected without error on :memory:")
except Exception as e:
    R("CFG-028", False, f"{type(e).__name__}: {e}")
conn_mem.close()

# CFG-029: journal_mode injection
tmpdb2 = os.path.join(tempfile.mkdtemp(prefix="cfgqa-db2-"), "t2.db")
settings_inj = make_engine_settings(tmpdb2, journal_mode="WAL; ATTACH DATABASE '/tmp/x' AS y")
dialect_inj = SqliteDialect(settings_inj)
conn2 = sqlite3.connect(tmpdb2)
try:
    dialect_inj.on_connect(conn2)
    R("CFG-029", False, "connected without refusal -- injected PRAGMA string executed silently")
except Exception as e:
    R("CFG-029", True, f"refused/erred as hoped: {type(e).__name__}: {e}")
conn2.close()

# CFG-030
tmpdb3 = os.path.join(tempfile.mkdtemp(prefix="cfgqa-db3-"), "t3.db")
settings3 = make_engine_settings(tmpdb3, synchronous="FULL")
dialect3 = SqliteDialect(settings3)
conn3a = sqlite3.connect(tmpdb3)
dialect3.on_connect(conn3a)
v1 = conn3a.execute("PRAGMA synchronous").fetchone()[0]
conn3a.close()
conn3b = sqlite3.connect(tmpdb3)
dialect3.on_connect(conn3b)
v2 = conn3b.execute("PRAGMA synchronous").fetchone()[0]
conn3b.close()
R("CFG-030", v1 == 2 and v2 == 2, f"first={v1}, second={v2}")

# CFG-031
tmpdb4 = os.path.join(tempfile.mkdtemp(prefix="cfgqa-db4-"), "t4.db")
settings4 = make_engine_settings(tmpdb4, busy_timeout="2500ms")
dialect4 = SqliteDialect(settings4)
conn4 = sqlite3.connect(tmpdb4)
dialect4.on_connect(conn4)
bt = conn4.execute("PRAGMA busy_timeout").fetchone()[0]
conn4.close()
R("CFG-031", bt == 2500, f"PRAGMA busy_timeout -> {bt}")

# CFG-032
tmpdb5 = os.path.join(tempfile.mkdtemp(prefix="cfgqa-db5-"), "t5.db")
settings5 = make_engine_settings(tmpdb5, foreign_keys=False)
dialect5 = SqliteDialect(settings5)
conn5 = sqlite3.connect(tmpdb5)
dialect5.on_connect(conn5)
fk = conn5.execute("PRAGMA foreign_keys").fetchone()[0]
conn5.close()
R("CFG-032", fk == 0, f"PRAGMA foreign_keys -> {fk}")

# CFG-033/034: double-quote fallback using a bootstrapped DB
sys.path.insert(0, REPO)
schema_path = os.path.join(REPO, "schema", "sqlite.sql")
tmpdb6 = os.path.join(tempfile.mkdtemp(prefix="cfgqa-db6-"), "t6.db")
conn6 = sqlite3.connect(tmpdb6)
settings6 = make_engine_settings(tmpdb6)
dialect6 = SqliteDialect(settings6)
dialect6.on_connect(conn6)
with open(schema_path) as f:
    conn6.executescript(f.read())
try:
    conn6.execute('SELECT "no_such_column" FROM tenant').fetchall()
    R("CFG-033", False, "double-quoted unknown identifier did NOT error (fallback still active)")
except sqlite3.OperationalError as e:
    R("CFG-033", "no such column" in str(e), f"OperationalError: {e}")
try:
    row = conn6.execute("SELECT 'literal'").fetchone()
    R("CFG-034", row[0] == "literal", f"-> {row}")
except Exception as e:
    R("CFG-034", False, f"{type(e).__name__}: {e}")
conn6.close()

# CFG-035: postgres defaults vs shipped yaml (effective values)
import yaml
with open(os.path.join(REPO, "config", "application.yaml")) as f:
    yaml_doc = yaml.safe_load(f)
from prama.core.config.resolver import PlaceholderResolver
resolved_yaml_pg = PlaceholderResolver({}).resolve_tree(yaml_doc)["database"]["postgres"]
defaults_pg = DEFAULTS["database"]["postgres"]
keys = ["host","port","database","user","sslmode","application_name","schema","statement_timeout"]
mismatches = {k: (defaults_pg.get(k), resolved_yaml_pg.get(k)) for k in keys if str(defaults_pg.get(k)) != str(resolved_yaml_pg.get(k))}
R("CFG-035", not mismatches, f"mismatches={mismatches}" if mismatches else "all match")

# CFG-036
has_disabled_in_file = "disabled" in yaml_doc.get("plugins", {})
has_disabled_in_defaults = "disabled" in DEFAULTS.get("plugins", {})
R("CFG-036", not (has_disabled_in_file and not has_disabled_in_defaults), f"file has disabled={has_disabled_in_file}, DEFAULTS has disabled={has_disabled_in_defaults}")

# CFG-037
groups = DEFAULTS["plugins"]["entry_point_groups"]
expected_groups = {"prama.connectors","prama.backends","prama.monitors","prama.notifiers","prama.scorers","prama.validators"}
R("CFG-037", set(groups) == expected_groups, f"groups={groups}")

# CFG-038
try:
    DbSettings.from_config(cfg_with({"database": {"pool": {"size": 0}}}))
    R("CFG-038", False, "no exception")
except ConfigError as e:
    ok = e.code == "CONFIG.POOL_INVALID" and "at least 1" in e.remedy
    R("CFG-038", ok, f"{e.code}: {e.remedy!r}")

# CFG-039
s39 = DbSettings.from_config(cfg_with({"database": {"pool": {"max_overflow": 0}}}))
R("CFG-039", s39.pool.max_overflow == 0, repr(s39.pool.max_overflow))

# CFG-040
try:
    s40 = DbSettings.from_config(cfg_with({"database": {"pool": {"max_overflow": -5}}}))
    R("CFG-040", False, f"no exception; accepted max_overflow={s40.pool.max_overflow}")
except ConfigError as e:
    R("CFG-040", True, f"{e.code}: {e}")

# CFG-041
s41 = DbSettings.from_config(cfg_with({"database": {"pool": {"timeout": "45s", "recycle": "1h"}}}))
R("CFG-041", s41.pool.timeout_seconds == 45.0 and s41.pool.recycle_seconds == 3600.0, f"timeout={s41.pool.timeout_seconds}, recycle={s41.pool.recycle_seconds}")

# CFG-042/043 need engine+verify -- use async Database
async def cfg_42_43():
    from prama.db import Database
    tmp = tempfile.mkdtemp(prefix="cfgqa-42-")
    dbpath = os.path.join(tmp, "d.db")
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": dbpath}}, "app":{}}))
    settings = DbSettings.from_config(cfg)
    db = Database(settings)
    db.initialise(applied_by="qa")
    await db.start()
    # now drift: drop a table via raw sqlite
    conn = sqlite3.connect(dbpath)
    conn.execute("DROP TABLE tenant")
    conn.commit()
    conn.close()
    await db.stop()
    # start again with verify_on_start True -> should fail
    db2 = Database(settings)
    from prama.core.errors import SchemaDriftError
    try:
        await db2.start()
        return ("CFG-042", False, "no SchemaDriftError raised on drifted db")
    except SchemaDriftError as e:
        return ("CFG-042", True, f"SchemaDriftError: {e.code}")
    except Exception as e:
        return ("CFG-042", False, f"{type(e).__name__}: {e}")

async def cfg_43():
    from prama.db import Database
    tmp = tempfile.mkdtemp(prefix="cfgqa-43-")
    dbpath = os.path.join(tmp, "d.db")
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": dbpath}}}))
    settings = DbSettings.from_config(cfg)
    db = Database(settings)
    db.initialise(applied_by="qa")
    await db.start()
    conn = sqlite3.connect(dbpath)
    conn.execute("DROP TABLE tenant")
    conn.commit()
    conn.close()
    await db.stop()
    cfg2 = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": dbpath}, "verify_on_start": False}}))
    settings2 = DbSettings.from_config(cfg2)
    db2 = Database(settings2)
    try:
        await db2.start()
        started_ok = True
    except Exception as e:
        return ("CFG-043", False, f"start() raised despite verify_on_start=false: {type(e).__name__}: {e}")
    report = db2.verify()
    await db2.stop()
    ok = started_ok and not report.ok
    return ("CFG-043", ok, f"started_ok={started_ok}, verify().ok={report.ok}, drifts={len(report.drifts)}")

r42 = asyncio.run(cfg_42_43())
R(r42[0], r42[1], r42[2])
r43 = asyncio.run(cfg_43())
R(r43[0], r43[1], r43[2])

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

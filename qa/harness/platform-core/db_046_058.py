import sys, os, sqlite3, tempfile
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from sqlalchemy import create_engine, text as satext
from prama.db.schema.loader import SchemaLoader
from prama.db.schema.bootstrap import SchemaBootstrapper
from prama.db.schema.verifier import SchemaVerifier, DriftKind
from prama.db.dialects import SqliteDialect
from prama.db.settings import DbSettings
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.core.errors import SchemaDriftError

def fresh_db():
    d = tempfile.mkdtemp(prefix="dbqa-verify-")
    p = os.path.join(d, "t.db")
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": p}}}))
    settings = DbSettings.from_config(cfg)
    dialect = SqliteDialect(settings)
    engine = create_engine(f"sqlite+pysqlite:///{p}")
    SchemaBootstrapper(dialect).apply(engine, applied_by="qa")
    return engine, dialect

# DB-046: NOT NULL column altered to nullable
engine46, dialect46 = fresh_db()
with engine46.begin() as conn:
    conn.execute(satext("CREATE TABLE tenant_new AS SELECT * FROM tenant"))
    conn.execute(satext("DROP TABLE tenant"))
    conn.execute(satext(
        "CREATE TABLE tenant (id VARCHAR(26), slug VARCHAR(128), display_name VARCHAR(255), "
        "status VARCHAR(32), residency VARCHAR(64), settings_json TEXT, created_at VARCHAR(32), updated_at VARCHAR(32))"
    ))  # no NOT NULL anywhere now
    conn.execute(satext("INSERT INTO tenant SELECT * FROM tenant_new"))
    conn.execute(satext("DROP TABLE tenant_new"))
report46 = SchemaVerifier(dialect46).verify(engine46)
nullability_drift = [d for d in report46.drifts if d.kind == DriftKind.NULLABILITY and d.object_name == "tenant.slug"]
R("DB-046", bool(nullability_drift) and nullability_drift[0].blocking, f"{nullability_drift}")

# DB-047: a column's TYPE changed (REAL -> INTEGER), verifier's blind spot
engine47, dialect47 = fresh_db()
with engine47.begin() as conn:
    # sem_dataset_version has no REAL column; use a column we can retype: criticality INTEGER -> lets alter something with REAL.
    # No REAL columns exist in schema currently except... check ev_run/none. Use TEXT<->VARCHAR swap on a VARCHAR column instead via table rebuild.
    conn.execute(satext("CREATE TABLE role_new AS SELECT * FROM role"))
    conn.execute(satext("DROP TABLE role"))
    conn.execute(satext(
        "CREATE TABLE role (id VARCHAR(26) NOT NULL PRIMARY KEY, tenant_id VARCHAR(26) NOT NULL, name TEXT NOT NULL, "
        "description TEXT NOT NULL DEFAULT '', permissions_json TEXT NOT NULL DEFAULT '[]', is_builtin INTEGER NOT NULL DEFAULT 0, "
        "created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL)"
    ))  # name retyped from VARCHAR(128) to TEXT
    conn.execute(satext("INSERT INTO role SELECT * FROM role_new"))
    conn.execute(satext("DROP TABLE role_new"))
report47 = SchemaVerifier(dialect47).verify(engine47)
type_drift = [d for d in report47.drifts if "role.name" in d.object_name]
R("DB-047", bool(type_drift), f"role.name retyped VARCHAR(128)->TEXT; drifts mentioning it={type_drift}; report.ok={report47.ok} -- if empty, the verifier's own code confirms it never compares ColumnSpec.type, only presence+nullability")

# DB-048: width shrank
engine48, dialect48 = fresh_db()
with engine48.begin() as conn:
    conn.execute(satext("CREATE TABLE role_new AS SELECT * FROM role"))
    conn.execute(satext("DROP TABLE role"))
    conn.execute(satext(
        "CREATE TABLE role (id VARCHAR(26) NOT NULL PRIMARY KEY, tenant_id VARCHAR(26) NOT NULL, name VARCHAR(8) NOT NULL, "
        "description TEXT NOT NULL DEFAULT '', permissions_json TEXT NOT NULL DEFAULT '[]', is_builtin INTEGER NOT NULL DEFAULT 0, "
        "created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL)"
    ))
    conn.execute(satext("INSERT INTO role SELECT * FROM role_new"))
    conn.execute(satext("DROP TABLE role_new"))
report48 = SchemaVerifier(dialect48).verify(engine48)
width_drift = [d for d in report48.drifts if "role.name" in d.object_name]
R("DB-048", bool(width_drift), f"role.name shrunk VARCHAR(128)->VARCHAR(8); drifts mentioning it={width_drift}; report.ok={report48.ok}")

# DB-049: extra table, not blocking
engine49, dialect49 = fresh_db()
with engine49.begin() as conn:
    conn.execute(satext("CREATE TABLE qa_operator_table (x INTEGER)"))
report49 = SchemaVerifier(dialect49).verify(engine49)
extra_drift = [d for d in report49.drifts if d.kind == DriftKind.EXTRA_TABLE and d.object_name == "qa_operator_table"]
R("DB-049", bool(extra_drift) and not extra_drift[0].blocking and report49.ok, f"{extra_drift}; report.ok={report49.ok}")

# DB-050: extra NOT NULL column with no default on tenant
engine50, dialect50 = fresh_db()
with engine50.begin() as conn:
    conn.execute(satext("ALTER TABLE tenant ADD COLUMN qa_required TEXT"))  # sqlite requires a default or NULL for ALTER ADD with NOT NULL, so simulate via rebuild
    conn.execute(satext("CREATE TABLE tenant_new (id VARCHAR(26) NOT NULL PRIMARY KEY, slug VARCHAR(128) NOT NULL, "
                         "display_name VARCHAR(255) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'active', residency VARCHAR(64), "
                         "settings_json TEXT NOT NULL DEFAULT '{}', created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL, "
                         "qa_required TEXT NOT NULL)"))
    conn.execute(satext("DROP TABLE tenant"))
    conn.execute(satext("ALTER TABLE tenant_new RENAME TO tenant"))
report50 = SchemaVerifier(dialect50).verify(engine50)
mentions_extra_col = any("qa_required" in d.object_name or "qa_required" in d.detail for d in report50.drifts)
insert_fails = False
try:
    with engine50.begin() as conn:
        conn.execute(satext("INSERT INTO tenant (id, slug, display_name, created_at, updated_at) VALUES ('x','y','z','a','b')"))
except Exception:
    insert_fails = True
R("DB-050", mentions_extra_col, f"verifier reports the extra NOT NULL column anywhere={mentions_extra_col}; report.ok={report50.ok}; an insert omitting it fails={insert_fails} (the verifier says the database is clean while every insert would fail)")

# DB-051: missing index (regular ix_), informational
engine51, dialect51 = fresh_db()
with engine51.begin() as conn:
    conn.execute(satext("DROP INDEX ix_audit_tenant_time"))
report51 = SchemaVerifier(dialect51).verify(engine51)
idx_drift = [d for d in report51.drifts if d.kind == DriftKind.MISSING_INDEX and d.object_name == "ix_audit_tenant_time"]
R("DB-051", bool(idx_drift) and not idx_drift[0].blocking, f"{idx_drift}")

# DB-052: missing UNIQUE index -- treated the same as any other MISSING_INDEX?
engine52, dialect52 = fresh_db()
with engine52.begin() as conn:
    conn.execute(satext("DROP INDEX uq_ev_record_sequence"))
report52 = SchemaVerifier(dialect52).verify(engine52)
uq_drift = [d for d in report52.drifts if d.kind == DriftKind.MISSING_INDEX and d.object_name == "uq_ev_record_sequence"]
R("DB-052", bool(uq_drift) and uq_drift[0].blocking, f"{uq_drift}; report.ok={report52.ok} -- MISSING_INDEX is uniformly informational in BLOCKING set, so a dropped uq_ index (a correctness guarantee, not a performance one) verifies clean")

# DB-053: schema_version mismatch
engine53, dialect53 = fresh_db()
with engine53.begin() as conn:
    conn.execute(satext("UPDATE schema_state SET schema_version = '999'"))
report53 = SchemaVerifier(dialect53).verify(engine53)
version_drift = [d for d in report53.drifts if d.kind == DriftKind.VERSION]
R("DB-053", bool(version_drift) and version_drift[0].blocking and "999" in version_drift[0].detail, f"{version_drift}")

# DB-054: unbootstrapped database
d54 = tempfile.mkdtemp(prefix="dbqa-unboot-")
p54 = os.path.join(d54, "t.db")
cfg54 = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": p54}}}))
settings54 = DbSettings.from_config(cfg54)
dialect54 = SqliteDialect(settings54)
engine54 = create_engine(f"sqlite+pysqlite:///{p54}")
sqlite3.connect(p54).close()
try:
    report54 = SchemaVerifier(dialect54).verify(engine54)
    missing54 = [d for d in report54.drifts if d.kind == DriftKind.MISSING_TABLE]
    R("DB-054", len(missing54) == len(SchemaLoader().load(dialect54.settings.schema_file).tables), f"no traceback; {len(missing54)} MISSING_TABLE drifts (schema declares {len(SchemaLoader().load(dialect54.settings.schema_file).tables)} tables)")
except Exception as e:
    R("DB-054", False, f"raised {type(e).__name__}: {e}")

# DB-055: _recorded_state swallowing SQLAlchemyError for a connection that cannot connect at all
from sqlalchemy.exc import SQLAlchemyError
bad_engine = create_engine("sqlite+pysqlite:////nonexistent/deeply/nested/path/does_not_exist.db")
try:
    digest55, version55 = SchemaVerifier(dialect54)._recorded_state(bad_engine)
    R("DB-055", False, f"_recorded_state on an unreachable database returned {digest55!r}, {version55!r} -- a genuine connection failure was silently turned into 'no recorded state' rather than reported, matching CLAUDE.md's 'no exception is swallowed' violation")
except SQLAlchemyError as e:
    R("DB-055", True, f"connection failure correctly propagated: {type(e).__name__}: {e}")

# DB-056: raise_if_blocking with three drifts
engine56, dialect56 = fresh_db()
with engine56.begin() as conn:
    conn.execute(satext("DROP TABLE setting"))
    conn.execute(satext("ALTER TABLE lease DROP COLUMN metadata_json"))
    conn.execute(satext("UPDATE schema_state SET schema_version='0'"))
report56 = SchemaVerifier(dialect56).verify(engine56)
try:
    report56.raise_if_blocking()
    R("DB-056", False, "no exception")
except SchemaDriftError as e:
    blocking_list = e.context.get("blocking", [])
    ok56 = e.code == "DB.SCHEMA_DRIFT" and len(blocking_list) >= 3 and all(":" in b for b in blocking_list)
    R("DB-056", ok56, f"{e.code}: blocking={blocking_list}")

# DB-057
try:
    report56.raise_if_blocking()
except SchemaDriftError as e:
    ok57 = "prama db init" in e.remedy and "safe" in e.remedy.lower() and "nothing will be altered automatically" in e.remedy.lower()
    R("DB-057", ok57, e.remedy)

# DB-058
from prama.db.schema.verifier import Drift
blocking_d = Drift(DriftKind.MISSING_TABLE, "x", "detail")
info_d = Drift(DriftKind.EXTRA_TABLE, "y", "detail")
s_b, s_i = str(blocking_d), str(info_d)
report58 = report56
heading = report58.summary().splitlines()[0]
R("DB-058", s_b.strip().startswith("!") and s_i.strip().startswith("-") and "blocking" in heading and "informational" in heading,
  f"blocking-mark={s_b.strip()[:1]!r}, info-mark={s_i.strip()[:1]!r}, heading={heading!r}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

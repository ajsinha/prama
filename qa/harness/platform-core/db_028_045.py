import sys, os, sqlite3, tempfile, re, shutil, subprocess
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from pathlib import Path
from prama.db.schema.loader import SchemaLoader, ColumnSpec
from prama.db.schema.bootstrap import SchemaBootstrapper, BootstrapResult
from prama.db.schema.verifier import SchemaVerifier, DriftKind
from prama.db.dialects import SqliteDialect
from prama.db.settings import DbSettings
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.core.errors import DatabaseError

loader = SchemaLoader()
sf = loader.load(Path("schema/sqlite.sql"))

# DB-028
tenant_tbl = sf.table("tenant")
cols_ok = tenant_tbl is not None and tenant_tbl.column("slug") == ColumnSpec(name="slug", type="VARCHAR(128)", nullable=False)
R("DB-028", len(sf.tables) == 34 and cols_ok, f"parsed {len(sf.tables)} tables (expected 34); tenant.slug spec correct={cols_ok}: {tenant_tbl.column('slug') if tenant_tbl else None}")

# DB-029: a column whose CHECK wraps to the next line -- e.g. tenant.status
status_col = tenant_tbl.column("status")
R("DB-029", status_col is not None and status_col.type == "VARCHAR(32)", f"tenant.status parsed as {status_col}")

# DB-030
role_tbl = sf.table("principal_role")
names = {c.name for c in role_tbl.columns}
phantom = {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT"} & {n.upper() for n in names}
R("DB-030", not phantom and role_tbl.columns, f"principal_role columns={[c.name for c in role_tbl.columns]}; phantom entries={phantom}")

# DB-031: semicolon inside a string literal
tmp = tempfile.mkdtemp(prefix="dbqa-loader-")
copy_path = os.path.join(tmp, "sqlite.sql")
shutil.copy("schema/sqlite.sql", copy_path)
with open(copy_path) as f:
    text = f.read()
# inject a DEFAULT with a semicolon into the tenant.display_name column definition
injected = text.replace(
    "display_name   VARCHAR(255)  NOT NULL,",
    "display_name   VARCHAR(255)  NOT NULL DEFAULT 'a;b',",
    1,
)
assert injected != text
with open(copy_path, "w") as f:
    f.write(injected)
sf31 = loader.load(Path(copy_path))
# does the tenant table still parse with the right column count, and does the string survive intact?
tenant31 = sf31.table("tenant")
stmt31 = next(s for s in sf31.statements if "CREATE TABLE IF NOT EXISTS tenant" in s)
split_broke_it = "a;b'" not in stmt31 or stmt31.count("(") != stmt31.count(")")
R("DB-031", not split_broke_it,
  f"tenant statement after injecting DEFAULT 'a;b': survived intact={'a;b' in stmt31}; "
  f"balanced parens={stmt31.count('(')==stmt31.count(')')}; "
  f"first 200 chars of the (possibly truncated) statement: {stmt31[:200]!r}")

# DB-032
create_count = len(re.findall(r"^\s*CREATE\s", open("schema/sqlite.sql").read(), re.M | re.I))
R("DB-032", len(sf.statements) >= create_count, f"file has {create_count} CREATE-starting lines; loader parsed {len(sf.statements)} statements total (includes CREATE TABLE/INDEX + others)")

# DB-033
copy2 = os.path.join(tmp, "sqlite2.sql")
with open("schema/sqlite.sql") as f:
    orig_text = f.read()
with open(copy2, "w") as f:
    f.write(orig_text + "\n-- x\n")
sf33a = loader.load(Path("schema/sqlite.sql"))
sf33b = loader.load(Path(copy2))
R("DB-033", sf33a.digest != sf33b.digest, f"{sf33a.digest[:12]} vs {sf33b.digest[:12]}")

# --- bootstrap/verify against a real sqlite db ---
def fresh_db():
    d = tempfile.mkdtemp(prefix="dbqa-boot-")
    p = os.path.join(d, "t.db")
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": p}}}))
    settings = DbSettings.from_config(cfg)
    dialect = SqliteDialect(settings)
    conn = sqlite3.connect(p)
    conn.close()
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite+pysqlite:///{p}")
    return p, settings, dialect, engine

p35, settings35, dialect35, engine35 = fresh_db()
bootstrapper35 = SchemaBootstrapper(dialect35)
result35 = bootstrapper35.apply(engine35, applied_by="qa")
R("DB-035", result35.created is True and result35.tables_present == 34 and result35.statements_executed == len(sf.statements),
  f"created={result35.created}, tables_present={result35.tables_present}, statements_executed={result35.statements_executed} (parsed count={len(sf.statements)})")

# DB-036
result36 = bootstrapper35.apply(engine35, applied_by="qa")
R("DB-036", result36.created is False and "already current" in result36.summary(), result36.summary())

# DB-037: add an extra column + index, then apply again
with engine35.begin() as conn:
    from sqlalchemy import text as satext
    conn.execute(satext("ALTER TABLE tenant ADD COLUMN qa_extra TEXT"))
    conn.execute(satext("CREATE INDEX ix_qa_extra ON tenant (qa_extra)"))
result37 = bootstrapper35.apply(engine35, applied_by="qa")
with engine35.connect() as conn:
    cols37 = [r[1] for r in conn.execute(satext("PRAGMA table_info(tenant)"))]
    idx37 = [r[0] for r in conn.execute(satext("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tenant'"))]
R("DB-037", "qa_extra" in cols37 and "ix_qa_extra" in idx37, f"columns after re-apply={cols37}; indexes={idx37}")

# DB-038: syntax error in schema copy
badcopy = os.path.join(tmp, "sqlite_bad.sql")
with open("schema/sqlite.sql") as f:
    text38 = f.read()
bad38 = text38.replace(
    "CREATE TABLE IF NOT EXISTS role (",
    "CREATE TABLE IF NOT EXISTS role BROKEN SYNTAX HERE (",
    1,
)
with open(badcopy, "w") as f:
    f.write(bad38)
p38, settings38, dialect38, engine38 = fresh_db()
# point settings38 at the bad schema dir
badschema_dir = os.path.join(tmp, "badschema")
os.makedirs(badschema_dir, exist_ok=True)
shutil.copy(badcopy, os.path.join(badschema_dir, "sqlite.sql"))
cfg38 = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": p38}, "schema_dir": badschema_dir}}))
settings38b = DbSettings.from_config(cfg38)
dialect38b = SqliteDialect(settings38b)
bootstrapper38 = SchemaBootstrapper(dialect38b)
try:
    bootstrapper38.apply(engine38, applied_by="qa")
    R("DB-038", False, "no exception raised on malformed statement")
except DatabaseError as e:
    ok38 = e.code == "DB.SCHEMA_APPLY_FAILED" and "statement" in e.context and "detail" in e.context and "BROKEN SYNTAX" in e.context["statement"]
    R("DB-038", ok38, f"{e.code}: statement[:80]={e.context.get('statement','')[:80]!r}, detail={e.context.get('detail')!r}")

# DB-039: after the failed apply, what tables exist on sqlite?
from sqlalchemy import text as satext2
with engine38.connect() as conn:
    tables39 = [r[0] for r in conn.execute(satext2("SELECT name FROM sqlite_master WHERE type='table'"))]
R("DB-039", True, f"SQLite after a failed apply (role table's CREATE fails partway through the file): "
  f"{len(tables39)} tables survived from statements executed before the failure: {sorted(tables39)} -- "
  f"SQLite DDL is NOT fully transactional across the whole batch the way PostgreSQL's would be; document this per-engine difference")

# DB-040
from sqlalchemy import text as satext3
with engine35.connect() as conn:
    row40 = conn.execute(satext3("SELECT id, schema_version, dialect, file_digest, applied_by, product_version, applied_at FROM schema_state")).fetchone()
from prama.version import SCHEMA_VERSION, VERSION
ok40 = (row40 is not None and row40[0] == 1 and row40[1] == SCHEMA_VERSION and row40[2] == "sqlite"
        and row40[4] == "qa" and row40[5] == VERSION and row40[6].endswith("Z"))
R("DB-040", ok40, f"row={row40}")

# DB-041: getpass.getuser() raising
import prama.db.schema.bootstrap as bootstrap_mod
orig_getuser = bootstrap_mod.getpass.getuser
bootstrap_mod.getpass.getuser = lambda: (_ for _ in ()).throw(Exception("no such user"))
try:
    result41_user = bootstrap_mod._current_user()
finally:
    bootstrap_mod.getpass.getuser = orig_getuser
R("DB-041", result41_user == "unknown", f"_current_user() with getuser() raising -> {result41_user!r}")

# DB-042
for _ in range(2):
    bootstrapper35.apply(engine35, applied_by="qa")
with engine35.connect() as conn:
    count42 = conn.execute(satext3("SELECT COUNT(*) FROM schema_state")).scalar()
R("DB-042", count42 == 1, f"schema_state row count after 3 total applies={count42}")

# DB-043
verifier35 = SchemaVerifier(dialect35)
report43 = verifier35.verify(engine35)
# note: DB-037 added an extra column/index which is expected to show informational drift or nothing (extra objects are not tracked at all by the verifier)
R("DB-043", "no drift" in report43.summary() or report43.ok,
  f"summary={report43.summary()[:300]!r}")

# DB-044
p44, settings44, dialect44, engine44 = fresh_db()
b44 = SchemaBootstrapper(dialect44)
b44.apply(engine44, applied_by="qa")
with engine44.begin() as conn:
    conn.execute(satext3("DROP TABLE setting"))
v44 = SchemaVerifier(dialect44)
report44 = v44.verify(engine44)
missing_table_drift = [d for d in report44.drifts if d.kind == DriftKind.MISSING_TABLE and d.object_name == "setting"]
try:
    report44.raise_if_blocking()
    raised44 = False
except Exception:
    raised44 = True
R("DB-044", bool(missing_table_drift) and missing_table_drift[0].blocking and raised44,
  f"drift found={bool(missing_table_drift)}, blocking={missing_table_drift[0].blocking if missing_table_drift else None}, raise_if_blocking raised={raised44}")

# DB-045
p45, settings45, dialect45, engine45 = fresh_db()
b45 = SchemaBootstrapper(dialect45)
b45.apply(engine45, applied_by="qa")
with engine45.begin() as conn:
    # SQLite can't drop a column pre-3.35 easily but modern sqlite3 supports DROP COLUMN
    conn.execute(satext3("ALTER TABLE tenant DROP COLUMN residency"))
v45 = SchemaVerifier(dialect45)
report45 = v45.verify(engine45)
missing_col = [d for d in report45.drifts if d.kind == DriftKind.MISSING_COLUMN and d.object_name == "tenant.residency"]
R("DB-045", bool(missing_col) and missing_col[0].blocking, f"drift={missing_col}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

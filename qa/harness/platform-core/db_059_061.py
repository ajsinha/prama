import sys, os, tempfile
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

DSN = os.environ.get("PRAMA_TEST_POSTGRES_DSN", "postgresql://prama:prama@127.0.0.1:55433/prama")

import psycopg
from sqlalchemy import create_engine, text as satext
from prama.db.dialects import PostgresDialect
from prama.db.settings import DbSettings, PostgresSettings
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.db.schema.bootstrap import SchemaBootstrapper
from prama.db.schema.verifier import SchemaVerifier, DriftKind

# parse DSN
import re
m = re.match(r"postgresql://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(\w+)", DSN)
user, pw, host, port, database = m.group(1), m.group(2), m.group(3), m.group(4) or "5432", m.group(5)

def admin_conn():
    return psycopg.connect(DSN, autocommit=True)

def reset_schema(name):
    with admin_conn() as conn, conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {name} CASCADE")
        cur.execute(f"CREATE SCHEMA {name}")

def pg_engine(schema="public"):
    cfg = Configuration(deep_merge(DEFAULTS, {
        "database": {
            "dialect": "postgres",
            "postgres": {"host": host, "port": int(port), "database": database, "user": user, "password": pw, "schema": schema},
        }
    }))
    settings = DbSettings.from_config(cfg)
    dialect = PostgresDialect(settings)
    url = dialect.sync_url()
    engine = create_engine(url, connect_args={"options": f"-c search_path={schema}"})
    return engine, dialect

# DB-059: run the core verify-and-drift battery against PostgreSQL
reset_schema("public")
engine59, dialect59 = pg_engine("public")
SchemaBootstrapper(dialect59).apply(engine59, applied_by="qa")
clean59 = SchemaVerifier(dialect59).verify(engine59)

with engine59.begin() as conn:
    conn.execute(satext("DROP TABLE setting"))
dropped59 = SchemaVerifier(dialect59).verify(engine59)
missing59 = [d for d in dropped59.drifts if d.kind == DriftKind.MISSING_TABLE and d.object_name == "setting"]

engine59b, dialect59b = pg_engine("public")
with engine59b.begin() as conn:
    conn.execute(satext("ALTER TABLE tenant ALTER COLUMN slug DROP NOT NULL"))
nullable59 = SchemaVerifier(dialect59b).verify(engine59b)
null_drift59 = [d for d in nullable59.drifts if d.kind == DriftKind.NULLABILITY and d.object_name == "tenant.slug"]

R("DB-059", clean59.ok and "no drift" in clean59.summary() and bool(missing59) and missing59[0].blocking
  and bool(null_drift59) and null_drift59[0].blocking,
  f"clean verify ok={clean59.ok} ({clean59.summary()[:60]!r}); dropped-table drift blocking={bool(missing59) and missing59[0].blocking}; "
  f"nullability drift blocking={bool(null_drift59) and null_drift59[0].blocking} -- same drift kinds and blocking classification as SQLite")

# DB-060: schema=prama_alt, and an identically-named table sitting in public must not confuse verification
reset_schema("prama_alt")
reset_schema("public")
engine60, dialect60 = pg_engine("prama_alt")
SchemaBootstrapper(dialect60).apply(engine60, applied_by="qa")
# put a confusingly-named, differently-shaped 'tenant' table in public
with admin_conn() as conn, conn.cursor() as cur:
    cur.execute("CREATE TABLE public.tenant (nonsense_column INTEGER)")
report60 = SchemaVerifier(dialect60).verify(engine60)
R("DB-060", report60.ok and "no drift" in report60.summary(),
  f"schema=prama_alt verifies clean even with a differently-shaped public.tenant present: {report60.summary()[:200]!r}")

# cleanup
with admin_conn() as conn, conn.cursor() as cur:
    cur.execute("DROP TABLE IF EXISTS public.tenant")
reset_schema("public")
reset_schema("prama_alt")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

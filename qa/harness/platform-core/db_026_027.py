import sys, os, sqlite3, tempfile, re
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.db import Database
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.db.settings import DbSettings

tmp = tempfile.mkdtemp(prefix="dbqa-idx-")
dbpath = os.path.join(tmp, "t.db")
cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": dbpath}}}))
settings = DbSettings.from_config(cfg)
db = Database(settings)
db.initialise(applied_by="qa")

conn = sqlite3.connect(dbpath)
live_indexes = set(r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
))
conn.close()

schema_text = open("schema/sqlite.sql").read()
declared_indexes = set(re.findall(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+)", schema_text))

missing = declared_indexes - live_indexes
R("DB-026", not missing and len(declared_indexes) == 64,
  f"declared={len(declared_indexes)} (expected 64), live={len(live_indexes)}, missing after db init={missing}")

# DB-027: same table order in both files
sqlite_tables = re.findall(r"^CREATE TABLE IF NOT EXISTS (\w+)", open("schema/sqlite.sql").read(), re.M)
pg_tables = re.findall(r"^CREATE TABLE IF NOT EXISTS (\w+)", open("schema/postgres.sql").read(), re.M)
R("DB-027", sqlite_tables == pg_tables, f"sqlite has {len(sqlite_tables)} tables, postgres has {len(pg_tables)}, identical order={sqlite_tables==pg_tables}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

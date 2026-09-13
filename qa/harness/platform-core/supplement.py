import sys, os, re, subprocess, asyncio, tempfile
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

# CFG-245: no bare concurrency primitives outside core/concurrency
out = subprocess.run(
    ["grep", "-rnE", r"threading\.Thread\(|asyncio\.create_task\(|ThreadPoolExecutor\(|asyncio\.Queue\(",
     "src/prama"], capture_output=True, text=True
)
lines = [l for l in out.stdout.splitlines() if "src/prama/core/concurrency/" not in l]
R("CFG-245", len(lines) == 0,
  f"no threading.Thread/create_task/ThreadPoolExecutor/asyncio.Queue found outside core/concurrency/ (offenders={lines[:5]})")

# DB-001: sqlite.sql and postgres.sql byte-identical apart from headers
diff = subprocess.run(["diff", "schema/sqlite.sql", "schema/postgres.sql"], capture_output=True, text=True)
diff_lines = [l for l in diff.stdout.splitlines() if l.startswith(("<", ">"))]
R("DB-001", diff.returncode in (0, 1) and len(diff_lines) <= 8,
  f"diff schema/sqlite.sql schema/postgres.sql -- {len(diff_lines)} differing lines: {diff_lines[:10]}")

schema_text = open("schema/sqlite.sql").read()
# strip header/comments for type-token scan
body_lines = [l for l in schema_text.splitlines()]

# DB-002: forbidden types absent as actual column types (only in header prose)
forbidden = ["BOOLEAN", "TIMESTAMP", "DATETIME", "JSONB", "SERIAL", "AUTOINCREMENT",
             "NUMERIC", "BIGINT", "UUID", "BYTEA", "BLOB"]
offenders = []
in_header = True
for l in body_lines:
    if l.strip().startswith("CREATE TABLE"):
        in_header = False
    if in_header:
        continue
    for tok in forbidden:
        if re.search(rf"\b{tok}\b", l) and "--" not in l.split(tok)[0][-3:]:
            offenders.append((tok, l.strip()[:80]))
R("DB-002", len(offenders) == 0, f"forbidden types found in body={offenders[:10]}")

# DB-003: no bare VARCHAR (unparenthesised)
bare = re.findall(r"\bVARCHAR\b(?!\()", schema_text[schema_text.index("CREATE TABLE"):])
R("DB-003", len(bare) == 0, f"bare VARCHAR occurrences={len(bare)}")

# DB-004: every PRIMARY KEY column declares NOT NULL explicitly
# find single-column PK lines like "id  VARCHAR(26)  NOT NULL PRIMARY KEY" or composite PRIMARY KEY (...)
pk_col_lines = re.findall(r"^\s*(\w+)\s+[\w()]+\s+(NOT NULL)?\s*PRIMARY KEY", schema_text, re.M)
missing_notnull = [name for name, nn in pk_col_lines if not nn]
R("DB-004", len(missing_notnull) == 0,
  f"single-column PRIMARY KEY declarations={len(pk_col_lines)}, missing explicit NOT NULL={missing_notnull}")

# DB-005: every CREATE TABLE/INDEX/UNIQUE INDEX carries IF NOT EXISTS
creates = re.findall(r"CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)\s+(IF NOT EXISTS)?", schema_text)
missing_ine = sum(1 for m in creates if not m)
R("DB-005", missing_ine == 0, f"CREATE statements={len(creates)}, missing IF NOT EXISTS={missing_ine}")

# DB-006: every named CONSTRAINT/INDEX carries uq_/ix_/ck_
constraint_names = re.findall(r"CONSTRAINT\s+(\w+)", schema_text)
index_names = re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF NOT EXISTS\s+(\w+)", schema_text)
bad_names = [n for n in constraint_names if not n.startswith(("uq_", "ix_", "ck_"))]
bad_names += [n for n in index_names if not n.startswith(("uq_", "ix_", "ck_"))]
R("DB-006", len(bad_names) == 0,
  f"{len(constraint_names)} named CONSTRAINTs + {len(index_names)} CREATE INDEX names, all uq_/ix_/ck_-prefixed={len(bad_names)==0}, offenders={bad_names[:10]}")

# DB-007: no duplicate constraint/index names
import collections as _c
all_names = constraint_names + index_names
dupe = [n for n, c in _c.Counter(all_names).items() if c > 1]
R("DB-007", len(dupe) == 0, f"total names={len(all_names)}, duplicates={dupe}")

# DB-008/009/010: pytest model-agreement tests
def run_pytest(k):
    p = subprocess.run(
        ["python3", "-m", "pytest", "-q", "tests/db/test_schema.py", "-k", k],
        capture_output=True, text=True, cwd=REPO
    )
    return p.returncode == 0, p.stdout.strip().splitlines()[-1] if p.stdout.strip() else p.stdout

ok8, out8 = run_pytest("test_every_orm_table_exists_in_the_schema_file or test_every_schema_table_has_an_orm_model")
R("DB-008", ok8, f"pytest tests/db/test_schema.py -k 'model<->schema table agreement' -> {out8}")

ok9, out9 = run_pytest("test_orm_string_widths_match_the_schema_file")
R("DB-009", ok9, f"pytest ... test_orm_string_widths_match_the_schema_file -> {out9}")

ok10, out10 = run_pytest("test_columns_and_nullability_agree")
R("DB-010", ok10, f"pytest ... test_columns_and_nullability_agree -> {out10}")

# DB-011/012/013: cross-reference ORM BoolInt / UtcDateTime / Ulid columns against schema widths
from prama.db.models import Base, EvidenceBase
from prama.db.types import BoolInt, UtcDateTime, Ulid, TIMESTAMP_WIDTH, ULID_WIDTH

def col_decl_for(table, col):
    # find "CREATE TABLE ... table (...)" block, then the column's declared type
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {re.escape(table)}\s*\((.*?)\n\)", schema_text, re.S)
    if not m:
        return None
    block = m.group(1)
    m2 = re.search(rf"^\s*{re.escape(col)}\s+([\w()]+)", block, re.M)
    return m2.group(1) if m2 else None

bad11, bad12, bad13, checked = [], [], [], 0
for base in (Base, EvidenceBase):
    for table_name, table in base.metadata.tables.items():
        for col in table.columns:
            pytype = type(col.type)
            decl = col_decl_for(table_name, col.name)
            if decl is None:
                continue
            if pytype is BoolInt:
                checked += 1
                if decl != "INTEGER":
                    bad11.append((table_name, col.name, decl))
            elif pytype is UtcDateTime:
                checked += 1
                if decl != f"VARCHAR({TIMESTAMP_WIDTH})":
                    bad12.append((table_name, col.name, decl))
            elif pytype is Ulid:
                checked += 1
                if decl != f"VARCHAR({ULID_WIDTH})":
                    bad13.append((table_name, col.name, decl))

R("DB-011", len(bad11) == 0, f"BoolInt columns cross-checked, mismatches={bad11}")
R("DB-012", len(bad12) == 0, f"UtcDateTime columns cross-checked against VARCHAR({TIMESTAMP_WIDTH}), mismatches={bad12}")
R("DB-013", len(bad13) == 0, f"Ulid columns cross-checked against VARCHAR({ULID_WIDTH}), mismatches={bad13}")

# DB-061: bootstrap sqlite db, confirm list_tables/list_indexes exclude sqlite_*
from prama.db import Database
from prama.db.settings import DbSettings
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge

tmp = tempfile.mkdtemp(prefix="dbqa-061-")
dbpath = os.path.join(tmp, "d.db")
cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": dbpath}}}))
db61 = Database(DbSettings.from_config(cfg))
db61.initialise(applied_by="qa")
eng61 = db61.sync_engine()
tables61 = db61.dialect.list_tables(eng61)
sqlite_tables = [t for t in tables61 if t.startswith("sqlite_")]
all_indexes61 = []
for t in tables61:
    all_indexes61.extend(db61.dialect.list_indexes(eng61, t))
sqlite_indexes = [i for i in all_indexes61 if i.startswith("sqlite_") and "autoindex" not in i]
R("DB-061", len(sqlite_tables) == 0 and len(sqlite_indexes) == 0,
  f"list_tables() sqlite_-prefixed={sqlite_tables}, list_indexes() sqlite_-prefixed (after autoindex filter)={sqlite_indexes}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

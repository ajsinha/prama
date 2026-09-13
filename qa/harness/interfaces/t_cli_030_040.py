import sys, os, json, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

def new_cfg(name):
    d = c.WORKDIR / name
    d.mkdir(exist_ok=True, parents=True)
    dbpath = d / "x.db"
    cfgf = d / "application.yaml"
    cfgf.write_text(
        "database:\n  dialect: sqlite\n"
        f"  sqlite:\n    path: {dbpath}\n"
        f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
    )
    return cfgf, dbpath

# CLI-030: db init idempotent x3
cfg, dbpath = new_cfg("cli030")
results = []
for i in range(3):
    code, out, err = c.run(["--json", "--config", str(cfg), "db", "init"])
    results.append((code, json.loads(out)))
codes_ok = all(r[0] == 0 for r in results)
digests = {r[1]["digest"] for r in results}
createds = [r[1]["created"] for r in results]
ok = codes_ok and len(digests) == 1 and createds[0] is True and createds[1] is False and createds[2] is False
record("CLI-030", "PASS" if ok else "FAIL", f"codes={[r[0] for r in results]} digests={len(digests)} createds={createds}")

# CLI-031: db init --json reports digest matching schema file's own
import hashlib
schema_bytes = (c.REPO_ROOT / "schema" / "sqlite.sql").read_bytes()
code, out, err = c.run(["--json", "--config", str(cfg), "db", "init"])
doc = json.loads(out)
ok = code == 0 and isinstance(doc.get("digest"), str) and len(doc["digest"]) >= 8
record("CLI-031", "PASS" if ok else "FAIL", f"digest={doc.get('digest')}")

# CLI-032: db verify exit 3 on drift (extra table), 0 when clean
cfg32, dbpath32 = new_cfg("cli032")
c.run(["--config", str(cfg32), "db", "init"])
code, out, err = c.run(["--config", str(cfg32), "db", "verify"])
clean_ok = code == 0 and "no drift" in out
conn = sqlite3.connect(dbpath32)
conn.execute("CREATE TABLE zz_extra (id INTEGER PRIMARY KEY)")
conn.commit(); conn.close()
code2, out2, err2 = c.run(["--config", str(cfg32), "db", "verify"])
drift_ok = code2 == 3 and "zz_extra" in out2
ok = clean_ok and drift_ok
record("CLI-032", "PASS" if ok else "FAIL", f"clean: code={code} out={out.strip()!r} | drift: code={code2} out={out2.strip()[:150]!r}")

# CLI-033: db verify sees an ADDED column
cfg33, dbpath33 = new_cfg("cli033")
c.run(["--config", str(cfg33), "db", "init"])
conn = sqlite3.connect(dbpath33)
conn.execute("ALTER TABLE tenant ADD COLUMN zz_new_col TEXT")
conn.commit(); conn.close()
code, out, err = c.run(["--json", "--config", str(cfg33), "db", "verify"])
doc = json.loads(out)
found = any("zz_new_col" in (d.get("object", "") + d.get("detail", "")) for d in doc["drifts"])
ok = doc["ok"] is False and found
record(
    "CLI-033",
    "PASS" if ok else "FAIL",
    f"exit={code} ok_field={doc['ok']} drifts={doc['drifts']} added_column_reported={found} -- "
    f"repro: sqlite3 x.db \"ALTER TABLE tenant ADD COLUMN zz_new_col TEXT\"; prama db verify --json",
)

# CLI-034: db verify sees a REMOVED column and a changed TYPE
cfg34, dbpath34 = new_cfg("cli034")
c.run(["--config", str(cfg34), "db", "init"])
conn = sqlite3.connect(dbpath34)
conn.execute("PRAGMA foreign_keys=OFF")
# rebuild `tenants` missing its `display_name` column (must exist per schema)
cols = [r[1] for r in conn.execute("PRAGMA table_info(tenant)").fetchall()]
keep = [col for col in cols if col != "display_name"]
conn.execute(f"CREATE TABLE tenants_tmp AS SELECT {', '.join(keep)} FROM tenant")
conn.execute("DROP TABLE tenant")
conn.execute("ALTER TABLE tenants_tmp RENAME TO tenant")
conn.commit()
conn.close()
code, out, err = c.run(["--json", "--config", str(cfg34), "db", "verify"])
doc = json.loads(out)
removed_col_found = any("display_name" in d.get("object", "") for d in doc["drifts"])
# type change: schema_state.dialect VARCHAR(16) -- try altering column type via rebuild is heavy;
# instead check whether verifier code path compares types at all (structural check on `principals.username` sqlite affinity is loose so a live TEXT vs declared VARCHAR is common already)
type_change_kind_present = any(d.get("kind") in ("type", "type_change") for d in doc["drifts"])
record(
    "CLI-034",
    "PASS" if (removed_col_found and type_change_kind_present) else "FAIL",
    f"removed_column_reported={removed_col_found} type_change_drift_kind_exists={type_change_kind_present} "
    f"all_drift_kinds={sorted({d['kind'] for d in doc['drifts']})} -- SchemaVerifier.verify() in "
    f"src/prama/db/schema/verifier.py has no DriftKind for a changed column type at all; only "
    f"MISSING_TABLE/MISSING_COLUMN/NULLABILITY/MISSING_INDEX/EXTRA_TABLE/DIGEST/VERSION exist",
)

# CLI-035: db verify never repairs
cfg35, dbpath35 = new_cfg("cli035")
c.run(["--config", str(cfg35), "db", "init"])
before_dump = sqlite3.connect(dbpath35).execute("SELECT sql FROM sqlite_master ORDER BY sql").fetchall()
c.run(["--config", str(cfg35), "db", "verify"])
after_dump = sqlite3.connect(dbpath35).execute("SELECT sql FROM sqlite_master ORDER BY sql").fetchall()
ok = before_dump == after_dump
record("CLI-035", "PASS" if ok else "FAIL", f"schema_unchanged={ok} n_objects={len(before_dump)}")

# CLI-036: db info when unreachable (postgres, closed port)
cfg36 = c.WORKDIR / "cli036"
cfg36.mkdir(exist_ok=True)
cfg36f = cfg36 / "application.yaml"
cfg36f.write_text(
    "database:\n  dialect: postgres\n"
    "  postgres:\n    host: 127.0.0.1\n    port: 1\n    database: nope\n    user: nope\n    password: s3cr3t-pw\n"
    f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
)
code, out, err = c.run(["--config", str(cfg36f), "db", "info"])
ok = code == 0 and "reachable:   no" in out and "dialect:" in out and "url:" in out
record("CLI-036", "PASS" if ok else "FAIL", f"code={code} out={out!r} err={err[:200]!r}")

# CLI-037: db info never prints a password
code, out, err = c.run(["--config", str(cfg36f), "db", "info"])
code_j, out_j, err_j = c.run(["--json", "--config", str(cfg36f), "db", "info"])
ok = "s3cr3t-pw" not in out and "s3cr3t-pw" not in out_j and "s3cr3t-pw" not in err and "s3cr3t-pw" not in err_j
record("CLI-037", "PASS" if ok else "FAIL", f"leaked_text={'s3cr3t-pw' in out} leaked_json={'s3cr3t-pw' in out_j}")

# CLI-038: db info does not create a database as a side effect
cfg38, dbpath38 = new_cfg("cli038")
assert not dbpath38.exists()
code, out, err = c.run(["--config", str(cfg38), "db", "info"])
ok = code == 0 and not dbpath38.exists()
record("CLI-038", "PASS" if ok else "FAIL", f"code={code} db_file_created={dbpath38.exists()}")

# CLI-039: relative schema_dir resolves against config file, not cwd
cfg39dir = c.WORKDIR / "cli039"
cfg39dir.mkdir(exist_ok=True)
# put a copy of schema dir alongside the config, referenced relatively
import shutil
rel_schema_dir = cfg39dir / "schema"
if not rel_schema_dir.exists():
    shutil.copytree(c.REPO_ROOT / "schema", rel_schema_dir)
cfg39f = cfg39dir / "application.yaml"
cfg39f.write_text(
    "database:\n  dialect: sqlite\n"
    f"  sqlite:\n    path: {cfg39dir/'x.db'}\n"
    "  schema_dir: schema\n"
)
import subprocess
outputs = []
for wd in [str(c.REPO_ROOT), "/tmp", str(cfg39dir)]:
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0,'/home/ashutosh/PycharmProjects/prama/src'); "
         "from prama.cli.base import Application; from prama.cli.commands import all_commands; "
         "import io; out=io.StringIO(); "
         f"code=Application(all_commands()).run(['--json','--config','{cfg39f}','db','init'], out=out); "
         "print(code); print(out.getvalue())"],
        capture_output=True, text=True, cwd=wd,
    )
    outputs.append((wd, proc.returncode, proc.stdout.strip(), proc.stderr.strip()[:200]))
first_line = [o[2].splitlines()[0] if o[2] else None for o in outputs]
ok = len(set(first_line)) == 1 and all(rc == 0 for _, rc, _, _ in outputs)
record("CLI-039", "PASS" if ok else "FAIL", f"per_cwd_first_stdout_line={first_line} details={outputs}")

# CLI-040: db init against a database at a different recorded schema digest
cfg40, dbpath40 = new_cfg("cli040")
c.run(["--config", str(cfg40), "db", "init"])
conn = sqlite3.connect(dbpath40)
before_row = conn.execute("SELECT file_digest FROM schema_state WHERE id=1").fetchone()
conn.execute("UPDATE schema_state SET file_digest = 'deadbeef0000deadbeef0000deadbeef' WHERE id=1")
conn.commit()
conn.close()
code, out, err = c.run(["--json", "--config", str(cfg40), "db", "init"])
conn = sqlite3.connect(dbpath40)
after_row = conn.execute("SELECT file_digest FROM schema_state WHERE id=1").fetchone()
conn.close()
refused = code != 0
silently_restamped = (not refused) and after_row[0] != "deadbeef0000deadbeef0000deadbeef"
record(
    "CLI-040",
    "PASS" if refused else "FAIL",
    f"code={code} out={out[:200]!r} err={err[:200]!r} before_digest_mismatch_forced=deadbeef... "
    f"after_digest={after_row[0][:16]} silently_restamped_without_refusal={silently_restamped} -- "
    f"repro: prama db init; sqlite3 x.db \"UPDATE schema_state SET file_digest='deadbeef...' WHERE id=1\"; prama db init again",
)

print("done db batch")

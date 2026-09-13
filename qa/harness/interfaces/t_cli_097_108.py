import sys, os, json, sqlite3, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record


def new_cfg(name):
    d = c.WORKDIR / name
    d.mkdir(exist_ok=True, parents=True)
    cfgf = d / "application.yaml"
    dbpath = d / "x.db"
    cfgf.write_text(
        "database:\n  dialect: sqlite\n"
        f"  sqlite:\n    path: {dbpath}\n"
        f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
        "security:\n  session_secret: test-only\n"
    )
    c.run_sub(["--config", str(cfgf), "db", "init"])
    tcode, tout, _ = c.run_sub(["--json", "--config", str(cfgf), "tenant", "create", "acme-bank"])
    tid = json.loads(tout)["id"]
    cfgf.write_text(cfgf.read_text() + f"tenancy:\n  default_tenant: {tid}\n")
    return cfgf, d, dbpath, tid


def make_source_db(path, n_tables=3):
    conn = sqlite3.connect(path)
    for i in range(n_tables):
        conn.execute(f"CREATE TABLE t{i} (id INTEGER, val TEXT)")
        conn.executemany(f"INSERT INTO t{i} VALUES (?, ?)", [(j, f"v{j}") for j in range(100 * (i + 1))])
    conn.commit()
    conn.close()


def declare_connection(app_dbpath, tenant_id, source_path, name="Trade extract"):
    """Insert a connection row directly via the async services, against the same sqlite db the CLI uses."""
    from prama.core.config import ConfigurationBuilder
    from prama.core.config.defaults import DEFAULTS
    from prama.db import Database
    from prama.semantic.services import ConnectionService

    cfg = (
        ConfigurationBuilder().with_defaults(DEFAULTS)
        .with_mapping({"database": {"dialect": "sqlite", "sqlite": {"path": str(app_dbpath)}, "schema_dir": str(c.REPO_ROOT / "schema")}}, name="t")
        .build()
    )

    async def go():
        db = Database.from_config(cfg)
        await db.start()
        try:
            async with db.unit_of_work() as uow:
                entity, _ = await ConnectionService(uow).configure(
                    tenant_id=tenant_id,
                    name=name,
                    source_type="sqlite",
                    config={"database_path": str(source_path)},
                    authored_by="alice",
                )
                await uow.flush()
                return str(entity.id)
        finally:
            await db.stop()

    return asyncio.run(go())


cfg97, d97, db97, tid97 = new_cfg("cli097")

# CLI-097: connectors lists every installed connector
code, out, err = c.run_sub(["--json", "--config", str(cfg97), "connectors"])
cat = json.loads(out)
code_t, out_t, err_t = c.run_sub(["--config", str(cfg97), "connectors"])
count_line = [l for l in out_t.splitlines() if "connector(s)" in l]
n_claimed = int(count_line[0].split()[0]) if count_line else -1
ok = code == 0 and len(cat) > 0 and n_claimed == len(cat) and all({"key", "kind", "display_name"} <= set(e) for e in cat)
record("CLI-097", "PASS" if ok else "FAIL", f"n_entries={len(cat)} n_claimed={n_claimed} keys={[e['key'] for e in cat][:10]}")

# CLI-098: connectors --key renders every registered key's form
bad98 = {}
for entry in cat:
    key = entry["key"]
    codek, outk, errk = c.run_sub(["--json", "--config", str(cfg97), "connectors", "--key", key])
    if codek != 0 or "Traceback" in errk:
        bad98[key] = (codek, errk[:150])
ok = not bad98
record("CLI-098", "PASS" if ok else "FAIL", f"n_keys={len(cat)} bad={bad98}")

# CLI-099: connectors --key with an unknown key
code, out, err = c.run_sub(["--config", str(cfg97), "connectors", "--key", "nosuch"])
ok = code != 0 and "Traceback" not in err and "KeyError" not in err
record("CLI-099", "PASS" if ok else "FAIL", f"code={code} err={err[:250]!r}")

# Prepare a real connection for CLI-100..108
src_path = d97 / "source.db"
make_source_db(src_path, n_tables=3)
conn_id = declare_connection(db97, tid97, src_path)

# CLI-100: connect test on a reachable source exits 0
code, out, err = c.run_sub(["--config", str(cfg97), "connect", "test", "--connection", conn_id])
ok = code == 0 and ":" in out
record("CLI-100", "PASS" if ok else "FAIL", f"code={code} out={out!r} err={err[:200]!r}")

# CLI-101: connect test distinguishing access problem from network -- needs a source
# whose credential lacks read permission. sqlite has no credential concept, so
# simulate by pointing at a file the process cannot read.
unreadable_db = d97 / "noaccess.db"
make_source_db(unreadable_db, n_tables=1)
os.chmod(unreadable_db, 0o000)
is_root = os.geteuid() == 0
if is_root:
    record("CLI-101", "BLOCKED", "running as root; chmod 000 does not deny read, cannot exercise the access-denied path")
else:
    conn_id_na = declare_connection(db97, tid97, unreadable_db, name="No access")
    code, out, err = c.run_sub(["--config", str(cfg97), "connect", "test", "--connection", conn_id_na])
    ok = code == 3 and "access problem" in out and "request:" in out
    record("CLI-101", "PASS" if ok else "FAIL", f"code={code} out={out!r} err={err[:200]!r}")
os.chmod(unreadable_db, 0o644)

# CLI-102: connect test with unknown connection id
code, out, err = c.run_sub(["--config", str(cfg97), "connect", "test", "--connection", "01NOSUCH"])
ok = code != 0 and "Traceback" not in err and "NoneType" not in err
record("CLI-102", "PASS" if ok else "FAIL", f"code={code} err={err[:250]!r}")

# CLI-103: connect commands require --connection
bad103 = {}
for sub in ["test", "discover", "profile"]:
    code, out, err = c.run_sub(["--config", str(cfg97), "connect", sub])
    if code != 2:
        bad103[sub] = (code, err[:150])
ok = not bad103
record("CLI-103", "PASS" if ok else "FAIL", f"bad={bad103}")

# CLI-104: connect discover --limit bounds the result
res104 = {}
for lim in ["1", "0", "-5", "100000"]:
    code, out, err = c.run_sub(["--json", "--config", str(cfg97), "connect", "discover", "--connection", conn_id, "--limit", lim])
    res104[lim] = (code, len(json.loads(out)) if code == 0 else None, err[:150] if code != 0 else "")
ok = res104["1"][0] == 0 and res104["1"][1] == 1 and res104["100000"][0] == 0 and "Traceback" not in str(res104)
record("CLI-104", "PASS" if ok else "FAIL", f"{res104}")

# CLI-105: connect discover orders largest first
code, out, err = c.run_sub(["--json", "--config", str(cfg97), "connect", "discover", "--connection", conn_id])
rows105 = json.loads(out)
sizes = [r["rows"] if r["rows"] is not None else r["bytes"] for r in rows105]
non_increasing = all(sizes[i] >= sizes[i + 1] for i in range(len(sizes) - 1))
code_t, out_t, _ = c.run_sub(["--config", str(cfg97), "connect", "discover", "--connection", conn_id])
claims_largest_first = "largest first" in out_t
ok = non_increasing and claims_largest_first
record("CLI-105", "PASS" if ok else "FAIL", f"sizes={sizes} non_increasing={non_increasing} claims_largest_first={claims_largest_first}")

# CLI-106: connect profile --object with a dotted path
bad106 = {}
code, out, err = c.run_sub(["--config", str(cfg97), "connect", "profile", "--connection", conn_id, "--object", "t0"])
bad106["t0 (bare table)"] = (code, err[-150:] if code != 0 else "ok")
code, out, err = c.run_sub(["--config", str(cfg97), "connect", "profile", "--connection", conn_id, "--object", "a.b.c.d"])
bad106["a.b.c.d (over-long)"] = (code, err[-200:] if code != 0 else f"UNEXPECTEDLY ACCEPTED: {out[:150]}")
code, out, err = c.run_sub(["--config", str(cfg97), "connect", "profile", "--connection", conn_id, "--object", ""])
bad106["'' (empty)"] = (code, err[-200:] if code != 0 else f"UNEXPECTEDLY ACCEPTED: {out[:150]}")
ok106 = bad106["t0 (bare table)"][0] == 0 and bad106["a.b.c.d (over-long)"][0] != 0 and "Traceback" not in str(bad106["a.b.c.d (over-long)"][1]) and bad106["'' (empty)"][0] != 0
record("CLI-106", "PASS" if ok106 else "FAIL", f"{bad106}")

# CLI-107: connect profile with no --object sweeps, bounded by --limit, and says how many of how many
code, out, err = c.run_sub(["--json", "--config", str(cfg97), "connect", "profile", "--connection", conn_id])
runs107 = json.loads(out)
code_t, out_t, err_t = c.run_sub(["--config", str(cfg97), "connect", "profile", "--connection", conn_id])
mentions_of_total = ("of 3" in out_t) or ("/3" in out_t) or ("3 object" in out_t)
ok = len(runs107) == 3 and code == 0  # only 3 objects exist, all under the default limit of 10
record("CLI-107", "PASS" if ok else "FAIL", f"n_profiled={len(runs107)} (source has 3 objects, default limit 10) mentions_total_in_text={mentions_of_total}")

# CLI-108: connect profile --json round-trips every profile field
code, out, err = c.run_sub(["--json", "--config", str(cfg97), "connect", "profile", "--connection", conn_id, "--object", "t0"])
doc108 = json.loads(out)[0]
code_t, out_t, err_t = c.run_sub(["--config", str(cfg97), "connect", "profile", "--connection", conn_id, "--object", "t0"])
col_keys = set(doc108.get("columns", [{}])[0].keys()) if doc108.get("columns") else set()
expected_fields = {"key_candidate", "constant", "null_rate", "distinct_estimate"}
missing = expected_fields - col_keys
first_col_json = doc108["columns"][0] if doc108.get("columns") else {}
ok = code == 0 and not missing
record(
    "CLI-108",
    "PASS" if ok else "FAIL",
    f"json_column_fields={sorted(col_keys)} missing={missing} first_col={first_col_json}",
)

print("done connect batch part1")

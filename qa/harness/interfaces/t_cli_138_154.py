import sys, os, json, asyncio, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "control3"
WORK.mkdir(exist_ok=True, parents=True)


def wf(name, text):
    p = WORK / name
    p.write_text(text, encoding="utf-8")
    return p


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


def declare_control(app_dbpath, tenant_id, identity, pql, *, active=True, criticality=1, schedule=""):
    from prama.core.config import ConfigurationBuilder
    from prama.core.config.defaults import DEFAULTS
    from prama.db import Database

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
                control, _ = await uow.controls.declare(
                    tenant_id=tenant_id, identity=identity, pql=pql, criticality=criticality, schedule=schedule
                )
                if active:
                    await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")
                await uow.flush()
                return str(control.id)
        finally:
            await db.stop()

    return asyncio.run(go())


def make_duckdb(path):
    import duckdb

    conn = duckdb.connect(str(path))
    conn.execute("CREATE TABLE positions_eod (account_id INTEGER, instrument_id INTEGER, notional_amount DOUBLE)")
    conn.executemany(
        "INSERT INTO positions_eod VALUES (?, ?, ?)",
        [(i, i, 100.0 * i) for i in range(1, 51)],
    )
    conn.close()


CLEAN_PQL = "CHECK positions_eod.notional_amount IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"

# CLI-138: control run --against a file that does not exist -- refused before db opens, before evidence written
cfg138, d138, db138, tid138 = new_cfg("cli138")
declare_control(db138, tid138, "c1", CLEAN_PQL)
code, out, err = c.run_sub(["--config", str(cfg138), "control", "run", "--against", "/nope/does-not-exist.duckdb"])
conn = sqlite3.connect(db138)
n_ev = conn.execute("SELECT COUNT(*) FROM ev_run").fetchone()[0]
conn.close()
ok = code == 1 and "Traceback" not in err and n_ev == 0
record("CLI-138", "PASS" if ok else "FAIL", f"code={code} err={err[:250]!r} evidence_rows_written={n_ev}")

# CLI-139: control run --against a directory
code, out, err = c.run_sub(["--config", str(cfg138), "control", "run", "--against", "/tmp"])
ok = code == 1 and "Traceback" not in err
record("CLI-139", "PASS" if ok else "FAIL", f"code={code} err={err[:250]!r}")

# CLI-140: control run --against a file that is not a database
notdb = WORK / "notadb.duckdb"
notdb.write_text("this is not a database\n")
code, out, err = c.run_sub(["--config", str(cfg138), "control", "run", "--against", str(notdb), "--dialect", "duckdb"])
conn = sqlite3.connect(db138)
n_ev2 = conn.execute("SELECT COUNT(*) FROM ev_run").fetchone()[0]
conn.close()
ok = code == 1 and "Traceback" not in err and n_ev2 == n_ev
record("CLI-140", "PASS" if ok else "FAIL", f"code={code} err={err[:250]!r} evidence_unchanged={n_ev2==n_ev}")

# CLI-141: control run --dialect restricted to duckdb/sqlite
code, out, err = c.run_sub(["--config", str(cfg138), "control", "run", "--against", "x", "--dialect", "postgresql"])
ok = code == 2 and "duckdb" in err and "sqlite" in err
record("CLI-141", "PASS" if ok else "FAIL", f"code={code} err={err[:300]!r}")

# CLI-142: control run with no tenant refuses before opening anything
cfg142 = WORK / "nodef.yaml"
cfg142.write_text(
    "database:\n  dialect: sqlite\n"
    f"  sqlite:\n    path: {db138}\n"
    f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
)
code, out, err = c.run_sub(["--config", str(cfg142), "control", "run", "--against", "/nope/x.duckdb"])
ok = code == 1 and "CLI.NO_TENANT" in err and "--tenant" in err
record("CLI-142", "PASS" if ok else "FAIL", f"code={code} err={err[:300]!r}")

# CLI-143: control run --tenant nonexistent writes nothing
code, out, err = c.run_sub(["--config", str(cfg138), "control", "run", "--against", "/nope/x.duckdb", "--tenant", "01NOSUCH"])
conn = sqlite3.connect(db138)
n_ev3 = conn.execute("SELECT COUNT(*) FROM ev_run").fetchone()[0]
conn.close()
ok = code != 0 and n_ev3 == n_ev
record("CLI-143", "PASS" if ok else "FAIL", f"code={code} err={err[:250]!r} evidence_rows={n_ev3}")

# Real run, against a real duckdb source, for CLI-144..148
cfg144, d144, db144, tid144 = new_cfg("cli144")
cid_clean = declare_control(db144, tid144, "clean", CLEAN_PQL)
# a control that will FAIL on real rows
FAILING_PQL = "CHECK positions_eod.notional_amount > 100000 SEVERITY major DIMENSION accuracy BECAUSE 'threshold'"
cid_fail = declare_control(db144, tid144, "failing", FAILING_PQL, criticality=2)
src144 = d144 / "src.duckdb"
make_duckdb(src144)

# CLI-144: --samples keeps failing rows, without it none are kept
code_nosample, out_ns, err_ns = c.run_sub(["--config", str(cfg144), "control", "run", "--against", str(src144), "--dialect", "duckdb"])
conn = sqlite3.connect(db144)
n_samples_without = conn.execute("SELECT COUNT(*) FROM ev_sample").fetchone()[0]
conn.close()
code_sample, out_s, err_s = c.run_sub(["--config", str(cfg144), "control", "run", "--against", str(src144), "--dialect", "duckdb", "--samples"])
conn = sqlite3.connect(db144)
n_samples_with = conn.execute("SELECT COUNT(*) FROM ev_sample").fetchone()[0]
conn.close()
ok = n_samples_without == 0 and n_samples_with > n_samples_without
record("CLI-144", "PASS" if ok else "FAIL", f"without_samples={n_samples_without} with_samples={n_samples_with} codes=({code_nosample},{code_sample})")

# CLI-145: --due-only runs only what is due, triggered_by differs
cfg145, d145, db145, tid145 = new_cfg("cli145")
declare_control(db145, tid145, "c1", CLEAN_PQL, schedule="0 0 1 1 *")  # once a year, almost certainly not due today
declare_control(db145, tid145, "c2", "CHECK positions_eod.account_id IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'x'")
declare_control(db145, tid145, "c3", "CHECK positions_eod.instrument_id IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'x'")
src145 = d145 / "src.duckdb"
make_duckdb(src145)
code_due, out_due, err_due = c.run_sub(["--json", "--config", str(cfg145), "control", "run", "--against", str(src145), "--dialect", "duckdb", "--due-only"])
code_all, out_all, err_all = c.run_sub(["--json", "--config", str(cfg145), "control", "run", "--against", str(src145), "--dialect", "duckdb"])
doc_due = json.loads(out_due) if code_due == 0 else {}
doc_all = json.loads(out_all) if code_all == 0 else {}
conn = sqlite3.connect(db145)
triggers = [r[0] for r in conn.execute("SELECT triggered_by FROM ev_run ORDER BY started_at").fetchall()]
conn.close()
ok = doc_due.get("controls") != doc_all.get("controls") and "schedule" in triggers and "manual" in triggers
record(
    "CLI-145",
    "PASS" if ok else "FAIL",
    f"due_only_controls={doc_due.get('controls')} all_controls={doc_all.get('controls')} triggers_seen={triggers}",
)

# CLI-146: control run exits non-zero when a control's source is unreadable
cfg146, d146, db146, tid146 = new_cfg("cli146")
declare_control(db146, tid146, "c1", "CHECK nonexistent_table.col IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'x'")
src146 = d146 / "src.duckdb"
make_duckdb(src146)
code, out, err = c.run_sub(["--config", str(cfg146), "control", "run", "--against", str(src146), "--dialect", "duckdb"])
ok = code == 1 and ("!" in out or "!" in err)
record("CLI-146", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r} err={err[:200]!r}")

# CLI-147: control run exits non-zero when a control is unschedulable
cfg147, d147, db147, tid147 = new_cfg("cli147")
declare_control(db147, tid147, "c1", CLEAN_PQL, schedule="not a valid cron")
src147 = d147 / "src.duckdb"
make_duckdb(src147)
code, out, err = c.run_sub(["--config", str(cfg147), "control", "run", "--against", str(src147), "--dialect", "duckdb", "--due-only"])
ok = code == 1 and "!" in out
record("CLI-147", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-148: control run --json carries run_id and verdict counts
cfg148, d148, db148, tid148 = new_cfg("cli148")
declare_control(db148, tid148, "c1", CLEAN_PQL)
src148 = d148 / "src.duckdb"
make_duckdb(src148)
code, out, err = c.run_sub(["--json", "--config", str(cfg148), "control", "run", "--against", str(src148), "--dialect", "duckdb"])
doc = json.loads(out)
conn = sqlite3.connect(db148)
run_ids = [r[0] for r in conn.execute("SELECT id FROM ev_run").fetchall()]
conn.close()
ok = code == 0 and doc.get("run_id") in run_ids and "verdicts" in doc and "unschedulable" in doc
record("CLI-148", "PASS" if ok else "FAIL", f"doc_keys={sorted(doc.keys())} run_id_in_ledger={doc.get('run_id') in run_ids}")

print("done control batch part3 (run)")

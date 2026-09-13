import asyncio, sys, os, sqlite3
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.db import Database
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.evidence.record import EvidenceRecord

SCR = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/r3/plat2/ops"
REPO = "/home/ashutosh/PycharmProjects/prama"

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

def cfg_for(dbpath):
    return (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping({
            "database": {
                "dialect": "sqlite",
                "sqlite": {"path": dbpath},
                "schema_dir": f"{REPO}/schema",
                "verify_on_start": True,
            },
            "security": {"session_secret": "test-only-not-a-secret", "cookies_https_only": False},
        }, name="test")
        .build()
    )

def rec(**overrides):
    base = dict(
        plan_id="ir:sha256:abc", control_id="01CONTROL", dataset="positions_eod",
        verdict="pass", metrics={"scanned_rows": 1000.0, "violating_rows": 0.0},
        started_at="2026-09-08T06:00:00Z", finished_at="2026-09-08T06:00:03Z", duration_ms=3000,
    )
    base.update(overrides)
    return EvidenceRecord(**base)

async def main():
    dbpath = f"{SCR}/wal_test.db"
    for ext in ("", "-wal", "-shm"):
        p = dbpath + ext
        if os.path.exists(p): os.remove(p)

    cfg = cfg_for(dbpath)
    db = Database.from_config(cfg)
    db.initialise(applied_by="qa-r3")
    await db.start()

    async with db.unit_of_work() as uow:
        t = uow.tenants.create(slug="wal-bank", display_name="WAL Bank")
        await uow.flush()
        tenant_id = str(t.id)
        for i in range(5):
            await uow.evidence.append(rec(verdict="pass" if i % 2 == 0 else "fail"), tenant_id=tenant_id)

    mode = sqlite3.connect(dbpath).execute("PRAGMA journal_mode").fetchone()[0]

    async with db.unit_of_work() as uow:
        pre_verify = await uow.evidence.verify(tenant_id)

    wal_exists_before = os.path.exists(dbpath + "-wal")

    # keep a write connection open (simulating "writes in progress") while backing up
    holder = sqlite3.connect(dbpath)
    holder.execute("PRAGMA journal_mode=WAL")
    holder.execute("BEGIN")
    holder.execute("CREATE TABLE IF NOT EXISTS _wal_probe (x INTEGER)")
    holder.execute("INSERT INTO _wal_probe (x) VALUES (1)")
    # do not commit yet -- simulate an in-flight write during backup

    src_conn = sqlite3.connect(dbpath)
    restored_path = f"{SCR}/wal_test_restored.db"
    if os.path.exists(restored_path): os.remove(restored_path)
    dst_conn = sqlite3.connect(restored_path)
    with dst_conn:
        src_conn.backup(dst_conn)
    src_conn.close()
    dst_conn.close()

    holder.rollback()
    holder.close()

    cfg2 = cfg_for(restored_path)
    db2 = Database.from_config(cfg2)
    try:
        report = db2.verify()
        drift_ok = (len(report.drifts) == 0)
        report_desc = f"drifts={report.drifts!r}"
    except Exception as e:
        drift_ok = False
        report_desc = f"EXC {type(e).__name__}: {e}"
    line("OPS-025", "PASS" if drift_ok else "FAIL",
         f"journal_mode={mode} wal_file_existed_pre_backup={wal_exists_before} restored_db_verify_clean={drift_ok} {report_desc}")

    await db2.start()
    async with db2.unit_of_work() as uow:
        post_verify = await uow.evidence.verify(tenant_id)
    ok2 = getattr(post_verify, "is_intact", None)
    line("OPS-026", "PASS" if ok2 else "FAIL",
         f"pre_backup_verify={pre_verify} post_restore_verify={post_verify}")

    await db.stop()
    await db2.stop()

asyncio.run(main())

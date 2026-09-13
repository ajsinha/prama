import asyncio, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database
from prama.semantic.services.graph import ConnectionService, BindingService
from prama.semantic.services import DatasetService

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")

def make_config(tmp_dir):
    return (
        ConfigurationBuilder().with_defaults(DEFAULTS).with_mapping(
            {"database": {"dialect": "sqlite", "sqlite": {"path": str(tmp_dir / "t.db")},
                          "schema_dir": str(REPO_ROOT / "schema"), "verify_on_start": True},
             "security": {"session_secret": "x", "cookies_https_only": False}}, name="test").build()
    )

async def main():
    tmp = Path(tempfile.mkdtemp())
    config = make_config(tmp)
    db = Database.from_config(config)
    db.initialise(applied_by="qa")
    await db.start()
    try:
        async with db.unit_of_work() as uow:
            tenant = uow.tenants.create(slug="acme", display_name="Acme")
            await uow.flush()
            tid = str(tenant.id)
        async with db.unit_of_work() as uow:
            conn_svc = ConnectionService(uow)
            conn, _ = await conn_svc.configure(tenant_id=tid, name="C1", source_type="postgres")
            print("conn id", conn.id)
            v = await conn_svc.record_health(tenant_id=tid, connection_id=str(conn.id), state="healthy")
            print("record_health returned version:", v)
            events = await uow.audit.for_object(tid, "connection", str(conn.id))
            print("events (same uow, before exit):", [(e.action, e.actor_kind) for e in events])
        async with db.unit_of_work() as uow:
            events2 = await uow.audit.for_object(tid, "connection", str(conn.id))
            print("events (new uow, after commit):", [(e.action, e.actor_kind) for e in events2])
    finally:
        await db.stop()
        db.sync_engine().dispose()

asyncio.run(main())

import asyncio, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database
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
            svc = DatasetService(uow)
            try:
                entity, version = await svc.declare(tenant_id=tid, name="Bad Crit Zero", criticality=0)
                print("no exception, version.criticality =", version.criticality)
            except Exception as e:
                print("CAUGHT INSIDE:", type(e).__name__, e)
        print("exited async-with cleanly")
    finally:
        await db.stop()
        db.sync_engine().dispose()

asyncio.run(main())

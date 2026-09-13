import asyncio, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.core.errors import ConflictError
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
        base = "C" * 128
        name_a = base + " AAAA suffix one"
        name_b = base + " BBBB suffix two, totally different"
        async with db.unit_of_work() as uow:
            svc = DatasetService(uow)
            entity_a, va = await svc.declare(tenant_id=tid, name=name_a)
            print("declared A ok, slug:", va.slug, "len:", len(va.slug))
        async with db.unit_of_work() as uow:
            svc = DatasetService(uow)
            try:
                entity_b, _ = await svc.declare(tenant_id=tid, name=name_b)
                print("declared B: NO EXCEPTION (unexpected) -- silently overwrote / coexisted")
            except ConflictError as e:
                print("declared B: ConflictError as expected:", e)
    finally:
        await db.stop()
        db.sync_engine().dispose()

asyncio.run(main())

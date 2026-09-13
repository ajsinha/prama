import asyncio, tempfile
from pathlib import Path
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database
from prama.semantic.services import DatasetService
from prama.semantic.services.graph import ConnectionService, BindingService

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")

def make_config(tmp_dir):
    return (
        ConfigurationBuilder().with_defaults(DEFAULTS).with_mapping({
            "database": {"dialect": "sqlite", "sqlite": {"path": str(tmp_dir / "t.db")},
                         "schema_dir": str(REPO_ROOT / "schema"), "verify_on_start": True},
            "security": {"session_secret": "x", "cookies_https_only": False},
        }, name="test").build()
    )

async def main():
    tmp_dir = Path(tempfile.mkdtemp())
    db = Database.from_config(make_config(tmp_dir))
    db.initialise(applied_by="qa")
    await db.start()
    try:
        async with db.unit_of_work() as uow:
            tenant = uow.tenants.create(slug="acme", display_name="acme")
            await uow.flush()
            tenant_id = str(tenant.id)
        async with db.unit_of_work() as uow:
            d, _ = await DatasetService(uow).declare(tenant_id=tenant_id, name="D1")
            c, _ = await ConnectionService(uow).configure(tenant_id=tenant_id, name="C1", source_type="file")
            b, _ = await BindingService(uow).bind_dataset(tenant_id=tenant_id, dataset_id=str(d.id), connection_id=str(c.id), physical_ref={})
            binding_id = str(b.id)
        try:
            async with db.unit_of_work() as uow:
                v = await BindingService(uow).record_drift(tenant_id=tenant_id, binding_id=binding_id, drift_state="changed")
            print("changed: SUCCEEDED, status=", v.status, "drift_state=", v.drift_state)
        except Exception as e:
            print("changed: RAISED", type(e).__name__, str(e)[:200])
        try:
            async with db.unit_of_work() as uow:
                v = await BindingService(uow).record_drift(tenant_id=tenant_id, binding_id=binding_id, drift_state="gone")
            print("gone: SUCCEEDED, status=", v.status, "drift_state=", v.drift_state)
        except Exception as e:
            print("gone: RAISED", type(e).__name__, str(e)[:200])
    finally:
        await db.stop()
        db.sync_engine().dispose()

asyncio.run(main())

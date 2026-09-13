import asyncio, tempfile, os
from pathlib import Path
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database
from prama.semantic.services.graph import ConnectionService
from prama.semantic.services.connectivity import ConnectivityService
from prama.connect.builtin import register_builtin
from prama.connect.registry import ConnectorRegistry

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
    os.environ["PG_PASSWORD"] = "hunter2-secret-value"
    tmp_dir = Path(tempfile.mkdtemp())
    db = Database.from_config(make_config(tmp_dir))
    db.initialise(applied_by="qa")
    await db.start()
    registry = register_builtin(ConnectorRegistry())
    try:
        async with db.unit_of_work() as uow:
            tenant = uow.tenants.create(slug="acme", display_name="acme")
            await uow.flush()
            tenant_id = str(tenant.id)
        async with db.unit_of_work() as uow:
            entity, _ = await ConnectionService(uow).configure(
                tenant_id=tenant_id, name="PG Conn", source_type="postgresql",
                credential_ref="env://PG_PASSWORD",
                config={"host": "localhost", "database": "acme", "schemas": ["public"]},
            )
            connection_id = str(entity.id)
        async with db.unit_of_work() as uow:
            try:
                connector = await ConnectivityService(uow, registry=registry).connector_for(connection_id)
                print("SUCCESS:", connector.config.get("password"))
            except Exception as e:
                print("RAISED:", type(e).__name__, e)
    finally:
        await db.stop()
        db.sync_engine().dispose()

asyncio.run(main())

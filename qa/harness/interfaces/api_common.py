import sys
from pathlib import Path

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")
sys.path.insert(0, str(REPO_ROOT / "src"))

import asyncio
import httpx
from httpx import ASGITransport

from prama.api import API_PREFIX, create_app
from prama.core.config import Configuration, ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database
from prama.db.security import ApiKeyIssuer


def sqlite_config(db_path, extra=None, web_enabled=True):
    mapping = {
        "database": {
            "dialect": "sqlite",
            "sqlite": {"path": str(db_path)},
            "schema_dir": str(REPO_ROOT / "schema"),
            "verify_on_start": True,
        },
        "security": {"session_secret": "test-only-not-a-secret", "cookies_https_only": False},
        "web": {"enabled": web_enabled},
    }
    if extra:
        for k, v in extra.items():
            mapping.setdefault(k, {}).update(v) if isinstance(v, dict) else mapping.update({k: v})
    return ConfigurationBuilder().with_defaults(DEFAULTS).with_mapping(mapping, name="test").build()


def new_database(db_path):
    cfg = sqlite_config(db_path)
    db = Database.from_config(cfg)
    db.initialise(applied_by="qa")
    return db, cfg


async def _issue_key(database, tenant_id, *, principal="alice", scopes=None):
    issued = ApiKeyIssuer().issue(environment="test")
    async with database.unit_of_work() as uow:
        person = uow.principals.create(tenant_id=tenant_id, username=principal, display_name=principal)
        await uow.flush()
        uow.api_keys.create(
            tenant_id=tenant_id,
            principal_id=str(person.id),
            name="api tests",
            key_prefix=issued.prefix,
            key_hash=issued.hash,
            scopes=scopes if scopes is not None else ["*"],
        )
    return issued.plaintext


async def _create_tenant(database, slug="acme-bank"):
    async with database.unit_of_work() as uow:
        tenant = uow.tenants.create(slug=slug, display_name=slug)
        await uow.flush()
        return str(tenant.id)


class Env:
    """One app + database + a couple of tenants/keys, all in one place."""

    def __init__(self, db_path):
        self.database, self.config = new_database(db_path)
        self.app = create_app(self.config, database=self.database)
        self.tenant_id = None
        self.other_tenant_id = None
        self.api_key = None
        self.other_key = None

    async def start(self):
        await self.database.start()
        self.tenant_id = await _create_tenant(self.database, "acme-bank")
        self.other_tenant_id = await _create_tenant(self.database, "rival-bank")
        self.api_key = await _issue_key(self.database, self.tenant_id, principal="alice")
        self.other_key = await _issue_key(self.database, self.other_tenant_id, principal="mallory")
        self._lifespan_cm = self.app.router.lifespan_context(self.app)
        await self._lifespan_cm.__aenter__()

    async def stop(self):
        await self._lifespan_cm.__aexit__(None, None, None)
        await self.database.stop()

    def client(self, key=None, headers=None):
        h = dict(headers or {})
        if key:
            h["Authorization"] = f"Bearer {key}"
        transport = ASGITransport(app=self.app)
        return httpx.AsyncClient(transport=transport, base_url="http://testserver" + API_PREFIX, headers=h)


def run(coro):
    return asyncio.run(coro)

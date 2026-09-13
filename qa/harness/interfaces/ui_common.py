import sys
from pathlib import Path

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")
sys.path.insert(0, str(REPO_ROOT / "src"))

import asyncio
import httpx
from httpx import ASGITransport

from prama.api import create_app
from prama.core.config import Configuration, ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database
from prama.db.security import PasswordHasher


def ui_config(db_path, *, default_tenant=None, web_enabled=True, secret="test-only-not-a-secret"):
    mapping = {
        "database": {
            "dialect": "sqlite",
            "sqlite": {"path": str(db_path)},
            "schema_dir": str(REPO_ROOT / "schema"),
            "verify_on_start": True,
        },
        "security": {"session_secret": secret, "cookies_https_only": False},
        "web": {"enabled": web_enabled},
    }
    if default_tenant:
        mapping["tenancy"] = {"default_tenant": default_tenant}
    return ConfigurationBuilder().with_defaults(DEFAULTS).with_mapping(mapping, name="test").build()


class UiEnv:
    """One app + database, with role-based principals ready to sign in."""

    BUILTIN_ROLES = {
        "admin": ("Everything, including creating other people.", ["*"]),
        "owner": (
            "Declares datasets and approves controls.",
            ["declaration:*", "relationship:*", "control:approve", "control:read",
             "attestation:sign", "evidence:read", "report:read"],
        ),
        "steward": (
            "Works incidents and breaks; proposes controls but does not approve them.",
            ["control:propose", "control:read", "incident:*", "break:*",
             "evidence:read", "report:read", "declaration:read"],
        ),
        "auditor": (
            "Reads everything and changes nothing.",
            ["control:read", "declaration:read", "relationship:read", "evidence:read",
             "report:read", "attestation:read"],
        ),
    }

    def __init__(self, db_path, *, default_tenant_fallback=False, web_enabled=True):
        self.db_path = db_path
        self.database = None
        self.tenant_id = None
        self._default_tenant_fallback = default_tenant_fallback
        self._web_enabled = web_enabled
        self._passwords = {}

    async def start(self):
        # Build DB with a placeholder config first (tenant unknown), init schema.
        placeholder_cfg = ui_config(self.db_path)
        self.database = Database.from_config(placeholder_cfg)
        self.database.initialise(applied_by="qa")
        await self.database.start()
        async with self.database.unit_of_work() as uow:
            tenant = uow.tenants.create(slug="acme-bank", display_name="Acme Bank")
            await uow.flush()
            self.tenant_id = str(tenant.id)
        self.config = ui_config(
            self.db_path,
            default_tenant=self.tenant_id if self._default_tenant_fallback else None,
            web_enabled=self._web_enabled,
        )
        self.app = create_app(self.config, database=self.database)
        self._lifespan_cm = self.app.router.lifespan_context(self.app)
        await self._lifespan_cm.__aenter__()

    async def stop(self):
        await self._lifespan_cm.__aexit__(None, None, None)
        await self.database.stop()

    async def create_principal(self, username, password, roles, *, tenant_id=None):
        tenant_id = tenant_id or self.tenant_id
        async with self.database.unit_of_work() as uow:
            person = uow.principals.create(tenant_id=tenant_id, username=username, display_name=username)
            await uow.flush()
            uow.principals.set_password(person, password)
            for role_name in roles:
                role = await uow.roles.by_name(tenant_id, role_name)
                if role is None:
                    description, permissions = self.BUILTIN_ROLES[role_name]
                    role = uow.roles.create(
                        tenant_id=tenant_id, name=role_name, permissions=permissions,
                        description=description, builtin=True,
                    )
                    await uow.flush()
                await uow.roles.grant(str(person.id), str(role.id))
            await uow.flush()
            return str(person.id)

    def client(self):
        transport = ASGITransport(app=self.app)
        return httpx.AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False)

    async def signed_in_client(self, username, password, tenant_slug="acme-bank"):
        http = self.client()
        r = await http.post("/sign-in", data={"username": username, "password": password, "tenant": tenant_slug})
        return http, r


def run(coro):
    return asyncio.run(coro)


def tamper_session_cookie(secret, raw_cookie, sign_with=None, **overrides):
    """Decode, modify, and correctly re-sign a Starlette session cookie -- matching
    Starlette's own SessionMiddleware exactly: TimestampSigner with NO salt, and
    STANDARD (not URL-safe) base64 for the payload, per starlette/middleware/sessions.py.

    *secret* decodes the presented cookie; *sign_with* (default: same as secret) is the
    key used to re-sign it -- pass a different value to simulate a forged/guessed key.
    """
    import itsdangerous, json as _json
    from base64 import b64decode, b64encode

    signer = itsdangerous.TimestampSigner(str(secret))
    data = signer.unsign(raw_cookie.encode(), max_age=14 * 24 * 60 * 60)
    payload = _json.loads(b64decode(data))
    for key, value in overrides.items():
        if value is _REMOVE:
            payload.pop(key, None)
        else:
            payload[key] = value
    new_data = b64encode(_json.dumps(payload).encode("utf-8"))
    out_signer = itsdangerous.TimestampSigner(str(sign_with if sign_with is not None else secret))
    return out_signer.sign(new_data).decode("utf-8")


class _Remove:
    pass


_REMOVE = _Remove()

"""The bootstrap admin: a way in on a fresh installation, said out loud.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from prama.api import create_app
from prama.core.config import Configuration
from prama.core.errors import ConfigError
from prama.db import Database
from prama.security import bootstrap


class _With:
    """A configuration with a few settings changed, the rest as given."""

    def __init__(self, base: Configuration, **overrides: Any) -> None:
        self._base, self._overrides = base, overrides

    def get(self, path: str, default: Any = None) -> Any:
        return self._overrides.get(path, self._base.get(path, default))

    def get_bool(self, path: str, default: bool | None = None) -> bool:
        return bool(self.get(path, default))


async def test_an_empty_installation_gets_an_estate_and_an_admin(
    sqlite_config: Configuration, started_database: Database
) -> None:
    config = _With(sqlite_config, **{"security.bootstrap_admin": True})
    async with started_database.unit_of_work() as uow:
        created = await bootstrap.seed(uow, config)
        again = await bootstrap.seed(uow, config)
        (estate,) = await uow.tenants.list_active(limit=5)
        admin = await uow.principals.authenticate(
            str(estate.id), "admin", bootstrap.DEFAULT_PASSWORD
        )
        active = await bootstrap.default_password_active(uow, config)
    assert created and again is None  # created once, never again
    assert estate.slug == "default"
    assert admin is not None and "admin" in {r.name for r in admin.roles}
    assert active and bootstrap.ACTIVE.value() == 1


async def test_it_is_not_created_where_somebody_already_is(
    sqlite_config: Configuration, started_database: Database, tenant_id: str
) -> None:
    config = _With(sqlite_config, **{"security.bootstrap_admin": True})
    async with started_database.unit_of_work() as uow:
        person = uow.principals.create(tenant_id=tenant_id, username="alice", display_name="A")
        uow.principals.set_password(person, "a-long-enough-password")
        await uow.flush()
        assert await bootstrap.seed(uow, config) is None
        assert await uow.principals.by_username(tenant_id, "admin") is None


def test_the_default_password_refuses_to_start_outside_development(
    sqlite_config: Configuration,
) -> None:
    production = _With(sqlite_config, **{"app.environment": "production"})
    with pytest.raises(ConfigError, match="default password"):
        bootstrap.refuse_outside_development(True, production)
    bootstrap.refuse_outside_development(False, production)  # changed: fine
    bootstrap.refuse_outside_development(True, sqlite_config)  # development: warned
    allowed = _With(
        sqlite_config,
        **{"app.environment": "production", "security.allow_default_admin_password": True},
    )
    bootstrap.refuse_outside_development(True, allowed)


async def test_signing_in_with_it_puts_a_banner_on_every_page(
    sqlite_config: Configuration, started_database: Database
) -> None:
    async with started_database.unit_of_work() as uow:
        await bootstrap.seed(uow, _With(sqlite_config, **{"security.bootstrap_admin": True}))
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ui,
        app.router.lifespan_context(app),
    ):
        signed = await ui.post(
            "/sign-in", data={"username": "admin", "password": bootstrap.DEFAULT_PASSWORD}
        )
        assert signed.status_code == 303
        page = await ui.get("/account")
        assert "default password" in page.text

"""Linting a control must not require permission to author one.

QA round 3, `Q-66`. The console's four language operations — `check`,
`completions`, `hover`, `compile` — are POSTs, because a control's text does not
belong in a query string. `ControlRoutes.page(scope="auto")` derives the
permission from the HTTP verb, so all four inherited the class's
`control:propose`.

They store nothing. Each one builds a `LanguageService` over the catalogue and
returns diagnostics, completions, a hover, or SQL. Requiring an authoring scope
to read the language is a category error, and it has a concrete victim: `owner`
holds `control:approve` and deliberately **not** `control:propose`, because the
vocabulary separates authoring a control from activating one — that is the
maker-checker rule expressed as a scope. So the owner could approve a control
and could not check its text first.

The workaround that invites — granting owners `control:propose` — erases exactly
the separation the two scopes exist to create, which is why this was recorded
for decision rather than quietly patched.

The counterfactual is the owner, not the admin. An admin holds the wildcard and
passes whatever the scope says, so a test written against `admin` would have
passed before the fix and after it, and proved nothing either way.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport

from prama.core.config import Configuration
from prama.db import Database

PASSWORD = "correct-horse-battery-staple"
#: Every language route, with the form fields it needs. All four are POSTs and
#: all four are reads; a new one added to this class should appear here too.
LANGUAGE_ROUTES = (
    ("/controls/check", {"source": "CHECK positions_eod.isin IS NOT NULL"}),
    ("/controls/completions", {"source": "CHECK positions_eod.", "line": "0", "column": "20"}),
    (
        "/controls/hover",
        {"source": "CHECK positions_eod.isin IS NOT NULL", "line": "0", "column": "7"},
    ),
    (
        "/controls/compile",
        {"source": "CHECK positions_eod.isin IS NOT NULL", "target": "postgresql"},
    ),
)


async def _sign_in_as(
    config: Configuration, estate: Database, tenant_id: str, role: str, username: str
) -> tuple[httpx.AsyncClient, object]:
    """A console signed in as a principal holding exactly one built-in role."""
    from prama.api import create_app
    from prama.cli.principal import BUILTIN_ROLES

    async with estate.unit_of_work() as uow:
        principal = uow.principals.create(
            tenant_id=tenant_id, username=username, display_name=username
        )
        uow.principals.set_password(principal, PASSWORD)
        principal.status = "active"
        await uow.flush()
        description, permissions = BUILTIN_ROLES[role]
        row = uow.roles.create(
            tenant_id=tenant_id,
            name=role,
            permissions=permissions,
            description=description,
            builtin=True,
        )
        await uow.flush()
        await uow.roles.grant(str(principal.id), str(row.id))
        await uow.flush()

    app = create_app(config, database=estate)
    return app, principal


@pytest.fixture
async def owner_console(
    qa_config: Configuration, estate: Database, two_tenants: tuple[str, str]
) -> AsyncIterator[httpx.AsyncClient]:
    """Signed in as an `owner` — the role the defect actually locked out."""
    ours, _ = two_tenants
    app, _ = await _sign_in_as(qa_config, estate, ours, "owner", "olivia")
    async with (
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http,
        app.router.lifespan_context(app),
    ):
        response = await http.post(
            "/sign-in",
            data={"username": "olivia", "password": PASSWORD, "tenant": "acme-bank"},
        )
        assert response.status_code == 303, f"sign-in failed: {response.status_code}"
        yield http


@pytest.mark.parametrize("path,form", LANGUAGE_ROUTES, ids=[p for p, _ in LANGUAGE_ROUTES])
async def test_an_owner_may_read_the_language(
    owner_console: httpx.AsyncClient, path: str, form: dict[str, str]
) -> None:
    """The role that approves controls can lint, complete, explain and compile."""
    response = await owner_console.post(path, data=form)
    assert response.status_code != 403, (
        f"{path} refused an owner, who holds control:approve and control:read. "
        "A route that stores nothing must not demand an authoring scope."
    )
    assert response.status_code < 500, f"{path} returned {response.status_code}"


async def test_the_language_routes_require_control_read_not_control_propose() -> None:
    """Asserted on the routing table, so a new route cannot quietly regress.

    The response-code test above proves an owner gets in today. This proves
    *why*, and it fails if somebody reverts the scope while leaving the owner
    role broad enough to pass the first test anyway.
    """
    from prama.web.routes.control_routes import ControlRoutes

    declared: dict[str, str] = {}

    class _Spy(ControlRoutes):
        def __init__(self) -> None:  # no router, no app; only the registrations
            pass

        def page(self, path, _handler, **declared_options):  # type: ignore[override]
            declared[path] = declared_options.get("scope", "auto")

    _Spy().register()

    for path, _ in LANGUAGE_ROUTES:
        assert declared.get(path) == "control:read", (
            f"{path} declares {declared.get(path)!r}; it reads the language and "
            "stores nothing, so it must require control:read"
        )

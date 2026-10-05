"""Every console page ends with "About this page", and every entry is a page.

After Maya's ``tests/test_page_help.py``: a new screen cannot ship without saying
what it is, an entry cannot outlive its page, and "More in Help" cannot point at a
help page that does not exist. One thing more than Maya: the "Who can use this
page" tile is derived from the permission the page is registered with, and is
checked against the check that actually runs.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from prama.api import create_app
from prama.core.config import Configuration
from prama.web import help_catalog, page_help
from prama.web.routes.base import PAGE_SCOPES

#: Routes the console serves that are not pages of it: the API's own docs.
NOT_CONSOLE = ("/docs", "/redoc", "/openapi")


def _console_pages(config: Configuration) -> set[str]:
    app = create_app(config)
    return {
        route.path
        for route in app.routes
        if "GET" in (getattr(route, "methods", None) or set())
        and route.path in PAGE_SCOPES
        and not route.path.startswith(("/help/assets", "/help/images"))
        and not route.path.endswith(".json")
        and not route.path.startswith(NOT_CONSOLE)
    }


def test_every_page_has_its_help_and_every_entry_is_a_page(sqlite_config: Configuration) -> None:
    pages = _console_pages(sqlite_config)
    assert len(pages) > 40, "the route scan found too few pages to mean anything"
    missing = sorted(pages - set(page_help.PAGES) - set(page_help.EXEMPT))
    assert missing == [], f"pages with no 'About this page': {missing}"
    stale = sorted((set(page_help.PAGES) | set(page_help.EXEMPT)) - pages)
    assert stale == [], f"help for pages that do not exist: {stale}"
    assert not set(page_help.PAGES) & set(page_help.EXEMPT)


@pytest.mark.parametrize("path", sorted(page_help.PAGES))
def test_an_entry_is_short_and_points_somewhere_real(path: str) -> None:
    entry = page_help.PAGES[path]
    assert entry.what.strip() and len(entry.what) <= 140, path
    assert 1 <= len(entry.tiles) <= 3, f"{path}: a hint, not a manual (1-3 written tiles)"
    for tile in entry.tiles:
        assert tile.heading.strip() and tile.text.strip(), (path, tile)
        assert re.fullmatch(r"[a-z0-9-]+", tile.icon), (path, tile.icon)
        assert len(re.sub(r"<[^>]+>", "", tile.text)) <= 140, (path, tile.heading)
    if entry.more is not None:
        slug = entry.more.split("#")[0]
        assert slug in help_catalog.BY_SLUG, f"{path}: More in Help names {slug!r}"


def test_who_can_use_it_is_the_check_that_runs() -> None:
    """The derived tile names the registered scope, and the roles that really hold it."""
    tiles = page_help.for_route("/admin/users")["tiles"]  # type: ignore[index]
    who = tiles[-1]
    assert who.heading == "Who can use this page"
    assert f"<code>{PAGE_SCOPES['/admin/users']}</code>" in who.text
    assert "<strong>admin</strong>" in who.text and "<strong>auditor</strong>" not in who.text
    public = page_help.for_route("/")["tiles"][-1]  # type: ignore[index]
    assert PAGE_SCOPES["/"] is None and "no sign-in" in public.text


@pytest.fixture
async def stranger(
    sqlite_config: Configuration, started_database: Any, tenant_id: str
) -> AsyncIterator[httpx.AsyncClient]:
    """No session: somebody arriving from outside."""
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http,
        app.router.lifespan_context(app),
    ):
        yield http


async def test_it_is_at_the_foot_of_a_public_page(stranger: Any) -> None:
    page = (await stranger.get("/sign-in")).text
    assert 'id="page-help"' in page and "About this page" in page
    assert 'class="ph-tile"' in page and "Who can use this page" in page
    assert 'href="/help/accounts"' in page  # More in Help
    assert "data-page-help" in page  # the ? in the header


async def test_it_is_at_the_foot_of_a_console_page(ui: Any) -> None:
    page = (await ui.get("/estate")).text
    assert 'id="page-help"' in page and "The four counts" in page
    assert 'href="/help/architecture-semantic-layer"' in page

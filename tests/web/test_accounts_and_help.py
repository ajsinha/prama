"""The pages adopted from Maya: landing, help, about, my account, API keys and
administration.

Each rule is tested with its counterfactual beside it, so none of these can be
satisfied by a page that refuses everything.

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
from prama.db import Database
from prama.report.themes import THEMES
from prama.security.accounts import BUILTIN_ROLES
from prama.web import help_catalog

PASSWORD = "correct horse battery staple"


async def _person(database: Database, tenant_id: str, username: str, role: str | None) -> str:
    async with database.unit_of_work() as uow:
        person = uow.principals.create(
            tenant_id=tenant_id, username=username, display_name=username.title()
        )
        uow.principals.set_password(person, PASSWORD)
        await uow.flush()
        if role is not None:
            _, permissions = BUILTIN_ROLES[role]
            granted = await uow.roles.by_name(tenant_id, role)
            if granted is None:
                granted = uow.roles.create(tenant_id=tenant_id, name=role, permissions=permissions)
                await uow.flush()
            await uow.roles.grant(str(person.id), str(granted.id))
            await uow.flush()
        return str(person.id)


async def _sign_in(ui: Any, username: str, password: str = PASSWORD) -> None:
    response = await ui.post("/sign-in", data={"username": username, "password": password})
    assert response.status_code == 303, response.text


@pytest.fixture
async def stranger(
    sqlite_config: Configuration, started_database: Database, tenant_id: str
) -> AsyncIterator[httpx.AsyncClient]:
    """No session and no default tenant: somebody arriving from outside."""
    app = create_app(sqlite_config, database=started_database)
    async with (
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http,
        app.router.lifespan_context(app),
    ):
        yield http


class TestThePublicPages:
    async def test_the_landing_page_offers_sign_in_to_a_stranger(self, stranger: Any) -> None:
        response = await stranger.get("/")
        assert response.status_code == 200
        assert 'href="/sign-in"' in response.text
        assert 'href="/help"' in response.text

    async def test_a_signed_in_person_goes_straight_to_the_estate(
        self, stranger: Any, started_database: Database, tenant_id: str
    ) -> None:
        await _person(started_database, tenant_id, "alice", "admin")
        await _sign_in(stranger, "alice")
        response = await stranger.get("/")
        assert response.status_code == 307
        assert response.headers["location"] == "/estate"

    async def test_the_landing_numbers_are_counted_not_typed(self, stranger: Any) -> None:
        text = (await stranger.get("/")).text
        assert f'<span class="lp-num">{len(THEMES)}</span>' in text
        assert f'<span class="lp-num">{len(help_catalog.BY_SLUG)}</span>' in text

    async def test_about_and_help_need_no_session(self, stranger: Any) -> None:
        for path in ("/about", "/help"):
            response = await stranger.get(path)
            assert response.status_code == 200, path

    async def test_every_help_topic_renders_from_its_source(self, stranger: Any) -> None:
        """Each entry names a file; a renamed document must fail here, not 404
        for a reader."""
        for slug, entry in help_catalog.BY_SLUG.items():
            assert entry.source().is_file(), f"{slug}: {entry.source()} is missing"
            response = await stranger.get(f"/help/{slug}")
            assert response.status_code == 200, slug
            assert "<h1" in response.text or "<h2" in response.text, slug

    async def test_an_unknown_topic_is_not_found(self, stranger: Any) -> None:
        assert (await stranger.get("/help/no-such-topic")).status_code == 404

    async def test_case_studies_have_a_card_each_and_a_page_each(self, stranger: Any) -> None:
        from prama.web import case_studies

        studies = case_studies.catalog()
        # Anti-vacuity: the catalogue is parsed from the index, and a table the
        # pattern stopped matching would otherwise list nothing and pass.
        assert len(studies) >= 8
        on_disk = {p.name for p in case_studies.ROOT.glob("0*") if (p / "README.md").is_file()}
        assert {s["slug"] for s in studies} == on_disk
        listing = await stranger.get("/help/case-studies")
        assert listing.status_code == 200
        index = await stranger.get("/help")
        for study in studies:
            href = f'href="/help/case-studies/{study["slug"]}"'
            assert href in listing.text and href in index.text, study["slug"]
            page = await stranger.get(f"/help/case-studies/{study['slug']}")
            assert page.status_code == 200, study["slug"]
            # The README itself, rendered: its sections and its tables.
            assert "<h2" in page.text and "<table" in page.text, study["slug"]
        assert (await stranger.get("/help/case-studies/09-no-such-study")).status_code == 404
        assert (await stranger.get("/help/case-studies/_common")).status_code == 404

    async def test_help_assets_serve_the_corpus_images_and_nothing_else(
        self, stranger: Any
    ) -> None:
        assert (await stranger.get("/help/assets/prama-mark.svg")).status_code == 200
        for bad in ("..%2FLICENSE", "preview.html", ".hidden.svg", "nope.svg"):
            assert (await stranger.get(f"/help/assets/{bad}")).status_code == 404, bad

    async def test_corpus_links_are_rewritten_to_help_pages(self) -> None:
        html = help_catalog._relink('<a href="07-rule-language-spec.md#x">x</a>')
        assert html == '<a href="/help/pql#x">x</a>'
        untouched = '<a href="not-in-the-catalogue.md">y</a>'
        assert help_catalog._relink(untouched) == untouched

    async def test_every_page_carries_the_proprietary_notice(self, stranger: Any) -> None:
        for path in ("/", "/about", "/help", "/legal", "/sign-in"):
            assert "All rights reserved" in (await stranger.get(path)).text, path


class TestTheThemeMenu:
    async def test_it_offers_every_theme_including_mayas_four(self, ui: Any) -> None:
        text = (await ui.get("/estate")).text
        offered = set(re.findall(r'data-theme-choice="([\w-]+)"', text))
        assert offered == {t.name for t in THEMES}
        assert {"maya-crimson", "maya-dark", "maya-blue", "maya-green"} <= offered


class TestMyAccount:
    async def test_it_needs_a_signed_in_person(self, ui: Any) -> None:
        # The single-tenant fallback has a tenant but no account to show.
        response = await ui.get("/account")
        assert response.status_code == 303
        assert response.headers["location"] == "/sign-in"

    async def test_it_shows_the_account(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        await _person(started_database, tenant_id, "alice", "steward")
        await _sign_in(ui, "alice")
        response = await ui.get("/account")
        assert response.status_code == 200
        assert "steward" in response.text

    async def test_changing_the_password_keeps_this_session_and_needs_the_old_one(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        await _person(started_database, tenant_id, "alice", "steward")
        await _sign_in(ui, "alice")
        wrong = await ui.post(
            "/account/password",
            data={"current": "not it at all", "new": "a" * 20, "confirm": "a" * 20},
        )
        assert wrong.status_code == 400
        ok = await ui.post(
            "/account/password",
            data={"current": PASSWORD, "new": "b" * 20, "confirm": "b" * 20},
        )
        assert ok.status_code == 303
        assert (await ui.get("/account")).status_code == 200
        await ui.post("/sign-out")
        await _sign_in(ui, "alice", "b" * 20)


class TestMyApiKeys:
    async def test_the_plaintext_is_shown_once_and_authenticates(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        await _person(started_database, tenant_id, "alice", "auditor")
        await _sign_in(ui, "alice")
        created = await ui.post(
            "/account/keys", data={"name": "nightly", "scopes": ["declaration:read"], "days": "30"}
        )
        assert created.status_code == 200
        match = re.search(r"<code>(pk_[^<]+)</code>", created.text)
        assert match, created.text
        plaintext = match.group(1)
        assert plaintext not in (await ui.get("/account/keys")).text
        api = await ui.get("/api/v1/concepts", headers={"Authorization": f"Bearer {plaintext}"})
        assert api.status_code == 200, api.text
        forged = await ui.get("/api/v1/concepts", headers={"Authorization": "Bearer pk_live_x"})
        assert forged.status_code == 401

    async def test_a_key_cannot_exceed_its_holder(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        await _person(started_database, tenant_id, "alice", "auditor")
        await _sign_in(ui, "alice")
        await ui.post(
            "/account/keys", data={"name": "grab", "scopes": ["control:approve"], "days": "30"}
        )
        async with started_database.unit_of_work() as uow:
            keys = await uow.api_keys.list_for_tenant(tenant_id)
        assert keys == []

    async def test_somebody_elses_key_cannot_be_revoked(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        await _person(started_database, tenant_id, "bob", "auditor")
        await _sign_in(ui, "bob")
        await ui.post("/account/keys", data={"name": "b", "scopes": ["report:read"], "days": "5"})
        await ui.post("/sign-out")
        async with started_database.unit_of_work() as uow:
            (bobs,) = await uow.api_keys.list_for_tenant(tenant_id)
        await _person(started_database, tenant_id, "alice", "auditor")
        await _sign_in(ui, "alice")
        response = await ui.post(f"/account/keys/{bobs.id}/revoke")
        assert response.status_code == 404
        async with started_database.unit_of_work() as uow:
            assert (await uow.api_keys.get(str(bobs.id))).revoked_at is None


class TestAdministration:
    async def test_it_refuses_a_non_admin(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        await _person(started_database, tenant_id, "sam", "steward")
        await _sign_in(ui, "sam")
        assert (await ui.get("/admin/users")).status_code == 403
        assert (await ui.get("/admin/keys")).status_code == 403

    async def test_an_admin_creates_disables_and_cannot_disable_themself(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        me = await _person(started_database, tenant_id, "root", "admin")
        await _sign_in(ui, "root")
        assert (await ui.get("/admin/users")).status_code == 200
        created = await ui.post(
            "/admin/users",
            data={"username": "carol", "password": PASSWORD, "roles": ["steward"]},
        )
        assert created.status_code == 303
        async with started_database.unit_of_work() as uow:
            carol = await uow.principals.by_username(tenant_id, "carol")
            assert carol is not None
            assert [r.name for r in await uow.principals.roles_of(str(carol.id))] == ["steward"]
            carol_id = str(carol.id)
        await ui.post(f"/admin/users/{carol_id}/status", data={"status": "disabled"})
        await ui.post(f"/admin/users/{me}/status", data={"status": "disabled"})
        async with started_database.unit_of_work() as uow:
            assert (await uow.principals.get(carol_id)).status == "disabled"
            assert (await uow.principals.get(me)).status == "active"


class TestAKeyIsNoMoreUsableThanItsHolder:
    async def test_disabling_a_person_stops_their_keys(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        await _person(started_database, tenant_id, "dana", "auditor")
        await _sign_in(ui, "dana")
        created = await ui.post(
            "/account/keys", data={"name": "etl", "scopes": ["declaration:read"], "days": "30"}
        )
        match = re.search(r"<code>(pk_[^<]+)</code>", created.text)
        assert match
        headers = {"Authorization": f"Bearer {match.group(1)}"}
        probe = "/api/v1/concepts"
        before = await ui.get(probe, headers=headers)
        assert before.status_code == 200, before.text  # the control: the key works
        async with started_database.unit_of_work() as uow:
            dana = await uow.principals.by_username(tenant_id, "dana")
            assert dana is not None
            dana.status = "disabled"
        after = await ui.get(probe, headers=headers)
        assert after.status_code == 401, after.text

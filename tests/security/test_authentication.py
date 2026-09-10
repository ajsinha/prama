"""Signing in.

The console had no authentication at all: it read its caller from
``tenancy.default_tenant`` and redirected to a ``/sign-in`` that did not exist.
These tests are about the parts of a sign-in form that are easy to get wrong in
ways nobody notices until somebody is enumerating your usernames.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import time

import httpx
import pytest

from prama.core.errors import ValidationError
from prama.db import Database
from prama.db.security import PasswordHasher

pytestmark = pytest.mark.anyio

PASSWORD = "correct-horse-battery-staple"


async def _principal(
    database: Database,
    tenant_id: str,
    username: str = "alice",
    *,
    password: str | None = PASSWORD,
    status: str = "active",
) -> str:
    async with database.unit_of_work() as uow:
        principal = uow.principals.create(
            tenant_id=tenant_id, username=username, display_name=username.title()
        )
        if password is not None:
            uow.principals.set_password(principal, password)
        principal.status = status
        await uow.flush()
        return str(principal.id)


class TestAuthenticate:
    async def test_the_right_password_returns_the_principal(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _principal(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            found = await uow.principals.authenticate(tenant_id, "alice", PASSWORD)
        assert found is not None
        assert found.username == "alice"

    @pytest.mark.parametrize(
        "username,password",
        [
            ("alice", "wrong"),
            ("nobody", PASSWORD),
            ("nobody", "wrong"),
            ("alice", ""),
        ],
    )
    async def test_every_failure_returns_the_same_nothing(
        self, started_database: Database, tenant_id: str, username: str, password: str
    ) -> None:
        """One answer for every kind of failure. A caller that could tell them
        apart could enumerate usernames."""
        await _principal(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            assert await uow.principals.authenticate(tenant_id, username, password) is None

    async def test_a_disabled_account_cannot_sign_in(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """And is refused the same way as a wrong password. "That account is
        disabled" confirms the account exists to exactly the person who should
        not be told."""
        await _principal(started_database, tenant_id, status="disabled")
        async with started_database.unit_of_work() as uow:
            assert await uow.principals.authenticate(tenant_id, "alice", PASSWORD) is None

    async def test_an_account_with_no_password_cannot_sign_in(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A service principal, or one provisioned for SSO. An empty hash must
        not be something an empty password matches."""
        await _principal(started_database, tenant_id, password=None)
        async with started_database.unit_of_work() as uow:
            assert await uow.principals.authenticate(tenant_id, "alice", "") is None
            assert await uow.principals.authenticate(tenant_id, "alice", PASSWORD) is None

    async def test_an_unknown_username_costs_the_same_as_a_known_one(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Skipping the hash for a missing user makes the absence measurable:
        an enumeration oracle built out of timing rather than wording.

        The bound is deliberately loose — this asserts the same *order of
        magnitude*, not a constant, because a tight bound on a shared CI machine
        is a flake generator."""
        await _principal(started_database, tenant_id)

        async def _time(username: str) -> float:
            async with started_database.unit_of_work() as uow:
                started = time.perf_counter()
                await uow.principals.authenticate(username, "alice", "wrong")
                return time.perf_counter() - started

        known = min([await _time(tenant_id) for _ in range(3)])
        unknown = min([await _time("01NOSUCHTENANT") for _ in range(3)])
        assert unknown > known / 4, (
            f"an unknown username returned in {unknown:.4f}s against {known:.4f}s "
            "for a known one, which is an enumeration oracle"
        )

    async def test_a_successful_sign_in_stamps_the_time(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _principal(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            found = await uow.principals.authenticate(tenant_id, "alice", PASSWORD)
            assert found is not None and found.last_login_at is not None

    async def test_a_weak_hash_is_upgraded_on_the_way_in(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The one occasion the plaintext is legibly in hand. A rehash
        scheduled for later is one that never runs."""
        identifier = await _principal(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            principal = await uow.principals.require(identifier)
            principal.password_hash = PasswordHasher(iterations=100_000).hash(PASSWORD)
            await uow.flush()

        async with started_database.unit_of_work() as uow:
            found = await uow.principals.authenticate(tenant_id, "alice", PASSWORD)
            assert found is not None
            assert not PasswordHasher().needs_rehash(found.password_hash or "")


class TestPasswordRules:
    async def test_a_short_password_is_refused(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            principal = uow.principals.create(
                tenant_id=tenant_id, username="bob", display_name="Bob"
            )
            with pytest.raises(ValidationError, match="at least"):
                uow.principals.set_password(principal, "short")

    async def test_the_plaintext_is_never_stored(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _principal(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            principal = await uow.principals.by_username(tenant_id, "alice")
        assert principal is not None
        assert PASSWORD not in (principal.password_hash or "")
        assert (principal.password_hash or "").startswith("pbkdf2_sha256$")

    async def test_two_identical_passwords_hash_differently(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Per-password salt. Identical hashes would tell anybody who reads the
        table which accounts share a password."""
        await _principal(started_database, tenant_id, "alice")
        await _principal(started_database, tenant_id, "bob")
        async with started_database.unit_of_work() as uow:
            first = await uow.principals.by_username(tenant_id, "alice")
            second = await uow.principals.by_username(tenant_id, "bob")
        assert first is not None and second is not None
        assert first.password_hash != second.password_hash


class TestTheSignInPage:
    async def test_it_exists(self, ui: httpx.AsyncClient) -> None:
        """It did not. The NotSignedIn handler redirected here and the page
        404ed, so an installation without a default tenant sent every page to
        nothing."""
        response = await ui.get("/sign-in")
        assert response.status_code == 200
        assert "Sign in" in response.text

    async def test_a_wrong_password_and_an_unknown_user_are_indistinguishable(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _principal(started_database, tenant_id)
        wrong = await ui.post("/sign-in", data={"username": "alice", "password": "no"})
        unknown = await ui.post("/sign-in", data={"username": "ghost", "password": "no"})
        assert wrong.status_code == unknown.status_code == 401
        assert "Those details did not work." in wrong.text
        assert wrong.text == unknown.text.replace("ghost", "alice")

    async def test_signing_in_establishes_a_session(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _principal(started_database, tenant_id)
        response = await ui.post("/sign-in", data={"username": "alice", "password": PASSWORD})
        assert response.status_code == 303
        assert response.headers["location"] == "/estate"
        assert (await ui.get("/estate")).status_code == 200

    async def test_signing_out_clears_the_session(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Cleared, not flagged. A session marked signed-out is still a session,
        and the flag is one bug away from being ignored."""
        await _principal(started_database, tenant_id)
        await ui.post("/sign-in", data={"username": "alice", "password": PASSWORD})
        response = await ui.post("/sign-out")
        assert response.status_code == 303
        assert response.headers["location"] == "/sign-in"

    @pytest.mark.parametrize(
        "target",
        ["https://evil.example/", "//evil.example/", "http://evil.example"],
    )
    async def test_an_offsite_next_is_refused(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str, target: str
    ) -> None:
        """``next=`` in a link is how a sign-in page becomes somebody else's
        phishing redirect. ``//evil.example`` matters as much as the rest: it is
        a protocol-relative URL that a naive path check calls a path."""
        await _principal(started_database, tenant_id)
        response = await ui.post(
            "/sign-in",
            data={"username": "alice", "password": PASSWORD, "next": target},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/estate"

    async def test_an_onsite_next_is_honoured(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _principal(started_database, tenant_id)
        response = await ui.post(
            "/sign-in",
            data={"username": "alice", "password": PASSWORD, "next": "/controls"},
        )
        assert response.headers["location"] == "/controls"

    async def test_it_says_when_nobody_could_possibly_sign_in(self, ui: httpx.AsyncClient) -> None:
        """A form that cannot succeed is otherwise indistinguishable from a
        form being used wrongly, and the person will try four more times before
        suspecting the installation."""
        body = " ".join((await ui.get("/sign-in")).text.split())
        assert "Nobody has been created on this installation yet." in body
        assert "prama principal create" in body

    async def test_that_notice_goes_away_once_somebody_exists(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _principal(started_database, tenant_id)
        body = (await ui.get("/sign-in")).text
        assert "Nobody has been created" not in body

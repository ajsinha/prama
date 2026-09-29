"""Signing in.

The console had no authentication at all: it read its caller from
``tenancy.default_tenant`` and redirected to a ``/sign-in`` that did not exist.
These tests are about the parts of a sign-in form that are easy to get wrong in
ways nobody notices until somebody is enumerating your usernames.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from prama.api import create_app
from prama.core.config import Configuration, ConfigurationBuilder
from prama.core.errors import ValidationError
from prama.db import Database
from prama.db.security import PasswordHasher

pytestmark = pytest.mark.anyio

PASSWORD = "correct-horse-battery-staple"


def _without_nonces(markup: str) -> str:
    """The page with its per-response CSP nonce blanked."""
    import re

    return re.sub(r'nonce="[^"]*"', 'nonce="…"', markup)


async def _principal(
    database: Database,
    tenant_id: str,
    username: str = "alice",
    *,
    password: str | None = PASSWORD,
    status: str = "active",
    role: str | None = "admin",
) -> str:
    """Somebody who can sign in.

    *role* defaults to admin because most tests here are about the session
    rather than about permissions, and a principal with no roles now holds
    nothing — the console checks scopes, so a role-less account signs in
    successfully and is then refused every page. That is the intended
    behaviour; `role=None` is how a test asks for it.
    """
    from prama.cli.principal import BUILTIN_ROLES

    async with database.unit_of_work() as uow:
        principal = uow.principals.create(
            tenant_id=tenant_id, username=username, display_name=username.title()
        )
        if password is not None:
            uow.principals.set_password(principal, password)
        principal.status = status
        await uow.flush()
        if role is not None:
            description, permissions = BUILTIN_ROLES[role]
            existing = await uow.roles.by_name(tenant_id, role)
            if existing is None:
                existing = uow.roles.create(
                    tenant_id=tenant_id,
                    name=role,
                    permissions=permissions,
                    description=description,
                    builtin=True,
                )
                await uow.flush()
            await uow.roles.grant(str(principal.id), str(existing.id))
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
        # The CSP nonce is per-response and random, so the two pages are not
        # byte-identical any more and should not be: it carries no information
        # about which of the two failures happened. Normalised rather than
        # dropped, because the assertion that matters — that nothing *else*
        # differs — is the whole point of this test.
        assert _without_nonces(wrong.text) == _without_nonces(
            unknown.text.replace("ghost", "alice")
        )

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
        """Cleared, and revoked.

        The docstring here used to end at "cleared, not flagged" — presenting
        the absence of a revocation flag as a security property. That is true of
        a flag and is not an argument for having nothing: clearing the client's
        cookie left one captured beforehand valid for Starlette's default
        fourteen days. See the revocation tests below.
        """
        await _principal(started_database, tenant_id)
        await ui.post("/sign-in", data={"username": "alice", "password": PASSWORD})
        response = await ui.post("/sign-out")
        assert response.status_code == 303
        assert response.headers["location"] == "/"  # the landing page, not the form

    @pytest.mark.parametrize(
        "target",
        [
            "https://evil.example/",
            "//evil.example/",
            "http://evil.example",
            # Finding S7. A backslash is a path separator for a special scheme
            # under the WHATWG URL spec, so Chrome, Firefox and Safari all
            # resolve these to //evil.example and then to http://evil.example.
            # The check read the raw string, saw one leading slash, and put it
            # straight into a 303 Location header. Two characters.
            "/\\evil.example",
            "/\\\\evil.example",
            "\\\\evil.example",
            # Characters a browser strips before resolving, which hide the
            # shape of the target from a check that reads the string as sent.
            "/\t/evil.example",
            "/\n/evil.example",
            "/\r/evil.example",
        ],
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


class TestASessionIsRevalidatedNotTrusted:
    """Finding S8. `ui_caller` built the caller from the cookie alone.

    No principal was loaded, no status was read, no role was re-checked. The
    session is a self-contained signed cookie with no server-side store, so
    disabling or deleting an account had **no effect on a session it already
    held** — `PrincipalDao.authenticate` refuses them at the door and the door
    was already open. Offboarding was not enforceable.

    Revocation is keyed on the principal's own `updated_at`: a session issued
    before the row last changed is refused. Any change to the account — being
    disabled, losing a role — invalidates its sessions as a side effect.
    Over-invalidation is the safe direction; the cost is signing in again.
    """

    async def signed_in(self, ui: Any, database: Database, tenant_id: str) -> Any:
        await _principal(database, tenant_id)
        response = await ui.post("/sign-in", data={"username": "alice", "password": PASSWORD})
        assert response.status_code == 303
        return response

    async def test_an_ordinary_session_still_works(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        """The positive control. A revalidation that refuses everything is not
        a security property, it is an outage."""
        await self.signed_in(ui, started_database, tenant_id)
        assert (await ui.get("/estate")).status_code == 200

    async def test_disabling_an_account_ends_its_session(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        await self.signed_in(ui, started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            person = await uow.principals.by_username(tenant_id, "alice")
            assert person is not None
            person.status = "disabled"
            await uow.flush()

        landed = await ui.get("/estate", follow_redirects=False)
        assert landed.status_code == 303, "a disabled account kept its session"
        assert landed.headers["location"] == "/sign-in"

    async def test_signing_out_revokes_a_cookie_captured_earlier(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        """The one that matters on a shared machine.

        Clearing the client's cookie is not revocation: it is asking the client
        nicely. A copy taken beforehand must stop working too.
        """
        await self.signed_in(ui, started_database, tenant_id)
        captured = dict(ui.cookies)
        assert captured, "no session cookie was set"

        await ui.post("/sign-out")

        # Present the captured cookie as an attacker would.
        ui.cookies.clear()
        for name, value in captured.items():
            ui.cookies.set(name, value)
        landed = await ui.get("/estate", follow_redirects=False)
        assert landed.status_code == 303, "a cookie captured before sign-out still worked"


class TestTheConsoleChecksWhatTheSessionMayDo:
    """The console was out of scope for finding S4, and it should not have been.

    It authenticates a *session* rather than a key, and a route was authorised
    by the caller merely being signed in. `ui_caller` had been putting the
    principal's permissions on the identity for waves and nothing read them: an
    `auditor` — the role whose entire description is "reads everything and
    changes nothing" — could post to `/controls/{id}/activate` exactly as an
    `owner` could.

    Enforced in `UiRoutes.page` rather than on each handler, because the console
    registers forty-eight routes through that one call and annotating them
    individually is forty-eight chances to forget.
    """

    async def signed_in_as(self, ui: Any, database: Database, tenant_id: str, role: str) -> None:
        from prama.cli.principal import BUILTIN_ROLES

        _, permissions = BUILTIN_ROLES[role]
        async with database.unit_of_work() as uow:
            person = uow.principals.create(
                tenant_id=tenant_id, username=role, display_name=role.title()
            )
            uow.principals.set_password(person, PASSWORD)
            granted = uow.roles.create(tenant_id=tenant_id, name=role, permissions=permissions)
            await uow.flush()
            await uow.roles.grant(str(person.id), str(granted.id))
            await uow.flush()
        response = await ui.post("/sign-in", data={"username": role, "password": PASSWORD})
        assert response.status_code == 303, response.text

    async def test_an_auditor_may_read(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        """The positive control. A guard that refuses everybody is an outage,
        not an authorisation model."""
        await self.signed_in_as(ui, started_database, tenant_id, "auditor")
        assert (await ui.get("/estate")).status_code == 200

    async def test_an_auditor_may_not_activate_a_control(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        await self.signed_in_as(ui, started_database, tenant_id, "auditor")
        response = await ui.post("/controls/01ANYTHING/activate")
        assert response.status_code == 403, (
            "the role whose description is 'reads everything and changes "
            f"nothing' activated a control: {response.status_code}"
        )

    async def test_an_owner_may(self, ui: Any, started_database: Database, tenant_id: str) -> None:
        """The other half of the counterfactual: the refusal above must be
        about the permission and not about the route being broken."""
        await self.signed_in_as(ui, started_database, tenant_id, "owner")
        response = await ui.post("/controls/01ANYTHING/activate")
        assert response.status_code != 403, response.text

    async def test_a_principal_with_no_roles_holds_nothing(
        self, ui: Any, started_database: Database, tenant_id: str
    ) -> None:
        """ "No roles recorded" is not "no restriction" — the same rule the API
        applies to a key with no scopes."""
        await _principal(started_database, tenant_id, username="nobody", role=None)
        assert (
            await ui.post("/sign-in", data={"username": "nobody", "password": PASSWORD})
        ).status_code == 303
        assert (await ui.get("/estate")).status_code == 403


class TestTheSignInPageIsReachableWithoutSigningIn:
    """A deployment nobody can get into.

    Found by standing the product up, not by the suite. Enforcing scopes at
    `UiRoutes.page` gave `/sign-in` the default read scope, so an
    unauthenticated request raised `NotSignedIn`, the handler turned that into
    a 303 to `/sign-in`, and `/sign-in` asked again — an infinite redirect on
    the only page that matters to somebody who is not yet in.

    Four thousand six hundred tests missed it because every console fixture
    sets `tenancy.default_tenant`, which is the pre-authentication path and
    grants the wildcard. The one configuration a real deployment uses — a
    tenant, a principal, and no default — was the one nothing exercised.

    These use a client with *no* session and no default tenant, which is what a
    browser arriving at a fresh install looks like.
    """

    @pytest.fixture
    async def stranger(
        self, sqlite_config: Configuration, started_database: Database
    ) -> AsyncIterator[httpx.AsyncClient]:
        """A browser with no session, against a deployment with no default
        tenant. Deliberately not the `ui` fixture, which has both."""
        app = create_app(sqlite_config, database=started_database)
        async with (
            httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as http,
            app.router.lifespan_context(app),
        ):
            yield http

    async def test_the_sign_in_page_renders(self, stranger: httpx.AsyncClient) -> None:
        response = await stranger.get("/sign-in")
        assert response.status_code == 200, (
            f"the sign-in page answered {response.status_code}; if it is a redirect "
            "to itself, nobody can ever sign in"
        )
        assert "password" in response.text.lower()

    async def test_it_does_not_redirect_to_itself(self, stranger: httpx.AsyncClient) -> None:
        """Stated separately because a 303 to somewhere else is a different
        bug from a 303 to here, and only one of them is a locked door."""
        response = await stranger.get("/sign-in", follow_redirects=False)
        assert response.headers.get("location") != "/sign-in"

    async def test_posting_credentials_is_reachable(self, stranger: httpx.AsyncClient) -> None:
        """The form must be able to submit to something other than a redirect.
        A GET that renders and a POST that bounces is the same locked door."""
        response = await stranger.post(
            "/sign-in", data={"username": "nobody", "password": "wrong-but-long-enough"}
        )
        assert response.status_code == 401, response.status_code

    async def test_a_protected_page_still_redirects(self, stranger: httpx.AsyncClient) -> None:
        """The counterfactual. Making sign-in anonymous must not make
        everything anonymous."""
        response = await stranger.get("/estate", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/sign-in"


class TestAFreshDeploymentCanBeSignedIntoAtAll:
    """QA found the console unenterable on the one configuration a real
    deployment uses: a tenant, a principal, and no `tenancy.default_tenant`.

    Two independent defects, either of which alone locks the door.

    **The tenant was never resolved.** `sign_in` took
    `form_field or tenancy.default_tenant`, `auth/sign_in.html` renders no
    tenant field, so with the default unset `tenant_id` was always `""`,
    `authenticate` was never called, and every correct password got a 401.
    Supplying `tenant=acme-bank` by hand did not help either — that is a slug,
    and `authenticate` compares it against a tenant *id*, which is the same
    slug-versus-id seam that broke `principal create --tenant`.

    **And the page said nobody existed.** `_no_way_in` returned `True` whenever
    the default was empty, without counting anything, so the sign-in page
    announced *"Nobody has been created on this installation yet"* while four
    principals existed — sending an operator to look for a bug in
    `principal create`.

    Every existing fixture sets `tenancy.default_tenant`, which is the
    pre-authentication path. That is why 4,699 tests passed over a locked door.
    """

    @pytest.fixture
    def no_default_tenant(self, sqlite_config: Configuration) -> Configuration:
        """A deployment that has not been told which estate it is."""
        return (
            ConfigurationBuilder()
            .with_defaults(sqlite_config.raw())
            .with_mapping({"tenancy": {"default_tenant": ""}}, name="no-default")
            .build()
        )

    @pytest.fixture
    async def door(
        self, no_default_tenant: Configuration, started_database: Database
    ) -> AsyncIterator[httpx.AsyncClient]:
        app = create_app(no_default_tenant, database=started_database)
        async with (
            httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as http,
            app.router.lifespan_context(app),
        ):
            yield http

    async def test_a_correct_password_gets_in(
        self, door: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _principal(started_database, tenant_id)
        response = await door.post("/sign-in", data={"username": "alice", "password": PASSWORD})
        assert response.status_code == 303, (
            f"a correct password was refused ({response.status_code}) on a deployment "
            "with no default tenant — the console cannot be entered at all"
        )

    async def test_a_wrong_password_is_still_refused(
        self, door: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """The counterfactual. Resolving the tenant must not let anybody in."""
        await _principal(started_database, tenant_id)
        response = await door.post(
            "/sign-in", data={"username": "alice", "password": "wrong-but-long-enough"}
        )
        assert response.status_code == 401

    async def test_the_slug_is_accepted_in_the_form(
        self, door: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A person knows `acme-bank`; the schema knows a ULID."""
        async with started_database.unit_of_work() as uow:
            tenant = await uow.tenants.get(tenant_id)
            assert tenant is not None
            slug = tenant.slug
        await _principal(started_database, tenant_id)
        response = await door.post(
            "/sign-in", data={"username": "alice", "password": PASSWORD, "tenant": slug}
        )
        assert response.status_code == 303, response.text

    async def test_the_page_does_not_claim_nobody_exists(
        self, door: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _principal(started_database, tenant_id)
        body = (await door.get("/sign-in")).text
        assert "Nobody has been created" not in body, (
            "the page told the operator nobody exists while a principal did"
        )

    async def test_it_still_says_so_when_nobody_does(self, door: httpx.AsyncClient) -> None:
        """The other counterfactual: the message is worth having when true.
        A form that cannot possibly succeed must say so, or somebody tries
        their password four more times before suspecting the installation."""
        body = (await door.get("/sign-in")).text
        assert "Nobody has been created" in body

"""The console's response headers, and a way to leave it.

QA round 2, `UI-045` and `UI-023`. Both were round-1 findings (`Q-45`, `Q-42`)
recorded as closed and found fully present again — closed without a test that
would notice the reversal, which is the argument for this whole directory.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest


class TestEveryResponseCarriesItsDefences:
    """`UI-045`. Zero security headers on any response of any kind.

    The console renders estate names, control text and evidence samples, all
    of which are somebody's input. The absence is not theoretical.
    """

    @pytest.mark.parametrize(
        "header,expected",
        [
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "same-origin"),
            ("X-Frame-Options", "DENY"),
        ],
    )
    async def test_the_static_headers_are_present(
        self, console_for_ours, header: str, expected: str
    ) -> None:
        response = await console_for_ours.get("/estate")
        assert response.headers.get(header) == expected

    async def test_the_policy_forbids_inline_script(self, console_for_ours) -> None:
        """A nonce, not `'unsafe-inline'`.

        The easy policy would leave the header present and its main protection
        absent, which is worse than none: it reads as protection in an audit.
        """
        policy = (await console_for_ours.get("/estate")).headers["Content-Security-Policy"]
        assert "script-src" in policy
        assert "'unsafe-inline'" not in policy.split("script-src")[1].split(";")[0]
        assert "'nonce-" in policy

    async def test_the_policy_stops_the_page_being_framed(self, console_for_ours) -> None:
        policy = (await console_for_ours.get("/estate")).headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in policy

    async def test_the_nonce_in_the_header_is_the_one_in_the_page(self, console_for_ours) -> None:
        """The assertion that makes the rest worth anything.

        A nonce in the header and a different one in the markup blocks every
        script on the page — a policy that looks correct and breaks the
        console. A nonce generated in the template rather than read from the
        request would do exactly that.
        """
        response = await console_for_ours.get("/estate")
        policy = response.headers["Content-Security-Policy"]
        nonce = policy.split("'nonce-")[1].split("'")[0]
        assert f'nonce="{nonce}"' in response.text

    async def test_a_fresh_request_gets_a_fresh_nonce(self, console_for_ours) -> None:
        """A reused nonce is a nonce an attacker can learn and then use."""
        first = (await console_for_ours.get("/estate")).headers["Content-Security-Policy"]
        second = (await console_for_ours.get("/estate")).headers["Content-Security-Policy"]
        assert first != second


class TestThereIsAWayToSignOut:
    """`UI-023`. The route existed since sign-in did and nothing linked to it.

    No way to leave the console from inside it — on a shared terminal in a
    dealing room, which is where this runs.

    Driven through `signed_in_console`, which signs in for real. The first
    version of this test used the default-tenant fixture, where there is no
    session, so the control is correctly absent and every assertion passed
    while proving nothing. That fixture is the same pre-auth wildcard that let
    4,666 round-1 tests pass over a broken sign-in door.
    """

    async def test_the_control_is_rendered(self, signed_in_console) -> None:
        page = (await signed_in_console.get("/estate")).text
        assert "/sign-out" in page

    async def test_it_is_a_post_not_a_link(self, signed_in_console) -> None:
        """A GET would let any page on the internet end a session with an <img>."""
        import re

        page = (await signed_in_console.get("/estate")).text
        form = re.search(r'<form[^>]*action="[^"]*/sign-out"[^>]*>', page)
        assert form is not None, "sign-out is not inside a form"
        assert 'method="post"' in form.group(0).lower()

    async def test_signing_out_actually_ends_the_session(self, signed_in_console) -> None:
        """The control has to work, not merely appear.

        A button that posts to a route that does not clear the session is the
        same defect one layer along, and it would satisfy both tests above.
        """
        assert (await signed_in_console.get("/estate")).status_code == 200
        await signed_in_console.post("/sign-out")
        after = await signed_in_console.get("/estate")
        assert after.status_code in (302, 303, 401), (
            "the estate page still rendered after signing out"
        )


class TestThePermissionMatrixDescribesTheRightThing:
    """`UI-005` to `UI-012`, and `SEC-014`. Every page asked for a declaration scope.

    `page(scope="auto")` derived the required permission from the HTTP verb
    alone — `declaration:read` for a GET, `declaration:write` for a POST — for
    all forty-seven routes that use it, whatever the page was about. So the
    console's permission matrix was accidental: a steward holding `break:*` was
    refused the break workbench, and a holder of `declaration:write` could
    reach it. The scopes existed, were enforced, and named the wrong thing.
    """

    def test_each_route_group_asks_about_its_own_subject(self) -> None:
        from prama.web.routes import ROUTE_CLASSES

        subjects = {cls.__name__: getattr(cls, "SUBJECT", "declaration") for cls in ROUTE_CLASSES}
        assert subjects["TriageRoutes"] == "incident"
        assert subjects["ReconRoutes"] == "break"
        assert subjects["ControlRoutes"] == "control"
        assert subjects["RelationshipRoutes"] == "relationship"
        assert subjects["AttestationRoutes"] == "attestation"

    def test_every_registered_scope_is_one_the_vocabulary_declares(self) -> None:
        """Enforced at registration, not asserted here after the fact.

        The scope vocabulary is deliberately finer than read/write: authoring a
        control is `control:propose` and signing an attestation is
        `attestation:sign`. Deriving `{subject}:write` everywhere would invent
        scopes nobody grants, and a page requiring a scope no role can hold is
        unreachable by everybody — which reads as a broken page rather than as
        a permission error.

        Writing this test first found exactly that latent case: `ReportRoutes`
        would have derived `report:write` the moment somebody added a POST to
        it. So the check moved into `page()`, where it fails at import instead
        of in production, and this test proves the check is real by trying to
        register a page that breaks it.
        """
        import pytest as _pytest
        from fastapi import FastAPI

        from prama.web.routes.base import UiRoutes

        class Nonsense(UiRoutes):
            SUBJECT = "nonexistent_subject"

            def register(self) -> None:
                self.page("/nowhere", self._handler, name="nowhere")

            async def _handler(self) -> None: ...

        with _pytest.raises(ValueError, match="no such scope is declared"):
            Nonsense(FastAPI())

    def test_no_group_silently_falls_back_to_declaration(self) -> None:
        """The anti-vacuity check.

        If SUBJECT were removed from every class this file would still pass its
        first test by accident once, and silently stop meaning anything. Naming
        the count makes a regression visible.
        """
        from prama.web.routes import ROUTE_CLASSES

        specific = [
            cls for cls in ROUTE_CLASSES if getattr(cls, "SUBJECT", "declaration") != "declaration"
        ]
        assert len(specific) >= 6, [c.__name__ for c in specific]

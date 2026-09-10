"""Signing in, and signing out.

Until now the console read its caller from ``tenancy.default_tenant`` and the
``NotSignedIn`` handler redirected to ``/sign-in``, which did not exist — so an
installation without that setting sent every page to a 404. This is that page,
and the session it establishes.

Three things this does that a sign-in form usually does not, each of them worth
the cost:

* **One message for every failure.** Unknown username, wrong password, disabled
  account, an account with no password at all: all of them are "those details
  did not work". A form that says "no such user" is a username oracle, and one
  that says "that account is disabled" confirms the account exists to whoever
  disabled it least deserves to know.
* **The session id changes on sign-in.** A session fixated before
  authentication is one an attacker can hand to somebody else and then ride;
  clearing the session and rebuilding it is what makes the pre-login identifier
  worthless.
* **Sign-out clears rather than marks.** A session flagged signed-out is still
  a session, and the flag is one bug away from being ignored.

**The single-tenant fallback survives, deliberately.** A deployment that sets
``tenancy.default_tenant`` still works without signing in, because that is how
every case study, every demo and every developer's first ten minutes run.
What changes is that it is now a fallback rather than the only path, and the
console says which one it is on.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Query, Request
from fastapi.responses import RedirectResponse

from prama.core.log import get_logger
from prama.web.deps import Uow
from prama.web.rendering import render
from prama.web.routes.base import UiRoutes

_log = get_logger(__name__)

#: Said for every failure, whatever the cause. See the module docstring.
REFUSED = "Those details did not work."

#: Where to go after signing in, when nothing else is remembered.
LANDING = "/estate"


class AuthRoutes(UiRoutes):
    """The sign-in page and the two things that change a session."""

    def register(self) -> None:
        self.page("/sign-in", self.sign_in_form, name="sign_in")
        self.page("/sign-in", self.sign_in, name="sign_in_post", methods=["POST"])
        self.page("/sign-out", self.sign_out, name="sign_out", methods=["POST"])

    async def sign_in_form(
        self,
        request: Request,
        uow: Uow,
        # Aliased, because the query parameter is called "next" by web
        # convention and `next` is a Python builtin.
        next_url: Annotated[str, Query(alias="next")] = "",
    ) -> Any:
        config = request.app.state.config
        return render(
            request,
            "auth/sign_in.html",
            next=_safe_next(next_url),
            error="",
            username="",
            # Named on the page, because "why am I being asked to sign in when
            # the last person was not" is otherwise an unanswerable question.
            single_tenant=bool(config.get_str("tenancy.default_tenant", "")),
            no_principals=await _no_way_in(uow, request),
        )

    async def sign_in(
        self,
        request: Request,
        uow: Uow,
        username: Annotated[str, Form()] = "",
        password: Annotated[str, Form()] = "",
        next_url: Annotated[str, Form(alias="next")] = "",
        tenant: Annotated[str, Form()] = "",
    ) -> Any:
        config = request.app.state.config
        tenant_id = tenant.strip() or config.get_str("tenancy.default_tenant", "")
        principal = None
        if tenant_id:
            principal = await uow.principals.authenticate(tenant_id, username.strip(), password)

        if principal is None:
            # Logged with the username and never with the password, and the
            # response says nothing the request did not already contain.
            _log.info("sign-in refused for %r on tenant %r", username, tenant_id)
            return render(
                request,
                "auth/sign_in.html",
                next=_safe_next(next_url),
                error=REFUSED,
                username=username,
                single_tenant=bool(config.get_str("tenancy.default_tenant", "")),
                no_principals=await _no_way_in(uow, request),
                status_code=401,
            )

        # Cleared, not updated. A session established before authentication and
        # merely amended afterwards is one somebody could have fixed in advance.
        request.session.clear()
        request.session["tenant_id"] = principal.tenant_id
        request.session["principal_id"] = str(principal.id)
        request.session["username"] = principal.username
        request.session["display_name"] = principal.display_name
        request.session["scopes"] = sorted(
            permission for role in principal.roles for permission in role.permissions_json
        )
        _log.info("signed in %s on tenant %s", principal.username, principal.tenant_id)
        return RedirectResponse(url=_safe_next(next_url) or LANDING, status_code=303)

    async def sign_out(self, request: Request) -> Any:
        request.session.clear()
        return RedirectResponse(url="/sign-in", status_code=303)


def _safe_next(target: str) -> str:
    """A redirect target, or nothing.

    Only a path on this site. ``next=https://elsewhere/`` in a link is how a
    sign-in page becomes somebody else's phishing redirect, and the check is
    "starts with exactly one slash" rather than a URL parse — ``//evil.example``
    is a protocol-relative URL that a parser will happily call a path.
    """
    candidate = (target or "").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return ""
    return candidate


async def _no_way_in(uow: Any, request: Request) -> bool:
    """Whether anybody could sign in at all.

    Counted, not inferred from configuration. A form that cannot possibly
    succeed — because nobody has run ``prama principal create`` — is otherwise
    indistinguishable from a form being used wrongly, and the person in front of
    it will try their password four more times before suspecting the
    installation.
    """
    tenant = request.app.state.config.get_str("tenancy.default_tenant", "")
    if not tenant:
        return True
    return not await uow.principals.any_for(tenant)


__all__ = ["LANDING", "REFUSED", "AuthRoutes"]

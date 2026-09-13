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

from prama.core.clock import utc_now
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
        # `scope=None`, and this is the one place it is right. A page that
        # demands a permission before you can sign in is a page that redirects
        # you to itself, for ever: `ui_caller` raises NotSignedIn, the handler
        # turns that into a 303 to /sign-in, and /sign-in asks again. Nobody
        # can ever get in.
        self.page("/sign-in", self.sign_in_form, name="sign_in", scope=None)
        self.page("/sign-in", self.sign_in, name="sign_in_post", methods=["POST"], scope=None)
        # Signing out needs no permission either. A principal whose roles were
        # just removed holds nothing, and telling them they may not leave is
        # both absurd and a way to strand a session that ought to be revoked.
        self.page("/sign-out", self.sign_out, name="sign_out", methods=["POST"], scope=None)

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
        tenant_id = await _sign_in_tenant(uow, tenant, config)
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
        # When, so the session can be refused if the account changes underneath
        # it. Flushed first and read from the row rather than from the clock:
        # `authenticate` stamps `last_login_at`, which moves `updated_at`, and a
        # session stamped before that flush would be refused by the request
        # immediately after it. See prama.web.deps.ui_caller.
        await uow.flush()
        request.session["issued_at"] = (principal.updated_at or utc_now()).isoformat()
        _log.info("signed in %s on tenant %s", principal.username, principal.tenant_id)
        return RedirectResponse(url=_safe_next(next_url) or LANDING, status_code=303)

    async def sign_out(self, request: Request, uow: Uow) -> Any:
        """Clear the cookie, and invalidate every session this account holds.

        Clearing alone left a captured cookie usable for Starlette's default
        fourteen days — finding S8. Touching the principal moves its
        ``updated_at`` past the ``issued_at`` of every session already minted,
        which `ui_caller` refuses. It revokes the other browser the user forgot
        about too, which is what somebody clicking "sign out" on a shared
        machine actually means.
        """
        principal_id = request.session.get("principal_id")
        request.session.clear()
        if principal_id:
            principal = await uow.principals.get(principal_id)
            if principal is not None:
                principal.updated_at = utc_now()
                await uow.flush()
        return RedirectResponse(url="/sign-in", status_code=303)


#: Characters a browser removes from a URL before resolving it. Left in place,
#: they hide the shape of the target from a check that reads the raw string:
#: ``/\tevil.example`` is ``//evil.example`` by the time it reaches the network.
_URL_IGNORED = str.maketrans({"\t": None, "\n": None, "\r": None})


async def _sign_in_tenant(uow: Any, given: str, config: Any) -> str:
    """The estate this sign-in is against, or "" if it cannot be known.

    Three sources, in order, and the third is the one that was missing.

    The form field, resolved as a **slug or an id** — a person knows
    `acme-bank`, the schema knows a ULID, and passing the slug straight to
    `authenticate` compares it against a tenant id and refuses every password.

    Then `tenancy.default_tenant`, which is the single-tenant deployment.

    Then, if there is exactly **one** estate, that one. A single-estate install
    is the overwhelmingly common case, and requiring somebody to name the only
    tenant there is — in a field the form did not render — is how this console
    became unenterable: the form posted no tenant, the default was unset, and
    every correct password was answered 401 (QA finding, console).
    """
    for candidate in (given.strip(), str(config.get_str("tenancy.default_tenant", "")).strip()):
        if not candidate:
            continue
        if await uow.tenants.get(candidate) is not None:
            return candidate
        by_slug = await uow.tenants.by_slug(candidate)
        if by_slug is not None:
            return str(by_slug.id)
    only = await uow.tenants.list_active(limit=2)
    return str(only[0].id) if len(only) == 1 else ""


def _safe_next(target: str) -> str:
    r"""A redirect target, or nothing.

    Only a path on this site. ``next=https://elsewhere/`` in a link is how a
    sign-in page becomes somebody else's phishing redirect, and the check is
    "starts with exactly one slash" rather than a URL parse — ``//evil.example``
    is a protocol-relative URL that a parser will happily call a path.

    **The string is normalised the way a browser normalises it before the check
    runs**, which the original did not do and is finding S7. Under the WHATWG
    URL spec a backslash is a path separator for special schemes, so Chrome,
    Firefox and Safari all resolve ``/\evil.example`` to ``//evil.example`` and
    then to ``http://evil.example``. The check saw one leading slash and passed
    it through to a 303 ``Location`` header. The attack is two characters:

        https://prama.customer/sign-in?next=/\attacker.example/prama-sso

    The victim authenticates against the genuine host and is bounced to a page
    that looks like a continuation of the login flow. Checking the raw string
    against a rule the browser will not apply to it is the defect; anything that
    changes the target's meaning has to be applied here first.
    """
    candidate = (target or "").strip().translate(_URL_IGNORED)
    candidate = candidate.replace("\\", "/")
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
    tenant = await _sign_in_tenant(uow, "", request.app.state.config)
    if tenant:
        return not await uow.principals.any_for(tenant)
    # No tenant resolved, and that means one of two opposite things. No estates
    # at all is a fresh `db init` and nothing else: nobody can sign in, and
    # saying so is the whole point of this function. Several estates and no
    # default is the other case — this installation has principals and we
    # simply do not know which estate the person in front of us belongs to.
    # Claiming "nobody has been created" there is a lie, and it said exactly
    # that while four principals existed, sending an operator to look for a bug
    # in `principal create`.
    return not await uow.tenants.list_active(limit=1)


__all__ = ["LANDING", "REFUSED", "AuthRoutes"]

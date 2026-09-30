"""Every route that sees a caller says what that caller must be allowed to do.

Finding S4 was not that one route forgot a check; it was that the check did not
exist, while every surrounding artefact — the key record, the stored scope list,
`CallerIdentity.scopes` — read as though it did. The fix is only worth having if
the next route cannot quietly rejoin the old state, so the permission a route
needs is declared in its *signature* (`caller: Reader` / `caller: Writer`) and
this walks the routing table to check.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Iterator
from typing import Any, ClassVar

import pytest
from fastapi.routing import APIRoute

from prama.api import API_PREFIX, create_app
from prama.api.deps import get_caller
from prama.core.config import Configuration
from prama.security.scopes import SCOPES


@dataclasses.dataclass(frozen=True)
class Endpoint:
    """One route, with the path it is actually served at."""

    path: str
    methods: frozenset[str]
    route: APIRoute

    def __str__(self) -> str:
        return f"{sorted(self.methods)} {self.path}"


def walk(routes: Iterable[Any], prefix: str = "") -> Iterator[Endpoint]:
    """Every route, with its full path, however the app nests it.

    FastAPI does not copy an included router's routes onto the application: it
    wraps the router in an ``_IncludedRouter`` that keeps the original and the
    prefix separately. A scan over ``app.routes`` therefore sees the console —
    which registers with ``@app.get`` directly — and **none of the API**. The
    first version of this file did exactly that, found zero API routes, and
    every assertion below passed. A guard walking the wrong collection finds
    nothing wrong, which from the outside is indistinguishable from a guard
    that has nothing to find; the anti-vacuity test exists because of it.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield Endpoint(prefix + route.path, frozenset(route.methods or ()), route)
            continue
        original = getattr(route, "original_router", None)
        if original is not None:
            context = getattr(route, "include_context", None)
            yield from walk(original.routes, prefix + getattr(context, "prefix", ""))
            continue
        nested = getattr(route, "routes", None)
        if nested:
            yield from walk(nested, prefix + getattr(route, "prefix", ""))


@pytest.fixture
def endpoints(sqlite_config: Configuration) -> list[Endpoint]:
    """The HTTP API only.

    The console is mounted into the same app and is deliberately out of scope
    here: it authenticates a *session*, not an API key, and carries no scope
    list to check. That is a real gap, recorded as such in
    `docs/reviews/2026-09-11-adversarial-review.md` rather than papered over
    with an exemption — a console route is authorised today by being signed in,
    which is coarser than what the API now does.
    """
    app = create_app(sqlite_config)
    return [end for end in walk(app.routes) if end.path.startswith(API_PREFIX)]


def _reaches(route: APIRoute, predicate: Any) -> Any:
    pending: list[Any] = [route.dependant]
    while pending:
        dependant = pending.pop()
        found = predicate(dependant)
        if found is not None:
            return found
        pending.extend(dependant.dependencies)
    return None


def scope_of(end: Endpoint) -> str | None:
    """The scope this route requires, from its dependency tree."""
    return _reaches(end.route, lambda d: getattr(d.call, "prama_scope", None))


def sees_a_caller(end: Endpoint) -> bool:
    return _reaches(end.route, lambda d: True if d.call is get_caller else None) is True


class TestEveryApiRouteDeclaresAScope:
    #: Routes that legitimately see no caller. Each is listed with its reason,
    #: because an exemption without one becomes a place to hide a route.
    ANONYMOUS: ClassVar[dict[str, str]] = {
        "/health": "liveness, read by a load balancer that holds no credential",
        "/capabilities": "what this build supports; no tenant data in the answer",
        "/relationship-kinds": "the fixed vocabulary, identical for every tenant",
        "/auth/token": (
            "exchanges a username and password for a key: the caller has no key yet, "
            "and the principal's own password is the authentication"
        ),
        # The agent fleet's own side (docs/design/agent-fleet-http.md). An agent
        # holds no API key and never sees a scope; what authenticates it is in
        # the body or the headers, and checked by prama.agent.fleet.
        "/fleet/enrol": (
            "redeems a one-use enrolment token for an agent identity: the token, issued "
            "by an administrator for one zone, is the authentication"
        ),
        "/fleet/hello": (
            "a signed agent message: X-Prama-Signature over the message, under a key "
            "derived from the tenant and the agent, is the authentication; anything "
            "unsigned, unknown, suspended or revoked gets a Refusal"
        ),
        "/fleet/report": "as /fleet/hello: the agent's signature is the authentication",
    }

    #: POSTs that change nothing, and so rightly need only a read scope. Each
    #: takes a control's text, which belongs in a body rather than a URL, and
    #: stores nothing — checking a control is reading it, and an owner who
    #: approves controls must be able to read one first. Listed with the reason,
    #: like ANONYMOUS, so a POST copied from a GET still fails.
    READ_ONLY_POSTS: ClassVar[dict[str, str]] = {
        "/pql/check": "parses, type-checks and lints a text; stores nothing",
        "/pql/explain": "renders a text as sentences; stores nothing",
        "/pql/compile": "compiles a text to SQL; stores nothing, runs nothing",
        "/pql/format": "renders a text canonically; stores nothing",
        "/pql/completions": "answers an editor about a text; stores nothing",
        "/pql/hover": "answers an editor about a text; stores nothing",
        "/rule-builder": "assembles PQL from the builder's answers; stores nothing",
        # Read-only by what they do, and needed by people who may only read: an
        # auditor reviewing a change's effect, or comparing a repository with
        # the estate, changes nothing by doing so.
        "/code/review": "diffs the lineage of two uploaded archives; stores nothing",
        "/code/review/git": "diffs the lineage of two git refs; stores nothing",
        "/lineage/change": "reports what a proposed change to lineage reaches; stores nothing",
        "/packs/banking/parse": "parses a financial message and says what is wrong; stores nothing",
        "/estate/diff": "compares supplied estate files with the store; resolves nothing",
    }

    def anonymous_paths(self) -> set[str]:
        return {API_PREFIX + path for path in self.ANONYMOUS}

    def read_only_posts(self) -> set[str]:
        return {API_PREFIX + path for path in self.READ_ONLY_POSTS}

    def test_there_are_routes_to_check(self, endpoints: list[Endpoint]) -> None:
        """Anti-vacuity, and not a formality: the first version of `walk` found
        zero routes and every other test in this class passed."""
        assert len(endpoints) >= 25, [str(e) for e in endpoints]

    def test_every_route_with_a_caller_declares_a_scope(self, endpoints: list[Endpoint]) -> None:
        missing = [str(e) for e in endpoints if sees_a_caller(e) and scope_of(e) is None]
        assert not missing, (
            "these authenticate a caller and then ask nothing about what that "
            f"caller may do: {missing}. Annotate with Reader or Writer."
        )

    def test_a_route_without_a_caller_is_one_of_the_declared_exceptions(
        self, endpoints: list[Endpoint]
    ) -> None:
        allowed = self.anonymous_paths()
        unexplained = sorted(
            e.path for e in endpoints if not sees_a_caller(e) and e.path not in allowed
        )
        assert not unexplained, (
            f"these see no caller at all and are not declared anonymous: {unexplained}"
        )

    def test_the_declared_exceptions_still_exist(self, endpoints: list[Endpoint]) -> None:
        """An exemption for a route that has been deleted is dead weight that
        makes the list look more considered than it is."""
        served = {e.path for e in endpoints}
        stale = sorted(path for path in self.anonymous_paths() if path not in served)
        assert not stale, f"declared anonymous but no longer routed: {stale}"
        posted = {e.path for e in endpoints if "POST" in e.methods}
        stale = sorted(path for path in self.read_only_posts() if path not in posted)
        assert not stale, f"declared a read-only POST but no longer posted to: {stale}"

    def test_a_mutating_route_never_settles_for_a_read_scope(
        self, endpoints: list[Endpoint]
    ) -> None:
        """The commonest way this control goes quietly wrong: a POST annotated
        Reader because it was copied from the GET above it."""
        exempt = self.read_only_posts()
        wrong = [
            f"{e} -> {scope_of(e)}"
            for e in endpoints
            if e.methods & {"POST", "PUT", "PATCH", "DELETE"}
            and (scope_of(e) or "").endswith(":read")
            and not (e.methods == {"POST"} and e.path in exempt)
        ]
        assert not wrong, f"these change state under a read-only scope: {wrong}"

    def test_every_declared_scope_is_a_real_one(self, endpoints: list[Endpoint]) -> None:
        from prama.api.deps import HOLDER

        # HOLDER is not a scope a role grants: it marks a question a key asks
        # about itself (who am I, end this key), which any holder may ask.
        used = {scope_of(e) for e in endpoints} - {None, HOLDER}
        assert used, "no route required any scope, so this proves nothing"
        assert used <= set(SCOPES), f"routes require scopes nobody can hold: {used - set(SCOPES)}"


class TestThereIsOneVocabulary:
    """Finding H5, and a defect this session introduced while fixing S4.

    `BUILTIN_ROLES` grants `declaration:*`, `control:approve`, `evidence:read`.
    The first pass at S4 annotated every API route with `semantic:read` and
    `semantic:write` — names no role grants and none ever could. A key issued to
    an `owner` would have held every permission that role names and been refused
    by every route.

    A permission model that cannot be satisfied is worse than one that is not
    enforced: it fails in production rather than in review, and it fails in the
    direction that looks like a bug in the caller's credentials.

    Both directions are checked. A role may not grant a permission no route can
    require, and no route may require a permission no role can hold — because
    each failure is silent in its own way, and neither shows up in a test of
    either half alone.
    """

    @staticmethod
    def granted() -> set[str]:
        from prama.cli.principal import BUILTIN_ROLES

        return {grant for _, permissions in BUILTIN_ROLES.values() for grant in permissions}

    def test_every_granted_permission_is_a_declared_scope(self) -> None:
        from prama.security.scopes import WILDCARD, unknown

        invented = unknown(self.granted() - {WILDCARD})
        assert not invented, (
            f"BUILTIN_ROLES grants permissions that are not scopes: {invented}. "
            "Anybody holding one holds nothing."
        )

    def test_every_wildcard_grant_covers_something(self) -> None:
        """`declaration:*` is only meaningful if a `declaration:` scope exists.
        A wildcard over an empty prefix reads as a broad grant and is a grant of
        nothing at all."""
        from prama.security.scopes import SCOPES

        empty = sorted(
            grant
            for grant in self.granted()
            if grant.endswith(":*") and not any(scope.startswith(grant[:-1]) for scope in SCOPES)
        )
        assert not empty, f"these wildcards match no declared scope: {empty}"

    def test_every_scope_a_route_requires_can_be_held(self, endpoints: list[Endpoint]) -> None:
        from prama.security.scopes import permits

        granted = self.granted()
        required = {scope_of(end) for end in endpoints} - {None}
        assert required, "no route required any scope, so this proves nothing"
        unreachable = sorted(scope for scope in required if scope and not permits(granted, scope))
        assert not unreachable, (
            f"these routes require a scope no built-in role grants: {unreachable}. "
            "Nobody can call them."
        )

    def test_each_builtin_role_can_actually_do_something(self) -> None:
        """A role that satisfies no route is a job title, not a permission."""
        from prama.cli.principal import BUILTIN_ROLES
        from prama.security.scopes import SCOPES, permits

        useless = sorted(
            name
            for name, (_, permissions) in BUILTIN_ROLES.items()
            if not any(permits(permissions, scope) for scope in SCOPES)
        )
        assert not useless, f"these roles grant nothing any route accepts: {useless}"

    def test_a_role_holds_the_reads_implied_by_its_writes(self) -> None:
        """Signing a thing you cannot read is not a permission set on purpose.

        The third direction, and the one the first two miss. QA round 3 found
        that `owner` holds `attestation:sign` and not `attestation:read`: the
        role built to attest could sign an attestation and then open neither the
        draft it was signing nor its own signed record. Only the wildcard admin
        could do both.

        Neither existing rule catches it, and both are right not to. No role
        grants a permission routes do not require, and no route requires one no
        role can hold — `auditor` holds `attestation:read`, so both directions
        are satisfied while nobody can actually complete the task.

        Stated as a rule about *subjects*: if a role may write within a subject,
        it must be able to read that subject. The converse is deliberately not
        required — `auditor` reads everything and writes nothing, which is the
        entire point of it.
        """
        from prama.cli.principal import BUILTIN_ROLES
        from prama.security.scopes import SCOPES, permits

        reads = {s.split(":", 1)[0] for s in SCOPES if s.endswith(":read")}
        blind_writers: list[str] = []
        for name, (_, permissions) in BUILTIN_ROLES.items():
            for scope in SCOPES:
                subject, _, verb = scope.partition(":")
                if verb == "read" or subject not in reads:
                    continue
                if permits(permissions, scope) and not permits(permissions, f"{subject}:read"):
                    blind_writers.append(f"{name} may {scope} but not {subject}:read")
        assert not blind_writers, (
            "a role may write what it cannot read: "
            + "; ".join(sorted(blind_writers))
            + ". Grant the matching read, or the role cannot finish the task "
            "the write belongs to."
        )

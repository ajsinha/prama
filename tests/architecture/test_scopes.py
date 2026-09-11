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
    }

    def anonymous_paths(self) -> set[str]:
        return {API_PREFIX + path for path in self.ANONYMOUS}

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

    def test_a_mutating_route_never_settles_for_a_read_scope(
        self, endpoints: list[Endpoint]
    ) -> None:
        """The commonest way this control goes quietly wrong: a POST annotated
        Reader because it was copied from the GET above it."""
        wrong = [
            f"{e} -> {scope_of(e)}"
            for e in endpoints
            if e.methods & {"POST", "PUT", "PATCH", "DELETE"}
            and (scope_of(e) or "").endswith(":read")
        ]
        assert not wrong, f"these change state under a read-only scope: {wrong}"

    def test_every_declared_scope_is_a_real_one(self, endpoints: list[Endpoint]) -> None:
        used = {scope_of(e) for e in endpoints} - {None}
        assert used, "no route required any scope, so this proves nothing"
        assert used <= set(SCOPES), f"routes require scopes nobody can hold: {used - set(SCOPES)}"

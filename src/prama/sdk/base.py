"""The SDK's resource base: the endpoint registry, and how a namespace is declared.

Every resource method is filed under the HTTP method and path it calls, with
`endpoint`. ``tests/sdk/test_parity.py`` compares that registry with the API's
routing table, both ways: an endpoint with no SDK method, or an SDK method
calling an endpoint that does not exist, fails the build. That is what keeps
"you can do anything in Prama from Python" true as the API grows.

A resource class is declared with `namespace`, which is how the clients find
it: adding an area of the SDK is adding a module under ``prama.sdk.resources``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar
from urllib.parse import quote

from prama.sdk.transport import Call

#: (method, path template) -> "Class.method", for every SDK method.
ENDPOINTS: dict[tuple[str, str], str] = {}
#: attribute name on the client -> resource class.
NAMESPACES: dict[str, type[Resource]] = {}

F = TypeVar("F", bound=Callable[..., Any])
R = TypeVar("R", bound="type[Resource]")


def endpoint(method: str, path: str) -> Callable[[F], F]:
    """File the decorated method under the endpoint it calls."""

    def deco(fn: F) -> F:
        key = (method.upper(), path)
        if key in ENDPOINTS and ENDPOINTS[key] != fn.__qualname__:
            raise ValueError(f"{method} {path} is already served by {ENDPOINTS[key]}")
        ENDPOINTS[key] = fn.__qualname__
        fn.prama_endpoint = key  # type: ignore[attr-defined]
        return fn

    return deco


def namespace(name: str) -> Callable[[R], R]:
    """Expose the decorated resource class as ``client.<name>``."""

    def deco(cls: R) -> R:
        if name in NAMESPACES and NAMESPACES[name] is not cls:
            raise ValueError(f"client.{name} is already {NAMESPACES[name].__qualname__}")
        NAMESPACES[name] = cls
        return cls

    return deco


def seg(value: Any) -> str:
    """One path segment, escaped: an id or a name can contain a slash."""
    return quote(str(value), safe="")


class Resource:
    """A group of SDK methods sharing a transport.

    Methods return the decoded JSON on a sync client, and a coroutine resolving
    to it on an async one.
    """

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._t.call(Call(method, path, **kwargs))

    def _get(self, path: str, **params: Any) -> Any:
        return self._call("GET", path, params=params)

    def _post(self, path: str, body: Any = None, **params: Any) -> Any:
        return self._call("POST", path, json_body=body, params=params)

    def _put(self, path: str, body: Any = None) -> Any:
        return self._call("PUT", path, json_body=body)

    def _patch(self, path: str, body: Any = None) -> Any:
        return self._call("PATCH", path, json_body=body)

    def _delete(self, path: str, **params: Any) -> Any:
        return self._call("DELETE", path, params=params)


def body(**fields: Any) -> dict[str, Any]:
    """A request body without the fields the caller left unset."""
    return {k: v for k, v in fields.items() if v is not None}

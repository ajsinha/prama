"""How an SDK call reaches Prama: over HTTP, or in-process through ASGI.

A resource method describes a call (`Call`) and hands it to a transport. The
sync transport returns the result; the async one returns a coroutine. So one
method, written once, serves `Client` and `AsyncClient` alike, and the two can
never drift apart.

Failures come back as Prama's own error types. The API answers every failure
with a problem document carrying a stable ``code``; the transport raises the
`prama.core.errors` class with that code, with the server's message and
remedy, so ``except NotFoundError`` means the same thing in a script as it
does inside the server.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import httpx

from prama.core import errors as taxonomy
from prama.core.errors import PramaError
from prama.version import VERSION

API_PREFIX = "/api/v1"


class ServerUnavailable(PramaError):
    """The Prama server could not be reached at all.

    Distinct from a refusal: nothing answered, so there is no problem
    document, and the remedy is about where the server is, not about the call.
    """

    code = "SDK.SERVER_UNAVAILABLE"


@dataclasses.dataclass(slots=True)
class Call:
    """One request, described independently of how it is sent."""

    method: str
    path: str
    params: dict[str, Any] = dataclasses.field(default_factory=dict)
    json_body: Any = None
    files: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    #: Return the body as bytes, for a download.
    raw: bool = False


def _codes() -> dict[str, type[PramaError]]:
    found: dict[str, type[PramaError]] = {}
    pending: list[type[PramaError]] = [PramaError]
    while pending:
        cls = pending.pop()
        found.setdefault(cls.code, cls)
        pending.extend(cls.__subclasses__())
    return found


_BY_STATUS: dict[int, type[PramaError]] = {
    401: taxonomy.UnauthorisedError,
    403: taxonomy.ForbiddenError,
    404: taxonomy.NotFoundError,
    409: taxonomy.ConflictError,
    422: taxonomy.ValidationError,
}


def raise_for(response: httpx.Response) -> None:
    """Raise the Prama error a failed response describes."""
    if response.status_code < 400:
        return
    try:
        body = response.json()
    except ValueError:
        body = {"title": response.text[:500] or f"HTTP {response.status_code}"}
    if not isinstance(body, dict):
        body = {"title": str(body)[:500]}
    code = str(body.get("code") or "")
    cls = _codes().get(code) or _BY_STATUS.get(response.status_code, PramaError)
    title = body.get("title") or body.get("detail") or f"HTTP {response.status_code}"
    if isinstance(title, list):  # FastAPI's request-validation detail
        title = "; ".join(str(item.get("msg", item)) for item in title)
    context = body.get("context") or {}
    if "errors" in body:
        context = {**context, "errors": json.dumps(body["errors"])[:2000]}
    remedy = str(body.get("remedy") or "See the server's log for this correlation id.")
    detail: dict[str, Any] = {str(k): str(v) for k, v in context.items()}
    try:
        error = cls(str(title), remedy=remedy, context=detail, code=code or None)
    except TypeError:  # a subclass with its own constructor: keep its code, not its class
        error = PramaError(str(title), remedy=remedy, context=detail, code=code or None)
    error.status = response.status_code  # type: ignore[attr-defined]
    raise error


def decode(response: httpx.Response, call: Call) -> Any:
    raise_for(response)
    if call.raw:
        return response.content
    if response.status_code == 204 or not response.content:
        return None
    if "json" in response.headers.get("content-type", ""):
        return response.json()
    return response.text


def headers(token: str | None) -> dict[str, str]:
    found = {"User-Agent": f"prama-sdk/{VERSION}", "X-Prama-Client": f"python/{VERSION}"}
    if token:
        found["Authorization"] = f"Bearer {token}"
    return found


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


def _unreachable(base: str, exc: Exception) -> ServerUnavailable:
    return ServerUnavailable(
        f"no Prama server answered at {base}",
        remedy=(
            "Start it (`prama serve`, or `python run_prama_web.py`), or point the SDK at the "
            "one you mean: connect(config='path/to/application.yaml') or "
            "connect(base_url='http://host:port')."
        ),
        context={"base_url": base, "error": type(exc).__name__},
    )


class SyncTransport:
    """Blocking calls through an `httpx.Client`."""

    asynchronous = False

    def __init__(self, http: httpx.Client, token: str | None) -> None:
        self.http, self.token = http, token

    def call(self, call: Call) -> Any:
        try:
            response = self.http.request(
                call.method,
                call.path,
                params=_clean(call.params),
                json=call.json_body,
                files=call.files,
                data=call.data,
                headers=headers(self.token),
            )
        except httpx.TransportError as exc:
            raise _unreachable(str(self.http.base_url), exc) from exc
        return decode(response, call)

    def close(self) -> None:
        self.http.close()


class AsyncTransport:
    """Awaitable calls through an `httpx.AsyncClient`."""

    asynchronous = True

    def __init__(self, http: httpx.AsyncClient, token: str | None) -> None:
        self.http, self.token = http, token

    async def call(self, call: Call) -> Any:
        try:
            response = await self.http.request(
                call.method,
                call.path,
                params=_clean(call.params),
                json=call.json_body,
                files=call.files,
                data=call.data,
                headers=headers(self.token),
            )
        except httpx.TransportError as exc:
            raise _unreachable(str(self.http.base_url), exc) from exc
        return decode(response, call)

    async def close(self) -> None:
        await self.http.aclose()

"""How an SDK call reaches Prama: over HTTP, or in-process through ASGI.

A resource method describes a call (`Call`) and hands it to a transport. The
sync transport returns the result; the async one returns a coroutine. So one
method, written once, serves `Client` and `AsyncClient` alike, and the two can
never drift apart.

Failures come back as the SDK's error types (`prama_sdk.errors`). The API
answers every failure with a problem document carrying a stable ``code``; the
transport raises the class for that code, with the server's message, remedy
and correlation id, so ``except NotFoundError`` means what it says.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import httpx

from prama_sdk.errors import ServerUnavailable, error_for
from prama_sdk.version import VERSION

API_PREFIX = "/api/v1"


@dataclasses.dataclass(slots=True)
class Call:
    """One request, described independently of how it is sent."""

    method: str
    path: str
    params: dict[str, Any] = dataclasses.field(default_factory=dict)
    json_body: Any = None
    #: A mapping, or a list of (field, file) pairs when one field carries several files.
    files: dict[str, Any] | list[tuple[str, Any]] | None = None
    data: dict[str, Any] | None = None
    #: Return the body as bytes, for a download.
    raw: bool = False


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
    title = body.get("title") or body.get("detail") or f"HTTP {response.status_code}"
    if isinstance(title, list):  # FastAPI's request-validation detail
        title = "; ".join(str(item.get("msg", item)) for item in title)
    context = body.get("context") or {}
    if "errors" in body:
        context = {**context, "errors": json.dumps(body["errors"])[:2000]}
    if body.get("correlation_id"):
        context = {**context, "correlation_id": body["correlation_id"]}
    cls = error_for(code, response.status_code)
    raise cls(
        str(title),
        remedy=str(body.get("remedy") or "See the server's log for this correlation id."),
        context={str(k): str(v) for k, v in context.items()},
        code=code or None,
        status=response.status_code,
    )


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

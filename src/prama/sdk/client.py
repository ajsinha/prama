"""The SDK clients, and `connect`: finding the Prama server and signing in to it.

``Client`` is synchronous and ``AsyncClient`` asynchronous. Both expose the same
namespaces (``client.controls``, ``client.evidence``, ``client.tenants`` …),
because a resource method is written once and returns a value on one and a
coroutine on the other.

**Where the server is.** `connect` reads the same ``config/application.yaml``
the server reads — ``server.host`` and ``server.port`` — so a script talks to
the Prama running on this machine without being told where it is. To use
another server, hand it another configuration file, or a ``base_url``.

**Who you are**, first match wins:

1. ``api_key=`` passed explicitly;
2. the ``PRAMA_API_KEY`` environment variable;
3. ``username=`` and ``password=``, exchanged for an expiring key
   (``POST /api/v1/auth/token``);
4. ``PRAMA_USERNAME`` and ``PRAMA_PASSWORD`` from the environment, likewise;
5. nobody: only the public endpoints answer.

A credential is never sent over plain HTTP to anything but this machine unless
``insecure=True`` says so, knowingly.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import importlib
import ipaddress
import os
import pkgutil
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from prama.core.errors import ValidationError
from prama.sdk import base
from prama.sdk.transport import API_PREFIX, AsyncTransport, SyncTransport

DEFAULT_TIMEOUT = 120.0


def _load_resources() -> None:
    """Import every module under ``prama.sdk.resources`` so each namespace registers."""
    from prama.sdk import resources

    for info in pkgutil.iter_modules(resources.__path__):
        if not info.name.startswith("_"):
            importlib.import_module(f"{resources.__name__}.{info.name}")


def _loopback(base_url: str) -> bool:
    host = urlsplit(base_url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _refuse_plain_http(base_url: str, credential: str | None, insecure: bool) -> None:
    if not credential or insecure or not base_url.startswith("http://") or _loopback(base_url):
        return
    raise ValidationError(
        f"refusing to send a credential over plain HTTP to {base_url}",
        remedy=(
            "Use https://, or pass insecure=True if this network is one you trust. The "
            "key would otherwise cross the network readable by anyone on the path."
        ),
        context={"base_url": base_url},
    )


class _Namespaces:
    """Binds every registered resource namespace to one transport."""

    #: Declared for type checkers; the real attributes come from NAMESPACES.
    identity: dict[str, Any]

    def _bind(self, transport: Any) -> None:
        _load_resources()
        self._transport = transport
        for name, cls in base.NAMESPACES.items():
            setattr(self, name, cls(transport))

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - for type checkers
        raise AttributeError(
            f"the SDK has no {name!r} namespace; see prama.sdk.base.NAMESPACES for those it has"
        )


class Client(_Namespaces):
    """A synchronous client of one Prama server, acting as one credential."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:5900",
        *,
        api_key: str | None = None,
        app: Any = None,
        timeout: float = DEFAULT_TIMEOUT,
        insecure: bool = False,
        verify: bool | str = True,
    ) -> None:
        _refuse_plain_http(base_url, api_key, insecure or app is not None)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        if app is not None:
            from starlette.testclient import TestClient

            http: httpx.Client = TestClient(app, base_url="http://inproc" + API_PREFIX)
            http.timeout = httpx.Timeout(timeout)
            self.mode = "inproc"
        else:
            http = httpx.Client(
                base_url=self.base_url + API_PREFIX,
                verify=verify,
                timeout=httpx.Timeout(timeout, connect=10.0),
            )
            self.mode = "http"
        self._app = app
        self._timeout, self._insecure, self._verify = timeout, insecure, verify
        self._bind(SyncTransport(http, api_key))

    @property
    def console_url(self) -> str:
        """Where a person opens this server's console."""
        return self.base_url + "/"

    def as_key(self, api_key: str) -> Client:
        """The same server, acting as another key — another estate, say."""
        return Client(
            self.base_url,
            api_key=api_key,
            app=self._app,
            timeout=self._timeout,
            insecure=self._insecure,
            verify=self._verify,
        )

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class AsyncClient(_Namespaces):
    """The asynchronous twin of `Client`: every method returns a coroutine."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:5900",
        *,
        api_key: str | None = None,
        app: Any = None,
        timeout: float = DEFAULT_TIMEOUT,
        insecure: bool = False,
        verify: bool | str = True,
    ) -> None:
        _refuse_plain_http(base_url, api_key, insecure or app is not None)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        if app is not None:
            http = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://inproc" + API_PREFIX,
                timeout=httpx.Timeout(timeout),
            )
            self.mode = "inproc"
        else:
            http = httpx.AsyncClient(
                base_url=self.base_url + API_PREFIX,
                verify=verify,
                timeout=httpx.Timeout(timeout, connect=10.0),
            )
            self.mode = "http"
        self._app = app
        self._timeout, self._insecure, self._verify = timeout, insecure, verify
        self._bind(AsyncTransport(http, api_key))

    @property
    def console_url(self) -> str:
        return self.base_url + "/"

    def as_key(self, api_key: str) -> AsyncClient:
        return AsyncClient(
            self.base_url,
            api_key=api_key,
            app=self._app,
            timeout=self._timeout,
            insecure=self._insecure,
            verify=self._verify,
        )

    async def close(self) -> None:
        await self._transport.close()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()


def server_url(config: str | Path | None = None) -> str:
    """The URL of the server a configuration file describes.

    ``config`` is an ``application.yaml``; by default the one in this checkout,
    with its ``application.local.yaml`` beside it, exactly as the server loads
    it. A server bound to every interface (``0.0.0.0``) is reached on loopback.
    """
    from prama.core.config import load_configuration

    configuration = load_configuration(Path(config).expanduser() if config else None)
    host = configuration.get_str("server.host", "127.0.0.1") or "127.0.0.1"
    if host in ("0.0.0.0", "::", ""):  # a bind address, reached on loopback
        host = "127.0.0.1"
    port = configuration.get_int("server.port", 5900)
    scheme = "https" if configuration.get_bool("server.tls", False) else "http"
    return f"{scheme}://{host}:{port}"


def connect(
    base_url: str | None = None,
    *,
    config: str | Path | None = None,
    api_key: str | None = None,
    username: str | None = None,
    password: str | None = None,
    tenant: str = "",
    timeout: float = DEFAULT_TIMEOUT,
    insecure: bool = False,
    verify: bool | str = True,
) -> Client:
    """A `Client` of the Prama server this configuration describes, signed in.

    ``tenant`` names the estate (slug or id) when signing in with a username
    and password on an installation with more than one.
    """
    url = (base_url or server_url(config)).rstrip("/")
    key = api_key or os.environ.get("PRAMA_API_KEY") or None
    user = username or os.environ.get("PRAMA_USERNAME") or None
    secret = password or os.environ.get("PRAMA_PASSWORD") or None
    if key is None and user and secret:
        _refuse_plain_http(url, secret, insecure)
        anonymous = Client(url, timeout=timeout, insecure=insecure, verify=verify)
        try:
            key = anonymous.auth.token(user, secret, tenant=tenant)["api_key"]
        finally:
            anonymous.close()
    return Client(url, api_key=key, timeout=timeout, insecure=insecure, verify=verify)

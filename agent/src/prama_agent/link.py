"""The agent's only way to the server: `FleetLink`, and its SDK implementation.

The daemon never builds an HTTP request. It talks to a `FleetLink`, whose three
methods are the fleet API's agent-facing endpoints (``docs/design/agent-fleet-http.md``):

* ``enrol`` — redeem a one-time token for an identity and a key;
* ``hello`` — announce, and be handed work; answered by a Receipt or a Refusal;
* ``report`` — deliver findings; answered by a Receipt or a Refusal.

`SdkFleetLink` implements it with ``prama_sdk``'s ``client.fleet`` namespace,
which signs each message with the agent's key. Everything else — the loop, the
backoff, the spool — is tested against a fake link, so the daemon's behaviour
does not depend on a server being up.

A link that cannot reach the server raises `LinkUnavailable`. That includes a
server that answers with a 5xx, a rate limit, or a route it does not have (an
older server without the fleet API): in every case the right response is the
same — keep the findings, back off, try again — and none of them is a Refusal,
which only the server's protocol answer can be.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any, Protocol

from prama_kernel.errors import ConfigError, PramaError


class LinkUnavailable(PramaError):
    """The server could not be reached, or did not answer with the protocol."""

    code = "AGENT.LINK_UNAVAILABLE"


class FleetLink(Protocol):
    """What the daemon needs from the server, and nothing more."""

    def enrol(
        self, token: str, *, name: str, version: str, capabilities: dict[str, Any]
    ) -> dict[str, Any]:
        """``{agent_id, key (hex), zone, poll_after_seconds}``."""
        ...

    def hello(self, hello: dict[str, Any], *, key: bytes) -> dict[str, Any]:
        """A Receipt's or a Refusal's dict (`prama_kernel.agent.protocol.response_from_dict`)."""
        ...

    def report(self, report: dict[str, Any], *, key: bytes) -> dict[str, Any]:
        """A Receipt's or a Refusal's dict."""
        ...

    def close(self) -> None: ...


class SdkFleetLink:
    """`FleetLink` over ``prama_sdk``: ``client.fleet.enrol / hello / report``.

    No API key: an agent holds none and is authenticated by its signature,
    which the SDK computes from the key it is handed on each call.
    """

    def __init__(
        self,
        url: str,
        *,
        verify: bool | str = True,
        timeout: float = 30.0,
        client: Any = None,
    ) -> None:
        import prama_sdk

        self._sdk = prama_sdk
        self._client = (
            prama_sdk.Client(url, timeout=timeout, verify=verify) if client is None else client
        )
        self.url = url
        if getattr(self._client, "fleet", None) is None:
            self._client.close()
            # Said at start rather than retried forever: an SDK without the
            # fleet namespace is an installation problem, not an outage.
            raise ConfigError(
                f"the installed prama-sdk ({prama_sdk.__version__}) has no fleet namespace",
                remedy="Install a prama-sdk that provides client.fleet (enrol, hello, report).",
                context={"sdk": prama_sdk.__version__},
            )

    def enrol(
        self, token: str, *, name: str, version: str, capabilities: dict[str, Any]
    ) -> dict[str, Any]:
        # Enrolment errors propagate as they are: a spent or expired token is
        # something the person running `enrol` must read, not something to retry.
        answer = self._client.fleet.enrol(
            token, name=name, version=version, capabilities=capabilities
        )
        return dict(answer)

    def hello(self, hello: dict[str, Any], *, key: bytes) -> dict[str, Any]:
        return self._guarded("hello", lambda: self._client.fleet.hello(hello, key=key))

    def report(self, report: dict[str, Any], *, key: bytes) -> dict[str, Any]:
        return self._guarded("report", lambda: self._client.fleet.report(report, key=key))

    def close(self) -> None:
        self._client.close()

    def _guarded(self, what: str, call: Any) -> dict[str, Any]:
        try:
            answer = call()
        except self._sdk.PramaError as exc:
            raise LinkUnavailable(
                f"{what} to {self.url} failed: {exc.message}",
                remedy=getattr(exc, "remedy", "") or "The agent will back off and try again.",
                context={"server": self.url, "code": str(getattr(exc, "code", ""))},
                cause=exc,
            ) from exc
        if not isinstance(answer, dict):
            raise LinkUnavailable(
                f"{what} to {self.url} was answered with something that is not a protocol message",
                remedy="Check that server.url names a Prama server with the fleet API.",
                context={"server": self.url},
            )
        return answer

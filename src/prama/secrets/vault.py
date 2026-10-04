"""HashiCorp Vault as a secret source — ``vault://path/to/secret#field``.

The provider a regulated estate is most likely to actually have. It resolves
against the KV v2 engine, which is the one people mean when they say Vault, and
it is deliberately narrow: read one secret, return one value, never write and
never list.

Four decisions that are not obvious from the API.

**KV v2 nests the data.** A read returns ``{"data": {"data": {...}}}``, and a
provider that reaches for the outer ``data`` returns the *metadata* — a dict of
version numbers and timestamps that is not the secret and does not look like an
error either. The inner document is what a caller wants.

**A soft-deleted version is not a value.** Vault keeps deleted versions and
returns them with an empty ``data`` and a ``deletion_time`` in the metadata. A
provider that reads the empty data hands back an empty string, which reaches the
driver as an authentication failure and sends somebody to check a password that
was never read.

**The token is a reference, not a literal.** The Vault token itself is a
credential, so it is resolved through the same resolver as everything else —
otherwise the one secret this module exists to protect is the one sitting in a
config file.

**It is an egress.** Reading a secret sends an authenticated request to
whatever address Vault is at, and under a residency rule that address is
checked. A secret store in the wrong region is a data movement like any other.

The transport is injected. Nothing here opens a socket, which is what lets the
whole of it be tested without a Vault — and, more to the point, what lets a
deployment substitute its own client with the organisation's mTLS, proxy and
retry policy already applied.

**Not verified against a real Vault.** The shapes below are from the documented
KV v2 API. Nobody has run this against a live server, and that is recorded here
rather than implied by its absence.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from typing import Any

from prama.secrets.reference import SecretRef
from prama.secrets.spi import (
    SecretProvider,
    SecretProviderUnavailableError,
    SecretResolutionError,
)
from prama.secrets.value import SecretValue

__all__ = ["ReadResult", "VaultSecretProvider", "VaultTransport", "http_transport"]

#: A callable taking (path, token) and returning the parsed JSON body, or
#: raising. A protocol rather than a client, so a deployment substitutes its own
#: with mTLS, proxying and retries already applied.
VaultTransport = Callable[[str, str], Mapping[str, Any]]


def http_transport(
    address: str, *, namespace: str = "", ca_file: str = "", timeout: float = 10.0
) -> VaultTransport:
    """The default transport: ``GET {address}/v1/{path}`` with the token in a header.

    The standard library's HTTP client, so the server needs no extra package for
    Vault. A deployment with its own client (mTLS, a proxy, retries) passes that
    to :class:`VaultSecretProvider` instead. ``ca_file`` trusts a private CA;
    certificate verification is never turned off.
    """
    import json
    import ssl
    import urllib.error
    import urllib.request

    base = address.rstrip("/")
    context = ssl.create_default_context(cafile=ca_file or None)

    def read(path: str, token: str) -> Mapping[str, Any]:
        headers = {"X-Vault-Token": token, "Accept": "application/json"}
        if namespace:
            headers["X-Vault-Namespace"] = namespace
        request = urllib.request.Request(f"{base}/v1/{path.lstrip('/')}", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                body: Mapping[str, Any] = json.loads(response.read().decode("utf-8"))
                return body
        except urllib.error.HTTPError as exc:
            # 404 is "no such secret", 403 a token without the policy: both are
            # answers about the reference, not an outage, so say which.
            reason = {404: "no secret at this path", 403: "the token may not read it"}
            raise SecretResolutionError(
                f"Vault refused {path}: {reason.get(exc.code, f'HTTP {exc.code}')}",
                remedy=(
                    "Check the path (KV v2 paths include the data/ segment) and the token's policy."
                ),
                context={"path": path, "status": str(exc.code)},
            ) from exc

    return read


@dataclasses.dataclass(frozen=True, slots=True)
class ReadResult:
    """What a KV v2 read actually contained."""

    fields: Mapping[str, Any]
    version: int = 0
    destroyed: bool = False
    deletion_time: str = ""

    @property
    def is_readable(self) -> bool:
        """Whether this version still holds anything.

        A soft-deleted version comes back with empty data and a deletion time,
        and is not an error at the HTTP layer. Treating it as a value hands an
        empty string to a driver.
        """
        return bool(self.fields) and not self.destroyed and not self.deletion_time

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> ReadResult:
        # The outer "data" is the envelope; the inner one is the secret. Reading
        # the outer returns version numbers and timestamps, which is not the
        # secret and does not look like an error either.
        envelope = body.get("data")
        if not isinstance(envelope, Mapping):
            return cls(fields={})
        fields = envelope.get("data")
        metadata = envelope.get("metadata")
        meta: Mapping[str, Any] = metadata if isinstance(metadata, Mapping) else {}
        return cls(
            fields=fields if isinstance(fields, Mapping) else {},
            version=int(meta.get("version", 0) or 0),
            destroyed=bool(meta.get("destroyed", False)),
            deletion_time=str(meta.get("deletion_time", "") or ""),
        )


class VaultSecretProvider(SecretProvider):
    """``vault://secret/data/prama/db#password``.

    The path is passed through as written, including the ``data/`` segment that
    KV v2 requires. Inserting it silently would be convenient and would break
    every deployment whose mount is not called ``secret``.
    """

    scheme = "vault"
    description = "HashiCorp Vault KV v2. Reads one secret; never writes, never lists."

    def __init__(
        self,
        transport: VaultTransport | None = None,
        *,
        token: str = "",
        address: str = "",
        region: str = "",
        gate: Any = None,
    ) -> None:
        self._transport = transport
        #: Resolved by the caller through the ordinary resolver, because the
        #: Vault token is itself a credential.
        self._token = token
        self._address = address
        self._region = region
        self._gate = gate

    def available(self) -> bool:
        """Whether this deployment can use Vault at all.

        A provider registered without a transport or a token is not available,
        and saying so lets the resolver's error name what *is* configured
        instead of failing at the first reference.
        """
        return bool(self._transport) and bool(self._token)

    def unavailable_remedy(self) -> str:
        missing = []
        if not self._transport:
            missing.append("no transport (the Vault address and an HTTP client)")
        if not self._token:
            missing.append("no token reference")
        return (
            f"Vault is installed but not configured: it has {' and '.join(missing)}. "
            "Set secrets.vault.address and secrets.vault.token_ref (env://VAULT_TOKEN) "
            "in configuration — the token is itself a credential, so it is given as a "
            "reference and not as a literal."
        )

    def resolve(self, reference: SecretRef) -> SecretValue:
        if not self.available():
            raise SecretProviderUnavailableError(
                "Vault is referenced but not configured",
                remedy=(
                    "Set secrets.vault.address and secrets.vault.token_ref in configuration. "
                    "The token is itself a credential, so it is given as a "
                    "reference (env://VAULT_TOKEN) and not as a literal."
                ),
                context={"reference": reference.render()},
            )

        if self._gate is not None:
            # Reading a secret sends an authenticated request somewhere. Under a
            # residency rule that somewhere is checked like any other egress.
            self._gate.require(
                "secret-fetch",
                destination=self._region,
                jurisdiction=self._region,
                subject="a credential read from Vault",
            )

        assert self._transport is not None  # available() checked it
        try:
            body = self._transport(reference.location, self._token)
        except SecretResolutionError:
            raise
        except Exception as exc:
            raise SecretResolutionError(
                f"Vault did not answer for {reference.location}",
                remedy=(
                    "Check that Vault is reachable and the token is current. A "
                    "Vault token expires, and an expired one fails exactly like "
                    "a wrong path."
                ),
                context={"reference": reference.render(), "error": type(exc).__name__},
            ) from exc

        result = ReadResult.from_body(body)
        if not result.is_readable:
            raise SecretResolutionError(
                self._why_empty(reference, result),
                remedy=(
                    "Write the secret, or read an earlier version. Returning an "
                    "empty value here would reach the driver as an authentication "
                    "failure and send somebody to check the wrong thing."
                ),
                context={"reference": reference.render(), "version": str(result.version)},
            )

        if not reference.key:
            raise SecretResolutionError(
                f"{reference.location} holds {len(result.fields)} field(s) and the "
                "reference names none",
                remedy=(
                    "Name the field: vault://path#password. A KV v2 secret is a "
                    "document, and guessing which field is the credential is how "
                    "a username gets used as a password."
                ),
                context={"reference": reference.render()},
            )

        if reference.key not in result.fields:
            raise SecretResolutionError(
                f"{reference.location} has no field called {reference.key!r}",
                # The available field *names* are safe to state — they are not
                # the values — and they are what makes this fixable in one step.
                remedy=(f"Fields present: {', '.join(sorted(map(str, result.fields)))}."),
                context={"reference": reference.render()},
            )

        raw = result.fields[reference.key]
        if raw is None or str(raw) == "":
            raise SecretResolutionError(
                f"{reference.location} field {reference.key!r} is empty",
                remedy=(
                    "An empty secret is almost always a half-finished write. "
                    "Prama refuses it rather than passing it to a driver."
                ),
                context={"reference": reference.render()},
            )
        return SecretValue(str(raw), origin=reference.render())

    def _why_empty(self, reference: SecretRef, result: ReadResult) -> str:
        if result.destroyed:
            return f"{reference.location} version {result.version} has been destroyed"
        if result.deletion_time:
            return (
                f"{reference.location} version {result.version} was deleted at "
                f"{result.deletion_time}"
            )
        return f"{reference.location} holds no data"

"""Vault from configuration: an address and a token reference, then real HTTP.

Until this, ``default_resolver()`` built the Vault provider with no address and
no token, and no configuration key could supply them, so every ``vault://``
reference was refused. These run against an HTTP server on loopback that
answers as Vault's KV v2 API does, so the transport is exercised, not mocked.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import pytest

from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.core.errors import ConfigError
from prama.secrets import resolver as secrets
from prama.secrets.spi import SecretResolutionError

TOKEN = "s.test-token-not-real"
SECRETS = {"secret/data/prama/db": {"password": "from-vault", "user": "prama_ro"}}


class _Vault(BaseHTTPRequestHandler):
    seen: ClassVar[list[dict[str, str]]] = []

    def do_GET(self) -> None:
        _Vault.seen.append({"path": self.path, **dict(self.headers)})
        if self.headers.get("X-Vault-Token") != TOKEN:
            self.send_response(403)
            self.end_headers()
            return
        data = SECRETS.get(self.path.removeprefix("/v1/"))
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({"data": {"data": data, "metadata": {"version": 3}}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: Any) -> None:
        pass


@pytest.fixture
def vault() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Vault)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        secrets._settings.clear()  # the next test starts unconfigured


def _configure(**vault: Any) -> None:
    builder = ConfigurationBuilder().with_defaults(DEFAULTS)
    builder.with_mapping({"secrets": {"vault": vault}}, name="test")
    secrets.configure(builder.build())


def test_a_configured_vault_resolves_a_reference(
    vault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRAMA_TEST_VAULT_TOKEN", TOKEN)
    _configure(address=vault, token_ref="env://PRAMA_TEST_VAULT_TOKEN")
    value = secrets.default_resolver().resolve("vault://secret/data/prama/db#password")
    assert value.reveal() == "from-vault"
    assert _Vault.seen[-1]["path"] == "/v1/secret/data/prama/db"


def test_a_missing_secret_says_so(vault: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRAMA_TEST_VAULT_TOKEN", TOKEN)
    _configure(address=vault, token_ref="env://PRAMA_TEST_VAULT_TOKEN")
    with pytest.raises(SecretResolutionError, match="no secret at this path"):
        secrets.default_resolver().resolve("vault://secret/data/absent#password")


def test_a_wrong_token_is_named_as_a_policy_problem(
    vault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRAMA_TEST_VAULT_TOKEN", "s.wrong")
    _configure(address=vault, token_ref="env://PRAMA_TEST_VAULT_TOKEN")
    with pytest.raises(SecretResolutionError, match="may not read it"):
        secrets.default_resolver().resolve("vault://secret/data/prama/db#password")


def test_a_literal_token_in_configuration_is_refused() -> None:
    with pytest.raises(ConfigError, match="must be a reference"):
        _configure(address="https://vault.example", token_ref=TOKEN)


def test_unconfigured_vault_still_says_what_to_set() -> None:
    secrets._settings.clear()
    with pytest.raises(SecretResolutionError) as refused:
        secrets.default_resolver().resolve("vault://secret/data/prama/db#password")
    # It names the settings to fill in, not a plugin to install.
    assert "secrets.vault.address" in refused.value.remedy

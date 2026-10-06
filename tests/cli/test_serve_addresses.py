"""What `prama serve` prints for where to open it, now that it binds every interface.

The default bind address is 0.0.0.0, so the console is reachable from the network.
That is an address a server listens on, not one a browser opens; the banner used
to print http://0.0.0.0:5900. It now prints this machine's loopback first, the
network address beside it, and what changes when other machines can connect.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.cli.commands import network_caveats, reachable_urls
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS


def _config(**security: object) -> object:
    builder = ConfigurationBuilder().with_defaults(DEFAULTS)
    return builder.with_mapping({"security": security}, name="t").build()


def test_the_default_is_every_interface() -> None:
    assert DEFAULTS["server"]["host"] == "0.0.0.0"


def test_a_bind_address_is_never_printed_as_a_url() -> None:
    urls = reachable_urls("0.0.0.0", 5900)
    assert urls[0] == "http://127.0.0.1:5900"
    assert not any("0.0.0.0" in u for u in urls)


def test_a_specific_host_is_printed_as_it_is() -> None:
    assert reachable_urls("10.1.2.3", 5900) == ["http://10.1.2.3:5900"]


def test_loopback_needs_no_caveat() -> None:
    assert network_caveats("127.0.0.1", _config()) == []


def test_the_network_caveat_names_the_settings() -> None:
    said = "\n".join(network_caveats("0.0.0.0", _config()))
    assert "server.host: 127.0.0.1" in said
    assert "cookies_https_only: false" in said  # secure cookies need https off loopback


def test_without_secure_only_cookies_the_cookie_caveat_is_not_said() -> None:
    said = "\n".join(network_caveats("0.0.0.0", _config(cookies_https_only=False)))
    assert "cookies_https_only" not in said and "server.host" in said

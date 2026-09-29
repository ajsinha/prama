"""Every API endpoint has an SDK method, and every SDK method an endpoint.

What keeps "anything Prama does, you can do from Python" true as the API grows:
a new endpoint without an SDK method fails here, and so does an SDK method
calling a path the server does not have.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.api import create_app
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.sdk import base
from prama.sdk.client import _load_resources
from prama.sdk.transport import API_PREFIX


def _server() -> set[tuple[str, str]]:
    config = (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping({"web": {"enabled": False}}, name="parity")
        .build()
    )
    # The OpenAPI document rather than the routing table: it is what an
    # integrator sees, and this FastAPI wraps included routers so the table
    # does not list their routes flat.
    found = set()
    for path, operations in create_app(config).openapi()["paths"].items():
        if path.startswith(API_PREFIX):
            for method in operations:
                found.add((method.upper(), path[len(API_PREFIX) :]))
    assert found, "the API published no endpoints, so this check would pass vacuously"
    return found


def test_every_endpoint_has_an_sdk_method_and_every_method_an_endpoint() -> None:
    _load_resources()
    server, sdk = _server(), set(base.ENDPOINTS)
    missing = sorted(server - sdk)
    phantom = sorted(sdk - server)
    assert not missing, "endpoints with no SDK method:\n" + "\n".join(
        f"  {m} {p}" for m, p in missing
    )
    assert not phantom, "SDK methods calling no endpoint:\n" + "\n".join(
        f"  {base.ENDPOINTS[k]} -> {k[0]} {k[1]}" for k in phantom
    )


def test_the_parity_check_can_fail() -> None:
    """The counterfactual: a method filed under a path the server lacks is caught."""
    _load_resources()
    key = ("GET", "/no/such/endpoint")
    base.ENDPOINTS[key] = "Phantom.method"
    try:
        assert key in set(base.ENDPOINTS) - _server()
    finally:
        del base.ENDPOINTS[key]

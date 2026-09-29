"""The SDK against a real application: sign in, estates, errors, and a round trip.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.sdk.conftest import PASSWORD

import prama.sdk as prama
from prama.sdk import AsyncClient


async def test_a_password_becomes_an_expiring_scoped_key(app: object, admin: str) -> None:
    anonymous = AsyncClient(app=app)
    issued = await anonymous.auth.token(admin, PASSWORD, tenant="acme-bank")
    assert issued["api_key"].startswith("pk_")
    assert issued["expires_at"] and "*" in issued["scopes"]
    me = await anonymous.as_key(issued["api_key"]).auth.me()
    assert me["username"] == "ada" and me["tenant_slug"] == "acme-bank"
    await anonymous.close()


async def test_a_wrong_password_is_prama_s_own_error(app: object, admin: str) -> None:
    anonymous = AsyncClient(app=app)
    with pytest.raises(prama.UnauthorisedError) as caught:
        await anonymous.auth.token(admin, "not-the-password", tenant="acme-bank")
    assert caught.value.code == "AUTH.UNAUTHORISED" and caught.value.remedy
    await anonymous.close()


async def test_a_revoked_key_stops_working(client: AsyncClient) -> None:
    await client.auth.revoke()
    with pytest.raises(prama.UnauthorisedError):
        await client.auth.me()


async def test_creating_an_estate_makes_you_its_administrator(client: AsyncClient) -> None:
    made = await client.tenants.create("study-one", "Study one")
    assert made["tenant"]["slug"] == "study-one"
    inside = client.as_key(made["credentials"]["api_key"])
    assert (await inside.tenants.current())["slug"] == "study-one"
    # The same person, with the same password, can sign in to it directly.
    anonymous = AsyncClient(app=client._app)
    again = await anonymous.auth.token("ada", PASSWORD, tenant="study-one")
    assert again["tenant_slug"] == "study-one"
    with pytest.raises(prama.ConflictError):
        await client.tenants.create("study-one", "Again")
    for c in (inside, anonymous):
        await c.close()


async def test_declarations_round_trip_and_stay_in_their_estate(client: AsyncClient) -> None:
    made = await client.tenants.create("study-two", "Study two")
    inside = client.as_key(made["credentials"]["api_key"])
    declared = await inside.datasets.declare("Trades", description="Executed trades.")
    assert declared["name"] == "Trades"
    assert [d["name"] for d in (await inside.datasets.list())["items"]] == ["Trades"]
    assert (await client.datasets.list())["items"] == []  # the first estate sees none of it
    with pytest.raises(prama.NotFoundError):
        await client.datasets.get(declared["id"])
    await inside.close()


def test_credentials_never_cross_plain_http_to_another_machine() -> None:
    with pytest.raises(prama.ValidationError, match="plain HTTP"):
        prama.Client("http://prama.example.com:5900", api_key="pk_live_x")
    prama.Client("http://127.0.0.1:5900", api_key="pk_live_x").close()  # loopback is fine
    prama.Client("http://prama.example.com:5900", api_key="pk_live_x", insecure=True).close()


def test_the_server_is_found_from_the_application_configuration(tmp_path: Path) -> None:
    config = tmp_path / "application.yaml"
    config.write_text("server:\n  host: 0.0.0.0\n  port: 6123\n")
    assert prama.server_url(config) == "http://127.0.0.1:6123"


def test_no_server_is_said_plainly() -> None:
    client = prama.Client("http://127.0.0.1:9")
    with pytest.raises(prama.ServerUnavailable, match="no Prama server answered"):
        client.system.health()
    client.close()


def test_the_sync_client_works_in_process(app: object) -> None:
    with prama.Client(app=app) as client:
        assert client.system.health()["status"]

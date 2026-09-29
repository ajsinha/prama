"""People, roles, keys, configuration and the audit log, through the SDK.

Each test drives the real application in process and asserts what the estate
now *does* — who can sign in, which key still works, what a key may carry —
rather than that a call returned 200. Every refusal has its counterfactual:
the same operation, by somebody entitled to it, succeeds.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest
from tests.sdk.conftest import PASSWORD

import prama.sdk as prama
from prama.sdk import AsyncClient

STEWARD_PASSWORD = "steward-password-1"


async def _sign_in(client: AsyncClient, username: str, password: str) -> AsyncClient:
    anonymous = AsyncClient(app=client._app)
    issued = await anonymous.auth.token(username, password, tenant="acme-bank")
    return anonymous.as_key(issued["api_key"])


async def test_an_admin_creates_a_steward_who_is_refused_administration(
    client: AsyncClient,
) -> None:
    made = await client.principals.create("bo", roles=["steward"], password=STEWARD_PASSWORD)
    assert made["roles"] == ["steward"] and made["can_sign_in"] and made["status"] == "active"

    bo = await _sign_in(client, "bo", STEWARD_PASSWORD)
    me = await bo.auth.me()
    assert me["username"] == "bo" and "admin" not in me["scopes"]
    assert "control:propose" in me["scopes"]

    # The steward is refused every administrative operation...
    with pytest.raises(prama.ForbiddenError):
        await bo.principals.list()
    with pytest.raises(prama.ForbiddenError):
        await bo.principals.create("mallory", roles=["admin"], password="whatever-password")
    with pytest.raises(prama.ForbiddenError):
        await bo.config.show()
    # ...which the administrator, the counterfactual, may do.
    names = {p["username"] for p in await client.principals.list()}
    assert names == {"ada", "bo"}
    await bo.close()


async def test_roles_can_be_replaced_and_the_new_ones_are_what_a_sign_in_carries(
    client: AsyncClient,
) -> None:
    await client.principals.create("cy", roles=["auditor"], password=STEWARD_PASSWORD)
    cy = await _sign_in(client, "cy", STEWARD_PASSWORD)
    assert "control:approve" not in (await cy.auth.me())["scopes"]
    await cy.close()

    changed = await client.principals.set_roles("cy", ["owner"])
    assert changed["roles"] == ["owner"]
    again = await _sign_in(client, "cy", STEWARD_PASSWORD)
    scopes = (await again.auth.me())["scopes"]
    assert "control:approve" in scopes and "admin" not in scopes
    await again.close()

    with pytest.raises(prama.ValidationError):
        await client.principals.set_roles("cy", ["overlord"])
    # An administrator cannot take away their own admin role.
    with pytest.raises(prama.ValidationError, match="your own admin role"):
        await client.principals.set_roles("ada", ["owner"])


async def test_a_disabled_principal_s_key_stops_working_and_enabling_restores_it(
    client: AsyncClient,
) -> None:
    await client.principals.create("dee", roles=["steward"], password=STEWARD_PASSWORD)
    dee = await _sign_in(client, "dee", STEWARD_PASSWORD)
    assert (await dee.auth.me())["username"] == "dee"

    await client.principals.disable("dee")
    with pytest.raises(prama.UnauthorisedError):
        await dee.auth.me()
    # Nor can they get a fresh key with their password.
    with pytest.raises(prama.UnauthorisedError):
        await _sign_in(client, "dee", STEWARD_PASSWORD)

    await client.principals.enable("dee")
    assert (await dee.auth.me())["username"] == "dee"  # the same key, working again
    # An administrator cannot disable themselves.
    with pytest.raises(prama.ValidationError, match="disable yourself"):
        await client.principals.disable("ada")
    await dee.close()


async def test_a_principal_without_a_password_cannot_sign_in_until_one_is_set(
    client: AsyncClient,
) -> None:
    made = await client.principals.create("svc-etl", kind="service", roles=["auditor"])
    assert made["can_sign_in"] is False and made["kind"] == "service"
    with pytest.raises(prama.UnauthorisedError):
        await _sign_in(client, "svc-etl", "anything-at-all")

    await client.principals.reset_password(made["id"], "a-new-password-1")
    assert (await client.principals.get("svc-etl"))["can_sign_in"] is True
    signed_in = await _sign_in(client, "svc-etl", "a-new-password-1")
    assert (await signed_in.auth.me())["username"] == "svc-etl"
    await signed_in.close()

    with pytest.raises(prama.ConflictError):
        await client.principals.create("svc-etl")
    with pytest.raises(prama.NotFoundError):
        await client.principals.get("nobody")


async def test_minting_a_key_refuses_a_scope_the_caller_does_not_hold(
    client: AsyncClient,
) -> None:
    await client.principals.create("eve", roles=["steward"], password=STEWARD_PASSWORD)
    eve = await _sign_in(client, "eve", STEWARD_PASSWORD)

    # Escalation: a steward asks for the approval its role withholds.
    with pytest.raises(prama.ValidationError, match="control:approve"):
        await eve.api_keys.create("ci", ["control:read", "control:approve"])
    with pytest.raises(prama.ValidationError):
        await eve.api_keys.create("ci", ["*"])
    grantable = (await eve.account.get())["grantable"]
    assert "control:propose" in grantable
    assert "control:approve" not in grantable and "admin" not in grantable

    # The counterfactual: a scope they do hold, and the key carries only that.
    minted = await eve.api_keys.create("ci", ["control:read"], days=7)
    assert minted["plaintext"].startswith("pk_") and minted["scopes"] == ["control:read"]
    narrow = client.as_key(minted["plaintext"])
    assert (await narrow.auth.me())["scopes"] == ["control:read"]
    # A narrowed key cannot mint its way back up.
    with pytest.raises(prama.ValidationError):
        await narrow.api_keys.create("wider", ["incident:write"])

    listed = await eve.api_keys.list()
    assert minted["id"] in {k["id"] for k in listed}
    assert all("hash" not in k and "plaintext" not in k for k in listed)

    await eve.api_keys.revoke(minted["id"])
    with pytest.raises(prama.UnauthorisedError):
        await narrow.auth.me()
    await eve.close()


async def test_an_admin_sees_and_revokes_every_key_but_a_holder_only_their_own(
    client: AsyncClient,
) -> None:
    await client.principals.create("fay", roles=["steward"], password=STEWARD_PASSWORD)
    fay = await _sign_in(client, "fay", STEWARD_PASSWORD)
    theirs = await fay.api_keys.create("notebook", ["report:read"])

    everything = await client.api_keys.list_all()
    row = next(k for k in everything if k["id"] == theirs["id"])
    assert row["owner"] == "fay" and row["state"] == "active"

    # A holder cannot revoke somebody else's key: it is "not found" to them.
    mine = await client.api_keys.create("admin-script", ["report:read"])
    with pytest.raises(prama.NotFoundError):
        await fay.api_keys.revoke(mine["id"])
    # A holder cannot see the estate's keys at all.
    with pytest.raises(prama.ForbiddenError):
        await fay.api_keys.list_all()

    revoked = await client.api_keys.revoke_any(theirs["id"])
    assert revoked["state"] == "revoked"
    # The audit log names the key itself, not "None": its id is minted before
    # the record of its creation is written.
    trail = await client.audit.list(object_kind="api_key", object_id=theirs["id"])
    assert sorted(e["action"] for e in trail) == ["api_key.create", "api_key.revoke"]
    with pytest.raises(prama.UnauthorisedError):
        await client.as_key(theirs["plaintext"]).auth.me()

    # An administrator may mint a key that acts as a service, with explicit scopes.
    await client.principals.create("svc-report", kind="service")
    issued = await client.api_keys.issue("svc-report", "nightly", ["report:read"], days=30)
    service = client.as_key(issued["plaintext"])
    me = await service.auth.me()
    assert me["username"] == "svc-report" and me["scopes"] == ["report:read"]
    await fay.close()


async def test_changing_my_own_password_needs_the_current_one(client: AsyncClient) -> None:
    with pytest.raises(prama.ForbiddenError):
        await client.account.change_password("not-the-password", "a-brand-new-one-1")
    await client.account.change_password(PASSWORD, "a-brand-new-one-1")
    with pytest.raises(prama.UnauthorisedError):
        await _sign_in(client, "ada", PASSWORD)
    fresh = await _sign_in(client, "ada", "a-brand-new-one-1")
    account = await fresh.account.get()
    assert account["username"] == "ada" and "admin" in account["roles"]
    await fresh.close()


async def test_roles_config_and_the_audit_log(client: AsyncClient) -> None:
    catalogue = await client.roles.list()
    by_name = {r["name"]: r for r in catalogue["roles"]}
    assert by_name["admin"]["permissions"] == ["*"]
    assert "control:approve" not in by_name["steward"]["permissions"]
    assert "control:approve" in catalogue["scopes"]

    shown = await client.config.show(provenance=True)
    # The test configuration carries a session secret; it must not come back.
    assert shown["values"]["security.session_secret"] == "***"
    assert "test-only-not-a-secret" not in str(shown)
    assert shown["provenance"]["database.dialect"]

    made = await client.principals.create("gil", roles=["auditor"])
    await client.principals.disable("gil")
    events = await client.audit.list(object_kind="principal", object_id=made["id"])
    assert sorted(e["action"] for e in events) == ["principal.create", "principal.disabled"]
    me = await client.auth.me()
    assert {e["actor_id"] for e in events} == {me["principal_id"]}

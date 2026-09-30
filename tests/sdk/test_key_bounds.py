"""A person's key is never worth more than the person, as they are now.

A key keeps the scopes it was minted with; a person's roles change. Before
this, taking somebody's approver role left every key they held able to approve
until it expired, 12 hours for a sign-in and up to a year for a minted key.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import prama_sdk as prama
import pytest
from prama_sdk import AsyncClient

PASSWORD = "key-bounds-password-1"


async def test_changing_somebodys_roles_narrows_the_keys_they_hold(client: AsyncClient) -> None:
    await client.principals.create("olu", roles=["owner"], password=PASSWORD)
    anonymous = AsyncClient(app=client._app)
    issued = await anonymous.auth.token("olu", PASSWORD, tenant="acme-bank")
    olu = client.as_key(issued["api_key"])
    assert "declaration:approve" in (await olu.auth.me())["effective_scopes"]
    # Held, because Tier 1 needs an approver; the admin declared it, so olu may approve.
    trades = await client.datasets.declare("Trades", criticality=1, description="Trades.")
    assert trades["lifecycle_state"] == "proposed"

    # The owner becomes a steward. The same key, still unexpired, now approves nothing.
    await client.principals.set_roles("olu", ["steward"])
    me = await olu.auth.me()
    assert "declaration:*" in me["scopes"]  # what the key was minted with
    assert "declaration:approve" not in me["effective_scopes"]  # what it may do now
    with pytest.raises(prama.ForbiddenError, match="roles no longer grant"):
        await olu.datasets.approve(trades["id"], reason="still an owner?")
    # What the new role does grant, the key still does: it is narrowed, not revoked.
    assert (await olu.datasets.get(trades["id"]))["name"] == "Trades"

    # And a key minted now cannot carry what the roles no longer grant.
    with pytest.raises(prama.PramaError):
        await olu.api_keys.create("sneaky", ["control:approve"])
    for c in (olu, anonymous):
        await c.close()

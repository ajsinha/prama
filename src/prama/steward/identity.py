"""A steward's identity: a service principal, a human sponsor, a propose-only key.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from prama.core.errors import ValidationError

#: What a steward may do: read, call models through the gateway, and nothing
#: that decides. Its outputs are proposals and notes for people.
STEWARD_SCOPES: tuple[str, ...] = (
    "llm:use",
    "declaration:read",
    "relationship:read",
    "control:read",
    "incident:read",
    "evidence:read",
    "report:read",
)

#: Never, whatever is asked: approving, confirming, signing, administering.
#: An agent that could approve its own proposal would be adjudicating (CON-007).
FORBIDDEN: frozenset[str] = frozenset(
    {"*", "admin", "control:approve", "attestation:sign", "relationship:write", "declaration:write"}
)

#: A steward's key lives this long before it must be rotated.
KEY_DAYS = 30


def check_scopes(scopes: list[str]) -> list[str]:
    refused = sorted(set(scopes) & FORBIDDEN)
    if refused:
        raise ValidationError(
            f"a steward may not hold {', '.join(refused)}",
            remedy="Stewards read and propose; a person approves, confirms and signs.",
            context={"refused": refused},
        )
    return sorted(set(scopes))


async def create(
    uow: Any, tenant_id: str, name: str, *, sponsor_id: str, scopes: list[str] | None = None
) -> tuple[Any, str]:
    """A new steward and the one copy of its key's plaintext."""
    from prama.db.security import ApiKeyIssuer
    from prama.security.accounts import USERNAME

    username = f"steward-{name}"
    if not USERNAME.match(username):
        raise ValidationError(
            f"{name!r} is not a usable steward name",
            remedy="Use letters, digits, dot, underscore and hyphen.",
        )
    granted = check_scopes(scopes or list(STEWARD_SCOPES))
    principal = uow.principals.create(
        tenant_id=tenant_id, username=username, display_name=f"Steward {name}", kind="service"
    )
    await uow.flush()
    issued = ApiKeyIssuer().issue(environment="agent")
    uow.api_keys.create(
        tenant_id=tenant_id,
        principal_id=str(principal.id),
        name=f"steward {name}",
        key_prefix=issued.prefix,
        key_hash=issued.hash,
        scopes=granted,
        expires_at=datetime.now(UTC) + timedelta(days=KEY_DAYS),
        created_by=sponsor_id,
    )
    steward = await uow.stewards.create(
        tenant_id, name=name, principal_id=str(principal.id), sponsor_id=sponsor_id
    )
    return steward, issued.plaintext


async def set_state(uow: Any, tenant_id: str, steward: Any, state: str, *, by: str | None) -> None:
    """The kill switch: pause (no new tasks), stop (running tasks cancelled),
    revoke (key revoked and the principal disabled, so nothing it holds works)."""
    from prama.core.clock import utc_now

    if state not in ("active", "paused", "stopped", "revoked"):
        raise ValidationError(f"{state!r} is not a steward state", remedy="Use the page's buttons.")
    if steward.state == "revoked" and state != "revoked":
        raise ValidationError(
            "a revoked steward stays revoked", remedy="Create a new steward if one is needed."
        )
    steward.state = state
    if state in ("stopped", "revoked"):
        await uow.stewards.cancel_open_tasks(tenant_id, steward.id)
    if state == "revoked":
        for key in await uow.api_keys.active_for_principal(steward.principal_id):
            key.revoked_at = utc_now()
        principal = await uow.principals.get(steward.principal_id)
        if principal is not None:
            principal.status = "disabled"
            principal.updated_at = utc_now()
    uow.audit.record(
        tenant_id=tenant_id,
        action=f"steward.{state}",
        object_kind="steward",
        object_id=str(steward.id),
        actor_id=by,
    )
    await uow.flush()

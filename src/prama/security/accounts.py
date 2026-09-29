"""Accounts: the built-in roles, what a username may be, and granting a role.

Shared by the CLI (``prama principal``) and the console's administration
pages, so the two cannot come to disagree about what "steward" permits. It was
in ``prama.cli.principal`` until the console needed it too, and a web page
importing the CLI would have been the wrong dependency.

Nothing here imports SQLAlchemy: it talks to DAOs through the unit of work.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
from typing import Any

USERNAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")

#: The roles a fresh estate gets, and what each one may do.
#:
#: Four, not fourteen. A permission model nobody can hold in their head is one
#: nobody audits, and the separation that actually matters in this product is
#: between *proposing* a control and *approving* one — the rest is detail that
#: a deployment can add for itself.
BUILTIN_ROLES: dict[str, tuple[str, list[str]]] = {
    "admin": (
        "Everything, including creating other people.",
        ["*"],
    ),
    "owner": (
        "Declares datasets and approves controls. The business owner of an estate.",
        [
            "declaration:*",
            "relationship:*",
            "control:approve",
            "control:read",
            "attestation:sign",
            # Signing a thing you cannot read is not a permission set anybody
            # writes down on purpose. Without this the owner — the role that
            # exists to attest — could sign an attestation and open neither the
            # draft it was signing nor its own signed record. QA round 3, Q-67.
            "attestation:read",
            "evidence:read",
            "report:read",
            "llm:use",
            "comment:write",
            "contract:check",
        ],
    ),
    "steward": (
        "Works incidents and breaks; proposes controls but does not approve them.",
        [
            "control:propose",
            "control:read",
            "incident:*",
            "break:*",
            "evidence:read",
            "report:read",
            "declaration:read",
            # Drafting and explaining through the model gateway; a model's
            # output is a proposal, never a verdict (CON-007).
            "llm:use",
            # Asking and answering questions on the objects they work.
            "comment:write",
            "contract:check",
        ],
    ),
    "auditor": (
        "Reads everything and changes nothing.",
        [
            "control:read",
            "declaration:read",
            "relationship:read",
            "evidence:read",
            "report:read",
            "attestation:read",
        ],
    ),
}


async def grant_roles(uow: Any, tenant: str, principal: Any, wanted: list[str]) -> list[str]:
    """Grant roles, creating the built-in ones on first use.

    Created lazily rather than at ``db init``: a role nobody holds is a row that
    has to be explained, and an estate that never signs anybody in should not
    carry four of them.
    """
    granted: list[str] = []
    for name in wanted:
        role = await uow.roles.by_name(tenant, name)
        if role is None:
            description, permissions = BUILTIN_ROLES[name]
            role = uow.roles.create(
                tenant_id=tenant,
                name=name,
                permissions=permissions,
                description=description,
                builtin=True,
            )
            await uow.flush()
        await uow.roles.grant(str(principal.id), str(role.id))
        granted.append(name)
    return granted

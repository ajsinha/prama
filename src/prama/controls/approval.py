"""Activating a control: the one way a control begins to run, held to its tier.

The approval policy (``prama.semantic.policy.ApprovalPolicy``) governed
declarations only. Activating a control needed the ``control:approve`` scope
and nothing else, so the author of a Tier-1 control could write it and switch
it on alone: segregation of duties stopped at the dataset and never reached
the rule that checks it. Every activation now comes through here.

Who the *maker* is decides it. A control a person wrote (in the studio, over
the API, imported) records that person as its author, and at Tier 1 somebody
else must activate it. A control Prama derived or mined records no author: the
derivation is the maker, and the person accepting it is the check.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.core.errors import NotFoundError, ValidationError
from prama.semantic.policy import ApprovalPolicy


async def activate(
    uow: Any,
    control_id: str,
    *,
    tenant_id: str,
    approver: str | None,
    reason: str = "",
    policy: ApprovalPolicy | None = None,
) -> Any:
    """Approve *control_id* so it runs, if *approver* may approve it at its tier."""
    current = await uow.controls.current(control_id, tenant_id=tenant_id)
    if current is None:
        raise NotFoundError(
            f"control {control_id!r} does not exist in this estate",
            remedy="Check the identifier, or list the controls.",
            context={"control_id": control_id},
        )
    rules = policy or ApprovalPolicy()
    tier = int(current.criticality)
    if rules.for_criticality(tier).needs_approver and not approver:
        raise ValidationError(
            f"a Tier-{tier} control needs a named approver to start running",
            remedy="Approve it as a signed-in person, so the record says who agreed.",
            context={"control_id": control_id, "criticality": tier},
        )
    if approver:
        rules.check_approver(
            criticality=tier,
            authored_by=current.authored_by,
            approver=approver,
            what="control",
        )
    return await uow.controls.activate(
        control_id,
        tenant_id=tenant_id,
        approved_by=approver or "system",
        reason=reason or "accepted",
    )


__all__ = ["activate"]

"""SCIM provisioning: deciding what the directory's view means for an account.

SCIM is how a directory tells a downstream system that somebody joined, changed
team, or left. The protocol is tedious and the decisions are not, so this module
is the decisions: given what the directory now says and what Prama currently
holds, what should change?

**Nobody is ever deleted.** A SCIM ``DELETE`` deactivates. The person signed
things — approved a control, attested a period — and those records name them.
Deleting the account leaves an attestation signed by a principal that does not
exist, which is a hole in the audit trail rather than a tidy-up. Deactivation
is the operation the protocol actually needs: it stops sign-in, which is the
point, and keeps the identity the evidence refers to.

**Deprovisioning is not the same as demotion, and both happen.** A person who
leaves the owners group should lose the owner role and keep their account; a
person who leaves the company should keep neither. The directory expresses these
differently — a group change versus ``active: false`` — and conflating them
either locks out somebody who moved desk or leaves a leaver signed in.

**Roles are never merged.** The directory is authoritative for group membership,
so the role set is *replaced*, not unioned with what was there. A union means a
role granted once is granted forever, and the group somebody was removed from
six months ago still confers it.

**A group Prama does not map grants nothing**, and the unmapped ones are
reported. Silently defaulting is how everybody in the directory becomes an
owner; silently ignoring is how somebody signs in successfully and can see
nothing, which looks exactly like a permissions bug.

**The last administrator cannot be deprovisioned.** A directory
misconfiguration that deactivates every admin locks everybody out of the tenant
with no way back in that does not involve the database. This refuses and says
why.

What this module is not: an HTTP endpoint. The routes that speak SCIM's wire
format are not written, and `docs/corpus/19` says so. What is here is the part where
being wrong is expensive.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from prama.security.oidc import ClaimMapping

__all__ = [
    "Account",
    "Change",
    "Decision",
    "ScimUser",
    "reconcile",
]


class Change(enum.Enum):
    """What provisioning decided."""

    CREATE = "create"
    UPDATE = "update"
    DEACTIVATE = "deactivate"
    REACTIVATE = "reactivate"
    #: The directory and Prama already agree.
    NONE = "none"
    #: Refused, with a reason. Distinct from NONE: nothing changed, and
    #: something should have.
    REFUSED = "refused"

    @property
    def alters_anything(self) -> bool:
        return self not in (Change.NONE, Change.REFUSED)


@dataclasses.dataclass(frozen=True, slots=True)
class ScimUser:
    """What the directory says, reduced to what Prama acts on."""

    external_id: str
    user_name: str
    active: bool = True
    email: str = ""
    display_name: str = ""
    groups: tuple[str, ...] = ()

    @classmethod
    def from_resource(cls, payload: Mapping[str, Any]) -> ScimUser:
        """From a SCIM 2.0 User resource.

        ``active`` defaults to true when absent, which is what the
        specification says — but the distinction matters here: a PATCH that
        omits it is not a request to activate anybody, and callers building a
        partial update should not route it through this.
        """
        groups = payload.get("groups") or []
        names = []
        for group in groups:
            if isinstance(group, Mapping):
                names.append(str(group.get("display") or group.get("value") or ""))
            else:
                names.append(str(group))
        emails = payload.get("emails") or []
        email = ""
        for entry in emails:
            if isinstance(entry, Mapping):
                if entry.get("primary") or not email:
                    email = str(entry.get("value", ""))
            elif not email:
                email = str(entry)
        return cls(
            external_id=str(payload.get("externalId") or payload.get("id") or ""),
            user_name=str(payload.get("userName", "")),
            active=bool(payload.get("active", True)),
            email=email,
            display_name=str((payload.get("name") or {}).get("formatted", ""))
            or str(payload.get("displayName", "")),
            groups=tuple(name for name in names if name),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Account:
    """What Prama currently holds for somebody."""

    external_id: str
    user_name: str
    active: bool = True
    email: str = ""
    display_name: str = ""
    roles: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class Decision:
    """What to do, and everything needed to argue with it."""

    change: Change
    external_id: str
    user_name: str = ""
    roles: tuple[str, ...] = ()
    #: Fields whose value should change, old → new. Named rather than counted:
    #: an audit record saying "3 fields changed" answers nothing.
    fields: tuple[tuple[str, str, str], ...] = ()
    #: Directory groups that map to no Prama role. Reported, never ignored.
    unmapped_groups: tuple[str, ...] = ()
    reason: str = ""

    @property
    def applies(self) -> bool:
        return self.change.alters_anything

    def describe(self) -> str:
        if self.change is Change.REFUSED:
            return f"refused: {self.reason}"
        if self.change is Change.NONE:
            return "the directory and Prama already agree"
        head = f"{self.change.value} {self.user_name or self.external_id}"
        if self.fields:
            head += ": " + ", ".join(f"{name} {old!r} to {new!r}" for name, old, new in self.fields)
        if self.roles:
            head += f" [roles: {', '.join(self.roles)}]"
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "change": self.change.value,
            "external_id": self.external_id,
            "user_name": self.user_name,
            "roles": list(self.roles),
            "fields": [{"field": f, "from": o, "to": n} for f, o, n in self.fields],
            "unmapped_groups": list(self.unmapped_groups),
            "reason": self.reason,
            "message": self.describe(),
        }


def reconcile(
    user: ScimUser,
    account: Account | None,
    *,
    mapping: ClaimMapping,
    other_active_admins: int = 0,
    admin_role: str = "admin",
) -> Decision:
    """What the directory's view means for this account.

    ``other_active_admins`` counts the *other* active administrators in the
    tenant. It is a caller's job to supply because only the caller can see the
    tenant, and getting it wrong in the safe direction (too low) only makes this
    refuse more often.
    """
    roles = mapping.roles_for(user.groups)
    unmapped = mapping.unmapped(user.groups)

    if not user.external_id:
        return Decision(
            change=Change.REFUSED,
            external_id="",
            user_name=user.user_name,
            reason=(
                "the directory sent no external id, and without one this cannot "
                "be matched to an account — a create would make a duplicate on "
                "every sync"
            ),
        )

    if account is None:
        if not user.active:
            # A leaver the directory is telling us about for the first time.
            # Creating a deactivated account would put somebody in the estate
            # who was never in it.
            return Decision(
                change=Change.NONE,
                external_id=user.external_id,
                user_name=user.user_name,
                unmapped_groups=unmapped,
                reason="the directory sent an inactive user Prama has never held",
            )
        return Decision(
            change=Change.CREATE,
            external_id=user.external_id,
            user_name=user.user_name,
            roles=roles,
            unmapped_groups=unmapped,
            reason="the directory has somebody Prama does not",
        )

    if not user.active and account.active:
        if admin_role in account.roles and other_active_admins == 0:
            # A directory misconfiguration that deactivates every admin locks
            # everybody out of the tenant with no way back that does not
            # involve the database.
            return Decision(
                change=Change.REFUSED,
                external_id=user.external_id,
                user_name=account.user_name,
                roles=account.roles,
                reason=(
                    "this is the last active administrator, and deactivating "
                    "them locks everybody out of the tenant with no way back "
                    "in that does not involve the database"
                ),
            )
        return Decision(
            change=Change.DEACTIVATE,
            external_id=user.external_id,
            user_name=account.user_name,
            roles=account.roles,
            unmapped_groups=unmapped,
            reason=(
                "the directory says this person has left. The account is "
                "deactivated and kept: they signed things, and deleting them "
                "leaves an attestation signed by a principal that does not exist"
            ),
        )

    if user.active and not account.active:
        return Decision(
            change=Change.REACTIVATE,
            external_id=user.external_id,
            user_name=user.user_name,
            roles=roles,
            unmapped_groups=unmapped,
            reason="the directory has this person active again",
        )

    changed = _differences(user, account, roles)
    if not changed and tuple(roles) == tuple(account.roles):
        return Decision(
            change=Change.NONE,
            external_id=user.external_id,
            user_name=account.user_name,
            roles=account.roles,
            unmapped_groups=unmapped,
        )

    return Decision(
        change=Change.UPDATE,
        external_id=user.external_id,
        user_name=user.user_name or account.user_name,
        # Replaced, never unioned: the directory is authoritative for group
        # membership, and a union means a role granted once is granted forever.
        roles=roles,
        fields=changed,
        unmapped_groups=unmapped,
        reason="the directory and Prama disagree about this account",
    )


def _differences(
    user: ScimUser, account: Account, roles: Sequence[str]
) -> tuple[tuple[str, str, str], ...]:
    changed: list[tuple[str, str, str]] = []
    for field, was, now in (
        ("user_name", account.user_name, user.user_name),
        ("email", account.email, user.email),
        ("display_name", account.display_name, user.display_name),
    ):
        # An absent field in a partial update is not a request to blank one.
        # SCIM PATCH omits what it is not changing, and treating omission as
        # deletion wipes an email address on every sync.
        if now and now != was:
            changed.append((field, was, now))
    if tuple(roles) != tuple(account.roles):
        changed.append(("roles", ", ".join(account.roles), ", ".join(roles)))
    return tuple(changed)


def reconcile_all(
    users: Iterable[ScimUser],
    accounts: Mapping[str, Account],
    *,
    mapping: ClaimMapping,
    admin_role: str = "admin",
) -> tuple[Decision, ...]:
    """A whole sync.

    The admin count is computed once across the accounts rather than per user,
    so a batch that deactivates several administrators refuses on the one that
    would leave none — not on the first one it happens to reach.
    """
    active_admins = {
        identity
        for identity, account in accounts.items()
        if account.active and admin_role in account.roles
    }
    decisions = []
    for user in users:
        account = accounts.get(user.external_id)
        others = len(active_admins - {user.external_id})
        decision = reconcile(
            user,
            account,
            mapping=mapping,
            other_active_admins=others,
            admin_role=admin_role,
        )
        if decision.change is Change.DEACTIVATE:
            # Subsequent decisions in this batch must see the smaller pool, or
            # a sync deactivating three of four admins leaves none.
            active_admins.discard(user.external_id)
        decisions.append(decision)
    return tuple(decisions)

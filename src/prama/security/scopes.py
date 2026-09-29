"""What a credential is allowed to do, and the one place that decides it.

Scopes were computed, stored on every API key, carried into every request and
read by nothing — finding S4 of ``docs/reviews/2026-09-11-adversarial-review.md``.
``Principal.has_permission`` existed and was called by no code and no test. A
permission model nobody consults is not a weaker control than none; it is worse,
because the key record, the admin screen and the audit log all read as though an
authorisation decision were being made.

The matcher lives here rather than on either of its two callers because it had
already been written once and was about to be written twice. A rule restated in
a second place drifts, silently, in the flattering direction.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterable

#: **The vocabulary. One of them.** Every scope the product enforces anywhere,
#: with the sentence a person reading an audit log needs.
#:
#: Finding H5 was two vocabularies a comment insisted were one; the first pass
#: at finding S4 briefly made it three, by inventing `semantic:read` and
#: `semantic:write` for the API while `BUILTIN_ROLES` granted `declaration:*`
#: and `control:approve`. A key issued to an `owner` would have held every
#: permission that role names and been refused by every route — a permission
#: model that cannot be satisfied is worse than one that is not enforced,
#: because it fails in production rather than in review.
#:
#: `prama.security.accounts.BUILTIN_ROLES` grants from this list and nothing else,
#: and `tests/architecture/test_scopes.py` checks both directions: a role may
#: not grant a permission no route requires, and no route may require a
#: permission no role can hold.
SCOPES: dict[str, str] = {
    "declaration:read": "read the semantic layer: domains, datasets, attributes, concepts",
    "declaration:write": "declare, amend, correct and retire semantic objects",
    "relationship:read": "read declared and discovered relationships",
    "relationship:write": "declare a relationship, confirm one, or reject one",
    "control:read": "read controls and their history",
    "control:propose": "author a control, which somebody else then approves",
    "control:approve": "activate a control, or suppress a running one",
    "incident:read": "read incidents",
    "incident:write": "triage and dispose of incidents",
    "break:read": "read reconciliation breaks",
    "break:write": "assign, explain and accept breaks",
    "evidence:read": "read evidence records and run history",
    "report:read": "read scorecards and reports",
    "attestation:read": "read attestations",
    "attestation:sign": "sign an attestation",
    "agent:work": "claim, report on and ask approval for steward agent tasks",
    "llm:use": "send prompts to a model through the gateway (budgeted, audited)",
    "comment:write": "comment on governed objects, mention colleagues, resolve threads",
    # Its own scope rather than `declaration:read`, because the requests upload
    # files and so are POSTs, and a POST under a read scope is what
    # `tests/architecture/test_scopes.py` exists to catch; and rather than
    # `declaration:write`, because a CI key that gates a build on a contract
    # must not be able to amend the estate.
    "contract:check": "read a data contract, check rows against it, diff two versions of data",
    "admin": "manage principals, roles and API keys",
    "tenant:admin": "list the estates on this installation and create new ones",
}

#: Held by a key that is deliberately unrestricted. Spelled out because an
#: empty scope list must mean "nothing", not "everything" — the opposite
#: default is how a credential created before scopes existed becomes a
#: superuser the day they are enforced.
WILDCARD = "*"


def permits(granted: Iterable[str], wanted: str) -> bool:
    """Whether *granted* satisfies *wanted*.

    Wildcards are supported one level deep: a holder of ``control:*`` satisfies
    ``control:approve``. Deeper globbing is deliberately absent — a permission
    model nobody can hold in their head is one nobody audits.

    An empty ``granted`` permits nothing. That is the whole point of the
    distinction: "no scopes recorded" is not "no restriction".
    """
    for grant in granted:
        if grant in (WILDCARD, wanted):
            return True
        if grant.endswith(":*") and wanted.startswith(grant[:-1]):
            return True
    return False


def unknown(scopes: Iterable[str]) -> list[str]:
    """Scope names that are not in :data:`SCOPES`, ignoring wildcards.

    A scope that does not exist can never be satisfied, so granting one is a
    silent denial. Callers that mint credentials check this rather than
    discovering it when somebody is refused.
    """
    return sorted(
        scope
        for scope in scopes
        if scope != WILDCARD and not scope.endswith(":*") and scope not in SCOPES
    )


__all__ = ["SCOPES", "WILDCARD", "permits", "unknown"]

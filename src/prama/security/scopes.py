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

#: Every scope the API enforces, with the sentence a person reading an audit
#: log needs. Declared rather than inferred, so `prama principal create` and
#: the console can offer the real list and a typo in a route is a test failure
#: rather than a permission nobody can ever hold.
SCOPES: dict[str, str] = {
    "semantic:read": "read declarations: datasets, attributes, relationships, journeys",
    "semantic:write": "declare, amend, correct and retire semantic objects",
    "control:read": "read controls and their history",
    "control:write": "author and amend controls",
    "control:approve": "activate a control, or suppress a running one",
    "evidence:read": "read evidence records and run history",
    "admin": "manage principals, roles and API keys",
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

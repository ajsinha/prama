"""Each run-backed console screen asks for the permission it actually needs.

QA round 4 triage, `UI-009`. `OperationsRoutes` never sets `SUBJECT`, so all
four of its screens fall back to `UiRoutes.DEFAULT_READ` — `declaration:read`:

    self.page("/incidents", ...)        # -> declaration:read
    self.page("/reconciliation", ...)   # -> declaration:read
    self.page("/scorecards", ...)       # -> declaration:read
    self.page("/evidence", ...)         # -> declaration:read

They serve four different subjects, and the vocabulary has a scope for each:
`incident:read`, `break:read`, `report:read`, `evidence:read`. `TriageRoutes`
sets `SUBJECT = "incident"` and gets this right, which is how the omission shows
— the incident *detail* route requires `incident:read` while the incident *list*
does not.

**The direction that matters.** A principal holding `declaration:read` and
nothing else can read the semantic layer, which is what that scope is for. Today
they can also read every incident, every reconciliation break, every scorecard
and the evidence chain. A scope granted to let somebody see the dataset
catalogue should not carry the estate's open incidents with it.

A single class-level `SUBJECT` cannot fix this — four screens, four subjects —
so each declares its own.

**What a careless version of this test would do.** Sign in as an `auditor`, who
holds every read scope, and check all four screens render. That passes before
the fix and after it, because the auditor was never the person affected. The
test has to hold a scope that *should not* open a screen.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

#: path -> the scope the screen's own subject implies.
EXPECTED_SCOPES = {
    "/incidents": "incident:read",
    "/reconciliation": "break:read",
    "/scorecards": "report:read",
    "/evidence": "evidence:read",
}


def declared_scopes() -> dict[str, str]:
    """What `OperationsRoutes.register` actually asks for, per path."""
    from prama.web.routes.operations_routes import OperationsRoutes

    seen: dict[str, str] = {}

    class _Spy(OperationsRoutes):
        def __init__(self) -> None:  # no router, no app; only the registrations
            pass

        def page(self, path, _handler, **options):  # type: ignore[override]
            seen[path] = options.get("scope", "auto")

    _Spy().register()
    return seen


@pytest.mark.parametrize("path,expected", sorted(EXPECTED_SCOPES.items()))
def test_each_screen_asks_for_its_own_subject(path: str, expected: str) -> None:
    declared = declared_scopes()
    assert declared.get(path) == expected, (
        f"{path} requires {declared.get(path)!r}, not {expected!r}. A caller holding "
        "declaration:read to browse the dataset catalogue should not also be reading "
        "the estate's incidents, breaks, scorecards and evidence chain."
    )


def test_no_operations_screen_still_falls_back_to_the_declaration_default() -> None:
    """Stated separately, because the fallback is silent.

    `page(scope="auto")` derives a scope and never complains, so a screen added
    to this class tomorrow inherits `declaration:read` exactly as these four did
    — with nothing failing. This fails.
    """
    from prama.web.routes.base import UiRoutes

    inherited = [
        path
        for path, scope in declared_scopes().items()
        if scope in ("auto", UiRoutes.DEFAULT_READ)
    ]
    assert not inherited, (
        f"these screens inherit the declaration default: {inherited}. Each serves a "
        "different subject and must name the scope that subject implies."
    )


def test_every_declared_scope_is_one_the_vocabulary_has() -> None:
    """A scope nobody can hold is a screen nobody can open.

    `page()` refuses an undeclared scope at registration, so this cannot fail
    silently — but it can fail at import time in a way that reads as unrelated,
    and saying so here makes the reason obvious.
    """
    from prama.security.scopes import SCOPES

    for path, scope in declared_scopes().items():
        assert scope in SCOPES, f"{path} requires {scope!r}, which is not in the vocabulary"

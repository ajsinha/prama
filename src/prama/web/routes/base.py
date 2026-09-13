"""What every route class has in common.

Route classes register themselves in ``__init__``, exactly as DishtaYantra's
do, so the application factory constructs an object and does not also have to
know which paths that object claims. Adding a page is then a change to one
file rather than to two.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI

from prama.core.log import get_logger
from prama.web.deps import ui_scope

_log = get_logger(__name__)


class UiRoutes:
    """Base for a group of pages."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.register()

    def register(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    #: The scope a page needs when it does not say. Reading is the default
    #: because the console is mostly reading; a page that writes says so.
    #: What this group of pages is *about*. `scope="auto"` builds the required
    #: permission from it, so an incidents page asks for `incident:read` rather
    #: than for a declaration scope that has nothing to do with it.
    #:
    #: It used to be fixed at `declaration`, for all forty-seven auto routes.
    #: The console's whole permission matrix was therefore accidental: a person
    #: holding `incident:read` and nothing else was refused the incidents page,
    #: and a person holding `declaration:write` could reach the break workbench
    #: (QA finding UI-005). The scopes existed, were checked, and described the
    #: wrong thing.
    SUBJECT = "declaration"
    #: The scope a mutating page in this group requires. Declared separately
    #: from SUBJECT because the vocabulary is finer than read/write and says
    #: so: authoring a control is `control:propose`, signing an attestation is
    #: `attestation:sign`, and neither is a "write". Deriving `{subject}:write`
    #: would have invented three scopes nobody granted and locked every holder
    #: out of the pages they are meant to use.
    WRITE_SCOPE: str | None = None
    DEFAULT_READ = "declaration:read"
    DEFAULT_WRITE = "declaration:write"

    def page(
        self,
        path: str,
        handler: Callable[..., Any],
        *,
        name: str,
        methods: list[str] | None = None,
        scope: str | None = "auto",
    ) -> None:
        """Register one page.

        ``include_in_schema=False`` always: the OpenAPI document describes the
        API that other programs call, and filling it with HTML pages makes the
        generated client unusable and the document unreadable.

        *scope* is the permission the caller must hold. ``"auto"`` derives it
        from the HTTP method — a page that changes something needs a write
        scope — and ``None`` marks a page as genuinely anonymous, which is the
        sign-in flow and nothing else.

        Enforcing here rather than in each handler is deliberate. The console
        has forty-eight routes registered through this one call, and finding S4
        was not that one of them forgot a check but that none of them had one:
        `ui_caller` had been putting the principal's permissions on the identity
        for waves and nothing read them. A guard applied at registration cannot
        be omitted by the next page.
        """
        verbs = methods or ["GET"]
        if scope == "auto":
            mutating = bool({"POST", "PUT", "PATCH", "DELETE"} & set(verbs))
            if mutating:
                scope = self.WRITE_SCOPE or f"{self.SUBJECT}:write"
            else:
                scope = f"{self.SUBJECT}:read"
            # Checked here, at registration, so a derived scope that nobody
            # grants cannot reach a running console. The vocabulary is finer
            # than read/write — `control:propose`, `attestation:sign` — so a
            # class whose write verb is not literally "write" must say so, and
            # this is where it finds out it has not.
            #
            # A page requiring a scope no role can hold is unreachable by
            # everybody, which reads as a broken page rather than as a
            # permission error. Failing at import makes it a five-second fix
            # instead of a support call.
            from prama.security.scopes import SCOPES

            if scope not in SCOPES:
                raise ValueError(
                    f"{type(self).__name__} derives the scope {scope!r} for "
                    f"{'/'.join(verbs)} {path}, and no such scope is declared. "
                    f"Add it to prama.security.scopes.SCOPES, or set WRITE_SCOPE "
                    f"on the class to the verb the vocabulary already has."
                )
        self.app.add_api_route(
            path,
            handler,
            methods=verbs,
            name=name,
            include_in_schema=False,
            dependencies=[] if scope is None else [Depends(ui_scope(scope))],
        )
        _log.debug("ui route %s -> %s (%s)", path, name, scope or "anonymous")

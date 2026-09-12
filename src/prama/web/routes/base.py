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

from prama.web.deps import ui_scope

from prama.core.log import get_logger

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
            scope = self.DEFAULT_WRITE if mutating else self.DEFAULT_READ
        self.app.add_api_route(
            path,
            handler,
            methods=verbs,
            name=name,
            include_in_schema=False,
            dependencies=[] if scope is None else [Depends(ui_scope(scope))],
        )
        _log.debug("ui route %s -> %s (%s)", path, name, scope or "anonymous")

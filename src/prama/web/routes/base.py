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

from fastapi import FastAPI

from prama.core.log import get_logger

_log = get_logger(__name__)


class UiRoutes:
    """Base for a group of pages."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.register()

    def register(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def page(
        self,
        path: str,
        handler: Callable[..., Any],
        *,
        name: str,
        methods: list[str] | None = None,
    ) -> None:
        """Register one page.

        ``include_in_schema=False`` always: the OpenAPI document describes the
        API that other programs call, and filling it with HTML pages makes the
        generated client unusable and the document unreadable.
        """
        self.app.add_api_route(
            path,
            handler,
            methods=methods or ["GET"],
            name=name,
            include_in_schema=False,
        )
        _log.debug("ui route %s -> %s", path, name)

"""Mounting the UI onto the API application.

One function, called by the application factory. It is a *mount* rather than a
second application because the UI and the API must agree about the database,
the configuration and the error taxonomy; running them as two processes that
merely happen to share a database is how the two drift apart.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from prama.core.config import Configuration
from prama.core.log import get_logger
from prama.web import rendering
from prama.web.deps import NotSignedIn
from prama.web.rendering import STATIC_DIR
from prama.web.routes import ROUTE_CLASSES

_log = get_logger(__name__)


def mount_ui(app: FastAPI, config: Configuration) -> None:
    """Attach the session, the static mount, and every route class."""
    # Shipped empty on purpose, and the refusal already lives in the config
    # layer: ``require_secret`` raises ``SecretMissingError`` with the remedy
    # attached. Restating the check here would give the same failure two
    # messages that could drift apart.
    secret = config.require_secret("security.session_secret")

    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie="prama_session",
        https_only=config.get_bool("security.cookies_https_only", True),
        same_site="lax",
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    rendering.install_globals()

    @app.exception_handler(NotSignedIn)
    async def _sign_in(request: Request, exc: NotSignedIn) -> Response:
        """A person without a session gets a sign-in page, not a 500."""
        _log.info("unauthenticated UI request for %s: %s", request.url.path, exc)
        return RedirectResponse(url="/sign-in", status_code=303)

    @app.get("/", include_in_schema=False, name="home")
    async def _home() -> RedirectResponse:
        return RedirectResponse(url="/estate", status_code=307)

    for route_class in ROUTE_CLASSES:
        route_class(app)

    _log.info("UI mounted: %d route classes, static from %s", len(ROUTE_CLASSES), STATIC_DIR)

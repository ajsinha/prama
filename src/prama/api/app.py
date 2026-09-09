"""The FastAPI application.

Assembled by a factory rather than created at import time, so a test can build
one against a scratch database without touching a module-level global — and so
that a future multi-tenant-per-process deployment remains possible.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from prama.api.deps import new_correlation_id
from prama.api.errors import prama_error_handler, unexpected_error_handler
from prama.api.routes import estate, graph, meta, semantic
from prama.core.config import Configuration, load_configuration
from prama.core.errors import PramaError
from prama.core.log import LoggingConfigurator, get_logger
from prama.db import Database
from prama.version import PRODUCT_TAGLINE, VERSION

_log = get_logger(__name__)

API_PREFIX = "/api/v1"

DESCRIPTION = f"""
**Prama — {PRODUCT_TAGLINE}**

The semantic layer API: declare datasets in business terms, describe what their
attributes mean, and state how datasets relate to one another. Those
declarations are what later compile into executable controls.

Every declaration is **bitemporal**. `valid_at` asks what was true at an
instant; `known_at` asks what we believed at an instant. After a correction the
two differ, and an evidence replay depends on the second.
"""


def create_app(config: Configuration | None = None, *, database: Database | None = None) -> FastAPI:
    """Build an application from a configuration.

    *database* is injectable so tests share one scratch database with their
    fixtures instead of racing a second connection to the same file.
    """
    config = config or load_configuration()
    LoggingConfigurator(
        level=config.get_str("logging.level", "INFO"),
        fmt=config.get_str("logging.format", "text"),
    ).apply()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = database is None
        db = database or Database.from_config(config)
        if owned:
            # Verifies the schema unless configuration says otherwise: a
            # mismatched schema produces failures that look like application
            # bugs, hours later, in unrelated code.
            await db.start()
        app.state.config = config
        app.state.database = db
        _log.info("prama %s ready on %s", VERSION, db.dialect.name)
        try:
            yield
        finally:
            if owned:
                await db.stop()

    app = FastAPI(
        title="Prama",
        version=VERSION,
        summary=PRODUCT_TAGLINE,
        description=DESCRIPTION,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
    )

    app.add_exception_handler(PramaError, prama_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)

    @app.middleware("http")
    async def correlate(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        """Every response carries a correlation id, whether or not it succeeded.

        It is the one thing a user can quote back to support, so it must survive
        the paths where everything else has gone wrong.
        """
        cid = new_correlation_id(request)
        response: Response = await call_next(request)
        response.headers["X-Correlation-Id"] = cid
        return response

    app.include_router(meta.router, prefix=API_PREFIX)
    app.include_router(semantic.router, prefix=API_PREFIX)
    app.include_router(graph.router, prefix=API_PREFIX)
    app.include_router(estate.router, prefix=API_PREFIX)

    # The console is mounted onto the same application rather than run beside
    # it, so the two cannot disagree about the database, the configuration or
    # the error taxonomy. It is a flag because a headless deployment — a worker
    # node, an API-only estate — should not be made to hold a session secret it
    # has no use for.
    if config.get_bool("web.enabled", True):
        from prama.web import mount_ui

        mount_ui(app, config)
    return app

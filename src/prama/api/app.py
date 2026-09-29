"""The FastAPI application.

Assembled by a factory rather than created at import time, so a test can build
one against a scratch database without touching a module-level global — and so
that a future multi-tenant-per-process deployment remains possible.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from prama.api.deps import new_correlation_id
from prama.api.errors import (
    prama_error_handler,
    router_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from prama.api.routes import (
    agents,
    collaboration,
    delegates,
    estate,
    graph,
    lineage,
    llm,
    meta,
    metadata,
    probes,
    semantic,
)
from prama.core.config import Configuration, load_configuration
from prama.core.errors import PramaError
from prama.core.log import LoggingConfigurator, get_logger
from prama.db import Database
from prama.packs import install_shipped
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
        # The always-on scheduler, supervised: it lives exactly as long as the
        # application and is cancelled with it, never a free-running task.
        from prama.core.concurrency.supervisor import RestartPolicy, TaskSupervisor
        from prama.execute.scheduler import from_config

        scheduler = from_config(config, db)
        app.state.scheduler = scheduler
        try:
            async with TaskSupervisor("scheduler") as supervisor:
                if scheduler is not None:
                    supervisor.spawn("tick", scheduler.loop, policy=RestartPolicy.ON_FAILURE)
                    _log.info(
                        "scheduler on: every %.0fs against %s",
                        scheduler.interval,
                        scheduler.against,
                    )
                if config.get_bool("agents.enabled", True):
                    from prama.steward.runner import loop as stewards

                    supervisor.spawn(
                        "stewards", lambda: stewards(db, config), policy=RestartPolicy.ON_FAILURE
                    )
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

    # Set now as well as in the lifespan, so the probes can read it on an
    # application whose lifespan has not run (a test transport, say).
    app.state.config = config
    from prama.telemetry import metrics
    from prama.telemetry.setup import configure as configure_telemetry

    metrics.BUILD.set(1, version=VERSION)
    configure_telemetry(config)

    app.add_exception_handler(PramaError, prama_error_handler)
    # Starlette and FastAPI answer these two with their own handlers unless we
    # claim them, producing bare `{"detail": ...}` JSON. They are the errors a
    # caller hits most — a mistyped path and a malformed parameter — and they
    # were the only ones this API did not emit as problem+json. QA round 4, B1.
    app.add_exception_handler(StarletteHTTPException, router_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)

    @app.middleware("http")
    async def correlate(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        """Every response carries a correlation id, whether or not it succeeded.

        It is the one thing a user can quote back to support, so it must survive
        the paths where everything else has gone wrong.
        """
        cid = new_correlation_id(request)
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            # Handled here rather than left to the outermost handler. Starlette
            # registers `add_exception_handler(Exception, …)` on
            # ServerErrorMiddleware, which sits *outside* this one — so an
            # unhandled exception propagated out through `call_next`, the line
            # below never ran, and the 500 was built beyond the reach of the
            # header. Every deliberate status carried a correlation id and the
            # one case where a user most needs something to quote did not
            # (QA finding API-006, and Q-24 before it).
            #
            # The same handler produces the body, so there is one error shape
            # and not two that drift apart.
            response = await unexpected_error_handler(request, exc)
        response.headers["X-Correlation-Id"] = cid
        # The route's template, never the raw path: /datasets/{id} is one
        # series, and a series per dataset id is how a metrics system falls over.
        route = getattr(request.scope.get("route"), "path", "") or "unmatched"
        metrics.HTTP_REQUESTS.inc(
            method=request.method, route=route, status=f"{response.status_code // 100}xx"
        )
        metrics.HTTP_SECONDS.observe(time.perf_counter() - started, route=route)
        return response

    # The console and the API author and check controls too, so the shipped
    # packs' functions must resolve here for the same reason they must in the
    # CLI — see prama.packs.install_shipped.
    install_shipped(disabled_plugins=config.get_list("plugins.disabled", []))

    app.include_router(probes.router)
    app.include_router(meta.router, prefix=API_PREFIX)
    app.include_router(semantic.router, prefix=API_PREFIX)
    app.include_router(graph.router, prefix=API_PREFIX)
    app.include_router(estate.router, prefix=API_PREFIX)
    app.include_router(lineage.router, prefix=API_PREFIX)
    app.include_router(llm.router, prefix=API_PREFIX)
    app.include_router(agents.router, prefix=API_PREFIX)
    app.include_router(delegates.router, prefix=API_PREFIX)
    app.include_router(metadata.router, prefix=API_PREFIX)
    app.include_router(collaboration.router, prefix=API_PREFIX)

    # The console is mounted onto the same application rather than run beside
    # it, so the two cannot disagree about the database, the configuration or
    # the error taxonomy. It is a flag because a headless deployment — a worker
    # node, an API-only estate — should not be made to hold a session secret it
    # has no use for.
    if config.get_bool("web.enabled", True):
        from prama.web import mount_ui

        mount_ui(app, config)
    return app

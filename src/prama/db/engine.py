"""Engine construction.

Two engines are built from one set of settings and one dialect:

* a **synchronous** engine for DDL — schema bootstrap, verification, and the
  CLI. DDL is rare, transactional, and far simpler to reason about
  synchronously.
* an **asynchronous** engine for everything else, because the API and the
  scheduler are async and a blocking driver in an event loop is a scale ceiling
  disguised as a convenience.

Both share the dialect's connect-time setup, so a pragma or a statement timeout
cannot apply on one path and not the other.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from prama.core.errors import DatabaseError
from prama.core.log import get_logger
from prama.db.dialects import Dialect
from prama.db.settings import DbSettings

_log = get_logger(__name__)


class EngineFactory:
    """Builds and caches the engines for one configuration.

    Engines are expensive and pooled; a process holds one of each. The factory
    is an object rather than a module function so a test — or a future
    multi-tenant-per-process deployment — can hold several without global state.
    """

    def __init__(self, settings: DbSettings, dialect: Dialect) -> None:
        self._settings = settings
        self._dialect = dialect
        self._sync: Engine | None = None
        self._async: AsyncEngine | None = None

    @property
    def settings(self) -> DbSettings:
        return self._settings

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    def sync_engine(self) -> Engine:
        if self._sync is None:
            self._dialect.prepare_filesystem()
            url = self._dialect.sync_url()
            try:
                engine = create_engine(url, **self._dialect.engine_kwargs(is_async=False))
            except SQLAlchemyError as exc:
                raise self._creation_error(url.render_as_string(hide_password=True), exc) from exc
            self._install_connect_hook(
                engine.sync_engine if hasattr(engine, "sync_engine") else engine
            )
            self._sync = engine
            _log.debug("sync engine created for %s", self._dialect.name)
        return self._sync

    def async_engine(self) -> AsyncEngine:
        if self._async is None:
            self._dialect.prepare_filesystem()
            url = self._dialect.async_url()
            try:
                engine = create_async_engine(url, **self._dialect.engine_kwargs(is_async=True))
            except SQLAlchemyError as exc:
                raise self._creation_error(url.render_as_string(hide_password=True), exc) from exc
            self._install_connect_hook(engine.sync_engine)
            self._async = engine
            _log.debug("async engine created for %s", self._dialect.name)
        return self._async

    def _install_connect_hook(self, engine: Any) -> None:
        dialect = self._dialect

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_connection: Any, _record: Any) -> None:
            dialect.on_connect(dbapi_connection)

    def _creation_error(self, url: str, exc: Exception) -> DatabaseError:
        return DatabaseError(
            f"could not create a {self._dialect.name} engine for {url}",
            code="DB.ENGINE_CREATE_FAILED",
            remedy=f"Check database.* configuration. {self._dialect.driver_hint}",
            context={"dialect": self._dialect.name, "url": url, "detail": str(exc)},
            cause=exc,
        )

    async def dispose(self) -> None:
        """Release both pools. Called on shutdown and between tests."""
        if self._async is not None:
            await self._async.dispose()
            self._async = None
        if self._sync is not None:
            self._sync.dispose()
            self._sync = None

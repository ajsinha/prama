"""Sessions and the unit of work.

A ``UnitOfWork`` owns one transaction and the repositories that act within it.
Services take a unit of work, not a session: they never see SQLAlchemy, which is
what keeps the layering test honest, and they cannot accidentally commit half of
a change because commit is the boundary's decision, not theirs.

    async with database.unit_of_work() as uow:
        tenant = await uow.tenants.get(tenant_id)
        await uow.audit.record(event)
        # commit on clean exit, rollback on any exception

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from prama.core.errors import ConflictError, DatabaseError
from prama.core.log import get_logger
from prama.db.engine import EngineFactory

if TYPE_CHECKING:
    from prama.db.dao import (
        ApiKeyDao,
        AuditDao,
        PrincipalDao,
        RoleDao,
        SettingDao,
        TenantDao,
    )

_log = get_logger(__name__)


class SessionManager:
    """Creates async sessions bound to the configured engine."""

    def __init__(self, factory: EngineFactory) -> None:
        self._factory = factory
        self._maker: async_sessionmaker[AsyncSession] | None = None

    def maker(self) -> async_sessionmaker[AsyncSession]:
        if self._maker is None:
            self._maker = async_sessionmaker(
                bind=self._factory.async_engine(),
                expire_on_commit=False,  # objects stay usable after the boundary closes
                autoflush=False,  # flush is explicit; surprise SQL is a debugging tax
            )
        return self._maker

    def session(self) -> AsyncSession:
        return self.maker()()


class UnitOfWork:
    """One transaction, and the DAOs that act inside it.

    DAOs are created lazily and cached, so a unit of work that touches one
    table does not construct six objects. Services receive a unit of work and
    never a session, which is what keeps SQLAlchemy confined to this package.
    """

    def __init__(self, session: AsyncSession, factory: EngineFactory) -> None:
        self._session = session
        self._factory = factory
        self._daos: dict[str, Any] = {}
        self._closed = False

    # -- data access objects ----------------------------------------------

    def _dao(self, name: str, cls: type[Any]) -> Any:
        if name not in self._daos:
            self._daos[name] = cls(self._session, self._factory.dialect)
        return self._daos[name]

    @property
    def tenants(self) -> TenantDao:
        from prama.db.dao import TenantDao

        return self._dao("tenants", TenantDao)  # type: ignore[no-any-return]

    @property
    def principals(self) -> PrincipalDao:
        from prama.db.dao import PrincipalDao

        return self._dao("principals", PrincipalDao)  # type: ignore[no-any-return]

    @property
    def roles(self) -> RoleDao:
        from prama.db.dao import RoleDao

        return self._dao("roles", RoleDao)  # type: ignore[no-any-return]

    @property
    def api_keys(self) -> ApiKeyDao:
        from prama.db.dao import ApiKeyDao

        return self._dao("api_keys", ApiKeyDao)  # type: ignore[no-any-return]

    @property
    def audit(self) -> AuditDao:
        from prama.db.dao import AuditDao

        return self._dao("audit", AuditDao)  # type: ignore[no-any-return]

    @property
    def settings(self) -> SettingDao:
        from prama.db.dao import SettingDao

        return self._dao("settings", SettingDao)  # type: ignore[no-any-return]

    # -- transaction boundary ---------------------------------------------

    async def flush(self) -> None:
        """Push pending changes without ending the transaction."""
        await self._guarded(self._session.flush)

    async def commit(self) -> None:
        await self._guarded(self._session.commit)

    async def rollback(self) -> None:
        await self._session.rollback()

    async def close(self) -> None:
        if not self._closed:
            await self._session.close()
            self._closed = True

    async def _guarded(self, operation: Any) -> None:
        try:
            await operation()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "the change conflicts with data already present",
                remedy=(
                    "A unique key or foreign key was violated. Re-read the current state "
                    "and retry, or correct the input."
                ),
                context={"detail": _first_line(exc)},
                cause=exc,
            ) from exc
        except SQLAlchemyError as exc:
            await self._session.rollback()
            raise DatabaseError(
                "the database rejected the transaction",
                code="DB.TRANSACTION_FAILED",
                remedy="Inspect the detail below; the transaction has been rolled back.",
                context={"detail": _first_line(exc)},
                cause=exc,
            ) from exc

    async def __aenter__(self) -> UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                await self.commit()
            else:
                await self.rollback()
        finally:
            await self.close()


def _first_line(exc: Exception) -> str:
    return str(exc).splitlines()[0][:400]

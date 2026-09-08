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
    from prama.db.repositories import (
        ApiKeyRepository,
        AuditRepository,
        PrincipalRepository,
        RoleRepository,
        SettingRepository,
        TenantRepository,
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
    """One transaction, and the repositories that act inside it.

    Repositories are created lazily and cached, so a unit of work that touches
    one table does not construct six objects.
    """

    def __init__(self, session: AsyncSession, factory: EngineFactory) -> None:
        self._session = session
        self._factory = factory
        self._repositories: dict[str, Any] = {}
        self._closed = False

    # -- repositories ------------------------------------------------------

    def _repository(self, name: str, cls: type[Any]) -> Any:
        if name not in self._repositories:
            self._repositories[name] = cls(self._session, self._factory.dialect)
        return self._repositories[name]

    @property
    def tenants(self) -> TenantRepository:
        from prama.db.repositories import TenantRepository

        return self._repository("tenants", TenantRepository)  # type: ignore[no-any-return]

    @property
    def principals(self) -> PrincipalRepository:
        from prama.db.repositories import PrincipalRepository

        return self._repository("principals", PrincipalRepository)  # type: ignore[no-any-return]

    @property
    def roles(self) -> RoleRepository:
        from prama.db.repositories import RoleRepository

        return self._repository("roles", RoleRepository)  # type: ignore[no-any-return]

    @property
    def api_keys(self) -> ApiKeyRepository:
        from prama.db.repositories import ApiKeyRepository

        return self._repository("api_keys", ApiKeyRepository)  # type: ignore[no-any-return]

    @property
    def audit(self) -> AuditRepository:
        from prama.db.repositories import AuditRepository

        return self._repository("audit", AuditRepository)  # type: ignore[no-any-return]

    @property
    def settings(self) -> SettingRepository:
        from prama.db.repositories import SettingRepository

        return self._repository("settings", SettingRepository)  # type: ignore[no-any-return]

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

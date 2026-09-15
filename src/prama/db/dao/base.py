"""The DAO base classes.

Every concrete DAO inherits from these two, so tenant scoping and error
translation are properties of the base rather than of anyone's memory.

Every read and write against Prama's schema is concentrated here. Nothing
outside ``prama.db`` issues SQL or touches an ORM session; higher layers call a
DAO through the unit of work and receive domain objects. An architecture test
enforces that by import scanning, so the rule is a property of the build rather
than of anyone's memory.

Three rules make the layering real:

* **Tenant scoping is structural.** ``TenantScopedDao`` takes the tenant on
  every read and write; no method can omit it. Multi-tenancy enforced by
  discipline is multi-tenancy that leaks.
* **Domain logic lives with the data it belongs to.** Password hashing sits
  beside the column that stores the hash, and key issuance beside the key
  table, rather than drifting into a service where the two can diverge.
* **No exception is swallowed.** Failures are translated into the Prama error
  taxonomy by the unit of work — with a remedy the caller can act on — and
  propagate. A DAO never returns a sentinel that means "something went wrong".

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from prama.core.errors import NotFoundError
from prama.db.dialects import Dialect

#: Bound to ``DeclarativeBase`` rather than to ``Base``, because there are two
#: declarative bases: the platform's and the evidence ledger's. The split is
#: what keeps a platform operation from reaching the ledger, and binding this
#: TypeVar to one of them would have forced the evidence DAOs to sit outside
#: the layer that translates errors and owns the session.
M = TypeVar("M", bound=DeclarativeBase)


class Dao(Generic[M]):
    """Base for every DAO: one model, one session, one dialect."""

    model: type[M]

    def __init__(self, session: AsyncSession, dialect: Dialect) -> None:
        self._session = session
        self._dialect = dialect

    async def _guarded_flush(self) -> None:
        """Flush, translating a constraint violation into the taxonomy.

        `self._session.flush()` directly is how a concurrent amendment's losing
        side surfaced a raw `sqlite3.IntegrityError` above `prama.db`. The
        translation is `prama.db.guard.guarded`, shared with `UnitOfWork` rather
        than copied. QA round 4, `DB-179`.
        """
        from prama.db.guard import guarded

        await guarded(self._session, self._session.flush)

    # -- primitives --------------------------------------------------------

    def add(self, entity: M) -> M:
        self._session.add(entity)
        return entity

    async def get(self, identifier: Any) -> M | None:
        return await self._session.get(self.model, identifier)

    async def require(self, identifier: Any) -> M:
        entity = await self.get(identifier)
        if entity is None:
            raise NotFoundError(
                f"{self.model.__name__} {identifier!r} does not exist",
                remedy="Check the identifier, or list the available entities first.",
                context={"model": self.model.__name__, "id": str(identifier)},
            )
        return entity

    async def delete(self, entity: M) -> None:
        await self._session.delete(entity)

    async def count(self, statement: Select[Any] | None = None) -> int:
        stmt = statement if statement is not None else select(self.model)
        result = await self._session.execute(select(func.count()).select_from(stmt.subquery()))
        return int(result.scalar_one())

    async def _all(self, statement: Select[Any]) -> list[M]:
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def _one_or_none(self, statement: Select[Any]) -> M | None:
        result = await self._session.execute(statement)
        return result.scalars().one_or_none()


class TenantScopedDao(Dao[M]):
    """A DAO whose every query is filtered by tenant.

    The tenant is a parameter of each method rather than constructor state so
    that a single unit of work can legitimately serve an admin operation across
    tenants — while still never issuing an unscoped query by accident.
    """

    async def list_for_tenant(
        self, tenant_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[M]:
        stmt = (
            select(self.model)
            .where(self.model.tenant_id == tenant_id)  # type: ignore[attr-defined]
            .order_by(self.model.id)  # type: ignore[attr-defined]
            .limit(limit)
            .offset(offset)
        )
        return await self._all(stmt)

    async def get_for_tenant(self, tenant_id: str, identifier: str) -> M | None:
        stmt = select(self.model).where(
            self.model.id == identifier,  # type: ignore[attr-defined]
            self.model.tenant_id == tenant_id,  # type: ignore[attr-defined]
        )
        return await self._one_or_none(stmt)

    async def require_for_tenant(self, tenant_id: str, identifier: str) -> M:
        entity = await self.get_for_tenant(tenant_id, identifier)
        if entity is None:
            raise NotFoundError(
                f"{self.model.__name__} {identifier!r} does not exist in this tenant",
                remedy="Check the identifier and the tenant it belongs to.",
                context={"model": self.model.__name__, "id": identifier, "tenant": tenant_id},
            )
        return entity

    async def count_for_tenant(self, tenant_id: str) -> int:
        return await self.count(
            select(self.model).where(self.model.tenant_id == tenant_id)  # type: ignore[attr-defined]
        )

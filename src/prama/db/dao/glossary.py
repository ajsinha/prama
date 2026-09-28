"""The business glossary. Every signature takes the tenant.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import or_, select

from prama.core.errors import NotFoundError, ValidationError
from prama.db.dao.base import Dao
from prama.db.models.glossary import GlBinding, GlTerm


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class GlossaryDao(Dao[GlTerm]):
    model = GlTerm

    async def terms(self, tenant_id: str) -> list[GlTerm]:
        await self._session.flush()
        result = await self._session.execute(
            select(GlTerm).where(GlTerm.tenant_id == tenant_id).order_by(GlTerm.name)
        )
        return list(result.scalars().all())

    async def term(self, tenant_id: str, name: str) -> GlTerm | None:
        await self._session.flush()
        result = await self._session.execute(
            select(GlTerm).where(GlTerm.tenant_id == tenant_id, GlTerm.name == name)
        )
        return result.scalars().one_or_none()

    async def upsert(
        self,
        tenant_id: str,
        *,
        name: str,
        definition: str = "",
        synonyms: list[str] | None = None,
        domain: str = "",
        steward: str = "",
        status: str = "accepted",
        source: str = "prama",
        external_id: str | None = None,
    ) -> tuple[GlTerm, bool]:
        """A term by its source identity, else by name. Returns (term, created)."""
        if not name.strip():
            raise ValidationError("a term needs a name", remedy="Give the term its name.")
        row = None
        if external_id:
            row = (
                (
                    await self._session.execute(
                        select(GlTerm).where(
                            GlTerm.tenant_id == tenant_id,
                            GlTerm.source == source,
                            GlTerm.external_id == external_id,
                        )
                    )
                )
                .scalars()
                .first()
            )
        row = row or await self.term(tenant_id, name.strip())
        created = row is None
        if row is None:
            row = GlTerm(tenant_id=tenant_id, name=name.strip(), created_at=_now(), updated_at="")
            self._session.add(row)
        row.name = name.strip()
        row.definition = definition
        row.synonyms_json = json.dumps(sorted({s.strip() for s in synonyms or [] if s.strip()}))
        row.domain, row.steward, row.status = domain, steward, status
        row.source, row.external_id, row.updated_at = source, external_id, _now()
        await self._session.flush()
        return row, created

    async def bind(
        self,
        tenant_id: str,
        term_name: str,
        object_kind: str,
        object_ref: str,
        *,
        how: str = "person",
        by: str | None = None,
    ) -> GlBinding:
        term = await self.term(tenant_id, term_name)
        if term is None:
            raise NotFoundError(f"no glossary term {term_name!r}", remedy="Add or import it.")
        existing = (
            (
                await self._session.execute(
                    select(GlBinding).where(
                        GlBinding.term_id == term.id,
                        GlBinding.object_kind == object_kind,
                        GlBinding.object_ref == object_ref,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            return existing
        row = GlBinding(
            tenant_id=tenant_id,
            term_id=term.id,
            object_kind=object_kind,
            object_ref=object_ref,
            how=how,
            created_by=by,
            created_at=_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def bindings(self, tenant_id: str, *, term_id: str | None = None) -> list[GlBinding]:
        await self._session.flush()
        statement = select(GlBinding).where(GlBinding.tenant_id == tenant_id)
        if term_id:
            statement = statement.where(GlBinding.term_id == term_id)
        result = await self._session.execute(statement.order_by(GlBinding.object_ref))
        return list(result.scalars().all())

    async def search(self, tenant_id: str, text: str, *, limit: int = 50) -> list[GlTerm]:
        """Terms whose name, synonyms or definition mention *text*."""
        await self._session.flush()
        like = f"%{text.strip().lower()}%"
        result = await self._session.execute(
            select(GlTerm)
            .where(
                GlTerm.tenant_id == tenant_id,
                or_(
                    GlTerm.name.ilike(like),
                    GlTerm.synonyms_json.ilike(like),
                    GlTerm.definition.ilike(like),
                ),
            )
            .order_by(GlTerm.name)
            .limit(limit)
        )
        return list(result.scalars().all())

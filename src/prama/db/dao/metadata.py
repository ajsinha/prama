"""Metadata templates and their values. Every signature takes the tenant.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from prama.db.dao.base import Dao
from prama.db.models.metadata import MdField, MdTemplate, MdValue


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class MetadataDao(Dao[MdTemplate]):
    model = MdTemplate

    async def templates(self, tenant_id: str, *, applies_to: str = "") -> list[MdTemplate]:
        await self._session.flush()
        statement = select(MdTemplate).where(
            MdTemplate.tenant_id == tenant_id, MdTemplate.status == "active"
        )
        if applies_to:
            statement = statement.where(MdTemplate.applies_to == applies_to)
        result = await self._session.execute(statement.order_by(MdTemplate.name))
        return list(result.scalars().all())

    async def template(self, tenant_id: str, name: str) -> MdTemplate | None:
        await self._session.flush()
        result = await self._session.execute(
            select(MdTemplate).where(MdTemplate.tenant_id == tenant_id, MdTemplate.name == name)
        )
        return result.scalars().one_or_none()

    async def save_template(self, tenant_id: str, spec: Any) -> tuple[MdTemplate, int, int]:
        """Create or update a template from a `TemplateSpec`. Returns (row, added, changed).

        Fields are matched by name and never removed here: a field removed from
        the YAML still holds values somebody set, and deleting them silently
        would delete metadata. Retire the template instead.
        """
        row = await self.template(tenant_id, spec.name)
        if row is None:
            row = MdTemplate(
                tenant_id=tenant_id,
                name=spec.name,
                applies_to=spec.applies_to,
                created_at=_now(),
                updated_at=_now(),
            )
            self._session.add(row)
            await self._session.flush()
        row.description, row.updated_at = spec.description, _now()
        existing = {f.name: f for f in await self.fields(row.id)}
        added = changed = 0
        for position, field in enumerate(spec.fields):
            values = {
                "label": field.label,
                "kind": field.kind,
                "choices_json": json.dumps(list(field.choices)),
                "required": int(field.required),
                "help": field.help,
                "position": position,
                "rules_json": json.dumps(
                    [{"pql": r.pql, "when": r.when, "note": r.note} for r in field.rules]
                ),
            }
            current = existing.get(field.name)
            if current is None:
                self._session.add(MdField(template_id=row.id, name=field.name, **values))
                added += 1
            elif any(getattr(current, k) != v for k, v in values.items()):
                for key, value in values.items():
                    setattr(current, key, value)
                changed += 1
        await self._session.flush()
        return row, added, changed

    async def fields(self, template_id: str) -> list[MdField]:
        result = await self._session.execute(
            select(MdField).where(MdField.template_id == template_id).order_by(MdField.position)
        )
        return list(result.scalars().all())

    async def current_values(
        self, tenant_id: str, *, object_kind: str = "", object_ref: str = ""
    ) -> list[MdValue]:
        await self._session.flush()
        statement = select(MdValue).where(
            MdValue.tenant_id == tenant_id, MdValue.valid_to.is_(None)
        )
        if object_kind:
            statement = statement.where(MdValue.object_kind == object_kind)
        if object_ref:
            statement = statement.where(MdValue.object_ref == object_ref)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def set_value(
        self,
        tenant_id: str,
        field_id: str,
        object_kind: str,
        object_ref: str,
        value: Any,
        *,
        by: str | None = None,
    ) -> bool:
        """Record *value* (None clears it). The previous value is closed, not overwritten.

        Returns whether anything changed.
        """
        await self._session.flush()
        current = (
            (
                await self._session.execute(
                    select(MdValue).where(
                        MdValue.tenant_id == tenant_id,
                        MdValue.field_id == field_id,
                        MdValue.object_kind == object_kind,
                        MdValue.object_ref == object_ref,
                        MdValue.valid_to.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        encoded = json.dumps(value, sort_keys=True) if value is not None else None
        if current is not None and current.value_json == encoded:
            return False
        now = _now()
        if current is not None:
            current.valid_to = now
        if encoded is not None:
            self._session.add(
                MdValue(
                    tenant_id=tenant_id,
                    field_id=field_id,
                    object_kind=object_kind,
                    object_ref=object_ref,
                    value_json=encoded,
                    valid_from=now,
                    recorded_by=by,
                )
            )
        await self._session.flush()
        return current is not None or encoded is not None

    async def history(self, tenant_id: str, field_id: str, object_ref: str) -> list[MdValue]:
        result = await self._session.execute(
            select(MdValue)
            .where(
                MdValue.tenant_id == tenant_id,
                MdValue.field_id == field_id,
                MdValue.object_ref == object_ref,
            )
            .order_by(MdValue.valid_from)
        )
        return list(result.scalars().all())

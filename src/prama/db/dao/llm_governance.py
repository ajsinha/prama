"""Prompt templates, stored payloads and evaluation runs. Every signature takes the tenant.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from prama.core.errors import ForbiddenError, NotFoundError, ValidationError
from prama.db.dao.base import Dao
from prama.db.models.llm import LlmProfile, LlmProfileVersion
from prama.db.models.llm_governance import (
    LlmEvalRun,
    LlmPayload,
    LlmTemplate,
    LlmTemplateVersion,
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class LlmGovernanceDao(Dao[LlmTemplate]):
    model = LlmTemplate

    # -- templates -----------------------------------------------------------

    async def template(self, tenant_id: str, name: str) -> LlmTemplate | None:
        await self._session.flush()
        result = await self._session.execute(
            select(LlmTemplate).where(LlmTemplate.tenant_id == tenant_id, LlmTemplate.name == name)
        )
        return result.scalars().one_or_none()

    async def templates(self, tenant_id: str) -> list[LlmTemplate]:
        await self._session.flush()
        result = await self._session.execute(
            select(LlmTemplate).where(LlmTemplate.tenant_id == tenant_id).order_by(LlmTemplate.name)
        )
        return list(result.scalars().all())

    async def template_versions(self, tenant_id: str, name: str) -> list[LlmTemplateVersion]:
        row = await self.template(tenant_id, name)
        if row is None:
            return []
        result = await self._session.execute(
            select(LlmTemplateVersion)
            .where(LlmTemplateVersion.template_id == row.id)
            .order_by(LlmTemplateVersion.version)
        )
        return list(result.scalars().all())

    async def add_template_version(
        self, tenant_id: str, template: Any, *, by: str | None
    ) -> LlmTemplateVersion:
        """Record a new draft version of *template* (a `PromptTemplate`)."""
        row = await self.template(tenant_id, template.name)
        if row is None:
            row = LlmTemplate(tenant_id=tenant_id, name=template.name, created_at=_now())
            self._session.add(row)
            await self._session.flush()
        versions = await self.template_versions(tenant_id, template.name)
        if versions and versions[-1].content_hash == template.content_hash:
            return versions[-1]  # unchanged: no new version
        version = LlmTemplateVersion(
            template_id=row.id,
            version=(versions[-1].version if versions else 0) + 1,
            system_text=template.system,
            body=template.body,
            variables_json=json.dumps(
                [
                    {"name": v.name, "sensitivity": v.sensitivity, "trusted": v.trusted}
                    for v in template.variables
                ]
            ),
            response_schema_json=json.dumps(template.response_schema)
            if template.response_schema is not None
            else None,
            content_hash=template.content_hash,
            recorded_at=_now(),
            recorded_by=by,
        )
        self._session.add(version)
        await self._session.flush()
        return version

    async def approve_template(
        self, tenant_id: str, name: str, version: int, *, by: str, require_eval: bool
    ) -> LlmTemplateVersion:
        """Approve a draft and make it current. With *require_eval*, only after a pass."""
        row = await self.template(tenant_id, name)
        found = next(
            (v for v in await self.template_versions(tenant_id, name) if v.version == version), None
        )
        if row is None or found is None:
            raise NotFoundError(f"no template {name} v{version}", remedy="List the templates.")
        if found.recorded_by and found.recorded_by == by:
            raise ForbiddenError(
                "the author of a template version cannot approve it",
                remedy="Ask another person to review and approve it.",
            )
        run = await self.passing_run(tenant_id, template_id=row.id, template_version=version)
        if require_eval and run is None:
            raise ValidationError(
                f"{name} v{version} has no passing evaluation run",
                remedy=f"Run `prama llm eval run <suite> --template {name}` first; "
                "llm.eval.gate_activation is on.",
            )
        for other in await self.template_versions(tenant_id, name):
            if other.status == "approved" and other.version != version:
                other.status = "retired"
        found.status, found.approved_by, found.approved_at = "approved", by, _now()
        found.eval_run_id = run.id if run else None
        row.current_version = version
        await self._session.flush()
        return found

    async def current_template(self, tenant_id: str, name: str) -> LlmTemplateVersion | None:
        row = await self.template(tenant_id, name)
        if row is None or row.current_version is None:
            return None
        return next(
            (
                v
                for v in await self.template_versions(tenant_id, name)
                if v.version == row.current_version
            ),
            None,
        )

    # -- profile activation --------------------------------------------------

    async def activate_profile(
        self, tenant_id: str, purpose: str, version: int, *, require_eval: bool
    ) -> LlmProfileVersion:
        profile = (
            (
                await self._session.execute(
                    select(LlmProfile).where(
                        LlmProfile.tenant_id == tenant_id, LlmProfile.purpose == purpose
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        if profile is None:
            raise NotFoundError(f"no profile for {purpose!r}", remedy="Set one first.")
        await self._session.refresh(profile, ["versions"])
        found = next((v for v in profile.versions if v.version == version), None)
        if found is None:
            raise NotFoundError(f"{purpose} has no version {version}", remedy="List the profile.")
        run = await self.passing_run(tenant_id, profile_id=profile.id, profile_version=version)
        if require_eval and run is None:
            raise ValidationError(
                f"{purpose} v{version} has no passing evaluation run",
                remedy=f"Run `prama llm eval run <suite> --purpose {purpose} --version {version}`.",
            )
        found.eval_run_id = run.id if run else found.eval_run_id
        profile.current_version = version
        await self._session.flush()
        return found

    # -- evaluation runs -----------------------------------------------------

    async def record_eval(self, tenant_id: str, **fields: Any) -> LlmEvalRun:
        fields.setdefault("finished_at", None)
        if fields["finished_at"] is None and fields.get("status", "running") != "running":
            fields["finished_at"] = _now()
        row = LlmEvalRun(tenant_id=tenant_id, started_at=_now(), **fields)
        self._session.add(row)
        await self._session.flush()
        return row

    async def eval_runs(self, tenant_id: str, *, limit: int = 50) -> list[LlmEvalRun]:
        await self._session.flush()
        result = await self._session.execute(
            select(LlmEvalRun)
            .where(LlmEvalRun.tenant_id == tenant_id)
            .order_by(LlmEvalRun.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def passing_run(self, tenant_id: str, **subject: Any) -> LlmEvalRun | None:
        """The latest passed run for exactly this profile or template version."""
        await self._session.flush()
        clauses = [getattr(LlmEvalRun, k) == v for k, v in subject.items()]
        result = await self._session.execute(
            select(LlmEvalRun)
            .where(LlmEvalRun.tenant_id == tenant_id, LlmEvalRun.status == "passed", *clauses)
            .order_by(LlmEvalRun.started_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    # -- payloads ------------------------------------------------------------

    async def put_payload(
        self,
        tenant_id: str,
        digest: str,
        *,
        request_json: str,
        response_json: str,
        mode: str,
        expires_at: str | None,
    ) -> None:
        if await self._session.get(LlmPayload, digest) is not None:
            return  # content-addressed: the same exchange is stored once
        self._session.add(
            LlmPayload(
                digest=digest,
                tenant_id=tenant_id,
                request_json=request_json,
                response_json=response_json,
                mode=mode,
                created_at=_now(),
                expires_at=expires_at,
            )
        )
        await self._session.flush()

    async def payload(self, tenant_id: str, digest: str) -> LlmPayload | None:
        row = await self._session.get(LlmPayload, digest)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def expire_payloads(self, tenant_id: str, *, now: str | None = None) -> int:
        """Blank payloads past their expiry. The call ledger keeps its hashes."""
        moment = now or _now()
        result = await self._session.execute(
            select(LlmPayload).where(
                LlmPayload.tenant_id == tenant_id,
                LlmPayload.expires_at.is_not(None),
                LlmPayload.expires_at <= moment,
                LlmPayload.mode != "expired",
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.request_json, row.response_json, row.mode = "", "", "expired"
        await self._session.flush()
        return len(rows)

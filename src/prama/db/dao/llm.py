"""Providers, profiles and the model-call ledger, persisted.

The gateway (`prama.llm.gateway`) knows nothing about the database; this is
the side that does. Profiles are append-only versions, so the model that wrote
a proposal stays answerable after the profile changes. Calls are chained per
tenant with `prama.llm.gateway.seal`, so the chain is computed by one function
whether it is written here or checked anywhere else.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import func, select

from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.db.dao.base import Dao
from prama.db.models.llm import (
    LlmCall,
    LlmProfile,
    LlmProfileRoute,
    LlmProfileVersion,
    LlmProvider,
)
from prama.llm.gateway import GENESIS, CallRecord, seal


class LlmDao(Dao[LlmProvider]):
    """Everything the gateway stores, scoped by tenant in every signature."""

    model = LlmProvider

    # -- providers ---------------------------------------------------------

    async def providers(self, tenant_id: str) -> list[LlmProvider]:
        await self._session.flush()  # a provider added in this unit of work counts
        return await self._all(
            select(LlmProvider).where(LlmProvider.tenant_id == tenant_id).order_by(LlmProvider.name)
        )

    async def provider(self, tenant_id: str, name: str) -> LlmProvider | None:
        await self._session.flush()
        return await self._one_or_none(
            select(LlmProvider).where(LlmProvider.tenant_id == tenant_id, LlmProvider.name == name)
        )

    async def add_provider(
        self,
        tenant_id: str,
        *,
        name: str,
        kind: str,
        hosting: str,
        endpoint: str = "",
        dialect: str = "",
        region: str = "",
        credential_ref: str | None = None,
        settings: dict[str, Any] | None = None,
        by: str | None = None,
    ) -> LlmProvider:
        if await self.provider(tenant_id, name) is not None:
            raise ConflictError(
                f"a provider called {name!r} already exists",
                remedy="Choose another name, or change the existing provider.",
                context={"provider": name},
            )
        return self.add(
            LlmProvider(
                tenant_id=tenant_id,
                name=name,
                kind=kind,
                hosting=hosting,
                endpoint=endpoint,
                dialect=dialect,
                region=region,
                credential_ref=credential_ref or None,
                settings_json=settings or {},
                created_by=by,
                updated_by=by,
            )
        )

    # -- profiles ----------------------------------------------------------

    async def profiles(self, tenant_id: str) -> list[LlmProfile]:
        return await self._all_of(
            select(LlmProfile).where(LlmProfile.tenant_id == tenant_id).order_by(LlmProfile.purpose)
        )

    async def current(
        self, tenant_id: str, purpose: str
    ) -> tuple[LlmProfile, LlmProfileVersion] | None:
        """A purpose's profile and its current version, or ``None``."""
        profile = await self._one_or_none_of(
            select(LlmProfile).where(
                LlmProfile.tenant_id == tenant_id, LlmProfile.purpose == purpose
            )
        )
        if profile is None or profile.current_version is None:
            return None
        for version in profile.versions:
            if version.version == profile.current_version:
                return profile, version
        return None

    async def set_profile(
        self,
        tenant_id: str,
        purpose: str,
        route: Sequence[tuple[str, str]],
        *,
        max_attempts: int = 2,
        fallback_across_hosting: bool = False,
        note: str = "",
        by: str | None = None,
    ) -> LlmProfileVersion:
        """Record a new version of *purpose*'s profile and make it current.

        *route* is ``(provider name, model)`` in the order to try them.
        """
        if not route:
            raise ValidationError(
                "a profile needs at least one provider and model",
                remedy="Name a provider and the model it should serve.",
            )
        providers = {p.name: p for p in await self.providers(tenant_id)}
        missing = [name for name, _ in route if name not in providers]
        if missing:
            raise NotFoundError(
                f"no provider called {', '.join(missing)}",
                remedy="Add the provider first: `prama llm provider add` or the Models page.",
                context={"missing": missing},
            )
        profile = await self._one_or_none_of(
            select(LlmProfile).where(
                LlmProfile.tenant_id == tenant_id, LlmProfile.purpose == purpose
            )
        )
        if profile is None:
            profile = LlmProfile(tenant_id=tenant_id, purpose=purpose)
            self._session.add(profile)
            await self._session.flush()
            number = 1
        else:
            await self._session.refresh(profile, ["versions"])
            number = max((v.version for v in profile.versions), default=0) + 1
        version = LlmProfileVersion(
            profile_id=profile.id,
            version=number,
            max_attempts=max_attempts,
            fallback_across_hosting=fallback_across_hosting,
            note=note,
            recorded_by=by,
        )
        self._session.add(version)
        await self._session.flush()
        for position, (name, model) in enumerate(route):
            self._session.add(
                LlmProfileRoute(
                    profile_version_id=version.id,
                    position=position,
                    provider_id=providers[name].id,
                    model=model,
                )
            )
        profile.current_version = number
        await self._session.flush()
        await self._session.refresh(profile, ["versions"])
        await self._session.refresh(version, ["routes"])
        return version

    # -- the call ledger ---------------------------------------------------

    async def calls(self, tenant_id: str, *, limit: int = 100) -> list[LlmCall]:
        result = await self._session.execute(
            select(LlmCall)
            .where(LlmCall.tenant_id == tenant_id)
            .order_by(LlmCall.sequence.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def append_calls(self, tenant_id: str, records: Iterable[CallRecord]) -> int:
        """Chain *records* onto the tenant's ledger. Returns how many."""
        await self._session.flush()
        last = (
            await self._session.execute(
                select(LlmCall.sequence, LlmCall.record_hash)
                .where(LlmCall.tenant_id == tenant_id)
                .order_by(LlmCall.sequence.desc())
                .limit(1)
            )
        ).first()
        sequence, previous = (last[0] + 1, last[1]) if last else (0, GENESIS)
        written = 0
        for record in records:
            if record.tenant_id != tenant_id:
                raise ValidationError(
                    "a call record belongs to another tenant",
                    remedy="Persist each tenant's records with its own ledger.",
                    context={"record": record.tenant_id, "tenant": tenant_id},
                )
            digest = seal(record, sequence=sequence, previous_hash=previous)
            self._session.add(
                LlmCall(
                    **record.content(),
                    sequence=sequence,
                    previous_hash=previous,
                    record_hash=digest,
                )
            )
            sequence, previous, written = sequence + 1, digest, written + 1
        await self._session.flush()
        return written

    async def count_calls(self, tenant_id: str) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(LlmCall).where(LlmCall.tenant_id == tenant_id)
        )
        return int(result.scalar_one())

    # -- helpers for the other tables --------------------------------------

    async def _all_of(self, statement: Any) -> list[Any]:
        return list((await self._session.execute(statement)).scalars().all())

    async def _one_or_none_of(self, statement: Any) -> Any:
        return (await self._session.execute(statement)).scalars().one_or_none()

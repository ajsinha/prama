"""Providers, profiles and the model-call ledger, persisted.

The gateway (`prama.llm.gateway`) knows nothing about the database; this is
the side that does. Profiles are append-only versions, so the model that wrote
a proposal stays answerable after the profile changes. Calls are chained per
tenant with `prama.llm.gateway.seal`, so the chain is computed by one function
whether it is written here or checked anywhere else.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import func, select

from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.db.dao.base import Dao
from prama.db.models.llm import (
    LlmBudget,
    LlmCall,
    LlmModel,
    LlmProfile,
    LlmProfileRoute,
    LlmProfileVersion,
    LlmProvider,
    LlmReservation,
)
from prama.llm.gateway import GENESIS, CallRecord, seal


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds")


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
        activate: bool = True,
    ) -> LlmProfileVersion:
        """Record a new version of *purpose*'s profile and, unless *activate* is
        false (the evaluation gate), make it current.

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
        if activate:
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

    async def verify_calls(self, tenant_id: str) -> tuple[bool, int, str]:
        """Recompute the tenant's call chain: (intact, records checked, first break)."""
        from prama.llm.gateway import CallRecord

        fields = {f.name for f in dataclasses.fields(CallRecord)}
        result = await self._session.execute(
            select(LlmCall).where(LlmCall.tenant_id == tenant_id).order_by(LlmCall.sequence)
        )
        previous = GENESIS
        checked = 0
        for row in result.scalars():
            record = CallRecord(**{name: getattr(row, name) for name in fields})
            if (
                row.previous_hash != previous
                or seal(record, sequence=row.sequence, previous_hash=previous) != row.record_hash
            ):
                return False, checked, f"call {row.sequence} does not match its seal"
            previous, checked = row.record_hash, checked + 1
        return True, checked, ""

    async def count_calls(self, tenant_id: str) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(LlmCall).where(LlmCall.tenant_id == tenant_id)
        )
        return int(result.scalar_one())

    # -- prices, budgets, spend -------------------------------------------

    async def set_price(
        self,
        tenant_id: str,
        provider: str,
        model: str,
        *,
        input_micros: int,
        output_micros: int,
        cached_micros: int = 0,
        effective_from: str = "",
    ) -> LlmModel:
        """A dated price per million tokens. Earlier prices are kept, so a past
        call's cost can still be explained by the price in force at the time."""
        row = await self.provider(tenant_id, provider)
        if row is None:
            raise NotFoundError(
                f"no provider called {provider!r}", remedy="Add the provider first."
            )
        price = LlmModel(
            tenant_id=tenant_id,
            provider_id=row.id,
            model=model,
            price_in_micros=input_micros,
            price_out_micros=output_micros,
            price_cached_micros=cached_micros,
            effective_from=effective_from or _now(),
        )
        self._session.add(price)
        await self._session.flush()
        return price

    async def price_for(
        self, tenant_id: str, provider_id: str, model: str, at: str
    ) -> LlmModel | None:
        """The price in force for *model* at *at*."""
        result = await self._session.execute(
            select(LlmModel)
            .where(
                LlmModel.tenant_id == tenant_id,
                LlmModel.provider_id == provider_id,
                LlmModel.model == model,
                LlmModel.effective_from <= at,
            )
            .order_by(LlmModel.effective_from.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def set_budget(
        self,
        tenant_id: str,
        *,
        scope_kind: str,
        scope_id: str = "",
        period: str = "month",
        limit_micros: int | None = None,
        limit_tokens: int | None = None,
        action: str = "refuse",
        by: str | None = None,
    ) -> LlmBudget:
        await self._session.flush()
        existing = (
            (
                await self._session.execute(
                    select(LlmBudget).where(
                        LlmBudget.tenant_id == tenant_id,
                        LlmBudget.scope_kind == scope_kind,
                        LlmBudget.scope_id == scope_id,
                        LlmBudget.period == period,
                    )
                )
            )
            .scalars()
            .first()
        )
        row = existing or LlmBudget(
            tenant_id=tenant_id, scope_kind=scope_kind, scope_id=scope_id, period=period
        )
        row.limit_micros, row.limit_tokens, row.action, row.updated_by = (
            limit_micros,
            limit_tokens,
            action,
            by,
        )
        if existing is None:
            self._session.add(row)
        await self._session.flush()
        return row

    async def budgets(self, tenant_id: str) -> list[LlmBudget]:
        result = await self._session.execute(
            select(LlmBudget).where(LlmBudget.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def spend(
        self, tenant_id: str, since: str, *, scope_kind: str = "tenant", scope_id: str = ""
    ) -> tuple[int, int]:
        """Micro-units and tokens spent since *since*, derived from the ledger."""
        column = {
            "principal": LlmCall.principal_id,
            "api_key": LlmCall.api_key_id,
            "profile": LlmCall.profile_id,
        }.get(scope_kind)
        statement = select(
            func.coalesce(func.sum(LlmCall.cost_micros), 0),
            func.coalesce(func.sum(LlmCall.input_tokens + LlmCall.output_tokens), 0),
        ).where(LlmCall.tenant_id == tenant_id, LlmCall.started_at >= since)
        if column is not None:
            statement = statement.where(column == scope_id)
        micros, tokens = (await self._session.execute(statement)).one()
        # Plus what calls in flight have reserved, so a fleet of servers sees
        # each other's spend before it lands in the ledger.
        live = await self._session.execute(
            select(LlmReservation).where(
                LlmReservation.tenant_id == tenant_id, LlmReservation.expires_at > _now()
            )
        )
        key = f"{scope_kind}:{scope_id}"
        for reservation in live.scalars():
            if key in reservation.scopes_json:
                micros += reservation.reserved_micros
                tokens += reservation.reserved_tokens
        return int(micros), int(tokens)

    async def reserve(
        self, tenant_id: str, scopes: list[str], *, micros: int, tokens: int, seconds: float
    ) -> LlmReservation:
        from datetime import UTC, datetime, timedelta

        row = LlmReservation(
            tenant_id=tenant_id,
            scopes_json=scopes,
            reserved_micros=micros,
            reserved_tokens=tokens,
            expires_at=(datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(
                timespec="milliseconds"
            ),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def release_reservation(self, tenant_id: str, reservation_id: str) -> None:
        row = await self._session.get(LlmReservation, reservation_id)
        if row is not None and row.tenant_id == tenant_id:
            await self._session.delete(row)
            await self._session.flush()

    # -- helpers for the other tables --------------------------------------

    async def _all_of(self, statement: Any) -> list[Any]:
        return list((await self._session.execute(statement)).scalars().all())

    async def _one_or_none_of(self, statement: Any) -> Any:
        return (await self._session.execute(statement)).scalars().one_or_none()

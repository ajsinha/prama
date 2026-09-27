"""Model spend: what a call cost, and whether the next one may be made.

Money is integer micro-units, and a call's cost is computed from the price row
in force when it started, which the call then names. Spend is derived from the
call ledger (`LlmDao.spend`), never kept as a second counter that could
disagree with it (design note §7).

A budget can bind a tenant, a profile, a principal or an API key, per day or
per month. At its limit it either refuses (`LLM.BUDGET_EXHAUSTED`, HTTP 429)
or warns. The check happens before a call is made; a fleet-wide reservation
under a lease, so several servers cannot jointly overrun, is the next step.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

from prama.core.errors import PramaError
from prama.llm.gateway import CallRecord


class BudgetExhausted(PramaError):
    """A spending limit has been reached."""

    code = "LLM.BUDGET_EXHAUSTED"


class BudgetBusy(BudgetExhausted):
    """Another server held the budget lease for longer than a request should wait."""

    code = "LLM.BUDGET_BUSY"


#: How long a request waits for the tenant's budget lease before giving up.
LEASE_WAIT_SECONDS = 5.0


def cost_micros(price: Any, input_tokens: int, output_tokens: int) -> int:
    """Micro-units for a call at *price* (micro-units per million tokens). Rounded up."""
    if price is None:
        return 0
    raw = int(input_tokens) * int(price.price_in_micros) + int(output_tokens) * int(
        price.price_out_micros
    )
    return -(-raw // 1_000_000)  # integer ceiling: exact, no float in a money figure


def period_start(period: str, now: datetime | None = None) -> str:
    moment = now or datetime.now(UTC)
    start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        start = start.replace(day=1)
    return start.isoformat(timespec="milliseconds")


async def check(
    uow: Any,
    tenant_id: str,
    *,
    principal_id: str | None = None,
    api_key_id: str | None = None,
    profile_id: str | None = None,
) -> list[str]:
    """Refuse if a binding budget is spent; return warnings for the rest."""
    wanted = {
        ("tenant", ""),
        ("principal", principal_id or "\x00"),
        ("api_key", api_key_id or "\x00"),
        ("profile", profile_id or "\x00"),
    }
    warnings: list[str] = []
    for budget in await uow.llm.budgets(tenant_id):
        if (budget.scope_kind, budget.scope_id) not in wanted:
            continue
        micros, tokens = await uow.llm.spend(
            tenant_id,
            period_start(budget.period),
            scope_kind=budget.scope_kind,
            scope_id=budget.scope_id,
        )
        over = (budget.limit_micros is not None and micros >= budget.limit_micros) or (
            budget.limit_tokens is not None and tokens >= budget.limit_tokens
        )
        if not over:
            continue
        message = (
            f"the {budget.period}ly model budget for this {budget.scope_kind} is spent "
            f"({micros / 1_000_000:.2f} of {(budget.limit_micros or 0) / 1_000_000:.2f})"
        )
        if budget.action == "warn":
            warnings.append(message)
            continue
        raise BudgetExhausted(
            message,
            remedy="Raise the budget on the Models page, or wait for the period to reset.",
            context={"scope": budget.scope_kind, "period": budget.period},
        )
    return warnings


def refusal(tenant_id: str, purpose: str, request: Any, caller: Any, detail: str) -> CallRecord:
    """The ledger's record of a call refused for budget: made, never sent."""
    import hashlib

    now = datetime.now(UTC).isoformat(timespec="milliseconds")
    return CallRecord(
        tenant_id=tenant_id,
        surface="api",
        purpose=purpose,
        sensitivity=request.sensitivity.value,
        request_fingerprint=request.fingerprint,
        prompt_hash=hashlib.sha256(
            (request.system + "\x1f" + request.prompt).encode("utf-8")
        ).hexdigest(),
        started_at=now,
        finished_at=now,
        outcome="refused_budget",
        principal_id=getattr(caller, "principal_id", None),
        api_key_id=getattr(caller, "api_key_id", None),
        outcome_detail=detail[:1000],
    )


def _scopes(principal_id: str | None, api_key_id: str | None, profile_id: str | None) -> list[str]:
    scopes = ["tenant:"]
    for kind, value in (
        ("principal", principal_id),
        ("api_key", api_key_id),
        ("profile", profile_id),
    ):
        if value:
            scopes.append(f"{kind}:{value}")
    return scopes


async def admit(
    database: Any,
    tenant_id: str,
    purpose: str,
    request: Any,
    *,
    principal_id: str | None,
    api_key_id: str | None,
    holder: str,
) -> tuple[list[str], str | None]:
    """Check the budgets and reserve this call's estimate, fleet-wide.

    Under the tenant's budget lease and in a transaction of its own, so the
    reservation is visible to every other server before this call is made:
    two servers cannot each spend the last of a budget. Returns the warnings
    and the reservation to release when the call ends.
    """
    import asyncio

    leases = database.lease_provider()
    resource = f"llm-budget:{tenant_id}"
    deadline = asyncio.get_running_loop().time() + LEASE_WAIT_SECONDS
    lease = await leases.acquire(resource, holder, 30.0)
    while lease is None:
        if asyncio.get_running_loop().time() > deadline:
            raise BudgetBusy(
                "the model budget is being checked by another request",
                remedy="Retry in a moment.",
                context={"tenant": tenant_id},
            )
        await asyncio.sleep(0.05)
        lease = await leases.acquire(resource, holder, 30.0)
    try:
        async with database.unit_of_work() as uow:
            current = await uow.llm.current(tenant_id, purpose)
            profile_id = current[0].id if current else None
            warnings = await check(
                uow,
                tenant_id,
                principal_id=principal_id,
                api_key_id=api_key_id,
                profile_id=profile_id,
            )
            if not await uow.llm.budgets(tenant_id):
                return warnings, None  # nothing to protect, nothing to reserve
            estimate_tokens = (len(request.system) + len(request.prompt)) // 4 + request.max_tokens
            micros = 0
            if current and current[1].routes:
                first = current[1].routes[0]
                price = await uow.llm.price_for(tenant_id, first.provider_id, first.model, _now())
                micros = cost_micros(
                    price, estimate_tokens - request.max_tokens, request.max_tokens
                )
            reservation = await uow.llm.reserve(
                tenant_id,
                _scopes(principal_id, api_key_id, profile_id),
                micros=micros,
                tokens=estimate_tokens,
                seconds=120,
            )
            return warnings, str(reservation.id)
    finally:
        await leases.release(lease)


async def release(database: Any, tenant_id: str, reservation_id: str | None) -> None:
    if reservation_id is None:
        return
    async with database.unit_of_work() as uow:
        await uow.llm.release_reservation(tenant_id, reservation_id)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


async def costed(uow: Any, record: CallRecord) -> CallRecord:
    """*record* with its cost from the price in force when it started."""
    if not record.provider_id or not record.model_requested:
        return record
    price = await uow.llm.price_for(
        record.tenant_id, record.provider_id, record.model_requested, record.started_at
    )
    if price is None:
        return record
    return dataclasses.replace(
        record,
        cost_micros=cost_micros(price, record.input_tokens, record.output_tokens),
        price_model_id=price.id,
    )

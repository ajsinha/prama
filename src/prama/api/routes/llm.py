"""Models over the API: the server is the only door to a model.

Programs and Prama agents send prompts here rather than holding provider
credentials themselves. The server then applies what an agent could not be
trusted to apply to itself: the purpose's profile and fallback, residency,
redaction, the budget, a per-principal rate, and a hash-chained record of the
call.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import collections
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import iterate_in_threadpool

from prama.api.deps import LlmUser, Uow
from prama.api.errors import problem_document
from prama.core.concurrency.limits import RateLimiter
from prama.llm import budget
from prama.llm.gateway import ResponseCache
from prama.llm.spi import Request as ModelRequest
from prama.llm.wiring import gateway_for, persist
from prama.semantic.values import Sensitivity

router = APIRouter(tags=["llm"])

#: Principals tracked by the rate limiter, at most; the least recently seen
#: goes first. A per-principal map with no bound is a leak an attacker can fill.
MAX_TRACKED = 10_000


class _Limiters:
    def __init__(self) -> None:
        self._buckets: collections.OrderedDict[str, RateLimiter] = collections.OrderedDict()

    def allow(self, key: str, per_minute: int) -> bool:
        bucket = self._buckets.pop(key, None) or RateLimiter(
            per_minute / 60.0, capacity=max(1.0, float(per_minute))
        )
        self._buckets[key] = bucket
        while len(self._buckets) > MAX_TRACKED:
            self._buckets.popitem(last=False)
        return bucket.try_acquire()


_limiters = _Limiters()


def _cache(request: Request) -> ResponseCache:
    """One bounded cache per application, created on first use."""
    state = request.app.state
    if getattr(state, "llm_cache", None) is None:
        state.llm_cache = ResponseCache()
    cache: ResponseCache = state.llm_cache
    return cache


class ChatIn(BaseModel):
    purpose: str = Field(..., max_length=64, examples=["author"])
    prompt: str = Field(..., max_length=200_000)
    system: str = Field("You are a careful assistant.", max_length=20_000)
    sensitivity: str = Field("internal", description="public | internal | pii | restricted")


class ChatOut(BaseModel):
    text: str
    model: str
    provider: str
    incomplete: str = ""
    grammar_enforced: bool = False
    warnings: list[str] = []


@router.post("/llm/chat", response_model=ChatOut)
async def chat(body: ChatIn, caller: LlmUser, uow: Uow, request: Request) -> ChatOut:
    """Send one prompt through a purpose's profile. Budgeted, rate-limited, recorded.

    The answer is a draft for a person or a deterministic check to judge. Nothing
    returned here is, or becomes, a verdict on data.
    """
    config = request.app.state.config
    per_minute = config.get_int("llm.per_principal_rpm", 60)
    who = caller.principal_id or caller.tenant_id
    if not _limiters.allow(who, per_minute):
        raise HTTPException(
            status_code=429,
            detail=f"more than {per_minute} model requests a minute",
            headers={"Retry-After": "60"},
        )
    try:
        sensitivity = Sensitivity(body.sensitivity)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"unknown sensitivity {body.sensitivity!r}"
        ) from exc

    question = ModelRequest(system=body.system, prompt=body.prompt, sensitivity=sensitivity)
    database = request.app.state.database
    try:
        warnings, reservation = await budget.admit(
            database,
            caller.tenant_id,
            body.purpose,
            question,
            principal_id=caller.principal_id,
            api_key_id=caller.api_key_id,
            holder=caller.api_key_id or caller.principal_id or "console",
        )
    except budget.BudgetExhausted as exc:
        # Recorded, then answered, rather than raised: raising rolls the unit
        # of work back and would take the record of the refusal with it.
        await uow.llm.append_calls(
            caller.tenant_id,
            [budget.refusal(caller.tenant_id, body.purpose, question, caller, str(exc))],
        )
        return JSONResponse(  # type: ignore[return-value]
            status_code=429,
            content=problem_document(exc, status=429, instance=str(request.url.path)),
            media_type="application/problem+json",
        )
    gateway, ledger = await gateway_for(
        uow,
        caller.tenant_id,
        surface="api",
        principal_id=caller.principal_id,
        api_key_id=caller.api_key_id,
        offline=config.get_bool("llm.offline", False),
        config=config,
        cache=_cache(request),
    )
    try:
        # Provider calls are blocking HTTP; run them off the event loop so one
        # slow model does not stall every other request this server is serving.
        response = await asyncio.to_thread(gateway.run, body.purpose, question)
    finally:
        # The record and the release in one short transaction of their own:
        # the reservation was written outside the request's transaction so
        # other servers could see it, and releasing it from there while the
        # request held a write would deadlock a single-writer engine.
        async with database.unit_of_work() as own:
            await persist(own, caller.tenant_id, ledger)
            if reservation is not None:
                await own.llm.release_reservation(caller.tenant_id, reservation)
    return ChatOut(
        text=response.text,
        model=response.model,
        provider=response.provider,
        incomplete=response.incomplete,
        grammar_enforced=response.grammar_enforced,
        warnings=warnings,
    )


@router.post("/llm/chat/stream")
async def chat_stream(body: ChatIn, caller: LlmUser, uow: Uow, request: Request) -> Any:
    """The same as ``/llm/chat``, answered as server-sent events.

    ``data: {"text": "…"}`` per piece, then ``event: done``. Tokens are pulled
    from the provider one at a time on a worker thread, so a slow client
    slows the model rather than filling a buffer.
    """
    config = request.app.state.config
    per_minute = config.get_int("llm.per_principal_rpm", 60)
    if not _limiters.allow(caller.principal_id or caller.tenant_id, per_minute):
        raise HTTPException(
            status_code=429, detail="too many model requests", headers={"Retry-After": "60"}
        )
    try:
        sensitivity = Sensitivity(body.sensitivity)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"unknown sensitivity {body.sensitivity!r}"
        ) from exc
    question = ModelRequest(system=body.system, prompt=body.prompt, sensitivity=sensitivity)
    database = request.app.state.database
    warnings, reservation = await budget.admit(
        database,
        caller.tenant_id,
        body.purpose,
        question,
        principal_id=caller.principal_id,
        api_key_id=caller.api_key_id,
        holder=caller.api_key_id or caller.principal_id or "console",
    )
    gateway, ledger = await gateway_for(
        uow,
        caller.tenant_id,
        surface="api",
        principal_id=caller.principal_id,
        api_key_id=caller.api_key_id,
        offline=config.get_bool("llm.offline", False),
        config=config,
    )

    async def events() -> AsyncIterator[str]:
        try:
            for warning in warnings:
                yield f"event: warning\ndata: {json.dumps({'warning': warning})}\n\n"
            async for piece in iterate_in_threadpool(gateway.run_stream(body.purpose, question)):
                yield f"data: {json.dumps({'text': piece})}\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            async with database.unit_of_work() as own:
                await persist(own, caller.tenant_id, ledger)
                if reservation is not None:
                    await own.llm.release_reservation(caller.tenant_id, reservation)

    return StreamingResponse(events(), media_type="text/event-stream")

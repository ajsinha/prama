"""The model gateway's administration over the API: the Models page, for a program.

Providers, the purpose-to-route profiles, versioned prompt templates, prices,
budgets, evaluation runs and the hash-chained call ledger. Everything here is
administration and needs the ``admin`` scope, as the console's Models page
does. Sending a prompt as an ordinary user is ``/llm/chat`` (``llm:use``).

**No secret is ever stored.** A provider carries a secret *reference*
(``env://OPENAI_KEY``, ``vault://llm/key``), resolved only when a call is made.
A value that is not a reference is refused rather than stored, and a
provider's settings may not carry a key whose name says it is a credential.
Neither the reference nor any setting is echoed back: a listing says only
whether a reference is set.

What a model returns here is a draft for a person to read, never a decision
about data (CON-007). Evaluation runs grade a model's answers against fixed,
deterministic expectations.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from prama.api.deps import Administrator, Uow
from prama.core.errors import NotFoundError, PramaError, ValidationError
from prama.core.log import SENSITIVE_KEYS
from prama.llm.budget import period_start
from prama.llm.kinds import DIALECTS, KINDS, ProviderSpec, build
from prama.llm.spi import Request as ModelRequest
from prama.llm.wiring import gateway_for, persist
from prama.secrets.reference import SecretRef

router = APIRouter(tags=["models"])

HOSTINGS = ("self_hosted", "tenant", "hosted")
BUDGET_KINDS = ("tenant", "profile", "principal", "api_key")
PERIODS = ("day", "month")
ACTIONS = ("refuse", "warn")


def _gated(request: Request) -> bool:
    return bool(request.app.state.config.get_bool("llm.eval.gate_activation", False))


def _micros(amount: str | float | int, what: str) -> int:
    try:
        return int(Decimal(str(amount)) * 1_000_000)
    except InvalidOperation as exc:
        raise ValidationError(
            f"{what} is not a number", remedy="For example 2.50", cause=exc
        ) from exc


def _money(micros: int | None) -> str | None:
    return None if micros is None else str(Decimal(micros) / Decimal(1_000_000))


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


# -- providers -------------------------------------------------------------


class ProviderIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    kind: str = Field(..., description="openai_compatible | anthropic | bedrock | …")
    hosting: str = Field(..., description="self_hosted | tenant | hosted")
    endpoint: str = Field("", max_length=512)
    dialect: str = Field("", max_length=32)
    region: str = Field("", max_length=32)
    #: A reference such as env://OPENAI_KEY. Never the credential itself.
    credential_ref: str = Field("", max_length=512)
    #: Non-secret provider settings, e.g. the scripted kind's fixed answers.
    settings: dict[str, Any] = Field(default_factory=dict)


def _describe_provider(p: Any) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "name": p.name,
        "kind": p.kind,
        "dialect": p.dialect,
        "hosting": p.hosting,
        "endpoint": p.endpoint,
        "region": p.region,
        "enabled": bool(p.enabled),
        "credential": "reference set" if p.credential_ref else "none",
    }


def _no_secrets_in(settings: dict[str, Any], path: str = "settings") -> None:
    for key, value in settings.items():
        if str(key).lower() in SENSITIVE_KEYS:
            raise ValidationError(
                f"{path}.{key} looks like a credential, and a provider stores none",
                remedy=(
                    "Put the secret in your secret manager or an environment variable and "
                    "pass credential_ref='env://NAME' instead."
                ),
                context={"setting": f"{path}.{key}"},
            )
        if isinstance(value, dict):
            _no_secrets_in(value, f"{path}.{key}")


@router.get("/models/kinds")
async def kinds(caller: Administrator) -> dict[str, Any]:
    """The provider kinds, OpenAI-compatible dialects and hosting classes."""
    return {"kinds": dict(KINDS), "dialects": sorted(DIALECTS), "hostings": list(HOSTINGS)}


@router.get("/models/providers")
async def providers(uow: Uow, caller: Administrator) -> list[dict[str, Any]]:
    """The configured providers. A credential shows only as "reference set"."""
    return [_describe_provider(p) for p in await uow.llm.providers(caller.tenant_id)]


@router.post("/models/providers", status_code=201)
async def add_provider(body: ProviderIn, uow: Uow, caller: Administrator) -> dict[str, Any]:
    """Add a provider. The credential is a reference, resolved only at call time."""
    reference = body.credential_ref.strip()
    if reference:
        SecretRef.parse(reference)  # a pasted key is refused, not stored
    _no_secrets_in(body.settings)
    spec = ProviderSpec(
        name=body.name.strip(),
        kind=body.kind,
        hosting=body.hosting,
        endpoint=body.endpoint.strip(),
        dialect=body.dialect,
        region=body.region.strip(),
        settings=body.settings,
    )
    build(spec, model="probe")  # refuse now what could never be used
    row = await uow.llm.add_provider(
        caller.tenant_id,
        name=spec.name,
        kind=spec.kind,
        hosting=spec.hosting,
        endpoint=spec.endpoint,
        dialect=spec.dialect,
        region=spec.region,
        credential_ref=reference or None,
        settings=body.settings,
        by=caller.principal_id,
    )
    await uow.flush()
    return _describe_provider(row)


# -- profiles --------------------------------------------------------------


class ProfileIn(BaseModel):
    purpose: str = Field(..., min_length=1, max_length=64)
    #: ``provider:model`` steps, tried in order.
    route: list[str] = Field(..., min_length=1)
    attempts: int = Field(2, ge=1, le=10)
    fallback_across_hosting: bool = False
    note: str = Field("", max_length=2000)


class ActivateIn(BaseModel):
    version: int = Field(..., ge=1)


async def _profiles(uow: Any, tenant: str) -> list[dict[str, Any]]:
    names = {p.id: p.name for p in await uow.llm.providers(tenant)}
    out = []
    for profile in await uow.llm.profiles(tenant):
        versions = sorted(profile.versions, key=lambda v: v.version)
        out.append(
            {
                "purpose": profile.purpose,
                "current_version": profile.current_version,
                "versions": [
                    {
                        "version": v.version,
                        "current": v.version == profile.current_version,
                        "route": [f"{names.get(r.provider_id, '?')}:{r.model}" for r in v.routes],
                        "max_attempts": v.max_attempts,
                        "fallback_across_hosting": bool(v.fallback_across_hosting),
                        "note": v.note,
                        "eval_run_id": v.eval_run_id,
                        "recorded_at": _iso(v.recorded_at),
                        "recorded_by": v.recorded_by,
                    }
                    for v in versions
                ],
            }
        )
    return out


@router.get("/models/profiles")
async def profiles(uow: Uow, caller: Administrator) -> list[dict[str, Any]]:
    """Each purpose, its versions and which one is current."""
    return await _profiles(uow, caller.tenant_id)


@router.post("/models/profiles", status_code=201)
async def set_profile(
    body: ProfileIn, uow: Uow, caller: Administrator, request: Request
) -> dict[str, Any]:
    """Record a new version of a purpose's route. With the evaluation gate on it
    waits for a passing run and an explicit activation; otherwise it is current."""
    steps: list[tuple[str, str]] = []
    for step in body.route:
        provider, sep, model = step.strip().partition(":")
        if not sep or not provider or not model:
            raise ValidationError(
                f"{step!r} is not provider:model",
                remedy="Write each step as provider:model, e.g. local:qwen2.5-coder:7b.",
            )
        steps.append((provider.strip(), model.strip()))
    gated = _gated(request)
    version = await uow.llm.set_profile(
        caller.tenant_id,
        body.purpose.strip(),
        steps,
        max_attempts=body.attempts,
        fallback_across_hosting=body.fallback_across_hosting,
        note=body.note,
        by=caller.principal_id,
        activate=not gated,
    )
    return {"purpose": body.purpose.strip(), "version": version.version, "current": not gated}


@router.post("/models/profiles/{purpose}/activate")
async def activate_profile(
    purpose: str, body: ActivateIn, uow: Uow, caller: Administrator, request: Request
) -> dict[str, Any]:
    """Make a recorded version current; with the gate on, only after a passing run."""
    found = await uow.llm_governance.activate_profile(
        caller.tenant_id, purpose, body.version, require_eval=_gated(request)
    )
    return {"purpose": purpose, "version": found.version, "eval_run_id": found.eval_run_id}


# -- templates -------------------------------------------------------------


class TemplateIn(BaseModel):
    #: The template document: name, system, body, variables, response_schema.
    document: dict[str, Any]


@router.get("/models/templates")
async def templates(uow: Uow, caller: Administrator) -> list[dict[str, Any]]:
    """Every template version, its status, and which is current."""
    out = []
    for row in await uow.llm_governance.templates(caller.tenant_id):
        for v in await uow.llm_governance.template_versions(caller.tenant_id, row.name):
            out.append(
                {
                    "name": row.name,
                    "version": v.version,
                    "status": v.status,
                    "current": v.version == row.current_version,
                    "content_hash": v.content_hash,
                    "recorded_by": v.recorded_by,
                    "approved_by": v.approved_by,
                    "eval_run_id": v.eval_run_id,
                }
            )
    return out


@router.post("/models/templates", status_code=201)
async def add_template(body: TemplateIn, uow: Uow, caller: Administrator) -> dict[str, Any]:
    """Record a template as a new draft version (unchanged content: the same version)."""
    from prama.llm.templates import parse

    template = parse(body.document)
    row = await uow.llm_governance.add_template_version(
        caller.tenant_id, template, by=caller.principal_id
    )
    return {"name": template.name, "version": row.version, "status": row.status}


@router.post("/models/templates/{name}/versions/{version}/approve")
async def approve_template(
    name: str, version: int, uow: Uow, caller: Administrator, request: Request
) -> dict[str, Any]:
    """Approve a draft and make it current. Not by its author; with the gate, not
    before a passing evaluation run."""
    if not caller.principal_id:
        raise ValidationError("an approval names a person", remedy="Sign in as a person.")
    found = await uow.llm_governance.approve_template(
        caller.tenant_id, name, version, by=caller.principal_id, require_eval=_gated(request)
    )
    return {
        "name": name,
        "version": found.version,
        "status": found.status,
        "approved_by": found.approved_by,
    }


# -- prices and budgets ----------------------------------------------------


class PriceIn(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64)
    model: str = Field(..., min_length=1, max_length=128)
    #: Currency units per million tokens, e.g. "2.50".
    input_per_million: str = "0"
    output_per_million: str = "0"
    cached_per_million: str = "0"
    #: ISO-8601; empty means now. Earlier prices are kept.
    effective_from: str = ""


class BudgetIn(BaseModel):
    scope_kind: str = Field("tenant", description="tenant | profile | principal | api_key")
    scope_id: str = Field("", max_length=64)
    period: str = Field("month", description="day | month")
    #: An amount of money, e.g. "250.00"; omitted means no money limit.
    limit: str | None = None
    limit_tokens: int | None = Field(None, ge=0)
    action: str = Field("refuse", description="refuse | warn")


@router.get("/models/prices")
async def prices(uow: Uow, caller: Administrator) -> list[dict[str, Any]]:
    """Every dated price per million tokens, newest first within a model."""
    names = {p.id: p.name for p in await uow.llm.providers(caller.tenant_id)}
    return [
        {
            "provider": names.get(p.provider_id, "?"),
            "model": p.model,
            "input_per_million": _money(p.price_in_micros),
            "output_per_million": _money(p.price_out_micros),
            "cached_per_million": _money(p.price_cached_micros),
            "currency": p.currency,
            "effective_from": p.effective_from,
        }
        for p in await uow.llm.prices(caller.tenant_id)
    ]


@router.post("/models/prices", status_code=201)
async def set_price(body: PriceIn, uow: Uow, caller: Administrator) -> dict[str, Any]:
    """Record a dated price. A past call's cost stays explained by the price then."""
    row = await uow.llm.set_price(
        caller.tenant_id,
        body.provider.strip(),
        body.model.strip(),
        input_micros=_micros(body.input_per_million, "input_per_million"),
        output_micros=_micros(body.output_per_million, "output_per_million"),
        cached_micros=_micros(body.cached_per_million, "cached_per_million"),
        effective_from=body.effective_from.strip(),
    )
    return {"provider": body.provider, "model": row.model, "effective_from": row.effective_from}


@router.get("/models/budgets")
async def budgets(uow: Uow, caller: Administrator) -> list[dict[str, Any]]:
    """Each budget and what has been spent against it this period."""
    out = []
    for b in await uow.llm.budgets(caller.tenant_id):
        spent, tokens = await uow.llm.spend(
            caller.tenant_id, period_start(b.period), scope_kind=b.scope_kind, scope_id=b.scope_id
        )
        out.append(
            {
                "scope_kind": b.scope_kind,
                "scope_id": b.scope_id,
                "period": b.period,
                "limit": _money(b.limit_micros),
                "limit_tokens": b.limit_tokens,
                "action": b.action,
                "spent": _money(spent),
                "spent_tokens": tokens,
            }
        )
    return out


@router.put("/models/budgets")
async def set_budget(body: BudgetIn, uow: Uow, caller: Administrator) -> dict[str, Any]:
    """Set (or replace) the budget for one scope and period."""
    for value, allowed, what in (
        (body.scope_kind, BUDGET_KINDS, "scope_kind"),
        (body.period, PERIODS, "period"),
        (body.action, ACTIONS, "action"),
    ):
        if value not in allowed:
            raise ValidationError(
                f"{what} {value!r} is not one of {', '.join(allowed)}",
                remedy=f"Use one of {', '.join(allowed)}.",
                context={what: value},
            )
    if body.scope_kind == "tenant" and body.scope_id:
        raise ValidationError(
            "an estate budget has no scope_id", remedy="Leave scope_id empty for scope_kind=tenant."
        )
    if body.scope_kind != "tenant" and not body.scope_id:
        raise ValidationError(
            f"a {body.scope_kind} budget names its {body.scope_kind}",
            remedy="Give scope_id: the profile, principal or key id.",
        )
    if body.limit is None and body.limit_tokens is None:
        raise ValidationError(
            "a budget with no limit limits nothing",
            remedy="Give limit (money) or limit_tokens, or both.",
        )
    row = await uow.llm.set_budget(
        caller.tenant_id,
        scope_kind=body.scope_kind,
        scope_id=body.scope_id,
        period=body.period,
        limit_micros=None if body.limit is None else _micros(body.limit, "limit"),
        limit_tokens=body.limit_tokens,
        action=body.action,
        by=caller.principal_id,
    )
    return {
        "scope_kind": row.scope_kind,
        "scope_id": row.scope_id,
        "period": row.period,
        "limit": _money(row.limit_micros),
        "limit_tokens": row.limit_tokens,
        "action": row.action,
    }


# -- the ledger, trying a model, evaluation --------------------------------


@router.get("/models/calls")
async def calls(
    uow: Uow, caller: Administrator, limit: int = Query(50, ge=1, le=1000)
) -> list[dict[str, Any]]:
    """The most recent model calls, newest first: hashes and costs, never text."""
    return [
        {
            "sequence": c.sequence,
            "started_at": c.started_at,
            "finished_at": c.finished_at,
            "surface": c.surface,
            "purpose": c.purpose,
            "principal_id": c.principal_id,
            "api_key_id": c.api_key_id,
            "provider_kind": c.provider_kind,
            "hosting": c.hosting,
            "model": c.model_requested,
            "model_reported": c.model_reported,
            "profile_version": c.profile_version,
            "template_version": c.template_version,
            "sensitivity": c.sensitivity,
            "input_tokens": c.input_tokens,
            "output_tokens": c.output_tokens,
            "cost": _money(c.cost_micros),
            "latency_ms": c.latency_ms,
            "attempts": c.attempts,
            "served_from": c.served_from,
            "outcome": c.outcome,
            "prompt_hash": c.prompt_hash,
            "response_hash": c.response_hash,
            "record_hash": c.record_hash,
        }
        for c in await uow.llm.calls(caller.tenant_id, limit=limit)
    ]


@router.get("/models/calls/verify")
async def verify(uow: Uow, caller: Administrator) -> dict[str, Any]:
    """Recompute the call ledger's hash chain: ``prama llm verify``."""
    intact, checked, where = await uow.llm.verify_calls(caller.tenant_id)
    return {"intact": intact, "checked": checked, "break": where}


class TryIn(BaseModel):
    purpose: str = Field(..., min_length=1, max_length=64)
    prompt: str = Field(..., max_length=200_000)
    system: str = Field("You are a careful assistant.", max_length=20_000)


@router.post("/models/try")
async def try_model(
    body: TryIn, uow: Uow, caller: Administrator, request: Request
) -> dict[str, Any]:
    """Send one prompt through a purpose's profile, as the Models page's tester
    does, and record it in the ledger. A failure is answered, not raised."""
    config = request.app.state.config
    try:
        gateway, ledger = await gateway_for(
            uow,
            caller.tenant_id,
            surface="api",
            principal_id=caller.principal_id,
            api_key_id=caller.api_key_id,
            offline=config.get_bool("llm.offline", False),
            config=config,
        )
        try:
            response = await asyncio.to_thread(
                gateway.run, body.purpose, ModelRequest(system=body.system, prompt=body.prompt)
            )
        finally:
            await persist(uow, caller.tenant_id, ledger)
    except PramaError as exc:
        return {"text": "", "incomplete": str(exc), "provider": "", "model": ""}
    return {
        "text": response.text,
        "incomplete": response.incomplete,
        "provider": response.provider,
        "model": response.model,
    }


class EvalIn(BaseModel):
    #: The suite: purpose, optional template, cases each with an ``expect``.
    suite: dict[str, Any]
    profile_version: int | None = Field(None, ge=1)
    template_version: int | None = Field(None, ge=1)


def _describe_run(row: Any, *, report: bool) -> dict[str, Any]:
    out = {
        "id": str(row.id),
        "suite": row.suite,
        "purpose": row.purpose,
        "status": row.status,
        "cases": row.cases,
        "passed": row.passed,
        "profile_version": row.profile_version,
        "template_version": row.template_version,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "started_by": row.started_by,
    }
    if report:
        out["report"] = json.loads(row.report_json or "[]")
    return out


@router.post("/models/evaluations", status_code=201)
async def run_evaluation(
    body: EvalIn, uow: Uow, caller: Administrator, request: Request
) -> dict[str, Any]:
    """Run an evaluation suite against a profile (and template) version.

    Graded by deterministic checks; the run is recorded, and a passing one is
    what the activation gate asks for.
    """
    from prama.llm.evaluation import run_suite

    row = await run_suite(
        uow,
        caller.tenant_id,
        body.suite,
        config=request.app.state.config,
        profile_version=body.profile_version,
        template_version=body.template_version,
        by=caller.principal_id,
    )
    return _describe_run(row, report=True)


@router.get("/models/evaluations")
async def evaluations(
    uow: Uow, caller: Administrator, limit: int = Query(50, ge=1, le=500)
) -> list[dict[str, Any]]:
    """Recent evaluation runs, newest first."""
    return [
        _describe_run(r, report=False)
        for r in await uow.llm_governance.eval_runs(caller.tenant_id, limit=limit)
    ]


@router.get("/models/evaluations/{run_id}")
async def evaluation(run_id: str, uow: Uow, caller: Administrator) -> dict[str, Any]:
    """One evaluation run with its per-case report."""
    for row in await uow.llm_governance.eval_runs(caller.tenant_id, limit=500):
        if str(row.id) == run_id:
            return _describe_run(row, report=True)
    raise NotFoundError(
        "no such evaluation run",
        remedy="List them: client.models.evaluations().",
        context={"run": run_id},
    )

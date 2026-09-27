"""``prama llm`` — model providers, profiles, and the call ledger.

Providers say where a model is and how it is hosted; profiles map a purpose
("author", "explain") to an ordered route of provider and model. Every call
made through ``prama llm ask`` or the console lands in the hash-chained call
ledger, which ``prama llm calls`` reads. The same data is on the Models page.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.core.errors import ValidationError


def _tenant(ctx: CommandContext) -> str:
    given = str(getattr(ctx.args, "tenant", "") or "").strip()
    resolved = given or ctx.config.get_str("tenancy.default_tenant", "")
    if not resolved:
        raise ValidationError(
            "no estate to configure models for",
            remedy="Pass --tenant, or set tenancy.default_tenant.",
        )
    return resolved


def _with_uow(ctx: CommandContext, work: Callable[[Any, str], Awaitable[Any]]) -> Any:
    """Run *work(uow, tenant_id)* in one unit of work against the configured database."""
    from prama.cli.principal import _resolve_tenant
    from prama.db import Database

    database = Database.from_config(ctx.config)

    async def go() -> Any:
        await database.start()
        try:
            async with database.unit_of_work() as uow:
                return await work(uow, await _resolve_tenant(uow, _tenant(ctx)))
        finally:
            await database.stop()

    return asyncio.run(go())


def _tenant_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tenant", default="", help="slug or id; defaults to the configured one")


class ProviderAddCommand(Command):
    name = "add"
    help = "add a model provider (no secret: pass a secret reference)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        from prama.llm.kinds import DIALECTS, KINDS

        parser.add_argument("name")
        parser.add_argument("--kind", required=True, choices=sorted(KINDS))
        parser.add_argument(
            "--hosting",
            required=True,
            choices=["self_hosted", "tenant", "hosted"],
            help="where the model runs; decides what data may be sent to it",
        )
        parser.add_argument("--endpoint", default="", help="e.g. http://localhost:11434")
        parser.add_argument("--dialect", default="", choices=["", *sorted(DIALECTS)])
        parser.add_argument("--region", default="", help="a jurisdiction such as EU")
        parser.add_argument(
            "--credential-ref", default="", help="e.g. env://OPENAI_KEY or vault://llm/key"
        )
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.llm.kinds import ProviderSpec, build

        args = ctx.args
        # Built once before storing, so a provider that could never be used
        # (a vendor API declared self-hosted, an unknown dialect) is refused
        # now rather than on the first call.
        build(
            ProviderSpec(
                name=args.name,
                kind=args.kind,
                hosting=args.hosting,
                endpoint=args.endpoint,
                dialect=args.dialect,
                region=args.region,
            ),
            model="probe",
        )

        async def work(uow: Any, tenant: str) -> str:
            row = await uow.llm.add_provider(
                tenant,
                name=args.name,
                kind=args.kind,
                hosting=args.hosting,
                endpoint=args.endpoint,
                dialect=args.dialect,
                region=args.region,
                credential_ref=args.credential_ref or None,
            )
            await uow.flush()
            return str(row.id)

        identifier = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json({"id": identifier, "name": args.name})
        else:
            ctx.emit(f"provider {args.name} added ({args.kind}, {args.hosting})")
        return EXIT_OK


class ProviderListCommand(Command):
    name = "list"
    help = "the configured providers"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> list[dict[str, Any]]:
            return [
                {
                    "name": p.name,
                    "kind": p.kind,
                    "dialect": p.dialect,
                    "hosting": p.hosting,
                    "endpoint": p.endpoint,
                    "enabled": p.enabled,
                    "credential": "reference set" if p.credential_ref else "none",
                }
                for p in await uow.llm.providers(tenant)
            ]

        rows = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(rows)
        elif not rows:
            ctx.emit("No providers. Add one, for example:")
            ctx.emit("  prama llm provider add local --kind openai_compatible \\")
            ctx.emit("    --hosting self_hosted \\")
            ctx.emit("    --dialect ollama --endpoint http://localhost:11434")
        for row in [] if ctx.json_output else rows:
            state = "" if row["enabled"] else "  [disabled]"
            kind = f"{row['kind']}/{row['dialect'] or '-'}"
            ctx.emit(f"{row['name']}  {kind}  {row['hosting']}{state}")
            ctx.emit(f"  {row['endpoint'] or '(no endpoint)'}  credential: {row['credential']}")
        return EXIT_OK


class ProfileSetCommand(Command):
    name = "set"
    help = "point a purpose at an ordered route of provider:model"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("purpose", help="e.g. author, explain, summarise")
        parser.add_argument(
            "--route",
            action="append",
            default=[],
            required=True,
            help="provider:model, repeatable, tried in order",
        )
        parser.add_argument("--attempts", type=int, default=2, help="tries per candidate")
        parser.add_argument(
            "--fallback-across-hosting",
            action="store_true",
            help="allow falling back to a less local provider",
        )
        parser.add_argument("--note", default="")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        route: list[tuple[str, str]] = []
        for step in ctx.args.route:
            provider, sep, model = str(step).partition(":")
            if not sep or not provider or not model:
                raise ValidationError(
                    f"{step!r} is not provider:model",
                    remedy="Write each step as provider:model, e.g. local:qwen2.5-coder:7b.",
                )
            route.append((provider, model))

        async def work(uow: Any, tenant: str) -> int:
            version = await uow.llm.set_profile(
                tenant,
                ctx.args.purpose,
                route,
                max_attempts=ctx.args.attempts,
                fallback_across_hosting=ctx.args.fallback_across_hosting,
                note=ctx.args.note,
            )
            return int(version.version)

        number = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json({"purpose": ctx.args.purpose, "version": number})
        else:
            ctx.emit(f"{ctx.args.purpose}: version {number} is now current")
        return EXIT_OK


class ProfileShowCommand(Command):
    name = "show"
    help = "each purpose's current route"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> list[dict[str, Any]]:
            names = {p.id: p.name for p in await uow.llm.providers(tenant)}
            out = []
            for profile in await uow.llm.profiles(tenant):
                current = await uow.llm.current(tenant, profile.purpose)
                if current is None:
                    continue
                version = current[1]
                out.append(
                    {
                        "purpose": profile.purpose,
                        "version": version.version,
                        "route": [
                            f"{names.get(r.provider_id, '?')}:{r.model}" for r in version.routes
                        ],
                    }
                )
            return out

        rows = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(rows)
        elif not rows:
            ctx.emit("No profiles. Set one, for example:")
            ctx.emit("  prama llm profile set author --route local:qwen2.5-coder")
        for row in [] if ctx.json_output else rows:
            ctx.emit(f"{row['purpose']} (v{row['version']}): {' -> '.join(row['route'])}")
        return EXIT_OK


class AskCommand(Command):
    name = "ask"
    help = "send one prompt through a purpose's profile, and record it"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("purpose")
        parser.add_argument("prompt")
        parser.add_argument("--system", default="You are a careful assistant.")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.llm.spi import Request
        from prama.llm.wiring import gateway_for, persist

        offline = ctx.config.get_bool("llm.offline", False)

        async def work(uow: Any, tenant: str) -> dict[str, Any]:
            gateway, ledger = await gateway_for(uow, tenant, surface="cli", offline=offline)
            try:
                response = gateway.run(
                    ctx.args.purpose, Request(system=ctx.args.system, prompt=ctx.args.prompt)
                )
            finally:
                await persist(uow, tenant, ledger)
            return {
                "text": response.text,
                "model": response.model,
                "provider": response.provider,
                "incomplete": response.incomplete,
                "grammar_enforced": response.grammar_enforced,
            }

        result = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(result)
        else:
            ctx.emit(result["text"] or f"(no answer: {result['incomplete']})")
            ctx.emit(f"  — {result['provider']} / {result['model']}")
        return EXIT_OK


class CallsCommand(Command):
    name = "calls"
    help = "the most recent model calls, newest first (hashes, never text)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--limit", type=int, default=20)
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        async def work(uow: Any, tenant: str) -> list[dict[str, Any]]:
            return [
                {
                    "sequence": c.sequence,
                    "started_at": c.started_at,
                    "surface": c.surface,
                    "purpose": c.purpose,
                    "model": c.model_requested,
                    "hosting": c.hosting,
                    "outcome": c.outcome,
                    "latency_ms": c.latency_ms,
                    "attempts": c.attempts,
                }
                for c in await uow.llm.calls(tenant, limit=ctx.args.limit)
            ]

        rows = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(rows)
        elif not rows:
            ctx.emit("No model calls recorded yet.")
        for r in [] if ctx.json_output else rows:
            ctx.emit(
                f"#{r['sequence']}  {r['started_at']}  {r['purpose']}  {r['model'] or '-'}"
                f"  {r['outcome']}  {r['latency_ms']} ms"
            )
        return EXIT_OK


class _Provider(CommandGroup):
    name = "provider"
    help = "where models run"

    def commands(self) -> list[Command]:
        return [ProviderAddCommand(), ProviderListCommand()]


class _Profile(CommandGroup):
    name = "profile"
    help = "which model serves which purpose"

    def commands(self) -> list[Command]:
        return [ProfileSetCommand(), ProfileShowCommand()]


class LlmCommand(CommandGroup):
    name = "llm"
    help = "model providers, profiles and the call ledger"

    def commands(self) -> list[Command]:
        return [_Provider(), _Profile(), AskCommand(), CallsCommand()]

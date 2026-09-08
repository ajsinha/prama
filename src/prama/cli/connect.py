"""Connectivity commands: test a connection, browse a source, profile it.

The Wave 3 release gate, in three commands. Point Prama at a source and get an
inventory with nobody having declared anything first.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from prama.cli.base import EXIT_DRIFT, EXIT_OK, Command, CommandContext, CommandGroup
from prama.connect.builtin import register_builtin
from prama.db import Database


class ConnectorsCommand(Command):
    name = "connectors"
    help = "list the installed connectors and what each one needs"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--key", help="show the full configuration form for one connector")

    def run(self, ctx: CommandContext) -> int:
        registry = register_builtin()
        if ctx.args.key:
            form = registry.schema(ctx.args.key).to_form()
            if ctx.json_output:
                ctx.emit_json(form)
            else:
                ctx.emit(f"{ctx.args.key}:")
                for group in form["groups"]:
                    ctx.emit(f"  [{group['name']}]")
                    for field in group["fields"]:
                        mark = "*" if field["required"] else " "
                        default = (
                            "" if field["default"] is None else f"  (default {field['default']!r})"
                        )
                        ctx.emit(f"   {mark} {field['name']:<24} {field['input']:<9}{default}")
                        if field["help"]:
                            ctx.emit(f"       {field['help']}")
            return EXIT_OK

        catalogue = registry.catalogue()
        if ctx.json_output:
            ctx.emit_json(catalogue)
        else:
            for entry in catalogue:
                ctx.emit(f"  {entry['key']:<14} {entry['kind']:<12} {entry['display_name']}")
            ctx.emit(f"\n{len(catalogue)} connector(s). Use --key to see one's form.")
        return EXIT_OK


class _ConnectionCommand(Command):
    """Shared plumbing for commands that act through a stored connection."""

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--connection", required=True, help="connection id")

    def _run(self, ctx: CommandContext, action: str) -> Any:
        register_builtin()

        async def go() -> Any:
            from prama.semantic.services import ConnectivityService

            database = Database.from_config(ctx.config)
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    service = ConnectivityService(uow)
                    return await getattr(self, action)(ctx, service)
            finally:
                await database.stop()

        return asyncio.run(go())


class ConnectionTestCommand(_ConnectionCommand):
    name = "test"
    help = "check whether a connection can reach its source, and may read it"

    async def _test(self, ctx: CommandContext, service: Any) -> Any:
        return await service.test(ctx.args.connection)

    def run(self, ctx: CommandContext) -> int:
        result = self._run(ctx, "_test")
        if ctx.json_output:
            ctx.emit_json(result)
        else:
            ctx.emit(f"{result['state']}: {result['detail']}")
            if result["needs_access_request"]:
                # The distinction that decides what the reader does next.
                ctx.emit("  this is an access problem, not a network one")
                for permission in result["missing_permissions"]:
                    ctx.emit(f"    request: {permission}")
        return EXIT_OK if result["usable"] else EXIT_DRIFT


class ConnectionDiscoverCommand(_ConnectionCommand):
    name = "discover"
    help = "browse a source, ranked as a person would scan it"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        super().configure(parser)
        parser.add_argument("--limit", type=int, default=50)

    async def _discover(self, ctx: CommandContext, service: Any) -> Any:
        return await service.discover(ctx.args.connection, limit=ctx.args.limit)

    def run(self, ctx: CommandContext) -> int:
        found = self._run(ctx, "_discover")
        if ctx.json_output:
            ctx.emit_json(
                [
                    {
                        "path": list(o.path),
                        "kind": o.kind,
                        "rows": o.estimated_rows,
                        "bytes": o.estimated_bytes,
                    }
                    for o in found
                ]
            )
        else:
            for obj in found:
                size = (
                    f"{obj.estimated_rows:,} rows"
                    if obj.estimated_rows is not None
                    else f"{(obj.estimated_bytes or 0):,} bytes"
                )
                ctx.emit(f"  {obj.qualified_name:<44} {obj.kind:<10} {size}")
            ctx.emit(f"\n{len(found)} object(s), largest first.")
        return EXIT_OK


class ConnectionProfileCommand(_ConnectionCommand):
    name = "profile"
    help = "profile a source: what is in it, and how confidently we know"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        super().configure(parser)
        parser.add_argument("--object", help="one object; omit to sweep the source")
        parser.add_argument("--limit", type=int, default=10, help="objects in a sweep")

    async def _profile(self, ctx: CommandContext, service: Any) -> Any:
        if ctx.args.object:
            return [await service.profile(ctx.args.connection, tuple(ctx.args.object.split(".")))]
        return await service.profile_source(ctx.args.connection, limit=ctx.args.limit)

    def run(self, ctx: CommandContext) -> int:
        runs = self._run(ctx, "_profile")
        if ctx.json_output:
            ctx.emit_json([run.to_dict() for run in runs])
            return EXIT_OK
        for run in runs:
            profile = run.profile
            ctx.emit(profile.summary())
            for column in profile.columns:
                notes = []
                if column.is_key_candidate:
                    notes.append("key candidate")
                if column.is_constant:
                    notes.append("constant")
                if column.null_rate:
                    notes.append(f"{column.null_rate:.1%} null")
                if (dominant := column.dominant_value) is not None:
                    notes.append(f"{dominant[1]:.0%} = {dominant[0]!r}")
                ctx.emit(
                    f"    {column.name:<26} {column.type_name:<12}"
                    f" {column.distinct_estimate:>9,} distinct"
                    + (f"   [{', '.join(notes)}]" if notes else "")
                )
            ctx.emit("")
        return EXIT_OK


class ConnectCommand(CommandGroup):
    name = "connect"
    help = "test, browse and profile a configured source"

    def commands(self) -> list[Command]:
        return [
            ConnectionTestCommand(),
            ConnectionDiscoverCommand(),
            ConnectionProfileCommand(),
        ]

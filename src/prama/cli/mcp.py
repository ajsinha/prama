"""``prama mcp serve`` — the MCP server on stdio.

Runs in the foreground and speaks JSON-RPC on stdin and stdout, which is what
an MCP client expects to launch. Everything Prama would normally print goes to
stderr instead: a single stray line on stdout corrupts the stream and the
client reports a protocol error rather than the banner you meant to show it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import sys

from prama.assistant.tools import read_only_registry
from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.core.errors import PramaError
from prama.mcp import Server, serve_stdio
from prama.mcp.estate import estate_for


class McpServeCommand(Command):
    name = "serve"
    help = "run the MCP server on stdio (read-only tools: it cannot propose or change)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--tenant",
            default="",
            help="the estate to expose; defaults to tenancy.default_tenant",
        )

    def run(self, ctx: CommandContext) -> int:
        from prama.db import Database

        tenant = ctx.args.tenant or ctx.config.get_str("tenancy.default_tenant", "")
        if not tenant:
            raise PramaError(
                "no tenant to expose over MCP",
                code="CLI.NO_TENANT",
                remedy=(
                    "Pass --tenant, or set tenancy.default_tenant. An MCP client has no "
                    "way to say which estate it means, so it has to be chosen here."
                ),
            )
        database = Database.from_config(ctx.config)
        server = Server(read_only_registry(estate_for(database, tenant)))
        # To stderr, always. stdout is the protocol stream.
        print(f"prama mcp: {len(server.tool_names())} tools, estate {tenant}", file=sys.stderr)
        serve_stdio(server, sys.stdin, sys.stdout)
        return EXIT_OK


class McpToolsCommand(Command):
    name = "tools"
    help = "list what the MCP server exposes, and its capability"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, ctx: CommandContext) -> int:
        """What a security reviewer asks for before enabling this at all.

        Answered without starting a server or touching a database, so it can be
        run from a change ticket.
        """
        from prama.assistant.tools import Estate

        registry = read_only_registry(Estate())
        rows = [
            {
                "name": name,
                "capability": registry.get(name).capability.value,
                "mutates": registry.get(name).capability.mutates,
                "returns_untrusted": registry.get(name).returns_untrusted,
                "description": registry.get(name).description,
            }
            for name in registry.names()
        ]
        if ctx.json_output:
            ctx.emit_json({"tools": rows, "any_mutates": any(row["mutates"] for row in rows)})
            return EXIT_OK
        for row in rows:
            marker = "!" if row["mutates"] else " "
            fence = " [fenced]" if row["returns_untrusted"] else ""
            ctx.emit(f" {marker} {row['name']:<20} {row['capability']:<8}{fence}")
            ctx.emit(f"     {row['description']}")
        ctx.emit()
        ctx.emit("No tool mutates the estate. There is none that could be added: the")
        ctx.emit("registry refuses a mutating capability at registration.")
        return EXIT_OK


class McpCommand(CommandGroup):
    name = "mcp"
    help = "expose Prama to an MCP client"

    def commands(self) -> list[Command]:
        return [McpServeCommand(), McpToolsCommand()]

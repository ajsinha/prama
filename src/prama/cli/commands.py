"""The commands themselves.

Wave 1 ships the three an operator needs before anything else exists:
``version``, ``config show`` (what am I actually running with?) and
``db init|verify|info`` (is my database what the schema file says it is?).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import socket

from prama.cli.apikey import ApiKeyCommand
from prama.cli.base import EXIT_DRIFT, EXIT_OK, Command, CommandContext, CommandGroup
from prama.cli.bench import BenchCommand
from prama.cli.bundle import BundleCommand
from prama.cli.connect import ConnectCommand, ConnectorsCommand
from prama.cli.contract import ContractCommand
from prama.cli.control import ControlCommand
from prama.cli.estate import EstateCommand
from prama.cli.llm import LlmCommand
from prama.cli.lsp import LspCommand
from prama.cli.mcp import McpCommand
from prama.cli.pack import PackCommand
from prama.cli.principal import PrincipalCommand
from prama.cli.tenant import TenantCommand
from prama.core.errors import PramaError, ValidationError
from prama.db import Database
from prama.version import IR_VERSION, PRODUCT_NAME, PRODUCT_TAGLINE, SCHEMA_VERSION, VERSION


class VersionCommand(Command):
    name = "version"
    help = "print version information"

    def run(self, ctx: CommandContext) -> int:
        payload = {
            "product": PRODUCT_NAME,
            "version": VERSION,
            "ir_version": IR_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
        if ctx.json_output:
            ctx.emit_json(payload)
        else:
            ctx.emit(f"{PRODUCT_NAME} {VERSION} — {PRODUCT_TAGLINE}")
            ctx.emit(f"  IR version:     {IR_VERSION}")
            ctx.emit(f"  schema version: {SCHEMA_VERSION}")
        return EXIT_OK


class ConfigShowCommand(Command):
    name = "show"
    help = "print the effective merged configuration, with secrets redacted"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--raw",
            action="store_true",
            help="do not redact (refused unless PRAMA_ALLOW_RAW_CONFIG=1)",
        )
        parser.add_argument("--provenance", action="store_true", help="show each value's source")

    def run(self, ctx: CommandContext) -> int:
        import os

        redact = not (ctx.args.raw and os.environ.get("PRAMA_ALLOW_RAW_CONFIG") == "1")
        flat = ctx.config.flatten(redact=redact)
        if not redact:
            # Before the output, and on stderr, so it is seen whether the caller
            # is reading text or piping JSON somewhere.
            ctx.warn("! secrets are NOT redacted below; do not paste this anywhere")
        if ctx.json_output:
            ctx.emit_json(flat)
            return EXIT_OK
        width = max((len(k) for k in flat), default=0)
        for key in sorted(flat):
            line = f"{key:<{width}}  {flat[key]!r}"
            if ctx.args.provenance:
                line += f"    [{ctx.config.provenance(key) or 'built-in defaults'}]"
            ctx.emit(line)
        return EXIT_OK


class ConfigCommand(CommandGroup):
    name = "config"
    help = "inspect configuration"

    def commands(self) -> list[Command]:
        return [ConfigShowCommand()]


class DbInitCommand(Command):
    name = "init"
    help = "apply the authoritative schema file (idempotent; never alters)"

    def run(self, ctx: CommandContext) -> int:
        database = Database.from_config(ctx.config)
        result = database.initialise()
        if ctx.json_output:
            ctx.emit_json(
                {
                    "dialect": result.dialect,
                    "schema_path": result.schema_path,
                    "digest": result.digest,
                    "statements": result.statements_executed,
                    "tables": result.tables_present,
                    "created": result.created,
                }
            )
        else:
            ctx.emit(result.summary())
        return EXIT_OK


class DbVerifyCommand(Command):
    name = "verify"
    help = "compare the live database with the schema file; report drift, never repair it"

    def run(self, ctx: CommandContext) -> int:
        database = Database.from_config(ctx.config)
        report = database.verify()
        if ctx.json_output:
            ctx.emit_json(
                {
                    "ok": report.ok,
                    "dialect": report.dialect,
                    "schema_path": report.schema_path,
                    "expected_digest": report.expected_digest,
                    "recorded_digest": report.recorded_digest,
                    "drifts": [
                        {
                            "kind": d.kind.value,
                            "object": d.object_name,
                            "detail": d.detail,
                            "blocking": d.blocking,
                        }
                        for d in report.drifts
                    ],
                }
            )
        else:
            ctx.emit(report.summary())
        return EXIT_OK if report.ok else EXIT_DRIFT


class DbInfoCommand(Command):
    name = "info"
    help = "show which database is configured and what it contains"

    def run(self, ctx: CommandContext) -> int:
        database = Database.from_config(ctx.config)
        dialect = database.dialect
        payload: dict[str, object] = {
            "dialect": dialect.name,
            "schema_file": str(database.settings.schema_file),
            # render_as_string(hide_password=True) is the only form of a URL
            # that may ever be printed or logged.
            "url": dialect.sync_url().render_as_string(hide_password=True),
        }
        # Reporting the configuration must not require the database to be
        # reachable: "what am I configured for?" is exactly the question asked
        # when it is *not* reachable.
        try:
            tables = dialect.list_tables(database.sync_engine())
            payload["reachable"] = True
            payload["tables"] = tables
        except Exception as exc:
            payload["reachable"] = False
            payload["tables"] = []
            payload["error"] = str(exc).splitlines()[0][:200]

        if ctx.json_output:
            ctx.emit_json(payload)
        else:
            ctx.emit(f"dialect:     {payload['dialect']}")
            ctx.emit(f"schema file: {payload['schema_file']}")
            ctx.emit(f"url:         {payload['url']}")
            if payload["reachable"]:
                listed = payload["tables"]
                assert isinstance(listed, list)
                ctx.emit(f"tables ({len(listed)}): {', '.join(listed) or '(none)'}")
            else:
                ctx.emit(f"reachable:   no — {payload['error']}")
        return EXIT_OK


class DbCommand(CommandGroup):
    name = "db"
    help = "database schema operations (Prama has no migrations)"

    def commands(self) -> list[Command]:
        return [DbInitCommand(), DbVerifyCommand(), DbInfoCommand()]


class ServeCommand(Command):
    name = "serve"
    help = "run the HTTP API"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        # Defaults are None so the configuration answers: `server.host` and
        # `server.port` are the one place the listener is stated.
        parser.add_argument("--host", default=None, help="bind address (server.host)")
        parser.add_argument("--port", type=int, default=None, help="port (server.port, 5900)")
        parser.add_argument("--reload", action="store_true", help="reload on code change")

    def run(self, ctx: CommandContext) -> int:
        try:
            import uvicorn
        except ImportError as exc:
            raise PramaError(
                "the HTTP server is not installed",
                code="CLI.SERVER_MISSING",
                remedy="Install it: pip install 'prama[serve]'.",
                cause=exc,
            ) from exc

        from prama.api import create_app

        if ctx.args.host is None:
            ctx.args.host = ctx.config.get_str("server.host", "127.0.0.1")
        port = int(
            ctx.args.port if ctx.args.port is not None else ctx.config.get_int("server.port")
        )
        if not 1 <= port <= 65535:
            raise ValidationError(
                f"{port} is not a port number",
                remedy="A TCP port is between 1 and 65535. server.port (5900) is the default.",
                context={"port": str(port)},
            )

        # Bound before anything is printed. The banner used to go out first and
        # uvicorn bound afterwards, so `--port 99999`, a busy port and an
        # unroutable host all printed a full success message and then failed —
        # the success banner was a statement about intent, not about what
        # happened (QA findings CLI-270, CLI-271, CLI-272).
        #
        # Binding here also means the URL printed is one somebody can open,
        # because the socket behind it already exists.
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((ctx.args.host, port))
            listener.listen(2048)
        except OSError as exc:
            listener.close()
            raise PramaError(
                f"cannot listen on {ctx.args.host}:{port}",
                code="CLI.BIND_FAILED",
                remedy=(
                    "Another process may already hold the port, or the address may "
                    "not belong to this host. Choose another with --port, or bind "
                    "0.0.0.0 to accept on every interface."
                ),
                cause=exc,
            ) from exc

        base = f"http://{ctx.args.host}:{port}"
        ctx.emit(f"Prama {VERSION} — {PRODUCT_TAGLINE}")
        if ctx.config.get_bool("web.enabled", True):
            # First, because it is the thing a person opens. The API and its
            # documentation are what a program uses, and printing them alone
            # left the console — the actual product — undiscoverable.
            ctx.emit(f"  Console  {base}/estate")
        ctx.emit(f"  API      {base}/api/v1")
        ctx.emit(f"  Docs     {base}/api/v1/docs")
        if ctx.config.get_bool("web.enabled", True) and not ctx.config.get_str(
            "tenancy.default_tenant", ""
        ):
            # Said at startup rather than discovered by clicking. Without a
            # tenant every console page redirects to a sign-in that does not
            # exist yet, which reads as a broken build rather than as a missing
            # setting.
            ctx.emit()
            ctx.emit("  No tenant is configured, so every console page will redirect to")
            ctx.emit("  a sign-in that does not exist yet. Create one and name it:")
            ctx.emit("      prama tenant create acme-bank --name 'Acme Bank'")
        # Flushed explicitly. stdout is line-buffered to a terminal and block-
        # buffered to anything else, and `Server.run` blocks forever — so under
        # systemd, Docker, or any `prama serve > log`, the banner sat in a
        # buffer that was never emptied and never appeared at all. That is
        # every real production invocation (QA finding CLI-276).
        ctx.out.flush()

        server = uvicorn.Server(
            uvicorn.Config(
                create_app(ctx.config),
                log_config=None,  # Prama configures logging itself
            )
        )
        try:
            server.run(sockets=[listener])
        finally:
            listener.close()
        return EXIT_OK


def all_commands() -> list[Command]:
    return [
        VersionCommand(),
        ConfigCommand(),
        ConnectCommand(),
        ConnectorsCommand(),
        BundleCommand(),
        ContractCommand(),
        ControlCommand(),
        DbCommand(),
        EstateCommand(),
        LspCommand(),
        McpCommand(),
        PackCommand(),
        BenchCommand(),
        PrincipalCommand(),
        ApiKeyCommand(),
        LlmCommand(),
        ServeCommand(),
        TenantCommand(),
    ]

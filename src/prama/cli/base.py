"""CLI framework.

An object-oriented command tree over ``argparse``: one class per command, each
declaring its own arguments and running its own logic. There is no third-party
CLI dependency, which matters for an air-gapped install where every wheel is a
question someone has to answer.

Every command inherits the global options — ``--config``, ``--set``,
``--log-level``, ``--json`` — so configuration is resolved identically no matter
which subcommand is invoked.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import sys
from abc import ABC, abstractmethod
from typing import Any, TextIO

from prama.core import pjson
from prama.core.config import Configuration, load_configuration
from prama.core.errors import PramaError
from prama.core.log import LoggingConfigurator
from prama.packs import install_shipped

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_DRIFT = 3


class CommandContext:
    """What a command is given: parsed arguments, configuration, and a stream."""

    def __init__(
        self,
        args: argparse.Namespace,
        *,
        out: TextIO | None = None,
        err: TextIO | None = None,
    ) -> None:
        self.args = args
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self._config: Configuration | None = None

    @property
    def config(self) -> Configuration:
        if self._config is None:
            from prama.secrets import resolver as secrets

            self._config = load_configuration(self.args.config, overrides=self.args.set or [])
            # Every command that resolves a credential does so as configured.
            secrets.configure(self._config)
        return self._config

    @property
    def json_output(self) -> bool:
        return bool(getattr(self.args, "json", False))

    def emit(self, text: str = "") -> None:
        print(text, file=self.out)

    def emit_json(self, payload: Any) -> None:
        print(pjson.dumps(payload, sort_keys=True, indent=True), file=self.out)

    def warn(self, text: str) -> None:
        """Say something to the operator that is not part of the output.

        On stderr deliberately. A warning printed to stdout either corrupts the
        JSON a caller is parsing, or — if it is skipped to keep the JSON valid —
        is not printed at all, which is how `config show --raw --json` came to
        dump unredacted configuration with none of the warning that the same
        command prints in text mode. stderr is the channel that survives a pipe.
        """
        print(text, file=self.err)


class Command(ABC):
    """One CLI command."""

    name: str = ""
    help: str = ""

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Declare this command's own arguments.

        Optional by design: most commands take none, and forcing every one to
        define an empty override would be ceremony, not safety.
        """
        _ = parser

    @abstractmethod
    def run(self, ctx: CommandContext) -> int:
        """Execute. Return a process exit code."""


class CommandGroup(Command):
    """A command with subcommands, e.g. ``prama db init``."""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        for command in self.commands():
            self._commands[command.name] = command

    def commands(self) -> list[Command]:
        return []

    def configure(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers(dest=f"{self.name}_command", metavar="<command>")
        for command in self._commands.values():
            sub = subparsers.add_parser(command.name, help=command.help, description=command.help)
            command.configure(sub)

    def run(self, ctx: CommandContext) -> int:
        chosen = getattr(ctx.args, f"{self.name}_command", None)
        if not chosen:
            ctx.emit(f"usage: prama {self.name} <{'|'.join(self._commands)}>")
            return EXIT_USAGE
        return self._commands[chosen].run(ctx)


class Application:
    """Builds the parser, dispatches, and turns Prama errors into exit codes."""

    def __init__(self, commands: list[Command]) -> None:
        self._commands = {c.name: c for c in commands}

    def build_parser(self) -> argparse.ArgumentParser:
        from prama.version import PRODUCT_TAGLINE, VERSION

        parser = argparse.ArgumentParser(
            prog="prama",
            description=f"Prama {VERSION} — {PRODUCT_TAGLINE}",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("--config", metavar="PATH", help="configuration file to load")
        parser.add_argument(
            "--set",
            action="append",
            metavar="KEY=VALUE",
            help="override one configuration key; repeatable",
        )
        parser.add_argument("--log-level", default=None, help="DEBUG | INFO | WARNING | ERROR")
        parser.add_argument("--json", action="store_true", help="emit machine-readable output")
        subparsers = parser.add_subparsers(dest="command", metavar="<command>")
        for command in self._commands.values():
            sub = subparsers.add_parser(command.name, help=command.help, description=command.help)
            command.configure(sub)
        return parser

    def run(self, argv: list[str] | None = None, *, out: TextIO | None = None) -> int:
        parser = self.build_parser()
        args = parser.parse_args(argv)
        if not args.command:
            parser.print_help(out or sys.stdout)
            return EXIT_USAGE
        ctx = CommandContext(args, out=out)
        try:
            # Before any command runs, so `prama control check` resolves the
            # same functions `prama pack list` advertises — and *after* the
            # configuration is known, so `plugins.disabled` is honoured here
            # exactly as `create_app` honours it. Installing at the entry point
            # instead meant reading the config was impossible: `--config` had
            # not been parsed, and reading a file the caller was about to
            # override would have been worse than reading none. QA round 3,
            # Q-63.
            install_shipped(disabled_plugins=ctx.config.get_list("plugins.disabled", []))
            LoggingConfigurator(
                level=args.log_level or ctx.config.get_str("logging.level", "INFO"),
                fmt="json" if args.json else ctx.config.get_str("logging.format", "text"),
            ).apply()
            return self._commands[args.command].run(ctx)
        except PramaError as exc:
            if ctx.json_output:
                ctx.emit_json({"error": exc.to_dict()})
            else:
                print(f"\nerror: {exc.message}", file=sys.stderr)
                print(f"  code: {exc.code}", file=sys.stderr)
                print(f"  next: {exc.remedy}", file=sys.stderr)
                for key, value in sorted(exc.context.items()):
                    print(f"  {key}: {value}", file=sys.stderr)
            return EXIT_ERROR
        except KeyboardInterrupt:
            print("\ninterrupted", file=sys.stderr)
            return EXIT_ERROR

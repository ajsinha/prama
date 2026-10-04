#!/usr/bin/env python
"""Prama — start the console and the API, from nothing.

    python run_prama_web.py

``prama serve`` is the real entry point and this does not replace it. What it
adds is the three steps somebody has to know about before ``serve`` is any use:
apply the schema, create the estate, and name that estate in configuration.
Discovering those by reading error messages is a first run nobody enjoys, and
"it redirected me to a sign-in page that does not exist" is the specific way a
fresh installation looks broken when it is merely empty.

So this is a *preparer*, not a second server. Every step below is the same code
path the CLI uses — ``prama db init``, ``prama tenant create``, ``prama serve``
— and there is deliberately no logic here that those commands do not already
have. A launcher with its own opinion about how to build the application is a
launcher that will one day start something the CLI cannot.

What it will not do:

* **Invent a secret.** ``security.session_secret`` is shipped empty on purpose
  and a fresh clone is meant to refuse to boot. Generating one here would mean
  every installation that never read the documentation runs on a key this file
  chose, and signed sessions would be forgeable by anyone holding the source.
* **Touch a database that is not SQLite** without being told. ``--prepare``
  applies the schema, and applying a schema to somebody's PostgreSQL because
  they ran a script called "run" is not a thing a script should decide.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
LOCAL_CONFIG = REPO / "config" / "application.local.yaml"

BANNER = r"""
   ___
  | _ \_ _ __ _ _ __  __ _     Prama {version}
  |  _/ '_/ _` | '  \/ _` |    Declare it. Prove it. Trust it.
  |_| |_| \__,_|_|_|_\__,_|
"""


def _fail(message: str, remedy: str = "") -> int:
    print(f"\n  {message}", file=sys.stderr)
    if remedy:
        print(f"  {remedy}", file=sys.stderr)
    return 1


def _configuration(path: str | None):
    from prama.core.config import load_configuration

    return load_configuration(Path(path)) if path else load_configuration()


def _secret_is_set(config) -> bool:
    return bool(config.get_str("security.session_secret", ""))


def _write_local_secret() -> str:
    """Write a generated secret into the git-ignored local file.

    Only ever on an explicit ``--init-secret``, and only into the file the
    pre-commit hook refuses to let a secret out of. The value is
    ``token_urlsafe`` rather than anything derived from the machine, because a
    secret you could recompute from the hostname is not one.
    """
    LOCAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(48)
    existing = LOCAL_CONFIG.read_text() if LOCAL_CONFIG.exists() else ""
    if "session_secret" in existing:
        # The goal of the flag, a secret in the local file, is already met. It
        # used to stop here with exit 1, which turned "run it again with the
        # same command" into a failure; the existing secret is kept, never
        # replaced, because rotating it would sign everybody out.
        return "kept"
    with LOCAL_CONFIG.open("a") as handle:
        handle.write(
            "\n# Written by run_prama_web.py --init-secret. This file is git-ignored;\n"
            "# the shipped config/application.yaml is tracked and must stay secretless.\n"
            "security:\n"
            f'  session_secret: "{generated}"\n'
        )
    return generated


async def _prepare(config, slug: str, name: str) -> tuple[str, bool]:
    """Schema, then estate. Returns the tenant id and whether it was created."""
    from prama.db import Database

    database = Database.from_config(config)
    database.initialise(applied_by="run_prama_web")
    await database.start()
    try:
        async with database.unit_of_work() as uow:
            existing = await uow.tenants.by_slug(slug)
            if existing is not None:
                return str(existing.id), False
            tenant = uow.tenants.create(slug=slug, display_name=name or slug)
            await uow.flush()
            return str(tenant.id), True
    finally:
        await database.stop()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start the Prama console and API.",
        epilog="Everything here is also available as `prama <command>`.",
    )
    # None, so configuration answers: server.host / server.port (5900).
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--reload", action="store_true", help="restart on every source change (development)"
    )
    parser.add_argument("--config", default="", help="configuration file to load")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="apply the schema and create the estate before serving",
    )
    parser.add_argument("--tenant-slug", default="acme-bank")
    parser.add_argument("--tenant-name", default="")
    parser.add_argument(
        "--init-secret",
        action="store_true",
        help="write a generated session secret into config/application.local.yaml",
    )
    args = parser.parse_args()

    from prama.core.errors import PramaError
    from prama.version import VERSION

    print(BANNER.format(version=VERSION))

    if args.init_secret:
        if _write_local_secret() == "kept":
            print(f"  {LOCAL_CONFIG} already has a session secret; keeping it")
        else:
            print(f"  wrote a session secret to {LOCAL_CONFIG}")

    try:
        config = _configuration(args.config or None)
    except PramaError as exc:
        return _fail(str(exc), getattr(exc, "remedy", ""))

    if not _secret_is_set(config):
        return _fail(
            "security.session_secret is empty, and Prama will not start without it.",
            "Run once with --init-secret, or export PRAMA_SECURITY__SESSION_SECRET.",
        )

    tenant = config.get_str("tenancy.default_tenant", "")

    if args.prepare:
        try:
            tenant, created = asyncio.run(_prepare(config, args.tenant_slug, args.tenant_name))
        except PramaError as exc:
            return _fail(str(exc), getattr(exc, "remedy", ""))
        print(f"  schema applied · estate {args.tenant_slug} · {tenant}")
        if created:
            print("  (created)")
        # Re-read with the tenant applied, rather than mutating the object the
        # rest of the process will use. Configuration is layered and immutable
        # by design, and a launcher that patched it in place would be the one
        # place in the codebase where it is not.
        from prama.core.config import ConfigurationBuilder

        config = (
            ConfigurationBuilder()
            .with_defaults(config.raw())
            .with_mapping({"tenancy": {"default_tenant": tenant}}, name="run-prama-web")
            .build()
        )

    try:
        import uvicorn
    except ImportError:
        return _fail(
            "the HTTP server is not installed.",
            'Install it: pip install -e ".[serve]".',
        )

    from prama.api import create_app

    if args.host is None:
        args.host = config.get_str("server.host", "127.0.0.1")
    if args.port is None:
        args.port = config.get_int("server.port")
    base = f"http://{args.host}:{args.port}"
    print()
    if config.get_bool("web.enabled", True):
        print(f"  Console  {base}/estate")
    print(f"  API      {base}/api/v1")
    print(f"  Docs     {base}/api/v1/docs")
    if config.get_bool("web.enabled", True) and not tenant:
        print()
        print("  No tenant is configured, so every console page will redirect to a")
        print("  sign-in that does not exist yet. Re-run with --prepare, or:")
        print("      prama tenant create acme-bank --name 'Acme Bank'")
    elif args.prepare:
        print()
        print("  This run set tenancy.default_tenant for itself only. To make it")
        print("  stick, put it in config/application.local.yaml:")
        print("      tenancy:")
        print(f"        default_tenant: {tenant}")
    print()
    # Flushed before uvicorn takes the process over. stdout is block-buffered
    # whenever it is not a terminal, so piping this to a file or running it
    # under a supervisor showed the log and never the URLs — which are the only
    # part somebody actually needs.
    sys.stdout.flush()

    if args.reload:
        # The worker is a fresh process: it gets the configuration file and
        # the estate this run chose through the environment, as any process
        # would (prama.api.reloading).
        from prama.api import reloading

        reloading.serve(
            args.host,
            args.port,
            config_path=args.config or None,
            environment={"PRAMA_TENANCY__DEFAULT_TENANT": tenant} if tenant else None,
        )
        return 0

    uvicorn.run(
        create_app(config),
        host=args.host,
        port=args.port,
        log_config=None,  # Prama configures logging itself
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

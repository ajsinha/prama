"""``prama tenant`` — the estate an installation is for.

Every other command takes ``--tenant`` and none of them could create one, which
made a fresh installation unreachable: the console reads its caller from
``tenancy.default_tenant``, that setting wants an identifier, and there was no
way to obtain an identifier short of opening a Python shell. A product whose
first step is "write a script" does not have a first step.

Deliberately not part of ``db init``. Applying the schema is an operation an
operator repeats — it is idempotent, it is safe, and it says nothing about who
the system is for. Creating the estate is a decision made once, and folding it
into the schema step would mean every ``db init`` on a shared database silently
added another tenant nobody asked for.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import asyncio
import re
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.core.errors import ConflictError, ValidationError

#: What a slug may contain. Lowercase, because it appears in URLs and in
#: configuration, and two tenants differing only in case is a distinction
#: nobody can see and everybody will trip over.
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class TenantCreateCommand(Command):
    name = "create"
    help = "create the estate this installation is for, and print its id"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("slug", help="short name, lowercase, e.g. acme-bank")
        parser.add_argument(
            "--name",
            default="",
            help="what people call it; defaults to the slug",
        )
        parser.add_argument(
            "--residency",
            default="",
            help="where this estate's data must stay, if that is constrained",
        )

    def run(self, ctx: CommandContext) -> int:
        from prama.db import Database

        slug = str(ctx.args.slug).strip().lower()
        if not SLUG.match(slug):
            raise ValidationError(
                f"{ctx.args.slug!r} is not a usable slug",
                remedy=(
                    "Lowercase letters, digits and hyphens, starting with a letter or "
                    "digit — it appears in URLs and in configuration."
                ),
                context={"slug": ctx.args.slug},
            )
        display = str(ctx.args.name).strip() or slug
        database = Database.from_config(ctx.config)

        async def go() -> tuple[str, str]:
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    existing = await uow.tenants.by_slug(slug)
                    if existing is not None:
                        # Refused rather than reused. Two runs of this command
                        # meaning "make one" and "you already have one" would
                        # make a typo in the slug indistinguishable from a
                        # second estate.
                        raise ConflictError(
                            f"there is already a tenant called {slug!r}",
                            remedy=(
                                f"Its id is {existing.id}. Use that, or choose a different slug."
                            ),
                            context={"slug": slug, "tenant": str(existing.id)},
                        )
                    tenant = uow.tenants.create(
                        slug=slug,
                        display_name=display,
                        residency=str(ctx.args.residency).strip() or None,
                    )
                    await uow.flush()
                    return str(tenant.id), tenant.display_name
            finally:
                await database.stop()

        tenant_id, name = asyncio.run(go())

        if ctx.json_output:
            ctx.emit_json({"id": tenant_id, "slug": slug, "display_name": name})
            return EXIT_OK
        ctx.emit(f"created {name} ({slug})")
        ctx.emit(f"  id: {tenant_id}")
        ctx.emit()
        # The next step, spelled out. An identifier printed without saying what
        # to do with it is a step somebody has to guess, and the guess is
        # usually "paste it into the tracked config file".
        ctx.emit("Set this as the console's default estate, so a signed-in person")
        ctx.emit("lands somewhere. Put it in config/application.local.yaml, which is")
        ctx.emit("git-ignored:")
        ctx.emit()
        ctx.emit("  tenancy:")
        ctx.emit(f"    default_tenant: {tenant_id}")
        ctx.emit()
        ctx.emit("Then create somebody who can sign in:")
        ctx.emit(f"  prama principal create <username> --admin --tenant {slug}")
        return EXIT_OK


class TenantListCommand(Command):
    name = "list"
    help = "the estates in this database"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, ctx: CommandContext) -> int:
        from prama.db import Database

        database = Database.from_config(ctx.config)

        async def go() -> list[dict[str, Any]]:
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    return [
                        {
                            "id": str(t.id),
                            "slug": t.slug,
                            "display_name": t.display_name,
                            "residency": t.residency,
                        }
                        for t in await uow.tenants.list_active()
                    ]
            finally:
                await database.stop()

        rows = asyncio.run(go())
        configured = ctx.config.get_str("tenancy.default_tenant", "")

        if ctx.json_output:
            ctx.emit_json({"tenants": rows, "default_tenant": configured})
            return EXIT_OK
        if not rows:
            ctx.emit("No tenants. Create one with `prama tenant create <slug>`.")
            ctx.emit("Until then the console has no estate to show and every page")
            ctx.emit("will send you to a sign-in that does not exist yet.")
            return EXIT_OK
        for row in rows:
            # Marked, because a list of three identifiers with no indication of
            # which one is configured is a list somebody reads and then still
            # has to check the configuration.
            marker = "*" if row["id"] == configured else " "
            ctx.emit(f" {marker} {row['id']}  {row['slug']:<24} {row['display_name']}")
        ctx.emit()
        if configured:
            ctx.emit("* is tenancy.default_tenant — the estate the console reads.")
        else:
            ctx.emit("tenancy.default_tenant is not set, so the console has no estate.")
        return EXIT_OK


class TenantCommand(CommandGroup):
    name = "tenant"
    help = "the estate this installation is for"

    def commands(self) -> list[Command]:
        return [TenantCreateCommand(), TenantListCommand()]


__all__ = ["SLUG", "TenantCommand", "TenantCreateCommand", "TenantListCommand"]

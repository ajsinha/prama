"""``prama principal`` — the people who sign in.

The console could not be signed into because nobody could be created. This is
that command, and the small set of built-in roles it grants from.

**Passwords are not accepted as arguments.** A password on a command line lands
in the shell history, in the process table where every other user on the box can
read it, and in whatever ships that machine's logs elsewhere. It is prompted for
when a terminal is attached and read from stdin when one is not, so a
provisioning script pipes it rather than passing it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import sys
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.core.errors import ConflictError, ValidationError

USERNAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")

#: The roles a fresh estate gets, and what each one may do.
#:
#: Four, not fourteen. A permission model nobody can hold in their head is one
#: nobody audits, and the separation that actually matters in this product is
#: between *proposing* a control and *approving* one — the rest is detail that
#: a deployment can add for itself.
BUILTIN_ROLES: dict[str, tuple[str, list[str]]] = {
    "admin": (
        "Everything, including creating other people.",
        ["*"],
    ),
    "owner": (
        "Declares datasets and approves controls. The business owner of an estate.",
        [
            "declaration:*",
            "relationship:*",
            "control:approve",
            "control:read",
            "attestation:sign",
            "evidence:read",
            "report:read",
        ],
    ),
    "steward": (
        "Works incidents and breaks; proposes controls but does not approve them.",
        [
            "control:propose",
            "control:read",
            "incident:*",
            "break:*",
            "evidence:read",
            "report:read",
            "declaration:read",
        ],
    ),
    "auditor": (
        "Reads everything and changes nothing.",
        [
            "control:read",
            "declaration:read",
            "relationship:read",
            "evidence:read",
            "report:read",
            "attestation:read",
        ],
    ),
}


def _read_password(confirm: bool = True) -> str:
    """From a prompt, or from stdin when there is no terminal.

    Never from an argument. A password passed on a command line is in the shell
    history and in the process table, where every other user on the machine can
    read it while it is being set.
    """
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if not piped:
            raise ValidationError(
                "no password on stdin",
                remedy="Pipe one: printf '%s' \"$PASSWORD\" | prama principal create alice",
            )
        return piped
    first = getpass.getpass("Password: ")
    if confirm and first != getpass.getpass("Again: "):
        raise ValidationError(
            "the two passwords did not match",
            remedy="Nothing was written. Run it again.",
        )
    return first


class PrincipalCreateCommand(Command):
    name = "create"
    help = "create somebody who can sign in"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("username")
        parser.add_argument("--tenant", default="", help="defaults to tenancy.default_tenant")
        parser.add_argument("--name", default="", help="display name; defaults to the username")
        parser.add_argument("--email", default="")
        parser.add_argument(
            "--role",
            action="append",
            default=[],
            help=f"repeatable; one of {', '.join(BUILTIN_ROLES)}",
        )
        parser.add_argument(
            "--admin",
            action="store_true",
            help="shorthand for --role admin",
        )

    def run(self, ctx: CommandContext) -> int:
        from prama.db import Database

        username = str(ctx.args.username).strip()
        if not USERNAME.match(username):
            raise ValidationError(
                f"{ctx.args.username!r} is not a usable username",
                remedy="Letters, digits, dot, underscore and hyphen; start with a letter or digit.",
                context={"username": ctx.args.username},
            )
        tenant = ctx.args.tenant or ctx.config.get_str("tenancy.default_tenant", "")
        if not tenant:
            raise ValidationError(
                "no tenant to create this principal in",
                remedy=(
                    "Pass --tenant, or set tenancy.default_tenant. Create an estate "
                    "first with `prama tenant create <slug>` if there is none."
                ),
            )
        wanted = list(ctx.args.role) + (["admin"] if ctx.args.admin else [])
        unknown = [r for r in wanted if r not in BUILTIN_ROLES]
        if unknown:
            raise ValidationError(
                f"unknown role(s): {', '.join(unknown)}",
                remedy=f"Built-in roles are {', '.join(BUILTIN_ROLES)}.",
                context={"roles": unknown},
            )

        password = _read_password()
        database = Database.from_config(ctx.config)

        async def go() -> tuple[str, list[str]]:
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    if await uow.principals.by_username(tenant, username) is not None:
                        raise ConflictError(
                            f"{username!r} already exists in this estate",
                            remedy="Choose another name, or reset the password instead.",
                            context={"username": username, "tenant": tenant},
                        )
                    principal = uow.principals.create(
                        tenant_id=tenant,
                        username=username,
                        display_name=str(ctx.args.name).strip() or username,
                        email=str(ctx.args.email).strip() or None,
                    )
                    uow.principals.set_password(principal, password)
                    await uow.flush()
                    granted = await _grant(uow, tenant, principal, wanted)
                    return str(principal.id), granted
            finally:
                await database.stop()

        principal_id, granted = asyncio.run(go())

        if ctx.json_output:
            ctx.emit_json({"id": principal_id, "username": username, "roles": granted})
            return EXIT_OK
        ctx.emit(f"created {username}")
        ctx.emit(f"  id:    {principal_id}")
        ctx.emit(f"  roles: {', '.join(granted) if granted else 'none'}")
        if not granted:
            # Said out loud. A principal with no role can sign in and do
            # nothing, which looks like a broken console rather than a
            # deliberate omission.
            ctx.emit()
            ctx.emit("  With no role this account can sign in and do nothing.")
            ctx.emit(f"  Grant one: --role {' | --role '.join(BUILTIN_ROLES)}")
        return EXIT_OK


class PrincipalListCommand(Command):
    name = "list"
    help = "who can sign in to an estate"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--tenant", default="", help="defaults to tenancy.default_tenant")

    def run(self, ctx: CommandContext) -> int:
        from prama.db import Database

        tenant = ctx.args.tenant or ctx.config.get_str("tenancy.default_tenant", "")
        if not tenant:
            raise ValidationError(
                "no tenant to list",
                remedy="Pass --tenant, or set tenancy.default_tenant.",
            )
        database = Database.from_config(ctx.config)

        async def go() -> list[dict[str, Any]]:
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    return [
                        {
                            "id": str(p.id),
                            "username": p.username,
                            "display_name": p.display_name,
                            "status": p.status,
                            "roles": p.role_names,
                            "can_sign_in": bool(p.password_hash),
                            "last_login_at": (
                                p.last_login_at.isoformat() if p.last_login_at else None
                            ),
                        }
                        for p in await uow.principals.list_for_tenant(tenant)
                    ]
            finally:
                await database.stop()

        rows = asyncio.run(go())
        if ctx.json_output:
            ctx.emit_json({"principals": rows})
            return EXIT_OK
        if not rows:
            ctx.emit("Nobody. Create one with `prama principal create <username> --admin`.")
            ctx.emit("Until then nobody can sign in, and the console falls back to")
            ctx.emit("tenancy.default_tenant if that is set.")
            return EXIT_OK
        for row in rows:
            # A principal with no password cannot sign in whatever its roles
            # say, and a list that showed only the roles would be describing an
            # account nobody can use as though it were in service.
            mark = " " if row["can_sign_in"] else "!"
            ctx.emit(
                f" {mark} {row['username']:<20} {row['status']:<10} "
                f"{', '.join(row['roles']) or 'no roles'}"
            )
        if any(not row["can_sign_in"] for row in rows):
            ctx.emit()
            ctx.emit("! has no password set and cannot sign in.")
        return EXIT_OK


class PrincipalRolesCommand(Command):
    name = "roles"
    help = "the built-in roles and what each one may do"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, ctx: CommandContext) -> int:
        """Answerable without a database, so it can be read from a change ticket."""
        rows = [
            {"name": name, "description": description, "permissions": permissions}
            for name, (description, permissions) in BUILTIN_ROLES.items()
        ]
        if ctx.json_output:
            ctx.emit_json({"roles": rows})
            return EXIT_OK
        for row in rows:
            ctx.emit(f"  {row['name']}")
            ctx.emit(f"    {row['description']}")
            ctx.emit(f"    {' '.join(row['permissions'])}")
            ctx.emit()
        ctx.emit("A role holding 'control:*' satisfies 'control:approve'. Wildcards go")
        ctx.emit("one level deep only: a model nobody can hold in their head is one")
        ctx.emit("nobody audits.")
        return EXIT_OK


async def _grant(uow: Any, tenant: str, principal: Any, wanted: list[str]) -> list[str]:
    """Grant roles, creating the built-in ones on first use.

    Created lazily rather than at ``db init``: a role nobody holds is a row that
    has to be explained, and an estate that never signs anybody in should not
    carry four of them.
    """
    granted: list[str] = []
    for name in wanted:
        role = await uow.roles.by_name(tenant, name)
        if role is None:
            description, permissions = BUILTIN_ROLES[name]
            role = uow.roles.create(
                tenant_id=tenant,
                name=name,
                permissions=permissions,
                description=description,
                builtin=True,
            )
            await uow.flush()
        await uow.roles.grant(str(principal.id), str(role.id))
        granted.append(name)
    return granted


class PrincipalCommand(CommandGroup):
    name = "principal"
    help = "the people who sign in"

    def commands(self) -> list[Command]:
        return [PrincipalCreateCommand(), PrincipalListCommand(), PrincipalRolesCommand()]


__all__ = ["BUILTIN_ROLES", "USERNAME", "PrincipalCommand"]

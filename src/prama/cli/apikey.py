"""``prama apikey`` — the credential the HTTP API requires.

Written because the API's own refusal named it and it did not exist. A caller
with no credential is told *"Create one with `prama apikey create`"*, and there
was no `apikey` command group at all — so on a clean install the HTTP API could
not be authenticated to by any supported means. A QA pass found it from both
ends: the API agent following the remedy, and the operator agent looking for a
way in.

**The plaintext is shown once.** Only its prefix and a hash are stored, so
there is no "show me that key again" — a key that can be re-read from the
database is a key the database's backups also carry.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.core.errors import ValidationError
from prama.security.scopes import SCOPES, unknown


def _tenant_of(ctx: CommandContext) -> str:
    given = str(getattr(ctx.args, "tenant", "") or "").strip()
    configured = ctx.config.get_str("tenancy.default_tenant", "")
    resolved = given or configured
    if not resolved:
        raise ValidationError(
            "no estate to issue this key for",
            remedy="Pass --tenant, or set tenancy.default_tenant.",
        )
    return resolved


class ApiKeyCreateCommand(Command):
    name = "create"
    help = "issue an API key; the plaintext is printed once and never stored"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("name", help="what this key is for, e.g. 'ci' or 'etl-nightly'")
        parser.add_argument(
            "--tenant", default="", help="slug or id; defaults to the configured one"
        )
        parser.add_argument(
            "--principal",
            required=True,
            help=(
                "username the key acts as. Required: every key is attributable, "
                "so an audit trail names a person and not just a credential. "
                "The principal's roles are NOT inherited — scopes are explicit."
            ),
        )
        parser.add_argument(
            "--scope",
            action="append",
            default=[],
            metavar="SCOPE",
            help=f"repeatable; one of {', '.join(sorted(SCOPES))}, or '*'",
        )
        parser.add_argument(
            "--expires-in-days",
            type=int,
            default=0,
            help="0 means no expiry, which is a decision rather than a default",
        )
        parser.add_argument("--environment", default="live", help="prefix tag: live | test")

    def run(self, ctx: CommandContext) -> int:
        from prama.cli.principal import _resolve_tenant
        from prama.db import Database
        from prama.db.security import ApiKeyIssuer

        scopes = list(ctx.args.scope)
        if not scopes:
            raise ValidationError(
                "a key with no scopes can do nothing",
                remedy=(
                    "Pass --scope at least once. An empty scope list is refused "
                    "everywhere, deliberately: 'none recorded' must not mean 'no "
                    f"limit'. Available: {', '.join(sorted(SCOPES))}, or '*'."
                ),
            )
        invented = unknown(scopes)
        if invented:
            raise ValidationError(
                f"unknown scope(s): {', '.join(invented)}",
                remedy=f"Scopes are {', '.join(sorted(SCOPES))}, or '*' for all of them.",
                context={"scopes": invented},
            )

        expires_at = (
            datetime.now(UTC) + timedelta(days=int(ctx.args.expires_in_days))
            if ctx.args.expires_in_days
            else None
        )
        issued = ApiKeyIssuer().issue(environment=str(ctx.args.environment))
        database = Database.from_config(ctx.config)

        async def go() -> dict[str, Any]:
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    tenant = await _resolve_tenant(uow, _tenant_of(ctx))
                    wanted = str(ctx.args.principal).strip()
                    person = await uow.principals.by_username(tenant, wanted)
                    if person is None:
                        raise ValidationError(
                            f"there is no principal called {wanted!r} in this estate",
                            remedy=(
                                "Create one with `prama principal create <username> "
                                "--tenant <estate>`. A key belongs to somebody: the "
                                "schema requires it, and an audit trail naming only a "
                                "credential answers the wrong question."
                            ),
                            context={"principal": wanted, "tenant": tenant},
                        )
                    principal_id = str(person.id)
                    row = uow.api_keys.create(
                        tenant_id=tenant,
                        principal_id=principal_id,
                        name=str(ctx.args.name),
                        key_prefix=issued.prefix,
                        key_hash=issued.hash,
                        scopes=scopes,
                        expires_at=expires_at,
                    )
                    await uow.flush()
                    return {
                        "id": str(row.id),
                        "name": str(ctx.args.name),
                        "tenant": tenant,
                        "prefix": issued.prefix,
                        "scopes": scopes,
                        "expires_at": expires_at.isoformat() if expires_at else None,
                        "key": issued.plaintext,
                    }
            finally:
                await database.stop()

        record = asyncio.run(go())
        if ctx.json_output:
            ctx.emit_json(record)
        else:
            ctx.emit(f"issued {record['name']}")
            ctx.emit(f"  id:      {record['id']}")
            ctx.emit(f"  scopes:  {', '.join(record['scopes'])}")
            ctx.emit(f"  expires: {record['expires_at'] or 'never'}")
            ctx.emit("")
            ctx.emit(f"  {record['key']}")
            ctx.emit("")
            # Said plainly, because the alternative is somebody closing the
            # terminal and asking for it back.
            ctx.emit("  Shown once. Only the prefix and a hash are stored, so this")
            ctx.emit("  cannot be recovered — issue another key and revoke this one.")
            ctx.emit("")
            ctx.emit("  Use it as:  Authorization: Bearer <key>")
        return EXIT_OK


class ApiKeyListCommand(Command):
    name = "list"
    help = "the keys this estate holds, by prefix — never the key itself"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--tenant", default="", help="slug or id; defaults to the configured one"
        )

    def run(self, ctx: CommandContext) -> int:
        from prama.cli.principal import _resolve_tenant
        from prama.db import Database

        database = Database.from_config(ctx.config)

        async def go() -> list[dict[str, Any]]:
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    tenant = await _resolve_tenant(uow, _tenant_of(ctx))
                    return [
                        {
                            "id": str(k.id),
                            "name": k.name,
                            "prefix": k.key_prefix,
                            "scopes": list(k.scopes_json or ()),
                            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                            "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
                        }
                        for k in await uow.api_keys.list_for_tenant(tenant_id=tenant)
                    ]
            finally:
                await database.stop()

        rows = asyncio.run(go())
        if ctx.json_output:
            ctx.emit_json(rows)
        elif not rows:
            ctx.emit("No API keys in this estate.")
            ctx.emit("  Issue one: prama apikey create ci --principal alice --scope '*'")
        else:
            for row in rows:
                state = "revoked" if row["revoked_at"] else "active"
                ctx.emit(f"{row['prefix']}…  {row['name']}  [{state}]")
                ctx.emit(f"  scopes:  {', '.join(row['scopes']) or '(none)'}")
                ctx.emit(f"  expires: {row['expires_at'] or 'never'}")
        return EXIT_OK


class ApiKeyRevokeCommand(Command):
    name = "revoke"
    help = "stop a key working, without deleting the record that it existed"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("prefix", help="the key's prefix, as shown by `apikey list`")
        parser.add_argument(
            "--tenant", default="", help="slug or id; defaults to the configured one"
        )

    def run(self, ctx: CommandContext) -> int:
        from prama.cli.principal import _resolve_tenant
        from prama.core.clock import utc_now
        from prama.db import Database

        database = Database.from_config(ctx.config)

        async def go() -> str:
            await database.start()
            try:
                async with database.unit_of_work() as uow:
                    tenant = await _resolve_tenant(uow, _tenant_of(ctx))
                    key = await uow.api_keys.by_prefix(str(ctx.args.prefix))
                    if key is None or key.tenant_id != tenant:
                        raise ValidationError(
                            f"no key with prefix {ctx.args.prefix!r} in this estate",
                            remedy="List them with `prama apikey list`.",
                            context={"prefix": ctx.args.prefix},
                        )
                    if key.revoked_at is not None:
                        return "already revoked"
                    key.revoked_at = utc_now()
                    await uow.flush()
                    return "revoked"
            finally:
                await database.stop()

        outcome = asyncio.run(go())
        if ctx.json_output:
            ctx.emit_json({"prefix": ctx.args.prefix, "state": outcome})
        else:
            ctx.emit(f"{ctx.args.prefix}: {outcome}")
        return EXIT_OK


class ApiKeyCommand(CommandGroup):
    name = "apikey"
    help = "API keys: the credential the HTTP API requires"

    def commands(self) -> list[Command]:
        return [ApiKeyCreateCommand(), ApiKeyListCommand(), ApiKeyRevokeCommand()]


__all__ = ["ApiKeyCommand"]

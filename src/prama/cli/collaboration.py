"""``prama comment`` and ``prama queue`` — discussion on governed objects, and what waits on you.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext
from prama.cli.llm import _tenant_flag, _with_uow
from prama.core.errors import NotFoundError


async def _person(uow: Any, tenant: str, username: str) -> Any:
    person = await uow.principals.by_username(tenant, username)
    if person is None:
        raise NotFoundError(f"nobody is called {username}", remedy="Pass an existing username.")
    return person


class CommentCommand(Command):
    name = "comment"
    help = "comment on a dataset, dataset.attribute, control, term or incident"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("target", help="dataset slug, dataset.attribute, or an id/name")
        parser.add_argument("text", help="the comment; @username mentions somebody")
        parser.add_argument(
            "--kind",
            default="dataset",
            choices=["dataset", "attribute", "control", "term", "incident"],
        )
        parser.add_argument("--as", dest="author", required=True, help="your username")
        parser.add_argument("--reply-to", default="", help="a thread's id")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.semantic.services.collaboration import post

        async def work(uow: Any, tenant: str) -> str:
            person = await _person(uow, tenant, ctx.args.author)
            row = await post(
                uow,
                tenant,
                object_kind=ctx.args.kind,
                object_ref=ctx.args.target,
                body=ctx.args.text,
                by=str(person.id),
                parent_id=ctx.args.reply_to or None,
            )
            return str(row.id)

        ctx.emit(f"posted {_with_uow(ctx, work)}")
        return EXIT_OK


class QueueCommand(Command):
    name = "queue"
    help = "what is waiting on a person: mentions, failures, inconsistencies, approvals"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--as", dest="person", required=True, help="the username")
        parser.add_argument("--approver", action="store_true", help="include approvals")
        _tenant_flag(parser)

    def run(self, ctx: CommandContext) -> int:
        from prama.semantic.services.collaboration import queue

        async def work(uow: Any, tenant: str) -> dict[str, Any]:
            person = await _person(uow, tenant, ctx.args.person)
            return await queue(uow, tenant, str(person.id), approver=ctx.args.approver)

        q = _with_uow(ctx, work)
        if ctx.json_output:
            ctx.emit_json(q)
            return EXIT_OK
        ctx.emit(f"{q['total']} item(s); datasets: {', '.join(q['datasets']) or 'none'}")
        for key in ("mentions", "threads", "failing", "inconsistent", "suggestions", "approvals"):
            for item in q[key]:
                ctx.emit(f"  {key:<12} {item}")
        return EXIT_OK

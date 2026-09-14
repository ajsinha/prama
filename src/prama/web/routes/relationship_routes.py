"""Relationships: declaring one, and confirming or rejecting a proposal.

The most valuable declarations in the product and the ones that most need a
human, which is why a discovered relationship stays a proposal — and every
control derived from it stays a proposal too — until somebody says yes.

Two ways in, both first-class. On the estate map you pick two datasets and the
form opens with them filled in. From the keyboard you pick them from two
selects. The map is the better story and the selects are the better tool for
finding one dataset among two thousand, so neither is the fallback for the
other.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.errors import PramaError
from prama.semantic.relationships import (
    Cardinality,
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
    Tolerance,
)
from prama.semantic.services import RelationshipService
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes
from prama.web.viewmodels import RelationshipEdge


def kind_options() -> list[dict[str, Any]]:
    """Every kind, with the question it answers and what it generates.

    Derived from ``RelationshipKind`` rather than written out here. The prompt
    — "these two should agree" — is the sentence a business owner recognises,
    and the list of generated controls is what makes the choice worth care: it
    is the difference between drawing a line on a diagram and turning on a
    reconciliation.
    """
    return [
        {
            "value": kind.value,
            "prompt": kind.prompt,
            "generates": list(kind.generates),
            "requires_match_keys": kind.requires_match_keys,
            "requires_tolerance": kind.requires_tolerance,
            # Only a reconciliation names a value to compare, and the
            # declaration is the authority on that — asked here rather than
            # left for the form to be refused after it is filled in.
            "requires_compare": kind is RelationshipKind.RECONCILES_WITH,
            "is_directional": kind.is_directional,
        }
        for kind in RelationshipKind
    ]


class RelationshipRoutes(UiRoutes):
    SUBJECT = "relationship"
    """Declaring, confirming and rejecting."""

    def register(self) -> None:
        self.page("/relationships", self.relationship_list, name="relationship_list")
        self.page("/relationships/new", self.relationship_form, name="relationship_form")
        self.page(
            "/relationships/new",
            self.relationship_create,
            name="relationship_create",
            methods=["POST"],
        )
        self.page(
            "/relationships/{relationship_id}/confirm",
            self.relationship_confirm,
            name="relationship_confirm",
            methods=["POST"],
        )
        self.page(
            "/relationships/{relationship_id}/reject",
            self.relationship_reject,
            name="relationship_reject",
            methods=["POST"],
        )

    async def _names(self, caller: Caller, uow: Uow) -> dict[str, str]:
        return {
            v.dataset_id: v.name
            for v in await uow.datasets.list_current(caller.tenant_id, limit=5000)
        }

    async def relationship_list(self, request: Request, caller: Caller, uow: Uow) -> Any:
        names = await self._names(caller, uow)
        edges = [
            RelationshipEdge.of(v)
            for v in await uow.relationships.list_current(caller.tenant_id, limit=20000)
        ]
        # Proposals first. They are the ones that need a decision, and a list
        # sorted by anything else buries them under relationships nobody has to
        # look at again.
        edges.sort(key=lambda e: (not e.is_proposed, e.kind))
        return render(
            request,
            "relationships/list.html",
            edges=edges,
            names=names,
            proposed=sum(1 for e in edges if e.status == "proposed"),
        )

    async def relationship_form(
        self,
        request: Request,
        caller: Caller,
        uow: Uow,
        source: str = "",
        target: str = "",
    ) -> Any:
        return render(
            request,
            "relationships/form.html",
            datasets=sorted(
                (
                    {"id": v.dataset_id, "name": v.name, "slug": v.slug}
                    for v in await uow.datasets.list_current(caller.tenant_id, limit=5000)
                ),
                key=lambda d: str(d["name"]).lower(),
            ),
            kinds=kind_options(),
            submitted={"from_dataset_id": source, "to_dataset_id": target},
        )

    async def relationship_create(
        self,
        request: Request,
        caller: Caller,
        uow: Uow,
        kind: Annotated[str, Form()],
        from_dataset_id: Annotated[str, Form()],
        to_dataset_id: Annotated[str, Form()],
        match_keys: Annotated[str, Form()] = "",
        description: Annotated[str, Form()] = "",
        cardinality: Annotated[str, Form()] = "many_to_many",
        tolerance_absolute: Annotated[str, Form()] = "",
        tolerance_currency: Annotated[str, Form()] = "",
        tolerance_relative_percent: Annotated[str, Form()] = "",
        compare: Annotated[str, Form()] = "",
    ) -> Any:
        """Record a relationship a human asserts to be true."""
        try:
            declaration = RelationshipDeclaration(
                kind=RelationshipKind(kind),
                from_dataset_id=from_dataset_id,
                to_dataset_id=to_dataset_id,
                match_keys=_parse_match_keys(match_keys),
                cardinality=Cardinality(cardinality),
                compare=tuple(part.strip() for part in compare.split(",") if part.strip()),
                tolerance=_parse_tolerance(
                    tolerance_absolute, tolerance_currency, tolerance_relative_percent
                ),
                description=description,
            )
            _, version = await RelationshipService(uow).declare(
                tenant_id=caller.tenant_id,
                declaration=declaration,
                authored_by=caller.principal_id,
                approved_by=caller.principal_id,
                confirmed=True,
            )
        except (PramaError, ValueError) as exc:
            flash_error_and_log(request, "That relationship could not be recorded", exc)
            return await self._reshow(
                request,
                caller,
                uow,
                {
                    "kind": kind,
                    "from_dataset_id": from_dataset_id,
                    "to_dataset_id": to_dataset_id,
                    "match_keys": match_keys,
                    "description": description,
                    "cardinality": cardinality,
                    "tolerance_absolute": tolerance_absolute,
                    "tolerance_currency": tolerance_currency,
                    "tolerance_relative_percent": tolerance_relative_percent,
                    "compare": compare,
                },
            )
        return redirect_to(
            request,
            "relationship_list",
            flash_message=f"Declared: {version.name}.",
        )

    async def _reshow(
        self, request: Request, caller: Caller, uow: Uow, submitted: dict[str, Any]
    ) -> Any:
        return render(
            request,
            "relationships/form.html",
            status_code=422,
            datasets=sorted(
                (
                    {"id": v.dataset_id, "name": v.name, "slug": v.slug}
                    for v in await uow.datasets.list_current(caller.tenant_id, limit=5000)
                ),
                key=lambda d: str(d["name"]).lower(),
            ),
            kinds=kind_options(),
            submitted=submitted,
        )

    async def relationship_confirm(
        self, request: Request, relationship_id: str, caller: Caller, uow: Uow
    ) -> Any:
        await RelationshipService(uow).confirm(
            tenant_id=caller.tenant_id,
            relationship_id=relationship_id,
            confirmed_by=caller.principal_id or "console",
        )
        return redirect_to(
            request,
            "relationship_list",
            flash_message=("Confirmed. Controls derived from it are no longer held as proposals."),
        )

    async def relationship_reject(
        self,
        request: Request,
        relationship_id: str,
        caller: Caller,
        uow: Uow,
        reason: Annotated[str, Form()] = "",
    ) -> Any:
        """Rejections are recorded, not deleted.

        A rejection is a training signal, and re-proposing something a steward
        has already turned down is the fastest way to lose their attention.
        """
        await RelationshipService(uow).reject(
            tenant_id=caller.tenant_id,
            relationship_id=relationship_id,
            rejected_by=caller.principal_id or "console",
            reason=reason or "rejected in the console",
        )
        return redirect_to(
            request,
            "relationship_list",
            flash_message="Rejected, and recorded as rejected so it is not proposed again.",
            flash_category="info",
        )


def _parse_tolerance(absolute: str, currency: str, relative_percent: str) -> Tolerance | None:
    """Read the materiality the form asked for, in the units it asked in.

    Percent on the form, fraction in the model. Asking a reconciliation analyst
    to type 0.001 for a tenth of a percent is how a tolerance ends up a
    thousand times wider than intended, and nothing about the resulting run
    looks wrong.
    """
    # `Decimal` straight from the typed text, not via `float`. What the analyst
    # wrote is what the materiality means, and `float("0.1") / 100` is not
    # exactly one tenth of a percent. QA round 4, `Q-78`.
    absolute_value = Decimal(absolute.strip()) if absolute.strip() else None
    relative_value = Decimal(relative_percent.strip()) / 100 if relative_percent.strip() else None
    if absolute_value is None and relative_value is None:
        # Not an error here: only some kinds need one, and the declaration
        # itself refuses — with the right message — when this kind does.
        return None
    return Tolerance(
        absolute=absolute_value,
        relative=relative_value,
        currency=currency.strip().upper() or None,
    )


def _parse_match_keys(text: str) -> tuple[MatchKey, ...]:
    """Read ``account_id = acct_id, trade_date`` as match keys.

    Two forms because both are how people write them: ``left = right`` when the
    columns are named differently, and a bare name when they are the same. The
    second is the common case and requiring the redundant ``x = x`` for it is
    how a form stops being used.
    """
    keys = []
    for part in text.split(","):
        piece = part.strip()
        if not piece:
            continue
        if "=" in piece:
            left, right = (side.strip() for side in piece.split("=", 1))
            keys.append(MatchKey(left=left, right=right or None))
        else:
            keys.append(MatchKey(left=piece))
    return tuple(keys)

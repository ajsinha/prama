"""Declarations: the list, and the form that adds one.

This is the screen the product is for. Everything downstream — controls,
incidents, scores — is derived from what a business owner types here, which is
why the form is organised around questions ("what is one row?") rather than
around columns ("grain_json").

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.errors import PramaError
from prama.semantic.policy import ApprovalPolicy
from prama.semantic.services import DatasetService
from prama.semantic.values import Grain
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes
from prama.web.viewmodels import DatasetCard

#: Offered in the form. The set is the schema's CHECK constraint, and it is
#: read from nowhere else — a second list here would drift, and the drift would
#: surface as a constraint violation on save rather than as a missing option.
SHAPES = (
    "unbound",
    "table",
    "table_set",
    "schema",
    "feed",
    "feed_set",
    "stream",
    "api",
    "report",
    "query",
)


class DeclarationRoutes(UiRoutes):
    """Listing, filtering and creating dataset declarations."""

    def register(self) -> None:
        self.page("/declarations", self.declaration_list, name="declaration_list")
        self.page("/declarations/new", self.declaration_form, name="declaration_form")
        self.page(
            "/declarations/new",
            self.declaration_create,
            name="declaration_create",
            methods=["POST"],
        )

    async def declaration_list(
        self,
        request: Request,
        caller: Caller,
        uow: Uow,
        incomplete: bool = False,
        tier: int | None = None,
    ) -> Any:
        """Every declaration, with what each one still cannot produce.

        Sorted by criticality first. A list sorted by name puts a Tier 4
        reference table above a broken regulatory return, which is a defensible
        default for a file browser and an indefensible one here.
        """
        cards = [
            DatasetCard.of(v) for v in await uow.datasets.list_current(caller.tenant_id, limit=5000)
        ]
        if incomplete:
            cards = [c for c in cards if not c.is_complete]
        if tier is not None:
            cards = [c for c in cards if c.criticality == tier]
        cards.sort(key=lambda c: (c.criticality, c.name.lower()))
        return render(
            request,
            "declarations/list.html",
            datasets=cards,
            incomplete=incomplete,
            tier=tier,
            total_incomplete=sum(1 for c in cards if not c.is_complete),
        )

    def _tiers(self) -> list[dict[str, Any]]:
        """The tier options, each carrying the approval its own policy demands.

        Derived from ``ApprovalPolicy``, not restated in the template. A
        hard-coded "Tier 1 needs approval" would go stale the moment the policy
        is configured differently, and it would go stale in the flattering
        direction — telling the user no approval is needed when one is.
        """
        policy = ApprovalPolicy()
        labels = {
            1: "Tier 1 — regulatory; a defect is reportable",
            2: "Tier 2 — material to a business decision",
            3: "Tier 3 — operational",
            4: "Tier 4 — informational",
        }
        out = []
        for tier, label in labels.items():
            requirement = policy.for_criticality(tier)
            out.append(
                {
                    "value": tier,
                    "label": label,
                    "needs_approver": requirement.needs_approver,
                    "needs_second_person": requirement.needs_second_person,
                }
            )
        return out

    async def declaration_form(self, request: Request) -> Any:
        return render(request, "declarations/form.html", shapes=SHAPES, tiers=self._tiers())

    async def declaration_create(
        self,
        request: Request,
        caller: Caller,
        uow: Uow,
        name: Annotated[str, Form()],
        description: Annotated[str, Form()] = "",
        purpose: Annotated[str, Form()] = "",
        shape: Annotated[str, Form()] = "unbound",
        criticality: Annotated[int, Form()] = 4,
        grain: Annotated[str, Form()] = "",
        grain_statement: Annotated[str, Form()] = "",
    ) -> Any:
        """Record a declaration, or say exactly why it could not be recorded.

        The failure path re-renders the form with what was typed still in it.
        A validation error that empties the form teaches the user to distrust
        the form, and they start drafting in a text editor.
        """
        grain_attributes = [part.strip() for part in grain.split(",") if part.strip()]
        try:
            _, version = await DatasetService(uow).declare(
                tenant_id=caller.tenant_id,
                name=name,
                description=description,
                purpose=purpose,
                shape=shape,
                criticality=criticality,
                # The sentence is kept verbatim alongside the attribute list,
                # because it is what appears in the generated control's BECAUSE
                # clause and in the attestation. Reconstructing prose from a
                # list of column names produces a sentence nobody wrote and
                # nobody will stand behind.
                grain=(
                    Grain(attributes=tuple(grain_attributes), statement=grain_statement.strip())
                    if grain_attributes
                    else None
                ),
                authored_by=caller.principal_id,
            )
        except PramaError as exc:
            flash_error_and_log(request, "That declaration could not be recorded", exc)
            return render(
                request,
                "declarations/form.html",
                shapes=SHAPES,
                tiers=self._tiers(),
                status_code=422,
                submitted={
                    "name": name,
                    "description": description,
                    "purpose": purpose,
                    "shape": shape,
                    "criticality": criticality,
                    "grain": grain,
                    "grain_statement": grain_statement,
                },
            )
        return redirect_to(
            request,
            "dataset_detail",
            dataset_id=version.dataset_id,
            flash_message=f"{name} declared.",
        )

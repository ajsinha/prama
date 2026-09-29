"""Metadata pages: templates, search, and each dataset's context, metadata and rules.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.errors import PramaError, ValidationError
from prama.semantic.metadata import STARTER
from prama.semantic.services import metadata as service
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes

READ, WRITE = "declaration:read", "declaration:write"


class MetadataRoutes(UiRoutes):
    SUBJECT = "declaration"

    def register(self) -> None:
        post = ["POST"]
        self.page("/metadata", self.index, name="metadata", scope=READ)
        self.page(
            "/metadata/templates",
            self.template,
            name="metadata_template",
            methods=post,
            scope=WRITE,
        )
        self.page("/metadata/d/{slug}", self.dataset, name="metadata_dataset", scope=READ)
        self.page(
            "/metadata/d/{slug}/context",
            self.context,
            name="metadata_context",
            methods=post,
            scope=WRITE,
        )
        self.page(
            "/metadata/d/{slug}/values",
            self.values,
            name="metadata_values",
            methods=post,
            scope=WRITE,
        )
        self.page(
            "/metadata/d/{slug}/rule",
            self.rule,
            name="metadata_rule",
            methods=post,
            scope="control:propose",
        )

    async def index(self, request: Request, uow: Uow, caller: Caller, q: str = "") -> Any:
        templates = []
        for row in await uow.metadata.templates(caller.tenant_id):
            fields = await uow.metadata.fields(row.id)
            templates.append({"row": row, "fields": fields})
        return render(
            request,
            "metadata/index.html",
            q=q,
            hits=await _find(request, uow, caller, q) if q.strip() else {},
            templates=templates,
            starters=sorted(STARTER),
            datasets=await uow.datasets.list_current(caller.tenant_id, limit=5000),
            correlation=await service.correlation(uow, caller.tenant_id),
            priorities=await _priorities(uow, caller.tenant_id),
        )

    async def template(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        starter: Annotated[str, Form()] = "",
        yaml_text: Annotated[str, Form()] = "",
    ) -> Any:
        try:
            if starter:
                result = await service.install_starter(uow, caller.tenant_id, starter)
            else:
                import yaml

                document = yaml.safe_load(yaml_text or "")
                if not isinstance(document, dict):
                    raise ValidationError(
                        "the template is not a YAML mapping",
                        remedy="Start with name:, applies_to: and fields:.",
                    )
                result = await service.save_template(uow, caller.tenant_id, document)
        except (PramaError, Exception) as exc:
            if not isinstance(exc, PramaError):
                exc = ValidationError(
                    f"the template could not be read: {exc}", remedy="Check the YAML."
                )
            flash_error_and_log(request, "That template was not saved", exc)
            return redirect_to(request, "metadata")
        return redirect_to(
            request,
            "metadata",
            flash_message=f"{result['template']}: {result['added']} field(s) added, "
            f"{result['changed']} changed.",
        )

    async def dataset(self, request: Request, uow: Uow, caller: Caller, slug: str) -> Any:
        described = await service.describe(uow, caller.tenant_id, slug)
        fields = {}
        for kind in ("dataset", "attribute"):
            fields[kind] = [
                row
                for template in await uow.metadata.templates(caller.tenant_id, applies_to=kind)
                for row in await uow.metadata.fields(template.id)
            ]
        from prama.semantic.services.collaboration import threads

        conversation = await threads(uow, caller.tenant_id, "dataset", described["slug"])
        for attribute in described["attributes"]:
            conversation += await threads(
                uow, caller.tenant_id, "attribute", f"{described['slug']}.{attribute['name']}"
            )
        return render(
            request, "metadata/dataset.html", d=described, fields=fields, conversation=conversation
        )

    async def context(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        slug: str,
        target: Annotated[str, Form()] = "",
        text: Annotated[str, Form()] = "",
    ) -> Any:
        try:
            await service.set_context(
                uow, caller.tenant_id, target or slug, text, by=caller.principal_id or None
            )
        except PramaError as exc:
            flash_error_and_log(request, "The business context was not saved", exc)
        return redirect_to(request, "metadata_dataset", slug=slug)

    async def values(self, request: Request, uow: Uow, caller: Caller, slug: str) -> Any:
        form = await request.form()
        target = str(form.get("target") or slug)
        values = {key[6:]: str(value) for key, value in form.items() if key.startswith("field_")}
        try:
            changed = await service.set_values(
                uow, caller.tenant_id, target, values, by=caller.principal_id or None
            )
        except PramaError as exc:
            flash_error_and_log(request, "The metadata was not saved", exc)
            return redirect_to(request, "metadata_dataset", slug=slug)
        return redirect_to(
            request,
            "metadata_dataset",
            slug=slug,
            flash_message=f"Saved: {', '.join(changed) or 'nothing changed'}.",
        )

    async def rule(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        slug: str,
        pql: Annotated[str, Form()] = "",
    ) -> Any:
        """A rule written by hand: proposed, and active once somebody else approves it."""
        try:
            await service.author_rule(uow, caller.tenant_id, slug, pql, by=caller.principal_id)
        except PramaError as exc:
            flash_error_and_log(request, "That rule was not recorded", exc)
            return redirect_to(request, "metadata_dataset", slug=slug)
        return redirect_to(
            request,
            "metadata_dataset",
            slug=slug,
            flash_message="Rule proposed; another person approves it on Controls.",
        )


async def _find(request: Request, uow: Any, caller: Any, q: str) -> dict[str, Any]:
    from prama.semantic.services.finding import find_data

    return await find_data(
        uow,
        caller.tenant_id,
        q,
        config=request.app.state.config,
        principal_id=caller.principal_id or None,
    )


async def _priorities(uow: Any, tenant_id: str) -> dict[str, Any]:
    from prama.semantic.services.priorities import priorities

    return await priorities(uow, tenant_id)

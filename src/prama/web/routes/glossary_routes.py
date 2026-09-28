"""The Glossary page: business terms, what they name, and binding them.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.errors import PramaError, ValidationError
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes


class GlossaryRoutes(UiRoutes):
    SUBJECT = "declaration"

    def register(self) -> None:
        self.page("/glossary", self.index, name="glossary", scope="declaration:read")
        self.page(
            "/glossary/bind",
            self.bind,
            name="glossary_bind",
            methods=["POST"],
            scope="declaration:write",
        )

    async def index(self, request: Request, uow: Uow, caller: Caller, q: str = "") -> Any:
        terms = (
            await uow.glossary.search(caller.tenant_id, q)
            if q.strip()
            else await uow.glossary.terms(caller.tenant_id)
        )
        concepts = {
            str(c.concept_id): c.name
            for c in await uow.concepts.list_current(caller.tenant_id, limit=5000)
        }
        rows = []
        for term in terms:
            bindings = await uow.glossary.bindings(caller.tenant_id, term_id=term.id)
            rows.append(
                {
                    "term": term,
                    "synonyms": json.loads(term.synonyms_json),
                    "bound": [
                        (b.object_kind, concepts.get(b.object_ref, b.object_ref), b.how)
                        for b in bindings
                    ],
                }
            )
        return render(request, "glossary/index.html", rows=rows, q=q)

    async def bind(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        term: Annotated[str, Form()] = "",
        kind: Annotated[str, Form()] = "",
        ref: Annotated[str, Form()] = "",
    ) -> Any:
        try:
            if kind not in ("concept", "dataset", "attribute") or not ref.strip():
                raise ValidationError("choose what to bind to", remedy="Pick a kind and name it.")
            target = ref.strip()
            if kind == "concept":
                concept = await uow.concepts.by_name(caller.tenant_id, target)
                if concept is None:
                    raise ValidationError(f"no concept {target!r}", remedy="Declare it first.")
                target = str(concept.concept_id)
            await uow.glossary.bind(
                caller.tenant_id, term, kind, target, by=caller.principal_id or None
            )
        except PramaError as exc:
            flash_error_and_log(request, "That binding was not made", exc)
            return redirect_to(request, "glossary")
        return redirect_to(request, "glossary", flash_message=f"{term} bound to {kind} {ref}.")

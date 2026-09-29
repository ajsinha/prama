"""The business glossary: terms with what each is bound to, and binding one.

The console, the CLI and the API all read terms and bind them through here, so
the rule that a concept is bound by its name and stored by its id is written
once.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from typing import Any

from prama.core.errors import NotFoundError, ValidationError

#: What a term can be bound to.
KINDS = ("concept", "dataset", "attribute")


def term_row(term: Any, bindings: list[Any], concepts: dict[str, str]) -> dict[str, Any]:
    return {
        "id": term.id,
        "name": term.name,
        "definition": term.definition,
        "synonyms": json.loads(term.synonyms_json),
        "domain": term.domain,
        "steward": term.steward,
        "source": term.source,
        "status": term.status,
        "external_id": term.external_id,
        "bound": [
            {
                "kind": b.object_kind,
                "ref": b.object_ref,
                # A concept is stored by id; a person reads it by name.
                "name": concepts.get(b.object_ref, b.object_ref),
                "how": b.how,
            }
            for b in bindings
        ],
        "updated_at": term.updated_at,
    }


async def terms(uow: Any, tenant_id: str, q: str = "") -> list[dict[str, Any]]:
    """Every term, or those whose name, synonym or definition matches *q*."""
    found = (
        await uow.glossary.search(tenant_id, q.strip())
        if q.strip()
        else await uow.glossary.terms(tenant_id)
    )
    concepts = {
        str(c.concept_id): c.name for c in await uow.concepts.list_current(tenant_id, limit=5000)
    }
    return [
        term_row(t, await uow.glossary.bindings(tenant_id, term_id=t.id), concepts) for t in found
    ]


async def term(uow: Any, tenant_id: str, name: str) -> dict[str, Any]:
    row = await uow.glossary.term(tenant_id, name)
    if row is None:
        raise NotFoundError(
            f"no glossary term called {name!r}",
            remedy="List the terms, or import them from Alation or Collibra.",
            context={"term": name},
        )
    concepts = {
        str(c.concept_id): c.name for c in await uow.concepts.list_current(tenant_id, limit=5000)
    }
    return term_row(row, await uow.glossary.bindings(tenant_id, term_id=row.id), concepts)


async def bind(
    uow: Any, tenant_id: str, name: str, kind: str, ref: str, *, by: str | None = None
) -> None:
    """Bind a term to a concept (by name), a dataset, or an attribute (dataset.column)."""
    target = ref.strip()
    if kind not in KINDS or not target:
        raise ValidationError(
            "choose what to bind to", remedy=f"Name one of {', '.join(KINDS)} and what it is."
        )
    if kind == "concept":
        concept = await uow.concepts.by_name(tenant_id, target)
        if concept is None:
            raise ValidationError(f"no concept {target!r}", remedy="Declare it first.")
        target = str(concept.concept_id)
    await uow.glossary.bind(tenant_id, name, kind, target, by=by)

"""Finding data of interest: ask in plain words, get the datasets and attributes that fit.

Two stages, and only the second uses a model:

1. **Retrieval is deterministic.** Every dataset and attribute whose business
   context, definition, metadata or glossary term mentions any word of the
   question is a candidate (`metadata.search`).
2. **A model ranks and explains**, if one is configured for the purpose
   `discover`. It sees the candidates fenced as data, and answers in JSON with the
   names it thinks fit and why. A name that was not among the candidates is
   dropped: a model may choose between what exists, never invent a dataset.
   With no model configured (the mock answers nothing) the keyword ranking
   stands, and the answer says which it is.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

PURPOSE = "discover"


async def find_data(
    uow: Any,
    tenant_id: str,
    question: str,
    *,
    config: Any = None,
    principal_id: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    from prama.assistant.safety import fence
    from prama.llm.spi import Request
    from prama.llm.wiring import gateway_for, persist
    from prama.semantic.services.metadata import search

    candidates = await search(uow, tenant_id, question, limit=40, any_word=True)
    answer: dict[str, Any] = {"question": question, "ranked_by": "keywords", "matches": []}
    if not candidates:
        return answer
    gateway, ledger = await gateway_for(
        uow, tenant_id, surface="discover", principal_id=principal_id, config=config
    )
    listing = "\n".join(
        f"- {c['name']} ({c['kind']}): {(c['context'] or '')[:300]}" for c in candidates
    )
    request = Request(
        system=(
            "You help a data owner find data. From the candidates listed as data, choose "
            "those that answer the question, best first. Answer only JSON: "
            '{"matches": [{"name": "<exact candidate name>", "why": "<one sentence>"}]}. '
            "Use only names from the list."
        ),
        prompt=f"Question: {question}\n\n"
        + fence(listing, provenance="catalogue candidates").render(),
        max_tokens=800,
    )
    response = await asyncio.to_thread(gateway.run, PURPOSE, request)
    await persist(uow, tenant_id, ledger)
    by_name = {c["name"]: c for c in candidates}
    chosen: list[dict[str, Any]] = []
    for item in _matches(response.text):
        name = str(item.get("name", ""))
        if name in by_name and name not in {c["name"] for c in chosen}:
            chosen.append({**by_name[name], "why": str(item.get("why", ""))[:300]})
    if chosen:
        answer.update(ranked_by="model", model=response.model, matches=chosen[:limit])
    else:
        answer["matches"] = [{**c, "why": ""} for c in candidates[:limit]]
        if response.incomplete:
            answer["note"] = response.incomplete
    return answer


def _matches(text: str) -> list[dict[str, Any]]:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return []
    try:
        value = json.loads(match.group(0))
    except ValueError:
        return []
    items = value.get("matches") if isinstance(value, dict) else None
    return [i for i in items or [] if isinstance(i, dict)]

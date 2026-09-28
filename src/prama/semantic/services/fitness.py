"""Which dataset is fit for a purpose: semantic search across the estate's datasets.

Each dataset is represented by its **profile**: its name, description, purpose,
business context, metadata values, glossary terms, and each attribute's name,
definition and business context. The profile is what the owners have said the
dataset means, so the better they describe it, the better this works.

Ranking, and the answer always says which was used:

* **Embeddings**, when a model is configured for the purpose `embed`. Profiles
  are embedded once and re-embedded only when their text changes; the question
  is embedded and datasets are ranked by cosine similarity. Meaning matches
  even without shared words ("exposure" finds "amount at risk").
* **Relevance (BM25)** otherwise: a deterministic ranking over the same
  profiles, which needs shared words but no model.

Each result carries evidence: the attributes whose own text best matches the
question, so the reader can see *why* a dataset ranked. Nothing here reads or
queries the data itself, and nothing here touches a score.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from typing import Any

PURPOSE = "embed"
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "which",
        "with",
        "what",
        "where",
        "who",
        "whose",
        "data",
        "dataset",
        "datasets",
        "need",
    }
)


def _stem(word: str) -> str:
    """Light stemming, so "trade" finds "trades" and "rates" finds "rate"."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("sses", "xes", "ches", "shes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _words(text: str) -> list[str]:
    return [_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP]


async def profiles(uow: Any, tenant_id: str) -> list[dict[str, Any]]:
    """Every current dataset, with the text that describes it and its attributes."""
    values: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for template in await uow.metadata.templates(tenant_id):
        for field in await uow.metadata.fields(template.id):
            names[field.id] = field.name
    for value in await uow.metadata.current_values(tenant_id):
        if value.field_id in names:
            values.setdefault(value.object_ref, []).append(
                f"{names[value.field_id]}: {json.loads(value.value_json)}"
            )
    terms: dict[str, list[str]] = {}
    term_names = {t.id: t for t in await uow.glossary.terms(tenant_id)}
    for binding in await uow.glossary.bindings(tenant_id):
        term = term_names.get(binding.term_id)
        if term is not None:
            terms.setdefault(binding.object_ref, []).append(f"{term.name} {term.definition}")
    out = []
    for version in await uow.datasets.list_current(tenant_id, limit=5000):
        attributes = []
        for a in await uow.attributes.for_dataset(version.dataset_id, tenant_id=tenant_id):
            text = " ".join(
                [
                    a.name.replace("_", " "),
                    a.definition,
                    a.business_context,
                    *values.get(a.attribute_id, []),
                    *terms.get(f"{version.slug}.{a.name}", []),
                ]
            )
            attributes.append({"name": a.name, "text": text})
        text = "\n".join(
            [
                version.name,
                version.description,
                version.purpose,
                version.business_context,
                *values.get(version.dataset_id, []),
                *terms.get(version.slug, []),
                *(a["text"] for a in attributes),
            ]
        )
        out.append(
            {
                "dataset_id": version.dataset_id,
                "name": version.name,
                "slug": version.slug,
                "context": version.business_context or version.description,
                "text": text,
                "attributes": attributes,
            }
        )
    return out


def bm25(question: str, documents: list[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Okapi BM25 scores of *documents* for *question*."""
    query = _words(question)
    docs = [_words(d) for d in documents]
    if not query or not docs:
        return [0.0] * len(documents)
    average = sum(len(d) for d in docs) / len(docs) or 1.0
    frequency: dict[str, int] = {}
    for words in docs:
        for word in set(words):
            frequency[word] = frequency.get(word, 0) + 1
    scores = []
    for words in docs:
        counts: dict[str, int] = {}
        for word in words:
            counts[word] = counts.get(word, 0) + 1
        score = 0.0
        for term in query:
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (len(docs) - frequency[term] + 0.5) / (frequency[term] + 0.5))
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(words) / average))
        scores.append(score)
    return scores


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


async def rank(
    uow: Any,
    tenant_id: str,
    question: str,
    *,
    config: Any = None,
    principal_id: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Datasets ranked by fitness for *question*, with evidence for each."""
    from prama.llm.wiring import gateway_for, persist

    documents = await profiles(uow, tenant_id)
    answer: dict[str, Any] = {"question": question, "ranked_by": "relevance", "matches": []}
    if not documents or not question.strip():
        return answer
    gateway, ledger = await gateway_for(
        uow, tenant_id, surface="search", principal_id=principal_id, config=config
    )
    scores: list[float] | None = None
    stored_model = ""
    stored: dict[str, tuple[str, list[float]]] = {}
    # One probe tells us whether an embedding model is configured at all.
    probe = await asyncio.to_thread(gateway.embed, PURPOSE, [question])
    if probe is not None:
        (question_vector,), stored_model = probe
        stored = await uow.semantic_index.vectors(tenant_id, stored_model)
        stale = [d for d in documents if stored.get(d["dataset_id"], ("",))[0] != _hash(d["text"])]
        if stale:
            made = await asyncio.to_thread(gateway.embed, PURPOSE, [d["text"] for d in stale])
            if made is not None:
                for document, vector in zip(stale, made[0], strict=True):
                    await uow.semantic_index.store(
                        tenant_id,
                        document["dataset_id"],
                        stored_model,
                        _hash(document["text"]),
                        vector,
                    )
                    stored[document["dataset_id"]] = (_hash(document["text"]), vector)
        if all(d["dataset_id"] in stored for d in documents):
            scores = [_cosine(question_vector, stored[d["dataset_id"]][1]) for d in documents]
            answer.update(ranked_by="embeddings", model=stored_model)
    await persist(uow, tenant_id, ledger)
    if scores is None:
        scores = bm25(question, [d["text"] for d in documents])
    ranked = sorted(zip(scores, documents, strict=True), key=lambda p: -p[0])
    for score, document in ranked[:limit]:
        if answer["ranked_by"] == "relevance" and score <= 0:
            break
        evidence_scores = bm25(question, [a["text"] for a in document["attributes"]])
        evidence = [
            a["name"]
            for s, a in sorted(
                zip(evidence_scores, document["attributes"], strict=True), key=lambda p: -p[0]
            )
            if s > 0
        ][:3]
        answer["matches"].append(
            {
                "kind": "dataset",
                "name": document["name"],
                "slug": document["slug"],
                "context": document["context"],
                "score": round(score, 4),
                "evidence": evidence,
                "why": "",
            }
        )
    return answer


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

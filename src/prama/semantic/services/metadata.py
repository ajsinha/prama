"""Metadata on datasets and attributes: set it, read it, and let rules grow from it.

The one place the console, the CLI and the API go through, so a value is
checked against its field's kind the same way whichever door it came in by.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from prama.core.errors import NotFoundError, PramaError, ValidationError
from prama.semantic.metadata import STARTER, FieldSpec, Rule, coerce, parse_template, render


def field_spec(row: Any) -> FieldSpec:
    return FieldSpec(
        name=row.name,
        kind=row.kind,
        label=row.label,
        choices=tuple(json.loads(row.choices_json)),
        required=bool(row.required),
        help=row.help,
        rules=tuple(Rule(**r) for r in json.loads(row.rules_json)),
    )


async def save_template(uow: Any, tenant_id: str, document: Mapping[str, Any]) -> dict[str, Any]:
    spec = parse_template(document)
    row, added, changed = await uow.metadata.save_template(tenant_id, spec)
    return {"template": row.name, "applies_to": row.applies_to, "added": added, "changed": changed}


async def install_starter(uow: Any, tenant_id: str, name: str) -> dict[str, Any]:
    if name not in STARTER:
        raise NotFoundError(
            f"no starter template {name!r}", remedy=f"Starters: {', '.join(sorted(STARTER))}."
        )
    return await save_template(uow, tenant_id, STARTER[name])


async def _fields(uow: Any, tenant_id: str, applies_to: str) -> dict[str, tuple[Any, Any]]:
    """Field name -> (template row, field row), across the active templates."""
    out: dict[str, tuple[Any, Any]] = {}
    for template in await uow.metadata.templates(tenant_id, applies_to=applies_to):
        for field in await uow.metadata.fields(template.id):
            out.setdefault(field.name, (template, field))
    return out


async def resolve(uow: Any, tenant_id: str, target: str) -> tuple[Any, Any | None]:
    """`dataset` or `dataset.attribute` (by slug or name) -> (dataset version, attribute)."""
    datasets = await uow.datasets.list_current(tenant_id, limit=5000)
    for version in sorted(datasets, key=lambda v: -len(v.slug)):
        for label in (version.slug, version.name):
            if target == label:
                return version, None
            if target.startswith(label + "."):
                name = target[len(label) + 1 :]
                for attribute in await uow.attributes.for_dataset(
                    version.dataset_id, tenant_id=tenant_id
                ):
                    if attribute.name == name:
                        return version, attribute
                raise NotFoundError(
                    f"{version.name} has no attribute {name!r}",
                    remedy="Declare the attribute first, or check its name.",
                )
    raise NotFoundError(f"no dataset {target!r}", remedy="Name a declared dataset (its slug).")


async def set_values(
    uow: Any, tenant_id: str, target: str, values: Mapping[str, Any], *, by: str | None = None
) -> list[str]:
    """Set metadata fields on a dataset or attribute. Returns the fields that changed."""
    dataset, attribute = await resolve(uow, tenant_id, target)
    kind = "attribute" if attribute is not None else "dataset"
    ref = attribute.attribute_id if attribute is not None else dataset.dataset_id
    fields = await _fields(uow, tenant_id, kind)
    changed = []
    for name, raw in values.items():
        if name not in fields:
            raise ValidationError(
                f"no {kind} metadata field called {name!r}",
                remedy=f"Fields: {', '.join(sorted(fields)) or 'none; add a template first'}.",
            )
        _, row = fields[name]
        value = coerce(field_spec(row), raw)
        if await uow.metadata.set_value(tenant_id, row.id, kind, ref, value, by=by):
            changed.append(name)
    return changed


async def set_context(
    uow: Any, tenant_id: str, target: str, text: str, *, by: str | None = None
) -> None:
    """Record business context: an amendment of the declaration, so it is versioned."""
    from prama.semantic.services.datasets import DatasetService

    dataset, attribute = await resolve(uow, tenant_id, target)
    service = DatasetService(uow)
    if attribute is None:
        await service.amend(
            tenant_id=tenant_id,
            dataset_id=dataset.dataset_id,
            reason="business context updated",
            authored_by=by,
            business_context=text.strip(),
        )
    else:
        await service.amend_attribute(
            tenant_id=tenant_id,
            attribute_id=attribute.attribute_id,
            reason="business context updated",
            authored_by=by,
            business_context=text.strip(),
        )


async def describe(uow: Any, tenant_id: str, target: str) -> dict[str, Any]:
    """A dataset with its business context, metadata, attributes and rules."""
    dataset, _ = await resolve(uow, tenant_id, target)
    names = {}
    for kind in ("dataset", "attribute"):
        for name, (_, row) in (await _fields(uow, tenant_id, kind)).items():
            names[row.id] = name
    values = await uow.metadata.current_values(tenant_id)
    by_object: dict[str, dict[str, Any]] = {}
    for v in values:
        if v.field_id in names:
            by_object.setdefault(v.object_ref, {})[names[v.field_id]] = json.loads(v.value_json)
    attributes = await uow.attributes.for_dataset(dataset.dataset_id, tenant_id=tenant_id)
    controls = await uow.controls.for_dataset(tenant_id, dataset.slug)
    return {
        "dataset": dataset.name,
        "slug": dataset.slug,
        "dataset_id": dataset.dataset_id,
        "description": dataset.description,
        "business_context": dataset.business_context,
        "metadata": by_object.get(dataset.dataset_id, {}),
        "attributes": [
            {
                "name": a.name,
                "attribute_id": a.attribute_id,
                "definition": a.definition,
                "business_context": a.business_context,
                "metadata": by_object.get(a.attribute_id, {}),
            }
            for a in attributes
        ],
        "rules": [
            {"control_id": c.control_id, "name": c.name, "pql": c.pql, "status": c.status}
            for c in controls
        ],
        "proposals": await proposals(uow, tenant_id, dataset_id=dataset.dataset_id),
    }


async def proposals(uow: Any, tenant_id: str, *, dataset_id: str = "") -> list[dict[str, Any]]:
    """Controls the estate's metadata implies, not yet accepted or rejected."""
    from prama.pql import parse_control

    fields: dict[str, tuple[Any, Any]] = {}
    for kind in ("dataset", "attribute"):
        for _, (template, row) in (await _fields(uow, tenant_id, kind)).items():
            fields[row.id] = (template, row)
    datasets = {v.dataset_id: v for v in await uow.datasets.list_current(tenant_id, limit=5000)}
    attributes: dict[str, tuple[Any, Any]] = {}
    for version in datasets.values():
        if dataset_id and version.dataset_id != dataset_id:
            continue
        for a in await uow.attributes.for_dataset(version.dataset_id, tenant_id=tenant_id):
            attributes[a.attribute_id] = (version, a)
    out = []
    for value in await uow.metadata.current_values(tenant_id):
        if value.field_id not in fields:
            continue
        template, row = fields[value.field_id]
        spec = field_spec(row)
        if value.object_kind == "dataset":
            version = datasets.get(value.object_ref)
            if version is None or (dataset_id and version.dataset_id != dataset_id):
                continue
            attribute_name = ""
        else:
            if value.object_ref not in attributes:
                continue
            version, attribute = attributes[value.object_ref]
            attribute_name = attribute.name
        for index, rule in enumerate(spec.rules):
            pql = render(
                rule,
                spec,
                json.loads(value.value_json),
                dataset=version.slug,
                attribute=attribute_name,
            )
            if pql is None:
                continue
            try:
                parse_control(pql)
            except PramaError as exc:
                out.append({"dataset": version.name, "pql": pql, "error": str(exc)[:200]})
                continue
            identity = (
                "metadata-"
                + hashlib.sha256(f"{row.id}|{value.object_ref}|{index}".encode()).hexdigest()[:24]
            )
            content_hash = hashlib.sha256(pql.encode("utf-8")).hexdigest()
            stored = await uow.controls.by_identity(tenant_id, identity)
            if stored is not None and stored.content_hash == content_hash:
                continue
            if await uow.rejections.was_rejected(tenant_id, identity, content_hash):
                continue
            where = f"{version.name}.{attribute_name}" if attribute_name else version.name
            out.append(
                {
                    "identity": identity,
                    "rule": f"metadata:{template.name}.{row.name}",
                    "dataset": version.name,
                    "dataset_id": version.dataset_id,
                    "pql": pql,
                    "content_hash": content_hash,
                    "sentence": f"{where} has {row.label or row.name} = "
                    f"{json.loads(value.value_json)!r}; "
                    f"{rule.note or 'the check follows from it'}.",
                    "amends": stored is not None,
                }
            )
    return out


async def search(
    uow: Any, tenant_id: str, text: str, *, limit: int = 30, any_word: bool = False
) -> list[dict[str, Any]]:
    """Datasets and attributes whose name, description, business context, definition
    or metadata mention every word of *text*. Keyword matching today; the same
    function is where an embedding search goes, over the same texts."""
    words = [w for w in text.lower().split() if w]
    if not words:
        return []
    values: dict[str, list[str]] = {}
    for v in await uow.metadata.current_values(tenant_id):
        values.setdefault(v.object_ref, []).append(v.value_json.lower())
    hits: list[tuple[int, dict[str, Any]]] = []

    def score(parts: list[str]) -> int:
        blob = " ".join(parts).lower()
        present = [w for w in words if w in blob]
        if not present or (not any_word and len(present) < len(words)):
            return 0
        return len(present) * 10 + sum(blob.count(w) for w in present)

    for version in await uow.datasets.list_current(tenant_id, limit=5000):
        found = score(
            [
                version.name,
                version.description,
                version.purpose,
                version.business_context,
                *values.get(version.dataset_id, []),
            ]
        )
        if found:
            hits.append(
                (
                    found,
                    {
                        "kind": "dataset",
                        "name": version.name,
                        "slug": version.slug,
                        "context": version.business_context or version.description,
                    },
                )
            )
        for a in await uow.attributes.for_dataset(version.dataset_id, tenant_id=tenant_id):
            found = score(
                [a.name, a.definition, a.business_context, *values.get(a.attribute_id, [])]
            )
            if found:
                hits.append(
                    (
                        found,
                        {
                            "kind": "attribute",
                            "name": f"{version.slug}.{a.name}",
                            "slug": version.slug,
                            "context": a.business_context or a.definition,
                        },
                    )
                )
    for term in await uow.glossary.search(tenant_id, words[0]):
        blob = " ".join([term.name, term.definition, term.synonyms_json]).lower()
        if any_word or all(w in blob for w in words):
            hits.append(
                (1, {"kind": "term", "name": term.name, "slug": "", "context": term.definition})
            )
    return [h for _, h in sorted(hits, key=lambda x: -x[0])[:limit]]


async def correlation(uow: Any, tenant_id: str) -> dict[str, Any]:
    """Groups of attributes that mean the same thing, the references that follow,
    and where one meaning is held inconsistently (`prama.semantic.correlate`)."""
    from prama.semantic.correlate import AttributeFact, findings, groups, references

    names: dict[str, str] = {}
    for template in await uow.metadata.templates(tenant_id, applies_to="attribute"):
        for row in await uow.metadata.fields(template.id):
            names[row.id] = row.name
    dataset_fields: dict[str, str] = {}
    for template in await uow.metadata.templates(tenant_id, applies_to="dataset"):
        for row in await uow.metadata.fields(template.id):
            dataset_fields[row.id] = row.name
    values: dict[str, dict[str, Any]] = {}
    for value in await uow.metadata.current_values(tenant_id):
        field = names.get(value.field_id) or dataset_fields.get(value.field_id)
        if field:
            values.setdefault(value.object_ref, {})[field] = json.loads(value.value_json)
    term_names = {t.id: t.name for t in await uow.glossary.terms(tenant_id)}
    bound: dict[str, set[str]] = {}
    for binding in await uow.glossary.bindings(tenant_id):
        if binding.object_kind == "attribute":
            bound.setdefault(binding.object_ref, set()).add(term_names.get(binding.term_id, ""))
    facts = []
    for version in await uow.datasets.list_current(tenant_id, limit=5000):
        keys = set((version.grain_json or {}).get("attributes") or [])
        keys |= set(values.get(version.dataset_id, {}).get("key") or [])
        for a in await uow.attributes.for_dataset(version.dataset_id, tenant_id=tenant_id):
            terms = set(bound.get(f"{version.slug}.{a.name}", set()))
            if a.glossary_term:
                terms.add(a.glossary_term)
            facts.append(
                AttributeFact(
                    dataset=version.slug,
                    attribute=a.name,
                    concept_property=a.concept_property_id or "",
                    terms=tuple(sorted(t for t in terms if t)),
                    semantic_type=a.semantic_type or "",
                    # A key, or a column declared unique: either identifies the
                    # dataset's entities, and so owns the meaning it carries.
                    is_key=a.name in keys or values.get(a.attribute_id, {}).get("unique") is True,
                    is_cde=bool(a.is_cde),
                    sensitivity=a.sensitivity,
                    metadata=values.get(a.attribute_id, {}),
                    described=bool(
                        (a.definition or "").strip() or (a.business_context or "").strip()
                    ),
                )
            )
    found = groups(facts)
    proposed = []
    for group in found:
        for ref in references(group):
            content_hash = hashlib.sha256(ref.pql.encode("utf-8")).hexdigest()
            if await uow.controls.by_identity(tenant_id, ref.identity) is not None:
                continue
            if await uow.rejections.was_rejected(tenant_id, ref.identity, content_hash):
                continue
            proposed.append(
                {
                    "identity": ref.identity,
                    "rule": ref.rule,
                    "dataset": ref.dataset,
                    "dataset_id": "",
                    "pql": ref.pql,
                    "content_hash": content_hash,
                    "sentence": ref.sentence,
                    "amends": False,
                }
            )
    return {
        "groups": [
            {"meaning": g.meaning, "by": g.by, "members": [m.qualified for m in g.members]}
            for g in found
        ],
        "findings": [f.to_dict() for g in found for f in findings(g)],
        "proposals": proposed,
        "queried_together": await queried_together(uow, tenant_id, facts),
    }


#: Queries in the window before two datasets read together are worth a steward's look.
TOGETHER_AT_LEAST = 3


async def queried_together(
    uow: Any, tenant_id: str, facts: list[Any], *, days: int = 30
) -> list[dict[str, Any]]:
    """Datasets the warehouse reads together, with a column in common and no relationship.

    A hint, never a proposal: two datasets in the same query share a name, not
    necessarily a meaning. Where one side's column of that name is a key and the
    other's is not, the likely relationship is suggested as PQL for a steward to
    judge. Like every usage signal, it never touches a score.
    """
    from datetime import UTC, datetime, timedelta

    from prama.semantic.services.priorities import _matches

    since = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
    together = await uow.usage.pairs(tenant_id, since=since)
    if not together:
        return []
    versions = await uow.datasets.list_current(tenant_id, limit=5000)
    related: set[frozenset[str]] = set()
    for version in versions:
        for rel in await uow.relationships.touching(tenant_id, version.dataset_id):
            related.add(frozenset({rel.from_dataset_id, rel.to_dataset_id}))
    by_slug = {v.slug: v for v in versions}
    columns: dict[str, dict[str, Any]] = {}
    for fact in facts:
        columns.setdefault(fact.dataset, {})[fact.attribute] = fact

    def slug_of(used: str) -> str:
        return next((v.slug for v in versions if _matches(used, v.slug)), "")

    out = []
    for (first, second), queries in sorted(together.items(), key=lambda p: -p[1]):
        a, b = slug_of(first), slug_of(second)
        if queries < TOGETHER_AT_LEAST or not a or not b or a == b:
            continue
        if frozenset({by_slug[a].dataset_id, by_slug[b].dataset_id}) in related:
            continue
        shared = sorted(set(columns.get(a, {})) & set(columns.get(b, {})))
        if not shared:
            continue
        suggested = []
        for name in shared:
            left, right = columns[a][name], columns[b][name]
            if (
                left.semantic_type
                and right.semantic_type
                and left.semantic_type != right.semantic_type
            ):
                continue
            if left.is_key != right.is_key:
                owner, other = (a, b) if left.is_key else (b, a)
                suggested.append(f"CHECK {other}.{name} REFERENCES {owner}.{name}")
        out.append(
            {
                "datasets": [a, b],
                "queries": queries,
                "shared": shared,
                "suggested": suggested,
                "detail": (
                    f"{a} and {b} were read by the same query {queries} times in {days} days, "
                    f"share {', '.join(shared)}, and have no declared relationship"
                ),
            }
        )
    return out


async def author_rule(
    uow: Any, tenant_id: str, slug: str, pql: str, *, by: str | None = None
) -> dict[str, Any]:
    """A rule written by hand against *slug*: proposed, active once somebody else approves it."""
    from prama.pql import parse_control

    text = pql.strip()
    control = parse_control(text)
    if control.target != slug:
        raise ValidationError(
            f"this rule is about {control.target or 'another dataset'}, not {slug}",
            remedy=f"Write it against {slug}, as in CHECK {slug}.column IS NOT NULL.",
        )
    identity = "authored-" + hashlib.sha256(text.encode()).hexdigest()[:24]
    row, version = await uow.controls.declare(
        tenant_id=tenant_id,
        identity=identity,
        pql=text,
        origin="declaration",
        rule="authored.metadata_page",
        status="proposed",
        authored_by=by,
        reason="written on the dataset's metadata page",
    )
    return {
        "control_id": str(row.id),
        "identity": identity,
        "status": version.status,
        "pql": text,
    }


async def templates(uow: Any, tenant_id: str) -> dict[str, Any]:
    """The estate's metadata templates with their fields, and the starters on offer."""
    out = []
    for row in await uow.metadata.templates(tenant_id):
        fields = [field_spec(f) for f in await uow.metadata.fields(row.id)]
        out.append(
            {
                "name": row.name,
                "applies_to": row.applies_to,
                "description": row.description,
                "status": row.status,
                "fields": [
                    {
                        "name": f.name,
                        "label": f.label,
                        "kind": f.kind,
                        "choices": list(f.choices),
                        "required": f.required,
                        "help": f.help,
                        "rules": [dataclasses.asdict(r) for r in f.rules],
                    }
                    for f in fields
                ],
            }
        )
    return {"templates": out, "starters": sorted(STARTER)}

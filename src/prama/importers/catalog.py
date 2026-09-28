"""Glossary terms and lineage from the catalogs a bank already has: Alation, Collibra, Manta.

Consuming them rather than competing with them. Each reader takes a vendor's
export (the JSON its REST API returns) and gives back three things, as every
Prama importer does: what came across, and what did not and why, one item at a
time. It never guesses:

* **Alation.** Terms from `/integration/v2/term/` (title, description,
  custom fields for synonyms and steward). Lineage from `/integration/v2/lineage/`
  objects, column level only. A lineage object with several sources *and*
  several targets does not say which source feeds which target, so it is
  dropped rather than cross-multiplied into edges nobody stated.
* **Collibra.** Business Term assets from `/rest/2.0/assets` (with their
  Definition attribute, and status). Other asset types are dropped, named.
* **Manta.** Its graph export: nodes with parents (column → table → schema)
  and edges. Direct flows become `derived` edges, filter flows `filter` edges;
  anything not between two columns is dropped.

Imported edges are stored as `imported:<vendor>` and never overwrite Prama's
own parse. Where the two disagree about a column, both are kept and the
difference is reported (`disagreements`).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import html
import re
from collections.abc import Mapping
from typing import Any

from prama.core.errors import ValidationError
from prama.importers.spi import Unmapped
from prama.lineage.graph import Column, Edge, Transform

_TAG = re.compile(r"<[^>]+>")


@dataclasses.dataclass(frozen=True, slots=True)
class ImportedTerm:
    name: str
    definition: str = ""
    synonyms: tuple[str, ...] = ()
    domain: str = ""
    steward: str = ""
    status: str = "accepted"
    external_id: str = ""


@dataclasses.dataclass
class CatalogImport:
    vendor: str
    terms: list[ImportedTerm] = dataclasses.field(default_factory=list)
    edges: list[Edge] = dataclasses.field(default_factory=list)
    dropped: list[Unmapped] = dataclasses.field(default_factory=list)

    def drop(self, source: str, reason: str) -> None:
        self.dropped.append(Unmapped(source=source, reason=reason))

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "terms": len(self.terms),
            "edges": len(self.edges),
            "dropped": [{"source": d.source, "reason": d.reason} for d in self.dropped],
        }


def _text(value: Any) -> str:
    return html.unescape(_TAG.sub(" ", str(value or ""))).strip()


def _items(document: Any, key: str = "results") -> list[Any]:
    if isinstance(document, Mapping):
        return list(document.get(key) or [])
    if isinstance(document, list):
        return document
    raise ValidationError(
        "the export is neither a list nor an object with results",
        remedy="Pass the JSON the vendor's API returned, unchanged.",
    )


# -- Alation -----------------------------------------------------------------


def _alation_field(term: Mapping[str, Any], name: str) -> Any:
    for field in term.get("custom_fields") or []:
        if str(field.get("field_name", "")).lower() == name:
            return field.get("value")
    return None


def alation_terms(document: Any) -> CatalogImport:
    result = CatalogImport("alation")
    for term in _items(document):
        title = str(term.get("title") or "").strip()
        if not title:
            result.drop(f"term {term.get('id', '?')}", "no title")
            continue
        synonyms = _alation_field(term, "synonyms") or []
        if isinstance(synonyms, str):
            synonyms = list(re.split(r"[,;]", synonyms))
        stewards = _alation_field(term, "steward") or []
        steward = ", ".join(
            str(s.get("name") or s.get("oid", "")) if isinstance(s, Mapping) else str(s)
            for s in (stewards if isinstance(stewards, list) else [stewards])
        )
        result.terms.append(
            ImportedTerm(
                name=title,
                definition=_text(term.get("description")),
                synonyms=tuple(str(s).strip() for s in synonyms if str(s).strip()),
                steward=steward,
                external_id=str(term.get("id", "")),
            )
        )
    return result


def _alation_column(node: Mapping[str, Any]) -> Column | None:
    """`ds_id.schema.table.column` for an attribute; None for anything else."""
    if str(node.get("otype", "")).lower() != "attribute":
        return None
    parts = str(node.get("key", "")).split(".")
    if len(parts) < 4:
        return None
    return Column(dataset=".".join(parts[1:-1]).lower(), name=parts[-1].lower())


def alation_lineage(document: Any) -> CatalogImport:
    result = CatalogImport("alation")
    for index, item in enumerate(_items(document)):
        where = f"lineage {item.get('dataflow_id') or index}"
        sources = [_alation_column(n) for n in item.get("source_nodes") or []]
        targets = [_alation_column(n) for n in item.get("target_nodes") or []]
        if None in sources or None in targets or not sources or not targets:
            result.drop(where, "not column-level; Prama's lineage is between columns")
            continue
        if len(sources) > 1 and len(targets) > 1:
            result.drop(
                where,
                f"{len(sources)} sources and {len(targets)} targets: which feeds which is "
                "not stated, and pairing them would invent edges",
            )
            continue
        for source in sources:
            for target in targets:
                assert source is not None and target is not None
                result.edges.append(
                    Edge(source, target, Transform.DERIVED, produced_by=f"alation:{where}")
                )
    return result


# -- Collibra ----------------------------------------------------------------

_COLLIBRA_STATUS = {
    "accepted": "accepted",
    "approved": "accepted",
    "candidate": "candidate",
    "under review": "candidate",
    "obsolete": "deprecated",
    "deprecated": "deprecated",
}


def collibra_terms(document: Any) -> CatalogImport:
    result = CatalogImport("collibra")
    for asset in _items(document):
        kind = str((asset.get("type") or {}).get("name", ""))
        name = str(asset.get("displayName") or asset.get("name") or "").strip()
        if kind != "Business Term":
            result.drop(
                name or str(asset.get("id", "?")), f"a {kind or 'untyped'} asset, not a term"
            )
            continue
        if not name:
            result.drop(str(asset.get("id", "?")), "no name")
            continue
        attributes = {
            str((a.get("type") or {}).get("name", "")).lower(): a.get("value")
            for a in asset.get("attributes") or []
        }
        status = str((asset.get("status") or {}).get("name", "accepted")).lower()
        synonyms = attributes.get("synonym") or attributes.get("synonyms") or ""
        result.terms.append(
            ImportedTerm(
                name=name,
                definition=_text(attributes.get("definition")),
                synonyms=tuple(s.strip() for s in re.split(r"[,;]", str(synonyms)) if s.strip()),
                domain=str((asset.get("domain") or {}).get("name", "")),
                status=_COLLIBRA_STATUS.get(status, "candidate"),
                external_id=str(asset.get("id", "")),
            )
        )
    return result


# -- Manta -------------------------------------------------------------------


def manta(document: Any) -> CatalogImport:
    result = CatalogImport("manta")
    if not isinstance(document, Mapping):
        raise ValidationError("a Manta export is an object", remedy="Pass nodes and edges.")
    nodes = {str(n.get("id")): n for n in document.get("nodes") or []}

    def column(node_id: str) -> Column | None:
        node = nodes.get(node_id)
        if node is None or str(node.get("type", "")).lower() != "column":
            return None
        table = nodes.get(str(node.get("parent", "")))
        if table is None:
            return None
        path = [str(table.get("name", ""))]
        parent = nodes.get(str(table.get("parent", "")))
        if parent is not None and str(parent.get("type", "")).lower() == "schema":
            path.insert(0, str(parent.get("name", "")))
        return Column(dataset=".".join(path).lower(), name=str(node.get("name", "")).lower())

    for edge in document.get("edges") or []:
        source, target = column(str(edge.get("source"))), column(str(edge.get("target")))
        kind = str(edge.get("type", "DIRECT")).upper()
        where = f"edge {edge.get('source')} -> {edge.get('target')}"
        if source is None or target is None:
            result.drop(where, "not between two columns")
            continue
        transform = Transform.FILTER if kind in ("FILTER", "INDIRECT") else Transform.DERIVED
        result.edges.append(Edge(source, target, transform, produced_by=f"manta:{kind.lower()}"))
    return result


READERS = {
    ("alation", "terms"): alation_terms,
    ("alation", "lineage"): alation_lineage,
    ("collibra", "terms"): collibra_terms,
    ("manta", "lineage"): manta,
}


def read(vendor: str, what: str, document: Any) -> CatalogImport:
    reader = READERS.get((vendor, what))
    if reader is None:
        raise ValidationError(
            f"no {what} reader for {vendor}",
            remedy="Terms: alation, collibra. Lineage: alation, manta (or OpenLineage).",
        )
    return reader(document)


# -- storing -----------------------------------------------------------------


async def ingest(
    uow: Any, tenant_id: str, imported: CatalogImport, *, source: str = ""
) -> dict[str, Any]:
    """Store terms (bound to same-named concepts) and edges; report what did not come across."""
    from prama.lineage.sql import Gap

    created = updated = bound = 0
    concepts = {c.name.lower(): c for c in await uow.concepts.list_current(tenant_id, limit=5000)}
    for term in imported.terms:
        row, was_new = await uow.glossary.upsert(
            tenant_id,
            name=term.name,
            definition=term.definition,
            synonyms=list(term.synonyms),
            domain=term.domain,
            steward=term.steward,
            status=term.status,
            source=imported.vendor,
            external_id=term.external_id or None,
        )
        created, updated = created + was_new, updated + (not was_new)
        for label in (term.name, *term.synonyms):
            concept = concepts.get(label.lower())
            if concept is not None:
                await uow.glossary.bind(
                    tenant_id, row.name, "concept", str(concept.concept_id), how="name_match"
                )
                bound += 1
                break
    run_edges = 0
    if imported.edges:
        lineage = await uow.lineage.ensure_source(
            tenant_id,
            (source or f"{imported.vendor}-import")[:128],
            kind="import",
            location=imported.vendor,
        )
        run = await uow.lineage.record_run(
            tenant_id,
            lineage,
            [(imported.edges, f"imported:{imported.vendor}", "parsed", 1.0)],
            [Gap(kind="dropped", detail=f"{d.source}: {d.reason}") for d in imported.dropped],
            statements=len(imported.edges) + len(imported.dropped),
            understood=len(imported.edges) / max(1, len(imported.edges) + len(imported.dropped)),
        )
        run_edges = run.edges
    return {
        **imported.to_dict(),
        "terms_created": created,
        "terms_updated": updated,
        "bound_to_concepts": bound,
        "edges_recorded": run_edges,
    }


async def disagreements(uow: Any, tenant_id: str) -> list[dict[str, Any]]:
    """Columns where an imported catalog and Prama's own parse name different sources."""
    theirs: dict[str, dict[str, set[str]]] = {}
    ours: dict[str, set[str]] = {}
    for edge in await uow.lineage.edges(tenant_id):
        target = f"{edge.target_dataset}.{edge.target_column}"
        source = f"{edge.source_dataset}.{edge.source_column}"
        if edge.method.startswith("imported:"):
            vendor = edge.method.split(":", 1)[1]
            theirs.setdefault(target, {}).setdefault(vendor, set()).add(source)
        else:
            ours.setdefault(target, set()).add(source)
    out = []
    for target, by_vendor in sorted(theirs.items()):
        if target not in ours:
            continue
        for vendor, sources in sorted(by_vendor.items()):
            if sources != ours[target]:
                out.append(
                    {
                        "column": target,
                        "vendor": vendor,
                        "theirs_only": sorted(sources - ours[target]),
                        "ours_only": sorted(ours[target] - sources),
                    }
                )
    return out

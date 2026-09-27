"""What a change to SQL puts at risk, as a CI gate.

Compares the lineage two versions of the same SQL produce, finds the columns
whose feeding changed or that are no longer produced at all, and follows each
through the estate's persisted lineage to everything downstream. Then it names
what matters about that: the controls on the affected datasets and the
attestations signed over them. `prama lineage impact --diff` exits 3 when
anything is at risk, so a pipeline can stop a change before it ships.

Filter dependencies are listed as affected, not waived. Prama's lineage treats
a wrong filter as carried in full, because it changes which rows exist, and a
dropped column breaks every query that filters on it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.lineage.graph import Column, Edge, LineageGraph
from prama.lineage.sql import SqlLineage


@dataclasses.dataclass(frozen=True, slots=True)
class ChangeImpact:
    """Everything one change reaches, and what of it is at risk."""

    changed: tuple[str, ...]
    reached: tuple[tuple[str, float], ...]
    datasets: tuple[str, ...]
    controls: tuple[dict[str, str], ...] = ()
    attestations: tuple[dict[str, str], ...] = ()

    @property
    def at_risk(self) -> bool:
        return bool(self.controls or self.attestations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": list(self.changed),
            "reached": [{"column": c, "impact": round(i, 3)} for c, i in self.reached],
            "datasets": list(self.datasets),
            "controls": list(self.controls),
            "attestations": list(self.attestations),
            "at_risk": self.at_risk,
        }


def _feeds(edges: tuple[Edge, ...]) -> dict[Column, set[tuple[str, str]]]:
    out: dict[Column, set[tuple[str, str]]] = {}
    for edge in edges:
        out.setdefault(edge.target, set()).add((edge.source.qualified, edge.transform.value))
    return out


def changed_columns(before: str, after: str, *, dialect: str = "ansi") -> list[Column]:
    """Target columns whose inputs differ, or that the new SQL no longer produces."""
    reader = SqlLineage(dialect=dialect)
    old = _feeds(reader.extract(before).edges)
    new = _feeds(reader.extract(after).edges)
    return sorted(
        (column for column in old.keys() | new.keys() if old.get(column) != new.get(column)),
        key=lambda c: c.qualified,
    )


async def assess(
    uow: Any, tenant_id: str, changed: list[Column], graph: LineageGraph | None = None
) -> ChangeImpact:
    """Follow *changed* through the tenant's lineage; name the controls and
    attestations on every dataset it reaches, the changed ones included."""
    graph = graph or await uow.lineage.graph(tenant_id)
    reached: dict[str, float] = {}
    for column in changed:
        for item in graph.blast_radius(column).reached:
            key = item.column.qualified
            reached[key] = max(reached.get(key, 0.0), item.impact)
    datasets = sorted(
        {c.dataset for c in changed}
        | {key.rpartition(".")[0] for key in reached if key.rpartition(".")[0]}
    )
    controls = []
    for dataset in datasets:
        for version in await uow.controls.for_dataset(tenant_id, dataset):
            controls.append(
                {
                    "dataset": dataset,
                    "control": version.control_id,
                    "name": version.name,
                    "severity": version.severity,
                }
            )
    attestations = [
        {"scope": a.scope, "attester": a.attester_name, "period_end": a.period_end}
        for a in await uow.attestations.current(tenant_id)
        if a.scope in datasets
    ]
    return ChangeImpact(
        changed=tuple(c.qualified for c in changed),
        reached=tuple(sorted(reached.items(), key=lambda kv: -kv[1])),
        datasets=tuple(datasets),
        controls=tuple(controls),
        attestations=tuple(attestations),
    )
